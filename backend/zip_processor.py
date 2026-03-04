"""
ZIP Processor — Extract and parse YOLO dataset ZIP files.

Handles:
- ZIP extraction to temp directory
- Structure validation (images/, labels/ folders)
- Class name extraction from data.yaml or classes.txt
- Image-label file matching
"""

import os
import zipfile
import tempfile
import shutil
from typing import Optional
import yaml


class ZipProcessorError(Exception):
    """Raised when ZIP processing fails."""
    pass


class YOLODatasetInfo:
    """Parsed information from a YOLO dataset ZIP."""
    
    def __init__(self):
        self.dataset_name: str = ""
        self.classes: list[str] = []
        self.image_files: list[str] = []  # Full paths in temp dir
        self.label_files: dict[str, str] = {}  # image_basename -> label_path
        self.temp_dir: str = ""
        self.image_count: int = 0
        self.labeled_count: int = 0
    
    def cleanup(self):
        """Remove temporary directory."""
        if self.temp_dir and os.path.exists(self.temp_dir):
            shutil.rmtree(self.temp_dir, ignore_errors=True)


def extract_and_parse_zip(zip_path: str, zip_filename: str) -> YOLODatasetInfo:
    """
    Extract ZIP and parse YOLO dataset structure.
    
    Args:
        zip_path: Path to the ZIP file on disk
        zip_filename: Original filename (for dataset name)
    
    Returns:
        YOLODatasetInfo with parsed data
    
    Raises:
        ZipProcessorError: If ZIP is invalid or missing required structure
    """
    info = YOLODatasetInfo()
    
    # Dataset name from ZIP filename (without extension)
    info.dataset_name = os.path.splitext(zip_filename)[0]
    
    # Create temp directory for extraction
    info.temp_dir = tempfile.mkdtemp(prefix="yolo_upload_")
    
    try:
        # Extract ZIP
        with zipfile.ZipFile(zip_path, 'r') as zf:
            zf.extractall(info.temp_dir)
        
        # Find images and labels folders (may be nested in a subfolder)
        images_dir = _find_folder(info.temp_dir, "images")
        labels_dir = _find_folder(info.temp_dir, "labels")
        
        if not images_dir:
            raise ZipProcessorError("ZIP must contain an 'images' folder")
        
        # Parse classes from data.yaml or classes.txt
        info.classes = _parse_classes(info.temp_dir)
        
        # Get all image files
        image_extensions = {'.jpg', '.jpeg', '.png', '.webp', '.bmp'}
        for filename in os.listdir(images_dir):
            ext = os.path.splitext(filename)[1].lower()
            if ext in image_extensions:
                info.image_files.append(os.path.join(images_dir, filename))
        
        info.image_count = len(info.image_files)
        
        # Match labels to images
        if labels_dir:
            for img_path in info.image_files:
                basename = os.path.splitext(os.path.basename(img_path))[0]
                label_path = os.path.join(labels_dir, f"{basename}.txt")
                if os.path.exists(label_path):
                    info.label_files[basename] = label_path
            
            info.labeled_count = len(info.label_files)
        
        # If no classes found but we have labels, generate class names
        if not info.classes and info.label_files:
            max_class_id = _find_max_class_id(info.label_files.values())
            info.classes = [f"class_{i}" for i in range(max_class_id + 1)]
        
        return info
        
    except zipfile.BadZipFile:
        info.cleanup()
        raise ZipProcessorError("Invalid ZIP file")
    except Exception as e:
        info.cleanup()
        raise ZipProcessorError(f"Failed to process ZIP: {str(e)}")


def _find_folder(root_dir: str, folder_name: str) -> Optional[str]:
    """Find a folder by name, handling nested structures."""
    # Check direct child
    direct = os.path.join(root_dir, folder_name)
    if os.path.isdir(direct):
        return direct
    
    # Check one level deep (for ZIPs with a root folder)
    for item in os.listdir(root_dir):
        item_path = os.path.join(root_dir, item)
        if os.path.isdir(item_path):
            nested = os.path.join(item_path, folder_name)
            if os.path.isdir(nested):
                return nested
            
            # Also check train/val subfolders
            for split in ["train", "valid", "val", "test"]:
                split_path = os.path.join(item_path, split, folder_name)
                if os.path.isdir(split_path):
                    return split_path
    
    return None


