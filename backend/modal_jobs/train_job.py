"""
Modal Training Job — GPU training for YOLO11 models.

Thin wrapper around shared core (backend/core/train_detect_core.py).
Environment-specific: Modal decorators, client initialization, LogCapture.

Usage (from Reflex app):
    fn = modal.Function.from_name("yolo-training", "train_yolo")
    fn.spawn(run_id=..., project_id=..., ...)
"""

import io
import os
import shutil
import sys
import tempfile
import threading
import time
from pathlib import Path

import modal

# Modal App configuration
app = modal.App("yolo-training")

# Build the container image with all dependencies
image = (
    modal.Image.debian_slim(python_version="3.11")
    .apt_install("libgl1-mesa-glx", "libglib2.0-0")  # OpenCV dependencies
    .pip_install(
        "ultralytics>=8.3.0",  # YOLO11
        "boto3",
        "supabase",
        "requests",
    )
    # Mount backend/core for shared training logic
    .env({"PYTHONPATH": "/root"})
    .add_local_python_source("backend")
)


def download_file(url: str, dest_path: Path) -> bool:
    """Download a file from a presigned URL."""
    import requests
    
    try:
        response = requests.get(url, timeout=60)
        response.raise_for_status()
        dest_path.parent.mkdir(parents=True, exist_ok=True)
        dest_path.write_bytes(response.content)
        return True
    except Exception as e:
        print(f"Failed to download {url}: {e}")
        return False


class LogCapture:
    """Capture stdout and stderr and stream to Supabase."""

    def __init__(self, run_id: str, flush_interval: int = 2):
        self.run_id = run_id
        self.flush_interval = flush_interval
        self.log_buffer = io.StringIO()
        self.lock = threading.Lock()
        self.stop_event = threading.Event()
        self.thread = None
        self.original_stdout = sys.stdout
        self.original_stderr = sys.stderr

    def __enter__(self):
        sys.stdout = self
        sys.stderr = self
        self.thread = threading.Thread(target=self._flush_loop, daemon=True)
        self.thread.start()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        # Signal thread to stop
        self.stop_event.set()
        # Don't wait long for daemon thread - it will die with the process anyway
        if self.thread:
            self.thread.join(timeout=1)
        # Restore stdout/stderr BEFORE final flush to avoid recursion
        sys.stdout = self.original_stdout
        sys.stderr = self.original_stderr
        # Final flush with short timeout (non-blocking)
        self._flush_buffer(timeout=3)

    def write(self, message):
        self.original_stdout.write(message)  # Keep local logging
        with self.lock:
            self.log_buffer.write(message)

    def flush(self):
        self.original_stdout.flush()

    def _flush_loop(self):
        while not self.stop_event.is_set():
            time.sleep(self.flush_interval)
            self._flush_buffer()

    def _flush_buffer(self, timeout: int = 10):
        import traceback
        from supabase import create_client
        
        try:
            with self.lock:
                content = self.log_buffer.getvalue()
                if not content:
                    return
                # Clear buffer
                self.log_buffer.seek(0)
                self.log_buffer.truncate(0)

            # Send to Supabase directly with timeout protection
            url = os.environ.get("SUPABASE_URL")
            key = os.environ.get("SUPABASE_KEY")
            if not url or not key:
                return  # Can't flush without credentials
            
            supabase = create_client(url, key)
            
            # 1. Fetch current logs
            res = supabase.table("training_runs").select("logs").eq("id", self.run_id).single().execute()
            current = res.data.get("logs", "") or ""
            
            # 2. Update
            new_logs = current + content
            supabase.table("training_runs").update({"logs": new_logs}).eq("id", self.run_id).execute()

        except Exception as e:
            # Fallback output to ensure we see the error - but don't block
            try:
                self.original_stderr.write(f"\n[LogCapture Error] {e}\n")
            except:
                pass  # Give up silently if we can't even log the error


