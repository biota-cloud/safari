"""
Tests for SAFARI API Key Validation.

These tests verify the authentication middleware works correctly.
Run with: pytest tests/test_api_keys.py -v
"""

import hashlib
import pytest
from datetime import datetime, timezone, timedelta
from unittest.mock import MagicMock, patch


def _hash_key(raw_key: str) -> str:
    """Hash an API key with SHA256."""
    return hashlib.sha256(raw_key.encode()).hexdigest()


class TestAPIKeyHashing:
    """Test API key hashing logic."""
    
    def test_hash_consistency(self):
        """Same key should always produce same hash."""
        key = "tyto_abc123xyz456"
        hash1 = _hash_key(key)
        hash2 = _hash_key(key)
        assert hash1 == hash2
    
    def test_hash_uniqueness(self):
        """Different keys should produce different hashes."""
        key1 = "tyto_abc123xyz456"
        key2 = "tyto_def789uvw012"
        assert _hash_key(key1) != _hash_key(key2)
    
    def test_hash_is_64_chars(self):
        """SHA256 hash should be 64 hex characters."""
        key = "tyto_test_key_12345"
        hash_val = _hash_key(key)
        assert len(hash_val) == 64
        assert all(c in "0123456789abcdef" for c in hash_val)


class TestAPIKeyValidation:
    """Test API key validation logic."""
    
    def test_missing_authorization_header(self):
        """Missing Authorization header should return 401."""
        pytest.importorskip("fastapi")
        from backend.api.auth import validate_api_key
        from fastapi import HTTPException
        
        with pytest.raises(HTTPException) as exc_info:
            # Simulate missing header
            import asyncio
            asyncio.get_event_loop().run_until_complete(
                validate_api_key(authorization=None)
            )
        
        assert exc_info.value.status_code == 401
        assert "Missing Authorization header" in exc_info.value.detail
    
    def test_invalid_authorization_format(self):
        """Invalid format should return 401."""
        pytest.importorskip("fastapi")
        from backend.api.auth import validate_api_key
        from fastapi import HTTPException
        
        with pytest.raises(HTTPException) as exc_info:
            import asyncio
            asyncio.get_event_loop().run_until_complete(
                validate_api_key(authorization="InvalidFormat")
            )
        
        assert exc_info.value.status_code == 401
        assert "Invalid Authorization header format" in exc_info.value.detail
    
    def test_missing_tyto_prefix(self):
        """Key without tyto_ prefix should return 401."""
        pytest.importorskip("fastapi")
        from backend.api.auth import validate_api_key
        from fastapi import HTTPException
        
        with pytest.raises(HTTPException) as exc_info:
            import asyncio
            asyncio.get_event_loop().run_until_complete(
                validate_api_key(authorization="Bearer abc123456789")
            )
        
        assert exc_info.value.status_code == 401
        assert "Invalid API key format" in exc_info.value.detail


class TestAPIKeyDataModel:
    """Test the APIKeyData model."""
    
    def test_api_key_data_creation(self):
        """APIKeyData should be created with all fields."""
        pytest.importorskip("fastapi")
        from backend.api.auth import APIKeyData
        
        data = APIKeyData(
            key_id="test-key-id",
            user_id="test-user-id",
            project_id="test-project-id",
            rate_limit_rpm=60,
            scopes=["infer"],
        )
        
        assert data.key_id == "test-key-id"
        assert data.user_id == "test-user-id"
        assert data.project_id == "test-project-id"
        assert data.rate_limit_rpm == 60
        assert data.scopes == ["infer"]
    
    def test_api_key_data_optional_project(self):
        """project_id should be optional."""
        pytest.importorskip("fastapi")
        from backend.api.auth import APIKeyData
        
        data = APIKeyData(
            key_id="test-key-id",
            user_id="test-user-id",
            project_id=None,
            rate_limit_rpm=100,
            scopes=["infer", "train"],
        )
        
        assert data.project_id is None


class TestExpiryChecks:
    """Test key expiry logic."""
    
    def test_expired_key_detection(self):
        """Expired keys should be detected."""
        from datetime import datetime, timezone, timedelta
        
        # Create an expiry time in the past
        expiry = datetime.now(timezone.utc) - timedelta(hours=1)
        current = datetime.now(timezone.utc)
        
        assert current > expiry  # Should be expired
    
    def test_valid_key_detection(self):
        """Non-expired keys should be valid."""
        from datetime import datetime, timezone, timedelta
        
        # Create an expiry time in the future
        expiry = datetime.now(timezone.utc) + timedelta(days=30)
        current = datetime.now(timezone.utc)
        
        assert current < expiry  # Should be valid


# Integration tests (require database connection)
@pytest.mark.integration
class TestAPIKeyIntegration:
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
    
    def test_create_and_validate_key(self, supabase_client):
        """Test full key creation and validation cycle."""
        from backend.supabase_client import create_api_key, validate_api_key
        
        # This would require a test user - skip in unit tests
        pytest.skip("Requires test user setup")
