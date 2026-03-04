"""
API Authentication — Middleware and dependencies for API key validation.

Security model:
- API keys are prefixed with "safari_" for easy identification
- Keys are hashed with SHA256 before storage (raw key never stored)
- Validation looks up by hash and checks is_active + expiry
"""

import os
import hashlib
from datetime import datetime, timezone
from typing import Optional

from fastapi import HTTPException, Security, status
from fastapi.security import APIKeyHeader
from pydantic import BaseModel


class APIKeyData(BaseModel):
    """Validated API key data attached to request context."""
    key_id: str
    user_id: str
    project_id: Optional[str]
    rate_limit_rpm: int
    scopes: list[str]


# FastAPI security scheme for Bearer token
api_key_header = APIKeyHeader(name="Authorization", auto_error=False)


def _hash_key(raw_key: str) -> str:
    """Hash an API key with SHA256 for database lookup."""
    return hashlib.sha256(raw_key.encode()).hexdigest()


async def validate_api_key(
    authorization: Optional[str] = Security(api_key_header),
) -> APIKeyData:
    """
    FastAPI dependency that validates the API key from Authorization header.
    
    Expected format: "Bearer safari_xxxxx..."
    
    Returns:
        APIKeyData with validated key information
        
    Raises:
        HTTPException 401 if key is missing, invalid, or expired
        HTTPException 403 if key is revoked
    """
    from supabase import create_client
    
    # Check header exists
    if not authorization:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing Authorization header",
            headers={"WWW-Authenticate": "Bearer"},
        )
    
    # Extract token from "Bearer <token>" format
    parts = authorization.split(" ", 1)
    if len(parts) != 2 or parts[0].lower() != "bearer":
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid Authorization header format. Use: Bearer <api_key>",
            headers={"WWW-Authenticate": "Bearer"},
        )
    
    raw_key = parts[1].strip()
    
    # Validate key prefix
    if not raw_key.startswith("safari_"):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid API key format",
            headers={"WWW-Authenticate": "Bearer"},
        )
    
    # Hash and lookup
    key_hash = _hash_key(raw_key)
    
    try:
        supabase = create_client(
            os.environ["SUPABASE_URL"],
            os.environ["SUPABASE_KEY"],
        )
        
        result = supabase.table("api_keys").select(
            "id, user_id, project_id, is_active, expires_at, rate_limit_rpm, scopes"
        ).eq("key_hash", key_hash).execute()
        
        # Check if we got any results
        if not result.data or len(result.data) == 0:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid API key",
                headers={"WWW-Authenticate": "Bearer"},
            )
        
        key_record = result.data[0]
        
    except HTTPException:
        raise  # Re-raise HTTP exceptions
    except Exception as e:
        print(f"Database error during key validation: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Authentication service unavailable",
        )
    
    # Check if key is active
    if not key_record.get("is_active", False):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="API key has been revoked",
        )
    
    # Check expiry
    expires_at = key_record.get("expires_at")
    if expires_at:
        try:
            expiry_time = datetime.fromisoformat(expires_at.replace("Z", "+00:00"))
            if datetime.now(timezone.utc) > expiry_time:
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail="API key has expired",
                )
        except ValueError:
            pass  # If parsing fails, treat as non-expiring
    
    # Update last_used_at (fire and forget, don't block on this)
    try:
        supabase.table("api_keys").update({
            "last_used_at": datetime.now(timezone.utc).isoformat()
        }).eq("id", key_record["id"]).execute()
    except Exception:
        pass  # Don't fail the request if this update fails
    
    return APIKeyData(
        key_id=key_record["id"],
        user_id=key_record["user_id"],
        project_id=key_record.get("project_id"),
        rate_limit_rpm=key_record.get("rate_limit_rpm", 60),
        scopes=key_record.get("scopes", ["infer"]),
    )
