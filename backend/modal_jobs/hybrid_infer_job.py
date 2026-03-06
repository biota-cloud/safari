"""
Modal Hybrid Inference Job — SAM3 Detection + YOLOv11-Classify Species Identification.

This Modal function implements a two-stage pipeline:
1. SAM3 detects generic objects using text prompts (e.g., "mammal", "bird")
2. Each detection is cropped and classified by a YOLOv11-Classify model
3. Detections are filtered/labeled based on classifier output and prompt-class mapping

The workflow:
  SAM3("mammal") → Crop → Classifier("Lynx", 0.95) → Final: "Lynx" at box location

Usage (from Reflex app / Model Playground):
    fn = modal.Function.from_name("hybrid-inference", "hybrid_inference")
    result = fn.remote(
        image_url="...",
        sam3_prompts=["mammal", "bird"],
        classifier_r2_path="projects/.../best.pt",
        classifier_classes=["Lynx", "Deer", "Eagle"],
        prompt_class_map={"mammal": ["Lynx", "Deer"], "bird": ["Eagle"]},
    )
"""

import io
import os
import tempfile
from pathlib import Path

import modal

# Note: backend.core modules are imported inside @app.function decorators
# because Modal mounts don't include the full backend/ package.
# See run_hybrid_inference() and run_hybrid_batch_inference() patterns.

# Modal App configuration
app = modal.App("hybrid-inference")

# SAM3 volume (for SAM3 model weights)
sam3_volume = modal.Volume.from_name("sam3-volume", create_if_missing=False)

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
        "ultralytics>=8.3.237",  # SAM3 + YOLO11-Classify support
        "boto3",
        "requests",
        "pillow",
        "ftfy",  # Required by CLIP
        "regex",  # Required by CLIP
        "timm",  # Required by some SAM3 backbones
        "huggingface_hub",
        "supabase",  # For progress updates to DB
    )
    .pip_install(
        "git+https://github.com/ultralytics/CLIP.git"  # Ultralytics CLIP fork for SAM3
    )
    # Add /root to Python path for backend.core imports (must be before add_local_*)
    .env({"PYTHONPATH": "/root"})
    # Mount backend/core/ modules for shared pipeline logic (must be last)
    .add_local_dir(
        local_path=str(_CORE_DIR),
        remote_path="/root/backend/core",
    )
    .add_local_file(
        local_path=str(_BACKEND_INIT),
        remote_path="/root/backend/__init__.py",
    )
)


def download_classifier_model(r2_path: str, local_path: Path) -> bool:
    """Download classifier model from R2 to local path."""
    import boto3
    from botocore.config import Config
    
    try:
        s3 = boto3.client(
            's3',
            endpoint_url=os.environ['R2_ENDPOINT_URL'],
            aws_access_key_id=os.environ['R2_ACCESS_KEY_ID'],
            aws_secret_access_key=os.environ['R2_SECRET_ACCESS_KEY'],
            config=Config(signature_version='s3v4'),
            region_name='auto',
        )
        bucket = os.environ['R2_BUCKET_NAME']
        
        response = s3.get_object(Bucket=bucket, Key=r2_path)
        local_path.parent.mkdir(parents=True, exist_ok=True)
        local_path.write_bytes(response['Body'].read())
        return True
    except Exception as e:
        print(f"Failed to download classifier model: {e}")
        return False


def _make_supabase_progress_callback(result_id: str):
    """Create a progress callback that writes to Supabase inference_results."""
    from supabase import create_client
    
    url = os.environ["SUPABASE_URL"]
    key = os.environ["SUPABASE_KEY"]
    client = create_client(url, key)
    
    def callback(phase: str, current: int, total: int, status: str):
        try:
            data = {
                "progress_current": current,
                "progress_total": total,
                "progress_status": status,
            }
            client.table("inference_results").update(data).eq("id", result_id).execute()
        except Exception as e:
            print(f"[Progress] Failed to update: {e}")
    
    return callback


# Note: load_classifier and classify_with_convnext are imported from backend.core.classifier_utils


