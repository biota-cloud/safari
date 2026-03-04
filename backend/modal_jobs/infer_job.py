"""
Modal Inference Job — GPU inference for YOLO11 models (Phase 3.4).

This Modal function:
1. Supports built-in models (yolo11n/s/m.pt) and custom trained models
2. Handles both image and video inference
3. Returns YOLO format labels (not rendered media)
4. Supports time ranges and frame skipping for videos

Usage (from Reflex app):
    cls = modal.Cls.lookup("yolo-inference", "YOLOInference")
    result = cls().predict_image.remote(...)
    result = cls().predict_video.remote(...)
"""

import os
import subprocess
from pathlib import Path

import modal

# Modal App configuration
app = modal.App("yolo-inference")

# Build the container image with all dependencies
image = (
    modal.Image.debian_slim(python_version="3.11")
    .apt_install(
        "libgl1-mesa-glx",  # OpenCV dependency
        "libglib2.0-0",     # OpenCV dependency
        "ffmpeg",           # Video processing
    )
    .pip_install(
        "ultralytics>=8.3.0",  # YOLO11
        "boto3",
        "supabase",
        "pillow",
        "opencv-python-headless",
    )
    .env({"PYTHONPATH": "/root"})
    .add_local_python_source("backend.core")
)


@app.cls(
    image=image,
    gpu="A10G",  # Same as training job for consistency
    timeout=600,  # 10 minutes for video processing
    enable_memory_snapshot=True,  # Dramatically reduces cold start time
    secrets=[
        modal.Secret.from_name("r2-credentials"),
        modal.Secret.from_name("supabase-credentials"),
    ],
)
class YOLOInference:
    """YOLO11 inference class supporting built-in and custom models."""
    
    def __init__(self):
        """Initialize the inference class."""
        self.model = None
        self.current_model_key = None
        self.model_cache_path = Path("/tmp/model_cache")
        self.model_cache_path.mkdir(exist_ok=True)
    
    def _load_builtin_model(self, model_name: str):
        """
        Load a built-in YOLO model from Ultralytics.
        
        Args:
            model_name: e.g., "yolo11n.pt", "yolo11s.pt", "yolo11m.pt"
        """
        from ultralytics import YOLO
        
        print(f"Loading built-in model: {model_name}")
        self.model = YOLO(model_name)  # Auto-downloads from Ultralytics
        self.current_model_key = f"builtin:{model_name}"
        print(f"Model loaded successfully")
    
    def _load_custom_model(self, model_id: str):
        """
        Download and load a custom model from R2 storage.
        
        Args:
            model_id: UUID of the model in the models table
        """
        import boto3
        from botocore.config import Config
        from supabase import create_client
        from ultralytics import YOLO
        
        print(f"Loading custom model {model_id}...")
        
        # Get model metadata from Supabase
        supabase = create_client(
            os.environ["SUPABASE_URL"],
            os.environ["SUPABASE_KEY"],
        )
        
        result = supabase.table("models").select("*").eq("id", model_id).single().execute()
        if not result.data:
            raise ValueError(f"Model {model_id} not found in database")
        
        model_data = result.data
        weights_path = model_data["weights_path"]
        
        print(f"Model weights path: {weights_path}")
        
        # Download from R2
        s3 = boto3.client(
            's3',
            endpoint_url=os.environ['R2_ENDPOINT_URL'],
            aws_access_key_id=os.environ['R2_ACCESS_KEY_ID'],
            aws_secret_access_key=os.environ['R2_SECRET_ACCESS_KEY'],
            config=Config(signature_version='s3v4'),
            region_name='auto',
        )
        bucket = os.environ['R2_BUCKET_NAME']
        
        # Cache file locally
        cache_file = self.model_cache_path / f"{model_id}.pt"
        
        if not cache_file.exists():
            print(f"Downloading weights from R2...")
            response = s3.get_object(Bucket=bucket, Key=weights_path)
            cache_file.write_bytes(response['Body'].read())
            print(f"Downloaded to {cache_file}")
        else:
            print(f"Using cached weights from {cache_file}")
        
        self.model = YOLO(str(cache_file))
        self.current_model_key = f"custom:{model_id}"
        print("Model loaded successfully")
    
    def _ensure_model_loaded(self, model_type: str, model_name_or_id: str):
        """Load model if not already loaded."""
        model_key = f"{model_type}:{model_name_or_id}"
        if self.current_model_key != model_key:
            if model_type == "builtin":
                self._load_builtin_model(model_name_or_id)
            else:
                self._load_custom_model(model_name_or_id)
    
    def _download_image(self, image_url: str) -> bytes:
        """Download image from presigned URL."""
        import requests
        response = requests.get(image_url)
        response.raise_for_status()
        return response.content
    
    @modal.method()
    def predict_image(
        self,
        model_type: str,
        model_name_or_id: str,
        image_url: str,
        confidence: float = 0.25,
    ) -> dict:
        """
        Run inference on a single image.
        
        Args:
            model_type: "builtin" or "custom"
            model_name_or_id: "yolo11s.pt" (builtin) or model UUID (custom)
            image_url: Presigned URL to download image
            confidence: Confidence threshold (0-1)
            
        Returns:
            {
                "predictions": [...],  # List of detections
                "labels_txt": "0 0.5 0.5 0.2 0.3\n...",  # YOLO format
                "detection_count": 2,
                "image_width": 1920,
                "image_height": 1080,
            }
        """
        from PIL import Image
        import io
        
        from backend.core.yolo_infer_core import (
            run_yolo_single_inference,
            format_predictions_to_yolo,
        )
        
        try:
            # Load model
            self._ensure_model_loaded(model_type, model_name_or_id)
            
            # Download image
            print(f"Downloading image from {image_url[:50]}...")
            image_bytes = self._download_image(image_url)
            image = Image.open(io.BytesIO(image_bytes))
            
            print(f"Running inference on {image.size[0]}x{image.size[1]} image...")
            
            # Run inference via core
            predictions, img_width, img_height = run_yolo_single_inference(
                self.model, image, confidence
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
    
    @modal.method()
    def predict_images_batch(
        self,
        model_type: str,
        model_name_or_id: str,
        image_urls: list[str],
        confidence: float = 0.25,
    ) -> list[dict]:
        """
        Run inference on multiple images sequentially in a single job.
        
        This keeps the GPU warm across all images, eliminating cold start
        overhead for each image. Designed for batch processing and Tauri API.
        
        Args:
            model_type: "builtin" or "custom"
            model_name_or_id: "yolo11s.pt" (builtin) or model UUID (custom)
            image_urls: List of presigned URLs to download images
            confidence: Confidence threshold (0-1)
            
        Returns:
            List of results, one per image:
            [
                {
                    "index": 0,
                    "predictions": [...],
                    "labels_txt": "...",
                    "detection_count": 2,
                    "image_width": 1920,
                    "image_height": 1080,
                },
                ...
            ]
        """
        from backend.core.yolo_infer_core import run_yolo_batch_inference
        
        print(f"=== Batch Inference: {len(image_urls)} images ===")
        
        try:
            # Load model ONCE for all images
            self._ensure_model_loaded(model_type, model_name_or_id)
            
            # Run batch inference via core
            results_list = run_yolo_batch_inference(
                self.model,
                image_urls,
                confidence,
                self._download_image,
            )
            
            print(f"=== Batch complete: {len(results_list)} images processed ===")
            return results_list
            
        except Exception as e:
            print(f"Batch inference failed: {e}")
            import traceback
            traceback.print_exc()
            raise
    
    @modal.method()
    def predict_video(
        self,
        model_type: str,
        model_name_or_id: str,
        video_url: str,
        confidence: float = 0.25,
        start_time: float = 0.0,
        end_time: float | None = None,
        frame_skip: int = 1,
        inference_result_id: str | None = None,
    ) -> dict:
        """
        Run inference on video frames.
        
        Args:
            model_type: "builtin" or "custom"
            model_name_or_id: "yolo11s.pt" (builtin) or model UUID (custom)
            video_url: Presigned URL to download video
            confidence: Confidence threshold (0-1)
            start_time: Start time in seconds
            end_time: End time in seconds (None = full video)
            frame_skip: Process every Nth frame (1 = every frame)
            
        Returns:
            {
                "predictions_by_frame": {
                    "0": [...],
                    "5": [...],
                    ...
                },
                "labels_by_frame": {
                    "0": "0 0.5 0.5 0.2 0.3",
                    "5": "",
                    ...
                },
                "total_frames_processed": 120,
                "total_detections": 45,
                "fps": 30.0,
                "video_width": 1920,
                "video_height": 1080,
            }
        """
        import requests
        import tempfile
        from supabase import create_client
        
        from backend.core.yolo_infer_core import run_yolo_video_inference
        
        try:
            # Initialize Supabase if ID provided (for progress updates)
            supabase = None
            if inference_result_id:
                try:
                    supabase = create_client(
                        os.environ["SUPABASE_URL"],
                        os.environ["SUPABASE_KEY"],
                    )
                except Exception as e:
                    print(f"Warning: Failed to init Supabase: {e}")
            
            # Load model
            self._ensure_model_loaded(model_type, model_name_or_id)
            
            # Download video
            print(f"Downloading video from {video_url[:50]}...")
            response = requests.get(video_url)
            response.raise_for_status()
            
            # Save to temp file
            with tempfile.NamedTemporaryFile(suffix=".mp4", delete=False) as tmp:
                tmp.write(response.content)
                temp_video_path = tmp.name
            
            # Trim video if time range specified
            trimmed_path = temp_video_path
            if start_time > 0 or end_time is not None:
                trimmed_path = self._trim_video(temp_video_path, start_time, end_time)
            
            # Create progress callback for Supabase updates
            def progress_callback(frames_processed: int, total_frames: int):
                if supabase and inference_result_id:
                    try:
                        supabase.table("inference_results").update({
                            "progress_current": frames_processed,
                            "progress_total": total_frames,
                            "inference_status": "processing"
                        }).eq("id", inference_result_id).execute()
                    except Exception as e:
                        print(f"Failed to update progress: {e}")
            
            # Send initial progress update
            if supabase and inference_result_id:
                try:
                    supabase.table("inference_results").update({
                        "progress_current": 0,
                        "progress_total": 0,
                        "inference_status": "processing"
                    }).eq("id", inference_result_id).execute()
                except Exception as e:
                    print(f"Failed to send initial progress: {e}")
            
            # Run video inference via core
            result = run_yolo_video_inference(
                self.model,
                trimmed_path,
                confidence,
                frame_skip,
                progress_callback,
            )
            
            # Cleanup
            Path(temp_video_path).unlink(missing_ok=True)
            if trimmed_path != temp_video_path:
                Path(trimmed_path).unlink(missing_ok=True)
            
            return result
            
        except Exception as e:
            print(f"Video inference failed: {e}")
            import traceback
            traceback.print_exc()
            raise
    
    def _trim_video(self, video_path: str, start_time: float, end_time: float | None) -> str:
        """Trim video to specified time range using ffmpeg."""
        print(f"Trimming video: {start_time}s to {end_time or 'end'}s")
        trimmed_path = video_path.replace(".mp4", "_trim.mp4")
        
        # Use re-encoding for reliability (stream copy can fail on short clips)
        ffmpeg_cmd = ["ffmpeg"]
        
        if start_time > 0:
            ffmpeg_cmd.extend(["-ss", str(start_time)])
        
        ffmpeg_cmd.extend(["-i", video_path])
        
        if end_time is not None:
            duration = end_time - start_time
            ffmpeg_cmd.extend(["-t", str(duration)])
        
        ffmpeg_cmd.extend([
            "-c:v", "libx264",
            "-preset", "ultrafast",
            "-crf", "23",
            "-an",  # No audio needed
            trimmed_path, "-y"
        ])
        
        print(f"Running ffmpeg: {' '.join(ffmpeg_cmd)}")
        result = subprocess.run(ffmpeg_cmd, capture_output=True, text=True)
        
        if result.returncode != 0:
            print(f"FFmpeg stderr: {result.stderr}")
            raise RuntimeError(f"FFmpeg failed: {result.stderr}")
        
        if not Path(trimmed_path).exists():
            raise RuntimeError(f"FFmpeg did not create output file: {trimmed_path}")
        
        print(f"Trimmed video created: {Path(trimmed_path).stat().st_size} bytes")
        return trimmed_path


# For local testing
if __name__ == "__main__":
    print("This module should be deployed to Modal, not run directly.")
    print("Deploy with: modal deploy backend/modal_jobs/infer_job.py")
