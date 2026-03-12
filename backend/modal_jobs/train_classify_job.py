"""
Modal Classification Training Job — GPU training for YOLOv11-Classify models.

This Modal function:
1. Downloads images from presigned R2 URLs
2. Crops images using annotation bounding boxes
3. Creates classification folder structure (class_name/crop.jpg)
4. Runs YOLOv11 classification training
5. Uploads artifacts (weights, results) to R2
6. Updates training run status in Supabase

The key difference from train_job.py:
- Uses annotation bounding boxes to create crops for each class
- Organizes crops in folder-per-class structure for classification
- Uses YOLO classification task instead of detection

Usage (from Reflex app):
    fn = modal.Function.from_name("yolo-classify-training", "train_classifier")
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

# Import shared utilities from core
from backend.core.image_utils import crop_image_from_annotation

# Modal App configuration
app = modal.App("yolo-classify-training")

# Build the container image with all dependencies
image = (
    modal.Image.debian_slim(python_version="3.11")
    .apt_install("libgl1-mesa-glx", "libglib2.0-0")  # OpenCV/PIL dependencies
    .pip_install(
        "ultralytics>=8.3.0",  # YOLO11
        "boto3",
        "supabase",
        "requests",
        "pillow",  # For image cropping
        "timm",    # ConvNeXt backbone
        "torch",
        "torchvision",
    )
    # Mount backend/core for shared utilities
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


# Note: crop_image_from_annotation is imported from backend.core.image_utils


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
def train_classifier(
    run_id: str,
    project_id: str,
    dataset_ids: list[str],
    image_urls: dict[str, str],  # {filename: presigned_url}
    annotations: dict[str, list[dict]],  # {filename: [{class_name, x, y, width, height}, ...]}
    classes: list[str],
    config: dict,  # {epochs, model_size, batch_size, image_size}
    train_split_ratio: float = 0.8,
    val_image_urls: dict[str, str] = None,  # Explicit validation images
    val_annotations: dict[str, list[dict]] = None,  # Explicit validation annotations
) -> dict:
    """
    Main classification training function executed on Modal GPU.
    
    Args:
        run_id: UUID of the training run
        project_id: UUID of the project
        dataset_ids: List of dataset UUIDs included in training
        image_urls: Dict mapping filename to presigned R2 URL for images
        annotations: Dict mapping filename to list of annotation dicts
                     Each annotation has: class_name, x, y, width, height (normalized)
        classes: List of class names
        config: Training configuration {epochs, model_size, batch_size, image_size}
        train_split_ratio: Ratio for train/val split if no explicit validation
        val_image_urls: Optional explicit validation image URLs
        val_annotations: Optional explicit validation annotations
    
    Returns:
        Dict with training results and metrics
    """
    import boto3
    from botocore.config import Config
    from supabase import create_client
    
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
    dataset_dir = Path(tempfile.mkdtemp(prefix="yolo_classify_training_"))
    download_dir = dataset_dir / "downloads"
    download_dir.mkdir()
    
    with LogCapture(run_id):
        try:
            # Update status to 'running'
            supabase.table("training_runs").update({
                "status": "running",
                "started_at": "now()",
            }).eq("id", run_id).execute()
            
            print(f"Starting classification training run {run_id}")
            print(f"Config: {config}")
            print(f"Classes: {classes}")
            print(f"Images: {len(image_urls)}, Annotations provided for {len(annotations)} images")
            
            # === Step 1: Download images in parallel ===
            print("Downloading images...")
            from backend.core.train_classify_core import (
                download_images_parallel,
                create_train_val_split_classification,
                create_classification_crops,
                ensure_validation_data,
                remove_empty_class_folders,
                train_classification,
                collect_classification_artifacts,
            )
            
            failed_downloads = download_images_parallel(image_urls, download_dir, download_file)
            if failed_downloads:
                print(f"Warning: Failed to download {len(failed_downloads)} files")
            
            # === Step 2: Create crops from annotations ===
            print("Creating crops from annotations...")
            
            train_filenames, val_filenames = create_train_val_split_classification(
                download_dir, image_urls, train_split_ratio, val_image_urls, download_file,
            )
            
            # Merge val_annotations into annotations so crops are created for both splits.
            # The train_filenames/val_filenames sets determine which split each crop goes to.
            all_annotations = dict(annotations)
            if val_annotations:
                all_annotations.update(val_annotations)
            
            crop_counts, class_counts = create_classification_crops(
                dataset_dir, download_dir, all_annotations, classes,
                train_filenames, val_filenames, crop_image_from_annotation,
            )
            
            print(f"Created crops - Train: {crop_counts['train']}, Val: {crop_counts['val']}")
            for class_name in classes:
                print(f"  {class_name}: train={class_counts[class_name]['train']}, val={class_counts[class_name]['val']}")
            
            # Validate we have enough data
            if crop_counts['train'] == 0:
                raise ValueError("No training crops created! Check that annotations match image filenames.")
            crop_counts = ensure_validation_data(dataset_dir, classes, crop_counts)
            
            # === Step 3: Run Classification Training (backbone-aware) ===
            valid_classes = remove_empty_class_folders(dataset_dir, classes, class_counts)
            
            if len(valid_classes) == 0:
                raise ValueError("No classes have any training samples!")
            
            # Run training (dispatches to YOLO or ConvNeXt based on config)
            metrics, weights_dir, backbone = train_classification(dataset_dir, valid_classes, config)
            
            print(f"Training complete! Metrics: {metrics}")
            
            # === Step 4: Upload artifacts to R2 ===
            print("Uploading artifacts to R2...")
            
            r2_prefix = f"projects/{project_id}/runs/{run_id}"
            
            # Collect artifacts (backbone-aware: .pt for YOLO, .pth for ConvNeXt)
            artifacts = collect_classification_artifacts(dataset_dir, backbone)
            
            uploaded = []
            for local_path, name in artifacts:
                r2_path = f"{r2_prefix}/{name}"
                if local_path.exists():
                    s3.put_object(
                        Bucket=bucket,
                        Key=r2_path,
                        Body=local_path.read_bytes(),
                    )
                    uploaded.append(r2_path)
                    print(f"  Uploaded: {r2_path}")
            
            # === Step 5: Update training run status ===
            print("Updating training run status...")
            
            supabase.table("training_runs").update({
                "status": "completed",
                "completed_at": "now()",
                "metrics": metrics,
                "artifacts_r2_prefix": r2_prefix,
                "top1_accuracy": metrics.get("top1_accuracy"),
                "top5_accuracy": metrics.get("top5_accuracy"),
            }).eq("id", run_id).execute()
            
            print(f"Classification training run {run_id} completed successfully!")
            
            return {
                "success": True,
                "run_id": run_id,
                "metrics": metrics,
                "artifacts": uploaded,
                "crop_counts": crop_counts,
            }
            
        except Exception as e:
            # Update status to 'failed'
            import traceback
            error_msg = str(e)
            print(f"Training failed: {error_msg}")
            traceback.print_exc()
            
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
    print("Deploy with: modal deploy backend/modal_jobs/train_classify_job.py")
