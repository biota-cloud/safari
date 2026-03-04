"""
Model Registry — Centralized model metadata and loading logic.

This module provides a single source of truth for model types, their expected
file extensions, and loader patterns. Used by Modal jobs and remote workers
to eliminate duplicated model loading code.

Architecture Reference: docs/architecture_reference.md (lines 179-215)
"""

from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from typing import Any


class ModelType(str, Enum):
    """Supported model types in SAFARI platform."""
    
    YOLO_DETECT = "yolo-detect"
    YOLO_CLASSIFY = "yolo-classify"
    CONVNEXT_CLASSIFY = "convnext-classify"
    SAM3_IMAGE = "sam3-image"
    SAM3_VIDEO = "sam3-video"


@dataclass(frozen=True)
class ModelInfo:
    """
    Metadata for a model type.
    
    Attributes:
        model_type: The ModelType enum value
        extension: Expected file extension (".pt" or ".pth")
        package: Package(s) required for loading
        loader_name: Human-readable name for logging
    """
    
    model_type: ModelType
    extension: str
    package: str
    loader_name: str


# Registry of all supported model types
_REGISTRY: dict[str, ModelInfo] = {
    ModelType.YOLO_DETECT.value: ModelInfo(
        model_type=ModelType.YOLO_DETECT,
        extension=".pt",
        package="ultralytics",
        loader_name="YOLO Detection",
    ),
    ModelType.YOLO_CLASSIFY.value: ModelInfo(
        model_type=ModelType.YOLO_CLASSIFY,
        extension=".pt",
        package="ultralytics",
        loader_name="YOLO Classification",
    ),
    ModelType.CONVNEXT_CLASSIFY.value: ModelInfo(
        model_type=ModelType.CONVNEXT_CLASSIFY,
        extension=".pth",
        package="torch+timm",
        loader_name="ConvNeXt Classification",
    ),
    ModelType.SAM3_IMAGE.value: ModelInfo(
        model_type=ModelType.SAM3_IMAGE,
        extension=".pt",
        package="ultralytics>=8.3.237",
        loader_name="SAM3 Image Predictor",
    ),
    ModelType.SAM3_VIDEO.value: ModelInfo(
        model_type=ModelType.SAM3_VIDEO,
        extension=".pt",
        package="ultralytics>=8.3.237",
        loader_name="SAM3 Video Predictor",
    ),
}


def get_model_info(model_type: str) -> ModelInfo:
    """
    Look up model metadata by type.
    
    Args:
        model_type: One of the ModelType values (e.g., "yolo-detect")
        
    Returns:
        ModelInfo with metadata for the model type
        
    Raises:
        KeyError: If model_type is not in the registry
    """
    if model_type not in _REGISTRY:
        valid_types = list(_REGISTRY.keys())
        raise KeyError(f"Unknown model type '{model_type}'. Valid types: {valid_types}")
    return _REGISTRY[model_type]


def detect_classifier_backbone(path: str | Path) -> str:
    """
    Auto-detect classifier backbone from file extension.
    
    This is used when loading a classifier model to determine whether
    it's a YOLO (.pt) or ConvNeXt (.pth) model.
    
    Args:
        path: Path to the model weights file
        
    Returns:
        "yolo-classify" or "convnext-classify"
        
    Raises:
        ValueError: If extension is not .pt or .pth
    """
    path = Path(path)
    ext = path.suffix.lower()
    
    if ext == ".pt":
        return ModelType.YOLO_CLASSIFY.value
    elif ext == ".pth":
        return ModelType.CONVNEXT_CLASSIFY.value
    else:
        raise ValueError(f"Unknown classifier extension '{ext}'. Expected .pt or .pth")


def get_all_model_types() -> list[str]:
    """Return list of all registered model type strings."""
    return list(_REGISTRY.keys())


def load_model(model_type: str, path: str | Path, **kwargs: Any) -> Any:
    """
    Load a model using the appropriate loader.
    
    Note: This function imports heavy dependencies only when called,
    keeping the registry module lightweight for import.
    
    Args:
        model_type: One of the ModelType values
        path: Path to the model weights
        **kwargs: Additional arguments passed to the loader
        
    Returns:
        Loaded model object
        
    Raises:
        KeyError: If model_type is not registered
        ImportError: If required packages are not installed
    """
    info = get_model_info(model_type)
    path = Path(path)
    
    if model_type == ModelType.YOLO_DETECT.value:
        from ultralytics import YOLO
        return YOLO(str(path))
    
    elif model_type == ModelType.YOLO_CLASSIFY.value:
        from ultralytics import YOLO
        return YOLO(str(path))
    
    elif model_type == ModelType.CONVNEXT_CLASSIFY.value:
        import torch
        import timm
        from torchvision import transforms
        
        device = kwargs.get("device") or torch.device(
            "cuda" if torch.cuda.is_available() else "cpu"
        )
        ckpt = torch.load(path, map_location=device, weights_only=False)
        
        model_size = ckpt.get("model_size", "tiny")
        num_classes = len(ckpt["classes"])
        
        model = timm.create_model(
            f"convnext_{model_size}", 
            pretrained=False, 
            num_classes=num_classes
        )
        model.load_state_dict(ckpt["model_state_dict"])
        model = model.to(device).eval()
        
        img_size = ckpt.get("image_size", 224)
        transform = transforms.Compose([
            transforms.Resize(int(img_size * 1.14)),
            transforms.CenterCrop(img_size),
            transforms.ToTensor(),
            transforms.Normalize([0.485, 0.456, 0.406], [0.229, 0.224, 0.225]),
        ])
        
        return {
            "model": model,
            "idx_to_class": ckpt["idx_to_class"],
            "transform": transform,
            "device": device,
        }
    
    elif model_type == ModelType.SAM3_IMAGE.value:
        from ultralytics.models.sam import SAM3SemanticPredictor
        
        overrides = kwargs.get("overrides", {})
        overrides["model"] = str(path)
        return SAM3SemanticPredictor(overrides=overrides)
    
    elif model_type == ModelType.SAM3_VIDEO.value:
        from ultralytics.models.sam import SAM3VideoSemanticPredictor
        
        overrides = kwargs.get("overrides", {})
        overrides["model"] = str(path)
        return SAM3VideoSemanticPredictor(overrides=overrides)
    
    else:
        raise KeyError(f"No loader implemented for model type '{model_type}'")
