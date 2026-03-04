#!/usr/bin/env python3
"""
SAFARI Remote Worker — Standard YOLO Inference.

Standalone script that mirrors Modal infer_job.py for local GPU execution.
Supports both built-in and custom trained YOLO models.

Usage:
    echo '{"image_url": "...", ...}' | python remote_infer.py

Expected JSON input (single image):
    {
        "model_type": "builtin",  # or "custom"
        "model_name_or_id": "yolo11s.pt",  # or model UUID
        "model_r2_path": null,  # R2 path for custom models
        "image_url": "presigned_url",
        "confidence": 0.25
    }

Expected JSON input (batch):
    {
        "batch": true,
        "model_type": "builtin",
        "model_name_or_id": "yolo11s.pt",
        "image_urls": ["url1", "url2", ...],
        "confidence": 0.25
    }

Output:
    JSON result to stdout with predictions.
"""

import json
import os
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from remote_utils import (
    download_from_r2_cached,
    get_models_dir,
)


class YOLOInference:
    """YOLO inference class supporting built-in and custom models."""
    
    def __init__(self):
        self.model = None
        self.current_model_key = None
    
    def _load_builtin_model(self, model_name: str):
        """Load a built-in YOLO model from Ultralytics."""
        from ultralytics import YOLO
        
        if self.current_model_key == f"builtin:{model_name}":
            return  # Already loaded
        
        print(f"Loading built-in model: {model_name}")
        self.model = YOLO(model_name)
        self.current_model_key = f"builtin:{model_name}"
    
    def _load_custom_model(self, model_id: str, model_r2_path: str = None):
        """Load a custom model from R2 or local cache."""
        from ultralytics import YOLO
        
        if self.current_model_key == f"custom:{model_id}":
            return  # Already loaded
        
        print(f"Loading custom model: {model_id}")
        
        # Check local cache first
        models_dir = get_models_dir()
        local_path = models_dir / f"{model_id}.pt"
        
        if not local_path.exists():
            if not model_r2_path:
                raise ValueError(f"model_r2_path required for custom model {model_id}")
            
            print(f"Downloading model from R2: {model_r2_path}")
            if not download_from_r2_cached(model_r2_path, local_path):
                raise RuntimeError(f"Failed to download model from {model_r2_path}")
        
        self.model = YOLO(str(local_path))
        self.current_model_key = f"custom:{model_id}"
    
    def _parse_yolo_results(self, results, img_width: int, img_height: int) -> list[dict]:
        """Parse YOLO results into standardized format."""
        predictions = []
        
        if results and len(results) > 0:
            res = results[0]
            if res.boxes is not None:
                for box in res.boxes:
                    cls_id = int(box.cls[0].item())
                    conf = float(box.conf[0].item())
                    x1, y1, x2, y2 = box.xyxy[0].cpu().numpy()
                    
                    # Normalize coordinates
                    predictions.append({
                        "class_id": cls_id,
                        "class_name": self.model.names.get(cls_id, "Unknown"),
                        "confidence": conf,
                        "box": [
                            float(x1) / img_width,
                            float(y1) / img_height,
                            float(x2) / img_width,
                            float(y2) / img_height,
                        ],
                    })
        
        return predictions
    
    def _format_predictions_to_yolo(self, predictions: list) -> str:
        """Convert predictions to YOLO format labels."""
        yolo_lines = []
        for pred in predictions:
            x1, y1, x2, y2 = pred["box"]
            class_id = pred["class_id"]
            
            x_center = (x1 + x2) / 2
            y_center = (y1 + y2) / 2
            width = x2 - x1
            height = y2 - y1
            
            yolo_lines.append(f"{class_id} {x_center:.6f} {y_center:.6f} {width:.6f} {height:.6f}")
        
        return "\n".join(yolo_lines)
    
    def predict_image(
        self,
        model_type: str,
        model_name_or_id: str,
        image_url: str,
        confidence: float = 0.25,
        model_r2_path: str = None,
    ) -> dict:
        """Run inference on a single image."""
        import cv2
        import numpy as np
        import requests
        
        os.environ["ULTRALYTICS_AUTOUPDATE"] = "false"
        
        try:
            # Load model
            if model_type == "builtin":
                self._load_builtin_model(model_name_or_id)
            else:
                self._load_custom_model(model_name_or_id, model_r2_path)
            
            # Download image
            print(f"Downloading image...")
            response = requests.get(image_url, timeout=60)
            response.raise_for_status()
            image_bytes = response.content
            
            # Decode image
            img_array = np.frombuffer(image_bytes, np.uint8)
            img = cv2.imdecode(img_array, cv2.IMREAD_COLOR)
            img_height, img_width = img.shape[:2]
            
            # Run inference
            print(f"Running inference...")
            results = self.model.predict(img, conf=confidence, verbose=False)
            
            # Parse predictions
            predictions = self._parse_yolo_results(results, img_width, img_height)
            yolo_labels = self._format_predictions_to_yolo(predictions)
            
            print(f"Found {len(predictions)} detections")
            
            return {
                "success": True,
                "predictions": predictions,
                "yolo_labels": yolo_labels,
                "image_width": img_width,
                "image_height": img_height,
            }
            
        except Exception as e:
            import traceback
            print(f"Inference failed: {e}")
            traceback.print_exc()
            
            return {
                "success": False,
                "error": str(e),
                "predictions": [],
                "yolo_labels": "",
            }
    
    def predict_images_batch(
        self,
        model_type: str,
        model_name_or_id: str,
        image_urls: list[str],
        confidence: float = 0.25,
        model_r2_path: str = None,
    ) -> list[dict]:
        """Run inference on multiple images sequentially."""
        import cv2
        import numpy as np
        import requests
        
        os.environ["ULTRALYTICS_AUTOUPDATE"] = "false"
        
        # Load model once
        if model_type == "builtin":
            self._load_builtin_model(model_name_or_id)
        else:
            self._load_custom_model(model_name_or_id, model_r2_path)
        
        results_list = []
        
        for idx, image_url in enumerate(image_urls):
            print(f"[{idx+1}/{len(image_urls)}] Processing...")
            
            try:
                # Download
                response = requests.get(image_url, timeout=60)
                response.raise_for_status()
                image_bytes = response.content
                
                # Decode
                img_array = np.frombuffer(image_bytes, np.uint8)
                img = cv2.imdecode(img_array, cv2.IMREAD_COLOR)
                img_height, img_width = img.shape[:2]
                
                # Infer
                results = self.model.predict(img, conf=confidence, verbose=False)
                
                # Parse
                predictions = self._parse_yolo_results(results, img_width, img_height)
                yolo_labels = self._format_predictions_to_yolo(predictions)
                
                print(f"[{idx+1}/{len(image_urls)}] Found {len(predictions)} detections")
                
                results_list.append({
                    "index": idx,
                    "success": True,
                    "predictions": predictions,
                    "yolo_labels": yolo_labels,
                    "image_width": img_width,
                    "image_height": img_height,
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
        
        print(f"\n=== Batch complete: {len(results_list)} images ===")
        return results_list


def main():
    """Read job params from stdin, execute inference, output result."""
    try:
        params = json.load(sys.stdin)
    except json.JSONDecodeError as e:
        print(json.dumps({"success": False, "error": f"Invalid JSON input: {e}"}))
        sys.exit(1)
    
    inference = YOLOInference()
    
    if params.get("batch", False):
        del params["batch"]
        result = inference.predict_images_batch(**params)
    else:
        result = inference.predict_image(**params)
    
    print(json.dumps(result))


if __name__ == "__main__":
    main()
