"""
YOLO Detection Core — Shared inference logic for Modal and remote workers.

This module contains pure detection logic that is environment-agnostic:
- Result parsing (YOLO boxes to normalized coordinates)
- YOLO format conversion (predictions to label strings)
- Single image inference core
- Batch image inference core
- Video frame inference core

Environment-specific concerns (model loading, image downloading, Supabase
progress updates) remain in the calling code (Modal job or remote worker).
"""

from typing import Callable, Optional
from PIL import Image


def parse_yolo_results(
    model_names: dict,
    results,
    img_width: int,
    img_height: int,
) -> list[dict]:
    """
    Parse YOLO detection results into standardized format.
    
    Args:
        model_names: Dictionary mapping class_id to class_name (model.names)
        results: YOLO prediction results (single frame/image)
        img_width: Image width in pixels
        img_height: Image height in pixels
        
    Returns:
        List of prediction dicts with normalized 0-1 coordinates:
        [
            {
                "class_id": 0,
                "class_name": "person",
                "confidence": 0.92,
                "box": [x1_norm, y1_norm, x2_norm, y2_norm]
            },
            ...
        ]
    """
    predictions = []
    
    if len(results) > 0 and results[0].boxes is not None:
        boxes = results[0].boxes
        
        for i in range(len(boxes)):
            # Get box coordinates (xyxy format, pixel values)
            xyxy = boxes.xyxy[i].cpu().numpy().tolist()
            
            # Normalize to 0-1 range
            x1, y1, x2, y2 = xyxy
            x1_norm = x1 / img_width
            y1_norm = y1 / img_height
            x2_norm = x2 / img_width
            y2_norm = y2 / img_height
            
            # Get class and confidence
            class_id = int(boxes.cls[i].cpu().item())
            confidence = float(boxes.conf[i].cpu().item())
            class_name = model_names.get(class_id, f"class_{class_id}")
            
            predictions.append({
                "class_id": class_id,
                "class_name": class_name,
                "confidence": confidence,
                "box": [x1_norm, y1_norm, x2_norm, y2_norm],
            })
    
    return predictions


def format_predictions_to_yolo(
    predictions: list[dict],
    img_width: int,
    img_height: int,
) -> str:
    """
    Convert predictions to YOLO format labels.
    
    YOLO format: class_id x_center y_center width height (all normalized 0-1)
    
    Args:
        predictions: List of predictions from parse_yolo_results
        img_width: Image width in pixels (unused, kept for API consistency)
        img_height: Image height in pixels (unused, kept for API consistency)
        
    Returns:
        String in YOLO format (one line per detection)
    """
    lines = []
    
    for pred in predictions:
        # Convert xyxy normalized box to xywh normalized
        x1, y1, x2, y2 = pred["box"]
        x_center = (x1 + x2) / 2
        y_center = (y1 + y2) / 2
        width = x2 - x1
        height = y2 - y1
        
        # Format: class_id x_center y_center width height
        line = f"{pred['class_id']} {x_center:.6f} {y_center:.6f} {width:.6f} {height:.6f}"
        lines.append(line)
    
    return "\n".join(lines)


def run_yolo_single_inference(
    model,
    image: Image.Image,
    confidence: float = 0.25,
) -> tuple[list[dict], int, int]:
    """
    Run YOLO detection on a single image.
    
    Args:
        model: Loaded YOLO model
        image: PIL Image to run inference on
        confidence: Confidence threshold (0-1)
        
    Returns:
        Tuple of (predictions, img_width, img_height)
    """
    img_width, img_height = image.size
    
    # Run inference
    results = model.predict(
        image,
        conf=confidence,
        verbose=False,
    )
    
    # Parse results
    predictions = parse_yolo_results(model.names, results, img_width, img_height)
    
    return predictions, img_width, img_height


