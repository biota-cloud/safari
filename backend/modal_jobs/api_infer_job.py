"""
API Inference Job — Dedicated Modal GPU inference for the public API.

This is a SEPARATE job from infer_job.py to maintain isolation per the API roadmap.
It supports both YOLO detection and SAM3+Classifier hybrid inference.

Deployment:
    modal deploy backend/modal_jobs/api_infer_job.py

Usage (from API server):
    APIInference = modal.Cls.from_name("tyto-api-inference", "APIInference")
    
    # Detection flow
    result = APIInference().predict_image.remote(...)
    
    # Hybrid classification flow
    result = APIInference().predict_image_hybrid.remote(...)
"""

import io
import os
import tempfile
from pathlib import Path

import modal

# Modal App configuration
app = modal.App("tyto-api-inference")

# SAM3 volume (for SAM3 model weights)
sam3_volume = modal.Volume.from_name("sam3-volume", create_if_missing=False)

# Build the container image with all dependencies
image = (
    modal.Image.debian_slim(python_version="3.11")
    .apt_install(
        "libgl1-mesa-glx",  # OpenCV dependency
        "libglib2.0-0",     # OpenCV dependency
        "git",              # For CLIP install
        "ffmpeg",           # Video processing
    )
    .pip_install(
        "ultralytics>=8.3.237",  # SAM3 + YOLO11-Classify support
        "boto3",
        "supabase",
        "pillow",
        "opencv-python-headless",
        "ftfy",             # Required by CLIP
        "regex",            # Required by CLIP
        "timm",             # Required by some SAM3 backbones
        "huggingface_hub",
    )
    .pip_install(
        "git+https://github.com/ultralytics/CLIP.git"  # Ultralytics CLIP fork for SAM3
    )
)


# =============================================================================
# HELPER FUNCTIONS
# =============================================================================

def crop_from_box(image_bytes: bytes, box: tuple, padding: float = 0.05) -> bytes:
    """
    Crop a region from an image using box coordinates.
    
    Args:
        image_bytes: Raw image bytes
        box: (x1, y1, x2, y2) absolute pixel coordinates
        padding: Percentage to expand the crop (e.g., 0.05 = 5% padding)
    
    Returns:
        Cropped image as JPEG bytes
    """
    from PIL import Image
    
    img = Image.open(io.BytesIO(image_bytes))
    img_width, img_height = img.size
    
    x1, y1, x2, y2 = box
    
    # Calculate box dimensions for padding
    box_width = x2 - x1
    box_height = y2 - y1
    
    # Add padding
    pad_x = int(box_width * padding)
    pad_y = int(box_height * padding)
    
    x1 = max(0, int(x1) - pad_x)
    y1 = max(0, int(y1) - pad_y)
    x2 = min(img_width, int(x2) + pad_x)
    y2 = min(img_height, int(y2) + pad_y)
    
    # Crop
    cropped = img.crop((x1, y1, x2, y2))
    
    # Convert to RGB if necessary
    if cropped.mode != "RGB":
        cropped = cropped.convert("RGB")
    
    # Save to bytes
    output = io.BytesIO()
    cropped.save(output, format="JPEG", quality=95)
    return output.getvalue()


def download_model_from_r2(r2_path: str, local_path: Path) -> bool:
    """Download a model from R2 to local path."""
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
        print(f"Failed to download model: {e}")
        return False


