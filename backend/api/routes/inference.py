"""
Inference Routes — /api/v1/infer endpoints for image and video inference.

Endpoints:
- POST /api/v1/infer/{model_slug} — Synchronous image inference
- POST /api/v1/infer/{model_slug}/video — Async video inference (returns job_id)
"""

import os
import time
import uuid
from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, Depends, File, HTTPException, Query, UploadFile, status
from pydantic import BaseModel

from backend.api.auth import APIKeyData, validate_api_key


router = APIRouter(prefix="/api/v1/infer", tags=["inference"])


# =============================================================================
# RESPONSE MODELS
# =============================================================================

class Prediction(BaseModel):
    """Single detection/classification prediction."""
    class_name: str
    class_id: int
    confidence: float
    box: list[float]  # [x1, y1, x2, y2] normalized 0-1
    box_format: str = "xyxy_normalized"


class ImageInferenceResponse(BaseModel):
    """Response for synchronous image inference."""
    model: str
    model_type: str
    predictions: list[Prediction]
    image_width: int
    image_height: int
    inference_time_ms: int
    request_id: str


class VideoJobResponse(BaseModel):
    """Response for async video job submission."""
    job_id: str
    status: str  # "pending" | "processing" | "completed" | "failed"
    message: str


class ImageResult(BaseModel):
    """Result for a single image in batch inference."""
    index: int
    success: bool = True
    predictions: list[Prediction]
    image_width: int = 0
    image_height: int = 0
    error: str | None = None


class BatchInferenceResponse(BaseModel):
    """Response for batch image inference."""
    model: str
    model_type: str
    results: list[ImageResult]
    total_images: int
    total_predictions: int
    inference_time_ms: int
    request_id: str


# =============================================================================
# HELPER FUNCTIONS
# =============================================================================

def _get_api_model(slug: str) -> dict:
    """
    Lookup API model by slug.
    
    Returns:
        Model record if found and active
        
    Raises:
        HTTPException 404 if not found or inactive
    """
    from supabase import create_client
    
    supabase = create_client(
        os.environ["SUPABASE_URL"],
        os.environ["SUPABASE_KEY"],
    )
    
    result = supabase.table("api_models").select(
        "id, slug, display_name, model_type, classes_snapshot, weights_r2_path, "
        "is_active, training_run_id, project_id, user_id, "
        "sam3_prompt, sam3_confidence, sam3_imgsz"  # Hybrid config fields
    ).eq("slug", slug).eq("is_active", True).execute()
    
    if not result.data or len(result.data) == 0:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Model '{slug}' not found or inactive",
        )
    
    return result.data[0]
    



def _check_model_access(api_key: APIKeyData, model: dict) -> None:
    """
    Verify the API key has access to this model.
    
    Rules:
    - If key has project_id, it must match model's project_id
    - User-wide keys (project_id=None) can access any model owned by that user
    """
    key_project = api_key.project_id
    model_project = model.get("project_id")
    model_user = model.get("user_id")
    
    # User-wide key — check user ownership
    if key_project is None:
        if model_user != api_key.user_id:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="API key does not have access to this model",
            )
        return
    
    # Project-scoped key — check project match
    if key_project != model_project:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="API key is scoped to a different project",
        )


def _log_usage(
    api_key: APIKeyData,
    model: dict,
    request_type: str,
    status_code: int,
    file_size_bytes: Optional[int] = None,
    inference_time_ms: Optional[int] = None,
    prediction_count: Optional[int] = None,
    error_message: Optional[str] = None,
) -> None:
    """Log API usage for analytics (fire and forget)."""
    from supabase import create_client
    
    try:
        supabase = create_client(
            os.environ["SUPABASE_URL"],
            os.environ["SUPABASE_KEY"],
        )
        
        supabase.table("api_usage_logs").insert({
            "api_key_id": api_key.key_id,
            "api_model_id": model["id"],
            "request_type": request_type,
            "file_size_bytes": file_size_bytes,
            "inference_time_ms": inference_time_ms,
            "prediction_count": prediction_count,
            "status_code": status_code,
            "error_message": error_message,
        }).execute()
        
        # Increment model usage counter and update last_used_at
        current = supabase.table("api_models").select("total_requests").eq("id", model["id"]).single().execute()
        new_count = (current.data.get("total_requests", 0) or 0) + 1
        supabase.table("api_models").update({
            "total_requests": new_count,
            "last_used_at": datetime.now(timezone.utc).isoformat(),
        }).eq("id", model["id"]).execute()
        
    except Exception as e:
        print(f"Failed to log usage: {e}")


