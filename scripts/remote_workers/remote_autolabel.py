#!/usr/bin/env python3
"""
SAFARI Remote Worker — Autolabeling.

Standalone script that mirrors Modal autolabel_job.py for local GPU execution.
Supports SAM3 text prompts and YOLO custom model modes.

Architecture:
    This is a thin wrapper around backend.core.autolabel_core.
    All inference logic is shared with Modal autolabel_job.py for full parity.

Usage:
    echo '{"job_id": "...", ...}' | python remote_autolabel.py

Expected JSON input:
    {
        "job_id": "uuid",
        "dataset_id": "uuid",
        "image_urls": {"image_id": "presigned_url", ...},
        "prompt_type": "text",  # "text", "bbox", "point", or "yolo"
        "prompt_value": "mammal, bird",
        "confidence": 0.25,
        "prompt_class_map": {"mammal": 0, "bird": 1}
    }

Output:
    JSON result to stdout with success/failure and detection counts.
"""

import hashlib
import json
import os
import shutil
import sys
import tempfile
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

# Add parent directory to path for remote_utils
sys.path.insert(0, str(Path(__file__).parent))

# Add SAFARI root to path for backend.core imports
# Try TYTO_ROOT env var first, then detect from script location
tyto_root = os.environ.get("TYTO_ROOT")
if not tyto_root:
    # Assume script is at scripts/remote_workers/remote_autolabel.py
    tyto_root = str(Path(__file__).parent.parent.parent)
if tyto_root not in sys.path:
    sys.path.insert(0, tyto_root)

from remote_utils import (
    LogCapture,
    download_file,
    download_from_r2_cached,
    get_r2_client,
    get_r2_bucket,
    get_supabase,
    get_models_dir,
)


