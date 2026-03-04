"""
Tests for the inference router module.
"""
import pytest
from unittest.mock import MagicMock, patch

from backend.inference_router import InferenceConfig, dispatch_inference


class TestInferenceConfig:
    """Tests for InferenceConfig dataclass."""
    
    def test_builtin_model_detection(self):
        """Test that built-in models are correctly identified."""
        config = InferenceConfig(
            model_type="yolo-detect",
            input_type="image",
            model_name_or_id="yolo11s.pt",
        )
        assert config.is_builtin_model is True
        
    def test_custom_model_detection(self):
        """Test that custom models (UUIDs) are correctly identified."""
        config = InferenceConfig(
            model_type="yolo-detect",
            input_type="image",
            model_name_or_id="a1b2c3d4-e5f6-7890-abcd-ef1234567890",
        )
        assert config.is_builtin_model is False
    
    def test_compute_target_defaults_to_cloud(self):
        """Test that compute target defaults to cloud when no project_id."""
        config = InferenceConfig(
            model_type="yolo-detect",
            input_type="image",
            model_name_or_id="yolo11s.pt",
        )
        assert config.compute_target == "cloud"
    
    @patch("backend.inference_router.get_job_target")
    def test_compute_target_from_project(self, mock_get_target):
        """Test that compute target is resolved from project."""
        mock_get_target.return_value = "local"
        
        config = InferenceConfig(
            model_type="yolo-detect",
            input_type="image",
            model_name_or_id="yolo11s.pt",
            project_id="test-project-id",
        )
        assert config.compute_target == "local"
        mock_get_target.assert_called_once_with("test-project-id")
    
    def test_hybrid_config_with_classifier(self):
        """Test hybrid config with classifier parameters."""
        config = InferenceConfig(
            model_type="hybrid",
            input_type="batch",
            model_name_or_id="classifier-uuid",
            project_id="test-project",
            classifier_r2_path="projects/test/best.pt",
            classifier_classes=["Lynx", "Deer"],
            sam3_prompts=["animal", "mammal"],
            prompt_class_map={"animal": ["Lynx", "Deer"]},
        )
        assert config.model_type == "hybrid"
        assert len(config.classifier_classes) == 2
        assert len(config.sam3_prompts) == 2


class TestDispatchRoutingLogic:
    """Tests for routing logic in dispatch_inference."""
    
    @patch("backend.inference_router.modal.Cls")
    def test_yolo_image_routes_to_modal_cloud(self, mock_cls):
        """Test YOLO image inference routes to Modal on cloud."""
        # Setup mock
        mock_instance = MagicMock()
        mock_instance.predict_image.remote.return_value = {"predictions": []}
        mock_cls.from_name.return_value.return_value = mock_instance
        
        config = InferenceConfig(
            model_type="yolo-detect",
            input_type="image",
            model_name_or_id="yolo11s.pt",
        )
        
        result = dispatch_inference(config, image_url="http://example.com/img.jpg", confidence=0.25)
        
        mock_cls.from_name.assert_called_once_with("yolo-inference", "YOLOInference")
        mock_instance.predict_image.remote.assert_called_once()
        
    @patch("backend.inference_router.modal.Cls")
    def test_yolo_batch_routes_to_modal_cloud(self, mock_cls):
        """Test YOLO batch inference routes to Modal on cloud."""
        mock_instance = MagicMock()
        mock_instance.predict_images_batch.remote.return_value = [{"predictions": []}]
        mock_cls.from_name.return_value.return_value = mock_instance
        
        config = InferenceConfig(
            model_type="yolo-detect",
            input_type="batch",
            model_name_or_id="yolo11s.pt",
        )
        
        result = dispatch_inference(config, image_urls=["http://example.com/1.jpg"], confidence=0.25)
        
        mock_instance.predict_images_batch.remote.assert_called_once()
    
    @patch("backend.job_router.dispatch_hybrid_inference")
    def test_hybrid_image_delegates_to_job_router(self, mock_dispatch):
        """Test hybrid image routes through job_router."""
        mock_dispatch.return_value = {"predictions": []}
        
        config = InferenceConfig(
            model_type="hybrid",
            input_type="image",
            model_name_or_id="classifier-uuid",
            classifier_r2_path="path/to/model.pt",
            classifier_classes=["Lynx"],
            sam3_prompts=["animal"],
            prompt_class_map={},
        )
        
        result = dispatch_inference(config, image_url="http://example.com/img.jpg", confidence=0.25)
        
        mock_dispatch.assert_called_once()
    
    def test_unsupported_config_raises_error(self):
        """Test that unsupported model types raise ValueError."""
        config = InferenceConfig(
            model_type="yolo-detect",
            input_type="image",
            model_name_or_id="yolo11s.pt",
        )
        # Manually set an invalid model_type
        object.__setattr__(config, 'model_type', 'invalid-type')
        
        with pytest.raises(ValueError, match="Unsupported config"):
            dispatch_inference(config, image_url="test")


class TestUUIDValidation:
    """Tests for UUID validation helper."""
    
    def test_valid_uuid_lowercase(self):
        """Test valid lowercase UUID."""
        assert InferenceConfig._is_uuid("a1b2c3d4-e5f6-7890-abcd-ef1234567890") is True
    
    def test_valid_uuid_uppercase(self):
        """Test valid uppercase UUID."""
        assert InferenceConfig._is_uuid("A1B2C3D4-E5F6-7890-ABCD-EF1234567890") is True
    
    def test_invalid_uuid_short(self):
        """Test invalid short string."""
        assert InferenceConfig._is_uuid("not-a-uuid") is False
    
    def test_invalid_uuid_model_name(self):
        """Test model names are not UUIDs."""
        assert InferenceConfig._is_uuid("yolo11s.pt") is False