# =============================================================================
# ENDPOINTS
# =============================================================================

@router.post("/{model_slug}", response_model=ImageInferenceResponse)
async def infer_image(
    model_slug: str,
    file: UploadFile = File(...),
    confidence: float = Query(0.25, ge=0.0, le=1.0, description="Confidence threshold"),
    api_key: APIKeyData = Depends(validate_api_key),
):
    """
    Run inference on a single image.
    
    - **model_slug**: Unique identifier for the model (e.g., "lynx-detector-v2")
    - **file**: Image file (JPEG, PNG, WebP)
    - **confidence**: Detection confidence threshold (0-1)
    
    Returns predictions with bounding boxes in normalized coordinates.
    """
    import modal
    
    request_id = str(uuid.uuid4())
    start_time = time.time()
    
    # Validate model exists and is accessible
    model = _get_api_model(model_slug)
    _check_model_access(api_key, model)
    
    # Validate file type
    content_type = file.content_type or ""
    if not content_type.startswith("image/"):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid file type: {content_type}. Expected image/jpeg, image/png, or image/webp",
        )
    
    # Read file content
    file_content = await file.read()
    file_size = len(file_content)
    
    # Validate file size (max 50MB)
    max_size = 50 * 1024 * 1024
    if file_size > max_size:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"File too large: {file_size} bytes. Maximum: {max_size} bytes",
        )
    
    try:
        # Call Modal inference job
        # Route by model_type: classification uses hybrid flow, detection uses YOLO
        APIInference = modal.Cls.from_name("tyto-api-inference", "APIInference")
        
        if model["model_type"] == "classification":
            # Hybrid flow: SAM3 detection + classifier
            result = APIInference().predict_image_hybrid.remote(
                classifier_r2_path=model["weights_r2_path"],
                image_bytes=file_content,
                sam3_prompt=model.get("sam3_prompt") or "animal",
                classifier_classes=model["classes_snapshot"],
                confidence=confidence,
                sam3_confidence=model.get("sam3_confidence") or 0.25,
                sam3_imgsz=model.get("sam3_imgsz") or 640,
            )
        else:
            # Detection flow: YOLO
            result = APIInference().predict_image.remote(
                weights_r2_path=model["weights_r2_path"],
                image_bytes=file_content,
                confidence=confidence,
                classes=model["classes_snapshot"],
            )
        
        inference_time_ms = int((time.time() - start_time) * 1000)
        
        # Format predictions
        predictions = [
            Prediction(
                class_name=p["class_name"],
                class_id=p["class_id"],
                confidence=p["confidence"],
                box=p["box"],
                box_format="xyxy_normalized",
            )
            for p in result.get("predictions", [])
        ]
        
        # Log success
        _log_usage(
            api_key=api_key,
            model=model,
            request_type="image",
            status_code=200,
            file_size_bytes=file_size,
            inference_time_ms=inference_time_ms,
            prediction_count=len(predictions),
        )
        
        return ImageInferenceResponse(
            model=model_slug,
            model_type=model["model_type"],
            predictions=predictions,
            image_width=result.get("image_width", 0),
            image_height=result.get("image_height", 0),
            inference_time_ms=inference_time_ms,
            request_id=request_id,
        )
        
    except modal.exception.NotFoundError:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Inference service unavailable. Please try again later.",
        )
    except Exception as e:
        inference_time_ms = int((time.time() - start_time) * 1000)
        _log_usage(
            api_key=api_key,
            model=model,
            request_type="image",
            status_code=500,
            file_size_bytes=file_size,
            inference_time_ms=inference_time_ms,
            error_message=str(e),
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Inference failed: {str(e)}",
        )


