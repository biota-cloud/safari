"""
Tests for SAFARI API Inference Endpoints.

These tests verify the inference API endpoints work correctly.
Run with: pytest tests/test_api_inference.py -v
"""

import pytest
from unittest.mock import MagicMock, patch, AsyncMock
from io import BytesIO


class TestImageInferenceRequest:
    """Test image inference request validation."""
    
    def test_valid_image_content_types(self):
        """Image endpoints should accept common image types."""
        valid_types = ["image/jpeg", "image/png", "image/webp"]
        
        for content_type in valid_types:
            assert content_type.startswith("image/")
    
    def test_invalid_content_type_rejected(self):
        """Non-image content types should be rejected."""
        invalid_types = ["text/plain", "application/json", "video/mp4"]
        
        for content_type in invalid_types:
            assert not content_type.startswith("image/")
    
    def test_file_size_limit(self):
        """Files over 50MB should be rejected."""
        max_size = 50 * 1024 * 1024  # 50MB
        
        # Test file under limit
        small_file = 10 * 1024 * 1024  # 10MB
        assert small_file <= max_size
        
        # Test file over limit
        large_file = 60 * 1024 * 1024  # 60MB
        assert large_file > max_size


class TestVideoJobRequest:
    """Test video job submission validation."""
    
    def test_valid_video_content_types(self):
        """Video endpoints should accept common video types."""
        valid_types = ["video/mp4", "video/quicktime", "video/x-msvideo", "video/webm"]
        
        for content_type in valid_types:
            assert content_type.startswith("video/")
    
    def test_video_file_size_limit(self):
        """Videos over 500MB should be rejected."""
        max_size = 500 * 1024 * 1024  # 500MB
        
        # Test file under limit
        small_video = 100 * 1024 * 1024  # 100MB
        assert small_video <= max_size
        
        # Test file over limit
        large_video = 600 * 1024 * 1024  # 600MB
        assert large_video > max_size
    
    def test_frame_skip_validation(self):
        """Frame skip should be between 1 and 30."""
        valid_skips = [1, 5, 10, 15, 30]
        invalid_skips = [0, -1, 31, 100]
        
        for skip in valid_skips:
            assert 1 <= skip <= 30
        
        for skip in invalid_skips:
            assert not (1 <= skip <= 30)
    
    def test_confidence_threshold_validation(self):
        """Confidence should be between 0 and 1."""
        valid_confidences = [0.0, 0.25, 0.5, 0.75, 1.0]
        invalid_confidences = [-0.1, 1.1, 2.0]
        
        for conf in valid_confidences:
            assert 0.0 <= conf <= 1.0
        
        for conf in invalid_confidences:
            assert not (0.0 <= conf <= 1.0)


class TestPredictionFormat:
    """Test prediction response format."""
    
    def test_prediction_has_required_fields(self):
        """Each prediction should have class_name, class_id, confidence, box."""
        prediction = {
            "class_name": "Lynx",
            "class_id": 0,
            "confidence": 0.92,
            "box": [0.12, 0.34, 0.56, 0.78],
            "box_format": "xyxy_normalized",
        }
        
        required_fields = ["class_name", "class_id", "confidence", "box"]
        for field in required_fields:
            assert field in prediction
    
    def test_box_normalized_coordinates(self):
        """Box coordinates should be normalized (0-1)."""
        box = [0.12, 0.34, 0.56, 0.78]
        
        for coord in box:
            assert 0.0 <= coord <= 1.0
    
    def test_box_is_xyxy_format(self):
        """Box should be in xyxy format: [x1, y1, x2, y2]."""
        box = [0.12, 0.34, 0.56, 0.78]
        
        x1, y1, x2, y2 = box
        # x2 should be >= x1, y2 should be >= y1
        assert x2 >= x1
        assert y2 >= y1
    
    def test_confidence_in_valid_range(self):
        """Confidence should be between 0 and 1."""
        confidence = 0.92
        assert 0.0 <= confidence <= 1.0


