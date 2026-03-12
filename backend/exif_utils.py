"""
EXIF Metadata Extraction Utility.

Extracts camera info and capture date from image EXIF data.
Used by both the upload pipeline and the backfill job.
"""

from typing import Optional
from datetime import datetime
import io

from PIL import Image
from PIL.ExifTags import TAGS


def extract_exif_metadata(image_bytes: bytes) -> dict:
    """
    Extract EXIF metadata from image bytes.
    
    Returns dict with keys (all optional, missing values are None):
        - captured_at: datetime or None
        - camera_make: str or None
        - camera_model: str or None  
        - is_night_shot: bool or None
    
    Returns empty dict if no EXIF data found or on error.
    """
    try:
        img = Image.open(io.BytesIO(image_bytes))
        exif_data = img._getexif()
        
        if exif_data is None:
            return {}
        
        result = {}
        
        # DateTimeOriginal (tag 36867) — when the photo was actually taken
        dt_original = exif_data.get(36867)  # DateTimeOriginal
        if not dt_original:
            dt_original = exif_data.get(36868)  # DateTimeDigitized
        if not dt_original:
            dt_original = exif_data.get(306)  # DateTime (last resort)
        
        if dt_original and isinstance(dt_original, str):
            try:
                # EXIF format: "2024:12:07 05:42:17"
                result["captured_at"] = datetime.strptime(dt_original, "%Y:%m:%d %H:%M:%S")
            except ValueError:
                pass
        
        # Camera Make (tag 271)
        make = exif_data.get(271)
        if make and isinstance(make, str):
            result["camera_make"] = make.strip().replace("\x00", "")
        
        # Camera Model (tag 272)
        model = exif_data.get(272)
        if model and isinstance(model, str):
            result["camera_model"] = model.strip().replace("\x00", "")
        
        # Night shot detection via Flash tag (tag 37385)
        # Flash tag: odd values = flash fired (IR flash on trail cameras = night)
        flash = exif_data.get(37385)
        if flash is not None and isinstance(flash, int):
            result["is_night_shot"] = bool(flash & 1)  # Bit 0 = flash fired
        
        return result
        
    except Exception as e:
        print(f"[EXIF] Error extracting metadata: {e}")
        return {}
