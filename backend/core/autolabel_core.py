"""
Core Autolabel Logic — YOLO and SAM3 Automatic Annotation.

This module contains the shared autolabeling pipeline logic used by both Modal jobs
and remote workers, enabling full Modal/Local GPU parity.

Key Components:
- YOLO mode: Custom trained model inference
- SAM3 mode: Text/bbox/point semantic segmentation
- Coordinate conversion utilities
- Annotation formatting for Supabase storage

Usage (Modal):
    from backend.core.autolabel_core import run_yolo_autolabel, run_sam3_autolabel
    
    results, class_names = run_yolo_autolabel(
        image_paths=image_paths,
        yolo_model_path="/yolo_models/model.pt",
        confidence=0.25,
    )

Usage (Remote Worker):
    from backend.core.autolabel_core import run_yolo_autolabel, run_sam3_autolabel
    
    results, class_names = run_yolo_autolabel(
        image_paths=image_paths,
        yolo_model_path="~/.tyto/models/yolo_abc123.pt",
        confidence=0.25,
    )
"""

import json
import uuid as uuid_lib
from pathlib import Path
from typing import Optional

import cv2
import numpy as np

from backend.core.hybrid_infer_core import mask_to_polygon


# =============================================================================
# Bounding Box Utilities
# =============================================================================

def expand_boxes(
    boxes: np.ndarray,
    img_width: int,
    img_height: int,
    padding: float = 0.03,
) -> np.ndarray:
    """
    Symmetrically expand bounding boxes by a fraction of their dimensions.
    
    Note: This is still used by API inference paths (hybrid_infer_core,
    hybrid_video_core) but is NO LONGER used by SAM3 autolabel, which
    derives bboxes from masks instead.
    
    Args:
        boxes: (N, 4+) array with xyxy coordinates in columns 0-3
        img_width: Image width for clamping
        img_height: Image height for clamping
        padding: Fraction of box w/h to expand on each side (0.03 = 3%)
    
    Returns:
        boxes array with expanded coordinates (modified in-place)
    """
    if padding <= 0 or len(boxes) == 0:
        return boxes
    
    for i in range(len(boxes)):
        x1, y1, x2, y2 = boxes[i][:4]
        w, h = x2 - x1, y2 - y1
        boxes[i][0] = max(0, x1 - w * padding)
        boxes[i][1] = max(0, y1 - h * padding)
        boxes[i][2] = min(img_width, x2 + w * padding)
        boxes[i][3] = min(img_height, y2 + h * padding)
    
    return boxes


def bbox_from_polygon(polygon: list[list[float]]) -> tuple[float, float, float, float]:
    """
    Derive a tight bounding box from a normalized mask polygon.
    
    Args:
        polygon: List of [x, y] points, normalized to [0, 1]
        
    Returns:
        (x, y, width, height) in normalized coordinates (top-left origin)
    """
    xs = [p[0] for p in polygon]
    ys = [p[1] for p in polygon]
    x_min, x_max = min(xs), max(xs)
    y_min, y_max = min(ys), max(ys)
    return x_min, y_min, x_max - x_min, y_max - y_min


# =============================================================================
# Coordinate Conversion Utilities
# =============================================================================

def xyxy_to_yolo_line(
    xyxy: tuple[float, float, float, float],
    width: int,
    height: int,
    class_id: int,
) -> str:
    """
    Convert xyxy bounding box to normalized YOLO format string.
    
    Args:
        xyxy: Bounding box as (x1, y1, x2, y2) in absolute pixel coordinates
        width: Image width in pixels
        height: Image height in pixels
        class_id: Class index for this detection
        
    Returns:
        YOLO format string: "class_id x_center y_center width height" (all normalized 0-1)
    """
    x1, y1, x2, y2 = xyxy
    
    # Convert to normalized center + size
    x_center = ((x1 + x2) / 2) / width
    y_center = ((y1 + y2) / 2) / height
    w = (x2 - x1) / width
    h = (y2 - y1) / height
    
    # Clamp to [0, 1]
    x_center = max(0.0, min(1.0, x_center))
    y_center = max(0.0, min(1.0, y_center))
    w = max(0.0, min(1.0, w))
    h = max(0.0, min(1.0, h))
    
    return f"{class_id} {x_center:.6f} {y_center:.6f} {w:.6f} {h:.6f}"


