"""
Unit tests for model_registry module.

These tests verify registry lookups and backbone detection without
requiring GPU or heavy ML dependencies.
"""

import pytest
from pathlib import Path

# Import the registry module (lightweight, no GPU deps needed for these tests)
from backend.model_registry import (
    ModelType,
    ModelInfo,
    get_model_info,
    detect_classifier_backbone,
    get_all_model_types,
)


class TestGetModelInfo:
    """Tests for get_model_info() function."""
    
    def test_yolo_detect(self):
        """YOLO detection model returns correct info."""
        info = get_model_info("yolo-detect")
        assert info.model_type == ModelType.YOLO_DETECT
        assert info.extension == ".pt"
        assert info.package == "ultralytics"
        assert "YOLO" in info.loader_name
    
    def test_yolo_classify(self):
        """YOLO classification model returns correct info."""
        info = get_model_info("yolo-classify")
        assert info.model_type == ModelType.YOLO_CLASSIFY
        assert info.extension == ".pt"
        assert info.package == "ultralytics"
    
    def test_convnext_classify(self):
        """ConvNeXt classification model returns correct info."""
        info = get_model_info("convnext-classify")
        assert info.model_type == ModelType.CONVNEXT_CLASSIFY
        assert info.extension == ".pth"
        assert "timm" in info.package
    
    def test_sam3_image(self):
        """SAM3 image predictor returns correct info."""
        info = get_model_info("sam3-image")
        assert info.model_type == ModelType.SAM3_IMAGE
        assert info.extension == ".pt"
        assert "8.3.237" in info.package  # Version requirement
    
    def test_sam3_video(self):
        """SAM3 video predictor returns correct info."""
        info = get_model_info("sam3-video")
        assert info.model_type == ModelType.SAM3_VIDEO
        assert info.extension == ".pt"
    
    def test_invalid_type_raises_keyerror(self):
        """Unknown model type raises KeyError with helpful message."""
        with pytest.raises(KeyError) as exc_info:
            get_model_info("invalid-model")
        
        # Error message should list valid types
        assert "invalid-model" in str(exc_info.value)
        assert "yolo-detect" in str(exc_info.value)


class TestDetectClassifierBackbone:
    """Tests for detect_classifier_backbone() function."""
    
    def test_pt_extension(self):
        """Files with .pt extension detected as YOLO classifier."""
        assert detect_classifier_backbone("model.pt") == "yolo-classify"
        assert detect_classifier_backbone("/path/to/best.pt") == "yolo-classify"
        assert detect_classifier_backbone(Path("weights/classifier.pt")) == "yolo-classify"
    
    def test_pth_extension(self):
        """Files with .pth extension detected as ConvNeXt classifier."""
        assert detect_classifier_backbone("model.pth") == "convnext-classify"
        assert detect_classifier_backbone("/path/to/best.pth") == "convnext-classify"
        assert detect_classifier_backbone(Path("weights/convnext.pth")) == "convnext-classify"
    
    def test_case_insensitive(self):
        """Extension detection is case-insensitive."""
        assert detect_classifier_backbone("model.PT") == "yolo-classify"
        assert detect_classifier_backbone("model.PTH") == "convnext-classify"
    
    def test_unknown_extension_raises_valueerror(self):
        """Unknown extension raises ValueError."""
        with pytest.raises(ValueError) as exc_info:
            detect_classifier_backbone("model.onnx")
        
        assert ".onnx" in str(exc_info.value)
        assert ".pt" in str(exc_info.value)  # Suggests valid extensions


class TestGetAllModelTypes:
    """Tests for get_all_model_types() function."""
    
    def test_returns_all_five_types(self):
        """All 5 model types are registered."""
        types = get_all_model_types()
        assert len(types) == 5
        assert "yolo-detect" in types
        assert "yolo-classify" in types
        assert "convnext-classify" in types
        assert "sam3-image" in types
        assert "sam3-video" in types


class TestModelInfoDataclass:
    """Tests for ModelInfo dataclass properties."""
    
    def test_frozen(self):
        """ModelInfo instances are immutable."""
        info = get_model_info("yolo-detect")
        with pytest.raises(Exception):  # FrozenInstanceError
            info.extension = ".pth"
