"""
Thumbnail Generator — Subject-centric thumbnails from inference results.

Generates stylized cutout thumbnails for inference results using either:
- Phase 1: SAM3 masks (hybrid inference) — purple-tinted polygon overlay
- Phase 2: Bounding boxes (detection-only) — purple-tinted rectangle overlay

Design tokens:
- Overlay: PURPLE (#A855F7) at 30% opacity
- Border: PURPLE (#A855F7) 2px solid
- Output: 120x120px square JPEG
"""

import tempfile
import subprocess
from typing import Optional
from pathlib import Path


# =============================================================================
# Styling Constants (shared across mask and box overlays)
# =============================================================================

PURPLE_RGB = (168, 85, 247)    # #A855F7 in RGB
PURPLE_BGR = (247, 85, 168)    # BGR for OpenCV

OVERLAY_OPACITY = 0.3          # 30% fill transparency
BORDER_THICKNESS = 2           # 2px border
CROP_PADDING = 0.35            # 35% padding around detection (balanced context)
THUMBNAIL_SIZE = 120           # 120x120px square


# =============================================================================
# Selection Functions (find largest detection)
# =============================================================================

def select_largest_detection(
    predictions: list[dict],
    masks: list[dict] | None = None,
) -> tuple[Optional[dict], Optional[dict]]:
    """
    Select the detection with the largest bounding box area.
    
    Args:
        predictions: List of prediction dicts with 'box' key (normalized xyxy)
        masks: Optional list of mask dicts with 'polygon' key
    
    Returns:
        Tuple of (prediction, mask) for the largest detection.
        mask is None if masks not provided or index not available.
    """
    if not predictions:
        return None, None
    
    largest_idx = -1
    largest_area = 0
    
    for idx, pred in enumerate(predictions):
        box = pred.get("box", [])
        if len(box) >= 4:
            x1, y1, x2, y2 = box[:4]
            area = (x2 - x1) * (y2 - y1)
            if area > largest_area:
                largest_area = area
                largest_idx = idx
    
    if largest_idx < 0:
        return None, None
    
    # Find matching mask (same index if available)
    mask = None
    if masks and largest_idx < len(masks):
        mask = masks[largest_idx]
    
    return predictions[largest_idx], mask


def select_best_frame_detection(
    predictions_by_frame: dict,
    masks_by_frame: dict,
) -> tuple[Optional[int], Optional[dict], Optional[dict]]:
    """
    Select the detection with the largest bounding box area across all frames.
    
    Args:
        predictions_by_frame: Dict of frame_num -> list of predictions
        masks_by_frame: Dict of frame_num -> list of masks
    
    Returns:
        Tuple of (frame_number, prediction, mask) for the largest detection
    """
    if not predictions_by_frame or not masks_by_frame:
        return None, None, None
    
    best_frame = None
    best_pred = None
    best_mask = None
    largest_area = 0
    
    for frame_str, predictions in predictions_by_frame.items():
        frame_num = int(frame_str)
        masks = masks_by_frame.get(str(frame_num), masks_by_frame.get(frame_num, []))
        
        if not masks:
            continue
        
        for idx, pred in enumerate(predictions):
            box = pred.get("box", [])
            if len(box) >= 4:
                x1, y1, x2, y2 = box[:4]
                area = (x2 - x1) * (y2 - y1)
                if area > largest_area and idx < len(masks):
                    largest_area = area
                    best_frame = frame_num
                    best_pred = pred
                    best_mask = masks[idx]
    
    return best_frame, best_pred, best_mask


def select_best_batch_detection(
    predictions_list: list[list[dict]],
    masks_list: list[list[dict]] | None = None,
) -> tuple[Optional[int], Optional[dict], Optional[dict]]:
    """
    Select the detection with the largest bounding box area across all batch images.
    
    Args:
        predictions_list: List of prediction lists, one per image
        masks_list: Optional list of mask lists, one per image
    
    Returns:
        Tuple of (image_index, prediction, mask) for the largest detection
    """
    if not predictions_list:
        return None, None, None
    
    best_idx = None
    best_pred = None
    best_mask = None
    largest_area = 0
    
    for img_idx, predictions in enumerate(predictions_list):
        masks = masks_list[img_idx] if masks_list and img_idx < len(masks_list) else None
        
        for pred_idx, pred in enumerate(predictions):
            box = pred.get("box", [])
            if len(box) >= 4:
                x1, y1, x2, y2 = box[:4]
                area = (x2 - x1) * (y2 - y1)
                if area > largest_area:
                    largest_area = area
                    best_idx = img_idx
                    best_pred = pred
                    best_mask = masks[pred_idx] if masks and pred_idx < len(masks) else None
    
    return best_idx, best_pred, best_mask


