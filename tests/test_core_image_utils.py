"""
Unit tests for backend/core/image_utils.py

Tests pure image processing functions used by both Modal jobs and remote workers.
"""

import io
from pathlib import Path
import pytest
from PIL import Image

# Import the module under test
from backend.core.image_utils import (
    crop_from_box,
    crop_image_from_annotation,
    download_image,
)


def create_test_image(width: int = 200, height: int = 200, color: str = "red") -> bytes:
    """Create a test image and return as bytes."""
    img = Image.new("RGB", (width, height), color=color)
    output = io.BytesIO()
    img.save(output, format="JPEG", quality=95)
    return output.getvalue()


class TestCropFromBox:
    """Tests for crop_from_box() function."""
    
    def test_basic_crop(self):
        """Test basic cropping with pixel coordinates."""
        image_bytes = create_test_image(200, 200)
        
        # Crop a 50x50 region from the center
        result = crop_from_box(image_bytes, (75, 75, 125, 125), padding=0.0)
        
        # Verify we get a JPEG back
        result_img = Image.open(io.BytesIO(result))
        assert result_img.format == "JPEG"
        assert result_img.size == (50, 50)
    
    def test_crop_with_padding(self):
        """Test cropping with 10% padding."""
        image_bytes = create_test_image(200, 200)
        
        # Crop with padding - box is 50x50, so 10% padding = 5px each side
        # Result should be 60x60
        result = crop_from_box(image_bytes, (75, 75, 125, 125), padding=0.1)
        
        result_img = Image.open(io.BytesIO(result))
        assert result_img.size == (60, 60)
    
    def test_crop_clamped_to_bounds(self):
        """Test that crop is clamped to image boundaries."""
        image_bytes = create_test_image(100, 100)
        
        # Try to crop with padding that would exceed bounds
        result = crop_from_box(image_bytes, (0, 0, 20, 20), padding=0.5)
        
        result_img = Image.open(io.BytesIO(result))
        # Should be clamped to start at 0, so effectively larger than expected
        assert result_img.width <= 100
        assert result_img.height <= 100
    
    def test_rgba_converted_to_rgb(self):
        """Test that RGBA images are converted to RGB."""
        # Create RGBA image
        img = Image.new("RGBA", (100, 100), color=(255, 0, 0, 128))
        output = io.BytesIO()
        img.save(output, format="PNG")
        image_bytes = output.getvalue()
        
        result = crop_from_box(image_bytes, (10, 10, 50, 50), padding=0.0)
        
        result_img = Image.open(io.BytesIO(result))
        assert result_img.mode == "RGB"


class TestCropImageFromAnnotation:
    """Tests for crop_image_from_annotation() function."""
    
    def test_normalized_coords_crop(self):
        """Test cropping with normalized 0-1 coordinates."""
        image_bytes = create_test_image(200, 200)
        
        # Crop from (0.25, 0.25) with size (0.5, 0.5) - i.e., center 50% of image
        # Without padding, should be 100x100
        result = crop_image_from_annotation(
            image_bytes,
            x=0.25,
            y=0.25,
            width=0.5,
            height=0.5,
            padding=0.0,
        )
        
        result_img = Image.open(io.BytesIO(result))
        assert result_img.size == (100, 100)
    
    def test_full_image_crop(self):
        """Test cropping the entire image."""
        image_bytes = create_test_image(100, 100)
        
        result = crop_image_from_annotation(
            image_bytes,
            x=0.0,
            y=0.0,
            width=1.0,
            height=1.0,
            padding=0.0,
        )
        
        result_img = Image.open(io.BytesIO(result))
        assert result_img.size == (100, 100)
    
    def test_crop_with_padding(self):
        """Test normalized crop with padding."""
        image_bytes = create_test_image(200, 200)
        
        # Small annotation in center
        result = crop_image_from_annotation(
            image_bytes,
            x=0.4,
            y=0.4,
            width=0.2,
            height=0.2,
            padding=0.1,  # 10% padding
        )
        
        result_img = Image.open(io.BytesIO(result))
        # 0.2 * 200 = 40px box, plus ~4px padding each side
        assert result_img.width > 40
        assert result_img.height > 40


class TestDownloadImage:
    """Tests for download_image() function."""
    
    def test_invalid_url_raises(self):
        """Test that invalid URLs raise an error."""
        with pytest.raises(Exception):  # requests.exceptions.ConnectionError or similar
            download_image("http://invalid-url-that-does-not-exist.local/image.jpg", timeout=1)