def yolo_lines_to_annotations(
    yolo_lines: list[str],
    class_names_lookup: dict[int, str],
    mask_polygons: Optional[list[Optional[list]]] = None,
) -> list[dict]:
    """
    Convert YOLO format lines to annotation dicts for Supabase storage.
    
    Args:
        yolo_lines: List of YOLO format strings
        class_names_lookup: Mapping of class_id -> class_name
        mask_polygons: Optional list of mask polygons (parallel to yolo_lines).
            Each entry is either a list of [x,y] normalized points or None.
        
    Returns:
        List of annotation dicts with {id, class_id, x, y, width, height, mask_polygon?}
        Note: x, y are top-left corner (canvas format), not center
    """
    annotations = []
    
    for idx, line in enumerate(yolo_lines):
        parts = line.split()
        if len(parts) >= 5:
            class_id = int(parts[0])
            x_center = float(parts[1])
            y_center = float(parts[2])
            w = float(parts[3])
            h = float(parts[4])
            
            # Convert center to top-left corner for canvas format
            x = x_center - w / 2
            y = y_center - h / 2
            
            # Get class name from lookup (may be "Unknown" if not found)
            class_name = class_names_lookup.get(class_id, "Unknown")
            
            ann = {
                "id": str(uuid_lib.uuid4()),
                "class_id": class_id,
                "class_name": class_name,
                "x": x,
                "y": y,
                "width": w,
                "height": h,
            }
            
            # Attach mask polygon if available for this detection
            if mask_polygons and idx < len(mask_polygons) and mask_polygons[idx] is not None:
                ann["mask_polygon"] = mask_polygons[idx]
            
            annotations.append(ann)
    
    return annotations


# =============================================================================
# YOLO Autolabel
# =============================================================================

def run_yolo_autolabel(
    image_paths: dict[str, Path],
    yolo_model_path: str,
    confidence: float = 0.25,
) -> tuple[dict[str, list[str]], dict[int, str]]:
    """
    Run YOLO detection autolabeling on images.
    
    Args:
        image_paths: Mapping of image_id -> local file path
        yolo_model_path: Path to custom YOLO .pt model file
        confidence: Detection confidence threshold (0-1)
        
    Returns:
        Tuple of:
        - results_by_image: {image_id: [yolo_line, ...]}
        - class_names_lookup: {class_id: class_name} from model
    """
    from ultralytics import YOLO
    
    # Load model
    yolo_model = YOLO(yolo_model_path)
    print(f"YOLO model loaded: {len(yolo_model.names)} classes")
    print(f"Classes: {yolo_model.names}")
    
    # Model's class names become the lookup
    class_names_lookup = yolo_model.names  # {0: 'class0', 1: 'class1', ...}
    
    results_by_image = {}
    total_detections = 0
    
    for image_id, image_path in image_paths.items():
        try:
            img = cv2.imread(str(image_path))
            if img is None:
                print(f"Error: Could not read image {image_id}")
                results_by_image[image_id] = []
                continue
            
            height, width = img.shape[:2]
            
            # Run YOLO prediction
            results = yolo_model.predict(str(image_path), conf=confidence, verbose=False)
            
            yolo_lines = []
            if results and len(results) > 0:
                res = results[0]
                if res.boxes is not None and len(res.boxes) > 0:
                    for box in res.boxes:
                        cls_id = int(box.cls[0].item())
                        x1, y1, x2, y2 = box.xyxy[0].cpu().numpy()
                        
                        yolo_line = xyxy_to_yolo_line(
                            (x1, y1, x2, y2), width, height, cls_id
                        )
                        yolo_lines.append(yolo_line)
            
            results_by_image[image_id] = yolo_lines
            total_detections += len(yolo_lines)
            print(f"Image {image_id}: {len(yolo_lines)} detections")
            
        except Exception as e:
            print(f"Error processing image {image_id}: {e}")
            results_by_image[image_id] = []
    
    print(f"YOLO autolabel complete: {total_detections} total detections")
    return results_by_image, class_names_lookup


# =============================================================================
# SAM3 Autolabel
# =============================================================================