@router.post("/{model_slug}/video", response_model=VideoJobResponse)
async def submit_video_job(
    model_slug: str,
    file: UploadFile = File(...),
    confidence: float = Query(0.25, ge=0.0, le=1.0, description="Confidence threshold"),
    frame_skip: int = Query(1, ge=1, le=30, description="Process every Nth frame"),
    start_time: float = Query(0.0, ge=0.0, description="Start time in seconds"),
    end_time: Optional[float] = Query(None, ge=0.0, description="End time in seconds"),
    api_key: APIKeyData = Depends(validate_api_key),
):
    """
    Submit a video for async inference processing.
    
    - **model_slug**: Unique identifier for the model
    - **file**: Video file (MP4, MOV, AVI)
    - **confidence**: Detection confidence threshold (0-1)
    - **frame_skip**: Process every Nth frame (1 = every frame, 5 = every 5th)
    - **start_time**: Start processing from this time (seconds)
    - **end_time**: Stop processing at this time (seconds)
    
    Returns a job_id to poll for progress at /api/v1/jobs/{job_id}
    """
    from supabase import create_client
    import modal
    
    # Validate model exists and is accessible
    model = _get_api_model(model_slug)
    _check_model_access(api_key, model)
    
    # Validate file type
    content_type = file.content_type or ""
    valid_video_types = ["video/mp4", "video/quicktime", "video/x-msvideo", "video/webm"]
    if content_type not in valid_video_types and not content_type.startswith("video/"):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid file type: {content_type}. Expected video/mp4, video/quicktime, etc.",
        )
    
    # Read file content
    file_content = await file.read()
    file_size = len(file_content)
    
    # Validate file size (max 500MB)
    max_size = 500 * 1024 * 1024
    if file_size > max_size:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"File too large: {file_size} bytes. Maximum: {max_size} bytes",
        )
    
    # Create job record
    job_id = str(uuid.uuid4())
    
    try:
        supabase = create_client(
            os.environ["SUPABASE_URL"],
            os.environ["SUPABASE_KEY"],
        )
        
        # Insert job into api_jobs table
        supabase.table("api_jobs").insert({
            "id": job_id,
            "api_key_id": api_key.key_id,
            "api_model_id": model["id"],
            "user_id": api_key.user_id,
            "job_type": "video_inference",
            "status": "pending",
            "progress_current": 0,
            "progress_total": 0,
            "input_metadata": {
                "filename": file.filename,
                "file_size_bytes": file_size,
                "confidence": confidence,
                "frame_skip": frame_skip,
                "start_time": start_time,
                "end_time": end_time,
            },
        }).execute()
        
        # Spawn Modal job (async, returns immediately)
        # Route by model_type: classification uses hybrid flow, detection uses YOLO
        APIInference = modal.Cls.from_name("tyto-api-inference", "APIInference")
        
        if model["model_type"] == "classification":
            # Hybrid flow: SAM3 detection + classifier
            APIInference().process_video_job_hybrid.spawn(
                job_id=job_id,
                classifier_r2_path=model["weights_r2_path"],
                video_bytes=file_content,
                sam3_prompt=model.get("sam3_prompt") or "animal",
                classifier_classes=model["classes_snapshot"],
                confidence=confidence,
                sam3_confidence=model.get("sam3_confidence") or 0.25,
                sam3_imgsz=model.get("sam3_imgsz") or 640,
                frame_skip=frame_skip,
                start_time=start_time,
                end_time=end_time,
            )
        else:
            # Detection flow: YOLO
            APIInference().process_video_job.spawn(
                job_id=job_id,
                weights_r2_path=model["weights_r2_path"],
                video_bytes=file_content,
                confidence=confidence,
                frame_skip=frame_skip,
                start_time=start_time,
                end_time=end_time,
                classes=model["classes_snapshot"],
            )
        
        return VideoJobResponse(
            job_id=job_id,
            status="pending",
            message="Video job submitted. Poll /api/v1/jobs/{job_id} for progress.",
        )
        
    except modal.exception.NotFoundError:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Inference service unavailable. Please try again later.",
        )
    except Exception as e:
        # Try to mark job as failed
        try:
            supabase.table("api_jobs").update({
                "status": "failed",
                "error_message": str(e),
            }).eq("id", job_id).execute()
        except Exception:
            pass
        
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to submit video job: {str(e)}",
        )


