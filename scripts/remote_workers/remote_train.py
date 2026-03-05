#!/usr/bin/env python3
"""
SAFARI Remote Worker — YOLO Detection Training.

Thin wrapper around shared core (backend/core/train_detect_core.py).
Environment-specific: stdin/stdout JSON protocol, remote_utils imports.

Usage:
    echo '{"run_id": "...", ...}' | python remote_train.py
    
    # Or with a JSON file:
    python remote_train.py < job_params.json

Expected JSON input:
    {
        "run_id": "uuid",
        "project_id": "uuid",
        "dataset_ids": ["uuid1", "uuid2"],
        "image_urls": {"filename.jpg": "presigned_url", ...},
        "annotations": {"filename.txt": [{"class_id": 0, "x": 0.1, ...}, ...]},
        "classes": ["class1", "class2"],
        "config": {"epochs": 50, "model_size": "n", "batch_size": 16},
        "train_split_ratio": 0.8,
        "val_image_urls": null,
        "val_annotations": null,
        "base_weights_r2_path": null
    }

Output:
    JSON result to stdout with success/failure and metrics.
"""

import json
import os
import shutil
import sys
import tempfile
from pathlib import Path

# Add backend to path for core imports
# Use TYTO_ROOT env var (set by SSH client) for portable path discovery
script_dir = Path(__file__).parent
tyto_root = os.environ.get("TYTO_ROOT")
if tyto_root:
    project_root = Path(tyto_root)
elif script_dir.name == "remote_workers":
    # Local dev: scripts/remote_workers/
    project_root = script_dir.parent.parent
else:
    # SSH client default: ~/.tyto/scripts/
    project_root = script_dir.parent
sys.path.insert(0, str(project_root))
sys.path.insert(0, str(script_dir))

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

from remote_utils import (
    LogCapture,
    download_file,
    download_from_r2,
    get_supabase,
    upload_to_r2,
)


def train_yolo(
    run_id: str,
    project_id: str,
    dataset_ids: list[str],
    image_urls: dict[str, str],
    annotations: dict[str, list[dict]],
    classes: list[str],
    config: dict,
    train_split_ratio: float = 0.8,
    val_image_urls: dict[str, str] = None,
    val_annotations: dict[str, list[dict]] = None,
    base_weights_r2_path: str = None,
    parent_run_id: str = None,
) -> dict:
    """
    Main training function for local GPU execution.
    
    Thin wrapper around shared core training functions.
    """
    supabase = get_supabase()
    
    # Create temp directory for dataset
    dataset_dir = Path(tempfile.mkdtemp(prefix="yolo_training_"))
    download_dir = dataset_dir / "downloads"
    download_dir.mkdir()
    
    with LogCapture(run_id, table="training_runs", log_column="logs"):
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
                download_from_r2(base_weights_r2_path, base_weights_path)
            
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
                if upload_to_r2(local_path, r2_path):
                    uploaded.append(r2_path)
            
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
            shutil.rmtree(dataset_dir, ignore_errors=True)


def main():
    """Read job params from stdin, execute training, output result."""
    try:
        params = json.load(sys.stdin)
    except json.JSONDecodeError as e:
        print(json.dumps({"success": False, "error": f"Invalid JSON input: {e}"}))
        sys.exit(1)
    
    result = train_yolo(**params)
    print(json.dumps(result))


if __name__ == "__main__":
    main()
