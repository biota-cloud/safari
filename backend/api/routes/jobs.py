"""
Jobs Routes — /api/v1/jobs endpoints for async job status polling.

Endpoints:
- GET /api/v1/jobs/{job_id} — Get job status and progress
"""

import os
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel

from backend.api.auth import APIKeyData, validate_api_key


router = APIRouter(prefix="/api/v1/jobs", tags=["jobs"])


# =============================================================================
# RESPONSE MODELS
# =============================================================================

class VideoFramePredictions(BaseModel):
    """Predictions for a single video frame."""
    frame: int
    predictions: list[dict]


class JobStatusResponse(BaseModel):
    """Response for job status query."""
    job_id: str
    status: str  # "pending" | "processing" | "completed" | "failed"
    progress: Optional[int] = None  # Percentage 0-100
    progress_current: Optional[int] = None
    progress_total: Optional[int] = None
    frames_processed: Optional[int] = None
    total_frames: Optional[int] = None
    error_message: Optional[str] = None
    result: Optional[dict] = None  # Final results when completed


# =============================================================================
# ENDPOINTS
# =============================================================================

@router.get("/{job_id}", response_model=JobStatusResponse)
async def get_job_status(
    job_id: str,
    api_key: APIKeyData = Depends(validate_api_key),
):
    """
    Get the status and progress of an async job.
    
    - **job_id**: The job ID returned from video submission
    
    Poll this endpoint periodically to track progress.
    When status is "completed", the result field contains predictions.
    """
    from supabase import create_client
    
    try:
        supabase = create_client(
            os.environ["SUPABASE_URL"],
            os.environ["SUPABASE_KEY"],
        )
        
        result = supabase.table("api_jobs").select(
            "id, api_key_id, status, progress_current, progress_total, "
            "error_message, result_json, created_at, completed_at"
        ).eq("id", job_id).maybe_single().execute()
        
    except Exception as e:
        print(f"Database error getting job status: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to retrieve job status",
        )
    
    if not result.data:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Job '{job_id}' not found",
        )
    
    job = result.data
    
    # Verify the requesting key owns this job
    if job["api_key_id"] != api_key.key_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You don't have access to this job",
        )
    
    # Calculate progress percentage
    progress_pct = None
    current = job.get("progress_current", 0)
    total = job.get("progress_total", 0)
    if total > 0:
        progress_pct = int((current / total) * 100)
    
    return JobStatusResponse(
        job_id=job["id"],
        status=job["status"],
        progress=progress_pct,
        progress_current=current,
        progress_total=total,
        frames_processed=current if job["status"] in ["processing", "completed"] else None,
        total_frames=total if total > 0 else None,
        error_message=job.get("error_message"),
        result=job.get("result_json") if job["status"] == "completed" else None,
    )
