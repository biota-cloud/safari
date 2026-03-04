"""
Shared image processing utilities used by both Modal jobs and remote workers.

This module provides a single source of truth for:
- Image cropping (by bounding box or annotation)
- Image downloading from presigned URLs
"""

import io


def crop_from_box(image_bytes: bytes, box: tuple, padding: float = 0.05) -> bytes:
    """
    Crop a region from an image using box coordinates.
    
    Args:
        image_bytes: Raw image bytes
        box: (x1, y1, x2, y2) absolute pixel coordinates
        padding: Percentage to expand the crop (0.05 = 5%)
    
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


def crop_image_from_annotation(
    image_bytes: bytes,
    x: float,
    y: float,
    width: float,
    height: float,
    padding: float = 0.05,
) -> bytes:
    """
    Crop a region from an image using normalized YOLO annotation coordinates.
    
    Args:
        image_bytes: Raw image bytes
        x, y, width, height: Normalized coordinates (0-1) where x,y is top-left corner
        padding: Percentage to expand the crop
    
    Returns:
        Cropped image as JPEG bytes
    """
    from PIL import Image
    
    img = Image.open(io.BytesIO(image_bytes))
    img_width, img_height = img.size
    
    # Convert normalized to absolute coordinates
    abs_x = x * img_width
    abs_y = y * img_height
    abs_w = width * img_width
    abs_h = height * img_height
    
    # Calculate box dimensions for padding
    pad_x = int(abs_w * padding)
    pad_y = int(abs_h * padding)
    
    # Calculate crop bounds with padding
    x1 = max(0, int(abs_x) - pad_x)
    y1 = max(0, int(abs_y) - pad_y)
    x2 = min(img_width, int(abs_x + abs_w) + pad_x)
    y2 = min(img_height, int(abs_y + abs_h) + pad_y)
    
    # Crop
    cropped = img.crop((x1, y1, x2, y2))
    
    # Convert to RGB if necessary
    if cropped.mode != "RGB":
        cropped = cropped.convert("RGB")
    
    # Save to bytes
    output = io.BytesIO()
    cropped.save(output, format="JPEG", quality=95)
    return output.getvalue()


def download_image(url: str, timeout: int = 60) -> bytes:
    """
    Download an image from a presigned URL and return bytes.
    
    Args:
        url: Presigned URL to download from
        timeout: Request timeout in seconds
    
    Returns:
        Raw image bytes
    
    Raises:
        requests.HTTPError: If download fails
    """
    import requests
    
    response = requests.get(url, timeout=timeout)
    response.raise_for_status()
    return response.content