def _parse_classes(root_dir: str) -> list[str]:
    """Parse class names from data.yaml or classes.txt."""
    classes = []
    
    # Try data.yaml (YOLO format)
    yaml_paths = [
        os.path.join(root_dir, "data.yaml"),
        os.path.join(root_dir, "dataset.yaml"),
    ]
    
    # Also check one level deep
    for item in os.listdir(root_dir):
        item_path = os.path.join(root_dir, item)
        if os.path.isdir(item_path):
            yaml_paths.append(os.path.join(item_path, "data.yaml"))
            yaml_paths.append(os.path.join(item_path, "dataset.yaml"))
    
    for yaml_path in yaml_paths:
        if os.path.exists(yaml_path):
            try:
                with open(yaml_path, 'r') as f:
                    data = yaml.safe_load(f)
                if data and "names" in data:
                    names = data["names"]
                    if isinstance(names, list):
                        classes = [str(n) for n in names]
                    elif isinstance(names, dict):
                        # Handle {0: 'class0', 1: 'class1'} format
                        classes = [str(names.get(i, f"class_{i}")) for i in range(len(names))]
                    if classes:
                        return classes
            except Exception as e:
                print(f"[ZIP] Error parsing {yaml_path}: {e}")
    
    # Try classes.txt
    txt_paths = [
        os.path.join(root_dir, "classes.txt"),
    ]
    for item in os.listdir(root_dir):
        item_path = os.path.join(root_dir, item)
        if os.path.isdir(item_path):
            txt_paths.append(os.path.join(item_path, "classes.txt"))
    
    for txt_path in txt_paths:
        if os.path.exists(txt_path):
            try:
                with open(txt_path, 'r') as f:
                    classes = [line.strip() for line in f if line.strip()]
                if classes:
                    return classes
            except Exception as e:
                print(f"[ZIP] Error parsing {txt_path}: {e}")
    
    return classes


def _find_max_class_id(label_paths) -> int:
    """Find the maximum class ID used in label files."""
    max_id = -1
    for label_path in label_paths:
        try:
            with open(label_path, 'r') as f:
                for line in f:
                    parts = line.strip().split()
                    if parts:
                        class_id = int(parts[0])
                        max_id = max(max_id, class_id)
        except Exception:
            continue
    return max_id


def parse_yolo_label(label_path: str, image_width: int, image_height: int) -> list[dict]:
    """
    Parse YOLO label file to annotation format.
    
    YOLO format: class_id center_x center_y width height (all normalized 0-1)
    
    Returns list of annotations in our internal format:
    {
        "id": str,
        "class_id": int,
        "x": float (pixel),
        "y": float (pixel),
        "width": float (pixel),
        "height": float (pixel)
    }
    """
    import uuid
    annotations = []
    
    try:
        with open(label_path, 'r') as f:
            for line in f:
                parts = line.strip().split()
                if len(parts) >= 5:
                    class_id = int(parts[0])
                    cx = float(parts[1])  # center x (normalized)
                    cy = float(parts[2])  # center y (normalized)
                    w = float(parts[3])   # width (normalized)
                    h = float(parts[4])   # height (normalized)
                    
                    # Convert to pixel coordinates (top-left corner)
                    x = (cx - w / 2) * image_width
                    y = (cy - h / 2) * image_height
                    width = w * image_width
                    height = h * image_height
                    
                    annotations.append({
                        "id": str(uuid.uuid4()),
                        "class_id": class_id,
                        "x": x,
                        "y": y,
                        "width": width,
                        "height": height,
                    })
    except Exception as e:
        print(f"[ZIP] Error parsing label {label_path}: {e}")
    
    return annotations