# =============================================================================
# Cropping & Formatting (shared utilities)
# =============================================================================

def _crop_with_padding(img, box_norm: list[float], padding: float = CROP_PADDING):
    """
    Crop image around bounding box with padding.
    
    Args:
        img: OpenCV image (BGR)
        box_norm: Normalized [x1, y1, x2, y2]
        padding: Padding ratio (default 20%)
    
    Returns:
        Tuple of (crop, crop_x1, crop_y1) for coordinate mapping
    """
    img_height, img_width = img.shape[:2]
    
    x1_norm, y1_norm, x2_norm, y2_norm = box_norm[:4]
    
    # Convert to pixel coordinates
    x1 = int(x1_norm * img_width)
    y1 = int(y1_norm * img_height)
    x2 = int(x2_norm * img_width)
    y2 = int(y2_norm * img_height)
    
    # Add padding
    box_width = x2 - x1
    box_height = y2 - y1
    pad_x = int(box_width * padding)
    pad_y = int(box_height * padding)
    
    crop_x1 = max(0, x1 - pad_x)
    crop_y1 = max(0, y1 - pad_y)
    crop_x2 = min(img_width, x2 + pad_x)
    crop_y2 = min(img_height, y2 + pad_y)
    
    crop = img[crop_y1:crop_y2, crop_x1:crop_x2].copy()
    
    return crop, crop_x1, crop_y1, img_width, img_height


def _square_resize(crop, output_size: int = THUMBNAIL_SIZE):
    """Center-crop to square and resize."""
    import cv2
    
    crop_height, crop_width = crop.shape[:2]
    
    # Center-crop to square (minimal loss with high padding)
    if crop_width > crop_height:
        offset = (crop_width - crop_height) // 2
        crop = crop[:, offset:offset + crop_height]
    elif crop_height > crop_width:
        offset = (crop_height - crop_width) // 2
        crop = crop[offset:offset + crop_width, :]
    
    return cv2.resize(crop, (output_size, output_size), interpolation=cv2.INTER_AREA)


def _encode_jpeg(img, quality: int = 85) -> Optional[bytes]:
    """Encode image as JPEG bytes."""
    import cv2
    
    success, encoded = cv2.imencode('.jpg', img, [cv2.IMWRITE_JPEG_QUALITY, quality])
    return encoded.tobytes() if success else None


# =============================================================================
# Overlay Functions (mask vs box)
# =============================================================================

def _apply_mask_overlay(crop, polygon_points: list, color=PURPLE_BGR, opacity=OVERLAY_OPACITY, border=BORDER_THICKNESS):
    """
    Apply styled mask polygon overlay.
    
    Args:
        crop: OpenCV image (BGR)
        polygon_points: List of [x, y] pixel coordinates (crop-relative)
        color: BGR color tuple
        opacity: Fill opacity (0-1)
        border: Border thickness in pixels
    
    Returns:
        Image with overlay applied
    """
    import cv2
    import numpy as np
    
    polygon_np = np.array([polygon_points], dtype=np.int32)
    
    overlay = crop.copy()
    cv2.fillPoly(overlay, polygon_np, color)
    crop = cv2.addWeighted(overlay, opacity, crop, 1 - opacity, 0)
    cv2.polylines(crop, polygon_np, isClosed=True, color=color, thickness=border)
    
    return crop


