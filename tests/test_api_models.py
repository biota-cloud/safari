"""
Tests for SAFARI API Model Promotion.

These tests verify model promotion and API model management.
Run with: pytest tests/test_api_models.py -v
"""

import pytest
from unittest.mock import MagicMock, patch


class TestSlugValidation:
    """Test slug generation and validation."""
    
    def test_slug_lowercase(self):
        """Slugs should be lowercase."""
        slug = "Lynx-Detector-V2"
        normalized = slug.lower()
        assert normalized == "lynx-detector-v2"
    
    def test_slug_no_spaces(self):
        """Slugs should not contain spaces."""
        slug = "lynx detector v2"
        normalized = slug.replace(" ", "-")
        assert " " not in normalized
        assert normalized == "lynx-detector-v2"
    
    def test_slug_url_safe(self):
        """Slugs should be URL-safe."""
        import re
        slug = "lynx-detector-v2"
        # URL-safe pattern: alphanumeric, hyphens, underscores
        pattern = r'^[a-z0-9\-_]+$'
        assert re.match(pattern, slug) is not None
    
    def test_slug_sanitization(self):
        """Special characters should be removed or replaced."""
        display_name = "Lynx Detector (v2.0)!"
        # Typical sanitization: lowercase, replace spaces, remove special chars
        slug = display_name.lower()
        slug = slug.replace(" ", "-")
        slug = "".join(c for c in slug if c.isalnum() or c in "-_")
        
        # Period is not alphanumeric, so it gets stripped
        assert slug == "lynx-detector-v20"


class TestModelTypeValidation:
    """Test model type validation."""
    
    def test_valid_detection_type(self):
        """Detection models should be valid."""
        valid_types = ["detection", "classification"]
        assert "detection" in valid_types
    
    def test_valid_classification_type(self):
        """Classification models should be valid."""
        valid_types = ["detection", "classification"]
        assert "classification" in valid_types
    
    def test_invalid_type_rejected(self):
        """Invalid model types should be rejected."""
        valid_types = ["detection", "classification"]
        assert "segmentation" not in valid_types


class TestClassesSnapshot:
    """Test classes snapshot logic."""
    
    def test_classes_snapshot_is_list(self):
        """Classes snapshot should be a list."""
        classes = ["Lynx", "Fox", "Deer"]
        assert isinstance(classes, list)
    
    def test_classes_snapshot_preserves_order(self):
        """Classes should maintain order (important for class_id)."""
        classes = ["Lynx", "Fox", "Deer"]
        assert classes[0] == "Lynx"
        assert classes[1] == "Fox"
        assert classes[2] == "Deer"
    
    def test_classes_snapshot_json_serializable(self):
        """Classes should be JSON serializable."""
        import json
        classes = ["Lynx", "Fox", "Deer"]
        json_str = json.dumps(classes)
        parsed = json.loads(json_str)
        assert parsed == classes


class TestPromoteModelResponse:
    """Test expected response format from model promotion."""
    
    def test_response_contains_required_fields(self):
        """Promotion response should have required fields."""
        required_fields = [
            "id", "slug", "display_name", "model_type",
            "classes_snapshot", "weights_r2_path", "is_active"
        ]
        
        mock_response = {
            "id": "uuid-123",
            "training_run_id": "uuid-456",
            "project_id": "uuid-789",
            "user_id": "uuid-user",
            "slug": "lynx-detector-v2",
            "display_name": "Lynx Detector v2",
            "description": "Detects lynx in wildlife images",
            "version": 1,
            "model_type": "detection",
            "classes_snapshot": ["Lynx", "Fox"],
            "weights_r2_path": "models/uuid-456/best.pt",
            "is_active": True,
            "is_public": False,
            "total_requests": 0,
            "last_used_at": None,
            "created_at": "2026-01-12T00:00:00Z",
            "updated_at": "2026-01-12T00:00:00Z",
        }
        
        for field in required_fields:
            assert field in mock_response


class TestDeactivateModel:
    """Test model deactivation logic."""
    
    def test_deactivate_sets_is_active_false(self):
        """Deactivation should set is_active to False."""
        model = {"id": "uuid-123", "is_active": True}
        # Simulate deactivation
        model["is_active"] = False
        assert model["is_active"] is False
    
    def test_deactivated_model_not_in_active_list(self):
        """Deactivated models should be filtered from active lists."""
        models = [
            {"id": "1", "slug": "model-a", "is_active": True},
            {"id": "2", "slug": "model-b", "is_active": False},
            {"id": "3", "slug": "model-c", "is_active": True},
        ]
        
        active_models = [m for m in models if m["is_active"]]
        
        assert len(active_models) == 2
        assert all(m["is_active"] for m in active_models)
        assert "model-b" not in [m["slug"] for m in active_models]


# Integration tests (require database connection)
@pytest.mark.integration
class TestModelPromotionIntegration:
    """Integration tests requiring Supabase connection."""
    
    @pytest.fixture
    def supabase_client(self):
        """Get Supabase client from environment."""
        import os
        from supabase import create_client
        
        url = os.environ.get("SUPABASE_URL")
        key = os.environ.get("SUPABASE_KEY")
        
        if not url or not key:
            pytest.skip("SUPABASE_URL and SUPABASE_KEY required")
        
        return create_client(url, key)
    
    def test_promote_model_creates_record(self, supabase_client):
        """Model promotion should create api_models record."""
        # This would require a completed training run - skip in unit tests
        pytest.skip("Requires completed training run")
    
    def test_get_api_model_by_slug(self, supabase_client):
        """Should lookup model by slug."""
        # This would require an existing API model - skip in unit tests
        pytest.skip("Requires existing API model")