def run_yolo_batch_inference(
    model,
    image_urls: list[str],
    confidence: float,
    download_fn: Callable[[str], bytes],
) -> list[dict]:
    """
    Run YOLO detection on multiple images sequentially.
    
    Keeps the GPU warm across all images, eliminating cold start overhead.
    
    Args:
        model: Loaded YOLO model
        image_urls: List of image URLs to process
        confidence: Confidence threshold (0-1)
        download_fn: Function to download image bytes from URL
        
    Returns:
        List of result dicts, one per image:
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
    import io
    
    results_list = []
    
    for idx, image_url in enumerate(image_urls):
        try:
            # Download image
            print(f"[{idx+1}/{len(image_urls)}] Downloading image...")
            image_bytes = download_fn(image_url)
            image = Image.open(io.BytesIO(image_bytes))
            
            # Run inference
            predictions, img_width, img_height = run_yolo_single_inference(
                model, image, confidence
            )
            
            # Convert to YOLO format
            labels_txt = format_predictions_to_yolo(predictions, img_width, img_height)
            
            print(f"[{idx+1}/{len(image_urls)}] Found {len(predictions)} detections")
            
            results_list.append({
                "index": idx,
                "predictions": predictions,
                "labels_txt": labels_txt,
                "detection_count": len(predictions),
                "image_width": img_width,
                "image_height": img_height,
            })
            
        except Exception as e:
            print(f"[{idx+1}/{len(image_urls)}] Failed: {e}")
            results_list.append({
                "index": idx,
                "error": str(e),
                "predictions": [],
                "labels_txt": "",
                "detection_count": 0,
            })
    
    return results_list


def run_yolo_video_inference(
    model,
    video_path: str,
    confidence: float,
    frame_skip: int = 1,
    progress_callback: Optional[Callable[[int, int], None]] = None,
) -> dict:
    """
    Run YOLO detection on video frames.
    
    Args:
        model: Loaded YOLO model
        video_path: Path to video file (already downloaded/trimmed)
        confidence: Confidence threshold (0-1)
        frame_skip: Process every Nth frame (1 = every frame)
        progress_callback: Optional callback(frames_processed, total_frames)
        
    Returns:
        {
            "predictions_by_frame": {"0": [...], "5": [...], ...},
            "labels_by_frame": {"0": "...", "5": "...", ...},
            "total_frames_processed": 120,
            "total_detections": 45,
            "fps": 30.0,
            "video_width": 1920,
            "video_height": 1080,
        }
    """
    import cv2
    
    # Get video metadata
    cap = cv2.VideoCapture(video_path)
    fps = cap.get(cv2.CAP_PROP_FPS)
    total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
    width = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
    height = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
    cap.release()
    
    print(f"Video: {width}x{height}, {fps:.2f} FPS, {total_frames} frames")
    print(f"Processing every {frame_skip} frame(s)...")
    
    # Process video with YOLO
    results_generator = model.predict(
        video_path,
        conf=confidence,
        vid_stride=frame_skip,
        verbose=False,
        stream=True,  # Stream results to avoid memory issues
    )
    
    predictions_by_frame = {}
    labels_by_frame = {}
    total_detections = 0
    frames_processed = 0
    est_total_frames = total_frames // frame_skip
    
    for frame_idx, result in enumerate(results_generator):
        # Actual frame number accounting for skip
        actual_frame = frame_idx * frame_skip
        
        # Parse predictions for this frame
        frame_predictions = parse_yolo_results(model.names, [result], width, height)
        
        # Store predictions
        predictions_by_frame[str(actual_frame)] = frame_predictions
        
        # Convert to YOLO format
        labels_txt = format_predictions_to_yolo(frame_predictions, width, height)
        labels_by_frame[str(actual_frame)] = labels_txt
        
        total_detections += len(frame_predictions)
        frames_processed += 1
        
        # Progress updates
        if frames_processed % 10 == 0:
            print(f"Processed {frames_processed} frames, {total_detections} detections so far")
            
            if progress_callback:
                progress_callback(frames_processed, est_total_frames)
    
    print(f"Video inference complete: {frames_processed} frames, {total_detections} detections")
    
    return {
        "predictions_by_frame": predictions_by_frame,
        "labels_by_frame": labels_by_frame,
        "total_frames_processed": frames_processed,
        "total_detections": total_detections,
        "fps": fps,
        "video_width": width,
        "video_height": height,
    }