@router.post("/{model_slug}/batch", response_model=BatchInferenceResponse)
async def infer_batch(
    model_slug: str,
    files: list[UploadFile] = File(...),
    confidence: float = Query(0.25, ge=0.0, le=1.0, description="Confidence threshold"),
    api_key: APIKeyData = Depends(validate_api_key),
):
    """
    Run inference on multiple images in a single call.
    
    Optimized for high-throughput frame sequences (e.g., from Tauri desktop client).
    Models are loaded once and reused across all images.
    
    - **model_slug**: Unique identifier for the model
    - **files**: Multiple image files (max 100 images, 10MB each)
    - **confidence**: Detection confidence threshold (0-1)
    
    Returns predictions for each image with preserved order.
    """
    import modal
    
    request_id = str(uuid.uuid4())
    start_time = time.time()
    
    # Validate model exists and is accessible
    model = _get_api_model(model_slug)
    _check_model_access(api_key, model)
    
    # Validate batch size
    max_batch_size = 100
    if len(files) > max_batch_size:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Too many files: {len(files)}. Maximum: {max_batch_size}",
        )
    
    if len(files) == 0:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="No files provided",
        )
    
    # Read all files and validate
    images_data = []
    total_size = 0
    max_file_size = 10 * 1024 * 1024  # 10MB per file
    
    for idx, file in enumerate(files):
        # Validate content type
        content_type = file.content_type or ""
        if not content_type.startswith("image/"):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"File {idx}: Invalid type {content_type}. Expected image/*",
            )
        
        # Read content
        content = await file.read()
        
        # Validate size
        if len(content) > max_file_size:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"File {idx} too large: {len(content)} bytes. Max: {max_file_size}",
            )
        
        images_data.append(content)
        total_size += len(content)
    
    try:
        # Call Modal batch inference
        APIInference = modal.Cls.from_name("tyto-api-inference", "APIInference")
        
        if model["model_type"] == "classification":
            # Hybrid flow: SAM3 + Classifier
            results = APIInference().predict_images_hybrid_batch.remote(
                classifier_r2_path=model["weights_r2_path"],
                images_data=images_data,
                sam3_prompt=model.get("sam3_prompt") or "animal",
                classifier_classes=model["classes_snapshot"],
                confidence=confidence,
                sam3_confidence=model.get("sam3_confidence") or 0.25,
                sam3_imgsz=model.get("sam3_imgsz") or 640,
            )
        else:
            # Detection flow: YOLO
            results = APIInference().predict_images_batch.remote(
                weights_r2_path=model["weights_r2_path"],
                images_data=images_data,
                confidence=confidence,
                classes=model["classes_snapshot"],
            )
        
        inference_time_ms = int((time.time() - start_time) * 1000)
        
        # Format results
        formatted_results = []
        total_predictions = 0
        
        for r in results:
            predictions = [
                Prediction(
                    class_name=p["class_name"],
                    class_id=p["class_id"],
                    confidence=p["confidence"],
                    box=p["box"],
                    box_format="xyxy_normalized",
                )
                for p in r.get("predictions", [])
            ]
            total_predictions += len(predictions)
            
            formatted_results.append(ImageResult(
                index=r["index"],
                success=r.get("success", True),
                predictions=predictions,
                image_width=r.get("image_width", 0),
                image_height=r.get("image_height", 0),
                error=r.get("error"),
            ))
        
        # Log success
        _log_usage(
            api_key=api_key,
            model=model,
            request_type="batch",
            status_code=200,
            file_size_bytes=total_size,
            inference_time_ms=inference_time_ms,
            prediction_count=total_predictions,
        )
        
        return BatchInferenceResponse(
            model=model_slug,
            model_type=model["model_type"],
            results=formatted_results,
            total_images=len(files),
            total_predictions=total_predictions,
            inference_time_ms=inference_time_ms,
            request_id=request_id,
        )
        
    except modal.exception.NotFoundError:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Inference service unavailable. Please try again later.",
        )
    except Exception as e:
        inference_time_ms = int((time.time() - start_time) * 1000)
        _log_usage(
            api_key=api_key,
            model=model,
            request_type="batch",
            status_code=500,
            file_size_bytes=total_size,
            inference_time_ms=inference_time_ms,
            error_message=str(e),
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Batch inference failed: {str(e)}",
        )
