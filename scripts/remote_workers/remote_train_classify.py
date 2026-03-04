#!/usr/bin/env python3
"""
SAFARI Remote Worker — YOLO Classification Training.

Standalone script that mirrors Modal train_classify_job.py for local GPU execution.

Usage:
    echo '{"run_id": "...", ...}' | python remote_train_classify.py

Expected JSON input:
    {
        "run_id": "uuid",
        "project_id": "uuid",
        "dataset_ids": ["uuid1", "uuid2"],
        "image_urls": {"filename.jpg": "presigned_url", ...},
        "annotations": {"filename.jpg": [{"class_name": "...", "x": 0.1, "y": 0.1, "width": 0.2, "height": 0.2}, ...]},
        "classes": ["class1", "class2"],
        "config": {"epochs": 100, "model_size": "n", "batch_size": 32, "image_size": 224},
        "train_split_ratio": 0.8
    }

Output:
    JSON result to stdout with success/failure and metrics.
"""

import io
import json
import os
import sys
import tempfile
from pathlib import Path

# Add backend to path for core imports
# Use TYTO_ROOT env var (set by SSH client) for portable path discovery
# Fallback to directory structure detection for local dev
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

# Import shared utilities from core
from backend.core.image_utils import crop_image_from_annotation

from remote_utils import (
    LogCapture,
    download_file,
    get_supabase,
    upload_to_r2,
)




def train_classifier(
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
) -> dict:
    """
    Main classification training function for local GPU execution.
    
    Mirrors Modal train_classify_job.train_classifier() but runs standalone.
    """
    supabase = get_supabase()
    
    # Create temp directory for dataset
    dataset_dir = Path(tempfile.mkdtemp(prefix="yolo_classify_training_"))
    download_dir = dataset_dir / "downloads"
    download_dir.mkdir()
    
    with LogCapture(run_id, table="training_runs", log_column="logs"):
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
            
            crop_counts, class_counts = create_classification_crops(
                dataset_dir, download_dir, annotations, classes,
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
            
            r2_prefix = f"projects/{project_id}/runs/{run_id}"
            
            # Collect artifacts (backbone-aware)
            artifact_pairs = collect_classification_artifacts(dataset_dir, backbone)
            artifacts_to_upload = [
                (local_path, f"{r2_prefix}/{name}") for local_path, name in artifact_pairs
            ]
            
            print(f"Training complete! Metrics: {metrics}")
            
            # === Step 4: Upload artifacts to R2 ===
            print("Uploading artifacts to R2...")
            
            uploaded = []
            for local_path, r2_path in artifacts_to_upload:
                if local_path.exists():
                    if upload_to_r2(local_path, r2_path):
                        uploaded.append(r2_path)
            
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
            shutil.rmtree(dataset_dir, ignore_errors=True)


def main():
    """Read job params from stdin, execute training, output result."""
    try:
        params = json.load(sys.stdin)
    except json.JSONDecodeError as e:
        print(json.dumps({"success": False, "error": f"Invalid JSON input: {e}"}))
        sys.exit(1)
    
    result = train_classifier(**params)
    print(json.dumps(result))


if __name__ == "__main__":
    main()