def mask_to_polygon(mask, img_width: int, img_height: int) -> list | None:
    """
    Convert a binary/probability mask to normalized polygon points.
    
    Args:
        mask: 2D numpy array representing the mask
        img_width: Original image width for normalization
        img_height: Original image height for normalization
    
    Returns:
        List of [x, y] normalized coordinates (0-1), or None if contours not found
    """
    import cv2
    import numpy as np
    
    # Ensure binary mask with proper thresholding
    if mask.max() <= 1.0:
        mask_uint8 = ((mask > 0.5) * 255).astype(np.uint8)
    else:
        mask_uint8 = (mask > 127).astype(np.uint8) * 255
    
    # Apply morphological closing to fill small gaps
    diagonal = int(np.sqrt(mask.shape[0]**2 + mask.shape[1]**2))
    kernel_size = max(5, diagonal // 100)  # ~1% of diagonal
    kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (kernel_size, kernel_size))
    mask_closed = cv2.morphologyEx(mask_uint8, cv2.MORPH_CLOSE, kernel)
    
    contours, _ = cv2.findContours(mask_closed, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    
    if not contours:
        return None
    
    # Take the largest contour
    largest_contour = max(contours, key=cv2.contourArea)
    
    # Simplify polygon
    epsilon = 0.001 * cv2.arcLength(largest_contour, True)
    approx = cv2.approxPolyDP(largest_contour, epsilon, True)
    
    # Convert to normalized coordinates (0-1)
    polygon_points = []
    for point in approx:
        px, py = point[0]
        polygon_points.append([
            round(float(px) / img_width, 6),
            round(float(py) / img_height, 6)
        ])
    
    return polygon_points


def crop_quality_score(box: list, frame_width: int, frame_height: int) -> float:
    """
    GPU-free heuristic to score a detection crop's quality.
    
    Combines area ratio, edge proximity penalty, and aspect ratio balance.
    Returns score in [0, 1] range.
    """
    x1, y1, x2, y2 = box
    w = x2 - x1
    h = y2 - y1
    
    if w <= 0 or h <= 0:
        return 0.0
    
    area_ratio = (w * h) / (frame_width * frame_height)
    area_score = min(area_ratio * 10, 1.0)
    
    margin_x = min(x1, frame_width - x2) / frame_width
    margin_y = min(y1, frame_height - y2) / frame_height
    edge_score = min(margin_x * 10, 1.0) * min(margin_y * 10, 1.0)
    
    aspect = w / h if h > 0 else 1.0
    aspect_score = 1.0 - abs(aspect - 1.0) / max(aspect, 1.0)
    
    return 0.5 * area_score + 0.3 * edge_score + 0.2 * aspect_score


def select_diverse_frames(
    candidates: list[dict],
    K: int,
    frame_width: int,
    frame_height: int,
) -> list[dict]:
    """
    Select K high-quality, temporally diverse frames from candidates.
    
    Algorithm:
    1. Score all candidates by crop quality
    2. Pick highest-quality frame as seed
    3. Greedily add frames respecting min_gap = span/(K+1)
    4. If fewer than K selected, relax gap and fill by quality
    """
    if len(candidates) <= K:
        return candidates
    
    scored = []
    for c in candidates:
        score = crop_quality_score(c["box"], frame_width, frame_height)
        scored.append((score, c))
    scored.sort(key=lambda x: x[0], reverse=True)
    
    frames = [c["frame"] for c in candidates]
    span = max(frames) - min(frames)
    min_gap = span / (K + 1) if span > 0 else 0
    
    selected = [scored[0][1]]
    selected_frames = {scored[0][1]["frame"]}
    
    for _, candidate in scored[1:]:
        if len(selected) >= K:
            break
        if all(abs(candidate["frame"] - sf) >= min_gap for sf in selected_frames):
            selected.append(candidate)
            selected_frames.add(candidate["frame"])
    
    if len(selected) < K:
        for _, candidate in scored:
            if len(selected) >= K:
                break
            if candidate["frame"] not in selected_frames:
                selected.append(candidate)
                selected_frames.add(candidate["frame"])
    
    return selected


def vote_classifications(
    results: list[tuple],
    classifier_confidence: float,
) -> tuple:
    """
    Majority vote over K classification results.
    
    Returns (winning_class, class_id_placeholder, avg_confidence, agreement_ratio).
    """
    from collections import Counter
    
    valid_votes = [
        (cls, conf) for cls, conf in results
        if cls is not None and conf >= classifier_confidence
    ]
    
    if not valid_votes:
        return ("Unknown", -1, 0.0, 0.0)
    
    class_counts = Counter(cls for cls, _ in valid_votes)
    winner, win_count = class_counts.most_common(1)[0]
    
    winner_confs = [conf for cls, conf in valid_votes if cls == winner]
    avg_conf = sum(winner_confs) / len(winner_confs)
    
    agreement = win_count / len(results) if results else 0.0
    
    return (winner, -1, avg_conf, agreement)


# =============================================================================
# API INFERENCE CLASS
# =============================================================================

@app.cls(
    image=image,
    gpu="L40S",
    timeout=1800,  # 30 minutes for video processing
    enable_memory_snapshot=True,  # Fast cold starts
    volumes={
        "/models": sam3_volume,  # SAM3 model at /models/sam3.pt
    },
    secrets=[
        modal.Secret.from_name("r2-credentials"),
        modal.Secret.from_name("supabase-credentials"),
    ],
)
class APIInference:
    """
    API Inference class for handling public API requests.
    
    Supports two flows:
    1. Detection (YOLO) — predict_image(), process_video_job()
    2. Classification (SAM3 + Classifier) — predict_image_hybrid(), process_video_job_hybrid()
    """
    
    def __init__(self):
        """Initialize the inference class."""
        self.model = None
        self.classifier = None
        self.current_weights_path = None
        self.current_classifier_path = None
        self.cache_path = Path("/tmp/api_model_cache")
        self.cache_path.mkdir(exist_ok=True)
        
        # Disable Ultralytics auto-update
        os.environ["ULTRALYTICS_AUTOUPDATE"] = "false"
    
    @modal.enter(snap=True)
    def preload_dependencies(self):
        """
        Preload heavy dependencies during snapshot creation.
        This runs once when the snapshot is created.
        """
        print("Preloading dependencies for snapshot...")
        import ultralytics
        import cv2
        import boto3
        print("Dependencies preloaded")
    
    @modal.enter(snap=False)
    def on_restore(self):
        """
        Called after container restore from snapshot.
        Reset any state that shouldn't persist.
        """
        self.model = None
        self.classifier = None
        self.current_weights_path = None
        self.current_classifier_path = None
        print("Container restored from snapshot")
    
    def _load_yolo_model(self, weights_r2_path: str):
        """Download and load a YOLO model from R2."""
        from ultralytics import YOLO
        
        if self.current_weights_path == weights_r2_path and self.model is not None:
            print(f"Using cached YOLO model: {weights_r2_path}")
            return
        
        print(f"Loading YOLO model from R2: {weights_r2_path}")
        
        import hashlib
        cache_key = hashlib.md5(weights_r2_path.encode()).hexdigest()[:16]
        cache_file = self.cache_path / f"{cache_key}.pt"
        
        if not cache_file.exists():
            if not download_model_from_r2(weights_r2_path, cache_file):
                raise RuntimeError(f"Failed to download model from {weights_r2_path}")
        
        self.model = YOLO(str(cache_file))
        self.current_weights_path = weights_r2_path
        print("YOLO model loaded successfully")
    
    def _load_classifier(self, classifier_r2_path: str):
        """
        Download and load a classifier model from R2.
        Supports both YOLO (.pt) and ConvNeXt (.pth) classifiers.
        
        Sets self.classifier_data with keys:
            - "type": "yolo" or "convnext"
            - "model": loaded model
            - For ConvNeXt: also "idx_to_class", "transform", "device"
        """
        if self.current_classifier_path == classifier_r2_path and hasattr(self, 'classifier_data') and self.classifier_data is not None:
            print(f"Using cached classifier: {classifier_r2_path}")
            return
        
        print(f"Loading classifier from R2: {classifier_r2_path}")
        
        import hashlib
        # Preserve original extension for type detection
        ext = ".pth" if classifier_r2_path.endswith(".pth") else ".pt"
        cache_key = hashlib.md5(classifier_r2_path.encode()).hexdigest()[:16]
        cache_file = self.cache_path / f"cls_{cache_key}{ext}"
        
        if not cache_file.exists():
            if not download_model_from_r2(classifier_r2_path, cache_file):
                raise RuntimeError(f"Failed to download classifier from {classifier_r2_path}")
        
        # Load with auto-detection based on extension
        if classifier_r2_path.endswith(".pth"):
            # ConvNeXt classifier
            import timm
            import torch
            from torchvision import transforms
            
            device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
            ckpt = torch.load(cache_file, map_location=device, weights_only=False)
            
            model_size = ckpt.get("model_size", "tiny")
            num_classes = len(ckpt["classes"])
            
            print(f"  Loading ConvNeXt-{model_size} with {num_classes} classes...")
            model = timm.create_model(f"convnext_{model_size}", pretrained=False, num_classes=num_classes)
            model.load_state_dict(ckpt["model_state_dict"])
            model = model.to(device).eval()
            
            # Create transform matching training
            img_size = ckpt.get("image_size", 224)
            transform = transforms.Compose([
                transforms.Resize(int(img_size * 1.14)),
                transforms.CenterCrop(img_size),
                transforms.ToTensor(),
                transforms.Normalize([0.485, 0.456, 0.406], [0.229, 0.224, 0.225]),
            ])
            
            self.classifier_data = {
                "type": "convnext",
                "model": model,
                "idx_to_class": ckpt["idx_to_class"],
                "transform": transform,
                "device": device,
            }
            self.classifier = None  # Not used for ConvNeXt
            print("ConvNeXt classifier loaded successfully")
        else:
            # YOLO classifier
            from ultralytics import YOLO
            self.classifier = YOLO(str(cache_file))
            self.classifier_data = {
                "type": "yolo",
                "model": self.classifier,
            }
            print("YOLO classifier loaded successfully")
        
        self.current_classifier_path = classifier_r2_path
    
    def _parse_yolo_predictions(self, results, img_width: int, img_height: int, classes: list) -> list:
        """Parse YOLO detection results into API format."""
        predictions = []
        
        if len(results) > 0 and results[0].boxes is not None:
            boxes = results[0].boxes
            
            for i in range(len(boxes)):
                xyxy = boxes.xyxy[i].cpu().numpy().tolist()
                x1, y1, x2, y2 = xyxy
                
                class_id = int(boxes.cls[i].cpu().item())
                confidence = float(boxes.conf[i].cpu().item())
                
                if classes and class_id < len(classes):
                    class_name = classes[class_id]
                else:
                    class_name = self.model.names.get(class_id, f"class_{class_id}")
                
                predictions.append({
                    "class_id": class_id,
                    "class_name": class_name,
                    "confidence": round(confidence, 4),
                    "box": [
                        round(x1 / img_width, 6),
                        round(y1 / img_height, 6),
                        round(x2 / img_width, 6),
                        round(y2 / img_height, 6),
                    ],
                })
        
        return predictions
    
    def _classify_crop(self, crop_bytes: bytes, crop_path: Path = None) -> tuple:
        """
        Classify a crop using the loaded classifier (YOLO or ConvNeXt).
        
        Args:
            crop_bytes: Raw image bytes of the crop
            crop_path: Optional path to save crop (required for YOLO)
        
        Returns:
            Tuple of (class_name, confidence) or (None, 0.0) on failure
        """
        if self.classifier_data["type"] == "convnext":
            # ConvNeXt classification
            import torch
            from PIL import Image
            
            model = self.classifier_data["model"]
            transform = self.classifier_data["transform"]
            idx_to_class = self.classifier_data["idx_to_class"]
            device = self.classifier_data["device"]
            
            img = Image.open(io.BytesIO(crop_bytes)).convert("RGB")
            
            with torch.no_grad():
                input_tensor = transform(img).unsqueeze(0).to(device)
                outputs = model(input_tensor)
                probs = torch.softmax(outputs, dim=1)
                conf, idx = probs.max(1)
            
            return idx_to_class[idx.item()], conf.item()
        else:
            # YOLO classification
            if crop_path is None:
                raise ValueError("crop_path required for YOLO classification")
            
            crop_path.write_bytes(crop_bytes)
            results = self.classifier.predict(str(crop_path), verbose=False)
            
            if results and len(results) > 0:
                probs = results[0].probs
                if probs is not None:
                    top1_idx = probs.top1
                    top1_conf = probs.top1conf.item()
                    top1_class = self.classifier.names[top1_idx]
                    return top1_class, top1_conf
            
            return None, 0.0
    
    # =========================================================================
    # DETECTION FLOW (YOLO)
    # =========================================================================
    
    @modal.method()
    def predict_image(
        self,
        weights_r2_path: str,
        image_bytes: bytes,
        confidence: float = 0.25,
        classes: list[str] = None,
    ) -> dict:
        """
        Run YOLO detection inference on a single image.
        """
        from PIL import Image
        
        try:
            self._load_yolo_model(weights_r2_path)
            
            image = Image.open(io.BytesIO(image_bytes))
            img_width, img_height = image.size
            
            print(f"Running YOLO detection on {img_width}x{img_height} image...")
            
            results = self.model.predict(image, conf=confidence, verbose=False)
            predictions = self._parse_yolo_predictions(results, img_width, img_height, classes or [])
            
            print(f"Found {len(predictions)} detections")
            
            return {
                "predictions": predictions,
                "image_width": img_width,
                "image_height": img_height,
            }
            
        except Exception as e:
            print(f"Image inference failed: {e}")
            import traceback
            traceback.print_exc()
            raise
    
    @modal.method()
    def process_video_job(
        self,
        job_id: str,
        weights_r2_path: str,
        video_bytes: bytes,
        confidence: float = 0.25,
        frame_skip: int = 1,
        start_time: float = 0.0,
        end_time: float | None = None,
        classes: list[str] = None,
    ) -> dict:
        """
        Process a video inference job (YOLO detection) with progress tracking.
        """
        import cv2
        import subprocess
        from supabase import create_client
        
        supabase = None
        temp_video_path = None
        trimmed_path = None
        
        try:
            supabase = create_client(
                os.environ["SUPABASE_URL"],
                os.environ["SUPABASE_KEY"],
            )
            
            supabase.table("api_jobs").update({"status": "processing"}).eq("id", job_id).execute()
            
            self._load_yolo_model(weights_r2_path)
            
            # Save video to temp file
            with tempfile.NamedTemporaryFile(suffix=".mp4", delete=False) as tmp:
                tmp.write(video_bytes)
                temp_video_path = tmp.name
            
            # Trim if needed
            trimmed_path = temp_video_path
            if start_time > 0 or end_time is not None:
                trimmed_path = temp_video_path.replace(".mp4", "_trim.mp4")
                ffmpeg_cmd = ["ffmpeg"]
                if start_time > 0:
                    ffmpeg_cmd.extend(["-ss", str(start_time)])
                ffmpeg_cmd.extend(["-i", temp_video_path])
                if end_time is not None:
                    ffmpeg_cmd.extend(["-t", str(end_time - start_time)])
                ffmpeg_cmd.extend(["-c:v", "libx264", "-preset", "ultrafast", "-crf", "23", "-an", trimmed_path, "-y"])
                subprocess.run(ffmpeg_cmd, capture_output=True, check=True)
            
            # Get video metadata
            cap = cv2.VideoCapture(trimmed_path)
            fps = cap.get(cv2.CAP_PROP_FPS)
            total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
            width = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
            height = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
            cap.release()
            
            est_frames = total_frames // frame_skip
            supabase.table("api_jobs").update({"progress_total": est_frames}).eq("id", job_id).execute()
            
            # Process video
            results_gen = self.model.predict(trimmed_path, conf=confidence, vid_stride=frame_skip, verbose=False, stream=True)
            
            predictions_by_frame = {}
            total_detections = 0
            frames_processed = 0
            
            for frame_idx, result in enumerate(results_gen):
                actual_frame = frame_idx * frame_skip
                frame_preds = self._parse_yolo_predictions([result], width, height, classes or [])
                predictions_by_frame[str(actual_frame)] = frame_preds
                total_detections += len(frame_preds)
                frames_processed += 1
                
                if frames_processed % 10 == 0:
                    try:
                        supabase.table("api_jobs").update({"progress_current": frames_processed}).eq("id", job_id).execute()
                    except Exception:
                        pass
            
            final_result = {
                "predictions_by_frame": predictions_by_frame,
                "total_frames_processed": frames_processed,
                "total_detections": total_detections,
                "fps": fps,
                "video_width": width,
                "video_height": height,
            }
            
            supabase.table("api_jobs").update({
                "status": "completed",
                "progress_current": frames_processed,
                "result_json": final_result,
            }).eq("id", job_id).execute()
            
            return final_result
            
        except Exception as e:
            print(f"Video inference failed: {e}")
            if supabase:
                try:
                    supabase.table("api_jobs").update({"status": "failed", "error_message": str(e)}).eq("id", job_id).execute()
                except Exception:
                    pass
            raise
        finally:
            if temp_video_path:
                Path(temp_video_path).unlink(missing_ok=True)
            if trimmed_path and trimmed_path != temp_video_path:
                Path(trimmed_path).unlink(missing_ok=True)
    
    # =========================================================================
    # HYBRID FLOW (SAM3 + CLASSIFIER)
    # =========================================================================
    
    @modal.method()
    def predict_image_hybrid(
        self,
        classifier_r2_path: str,
        image_bytes: bytes,
        sam3_prompt: str = "animal",
        classifier_classes: list[str] = None,
        confidence: float = 0.25,
        sam3_confidence: float = 0.25,
        include_masks: bool = True,
        sam3_imgsz: int = 640,
    ) -> dict:
        """
        Run hybrid SAM3 + Classifier inference on a single image.
        
        Flow:
        1. SAM3 detects with generic prompt (e.g., "animal")
        2. Each detection is cropped
        3. Classifier identifies species from crop
        4. Return all classifications (with optional mask polygons)
        
        Args:
            include_masks: If True, include mask_polygon for each prediction
        """
        import cv2
        import numpy as np
        from ultralytics.models.sam import SAM3SemanticPredictor
        from PIL import Image
        
        work_dir = Path(tempfile.mkdtemp(prefix="api_hybrid_"))
        
        try:
            print(f"=== Hybrid Image Inference ===")
            print(f"SAM3 prompt: {sam3_prompt}")
            print(f"SAM3 confidence: {sam3_confidence}")
            print(f"Classifier classes: {classifier_classes}")
            
            # Get image dimensions
            img_array = np.frombuffer(image_bytes, np.uint8)
            img = cv2.imdecode(img_array, cv2.IMREAD_COLOR)
            img_height, img_width = img.shape[:2]
            print(f"Image size: {img_width}x{img_height}")
            
            # Save image for SAM3
            image_path = work_dir / "input.jpg"
            image_path.write_bytes(image_bytes)
            
            # === SAM3 Detection ===
            print("Running SAM3 detection...")
            
            overrides = dict(
                conf=sam3_confidence,
                task="segment",
                mode="predict",
                model="/models/sam3.pt",
                imgsz=sam3_imgsz,
                half=False,
                save=False,
            )
            
            predictor = SAM3SemanticPredictor(overrides=overrides)
            predictor.set_image(str(image_path))
            
            results_list = predictor(text=[sam3_prompt])
            
            sam3_detections = []  # List of (box, mask_polygon)
            if results_list and len(results_list) > 0:
                res = results_list[0]
                if hasattr(res, 'boxes') and res.boxes is not None:
                    boxes = res.boxes.xyxy.cpu().numpy()
                    print(f"SAM3 found {len(boxes)} detections")
                    
                    # Extract masks if requested
                    masks_data = None
                    if include_masks and hasattr(res, 'masks') and res.masks is not None:
                        try:
                            if hasattr(res.masks, 'data'):
                                masks_data = res.masks.data.cpu().numpy()
                                print(f"Masks extracted: shape {masks_data.shape}")
                        except Exception as e:
                            print(f"Error extracting masks: {e}")
                    
                    for idx, box in enumerate(boxes):
                        mask_polygon = None
                        if masks_data is not None and idx < len(masks_data):
                            mask_polygon = mask_to_polygon(masks_data[idx], img_width, img_height)
                        sam3_detections.append((box[:4], mask_polygon))
            
            if not sam3_detections:
                print("No SAM3 detections, returning empty")
                return {
                    "predictions": [],
                    "image_width": img_width,
                    "image_height": img_height,
                    "sam3_detections": 0,
                }
            
            # === Load Classifier ===
            print("Loading classifier...")
            self._load_classifier(classifier_r2_path)
            
            class_to_id = {name: idx for idx, name in enumerate(classifier_classes or [])}
            
            # === Classify Each Crop ===
            print("Classifying crops...")
            final_predictions = []
            
            for idx, (box, mask_polygon) in enumerate(sam3_detections):
                try:
                    x1, y1, x2, y2 = box
                    crop_bytes = crop_from_box(image_bytes, (x1, y1, x2, y2), padding=0.05)
                    
                    crop_path = work_dir / f"crop_{idx}.jpg"
                    top1_class, top1_conf = self._classify_crop(crop_bytes, crop_path)
                    
                    if top1_class is None:
                        print(f"  [{idx}] No classification result → Unknown")
                    
                    if top1_class is not None and top1_conf >= confidence:
                        pred_class_name = top1_class
                        pred_class_id = class_to_id.get(top1_class, idx)
                        pred_confidence = round(top1_conf, 4)
                        print(f"  [{idx}] {top1_class} ({top1_conf:.2f}) ✓")
                    else:
                        pred_class_name = "Unknown"
                        pred_class_id = -1
                        pred_confidence = 0.0
                        if top1_class is not None:
                            print(f"  [{idx}] {top1_class} ({top1_conf:.2f}) → Unknown (below threshold)")
                    
                    pred = {
                        "class_name": pred_class_name,
                        "class_id": pred_class_id,
                        "confidence": pred_confidence,
                        "box": [
                            round(float(x1) / img_width, 6),
                            round(float(y1) / img_height, 6),
                            round(float(x2) / img_width, 6),
                            round(float(y2) / img_height, 6),
                        ],
                    }
                    # Include mask polygon if requested and available
                    if include_masks:
                        pred["mask_polygon"] = mask_polygon
                    final_predictions.append(pred)
                                
                except Exception as e:
                    print(f"  [{idx}] Error: {e}")
            
            print(f"=== Results: {len(final_predictions)} predictions ===")
            
            return {
                "predictions": final_predictions,
                "image_width": img_width,
                "image_height": img_height,
                "sam3_detections": len(sam3_detections),
            }
            
        except Exception as e:
            print(f"Hybrid image inference failed: {e}")
            import traceback
            traceback.print_exc()
            raise
        finally:
            import shutil
            shutil.rmtree(work_dir, ignore_errors=True)
    
    # =========================================================================
    # BATCH INFERENCE (for Tauri frame sequences)
    # =========================================================================
    
    @modal.method()
    def predict_images_batch(
        self,
        weights_r2_path: str,
        images_data: list[bytes],
        confidence: float = 0.25,
        classes: list[str] = None,
    ) -> list[dict]:
        """
        Run YOLO detection inference on multiple images in a single call.
        
        Reuses the YOLO model across all images to amortize cold start.
        Designed for high-throughput Tauri frame sequences.
        
        Args:
            weights_r2_path: R2 path to YOLO weights
            images_data: List of raw image bytes (max 100 images)
            confidence: Detection confidence threshold
            classes: List of class names
            
        Returns:
            List of results, one per image:
            [
                {
                    "index": 0,
                    "predictions": [...],
                    "image_width": 1920,
                    "image_height": 1080,
                },
                ...
            ]
        """
        import cv2
        import numpy as np
        from PIL import Image
        
        print(f"=== Batch YOLO Inference: {len(images_data)} images ===")
        
        try:
            # Load model ONCE
            self._load_yolo_model(weights_r2_path)
            
            results_list = []
            
            for idx, image_bytes in enumerate(images_data):
                try:
                    # Decode image from bytes (no disk I/O)
                    img_array = np.frombuffer(image_bytes, np.uint8)
                    img = cv2.imdecode(img_array, cv2.IMREAD_COLOR)
                    
                    if img is None:
                        results_list.append({
                            "index": idx,
                            "success": False,
                            "error": "Failed to decode image",
                            "predictions": [],
                        })
                        continue
                    
                    img_height, img_width = img.shape[:2]
                    
                    # Convert BGR to RGB for PIL/YOLO
                    img_rgb = cv2.cvtColor(img, cv2.COLOR_BGR2RGB)
                    pil_image = Image.fromarray(img_rgb)
                    
                    # Run inference
                    results = self.model.predict(pil_image, conf=confidence, verbose=False)
                    predictions = self._parse_yolo_predictions(results, img_width, img_height, classes or [])
                    
                    results_list.append({
                        "index": idx,
                        "success": True,
                        "predictions": predictions,
                        "image_width": img_width,
                        "image_height": img_height,
                    })
                    
                    if (idx + 1) % 10 == 0:
                        print(f"  Processed {idx + 1}/{len(images_data)} images")
                        
                except Exception as e:
                    print(f"  Image {idx} failed: {e}")
                    results_list.append({
                        "index": idx,
                        "success": False,
                        "error": str(e),
                        "predictions": [],
                    })
            
            total_predictions = sum(len(r.get("predictions", [])) for r in results_list)
            print(f"=== Batch complete: {len(results_list)} images, {total_predictions} predictions ===")
            
            return results_list
            
        except Exception as e:
            print(f"Batch inference failed: {e}")
            import traceback
            traceback.print_exc()
            raise
    
    @modal.method()
    def predict_images_hybrid_batch(
        self,
        classifier_r2_path: str,
        images_data: list[bytes],
        sam3_prompt: str = "animal",
        classifier_classes: list[str] = None,
        confidence: float = 0.25,
        sam3_confidence: float = 0.25,
        include_masks: bool = True,
        sam3_imgsz: int = 640,
    ) -> list[dict]:
        """
        Run hybrid SAM3 + Classifier inference on multiple images.
        
        Reuses SAM3 predictor and classifier across all images.
        Designed for high-throughput Tauri frame sequences.
        
        Args:
            classifier_r2_path: R2 path to classifier weights
            images_data: List of raw image bytes (max 100 images)
            sam3_prompt: Generic prompt for SAM3 detection
            classifier_classes: List of class names
            sam3_confidence: SAM3 detection confidence
            confidence: Minimum classifier confidence
            include_masks: If True, include mask_polygon for each prediction
            
        Returns:
            List of results, one per image
        """
        import cv2
        import numpy as np
        from ultralytics import YOLO
        from ultralytics.models.sam import SAM3SemanticPredictor
        
        work_dir = Path(tempfile.mkdtemp(prefix="api_hybrid_batch_"))
        
        print(f"=== Batch Hybrid Inference: {len(images_data)} images ===")
        print(f"SAM3 prompt: {sam3_prompt}")
        print(f"SAM3 confidence: {sam3_confidence}")
        print(f"Classifier confidence: {confidence}")
        print(f"Classifier classes: {classifier_classes}")
        
        try:
            # === Initialize SAM3 predictor ONCE ===
            print("[Setup] Loading SAM3 predictor...")
            overrides = dict(
                conf=sam3_confidence,
                task="segment",
                mode="predict",
                model="/models/sam3.pt",
                imgsz=sam3_imgsz,
                half=False,
                save=False,
            )
            predictor = SAM3SemanticPredictor(overrides=overrides)
            
            # === Load classifier ONCE ===
            print("[Setup] Loading classifier...")
            self._load_classifier(classifier_r2_path)
            
            class_to_id = {name: idx for idx, name in enumerate(classifier_classes or [])}
            
            results_list = []
            
            # === Process each image ===
            for idx, image_bytes in enumerate(images_data):
                try:
                    # Decode image from bytes
                    img_array = np.frombuffer(image_bytes, np.uint8)
                    img = cv2.imdecode(img_array, cv2.IMREAD_COLOR)
                    
                    if img is None:
                        results_list.append({
                            "index": idx,
                            "success": False,
                            "error": "Failed to decode image",
                            "predictions": [],
                        })
                        continue
                    
                    img_height, img_width = img.shape[:2]
                    
                    # Save temporarily for SAM3 (it requires file path)
                    image_path = work_dir / f"input_{idx}.jpg"
                    cv2.imwrite(str(image_path), img)
                    
                    # Run SAM3 detection
                    predictor.set_image(str(image_path))
                    sam3_results = predictor(text=[sam3_prompt])
                    
                    sam3_detections = []  # List of (box, mask_polygon)
                    if sam3_results and len(sam3_results) > 0:
                        res = sam3_results[0]
                        if hasattr(res, 'boxes') and res.boxes is not None:
                            boxes = res.boxes.xyxy.cpu().numpy()
                            
                            # Extract masks if requested
                            masks_data = None
                            if include_masks and hasattr(res, 'masks') and res.masks is not None:
                                try:
                                    if hasattr(res.masks, 'data'):
                                        masks_data = res.masks.data.cpu().numpy()
                                except Exception:
                                    pass
                            
                            for box_idx, box in enumerate(boxes):
                                mask_polygon = None
                                if masks_data is not None and box_idx < len(masks_data):
                                    mask_polygon = mask_to_polygon(masks_data[box_idx], img_width, img_height)
                                sam3_detections.append((box[:4], mask_polygon))
                    
                    if not sam3_detections:
                        results_list.append({
                            "index": idx,
                            "success": True,
                            "predictions": [],
                            "image_width": img_width,
                            "image_height": img_height,
                            "sam3_detections": 0,
                        })
                        continue
                    
                    # Classify each detection
                    final_predictions = []
                    
                    for det_idx, (box, mask_polygon) in enumerate(sam3_detections):
                        try:
                            x1, y1, x2, y2 = box
                            crop_bytes = crop_from_box(image_bytes, (x1, y1, x2, y2), padding=0.05)
                            
                            crop_path = work_dir / f"crop_{idx}_{det_idx}.jpg"
                            top1_class, top1_conf = self._classify_crop(crop_bytes, crop_path)
                            
                            if top1_class is None:
                                continue
                            
                            # Accept if confidence meets threshold, otherwise Unknown
                            if top1_conf >= confidence:
                                pred_class_name = top1_class
                                pred_class_id = class_to_id.get(top1_class, det_idx)
                                pred_confidence = round(top1_conf, 4)
                            else:
                                pred_class_name = "Unknown"
                                pred_class_id = -1
                                pred_confidence = 0.0
                            
                            pred = {
                                "class_name": pred_class_name,
                                "class_id": pred_class_id,
                                "confidence": pred_confidence,
                                "box": [
                                    round(float(x1) / img_width, 6),
                                    round(float(y1) / img_height, 6),
                                    round(float(x2) / img_width, 6),
                                    round(float(y2) / img_height, 6),
                                ],
                            }
                            # Include mask polygon if requested and available
                            if include_masks:
                                pred["mask_polygon"] = mask_polygon
                            final_predictions.append(pred)
                        except Exception as e:
                            print(f"  Image {idx} crop {det_idx} failed: {e}")
                    
                    results_list.append({
                        "index": idx,
                        "success": True,
                        "predictions": final_predictions,
                        "image_width": img_width,
                        "image_height": img_height,
                        "sam3_detections": len(sam3_detections),
                    })
                    
                    if (idx + 1) % 10 == 0:
                        print(f"  Processed {idx + 1}/{len(images_data)} images")
                        
                except Exception as e:
                    print(f"  Image {idx} failed: {e}")
                    results_list.append({
                        "index": idx,
                        "success": False,
                        "error": str(e),
                        "predictions": [],
                    })
            
            total_predictions = sum(len(r.get("predictions", [])) for r in results_list)
            print(f"=== Batch complete: {len(results_list)} images, {total_predictions} predictions ===")
            
            return results_list
            
        except Exception as e:
            print(f"Batch hybrid inference failed: {e}")
            import traceback
            traceback.print_exc()
            raise
        finally:
            import shutil
            shutil.rmtree(work_dir, ignore_errors=True)
    
    @modal.method()
    def process_video_job_hybrid(
        self,
        job_id: str,
        classifier_r2_path: str,
        video_bytes: bytes,
        sam3_prompt: str = "animal",
        classifier_classes: list[str] = None,
        confidence: float = 0.25,
        sam3_confidence: float = 0.25,
        frame_skip: int = 1,
        start_time: float = 0.0,
        end_time: float | None = None,
        classify_top_k: int = 3,
        sam3_imgsz: int = 640,
        include_masks: bool = True,
    ) -> dict:
        """
        Process a hybrid video inference job with tracking.
        
        Uses SAM3VideoSemanticPredictor for temporal consistency:
        1. SAM3 detects and tracks objects across frames
        2. Each unique track is classified once
        3. Classifications are propagated to all frames
        """
        import cv2
        import numpy as np
        import subprocess
        from ultralytics import YOLO
        from ultralytics.models.sam import SAM3VideoSemanticPredictor
        from supabase import create_client
        
        work_dir = Path(tempfile.mkdtemp(prefix="api_hybrid_video_"))
        supabase = None
        
        try:
            print(f"=== Hybrid Video Inference ===")
            print(f"SAM3 prompt: {sam3_prompt}")
            print(f"Frame skip: {frame_skip}")
            
            supabase = create_client(
                os.environ["SUPABASE_URL"],
                os.environ["SUPABASE_KEY"],
            )
            
            supabase.table("api_jobs").update({"status": "processing"}).eq("id", job_id).execute()
            
            # Save video
            video_path = work_dir / "video.mp4"
            video_path.write_bytes(video_bytes)
            
            # Trim if needed
            if start_time > 0 or end_time is not None:
                trimmed_path = work_dir / "trimmed.mp4"
                ffmpeg_cmd = ["ffmpeg"]
                if start_time > 0:
                    ffmpeg_cmd.extend(["-ss", str(start_time)])
                ffmpeg_cmd.extend(["-i", str(video_path)])
                if end_time is not None:
                    ffmpeg_cmd.extend(["-t", str(end_time - start_time)])
                ffmpeg_cmd.extend(["-c:v", "libx264", "-preset", "ultrafast", "-crf", "23", "-an", str(trimmed_path), "-y"])
                subprocess.run(ffmpeg_cmd, capture_output=True, check=True)
                video_path = trimmed_path
            
            # Get video metadata
            cap = cv2.VideoCapture(str(video_path))
            fps = cap.get(cv2.CAP_PROP_FPS)
            total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
            frame_width = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
            frame_height = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
            cap.release()
            
            print(f"Video: {total_frames} frames, {fps:.2f} FPS, {frame_width}x{frame_height}")
            
            # === Load Classifier ===
            print("Loading classifier...")
            self._load_classifier(classifier_r2_path)
            class_to_id = {name: idx for idx, name in enumerate(classifier_classes or [])}
            
            # === SAM3 Video Detection ===
            print("Running SAM3 video detection...")
            
            overrides = dict(
                conf=confidence,
                task="segment",
                mode="predict",
                model="/models/sam3.pt",
                imgsz=sam3_imgsz,
                half=False,
                save=False,
            )
            
            video_predictor = SAM3VideoSemanticPredictor(overrides=overrides)
            
            sam3_results_iter = video_predictor(
                source=str(video_path),
                text=[sam3_prompt],
                stream=True,
            )
            
            # Collect detections with track IDs — accumulate ALL candidate frames per track
            all_frame_detections = []
            unique_tracks = {}  # track_id -> {candidate_frames: [{frame, box}, ...]}
            
            for frame_idx, result in enumerate(sam3_results_iter):
                frame_dets = []
                
                if hasattr(result, 'boxes') and result.boxes is not None:
                    boxes = result.boxes.xyxy.cpu().numpy()
                    
                    track_ids = None
                    if hasattr(result.boxes, 'id') and result.boxes.id is not None:
                        track_ids = result.boxes.id.cpu().numpy().astype(int)
                    
                    # Extract masks inline — convert to polygon immediately, discard raw tensor
                    masks_data = None
                    if include_masks and hasattr(result, 'masks') and result.masks is not None:
                        try:
                            if hasattr(result.masks, 'data'):
                                masks_data = result.masks.data.cpu().numpy()
                        except Exception:
                            pass
                    
                    for idx, box in enumerate(boxes):
                        track_id = int(track_ids[idx]) if track_ids is not None else idx + frame_idx * 1000
                        
                        # Inline mask-to-polygon (avoids storing raw tensors in RAM)
                        mask_polygon = None
                        if masks_data is not None and idx < len(masks_data):
                            mask_polygon = mask_to_polygon(masks_data[idx], frame_width, frame_height)
                        
                        frame_dets.append({
                            "box": box[:4],
                            "track_id": track_id,
                            "mask_polygon": mask_polygon,
                        })
                        
                        # Accumulate all candidate frames for Top-K selection
                        if track_id not in unique_tracks:
                            unique_tracks[track_id] = {"candidate_frames": []}
                        unique_tracks[track_id]["candidate_frames"].append({
                            "frame": frame_idx,
                            "box": box[:4].tolist(),
                        })
                
                all_frame_detections.append({
                    "frame_number": frame_idx,
                    "timestamp": frame_idx / fps,
                    "detections": frame_dets,
                })
                
                if frame_idx % 50 == 0:
                    print(f"  SAM3 frame {frame_idx}/{total_frames}, {len(frame_dets)} detections")
                    try:
                        supabase.table("api_jobs").update({"progress_current": frame_idx}).eq("id", job_id).execute()
                    except Exception:
                        pass
            
            print(f"SAM3 done: {len(all_frame_detections)} frames, {len(unique_tracks)} unique tracks")
            
            # === Classify Unique Tracks (Quality-Diverse Top-K) ===
            print(f"Classifying unique tracks (top-K={classify_top_k})...")
            
            cap = cv2.VideoCapture(str(video_path))
            classifications = {}  # track_id -> (class_name, class_id, confidence)
            
            for track_id, track_info in unique_tracks.items():
                candidates = track_info.get("candidate_frames", [])
                if not candidates:
                    continue
                
                # Select K diverse, high-quality frames
                selected = select_diverse_frames(
                    candidates, classify_top_k, frame_width, frame_height,
                )
                
                # Classify each selected frame
                frame_results = []  # (class_name, confidence)
                
                for sel in selected:
                    frame_num = sel["frame"]
                    box = sel["box"]
                    
                    cap.set(cv2.CAP_PROP_POS_FRAMES, frame_num)
                    ret, frame = cap.read()
                    if not ret:
                        frame_results.append((None, 0.0))
                        continue
                    
                    try:
                        _, frame_encoded = cv2.imencode('.jpg', frame)
                        frame_bytes = frame_encoded.tobytes()
                        x1, y1, x2, y2 = box
                        crop_bytes = crop_from_box(frame_bytes, (x1, y1, x2, y2), padding=0.05)
                        crop_path = work_dir / f"crop_t{track_id}_f{frame_num}.jpg"
                        top1_class, top1_conf = self._classify_crop(crop_bytes, crop_path)
                        frame_results.append((top1_class, top1_conf))
                    except Exception as e:
                        print(f"  Track {track_id} frame {frame_num}: error - {e}")
                        frame_results.append((None, 0.0))
                
                # Majority vote
                winner, _, avg_conf, agreement = vote_classifications(
                    frame_results, confidence,
                )
                
                vote_str = ", ".join(
                    f"{cls}({conf:.2f})" if cls else "fail"
                    for cls, conf in frame_results
                )
                
                if winner != "Unknown":
                    class_id = class_to_id.get(winner, -1)
                    classifications[track_id] = (winner, class_id, avg_conf)
                    print(f"  Track {track_id}: {winner} (avg={avg_conf:.2f}, agree={agreement:.0%}) ← [{vote_str}]")
                else:
                    print(f"  Track {track_id}: skipped (below threshold) ← [{vote_str}]")
            
            cap.release()
            print(f"Classified {len(classifications)} tracks")
            
            # === Propagate Labels ===
            print("Propagating labels to frames...")
            
            frame_results = []
            
            for frame_data in all_frame_detections:
                frame_number = frame_data["frame_number"]
                
                # Apply frame_skip for output
                if frame_number % frame_skip != 0:
                    continue
                
                frame_predictions = []
                
                for det in frame_data["detections"]:
                    track_id = det["track_id"]
                    box = det["box"]
                    
                    # Skip detections with no valid classification
                    if track_id not in classifications:
                        continue
                    
                    class_name, class_id, conf = classifications[track_id]
                    
                    x1, y1, x2, y2 = box
                    pred = {
                        "class_name": class_name,
                        "class_id": class_id,
                        "confidence": round(conf, 4),
                        "box": [
                            round(float(x1) / frame_width, 6),
                            round(float(y1) / frame_height, 6),
                            round(float(x2) / frame_width, 6),
                            round(float(y2) / frame_height, 6),
                        ],
                        "track_id": track_id,
                    }
                    if include_masks:
                        pred["mask_polygon"] = det.get("mask_polygon")
                    frame_predictions.append(pred)
                
                frame_results.append({
                    "frame_number": frame_number,
                    "timestamp": frame_data["timestamp"],
                    "predictions": frame_predictions,
                })
            
            total_predictions = sum(len(f["predictions"]) for f in frame_results)
            
            final_result = {
                "frame_results": frame_results,
                "processed_frames": len(frame_results),
                "total_predictions": total_predictions,
                "unique_tracks": len(unique_tracks),
                "classified_tracks": len(classifications),
                "fps": fps,
                "video_width": frame_width,
                "video_height": frame_height,
            }
            
            supabase.table("api_jobs").update({
                "status": "completed",
                "progress_current": len(frame_results),
                "result_json": final_result,
            }).eq("id", job_id).execute()
            
            print(f"=== Done: {len(frame_results)} frames, {total_predictions} predictions ===")
            
            return final_result
            
        except Exception as e:
            print(f"Hybrid video inference failed: {e}")
            import traceback
            traceback.print_exc()
            
            if supabase:
                try:
                    supabase.table("api_jobs").update({
                        "status": "failed",
                        "error_message": str(e),
                    }).eq("id", job_id).execute()
                except Exception:
                    pass
            raise
        finally:
            import shutil
            shutil.rmtree(work_dir, ignore_errors=True)


# For local testing
if __name__ == "__main__":
    print("This module should be deployed to Modal, not run directly.")
    print("Deploy with: modal deploy backend/modal_jobs/api_infer_job.py")