def _apply_box_overlay(crop, box_relative: tuple, color=PURPLE_BGR, opacity=OVERLAY_OPACITY, border=BORDER_THICKNESS):
    """
    Apply sophisticated spotlight effect for bounding box thumbnails.
    
    Creates a professional "spotlight" effect:
    1. Background is blurred (Gaussian) for depth-of-field simulation
    2. Background is desaturated to grayscale
    3. Subject area stays sharp and in full color
    4. Subtle glowing border around the subject
    
    Args:
        crop: OpenCV image (BGR)
        box_relative: (x1, y1, x2, y2) pixel coordinates (crop-relative)
        color: BGR color tuple (used for subtle glow)
        opacity: Not used in spotlight mode
        border: Border thickness in pixels
    
    Returns:
        Image with spotlight effect applied
    """
    import cv2
    import numpy as np
    
    x1, y1, x2, y2 = [int(v) for v in box_relative]
    h, w = crop.shape[:2]
    
    # Clamp coordinates to image bounds
    x1 = max(0, min(x1, w - 1))
    x2 = max(0, min(x2, w))
    y1 = max(0, min(y1, h - 1))
    y2 = max(0, min(y2, h))
    
    # Safety check for valid box dimensions
    if x2 <= x1 or y2 <= y1:
        return crop
    
    # =========================================================================
    # Step 1: Create blurred + desaturated background
    # =========================================================================
    
    # Apply strong Gaussian blur to entire image
    blur_strength = max(15, min(w, h) // 8)  # Adaptive blur based on size
    if blur_strength % 2 == 0:
        blur_strength += 1  # Must be odd
    blurred = cv2.GaussianBlur(crop, (blur_strength, blur_strength), 0)
    
    # Convert to grayscale and back to BGR (desaturated)
    gray = cv2.cvtColor(blurred, cv2.COLOR_BGR2GRAY)
    desaturated = cv2.cvtColor(gray, cv2.COLOR_GRAY2BGR)
    
    # Darken the desaturated background slightly (multiply by 0.7)
    background = (desaturated.astype(np.float32) * 0.7).astype(np.uint8)
    
    # =========================================================================
    # Step 2: Composite - sharp subject over blurred background
    # =========================================================================
    
    # Start with the desaturated blurred background
    result = background.copy()
    
    # Paste the sharp, full-color subject region back
    result[y1:y2, x1:x2] = crop[y1:y2, x1:x2]
    
    # =========================================================================
    # Step 3: Add soft glowing border around subject
    # =========================================================================
    
    # Create a subtle glow effect using multiple border passes
    # Outer glow (softer, wider)
    glow_color = (200, 120, 255)  # Lighter purple for glow
    cv2.rectangle(result, (x1 - 2, y1 - 2), (x2 + 2, y2 + 2), glow_color, 1)
    
    # Inner border (solid, crisp)
    cv2.rectangle(result, (x1, y1), (x2, y2), color, border)
    
    return result


# =============================================================================
# Video Frame Extraction
# =============================================================================

def extract_video_frame(video_url: str, frame_number: int, fps: float) -> Optional[bytes]:
    """
    Extract a single frame from a video URL using ffmpeg.
    
    Args:
        video_url: Presigned URL to video file
        frame_number: Frame number to extract (0-indexed)
        fps: Video frames per second
    
    Returns:
        JPEG bytes of the extracted frame, or None on failure
    """
    try:
        timestamp = frame_number / fps
        
        with tempfile.TemporaryDirectory() as tmpdir:
            output_path = Path(tmpdir) / "frame.jpg"
            
            result = subprocess.run(
                [
                    "ffmpeg",
                    "-ss", str(timestamp),
                    "-i", video_url,
                    "-vframes", "1",
                    "-q:v", "2",
                    "-y",
                    str(output_path)
                ],
                capture_output=True,
                timeout=30,
            )
            
            if result.returncode != 0:
                print(f"[Thumbnail] ffmpeg error: {result.stderr.decode()[:200]}")
                return None
            
            if output_path.exists():
                return output_path.read_bytes()
        
        return None
        
    except Exception as e:
        print(f"[Thumbnail] Frame extraction error: {e}")
        return None


# =============================================================================
# Entry Points
# =============================================================================

def generate_hybrid_thumbnail(
    image_bytes: bytes,
    prediction: dict,
    mask: dict,
    output_size: int = THUMBNAIL_SIZE,
) -> Optional[bytes]:
    """
    Generate a stylized thumbnail from a SAM3 mask (Phase 1: Hybrid).
    
    Args:
        image_bytes: Raw image bytes (JPEG/PNG)
        prediction: Prediction dict with 'box' key (normalized xyxy)
        mask: Mask dict with 'polygon' key (normalized points)
        output_size: Output thumbnail size (square)
    
    Returns:
        JPEG bytes of the styled thumbnail, or None on failure
    """
    import cv2
    import numpy as np
    
    try:
        # Decode image
        img_array = np.frombuffer(image_bytes, np.uint8)
        img = cv2.imdecode(img_array, cv2.IMREAD_COLOR)
        
        if img is None:
            print("[Thumbnail] Failed to decode image")
            return None
        
        # Get bounding box
        box = prediction.get("box", [])
        if len(box) < 4:
            print("[Thumbnail] Invalid bounding box")
            return None
        
        # Crop with padding
        crop, crop_x1, crop_y1, img_width, img_height = _crop_with_padding(img, box)
        
        if crop.shape[0] == 0 or crop.shape[1] == 0:
            print("[Thumbnail] Empty crop region")
            return None
        
        # Convert mask polygon to crop-relative coordinates
        polygon_norm = mask.get("polygon", [])
        if not polygon_norm:
            print("[Thumbnail] No polygon in mask")
            return None
        
        polygon_points = []
        for point in polygon_norm:
            if len(point) >= 2:
                px = int(point[0] * img_width) - crop_x1
                py = int(point[1] * img_height) - crop_y1
                polygon_points.append([px, py])
        
        if len(polygon_points) < 3:
            print("[Thumbnail] Insufficient polygon points")
            return None
        
        # Apply mask overlay
        crop = _apply_mask_overlay(crop, polygon_points)
        
        # Square resize
        thumb = _square_resize(crop, output_size)
        
        # Encode
        thumb_bytes = _encode_jpeg(thumb)
        if thumb_bytes:
            print(f"[Thumbnail] Generated {output_size}x{output_size} hybrid thumbnail ({len(thumb_bytes)} bytes)")
        
        return thumb_bytes
        
    except Exception as e:
        print(f"[Thumbnail] Error generating hybrid thumbnail: {e}")
        import traceback
        traceback.print_exc()
        return None


def generate_detection_thumbnail(
    image_bytes: bytes,
    prediction: dict,
    output_size: int = THUMBNAIL_SIZE,
) -> Optional[bytes]:
    """
    Generate a stylized thumbnail from a bounding box (Phase 2: Detection-only).
    
    Uses the same visual style as hybrid thumbnails (purple overlay + border).
    
    Args:
        image_bytes: Raw image bytes (JPEG/PNG)
        prediction: Prediction dict with 'box' key (normalized xyxy)
        output_size: Output thumbnail size (square)
    
    Returns:
        JPEG bytes of the styled thumbnail, or None on failure
    """
    import cv2
    import numpy as np
    
    try:
        # Decode image
        img_array = np.frombuffer(image_bytes, np.uint8)
        img = cv2.imdecode(img_array, cv2.IMREAD_COLOR)
        
        if img is None:
            print("[Thumbnail] Failed to decode image")
            return None
        
        # Get bounding box
        box = prediction.get("box", [])
        if len(box) < 4:
            print("[Thumbnail] Invalid bounding box")
            return None
        
        # Crop with padding
        crop, crop_x1, crop_y1, img_width, img_height = _crop_with_padding(img, box)
        
        if crop.shape[0] == 0 or crop.shape[1] == 0:
            print("[Thumbnail] Empty crop region")
            return None
        
        # Convert box to crop-relative coordinates
        x1_norm, y1_norm, x2_norm, y2_norm = box[:4]
        box_relative = (
            int(x1_norm * img_width) - crop_x1,
            int(y1_norm * img_height) - crop_y1,
            int(x2_norm * img_width) - crop_x1,
            int(y2_norm * img_height) - crop_y1,
        )
        
        # Apply box overlay (same style as mask)
        crop = _apply_box_overlay(crop, box_relative)
        
        # Square resize
        thumb = _square_resize(crop, output_size)
        
        # Encode
        thumb_bytes = _encode_jpeg(thumb)
        if thumb_bytes:
            print(f"[Thumbnail] Generated {output_size}x{output_size} detection thumbnail ({len(thumb_bytes)} bytes)")
        
        return thumb_bytes
        
    except Exception as e:
        print(f"[Thumbnail] Error generating detection thumbnail: {e}")
        import traceback
        traceback.print_exc()
        return None


def generate_label_thumbnail(
    image_bytes: bytes,
    annotation: dict,
    output_size: int = THUMBNAIL_SIZE,
) -> Optional[bytes]:
    """
    Generate a stylized thumbnail from a labeling annotation.
    
    Converts annotation format (x, y, width, height normalized) to box format
    and applies the same purple-tinted styling as inference thumbnails.
    
    Args:
        image_bytes: Raw image bytes (JPEG/PNG)
        annotation: Annotation dict with 'x', 'y', 'width', 'height' keys (normalized 0-1)
        output_size: Output thumbnail size (square)
    
    Returns:
        JPEG bytes of the styled thumbnail, or None on failure
    """
    try:
        # Convert annotation format (x, y, w, h) to box format (x1, y1, x2, y2)
        x = annotation.get("x", 0)
        y = annotation.get("y", 0)
        w = annotation.get("width", 0)
        h = annotation.get("height", 0)
        
        # Create xyxy box format
        box = [x, y, x + w, y + h]
        
        prediction = {"box": box}
        return generate_detection_thumbnail(image_bytes, prediction, output_size)
        
    except Exception as e:
        print(f"[Thumbnail] Error generating label thumbnail: {e}")
        import traceback
        traceback.print_exc()
        return None