@app.function(
    image=image,
    gpu="L40S",
    timeout=300,  # 5 minutes max for single image inference
    enable_memory_snapshot=True,  # Dramatically reduces cold start time
    volumes={
        "/models": sam3_volume,  # SAM3 model at /models/sam3.pt
    },
    secrets=[
        modal.Secret.from_name("r2-credentials"),
    ],
)
def hybrid_inference(
    image_url: str,
    sam3_prompts: list[str],  # Generic prompts like ["mammal", "bird"]
    classifier_r2_path: str,  # R2 path to classifier weights (e.g., "projects/.../best.pt")
    classifier_classes: list[str],  # Class names the classifier was trained on
    prompt_class_map: dict[str, list[str]],  # {sam3_prompt: list of valid classifier classes}
    confidence_threshold: float = 0.25,
    classifier_confidence: float = 0.5,  # Minimum classifier confidence to keep detection
    sam3_model_path: str = "/models/sam3.pt",  # Volume path to SAM3 model (supports fine-tuned)
    sam3_imgsz: int = 644,  # SAM3 inference resolution (stride-14 aligned)
) -> dict:
    """
    Run hybrid SAM3 + Classifier inference on a single image.
    
    This is a thin wrapper around the core pipeline, providing Modal-specific
    configuration (SAM3 model path, R2 download function).
    """
    from backend.core.hybrid_infer_core import run_hybrid_inference
    
    print(f"[Modal] SAM3 model path: {sam3_model_path}")
    
    return run_hybrid_inference(
        image_url=image_url,
        sam3_prompts=sam3_prompts,
        classifier_r2_path=classifier_r2_path,
        classifier_classes=classifier_classes,
        prompt_class_map=prompt_class_map,
        confidence_threshold=confidence_threshold,
        classifier_confidence=classifier_confidence,
        # Modal-specific configuration:
        sam3_model_path=sam3_model_path,
        sam3_imgsz=sam3_imgsz,
        download_classifier_fn=download_classifier_model,
    )


@app.function(
    image=image,
    gpu="L40S",
    timeout=900,  # 15 minutes for batch processing
    enable_memory_snapshot=True,
    volumes={
        "/models": sam3_volume,
    },
    secrets=[
        modal.Secret.from_name("r2-credentials"),
    ],
)
def hybrid_inference_batch(
    image_urls: list[str],
    sam3_prompts: list[str],
    classifier_r2_path: str,
    classifier_classes: list[str],
    prompt_class_map: dict[str, list[str]],  # Kept for API compat, unused in hybrid
    confidence_threshold: float = 0.25,
    classifier_confidence: float = 0.5,
    sam3_model_path: str = "/models/sam3.pt",  # Volume path to SAM3 model (supports fine-tuned)
    sam3_imgsz: int = 644,  # SAM3 inference resolution (stride-14 aligned)
) -> list[dict]:
    """
    Run hybrid SAM3 + Classifier inference on multiple images sequentially.
    
    This is a thin wrapper around the core pipeline, providing Modal-specific
    configuration (SAM3 model path, R2 download function).
    """
    from backend.core.hybrid_batch_core import run_hybrid_batch_inference
    
    print(f"[Modal] SAM3 model path (batch): {sam3_model_path}")
    
    return run_hybrid_batch_inference(
        image_urls=image_urls,
        sam3_prompts=sam3_prompts,
        classifier_r2_path=classifier_r2_path,
        classifier_classes=classifier_classes,
        confidence_threshold=confidence_threshold,
        classifier_confidence=classifier_confidence,
        # Modal-specific configuration:
        sam3_model_path=sam3_model_path,
        sam3_imgsz=sam3_imgsz,
        download_classifier_fn=download_classifier_model,
    )


