"""
Shared classifier utilities used by both Modal jobs and remote workers.

This module provides a single source of truth for:
- ConvNeXt model loading
- Unified classifier loading (YOLO vs ConvNeXt auto-detection)
- ConvNeXt classification inference
"""

import io
from pathlib import Path


def load_convnext_classifier(local_path: Path) -> tuple:
    """
    Load ConvNeXt classifier from .pth checkpoint.
    
    Args:
        local_path: Path to the .pth checkpoint file
    
    Returns:
        Tuple of (model, idx_to_class, transform, device)
    """
    import timm
    import torch
    from torchvision import transforms
    
    device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
    ckpt = torch.load(local_path, map_location=device, weights_only=False)
    
    # Get model config from checkpoint
    model_size = ckpt.get("model_size", "tiny")
    model_version = ckpt.get("model_version", "v1")  # v1 default for backward compat
    num_classes = len(ckpt["classes"])
    
    # Resolve timm model name
    if model_version == "v2":
        timm_name = f"convnextv2_{model_size}"
        version_label = "V2-"
    else:
        timm_name = f"convnext_{model_size}"
        version_label = ""
    
    print(f"  Loading ConvNeXt{version_label}{model_size} with {num_classes} classes...")
    model = timm.create_model(timm_name, pretrained=False, num_classes=num_classes)
    model.load_state_dict(ckpt["model_state_dict"])
    model = model.to(device).eval()
    
    # Create transform matching training (including CLAHE)
    img_size = ckpt.get("image_size", 224)
    transform = transforms.Compose([
        transforms.Lambda(_apply_clahe),  # Match training CLAHE preprocessing
        transforms.Resize(int(img_size * 1.14)),
        transforms.CenterCrop(img_size),
        transforms.ToTensor(),
        transforms.Normalize([0.485, 0.456, 0.406], [0.229, 0.224, 0.225]),
    ])
    
    return model, ckpt["idx_to_class"], transform, device


def _apply_clahe(img):
    """Apply CLAHE to PIL image — must match training preprocessing."""
    import cv2
    import numpy as np
    arr = np.array(img)
    lab = cv2.cvtColor(arr, cv2.COLOR_RGB2LAB)
    clahe = cv2.createCLAHE(clipLimit=2.0, tileGridSize=(8, 8))
    lab[:, :, 0] = clahe.apply(lab[:, :, 0])
    result = cv2.cvtColor(lab, cv2.COLOR_LAB2RGB)
    from PIL import Image
    return Image.fromarray(result)


def load_classifier(r2_path: str, local_path: Path) -> dict:
    """
    Unified classifier loader with auto-detection of backbone type.
    
    Detects model type from file extension (.pt = YOLO, .pth = ConvNeXt)
    and loads using the appropriate method.
    
    Args:
        r2_path: Original R2 path (used for extension detection)
        local_path: Local path where model was downloaded
    
    Returns:
        dict with keys:
            - "type": "yolo" or "convnext"
            - "model": loaded model
            - For ConvNeXt: also "idx_to_class", "transform", "device"
    """
    if r2_path.endswith(".pth"):
        model, idx_to_class, transform, device = load_convnext_classifier(local_path)
        return {
            "type": "convnext",
            "model": model,
            "idx_to_class": idx_to_class,
            "transform": transform,
            "device": device,
        }
    else:
        from ultralytics import YOLO
        return {
            "type": "yolo",
            "model": YOLO(str(local_path)),
        }


def classify_with_convnext(
    model, transform, crop_bytes: bytes, idx_to_class: dict, device
) -> tuple:
    """
    Classify a crop image using ConvNeXt.
    
    Args:
        model: Loaded ConvNeXt model
        transform: Image transform pipeline
        crop_bytes: Raw image bytes
        idx_to_class: Mapping from class index to name
        device: torch device
    
    Returns:
        Tuple of (class_name, confidence)
    """
    import torch
    from PIL import Image
    
    img = Image.open(io.BytesIO(crop_bytes)).convert("RGB")
    
    with torch.no_grad():
        input_tensor = transform(img).unsqueeze(0).to(device)
        outputs = model(input_tensor)
        probs = torch.softmax(outputs, dim=1)
        conf, idx = probs.max(1)
    
    return idx_to_class[idx.item()], conf.item()
