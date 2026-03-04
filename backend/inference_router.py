"""
Inference Router — Unified entry point for all inference operations.

Routes YOLO detection and Hybrid (SAM3 + classifier) inference to the
appropriate executor based on project processing target (cloud/local).

Usage:
    from backend.inference_router import dispatch_inference, InferenceConfig

    # YOLO Detection
    config = InferenceConfig(
        model_type="yolo-detect",
        input_type="image",
        model_name_or_id="yolo11s.pt",  # or model UUID
    )
    result = dispatch_inference(config, image_url=url, confidence=0.25)

    # Hybrid Inference
    config = InferenceConfig(
        model_type="hybrid",
        input_type="batch",
        project_id=project_id,
        classifier_r2_path=path,
        classifier_classes=classes,
        sam3_prompts=prompts,
        prompt_class_map=mapping,
    )
    results = dispatch_inference(config, image_urls=urls, confidence=0.25)
"""

import modal
from dataclasses import dataclass, field
from typing import Literal, Optional, Any

from backend.job_router import get_job_target


@dataclass
class InferenceConfig:
    """Configuration for an inference request."""
    
    # Core params
    model_type: Literal["yolo-detect", "hybrid"]
    input_type: Literal["image", "batch", "video"]
    model_name_or_id: str  # "yolo11s.pt" (builtin) or model UUID (custom)
    
    # Target resolution
    project_id: Optional[str] = None  # For determining cloud/local
    
    # Hybrid-specific
    classifier_r2_path: str = ""
    classifier_classes: list[str] = field(default_factory=list)
    sam3_prompts: list[str] = field(default_factory=list)
    prompt_class_map: dict = field(default_factory=dict)
    
    @property
    def compute_target(self) -> Literal["cloud", "local"]:
        """Determine compute target from project."""
        return get_job_target(self.project_id) if self.project_id else "cloud"
    
    @property
    def is_builtin_model(self) -> bool:
        """Check if model is a built-in Ultralytics model."""
        return self.model_name_or_id.endswith(".pt") and not self._is_uuid(self.model_name_or_id)
    
    @staticmethod
    def _is_uuid(value: str) -> bool:
        """Check if string looks like a UUID."""
        import re
        uuid_pattern = re.compile(r'^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$', re.I)
        return bool(uuid_pattern.match(value))


# =============================================================================
# YOLO DETECTION DISPATCH
# =============================================================================

def _dispatch_yolo_image(config: InferenceConfig, **params) -> dict:
    """Dispatch single image YOLO inference."""
    image_url = params.get("image_url", "")
    confidence = params.get("confidence", 0.25)
    
    model_type = "builtin" if config.is_builtin_model else "custom"
    
    if config.compute_target == "local":
        # Local GPU requires action-level target selection with explicit machine
        raise RuntimeError(
            "Local inference requires explicit machine selection via action-level compute target."
        )
    else:
        # Cloud: Use Modal
        cls = modal.Cls.from_name("yolo-inference", "YOLOInference")
        return cls().predict_image.remote(
            model_type=model_type,
            model_name_or_id=config.model_name_or_id,
            image_url=image_url,
            confidence=confidence,
        )


def _dispatch_yolo_batch(config: InferenceConfig, **params) -> list[dict]:
    """Dispatch batch YOLO inference."""
    image_urls = params.get("image_urls", [])
    confidence = params.get("confidence", 0.25)
    
    model_type = "builtin" if config.is_builtin_model else "custom"
    
    if config.compute_target == "local":
        raise RuntimeError(
            "Local inference requires explicit machine selection via action-level compute target."
        )
    else:
        # Cloud: Use Modal
        cls = modal.Cls.from_name("yolo-inference", "YOLOInference")
        return cls().predict_images_batch.remote(
            model_type=model_type,
            model_name_or_id=config.model_name_or_id,
            image_urls=image_urls,
            confidence=confidence,
        )