def run_sam3_autolabel(
    image_paths: dict[str, Path],
    prompt_type: str,
    prompt_value: str,
    sam3_model_path: str,
    confidence: float = 0.25,
    prompt_class_map: Optional[dict[str, int]] = None,
    class_names_lookup: Optional[dict[int, str]] = None,
    save_masks: bool = True,
    # Legacy params (accepted but ignored for backward compat)
    bbox_padding: float = 0.0,
    include_masks: bool = True,
) -> tuple[dict[str, dict], dict[int, str]]:
    """
    Run SAM3 semantic segmentation autolabeling.
    
    SAM3 always produces masks internally. Bounding boxes are derived from
    the mask polygon's bounding rectangle for perfect alignment.
    
    Args:
        image_paths: Mapping of image_id -> local file path
        prompt_type: One of "text", "bbox", "point"
        prompt_value: Prompt content (comma-separated text or JSON for bbox/point)
        sam3_model_path: Path to SAM3 .pt model file
        confidence: Detection confidence threshold (0-1)
        prompt_class_map: {prompt_term: class_id} mapping for text mode (required)
        class_names_lookup: {class_id: class_name} for annotation formatting
        save_masks: If True, include mask_polygon in results (masks are always
            extracted internally for bbox derivation)
        
    Returns:
        Tuple of:
        - results_by_image: {image_id: {"yolo_lines": [...], "mask_polygons": [...]}}
          mask_polygons is parallel to yolo_lines (None entries if mask extraction fails)
        - class_names_lookup: {class_id: class_name} (passed through or generated)
    """
    from ultralytics.models.sam import SAM3SemanticPredictor
    
    # Parse prompts based on type
    if prompt_type == "text":
        raw_prompts = [p.strip() for p in prompt_value.split(",") if p.strip()]
        
        if not prompt_class_map:
            raise ValueError("prompt_class_map is required for SAM3 text mode")
        
        # Build class_id_map from provided mapping
        class_id_map = {}
        for prompt in raw_prompts:
            if prompt in prompt_class_map:
                class_id_map[prompt] = prompt_class_map[prompt]
            else:
                raise ValueError(f"Prompt '{prompt}' not found in prompt_class_map")
        
        print(f"SAM3 text mode: {raw_prompts}")
        print(f"Class ID map: {class_id_map}")
        
        # Use provided class_names_lookup or create from prompts
        if class_names_lookup is None:
            class_names_lookup = {v: k.replace(" ", "_") for k, v in prompt_class_map.items()}
    else:
        raw_prompts = [prompt_value]
        class_id_map = {prompt_value: 0}  # Legacy single class_id
        if class_names_lookup is None:
            class_names_lookup = {0: prompt_value.replace(" ", "_")}
    
    # Initialize SAM3 predictor
    overrides = dict(
        conf=confidence,
        task="segment",
        mode="predict",
        model=sam3_model_path,
        half=True,
        save=False,
    )
    
    predictor = SAM3SemanticPredictor(overrides=overrides)
    print(f"SAM3 model loaded from {sam3_model_path}")
    print(f"Mask-derived bboxes enabled (box padding disabled)")
    
    results_by_image = {}
    total_detections = 0
    total_masks = 0
    
    def _process_detections(res, cls_id, width, height, yolo_lines, mask_polygons_list):
        """Extract masks from SAM3 results and derive bboxes from mask bounds."""
        nonlocal total_masks, total_detections
        
        if not (hasattr(res, 'boxes') and res.boxes is not None):
            return
        
        n_boxes = len(res.boxes)
        
        # Always extract masks — SAM3 is a segmentation model
        masks_data = None
        if hasattr(res, 'masks') and res.masks is not None:
            masks_data = res.masks.data.cpu().numpy()
        
        for idx in range(n_boxes):
            poly = None
            if masks_data is not None and idx < len(masks_data):
                poly = mask_to_polygon(masks_data[idx], width, height)
            
            if poly:
                # Derive bbox from mask polygon (tight fit, perfect alignment)
                bx, by, bw, bh = bbox_from_polygon(poly)
                yolo_line = f"{cls_id} {bx + bw/2:.6f} {by + bh/2:.6f} {bw:.6f} {bh:.6f}"
                total_masks += 1
            else:
                # Fallback: use SAM3's native bbox if mask extraction failed
                box = res.boxes.xyxy.cpu().numpy()[idx]
                x1, y1, x2, y2 = box[:4]
                yolo_line = xyxy_to_yolo_line(
                    (x1, y1, x2, y2), width, height, cls_id
                )
            
            yolo_lines.append(yolo_line)
            mask_polygons_list.append(poly)
    
    for image_id, image_path in image_paths.items():
        try:
            img = cv2.imread(str(image_path))
            if img is None:
                print(f"Error: Could not read image {image_id}")
                results_by_image[image_id] = {"yolo_lines": [], "mask_polygons": []}
                continue
            
            height, width = img.shape[:2]
            predictor.set_image(str(image_path))
            
            yolo_lines = []
            mask_polygons_list = []  # Parallel to yolo_lines
            
            if prompt_type == "text":
                # Run inference for each prompt separately to track class IDs
                for prompt in raw_prompts:
                    cls_id = class_id_map.get(prompt, 0)
                    results_list = predictor(text=[prompt])
                    if results_list and len(results_list) > 0:
                        _process_detections(
                            results_list[0], cls_id, width, height,
                            yolo_lines, mask_polygons_list,
                        )
            
            elif prompt_type == "bbox":
                bbox_data = json.loads(prompt_value)
                bboxes = bbox_data.get("bboxes", [])
                results_list = predictor(bboxes=bboxes)
                if results_list and len(results_list) > 0:
                    _process_detections(
                        results_list[0], 0, width, height,
                        yolo_lines, mask_polygons_list,
                    )
            
            elif prompt_type == "point":
                point_data = json.loads(prompt_value)
                points = point_data.get("points", [])
                labels = point_data.get("labels", [1] * len(points))
                results_list = predictor(points=points, labels=labels)
                if results_list and len(results_list) > 0:
                    _process_detections(
                        results_list[0], 0, width, height,
                        yolo_lines, mask_polygons_list,
                    )
            
            else:
                raise ValueError(f"Unknown prompt type: {prompt_type}")
            
            results_by_image[image_id] = {
                "yolo_lines": yolo_lines,
                "mask_polygons": mask_polygons_list if save_masks else [],
            }
            total_detections += len(yolo_lines)
            print(f"Image {image_id}: {len(yolo_lines)} detections, {sum(1 for p in mask_polygons_list if p)} masks")
            
        except Exception as e:
            print(f"Error processing image {image_id}: {e}")
            results_by_image[image_id] = {"yolo_lines": [], "mask_polygons": []}
    
    print(f"SAM3 autolabel complete: {total_detections} total detections, {total_masks} masks")
    return results_by_image, class_names_lookup


