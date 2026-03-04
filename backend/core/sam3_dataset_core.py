"""
SAM3 Dataset Core — COCO JSON dataset generation for SAM3 fine-tuning.

Converts SAFARI annotations into COCO format for SAM3 fine-tuning.
format required by facebookresearch/sam3 training.

Key insight: Uses a configurable domain-level prompt (e.g. "animal") as noun_phrase for all
annotations. This trains SAM3 to detect a single concept, keeping inference to one SAM3 pass
regardless of class count. The classifier handles species-level identification.

Usage:
    from backend.core.sam3_dataset_core import build_sam3_coco_dataset

    train_coco, test_coco, image_mapping = build_sam3_coco_dataset(
        image_records=[...],
        project_classes=["lynx", "red_fox", "wild_boar"],
        train_split=0.8,
    )
"""

import json
import random
from pathlib import Path


def polygon_area(polygon_points: list[list[float]], img_width: int, img_height: int) -> float:
    """
    Calculate polygon area using the Shoelace formula.
    
    Args:
        polygon_points: List of [x, y] normalized points (0-1)
        img_width: Image width for denormalization
        img_height: Image height for denormalization
        
    Returns:
        Area in absolute pixels
    """
    n = len(polygon_points)
    if n < 3:
        return 0.0
    
    area = 0.0
    for i in range(n):
        x1 = polygon_points[i][0] * img_width
        y1 = polygon_points[i][1] * img_height
        x2 = polygon_points[(i + 1) % n][0] * img_width
        y2 = polygon_points[(i + 1) % n][1] * img_height
        area += x1 * y2 - x2 * y1
    
    return abs(area) / 2.0


def normalized_bbox_to_coco(
    x: float, y: float, width: float, height: float,
    img_width: int, img_height: int,
) -> list[float]:
    """
    Convert SAFARI normalized top-left bbox to COCO [x, y, w, h] absolute pixels.
    """
    return [
        x * img_width,
        y * img_height,
        width * img_width,
        height * img_height,
    ]


def mask_polygon_to_coco_segmentation(
    polygon_points: list[list[float]],
    img_width: int,
    img_height: int,
) -> list[list[float]]:
    """
    Convert SAFARI normalized mask_polygon to COCO segmentation format.
    
    SAFARI format: [[x1, y1], [x2, y2], ...] — normalized 0-1
    COCO format: [[x1, y1, x2, y2, x3, y3, ...]] — absolute pixels, flattened
    """
    flat = []
    for point in polygon_points:
        flat.append(point[0] * img_width)
        flat.append(point[1] * img_height)
    return [flat]


def build_sam3_coco_dataset(
    image_records: list[dict],
    project_classes: list[str],
    train_split: float = 0.8,
    seed: int = 42,
    prompt: str = "animal",
) -> tuple[dict, dict, dict]:
    """
    Build COCO JSON datasets from SAFARI annotated image records.
    
    Args:
        image_records: List of dicts, each containing:
            - id: str (image ID)
            - filename: str (image filename)
            - r2_path: str (R2 path for download)
            - width: int (image width in pixels)
            - height: int (image height in pixels)
            - annotations: list[dict] with {class_id, x, y, width, height, mask_polygon}
        project_classes: Ordered list of class names (index = class_id)
        train_split: Fraction for training set (default 0.8)
        seed: Random seed for reproducible splits
        prompt: SAM3 concept prompt used as noun_phrase for all annotations.
                Default "animal" — trains SAM3 to detect/segment a single domain 
                concept. Keeps inference to one SAM3 pass regardless of class count.
        
    Returns:
        Tuple of:
        - train_coco: COCO JSON dict for training split
        - test_coco: COCO JSON dict for test split  
        - image_r2_mapping: {filename: r2_path} for all images included
    """
    # Filter to only images that have annotations
    valid_records = []
    skipped_no_annotations = 0
    
    for record in image_records:
        anns = record.get("annotations", [])
        if not anns:
            skipped_no_annotations += 1
            continue
        
        valid_records.append(record)
    
    print(f"[SAM3 Dataset] {len(valid_records)} images with annotations, "
          f"skipped {skipped_no_annotations} without annotations")
    print(f"[SAM3 Dataset] Using prompt: '{prompt}' for all annotations")
    
    if not valid_records:
        raise ValueError("No images with annotations found in selected datasets")
    
    # Shuffle and split
    random.seed(seed)
    shuffled = list(valid_records)
    random.shuffle(shuffled)
    
    split_idx = max(1, int(len(shuffled) * train_split))
    train_records = shuffled[:split_idx]
    test_records = shuffled[split_idx:] if split_idx < len(shuffled) else []
    
    if not test_records:
        test_records = train_records[:1]
        print(f"[SAM3 Dataset] Warning: tiny dataset, using first train image as test")
    
    print(f"[SAM3 Dataset] Split: {len(train_records)} train, {len(test_records)} test")
    
    # Build categories
    categories = [{"id": i, "name": name} for i, name in enumerate(project_classes)]
    
    def build_coco_json(records: list[dict]) -> tuple[dict, dict]:
        images = []
        annotations = []
        image_mapping = {}
        ann_id = 1
        
        for img_idx, record in enumerate(records):
            img_id = img_idx + 1
            img_width = record["width"]
            img_height = record["height"]
            filename = record["filename"]
            
            images.append({
                "id": img_id,
                "file_name": filename,
                "width": img_width,
                "height": img_height,
            })
            
            image_mapping[filename] = record["r2_path"]
            
            for ann in record.get("annotations", []):
                class_id = ann.get("class_id", 0)
                
                coco_bbox = normalized_bbox_to_coco(
                    ann["x"], ann["y"], ann["width"], ann["height"],
                    img_width, img_height,
                )
                
                # Use mask polygon if available, otherwise derive from bbox
                mask_poly = ann.get("mask_polygon")
                if mask_poly:
                    coco_seg = mask_polygon_to_coco_segmentation(
                        mask_poly, img_width, img_height,
                    )
                    area = polygon_area(mask_poly, img_width, img_height)
                else:
                    # Derive segmentation polygon from bounding box
                    bx, by, bw, bh = coco_bbox
                    coco_seg = [[bx, by, bx + bw, by, bx + bw, by + bh, bx, by + bh]]
                    area = bw * bh
                
                annotations.append({
                    "id": ann_id,
                    "image_id": img_id,
                    "category_id": class_id,
                    "bbox": coco_bbox,
                    "segmentation": coco_seg,
                    "area": area,
                    "iscrowd": 0,
                    "noun_phrase": prompt,
                })
                ann_id += 1
            
        return {
            "images": images,
            "annotations": annotations,
            "categories": categories,
        }, image_mapping
    
    train_coco, train_mapping = build_coco_json(train_records)
    test_coco, test_mapping = build_coco_json(test_records)
    
    all_mapping = {**train_mapping, **test_mapping}
    
    print(f"[SAM3 Dataset] Train: {len(train_coco['images'])} images, "
          f"{len(train_coco['annotations'])} annotations")
    print(f"[SAM3 Dataset] Test: {len(test_coco['images'])} images, "
          f"{len(test_coco['annotations'])} annotations")
    
    return train_coco, test_coco, all_mapping


def save_coco_json(coco_dict: dict, output_path: Path) -> None:
    """Save COCO JSON to file."""
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with open(output_path, "w") as f:
        json.dump(coco_dict, f, indent=2)
    print(f"[SAM3 Dataset] Saved COCO JSON: {output_path} "
          f"({len(coco_dict.get('annotations', []))} annotations)")
