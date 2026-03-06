"""
Core Hybrid Inference Logic — SAM3 Detection + Classifier Species Identification.

This module contains the shared pipeline logic used by both Modal jobs and remote workers.
Environment-specific concerns (model paths, download functions) are passed as parameters.

Functions:
    mask_to_polygon: Convert binary mask to normalized polygon points
    run_sam3_detection: Run SAM3 on an image with text prompts
    run_classification_loop: Classify each detection and filter by confidence  
    run_hybrid_inference: Orchestrate the full pipeline
"""

import base64
import io
import os
import tempfile
from pathlib import Path
from typing import Callable, Optional

# Import shared utilities from core
from backend.core.image_utils import crop_from_box, download_image
from backend.core.classifier_utils import load_classifier, classify_with_convnext


def mask_to_polygon(
    mask,  # numpy array (H, W)
    img_width: int,
    img_height: int,
) -> Optional[list]:
    """
    Convert a binary/probability mask to normalized polygon points.
    
    Args:
        mask: 2D numpy array representing the mask
        img_width: Original image width for normalization
        img_height: Original image height for normalization
    
    Returns:
        List of [x, y] normalized coordinates, or None if contours not found
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
            float(px) / img_width,
            float(py) / img_height
        ])
    
    return polygon_points


def run_sam3_detection(
    image_path: Path,
    img_width: int,
    img_height: int,
    sam3_prompts: list[str],
    confidence_threshold: float,
    sam3_model_path: Optional[str] = None,
    bbox_padding: float = 0.03,
    sam3_imgsz: int = 644,
) -> list[tuple]:
    """
    Run SAM3 semantic detection on an image.
    
    Args:
        image_path: Path to the image file
        img_width: Image width for mask normalization
        img_height: Image height for mask normalization
        sam3_prompts: List of text prompts (e.g., ["mammal", "bird"])
        confidence_threshold: Detection confidence threshold
        sam3_model_path: Optional path to SAM3 model. If None, uses auto-download.
    
    Returns:
        List of (box, prompt, mask_polygon) tuples where:
            - box: (x1, y1, x2, y2) in pixel coordinates
            - prompt: The SAM3 prompt that triggered this detection
            - mask_polygon: List of [x, y] normalized points, or None
    """
    import numpy as np
    from ultralytics.models.sam import SAM3SemanticPredictor
    
    # Build predictor overrides
    overrides = dict(
        conf=confidence_threshold,
        task="segment",
        mode="predict",
        imgsz=sam3_imgsz,
        half=True,
        save=False,
    )
    
    # Add model path if specified
    if sam3_model_path:
        overrides["model"] = sam3_model_path
        print(f"  [SAM3] Loading fine-tuned model: {sam3_model_path}")
    else:
        print(f"  [SAM3] Loading pretrained model (auto-download)")
    
    predictor = SAM3SemanticPredictor(overrides=overrides)
    predictor.set_image(str(image_path))
    
    # Collect all detections with their source prompt and masks
    sam3_detections = []
    
    for prompt in sam3_prompts:
        print(f"  Prompt: '{prompt}'")
        results_list = predictor(text=[prompt])
        
        if results_list and len(results_list) > 0:
            res = results_list[0]
            
            if hasattr(res, 'boxes') and res.boxes is not None:
                boxes = res.boxes.xyxy.cpu().numpy()
                print(f"    Found {len(boxes)} detections")
                
                # Expand SAM3 boxes to compensate for conservative predictions
                if bbox_padding > 0 and len(boxes) > 0:
                    from backend.core.autolabel_core import expand_boxes
                    expand_boxes(boxes, img_width, img_height, bbox_padding)
                
                # Extract masks if available
                masks_data = None
                if hasattr(res, 'masks') and res.masks is not None:
                    try:
                        if hasattr(res.masks, 'data'):
                            masks_data = res.masks.data.cpu().numpy()  # Shape: (N, H, W)
                            print(f"    Masks extracted: shape {masks_data.shape}")
                    except Exception as e:
                        print(f"    Error extracting masks: {e}")
                
                for idx, box in enumerate(boxes):
                    mask_polygon = None
                    
                    # Convert mask to polygon if available
                    if masks_data is not None and isinstance(masks_data, np.ndarray) and idx < len(masks_data):
                        mask_polygon = mask_to_polygon(masks_data[idx], img_width, img_height)
                    
                    sam3_detections.append((box[:4], prompt, mask_polygon))
            else:
                print(f"    No boxes")
        else:
            print(f"    No results")
    
    print(f"  Total SAM3 detections: {len(sam3_detections)}")
    return sam3_detections


def run_classification_loop(
    image_bytes: bytes,
    img_width: int,
    img_height: int,
    sam3_detections: list[tuple],
    classifier_data: dict,
    classifier_classes: list[str],
    classifier_confidence: float,
    work_dir: Path,
) -> tuple[list[dict], list[dict], bytes | None]:
    """
    Classify each SAM3 detection and filter by confidence.
    
    Args:
        image_bytes: Raw image bytes for cropping
        img_width: Image width for normalization
        img_height: Image height for normalization
        sam3_detections: List of (box, prompt, mask_polygon) from SAM3
        classifier_data: Dict from load_classifier() with model info
        classifier_classes: List of expected class names
        classifier_confidence: Minimum confidence to accept
        work_dir: Directory for temporary files
    
    Returns:
        Tuple of (predictions, masks, first_crop_bytes) where:
            - predictions: List of prediction dicts
            - masks: List of mask dicts (only for accepted predictions)
            - first_crop_bytes: Raw bytes of the first crop (for debugging), or None
    """
    is_convnext = classifier_data["type"] == "convnext"
    
    if is_convnext:
        convnext_model = classifier_data["model"]
        convnext_idx_to_class = classifier_data["idx_to_class"]
        convnext_transform = classifier_data["transform"]
        convnext_device = classifier_data["device"]
    else:
        classifier = classifier_data["model"]
    
    # Build class name to ID mapping
    class_to_id = {name: idx for idx, name in enumerate(classifier_classes)}
    
    final_predictions = []
    final_masks = []
    first_crop_bytes = None
    
    for idx, (box, sam3_prompt, mask_polygon) in enumerate(sam3_detections):
        try:
            # Crop the detection
            x1, y1, x2, y2 = box
            crop_bytes = crop_from_box(image_bytes, (x1, y1, x2, y2), padding=0.05)
            
            # Capture first crop for debugging
            if first_crop_bytes is None:
                first_crop_bytes = crop_bytes
            
            # Classify using appropriate model
            if is_convnext:
                top1_class, top1_conf = classify_with_convnext(
                    convnext_model, convnext_transform, crop_bytes, convnext_idx_to_class, convnext_device
                )
            else:
                # Save crop temporarily for YOLO classifier
                crop_path = work_dir / f"crop_{idx}.jpg"
                crop_path.write_bytes(crop_bytes)
                
                results = classifier.predict(str(crop_path), verbose=False)
                
                if results and len(results) > 0:
                    res = results[0]
                    probs = res.probs
                    
                    if probs is not None:
                        top1_idx = probs.top1
                        top1_conf = probs.top1conf.item()
                        top1_class = classifier.names[top1_idx]
                    else:
                        print(f"  [{idx}] No classification probs → Unknown")
                        top1_class = None
                        top1_conf = 0.0
                else:
                    print(f"  [{idx}] Classifier returned no results → Unknown")
                    top1_class = None
                    top1_conf = 0.0
            
            # Determine if classified or unknown
            if top1_class is not None and top1_conf >= classifier_confidence:
                # Classified successfully
                pred_class_name = top1_class
                pred_class_id = class_to_id.get(top1_class, 0)
                pred_confidence = top1_conf
                print(f"  [{idx}] SAM3='{sam3_prompt}' → Classifier='{top1_class}' ({top1_conf:.2f}) ✓ Accepted")
            else:
                # SAM3 detected an animal but classifier couldn't identify species
                pred_class_name = "Unknown"
                pred_class_id = -1
                pred_confidence = 0.0
                if top1_class is not None:
                    print(f"  [{idx}] SAM3='{sam3_prompt}' → Classifier='{top1_class}' ({top1_conf:.2f}) → Unknown (below threshold)")
                else:
                    print(f"  [{idx}] SAM3='{sam3_prompt}' → Unknown (classification failed)")
            
            # Normalize box to 0-1 range
            final_predictions.append({
                "class_name": pred_class_name,
                "class_id": pred_class_id,
                "confidence": pred_confidence,
                "box": [
                    float(x1) / img_width,
                    float(y1) / img_height,
                    float(x2) / img_width,
                    float(y2) / img_height,
                ],
                "sam3_prompt": sam3_prompt,
            })
            
            # Add mask if available
            if mask_polygon:
                final_masks.append({
                    "class_name": pred_class_name,
                    "class_id": pred_class_id,
                    "polygon": mask_polygon,
                })
                
        except Exception as e:
            print(f"  [{idx}] Error classifying crop: {e}")
    
    return final_predictions, final_masks, first_crop_bytes


def format_yolo_labels(predictions: list[dict]) -> str:
    """Convert predictions to YOLO label format string."""
    yolo_lines = []
    for pred in predictions:
        x1, y1, x2, y2 = pred["box"]  # Already normalized
        class_id = pred["class_id"]
        
        # Convert xyxy to xywh format
        x_center = (x1 + x2) / 2
        y_center = (y1 + y2) / 2
        width = x2 - x1
        height = y2 - y1
        
        yolo_lines.append(f"{class_id} {x_center:.6f} {y_center:.6f} {width:.6f} {height:.6f}")
    
    return "\n".join(yolo_lines)


def run_hybrid_inference(
    image_url: str,
    sam3_prompts: list[str],
    classifier_r2_path: str,
    classifier_classes: list[str],
    prompt_class_map: dict[str, list[str]],
    confidence_threshold: float,
    classifier_confidence: float,
    # Environment-specific parameters:
    sam3_model_path: Optional[str] = None,
    sam3_imgsz: int = 644,
    download_classifier_fn: Callable[[str, Path], bool] = None,
) -> dict:
    """
    Run the full hybrid SAM3 + Classifier inference pipeline.
    
    This is the main entry point called by both Modal jobs and remote workers.
    
    Args:
        image_url: Presigned URL to the image
        sam3_prompts: List of generic prompts for SAM3
        classifier_r2_path: R2 path to classifier model weights
        classifier_classes: List of class names the classifier can predict
        prompt_class_map: Mapping from SAM3 prompt to valid classifier classes
        confidence_threshold: SAM3 detection confidence threshold
        classifier_confidence: Minimum classifier confidence to accept
        sam3_model_path: Path to SAM3 model (None for auto-download)
        download_classifier_fn: Function to download classifier from R2
    
    Returns:
        Dict with predictions, masks, yolo_labels, and metadata
    """
    import cv2
    import numpy as np
    import shutil
    
    # Disable AutoUpdate
    os.environ["ULTRALYTICS_AUTOUPDATE"] = "false"
    
    # Create temp directory
    work_dir = Path(tempfile.mkdtemp(prefix="hybrid_infer_"))
    
    try:
        print(f"=== Hybrid Inference ===")
        print(f"SAM3 prompts: {sam3_prompts}")
        print(f"Classifier classes: {classifier_classes}")
        
        # === Step 1: Download image ===
        print("\n[1/5] Downloading image...")
        image_bytes = download_image(image_url)
        
        # Get image dimensions
        img_array = np.frombuffer(image_bytes, np.uint8)
        img = cv2.imdecode(img_array, cv2.IMREAD_COLOR)
        img_height, img_width = img.shape[:2]
        print(f"  Image size: {img_width}x{img_height}")
        
        # Save to disk for SAM3
        image_path = work_dir / "input.jpg"
        image_path.write_bytes(image_bytes)
        
        # === Step 2: Run SAM3 detection ===
        print("\n[2/5] Running SAM3 detection...")
        sam3_detections = run_sam3_detection(
            image_path=image_path,
            img_width=img_width,
            img_height=img_height,
            sam3_prompts=sam3_prompts,
            confidence_threshold=confidence_threshold,
            sam3_model_path=sam3_model_path,
            sam3_imgsz=sam3_imgsz,
        )
        
        if not sam3_detections:
            return {
                "success": True,
                "predictions": [],
                "masks": [],
                "yolo_labels": "",
                "image_width": img_width,
                "image_height": img_height,
                "sam3_detections": 0,
                "filtered_detections": 0,
            }
        
        # === Step 3: Download and load classifier ===
        # Flush GPU memory after SAM3 to reduce fragmentation before classifier load
        import gc
        import torch
        gc.collect()
        if torch.cuda.is_available():
            torch.cuda.empty_cache()
        print("\n[3/5] Loading classifier model...")
        ext = ".pth" if classifier_r2_path.endswith(".pth") else ".pt"
        classifier_path = work_dir / f"classifier{ext}"
        
        if download_classifier_fn:
            if not download_classifier_fn(classifier_r2_path, classifier_path):
                raise RuntimeError(f"Failed to download classifier from {classifier_r2_path}")
        else:
            raise ValueError("download_classifier_fn is required")
        
        classifier_data = load_classifier(classifier_r2_path, classifier_path)
        print(f"  Classifier loaded: {classifier_data['type']}")
        
        # === Step 4: Classify each crop ===
        print("\n[4/5] Classifying crops...")
        final_predictions, final_masks, first_crop_bytes = run_classification_loop(
            image_bytes=image_bytes,
            img_width=img_width,
            img_height=img_height,
            sam3_detections=sam3_detections,
            classifier_data=classifier_data,
            classifier_classes=classifier_classes,
            classifier_confidence=classifier_confidence,
            work_dir=work_dir,
        )
        
        # === Step 5: Format output ===
        print("\n[5/5] Formatting output...")
        yolo_labels = format_yolo_labels(final_predictions)
        
        print(f"\n=== Results ===")
        print(f"SAM3 detections: {len(sam3_detections)}")
        print(f"Final predictions: {len(final_predictions)}")
        print(f"Masks extracted: {len(final_masks)}")
        
        return {
            "success": True,
            "predictions": final_predictions,
            "masks": final_masks,
            "yolo_labels": yolo_labels,
            "image_width": img_width,
            "image_height": img_height,
            "sam3_detections": len(sam3_detections),
            "filtered_detections": len(final_predictions),
            "debug_crop": base64.b64encode(first_crop_bytes).decode("ascii") if first_crop_bytes else None,
        }
        
    except Exception as e:
        import traceback
        error_msg = str(e)
        print(f"\nHybrid inference failed: {error_msg}")
        traceback.print_exc()
        
        return {
            "success": False,
            "error": error_msg,
            "predictions": [],
            "masks": [],
            "yolo_labels": "",
        }
        
    finally:
        # Cleanup
        import shutil
        shutil.rmtree(work_dir, ignore_errors=True)
