"""
Modal Auto-Label Job — GPU inference for SAM3 and YOLO-based automatic annotation.

This Modal function:
1. Downloads images from presigned R2 URLs
2. Runs SAM3 inference with text/bbox/point prompts OR YOLO detection with custom models
3. Converts detections to YOLO format
4. Uploads label files to R2
5. Updates annotation counts in Supabase
6. Streams logs to Supabase

Usage (from Reflex app):
    fn = modal.Function.from_name("yolo-autolabel", "autolabel_images")
    fn.spawn(job_id=..., dataset_id=..., ...)

Architecture:
    This is a thin wrapper around backend.core.autolabel_core.
    All inference logic is shared with remote_autolabel.py for Modal/Local GPU parity.
"""

import os
import io
import sys
import threading
import time
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor, as_completed

import modal

# Modal App configuration
app = modal.App("yolo-autolabel")

# SAM3 volume (for SAM3 model weights)
sam3_volume = modal.Volume.from_name("sam3-volume", create_if_missing=False)

# YOLO models volume (for custom trained YOLO models)
yolo_models_volume = modal.Volume.from_name("yolo-models-volume", create_if_missing=False)

# Compute paths before image definition (Modal requires resolved paths)
_THIS_DIR = Path(__file__).parent
_BACKEND_DIR = _THIS_DIR.parent
_CORE_DIR = _BACKEND_DIR / "core"
_BACKEND_INIT = _BACKEND_DIR / "__init__.py"