def _dispatch_yolo_video(config: InferenceConfig, **params) -> dict:
    """Dispatch video YOLO inference."""
    video_url = params.get("video_url", "")
    confidence = params.get("confidence", 0.25)
    start_time = params.get("start_time", 0.0)
    end_time = params.get("end_time")
    frame_skip = params.get("frame_skip", 1)
    inference_result_id = params.get("inference_result_id")
    
    model_type = "builtin" if config.is_builtin_model else "custom"
    
    if config.compute_target == "local":
        raise RuntimeError(
            "Local inference requires explicit machine selection via action-level compute target."
        )
    else:
        # Cloud: Use Modal
        cls = modal.Cls.from_name("yolo-inference", "YOLOInference")
        return cls().predict_video.remote(
            model_type=model_type,
            model_name_or_id=config.model_name_or_id,
            video_url=video_url,
            confidence=confidence,
            start_time=start_time,
            end_time=end_time,
            frame_skip=frame_skip,
            inference_result_id=inference_result_id,
        )


# =============================================================================
# HYBRID DISPATCH (delegates to existing job_router)
# =============================================================================

def _dispatch_hybrid_image(config: InferenceConfig, **params) -> dict:
    """Dispatch single image hybrid inference."""
    from backend.job_router import dispatch_hybrid_inference
    
    return dispatch_hybrid_inference(
        project_id=config.project_id or "",
        image_url=params.get("image_url", ""),
        sam3_prompts=config.sam3_prompts,
        classifier_r2_path=config.classifier_r2_path,
        classifier_classes=config.classifier_classes,
        prompt_class_map=config.prompt_class_map,
        confidence_threshold=params.get("confidence", 0.25),
        classifier_confidence=params.get("classifier_confidence", 0.5),
    )


def _dispatch_hybrid_batch(config: InferenceConfig, **params) -> list[dict]:
    """Dispatch batch hybrid inference."""
    from backend.job_router import dispatch_hybrid_inference_batch
    
    return dispatch_hybrid_inference_batch(
        project_id=config.project_id or "",
        image_urls=params.get("image_urls", []),
        sam3_prompts=config.sam3_prompts,
        classifier_r2_path=config.classifier_r2_path,
        classifier_classes=config.classifier_classes,
        prompt_class_map=config.prompt_class_map,
        confidence_threshold=params.get("confidence", 0.25),
        classifier_confidence=params.get("classifier_confidence", 0.5),
    )


def _dispatch_hybrid_video(config: InferenceConfig, **params) -> dict:
    """Dispatch video hybrid inference."""
    from backend.job_router import dispatch_hybrid_inference_video
    
    return dispatch_hybrid_inference_video(
        project_id=config.project_id or "",
        video_url=params.get("video_url", ""),
        sam3_prompts=config.sam3_prompts,
        classifier_r2_path=config.classifier_r2_path,
        classifier_classes=config.classifier_classes,
        prompt_class_map=config.prompt_class_map,
        confidence_threshold=params.get("confidence", 0.25),
        classifier_confidence=params.get("classifier_confidence", 0.5),
        start_time=params.get("start_time", 0.0),
        end_time=params.get("end_time"),
        frame_skip=params.get("frame_skip", 1),
    )


# =============================================================================
# UNIFIED DISPATCH ENTRY POINT
# =============================================================================

def dispatch_inference(config: InferenceConfig, **params) -> dict | list[dict]:
    """
    Unified entry point for all inference operations.
    
    Routes to appropriate executor based on model_type, input_type, and compute_target.
    
    Args:
        config: InferenceConfig with model and routing parameters
        **params: Input-specific parameters:
            - image_url: str (for single image)
            - image_urls: list[str] (for batch)
            - video_url: str (for video)
            - confidence: float
            - classifier_confidence: float (hybrid only)
            - start_time, end_time, frame_skip: float/int (video only)
    
    Returns:
        dict for single/video, list[dict] for batch
    """
    # Route based on model type and input type
    if config.model_type == "yolo-detect":
        if config.input_type == "image":
            return _dispatch_yolo_image(config, **params)
        elif config.input_type == "batch":
            return _dispatch_yolo_batch(config, **params)
        elif config.input_type == "video":
            return _dispatch_yolo_video(config, **params)
    
    elif config.model_type == "hybrid":
        if config.input_type == "image":
            return _dispatch_hybrid_image(config, **params)
        elif config.input_type == "batch":
            return _dispatch_hybrid_batch(config, **params)
        elif config.input_type == "video":
            return _dispatch_hybrid_video(config, **params)
    
    raise ValueError(f"Unsupported config: model_type={config.model_type}, input_type={config.input_type}")