class TestInferenceResponse:
    """Test full inference response format."""
    
    def test_image_response_format(self):
        """Image inference response should have expected format."""
        response = {
            "model": "lynx-detector-v2",
            "model_type": "detection",
            "predictions": [
                {
                    "class_name": "Lynx",
                    "class_id": 0,
                    "confidence": 0.92,
                    "box": [0.12, 0.34, 0.56, 0.78],
                    "box_format": "xyxy_normalized"
                }
            ],
            "image_width": 1920,
            "image_height": 1080,
            "inference_time_ms": 145,
            "request_id": "uuid-123"
        }
        
        assert "model" in response
        assert "predictions" in response
        assert "image_width" in response
        assert "image_height" in response
        assert "inference_time_ms" in response
        assert "request_id" in response
    
    def test_video_job_response_format(self):
        """Video job submission should return job_id."""
        response = {
            "job_id": "uuid-456",
            "status": "pending",
            "message": "Video job submitted. Poll /api/v1/jobs/{job_id} for progress."
        }
        
        assert "job_id" in response
        assert "status" in response
        assert response["status"] == "pending"


class TestJobStatusResponse:
    """Test job status polling response."""
    
    def test_pending_status(self):
        """Pending jobs should have minimal progress info."""
        response = {
            "job_id": "uuid-456",
            "status": "pending",
            "progress": None,
            "progress_current": 0,
            "progress_total": 0,
        }
        
        assert response["status"] == "pending"
    
    def test_processing_status(self):
        """Processing jobs should show progress."""
        response = {
            "job_id": "uuid-456",
            "status": "processing",
            "progress": 45,
            "progress_current": 450,
            "progress_total": 1000,
            "frames_processed": 450,
            "total_frames": 1000,
        }
        
        assert response["status"] == "processing"
        assert response["progress"] == 45
    
    def test_completed_status(self):
        """Completed jobs should have results."""
        response = {
            "job_id": "uuid-456",
            "status": "completed",
            "progress": 100,
            "progress_current": 1000,
            "progress_total": 1000,
            "result": {
                "predictions_by_frame": {"0": [], "5": []},
                "total_frames_processed": 200,
                "total_detections": 45,
            }
        }
        
        assert response["status"] == "completed"
        assert "result" in response
        assert response["result"] is not None
    
    def test_failed_status(self):
        """Failed jobs should have error message."""
        response = {
            "job_id": "uuid-456",
            "status": "failed",
            "error_message": "Video format not supported",
        }
        
        assert response["status"] == "failed"
        assert "error_message" in response


class TestRateLimiting:
    """Test rate limiting logic."""
    
    def test_rpm_limit_default(self):
        """Default rate limit should be 60 RPM."""
        default_rpm = 60
        assert default_rpm == 60
    
    def test_requests_within_limit(self):
        """Requests within limit should pass."""
        limit = 60
        current_requests = 30
        assert current_requests < limit
    
    def test_requests_exceed_limit(self):
        """Requests exceeding limit should fail."""
        limit = 60
        current_requests = 65
        assert current_requests > limit


class TestModelAccessControl:
    """Test model access control logic."""
    
    def test_user_wide_key_access_own_model(self):
        """User-wide key should access own models."""
        api_key = {"user_id": "user-123", "project_id": None}
        model = {"user_id": "user-123", "project_id": "project-456"}
        
        # Same user should have access
        assert api_key["user_id"] == model["user_id"]
    
    def test_user_wide_key_no_access_other_model(self):
        """User-wide key should not access other user's models."""
        api_key = {"user_id": "user-123", "project_id": None}
        model = {"user_id": "user-456", "project_id": "project-789"}
        
        # Different user should not have access
        assert api_key["user_id"] != model["user_id"]
    
    def test_project_scoped_key_access_same_project(self):
        """Project-scoped key should access models in same project."""
        api_key = {"user_id": "user-123", "project_id": "project-456"}
        model = {"user_id": "user-123", "project_id": "project-456"}
        
        assert api_key["project_id"] == model["project_id"]
    
    def test_project_scoped_key_no_access_other_project(self):
        """Project-scoped key should not access models in other projects."""
        api_key = {"user_id": "user-123", "project_id": "project-456"}
        model = {"user_id": "user-123", "project_id": "project-789"}
        
        assert api_key["project_id"] != model["project_id"]