# Build the container image with all dependencies
image = (
    modal.Image.debian_slim(python_version="3.11")
    .apt_install("libgl1-mesa-glx", "libglib2.0-0", "git")  # OpenCV deps + git for CLIP
    .pip_install(
        "ultralytics>=8.3.237",  # SAM3 support
        "boto3",
        "supabase",
        "requests",
        "pillow",
        "ftfy",  # Required by CLIP
        "regex",  # Required by CLIP
        "timm",  # Required by some SAM3 backbones
        "huggingface_hub",
    )
    .pip_install(
        "git+https://github.com/ultralytics/CLIP.git"  # Ultralytics CLIP fork for SAM3
    )
    # Add /root to Python path for backend.core imports (must be before add_local_*)
    .env({"PYTHONPATH": "/root"})
    # Mount backend/core/ modules for shared autolabel logic (must be last)
    .add_local_dir(
        local_path=str(_CORE_DIR),
        remote_path="/root/backend/core",
    )
    .add_local_file(
        local_path=str(_BACKEND_INIT),
        remote_path="/root/backend/__init__.py",
    )
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

    def __init__(self, job_id: str, flush_interval: int = 2):
        self.job_id = job_id
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
        self.stop_event.set()
        if self.thread:
            self.thread.join(timeout=5)
        sys.stdout = self.original_stdout
        sys.stderr = self.original_stderr
        self._flush_buffer()  # Final flush

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

    def _flush_buffer(self):
        import os
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

            # Send to Supabase directly
            url = os.environ["SUPABASE_URL"]
            key = os.environ["SUPABASE_KEY"]
            supabase = create_client(url, key)
            
            # 1. Fetch current logs
            res = supabase.table("autolabel_jobs").select("logs").eq("id", self.job_id).single().execute()
            current = res.data.get("logs", "") or ""
            
            # 2. Update
            new_logs = current + content
            supabase.table("autolabel_jobs").update({"logs": new_logs}).eq("id", self.job_id).execute()

        except Exception as e:
            # Fallback output to ensure we see the error
            self.original_stderr.write(f"\n[LogCapture Error] {e}\n")
            traceback.print_exc(file=self.original_stderr)


@app.function(
    image=image,
    gpu="L40S",
    timeout=1800,  # 30 minutes max
    enable_memory_snapshot=True,  # Dramatically reduces cold start time
    volumes={
        "/models": sam3_volume,  # SAM3 model at /models/sam3.pt
        "/yolo_models": yolo_models_volume,  # Custom YOLO models at /yolo_models/{model_id}.pt
    },
    secrets=[
        modal.Secret.from_name("r2-credentials"),
        modal.Secret.from_name("supabase-credentials"),
    ],
)
def autolabel_images(
    job_id: str,
    dataset_id: str,
    image_urls: dict[str, str],  # {image_id: presigned_url}
    prompt_type: str,  # "text", "bbox", "point", or "yolo"
    prompt_value: str = "",  # text prompt or JSON for bbox/point (ignored for yolo)
    class_id: int = 0,  # Class ID to assign to detections (for SAM3 modes, legacy)
    confidence: float = 0.25,  # Confidence threshold
    video_mode: bool = False,  # True = processing video keyframes
    keyframe_meta: dict = None,  # {keyframe_id: {video_id, frame_number}} for video mode
    model_id: str = "",  # Model ID for YOLO mode (corresponds to /yolo_models/{model_id}.pt)
    prompt_class_map: dict = None,  # {prompt_term: class_id} for SAM3 text mode (mandatory mapping)
    bbox_padding: float = 0.03,  # SAM3 box expansion fraction
    generate_bboxes: bool = True,  # Generate bounding box annotations
    generate_masks: bool = False,  # Generate mask polygon annotations
    existing_annotations: dict = None,  # {image_id: [ann_dict]} for bbox-prompt mask shortcut
) -> dict:
    """
    Main auto-labeling function executed on Modal GPU.
    
    Thin wrapper around backend.core.autolabel_core — all inference logic is shared
    with remote_autolabel.py for full Modal/Local GPU parity.
    """
    import boto3
    import tempfile
    import shutil
    from botocore.config import Config
    from supabase import create_client
    
    # Import shared core logic
    from backend.core.autolabel_core import (
        run_yolo_autolabel,
        run_sam3_autolabel,
        run_sam3_mask_from_bboxes,
        yolo_lines_to_annotations,
    )
    
    # Disable AutoUpdate to prevent conflicts on Modal
    os.environ["ULTRALYTICS_AUTOUPDATE"] = "false"
    
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
    
    # Create temp directory
    work_dir = Path(tempfile.mkdtemp(prefix="autolabel_"))
    image_dir = work_dir / "images"
    image_dir.mkdir()
    
    with LogCapture(job_id):
        try:
            # Update status to 'running'
            supabase.table("autolabel_jobs").update({
                "status": "running",
                "started_at": "now()",
            }).eq("id", job_id).execute()
            
            print(f"Starting auto-labeling job {job_id}")
            print(f"Dataset: {dataset_id}")
            print(f"Prompt type: {prompt_type}")
            print(f"Prompt value: {prompt_value}")
            print(f"Model ID: {model_id}" if model_id else "Model ID: (SAM3)")
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
                if not model_id:
                    raise ValueError("model_id is required for YOLO mode")
                
                yolo_model_path = f"/yolo_models/{model_id}.pt"
                if not Path(yolo_model_path).exists():
                    raise FileNotFoundError(f"YOLO model not found at {yolo_model_path}")
                
                print(f"\n=== YOLO Mode: {yolo_model_path} ===")
                results_by_image, class_names_lookup = run_yolo_autolabel(
                    image_paths=image_paths,
                    yolo_model_path=yolo_model_path,
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
                
                print(f"\n=== SAM3 Mode ===")
                
                # Fast path: mask-only with existing bboxes
                if generate_masks and not generate_bboxes and existing_annotations:
                    print("Using bbox-prompt fast path for mask generation")
                    mask_results = run_sam3_mask_from_bboxes(
                        image_paths=image_paths,
                        existing_annotations=existing_annotations,
                        sam3_model_path="/models/sam3.pt",
                    )
                    # Convert to standard format: wrap as pre-built annotations
                    results_by_image = {}
                    for img_id, anns in mask_results.items():
                        results_by_image[img_id] = {"yolo_lines": [], "mask_polygons": [], "_prebuilt_annotations": anns}
                else:
                    # Standard path: full detection + optional masks
                    results_by_image, class_names_lookup = run_sam3_autolabel(
                        image_paths=image_paths,
                        prompt_type=prompt_type,
                        prompt_value=prompt_value,
                        sam3_model_path="/models/sam3.pt",
                        confidence=confidence,
                        prompt_class_map=prompt_class_map,
                        class_names_lookup=class_names_lookup,
                        save_masks=generate_masks,
                    )
            
            # === Upload label files & update annotations ===
            print("\n=== Uploading label files & updating annotations ===")
            print(f"Video mode: {video_mode}")
            
            uploaded_count = 0
            total_detections = 0
            total_masks = 0
            
            for image_id, result_data in results_by_image.items():
                # Handle both YOLO (list) and SAM3 (dict) result formats
                if isinstance(result_data, list):
                    # YOLO mode returns list of yolo_lines
                    yolo_lines = result_data
                    mask_polygons = []
                    prebuilt_annotations = None
                else:
                    # SAM3 mode returns dict
                    yolo_lines = result_data.get("yolo_lines", [])
                    mask_polygons = result_data.get("mask_polygons", [])
                    prebuilt_annotations = result_data.get("_prebuilt_annotations")
                
                # Upload YOLO label file to R2 (only if we have yolo_lines)
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
                    # Bbox-prompt fast path: annotations already built with masks
                    annotations_list = prebuilt_annotations
                else:
                    annotations_list = yolo_lines_to_annotations(
                        yolo_lines, class_names_lookup,
                        mask_polygons=mask_polygons if mask_polygons else None,
                    )
                
                # Count masks
                masks_in_image = sum(1 for a in annotations_list if "mask_polygon" in a)
                total_masks += masks_in_image
                
                ann_count = len(annotations_list)
                
                try:
                    if video_mode:
                        supabase.table("keyframes").update({
                            "annotation_count": ann_count,
                            "annotations": annotations_list,
                        }).eq("id", image_id).execute()
                        print(f"  Updated keyframe {image_id}: {ann_count} annotations ({masks_in_image} masks)")
                    else:
                        supabase.table("images").update({
                            "annotation_count": ann_count,
                            "labeled": ann_count > 0,
                            "annotations": annotations_list,
                        }).eq("id", image_id).execute()
                        print(f"  Updated image {image_id}: {ann_count} annotations ({masks_in_image} masks)")
                except Exception as e:
                    print(f"Error updating annotations for {image_id}: {e}")
            
            # === Update job status ===
            print("\n=== Job completed successfully ===")
            
            processed_count = len(image_paths)
            supabase.table("autolabel_jobs").update({
                "status": "completed",
                "completed_at": "now()",
                "detections_count": total_detections,
                "processed_count": processed_count,
            }).eq("id", job_id).execute()
            
            return {
                "success": True,
                "job_id": job_id,
                "processed_count": processed_count,
                "detections_count": total_detections,
                "masks_count": total_masks,
            }
            
        except Exception as e:
            # Update status to 'failed'
            error_msg = str(e)
            print(f"\nAuto-labeling failed: {error_msg}")
            
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
            # Cleanup
            shutil.rmtree(work_dir, ignore_errors=True)


# For local testing
if __name__ == "__main__":
    print("This module should be deployed to Modal, not run directly.")
    print("Deploy with: modal deploy backend/modal_jobs/autolabel_job.py")