@app.function(
    image=image,
    gpu="A10G",
    timeout=7200,  # 2 hours max
    enable_memory_snapshot=True,  # Dramatically reduces cold start time
    secrets=[
        modal.Secret.from_name("r2-credentials"),
        modal.Secret.from_name("supabase-credentials"),
    ],
)
def train_yolo(
    run_id: str,
    project_id: str,
    dataset_ids: list[str],
    image_urls: dict[str, str],  # {filename: presigned_url}
    annotations: dict[str, list[dict]],  # {filename.txt: [{class_id, x, y, width, height}, ...]}
    classes: list[str],
    config: dict,  # {epochs, model_size, batch_size}
    train_split_ratio: float = 0.8,  # Configurable train/val split
    val_image_urls: dict[str, str] = None,  # Explicit validation images
    val_annotations: dict[str, list[dict]] = None,  # Explicit validation annotations
    base_weights_r2_path: str = None,  # R2 path to weights for continued training
    parent_run_id: str = None,  # Parent run ID for lineage tracking
) -> dict:
    """
    Main training function executed on Modal GPU.
    
    Thin wrapper around shared core training functions.
    """
    import boto3
    from botocore.config import Config
    from supabase import create_client
    
    # Import shared core functions
    from backend.core.train_detect_core import (
        generate_yolo_labels,
        download_images,
        create_train_val_split,
        organize_train_val_structure,
        create_yolo_data_yaml,
        run_yolo_detection_training,
        run_validation_curves,
        collect_detection_artifacts,
    )
    
    # Initialize clients
    supabase = create_client(
        os.environ["SUPABASE_URL"],
        os.environ["SUPABASE_KEY"],
    )
    
    s3 = boto3.client(
        's3',
        endpoint_url=os.environ['R2_ENDPOINT_URL'],
        aws_access_key_id=os.environ['R2_ACCESS_KEY_ID'],
        aws_secret_access_key=os.environ['R2_SECRET_ACCESS_KEY'],
        config=Config(signature_version='s3v4'),
        region_name='auto',
    )
    bucket = os.environ['R2_BUCKET_NAME']
    
    # Create temp directory for dataset
    dataset_dir = Path(tempfile.mkdtemp(prefix="yolo_training_"))
    download_dir = dataset_dir / "downloads"
    download_dir.mkdir()
    
    with LogCapture(run_id):
        try:
            # Update status to 'running'
            supabase.table("training_runs").update({
                "status": "running",
                "started_at": "now()",
            }).eq("id", run_id).execute()
            
            print(f"Starting training run {run_id}")
            print(f"Config: {config}")
            print(f"Classes: {classes}")
            print(f"Images: {len(image_urls)}, Labels: {len(annotations)}")
            
            # === Step 1: Download images and generate labels ===
            print("Downloading images...")
            failed = download_images(image_urls, download_dir, download_file)
            if failed:
                print(f"Warning: Failed to download {len(failed)} images")
            
            print("Generating YOLO labels from annotations...")
            label_count = generate_yolo_labels(annotations, download_dir)
            print(f"Generated {label_count} label files")
            
            # === Step 2: Create train/val split ===
            print("Creating train/val split...")
            train_images, val_images, val_download_dir = create_train_val_split(
                download_dir,
                train_split_ratio,
                val_image_urls,
                val_annotations,
                download_file,
            )
            
            # Organize into YOLO structure
            organize_train_val_structure(
                dataset_dir, download_dir, train_images, val_images, val_download_dir
            )
            
            # Create data.yaml
            yaml_path = create_yolo_data_yaml(dataset_dir, classes)
            
            # === Step 3: Download base weights if continuing training ===
            base_weights_path = None
            if base_weights_r2_path:
                base_weights_path = dataset_dir / "base_weights.pt"
                print(f"Downloading weights from R2: {base_weights_r2_path}")
                s3.download_file(bucket, base_weights_r2_path, str(base_weights_path))
            
            # === Step 4: Run YOLO training ===
            print("Starting YOLO11 training...")
            metrics, run_dir = run_yolo_detection_training(
                dataset_dir, yaml_path, config, base_weights_path
            )
            
            # Run validation for curves
            val_dir = run_validation_curves(yaml_path, run_dir, dataset_dir)
            
            # === Step 5: Upload artifacts to R2 ===
            print("Uploading artifacts to R2...")
            r2_prefix = f"projects/{project_id}/runs/{run_id}"
            
            artifacts = collect_detection_artifacts(run_dir, val_dir)
            uploaded = []
            for local_path, name in artifacts:
                r2_path = f"{r2_prefix}/{name}"
                s3.put_object(
                    Bucket=bucket,
                    Key=r2_path,
                    Body=local_path.read_bytes(),
                )
                uploaded.append(r2_path)
                print(f"  Uploaded: {r2_path}")
            
            # === Step 6: Update training run status ===
            print("Updating training run status...")
            
            supabase.table("training_runs").update({
                "status": "completed",
                "completed_at": "now()",
                "metrics": metrics,
                "artifacts_r2_prefix": r2_prefix,
            }).eq("id", run_id).execute()
            
            print(f"Training run {run_id} completed successfully!")
            
            return {
                "success": True,
                "run_id": run_id,
                "metrics": metrics,
                "artifacts": uploaded,
            }
            
        except Exception as e:
            # Update status to 'failed'
            error_msg = str(e)
            print(f"Training failed: {error_msg}")
            
            supabase.table("training_runs").update({
                "status": "failed",
                "completed_at": "now()",
                "error_message": error_msg,
            }).eq("id", run_id).execute()
            
            return {
                "success": False,
                "run_id": run_id,
                "error": error_msg,
            }
            
        finally:
            # Cleanup
            shutil.rmtree(dataset_dir, ignore_errors=True)


# For local testing
if __name__ == "__main__":
    print("This module should be deployed to Modal, not run directly.")
    print("Deploy with: modal deploy backend/modal_jobs/train_job.py")