def autolabel_images(
    job_id: str,
    dataset_id: str,
    image_urls: dict[str, str],
    prompt_type: str,
    prompt_value: str = "",
    class_id: int = 0,
    confidence: float = 0.25,
    video_mode: bool = False,
    keyframe_meta: dict = None,
    model_id: str = "",
    model_r2_path: str = "",  # R2 path for custom YOLO model
    prompt_class_map: dict = None,
    bbox_padding: float = 0.03,  # SAM3 box expansion fraction
    generate_bboxes: bool = True,  # Generate bounding box annotations
    generate_masks: bool = False,  # Generate mask polygon annotations
    existing_annotations: dict = None,  # {image_id: [ann_dict]} for bbox-prompt mask shortcut
) -> dict:
    """
    Main auto-labeling function for local GPU execution.
    
    Thin wrapper around backend.core.autolabel_core — all inference logic is shared
    with Modal autolabel_job.py for full parity.
    """
    # Import shared core logic
    from backend.core.autolabel_core import (
        run_yolo_autolabel,
        run_sam3_autolabel,
        run_sam3_mask_from_bboxes,
        yolo_lines_to_annotations,
    )
    
    os.environ["ULTRALYTICS_AUTOUPDATE"] = "false"
    
    supabase = get_supabase()
    s3 = get_r2_client()
    bucket = get_r2_bucket()
    
    work_dir = Path(tempfile.mkdtemp(prefix="autolabel_"))
    image_dir = work_dir / "images"
    image_dir.mkdir()
    
    with LogCapture(job_id, table="autolabel_jobs", log_column="logs"):
        try:
            # Update status
            supabase.table("autolabel_jobs").update({
                "status": "running",
                "started_at": "now()",
            }).eq("id", job_id).execute()
            
            print(f"Starting auto-labeling job {job_id}")
            print(f"Dataset: {dataset_id}")
            print(f"Prompt type: {prompt_type}")
            print(f"Confidence: {confidence}")
            print(f"Target images: {len(image_urls)}")
            
            # === Download images ===
            print("\n=== Downloading images ===")
            image_paths = {}
            failed_downloads = []
            
            with ThreadPoolExecutor(max_workers=10) as executor:
                futures = {}
                for image_id, url in image_urls.items():
                    dest = image_dir / f"{image_id}.jpg"
                    futures[executor.submit(download_file, url, dest)] = (image_id, dest)
                
                for future in as_completed(futures):
                    image_id, dest = futures[future]
                    if future.result():
                        image_paths[image_id] = dest
                    else:
                        failed_downloads.append(image_id)
            
            if failed_downloads:
                print(f"Warning: Failed to download {len(failed_downloads)} images")
            print(f"Downloaded {len(image_paths)} images successfully")
            
            # === Run inference via shared core ===
            if prompt_type == "yolo":
                if not model_r2_path:
                    raise ValueError("model_r2_path is required for YOLO mode")
                
                # Download YOLO model from R2 with caching
                model_hash = hashlib.md5(model_r2_path.encode()).hexdigest()[:12]
                model_path = get_models_dir() / f"yolo_{model_hash}.pt"
                if not download_from_r2_cached(model_r2_path, model_path):
                    raise RuntimeError(f"Failed to download YOLO model from {model_r2_path}")
                
                print(f"\n=== YOLO Mode: {model_path} ===")
                results_by_image, class_names_lookup = run_yolo_autolabel(
                    image_paths=image_paths,
                    yolo_model_path=str(model_path),
                    confidence=confidence,
                )
            else:
                # SAM3 mode — get class names from project for text mode
                class_names_lookup = None
                if prompt_type == "text":
                    try:
                        dataset_result = supabase.table("datasets").select("project_id").eq("id", dataset_id).single().execute()
                        project_id = dataset_result.data.get("project_id")
                        project_result = supabase.table("projects").select("classes").eq("id", project_id).single().execute()
                        existing_classes = project_result.data.get("classes") or []
                        class_names_lookup = {i: name for i, name in enumerate(existing_classes)}
                        print(f"Loaded {len(existing_classes)} classes from project")
                    except Exception as e:
                        print(f"Warning: Could not fetch classes: {e}")
                
                # Use local SAM3 model
                tyto_home = Path.home() / ".tyto"
                sam3_model_path = tyto_home / "models" / "sam3.pt"
                
                if not sam3_model_path.exists():
                    raise FileNotFoundError(
                        f"SAM3 model not found at {sam3_model_path}. "
                        "Run: modal volume get sam3-volume /sam3.pt ~/.tyto/models/sam3.pt"
                    )
                
                print(f"\n=== SAM3 Mode ===")
                
                # Fast path: mask-only with existing bboxes
                if generate_masks and not generate_bboxes and existing_annotations:
                    print("Using bbox-prompt fast path for mask generation")
                    mask_results = run_sam3_mask_from_bboxes(
                        image_paths=image_paths,
                        existing_annotations=existing_annotations,
                        sam3_model_path=str(sam3_model_path),
                    )
                    results_by_image = {}
                    for img_id, anns in mask_results.items():
                        results_by_image[img_id] = {"yolo_lines": [], "mask_polygons": [], "_prebuilt_annotations": anns}
                else:
                    results_by_image, class_names_lookup = run_sam3_autolabel(
                        image_paths=image_paths,
                        prompt_type=prompt_type,
                        prompt_value=prompt_value,
                        sam3_model_path=str(sam3_model_path),
                        confidence=confidence,
                        prompt_class_map=prompt_class_map,
                        class_names_lookup=class_names_lookup,
                        save_masks=generate_masks,
                    )
            
            # === Upload label files & update annotations ===
            print("\n=== Uploading label files & updating annotations ===")
            uploaded_count = 0
            total_detections = 0
            total_masks = 0
            
            for image_id, result_data in results_by_image.items():
                # Handle both YOLO (list) and SAM3 (dict) result formats
                if isinstance(result_data, list):
                    yolo_lines = result_data
                    mask_polygons = []
                    prebuilt_annotations = None
                else:
                    yolo_lines = result_data.get("yolo_lines", [])
                    mask_polygons = result_data.get("mask_polygons", [])
                    prebuilt_annotations = result_data.get("_prebuilt_annotations")
                
                # Upload YOLO label file to R2
                if yolo_lines:
                    label_content = "\n".join(yolo_lines)
                    total_detections += len(yolo_lines)
                    
                    if video_mode and keyframe_meta and image_id in keyframe_meta:
                        meta = keyframe_meta[image_id]
                        video_id = meta.get("video_id", "")
                        frame_number = meta.get("frame_number", 0)
                        label_path = f"datasets/{dataset_id}/labels/{video_id}_f{frame_number}.txt"
                    else:
                        label_path = f"datasets/{dataset_id}/labels/{image_id}.txt"
                    
                    try:
                        s3.put_object(
                            Bucket=bucket,
                            Key=label_path,
                            Body=label_content.encode('utf-8'),
                        )
                        uploaded_count += 1
                    except Exception as e:
                        print(f"Error uploading label for {image_id}: {e}")
                
                # Build annotations for Supabase
                if prebuilt_annotations is not None:
                    annotations_list = prebuilt_annotations
                else:
                    annotations_list = yolo_lines_to_annotations(
                        yolo_lines, class_names_lookup,
                        mask_polygons=mask_polygons if mask_polygons else None,
                    )
                
                masks_in_image = sum(1 for a in annotations_list if "mask_polygon" in a)
                total_masks += masks_in_image
                ann_count = len(annotations_list)
                
                try:
                    if video_mode:
                        supabase.table("keyframes").update({
                            "annotation_count": ann_count,
                            "annotations": annotations_list,
                        }).eq("id", image_id).execute()
                    else:
                        supabase.table("images").update({
                            "annotation_count": ann_count,
                            "labeled": ann_count > 0,
                            "annotations": annotations_list,
                        }).eq("id", image_id).execute()
                except Exception as e:
                    print(f"Error updating annotations for {image_id}: {e}")
            
            # === Update job status ===
            processed_count = len(image_paths)
            supabase.table("autolabel_jobs").update({
                "status": "completed",
                "completed_at": "now()",
                "detections_count": total_detections,
                "processed_count": processed_count,
            }).eq("id", job_id).execute()
            
            print(f"\n=== Job completed: {total_detections} detections, {total_masks} masks ===")
            
            return {
                "success": True,
                "job_id": job_id,
                "processed_count": processed_count,
                "detections_count": total_detections,
                "masks_count": total_masks,
            }
            
        except Exception as e:
            import traceback
            error_msg = str(e)
            print(f"Autolabeling failed: {error_msg}")
            traceback.print_exc()
            
            supabase.table("autolabel_jobs").update({
                "status": "failed",
                "completed_at": "now()",
                "error_message": error_msg,
            }).eq("id", job_id).execute()
            
            return {
                "success": False,
                "job_id": job_id,
                "error": error_msg,
            }
            
        finally:
            shutil.rmtree(work_dir, ignore_errors=True)


def main():
    """Read job params from stdin, execute autolabeling, output result."""
    try:
        params = json.load(sys.stdin)
    except json.JSONDecodeError as e:
        print(json.dumps({"success": False, "error": f"Invalid JSON input: {e}"}))
        sys.exit(1)
    
    result = autolabel_images(**params)
    print(json.dumps(result))


if __name__ == "__main__":
    main()
