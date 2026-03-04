#!/usr/bin/env python3
"""
SAFARI Remote Worker — Hybrid SAM3 + Classifier Inference.

Standalone script that mirrors Modal hybrid_infer_job.py for local GPU execution.

Usage:
    echo '{"image_url": "...", ...}' | python remote_hybrid_infer.py

Expected JSON input (single image):
    {
        "image_url": "presigned_url",
        "sam3_prompts": ["mammal", "bird"],
        "classifier_r2_path": "projects/.../best.pt",
        "classifier_classes": ["Lynx", "Deer", "Eagle"],
        "prompt_class_map": {"mammal": ["Lynx", "Deer"], "bird": ["Eagle"]},
        "confidence_threshold": 0.25,
        "classifier_confidence": 0.5
    }

Expected JSON input (batch):
    {
        "batch": true,
        "image_urls": ["url1", "url2", ...],
        "sam3_prompts": [...],
        ...
    }

Output:
    JSON result to stdout with predictions.
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
from backend.core.image_utils import crop_from_box, download_image
from backend.core.classifier_utils import load_classifier, classify_with_convnext

from remote_utils import (
    download_file,
    download_from_r2_cached,
    get_models_dir,
)


# Note: crop_from_box, download_image, load_classifier, classify_with_convnext 
# are imported from backend.core modules for single source of truth


def _download_classifier_for_inference(r2_path: str, local_path: Path) -> bool:
    """Wrapper for classifier download that uses cached R2 download with hashed filename."""
    import hashlib
    
    # Use hash of R2 path for unique cache file name
    model_hash = hashlib.md5(r2_path.encode()).hexdigest()[:12]
    ext = ".pth" if r2_path.endswith(".pth") else ".pt"
    cached_path = get_models_dir() / f"classifier_{model_hash}{ext}"
    
    if download_from_r2_cached(r2_path, cached_path):
        # Copy to expected location if different
        if cached_path != local_path:
            local_path.parent.mkdir(parents=True, exist_ok=True)
            import shutil
            shutil.copy2(cached_path, local_path)
        return True
    return False


def hybrid_inference(
    image_url: str,
    sam3_prompts: list[str],
    classifier_r2_path: str,
    classifier_classes: list[str],
    prompt_class_map: dict[str, list[str]],
    confidence_threshold: float = 0.25,
    classifier_confidence: float = 0.5,
) -> dict:
    """
    Run hybrid SAM3 + Classifier inference on a single image.
    
    This is a thin wrapper around the core pipeline, providing remote-worker-specific
    configuration (local SAM3 model, cached R2 download function).
    
    Now includes mask extraction (previously missing — legacy bug fix).
    """
    from backend.core.hybrid_infer_core import run_hybrid_inference
    
    # Use local SAM3 model (avoids re-downloading pretrained weights every run)
    sam3_model_path = str(get_models_dir() / "sam3.pt")
    
    return run_hybrid_inference(
        image_url=image_url,
        sam3_prompts=sam3_prompts,
        classifier_r2_path=classifier_r2_path,
        classifier_classes=classifier_classes,
        prompt_class_map=prompt_class_map,
        confidence_threshold=confidence_threshold,
        classifier_confidence=classifier_confidence,
        # Remote-worker-specific configuration:
        sam3_model_path=sam3_model_path,
        download_classifier_fn=_download_classifier_for_inference,
    )


def hybrid_inference_batch(
    image_urls: list[str],
    sam3_prompts: list[str],
    classifier_r2_path: str,
    classifier_classes: list[str],
    prompt_class_map: dict[str, list[str]],  # Kept for API compat, unused in hybrid
    confidence_threshold: float = 0.25,
    classifier_confidence: float = 0.5,
) -> list[dict]:
    """
    Run hybrid inference on multiple images sequentially.
    
    This is a thin wrapper around the core pipeline, providing remote-worker-specific
    configuration (local SAM3 model, cached R2 download function).
    """
    from backend.core.hybrid_batch_core import run_hybrid_batch_inference
    
    # Use local SAM3 model (avoids re-downloading pretrained weights every run)
    sam3_model_path = str(get_models_dir() / "sam3.pt")
    
    return run_hybrid_batch_inference(
        image_urls=image_urls,
        sam3_prompts=sam3_prompts,
        classifier_r2_path=classifier_r2_path,
        classifier_classes=classifier_classes,
        confidence_threshold=confidence_threshold,
        classifier_confidence=classifier_confidence,
        # Remote-worker-specific configuration:
        sam3_model_path=sam3_model_path,
        download_classifier_fn=_download_classifier_for_inference,
    )


def _emit_progress(phase: str, current: int, total: int, status: str):
    """Emit a structured progress line to stderr for SSH log polling."""
    progress = json.dumps({"phase": phase, "current": current, "total": total, "status": status})
    print(f"PROGRESS:{progress}", file=sys.stderr, flush=True)


def hybrid_inference_video(
    video_url: str,
    sam3_prompts: list[str],
    classifier_r2_path: str,
    classifier_classes: list[str],
    prompt_class_map: dict[str, list[str]],
    confidence_threshold: float = 0.25,
    classifier_confidence: float = 0.5,
    start_time: float = 0.0,
    end_time: float = None,
    frame_skip: int = 1,
    classify_top_k: int = 3,
    sam3_imgsz: int = 640,
) -> dict:
    """
    Run hybrid inference on video using SAM3's native video tracking.
    
    This is a thin wrapper around the core pipeline, providing remote-worker-specific
    configuration (local SAM3 path, cached R2 download function).
    
    Now includes mask extraction (previously missing — fixed via shared core).
    """
    from backend.core.hybrid_video_core import run_hybrid_video_inference
    from remote_utils import get_r2_client, get_r2_bucket
    
    def _upload_crop_to_r2(crop_bytes: bytes, r2_path: str) -> str:
        """Upload crop image to R2 and return presigned URL."""
        s3 = get_r2_client()
        bucket = get_r2_bucket()
        s3.put_object(Bucket=bucket, Key=r2_path, Body=crop_bytes, ContentType='image/jpeg')
        return s3.generate_presigned_url(
            'get_object', Params={'Bucket': bucket, 'Key': r2_path}, ExpiresIn=3600
        )
    
    # Use local SAM3 model
    tyto_home = Path.home() / ".tyto"
    sam3_model_path = tyto_home / "models" / "sam3.pt"
    
    if not sam3_model_path.exists():
        raise FileNotFoundError(
            f"SAM3 model not found at {sam3_model_path}. "
            "Run: modal volume get sam3-volume /sam3.pt ~/.tyto/models/sam3.pt"
        )
    
    return run_hybrid_video_inference(
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
        # Remote-worker-specific configuration:
        sam3_model_path=str(sam3_model_path),
        download_classifier_fn=_download_classifier_for_inference,
        upload_crop_fn=_upload_crop_to_r2,
        progress_callback=_emit_progress,
        imgsz=sam3_imgsz,
    )


def main():
    """Read job params from stdin, execute inference, output result."""
    try:
        params = json.load(sys.stdin)
    except json.JSONDecodeError as e:
        print(json.dumps({"success": False, "error": f"Invalid JSON input: {e}"}))
        sys.exit(1)
    
    # Determine dispatch mode
    mode = params.pop("mode", "single")  # Remove mode from params
    
    if mode == "video":
        result = hybrid_inference_video(**params)
        
        # For video results, upload the full result to R2 instead of printing
        # to stdout (avoids SSH bottleneck with large mask polygon data)
        try:
            import uuid
            from remote_utils import upload_to_r2
            
            result_json = json.dumps(result)
            r2_key = f"inference_temp/ssh_results/{uuid.uuid4()}.json"
            
            # Write to temp file then upload
            tmp_path = Path(tempfile.gettempdir()) / f"result_{uuid.uuid4().hex[:8]}.json"
            tmp_path.write_text(result_json)
            
            if upload_to_r2(tmp_path, r2_key):
                # Print small reference (SSH polling reads this)
                print(json.dumps({
                    "success": result.get("success", True),
                    "r2_result_path": r2_key,
                    "processed_frames": result.get("processed_frames", 0),
                    "total_predictions": result.get("total_predictions", 0),
                    "unique_tracks": result.get("unique_tracks", 0),
                    "classified_tracks": result.get("classified_tracks", 0),
                    "fps": result.get("fps", 0),
                }))
            else:
                # Fallback: print full result if R2 upload fails
                print(result_json)
            
            tmp_path.unlink(missing_ok=True)
        except Exception as e:
            print(f"Warning: R2 upload failed, printing full result: {e}", file=sys.stderr)
            print(json.dumps(result))
    elif mode == "batch":
        # Wrap list result in dict for job router compatibility
        batch_results = hybrid_inference_batch(**params)
        result = {"results": batch_results}
        print(json.dumps(result))
    else:  # "single" or default
        result = hybrid_inference(**params)
        print(json.dumps(result))

if __name__ == "__main__":
    main()
