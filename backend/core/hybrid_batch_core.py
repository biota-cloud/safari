"""
Core Batch Hybrid Inference Logic — SAM3 Detection + Classifier Species Identification.

This module contains the shared batch pipeline logic used by both Modal jobs and remote workers.
Environment-specific concerns (model paths, download functions) are passed as parameters.

The key optimization is reusing the SAM3 predictor and classifier across all images,
eliminating per-image cold start overhead.

Functions:
    run_hybrid_batch_inference: Process multiple images with shared model instances
"""

import base64
import os
import tempfile
from pathlib import Path
from typing import Callable, Optional

import cv2
import numpy as np

# Import shared utilities from core
from backend.core.image_utils import crop_from_box, download_image
from backend.core.classifier_utils import load_classifier, classify_with_convnext
from backend.core.hybrid_infer_core import mask_to_polygon


def run_hybrid_batch_inference(
    image_urls: list[str],
    sam3_prompts: list[str],
    classifier_r2_path: str,
    classifier_classes: list[str],
    confidence_threshold: float,
    classifier_confidence: float,
    # Environment-specific parameters:
    sam3_model_path: Optional[str] = None,
    download_classifier_fn: Callable[[str, Path], bool] = None,
    sam3_imgsz: int = 644,
    image_filenames: list[str] | None = None,  # Original filenames for debug logging
) -> list[dict]:
    """
    Run hybrid SAM3 + Classifier inference on multiple images sequentially.
    
    Reuses the SAM3 predictor and classifier across all images, eliminating
    cold start overhead. Designed for batch processing and Tauri API.
    
    Args:
        image_urls: List of presigned URLs to images
        sam3_prompts: Generic prompts for SAM3 (e.g., ["mammal", "bird"])
        classifier_r2_path: R2 path to classifier model weights
        classifier_classes: Class names the classifier can predict
        confidence_threshold: SAM3 detection confidence threshold
        classifier_confidence: Minimum classifier confidence to accept
        sam3_model_path: Path to SAM3 model (None for auto-download)
        download_classifier_fn: Function to download classifier from R2
    
    Returns:
        List of results, one per image, each containing:
            - index: Image index in batch
            - success: Whether processing succeeded
            - predictions: List of prediction dicts
            - yolo_labels: YOLO format label string
            - image_width/height: Image dimensions
            - sam3_detections: Number of SAM3 detections
            - filtered_detections: Number after confidence filtering
            - masks: List of mask dicts with polygon coordinates
    """
    from ultralytics.models.sam import SAM3SemanticPredictor
    
    os.environ["ULTRALYTICS_AUTOUPDATE"] = "false"
    
    work_dir = Path(tempfile.mkdtemp(prefix="hybrid_batch_"))
    
    print(f"=== Hybrid Batch Inference: {len(image_urls)} images ===")
    print(f"SAM3 prompts: {sam3_prompts}")
    print(f"Classifier classes: {classifier_classes}")
    
    try:
        # === Initialize SAM3 predictor ONCE ===
        print("\n[Setup] Loading SAM3 predictor...")
        overrides = dict(
            conf=confidence_threshold,
            task="segment",
            mode="predict",
            imgsz=sam3_imgsz,
            half=True,
            save=False,
        )
        
        # Add model path if specified (Modal uses explicit path, remote may auto-download)
        if sam3_model_path:
            overrides["model"] = sam3_model_path
        
        predictor = SAM3SemanticPredictor(overrides=overrides)
        
        # === Load classifier ONCE ===
        # Flush GPU memory after SAM3 init to reduce fragmentation
        import gc
        import torch
        gc.collect()
        if torch.cuda.is_available():
            torch.cuda.empty_cache()
        print("[Setup] Loading classifier model...")
        
        ext = ".pth" if classifier_r2_path.endswith(".pth") else ".pt"
        classifier_path = work_dir / f"classifier{ext}"
        
        if download_classifier_fn:
            if not download_classifier_fn(classifier_r2_path, classifier_path):
                raise RuntimeError(f"Failed to download classifier from {classifier_r2_path}")
        else:
            raise ValueError("download_classifier_fn is required")
        
        # Load classifier using unified loader
        classifier_data = load_classifier(classifier_r2_path, classifier_path)
        is_convnext = classifier_data["type"] == "convnext"
        
        if is_convnext:
            convnext_model = classifier_data["model"]
            convnext_idx_to_class = classifier_data["idx_to_class"]
            convnext_transform = classifier_data["transform"]
            convnext_device = classifier_data["device"]
            print(f"[Setup] ConvNeXt classifier loaded: {len(convnext_idx_to_class)} classes")
        else:
            classifier = classifier_data["model"]
            print(f"[Setup] YOLO classifier loaded: {len(classifier.names)} classes")
        
        # Build class name to ID mapping
        class_to_id = {name: idx for idx, name in enumerate(classifier_classes)}
        
        results_list = []
        batch_first_crop = None  # Capture first crop from entire batch for debugging
        batch_crop_widths = []   # Accumulated across all images for distribution summary
        batch_crop_heights = []
        
        # === Process each image ===
        for idx, image_url in enumerate(image_urls):
            # Use provided filename or fall back to URL extraction
            if image_filenames and idx < len(image_filenames):
                orig_filename = image_filenames[idx]
            else:
                from urllib.parse import urlparse, unquote
                url_path = urlparse(image_url).path
                orig_filename = unquote(url_path.split('/')[-1]) if url_path else f"input_{idx}"
            
            # Clear GPU cache between images to prevent memory fragmentation
            if idx > 0:
                torch.cuda.empty_cache()
            
            # GPU memory diagnostic
            gpu_alloc = torch.cuda.memory_allocated() / 1024**2
            gpu_reserved = torch.cuda.memory_reserved() / 1024**2
            print(f"\n[{idx+1}/{len(image_urls)}] Processing: {orig_filename}  [GPU: {gpu_alloc:.0f}MB alloc, {gpu_reserved:.0f}MB reserved]")
            
            try:
                # Download image
                image_bytes = download_image(image_url)
                
                # Get dimensions
                img_array = np.frombuffer(image_bytes, np.uint8)
                img = cv2.imdecode(img_array, cv2.IMREAD_COLOR)
                img_height, img_width = img.shape[:2]
                print(f"[{idx+1}] {orig_filename}: {img_width}x{img_height} ({len(image_bytes)} bytes)")
                
                # Save for SAM3
                image_path = work_dir / f"input_{idx}.jpg"
                image_path.write_bytes(image_bytes)
                
                # Diagnostic: confirm image on disk and expected SAM3 preprocessing
                aspect_ratio = img_width / img_height
                expected_long = sam3_imgsz
                expected_short = int(sam3_imgsz / aspect_ratio) if aspect_ratio > 1 else int(sam3_imgsz * aspect_ratio)
                print(f"[{idx+1}] SAM3 input: {img_width}x{img_height} (AR={aspect_ratio:.2f}), imgsz={sam3_imgsz}")
                print(f"[{idx+1}] Expected letterbox: {expected_long}x{expected_short} padded to {sam3_imgsz}x{sam3_imgsz}")
                
                # Run SAM3 detection (reusing predictor)
                predictor.set_image(str(image_path))
                
                sam3_detections = []
                for prompt in sam3_prompts:
                    results = predictor(text=[prompt])
                    if results and len(results) > 0:
                        res = results[0]
                        if hasattr(res, 'boxes') and res.boxes is not None:
                            boxes = res.boxes.xyxy.cpu().numpy()
                            # Log SAM3 confidence scores
                            confs = res.boxes.conf.cpu().numpy() if hasattr(res.boxes, 'conf') and res.boxes.conf is not None else []
                            for ci, c in enumerate(confs):
                                print(f"    [SAM3 det {ci}] conf={c:.4f} box={boxes[ci][:4].tolist()}")
                            
                            # Extract masks if available
                            masks_data = None
                            if hasattr(res, 'masks') and res.masks is not None:
                                try:
                                    if hasattr(res.masks, 'data'):
                                        masks_data = res.masks.data.cpu().numpy()  # Shape: (N, H, W)
                                except Exception as e:
                                    print(f"    Error extracting masks: {e}")
                            
                            for box_idx, box in enumerate(boxes):
                                # Convert mask to polygon if available
                                mask_polygon = None
                                if masks_data is not None and box_idx < len(masks_data):
                                    mask_polygon = mask_to_polygon(masks_data[box_idx], img_width, img_height)
                                
                                sam3_detections.append((box[:4], prompt, mask_polygon))
                        else:
                            print(f"    [SAM3] prompt='{prompt}': no boxes returned")
                    else:
                        print(f"    [SAM3] prompt='{prompt}': no results")
                
                print(f"[{idx+1}/{len(image_urls)}] SAM3 found {len(sam3_detections)} detections")
                
                if not sam3_detections:
                    results_list.append({
                        "index": idx,
                        "success": True,
                        "predictions": [],
                        "yolo_labels": "",
                        "image_width": img_width,
                        "image_height": img_height,
                        "sam3_detections": 0,
                        "filtered_detections": 0,
                    })
                    continue
                
                # Classify each detection
                final_predictions = []
                final_masks = []
                image_first_crop = None  # First crop from this image
                
                for det_idx, (box, sam3_prompt, mask_polygon) in enumerate(sam3_detections):
                    try:
                        x1, y1, x2, y2 = box
                        crop_bytes = crop_from_box(image_bytes, (x1, y1, x2, y2), padding=0.05)
                        
                        # Track crop resolution
                        from PIL import Image
                        import io as _io
                        _crop_img = Image.open(_io.BytesIO(crop_bytes))
                        batch_crop_widths.append(_crop_img.width)
                        batch_crop_heights.append(_crop_img.height)
                        print(f"    [Crop {det_idx}] Resolution: {_crop_img.width}x{_crop_img.height} (box: {int(x2-x1)}x{int(y2-y1)} from {img_width}x{img_height})")
                        
                        # Capture first crop for debugging
                        if image_first_crop is None:
                            image_first_crop = crop_bytes
                        
                        # Classify using appropriate model
                        if is_convnext:
                            top1_class, top1_conf = classify_with_convnext(
                                convnext_model, convnext_transform, crop_bytes, convnext_idx_to_class, convnext_device
                            )
                        else:
                            crop_path = work_dir / f"crop_{idx}_{det_idx}.jpg"
                            crop_path.write_bytes(crop_bytes)
                            
                            cls_results = classifier.predict(str(crop_path), verbose=False)
                            
                            if cls_results and len(cls_results) > 0:
                                probs = cls_results[0].probs
                                if probs is not None:
                                    top1_idx = probs.top1
                                    top1_conf = probs.top1conf.item()
                                    top1_class = classifier.names[top1_idx]
                                else:
                                    top1_class = None
                                    top1_conf = 0.0
                            else:
                                top1_class = None
                                top1_conf = 0.0
                        
                        print(f"    [Classify] crop {det_idx}: {top1_class} ({top1_conf:.2f})")
                        
                        # Determine if classified or unknown
                        if top1_class is not None and top1_conf >= classifier_confidence:
                            pred_class_name = top1_class
                            pred_class_id = class_to_id.get(top1_class, 0)
                            pred_confidence = top1_conf
                            print(f"    [Classify] ✓ Accepted")
                        else:
                            pred_class_name = "Unknown"
                            pred_class_id = -1
                            pred_confidence = 0.0
                            if top1_class is not None:
                                print(f"    [Classify] → Unknown (conf {top1_conf:.2f} < {classifier_confidence})")
                            else:
                                print(f"    [Classify] → Unknown (classification failed)")
                        
                        pred_dict = {
                            "class_name": pred_class_name,
                            "class_id": pred_class_id,
                            "confidence": pred_confidence,
                            "box": [
                                float(x1) / img_width,
                                float(y1) / img_height,
                                float(x2) / img_width,
                                float(y2) / img_height,
                            ],
                            "sam3_prompt": sam3_prompt,
                        }
                        final_predictions.append(pred_dict)
                        
                        # Add mask if available
                        if mask_polygon:
                            final_masks.append({
                                "class_name": pred_class_name,
                                "class_id": pred_class_id,
                                "polygon": mask_polygon,
                            })
                    except Exception as e:
                        print(f"[{idx+1}] Detection {det_idx} classification failed: {e}")
                
                # Format YOLO labels
                yolo_lines = []
                for pred in final_predictions:
                    x1, y1, x2, y2 = pred["box"]
                    x_center = (x1 + x2) / 2
                    y_center = (y1 + y2) / 2
                    width = x2 - x1
                    height = y2 - y1
                    yolo_lines.append(f"{pred['class_id']} {x_center:.6f} {y_center:.6f} {width:.6f} {height:.6f}")
                
                print(f"[{idx+1}/{len(image_urls)}] Final predictions: {len(final_predictions)}")
                
                # Track first crop from the entire batch
                if batch_first_crop is None and image_first_crop is not None:
                    batch_first_crop = image_first_crop
                
                results_list.append({
                    "index": idx,
                    "success": True,
                    "predictions": final_predictions,
                    "masks": final_masks,
                    "yolo_labels": "\n".join(yolo_lines),
                    "image_width": img_width,
                    "image_height": img_height,
                    "sam3_detections": len(sam3_detections),
                    "filtered_detections": len(final_predictions),
                    "debug_crop": base64.b64encode(image_first_crop).decode("ascii") if image_first_crop else None,
                })
                
            except Exception as e:
                print(f"[{idx+1}/{len(image_urls)}] Failed: {e}")
                results_list.append({
                    "index": idx,
                    "success": False,
                    "error": str(e),
                    "predictions": [],
                    "yolo_labels": "",
                })
        
        print(f"\n=== Batch complete: {len(results_list)} images processed ===")
        
        # === Crop Resolution Distribution Summary (across all images) ===
        if batch_crop_widths:
            import statistics
            min_sides = sorted([min(w, h) for w, h in zip(batch_crop_widths, batch_crop_heights)])
            print(f"\n  === Crop Resolution Distribution ({len(batch_crop_widths)} crops across {len(results_list)} images) ===")
            print(f"  Width  \u2014 min: {min(batch_crop_widths)}, max: {max(batch_crop_widths)}, "
                  f"mean: {int(statistics.mean(batch_crop_widths))}, median: {int(statistics.median(batch_crop_widths))}")
            print(f"  Height \u2014 min: {min(batch_crop_heights)}, max: {max(batch_crop_heights)}, "
                  f"mean: {int(statistics.mean(batch_crop_heights))}, median: {int(statistics.median(batch_crop_heights))}")
            p25 = min_sides[len(min_sides) // 4]
            p75 = min_sides[3 * len(min_sides) // 4]
            print(f"  Min side \u2014 p25: {p25}, median: {int(statistics.median(min_sides))}, p75: {p75}")
            print(f"  \u2192 Recommended ConvNeXt imgsz: {int(statistics.median(min_sides))} "
                  f"(median of shortest side)")
            print(f"    Crops below 224px: {sum(1 for s in min_sides if s < 224)}/{len(min_sides)}")
            print(f"    Crops below 384px: {sum(1 for s in min_sides if s < 384)}/{len(min_sides)}")
            print(f"    Crops below 448px: {sum(1 for s in min_sides if s < 448)}/{len(min_sides)}")
        
        return results_list
        
    except Exception as e:
        import traceback
        print(f"\nHybrid batch inference failed: {e}")
        traceback.print_exc()
        raise
        
    finally:
        import shutil
        shutil.rmtree(work_dir, ignore_errors=True)
