#!/usr/bin/env python3
"""
SAFARI Remote Worker — YOLO Detection Inference.

Standalone script that mirrors Modal infer_job.py for local GPU execution.
Uses shared core module for inference logic parity.

Usage:
    echo '{"mode": "single", "image_url": "...", ...}' | python remote_yolo_infer.py

Modes:
- single: Run inference on a single image
- batch: Run inference on multiple images
- video: Run inference on video frames

Expected JSON input (single):
    {
        "mode": "single",
        "model_type": "builtin",  # or "custom"
        "model_name_or_id": "yolo11s.pt",  # or model UUID
        "image_url": "presigned_url",
        "confidence": 0.25
    }

Expected JSON input (batch):
    {
        "mode": "batch",
        "model_type": "builtin",
        "model_name_or_id": "yolo11s.pt",
        "image_urls": ["url1", "url2", ...],
        "confidence": 0.25
    }

Expected JSON input (video):
    {
        "mode": "video",
        "model_type": "builtin",
        "model_name_or_id": "yolo11s.pt",
        "video_url": "presigned_url",
        "confidence": 0.25,
        "start_time": 0.0,
        "end_time": null,
        "frame_skip": 1
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

# Path setup for imports
sys.path.insert(0, str(Path(__file__).parent))

# Support TYTO_ROOT env var or detect from script location
TYTO_ROOT = os.environ.get("TYTO_ROOT")
if TYTO_ROOT:
    sys.path.insert(0, TYTO_ROOT)
else:
    # Detect from script location: scripts/remote_workers -> project root
    project_root = Path(__file__).parent.parent.parent
    sys.path.insert(0, str(project_root))

from remote_utils import (
    download_from_r2_cached,
    get_models_dir,
)

# Disable Ultralytics auto-update
os.environ["ULTRALYTICS_AUTOUPDATE"] = "false"


def download_image(url: str) -> bytes:
    """Download an image from a presigned URL and return bytes."""
    import requests
    
    response = requests.get(url, timeout=60)
    response.raise_for_status()
    return response.content


def download_video(url: str, dest_path: Path) -> None:
    """Download a video from a presigned URL to disk."""
    import requests
    
    response = requests.get(url, timeout=300, stream=True)
    response.raise_for_status()
    with open(dest_path, 'wb') as f:
        for chunk in response.iter_content(chunk_size=8192):
            f.write(chunk)


def load_model(model_type: str, model_name_or_id: str):
    """
    Load a YOLO model (built-in or custom).
    
    Args:
        model_type: "builtin" or "custom"
        model_name_or_id: "yolo11s.pt" or model UUID
    
    Returns:
        Loaded YOLO model
    """
    from ultralytics import YOLO
    
    if model_type == "builtin":
        print(f"Loading built-in model: {model_name_or_id}")
        return YOLO(model_name_or_id)  # Auto-downloads from Ultralytics
    else:
        # Custom model — download from R2
        print(f"Loading custom model: {model_name_or_id}")
        
        # Get model R2 path from Supabase
        from remote_utils import get_supabase
        supabase = get_supabase()
        
        result = supabase.table("models").select("weights_path").eq("id", model_name_or_id).single().execute()
        if not result.data:
            raise ValueError(f"Model {model_name_or_id} not found in database")
        
        weights_path = result.data["weights_path"]
        local_path = get_models_dir() / f"model_{model_name_or_id}.pt"
        
        if not download_from_r2_cached(weights_path, local_path):
            raise RuntimeError(f"Failed to download model from {weights_path}")
        
        return YOLO(str(local_path))


def trim_video(video_path: Path, start_time: float, end_time: float | None, work_dir: Path) -> Path:
    """Trim video to specified time range using ffmpeg."""
    import subprocess
    
    print(f"Trimming video: {start_time}s to {end_time or 'end'}s")
    trimmed_path = work_dir / "video_trim.mp4"
    
    ffmpeg_cmd = ["ffmpeg"]
    if start_time > 0:
        ffmpeg_cmd.extend(["-ss", str(start_time)])
    ffmpeg_cmd.extend(["-i", str(video_path)])
    if end_time is not None:
        duration = end_time - start_time
        ffmpeg_cmd.extend(["-t", str(duration)])
    ffmpeg_cmd.extend([
        "-c:v", "libx264",
        "-preset", "ultrafast",
        "-crf", "23",
        "-an",
        str(trimmed_path), "-y"
    ])
    
    result = subprocess.run(ffmpeg_cmd, capture_output=True, text=True)
    if result.returncode != 0:
        raise RuntimeError(f"FFmpeg failed: {result.stderr}")
    
    return trimmed_path


def predict_image(
    model_type: str,
    model_name_or_id: str,
    image_url: str,
    confidence: float = 0.25,
) -> dict:
    """
    Run inference on a single image.
    
    Mirrors Modal infer_job.predict_image()
    """
    from PIL import Image
    from backend.core.yolo_infer_core import (
        run_yolo_single_inference,
        format_predictions_to_yolo,
    )
    
    print(f"=== YOLO Image Inference (Local GPU) ===")
    print(f"Model: {model_type}/{model_name_or_id}")
    
    try:
        # Load model
        model = load_model(model_type, model_name_or_id)
        
        # Download image
        print("Downloading image...")
        image_bytes = download_image(image_url)
        image = Image.open(io.BytesIO(image_bytes))
        
        print(f"Running inference on {image.size[0]}x{image.size[1]} image...")
        
        # Run inference via core
        predictions, img_width, img_height = run_yolo_single_inference(
            model, image, confidence
        )
        
        # Convert to YOLO format
        labels_txt = format_predictions_to_yolo(predictions, img_width, img_height)
        
        print(f"Found {len(predictions)} detections")
        
        return {
            "predictions": predictions,
            "labels_txt": labels_txt,
            "detection_count": len(predictions),
            "image_width": img_width,
            "image_height": img_height,
        }
        
    except Exception as e:
        print(f"Image inference failed: {e}")
        import traceback
        traceback.print_exc()
        raise


def predict_images_batch(
    model_type: str,
    model_name_or_id: str,
    image_urls: list[str],
    confidence: float = 0.25,
) -> list[dict]:
    """
    Run inference on multiple images sequentially.
    
    Mirrors Modal infer_job.predict_images_batch()
    """
    from backend.core.yolo_infer_core import run_yolo_batch_inference
    
    print(f"=== YOLO Batch Inference: {len(image_urls)} images (Local GPU) ===")
    print(f"Model: {model_type}/{model_name_or_id}")
    
    try:
        # Load model ONCE for all images
        model = load_model(model_type, model_name_or_id)
        
        # Run batch inference via core
        results_list = run_yolo_batch_inference(
            model,
            image_urls,
            confidence,
            download_image,
        )
        
        print(f"=== Batch complete: {len(results_list)} images processed ===")
        return results_list
        
    except Exception as e:
        print(f"Batch inference failed: {e}")
        import traceback
        traceback.print_exc()
        raise


def predict_video(
    model_type: str,
    model_name_or_id: str,
    video_url: str,
    confidence: float = 0.25,
    start_time: float = 0.0,
    end_time: float = None,
    frame_skip: int = 1,
    inference_result_id: str = None,
) -> dict:
    """
    Run inference on video frames.
    
    Mirrors Modal infer_job.predict_video()
    """
    import shutil
    from backend.core.yolo_infer_core import run_yolo_video_inference
    
    work_dir = Path(tempfile.mkdtemp(prefix="yolo_video_"))
    
    try:
        print(f"=== YOLO Video Inference (Local GPU) ===")
        print(f"Model: {model_type}/{model_name_or_id}")
        
        # Load model
        model = load_model(model_type, model_name_or_id)
        
        # Download video
        print("Downloading video...")
        video_path = work_dir / "video.mp4"
        download_video(video_url, video_path)
        
        # Trim video if time range specified
        final_path = video_path
        if start_time > 0 or end_time is not None:
            final_path = trim_video(video_path, start_time, end_time, work_dir)
        
        # Run video inference via core
        result = run_yolo_video_inference(
            model,
            str(final_path),
            confidence,
            frame_skip,
            progress_callback=None,  # No Supabase updates for remote
        )
        
        return result
        
    except Exception as e:
        print(f"Video inference failed: {e}")
        import traceback
        traceback.print_exc()
        raise
        
    finally:
        shutil.rmtree(work_dir, ignore_errors=True)


def main():
    """Entry point for stdin/stdout JSON interface."""
    # Read JSON from stdin
    input_data = json.load(sys.stdin)
    
    mode = input_data.get("mode", "single")
    
    try:
        if mode == "single":
            result = predict_image(
                model_type=input_data.get("model_type", "builtin"),
                model_name_or_id=input_data.get("model_name_or_id", "yolo11s.pt"),
                image_url=input_data.get("image_url", ""),
                confidence=input_data.get("confidence", 0.25),
            )
        elif mode == "batch":
            results = predict_images_batch(
                model_type=input_data.get("model_type", "builtin"),
                model_name_or_id=input_data.get("model_name_or_id", "yolo11s.pt"),
                image_urls=input_data.get("image_urls", []),
                confidence=input_data.get("confidence", 0.25),
            )
            result = {"results": results}
        elif mode == "video":
            result = predict_video(
                model_type=input_data.get("model_type", "builtin"),
                model_name_or_id=input_data.get("model_name_or_id", "yolo11s.pt"),
                video_url=input_data.get("video_url", ""),
                confidence=input_data.get("confidence", 0.25),
                start_time=input_data.get("start_time", 0.0),
                end_time=input_data.get("end_time"),
                frame_skip=input_data.get("frame_skip", 1),
                inference_result_id=input_data.get("inference_result_id"),
            )
        else:
            raise ValueError(f"Unknown mode: {mode}")
        
        # Output JSON to stdout
        print(json.dumps(result))
        
    except Exception as e:
        import traceback
        error_result = {
            "success": False,
            "error": str(e),
            "traceback": traceback.format_exc(),
        }
        print(json.dumps(error_result), file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