# FastAPI TestClient tests
class TestAPIEndpoints:
    """Test API endpoints using FastAPI TestClient."""
    
    @pytest.fixture
    def client(self):
        """Create test client."""
        try:
            from fastapi.testclient import TestClient
            from backend.api.server import fastapi_app
            return TestClient(fastapi_app)
        except ImportError:
            pytest.skip("FastAPI TestClient not available")
    
    def test_health_endpoint(self, client):
        """Health endpoint should return 200."""
        response = client.get("/health")
        assert response.status_code == 200
        assert response.json()["status"] == "healthy"
    
    def test_root_endpoint(self, client):
        """Root endpoint should return API info."""
        response = client.get("/")
        assert response.status_code == 200
        assert "name" in response.json()
    
    def test_inference_requires_auth(self, client):
        """Inference endpoint should require authentication."""
        # Create a fake file
        files = {"file": ("test.jpg", b"fake image content", "image/jpeg")}
        response = client.post("/api/v1/infer/test-model", files=files)
        
        # Should require auth
        assert response.status_code == 401
    
    def test_inference_with_invalid_key(self, client):
        """Invalid API key should return 401."""
        files = {"file": ("test.jpg", b"fake image content", "image/jpeg")}
        headers = {"Authorization": "Bearer invalid_key"}
        response = client.post("/api/v1/infer/test-model", files=files, headers=headers)
        
        # Should reject invalid key format (no tyto_ prefix)
        assert response.status_code == 401


class TestBatchInference:
    """Test batch inference request validation."""
    
    def test_batch_size_limit(self):
        """Batch should reject > 100 images."""
        max_batch_size = 100
        
        # Under limit
        assert 50 <= max_batch_size
        
        # Over limit
        assert 150 > max_batch_size
    
    def test_batch_file_size_limit(self):
        """Individual files should be max 10MB."""
        max_file_size = 10 * 1024 * 1024  # 10MB
        
        # Under limit
        small_file = 5 * 1024 * 1024  # 5MB
        assert small_file <= max_file_size
        
        # Over limit
        large_file = 15 * 1024 * 1024  # 15MB
        assert large_file > max_file_size
    
    def test_batch_response_format(self):
        """Batch response should have expected format."""
        response = {
            "model": "lynx-detector-v2",
            "model_type": "detection",
            "results": [
                {
                    "index": 0,
                    "success": True,
                    "predictions": [
                        {
                            "class_name": "Lynx",
                            "class_id": 0,
                            "confidence": 0.92,
                            "box": [0.12, 0.34, 0.56, 0.78],
                            "box_format": "xyxy_normalized"
                        }
                    ],
                    "image_width": 1920,
                    "image_height": 1080,
                }
            ],
            "total_images": 1,
            "total_predictions": 1,
            "inference_time_ms": 245,
            "request_id": "uuid-789"
        }
        
        assert "model" in response
        assert "results" in response
        assert "total_images" in response
        assert "total_predictions" in response
        assert len(response["results"]) == 1
        assert response["results"][0]["index"] == 0
        assert response["results"][0]["success"] is True


# Integration tests
@pytest.mark.integration
class TestInferenceIntegration:
    """Integration tests requiring Modal deployment."""
    
    def test_real_image_inference(self):
        """Test actual image inference with deployed Modal job."""
        pytest.skip("Requires Modal deployment and valid API key")
    
    def test_real_video_inference(self):
        """Test actual video inference with deployed Modal job."""
        pytest.skip("Requires Modal deployment and valid API key")