# =============================================================================
# SAM3 Mask-from-Bboxes (Fast Path)
# =============================================================================

def run_sam3_mask_from_bboxes(
    image_paths: dict[str, Path],
    existing_annotations: dict[str, list[dict]],
    sam3_model_path: str,
) -> dict[str, list[dict]]:
    """
    Generate mask polygons for images that already have bbox annotations.
    
    Uses SAM3's bbox-prompt mode for fast mask generation (~10-20x faster
    than full text-prompt detection since no grounding scan is needed).
    
    Args:
        image_paths: Mapping of image_id -> local file path
        existing_annotations: {image_id: [{id, class_id, class_name, x, y, width, height}]}
        sam3_model_path: Path to SAM3 .pt model file
        
    Returns:
        {image_id: [updated_annotation_dicts_with_mask_polygon]}
    """
    from ultralytics import SAM
    
    model = SAM(sam3_model_path)
    print(f"SAM3 model loaded for bbox-prompt mask generation")
    
    results_by_image = {}
    total_masks = 0
    
    for image_id, image_path in image_paths.items():
        annotations = existing_annotations.get(image_id, [])
        if not annotations:
            results_by_image[image_id] = []
            continue
        
        try:
            img = cv2.imread(str(image_path))
            if img is None:
                print(f"Error: Could not read image {image_id}")
                results_by_image[image_id] = annotations  # Return unchanged
                continue
            
            height, width = img.shape[:2]
            
            # Convert annotations to xyxy bboxes for SAM3 prompt
            bboxes = []
            for ann in annotations:
                # Annotations use top-left (x, y) + (width, height), normalized 0-1
                x1 = ann["x"] * width
                y1 = ann["y"] * height
                x2 = (ann["x"] + ann["width"]) * width
                y2 = (ann["y"] + ann["height"]) * height
                bboxes.append([x1, y1, x2, y2])
            
            # Run SAM3 with bbox prompts
            results = model(str(image_path), bboxes=bboxes)
            
            updated_annotations = []
            if results and len(results) > 0:
                res = results[0]
                masks_data = None
                if hasattr(res, 'masks') and res.masks is not None:
                    masks_data = res.masks.data.cpu().numpy()
                
                for idx, ann in enumerate(annotations):
                    ann_copy = dict(ann)  # Don't mutate originals
                    if masks_data is not None and idx < len(masks_data):
                        poly = mask_to_polygon(masks_data[idx], width, height)
                        if poly:
                            ann_copy["mask_polygon"] = poly
                            total_masks += 1
                    updated_annotations.append(ann_copy)
            else:
                updated_annotations = annotations
            
            results_by_image[image_id] = updated_annotations
            print(f"Image {image_id}: {len([a for a in updated_annotations if 'mask_polygon' in a])} masks")
            
        except Exception as e:
            print(f"Error processing image {image_id}: {e}")
            results_by_image[image_id] = annotations  # Return unchanged
    
    print(f"SAM3 bbox-prompt mask generation complete: {total_masks} masks")
    return results_by_image