@app.function(
    image=image,
    gpu="L40S",
    timeout=1800,  # 30 minutes for video
    enable_memory_snapshot=True,  # Dramatically reduces cold start time
    volumes={
        "/models": sam3_volume,
    },
    secrets=[
        modal.Secret.from_name("r2-credentials"),
        modal.Secret.from_name("supabase-credentials"),
    ],
)
def hybrid_inference_video(
    video_url: str,
    sam3_prompts: list[str],
    classifier_r2_path: str,
    classifier_classes: list[str],
    prompt_class_map: dict[str, list[str]],
    confidence_threshold: float = 0.25,
    classifier_confidence: float = 0.5,
    start_time: float = 0.0,
    end_time: float | None = None,
    frame_skip: int = 1,
    classify_top_k: int = 3,
    sam3_imgsz: int = 644,
    result_id: str | None = None,  # For progress updates to Supabase
    sam3_model_path: str = "/models/sam3.pt",  # Volume path to SAM3 model (supports fine-tuned)
) -> dict:
    """
    Run hybrid inference on video using SAM3's native video tracking.
    
    This is a thin wrapper around the core pipeline, providing Modal-specific
    configuration (SAM3 model path, R2 download function).
    
    Uses a two-phase pipeline:
    1. SAM3VideoSemanticPredictor processes the full video with temporal tracking
    2. Unique tracked objects are classified once (not per-frame)
    3. Classifications are propagated to all frames via track IDs
    """
    from backend.core.hybrid_video_core import run_hybrid_video_inference
    
    def _upload_crop_to_r2(crop_bytes: bytes, r2_path: str) -> str:
        """Upload crop image to R2 and return presigned URL."""
        import boto3
        from botocore.config import Config
        
        s3 = boto3.client(
            's3',
            endpoint_url=os.environ['R2_ENDPOINT_URL'],
            aws_access_key_id=os.environ['R2_ACCESS_KEY_ID'],
            aws_secret_access_key=os.environ['R2_SECRET_ACCESS_KEY'],
            config=Config(signature_version='s3v4'),
            region_name='auto',
        )
        bucket = os.environ['R2_BUCKET_NAME']
        s3.put_object(Bucket=bucket, Key=r2_path, Body=crop_bytes, ContentType='image/jpeg')
        return s3.generate_presigned_url(
            'get_object', Params={'Bucket': bucket, 'Key': r2_path}, ExpiresIn=3600
        )
    
    # Create progress callback if result_id provided
    progress_callback = None
    if result_id:
        progress_callback = _make_supabase_progress_callback(result_id)
    
    try:
        print(f"[Modal] SAM3 model path (video): {sam3_model_path}")
        result = run_hybrid_video_inference(
            video_url=video_url,
            sam3_prompts=sam3_prompts,
            classifier_r2_path=classifier_r2_path,
            classifier_classes=classifier_classes,
            confidence_threshold=confidence_threshold,
            classifier_confidence=classifier_confidence,
            start_time=start_time,
            end_time=end_time,
            frame_skip=frame_skip,
            classify_top_k=classify_top_k,
            # Modal-specific configuration:
            sam3_model_path=sam3_model_path,
            download_classifier_fn=download_classifier_model,
            upload_crop_fn=_upload_crop_to_r2,
            progress_callback=progress_callback,
            imgsz=sam3_imgsz,
        )
        
        # When spawned (result_id provided), we must write the result
        # to Supabase since fn.spawn() doesn't return the value
        if result_id:
            from supabase import create_client
            
            url = os.environ["SUPABASE_URL"]
            key = os.environ["SUPABASE_KEY"]
            client = create_client(url, key)
            
            client.table("inference_results").update({
                "inference_status": "completed",
                "predictions_json": result,  # Full result dict with frame_results
                "progress_status": "completed",
                "progress_current": result.get("processed_frames", 0),
                "progress_total": result.get("processed_frames", 0),
                "video_fps": result.get("fps"),
                "video_total_frames": result.get("processed_frames"),
                "detection_count": result.get("total_predictions", 0),
            }).eq("id", result_id).execute()
            print(f"[Modal] Video inference completed, result saved to DB: {result_id}")
        
        return result
    except Exception as e:
        # Mark job as failed in DB if result_id provided
        if result_id:
            try:
                from supabase import create_client
                url = os.environ["SUPABASE_URL"]
                key = os.environ["SUPABASE_KEY"]
                client = create_client(url, key)
                client.table("inference_results").update({
                    "inference_status": "failed",
                    "progress_status": f"failed: {str(e)[:200]}",
                }).eq("id", result_id).execute()
            except Exception:
                pass
        raise


# For local testing
if __name__ == "__main__":
    print("This module should be deployed to Modal, not run directly.")
    print("Deploy with: modal deploy backend/modal_jobs/hybrid_infer_job.py")
