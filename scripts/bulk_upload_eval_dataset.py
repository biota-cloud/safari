#!/usr/bin/env python3
"""
Bulk Upload Evaluation Dataset — Reusable CLI script.

Uploads YOLO-labeled images to R2 + Supabase as a ground truth
evaluation dataset, with class filtering, dedup, and parallel uploads.

Usage:
    .venv/bin/python scripts/bulk_upload_eval_dataset.py \
        --images-dir "/Volumes/SSD Miguel/BIOTA/SAFArI/Img" \
        --labels-dir "/Volumes/SSD Miguel/BIOTA/SAFArI/labels" \
        --project-id b26d12d1-0511-4ae4-a74d-c3e0460b8308 \
        --limit 30 --dry-run
"""

import argparse
import os
import sys
import uuid
import random
import io
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor, as_completed

from PIL import Image

# Ensure project root is in path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from backend.supabase_client import get_supabase, create_dataset
from backend.r2_storage import R2Client

THUMBNAIL_MAX_SIZE = 200  # px, longest edge

# =============================================================================
# CLASS MAPPING CONFIG
# =============================================================================

# Full 23-class GT index → class name
GT_CLASSES = [
    'Vaca', 'Cao', 'Lobo', 'Cabra', 'Corco', 'Burro', 'Cavalo', 'Ourico',
    'Gato', 'Gato_selvagem', 'Geneta', 'Sacarabos', 'Lebre', 'Lince_iberico',
    'Fuinha', 'Texugo', 'Doninha', 'Coelho', 'Ovelha', 'Esquilo', 'Javali',
    'Raposa', 'Lontra',
]

# Project Lobo class list (index = class_id in project)
PROJECT_CLASSES = ["Lobo", "Javali", "Corço", "Cao"]

# Mapping: GT class index → project class index
# GT: Cao=1, Lobo=2, Corco=4, Javali=20
# Project: Lobo=0, Javali=1, Corço=2, Cao=3
GT_TO_PROJECT = {
    1: 3,   # Cao → project index 3
    2: 0,   # Lobo → project index 0
    4: 2,   # Corco → Corço, project index 2
    20: 1,  # Javali → project index 1
}

TARGET_GT_INDICES = set(GT_TO_PROJECT.keys())


# =============================================================================
# STEP 1: SCAN & FILTER LABELS
# =============================================================================

def scan_labels(labels_dir: str) -> dict[str, list[dict]]:
    """
    Read all YOLO label files and return only those with target classes.
    Strips non-target annotations and remaps class IDs.

    Returns:
        Dict mapping image stem → list of remapped annotations.
        Annotations use SAFARI format: {x, y, width, height, class_id, id}
    """
    results = {}
    skipped = 0

    label_files = [f for f in os.listdir(labels_dir) if f.endswith('.txt')]
    print(f"  Scanning {len(label_files)} label files...")

    for label_file in label_files:
        filepath = os.path.join(labels_dir, label_file)
        stem = os.path.splitext(label_file)[0]
        annotations = []

        with open(filepath) as f:
            for line in f:
                parts = line.strip().split()
                if len(parts) < 5:
                    continue
                gt_class_id = int(parts[0])
                if gt_class_id not in TARGET_GT_INDICES:
                    continue  # Strip non-target classes

                cx, cy, w, h = float(parts[1]), float(parts[2]), float(parts[3]), float(parts[4])

                # Convert YOLO center format (cx, cy, w, h) → app top-left format (x, y, w, h)
                annotations.append({
                    "x": round(cx - w / 2, 6),
                    "y": round(cy - h / 2, 6),
                    "width": round(w, 6),
                    "height": round(h, 6),
                    "class_id": GT_TO_PROJECT[gt_class_id],
                    "id": str(uuid.uuid4()),
                })

        if annotations:
            results[stem] = annotations
        else:
            skipped += 1

    print(f"  Found {len(results)} images with target classes ({skipped} skipped)")
    return results


# =============================================================================
# STEP 2: DEDUPLICATE AGAINST TRAINING DATA
# =============================================================================

def get_existing_filenames(project_id: str) -> set[str]:
    """Get all filenames already in any dataset for this project."""
    supabase = get_supabase()

    datasets = (
        supabase.table("datasets")
        .select("id")
        .eq("project_id", project_id)
        .execute()
    )
    if not datasets.data:
        return set()

    existing = set()
    for d in datasets.data:
        images = (
            supabase.table("images")
            .select("filename")
            .eq("dataset_id", d["id"])
            .execute()
        )
        for img in images.data or []:
            existing.add(img["filename"])

    return existing


def deduplicate(candidates: dict[str, list[dict]], project_id: str) -> dict[str, list[dict]]:
    """Remove images that are already in training datasets."""
    existing = get_existing_filenames(project_id)
    before = len(candidates)

    deduped = {}
    for stem, annotations in candidates.items():
        # Check common extensions
        if f"{stem}.JPG" in existing or f"{stem}.jpg" in existing or f"{stem}.png" in existing:
            continue
        deduped[stem] = annotations

    removed = before - len(deduped)
    print(f"  Removed {removed} images (already in training datasets)")
    print(f"  Pool: {len(deduped)} images")
    return deduped


# =============================================================================
# STEP 3: RANDOM SAMPLING (PER CLASS, MULTI-POOL)
# =============================================================================

def sample_per_class(candidates: dict[str, list[dict]], limit: int) -> dict[str, list[dict]]:
    """
    Sample up to `limit` images per class.
    An image can appear in multiple class pools.
    """
    # Build per-class pools
    class_pools: dict[int, list[str]] = defaultdict(list)
    for stem, annotations in candidates.items():
        classes_in_image = set(a["class_id"] for a in annotations)
        for cls_id in classes_in_image:
            class_pools[cls_id].append(stem)

    # Sample from each pool
    selected_stems = set()
    for cls_id in sorted(class_pools.keys()):
        pool = class_pools[cls_id]
        cls_name = PROJECT_CLASSES[cls_id]
        n_available = len(pool)
        n_sample = min(limit, n_available)
        sampled = random.sample(pool, n_sample)
        selected_stems.update(sampled)
        print(f"  {cls_name}: {n_sample} / {n_available} available")

    # Return only selected stems with their annotations
    result = {stem: candidates[stem] for stem in selected_stems}
    print(f"  Total unique images: {len(result)}")
    return result


# =============================================================================
# STEP 4: PARALLEL UPLOAD TO R2
# =============================================================================

def upload_images(
    selected: dict[str, list[dict]],
    images_dir: str,
    dataset_id: str,
    workers: int = 8,
    dry_run: bool = False,
) -> list[dict]:
    """
    Upload images to R2 in parallel. Returns list of image records for Supabase.
    """
    r2_client = R2Client() if not dry_run else None
    records = []
    stems = list(selected.keys())

    def upload_one(stem: str) -> dict | None:
        """Upload a single image + thumbnail and return its record."""
        # Find the actual file (try .JPG, .jpg, .png)
        for ext in [".JPG", ".jpg", ".png", ".jpeg"]:
            filepath = os.path.join(images_dir, f"{stem}{ext}")
            if os.path.exists(filepath):
                break
        else:
            print(f"  [WARN] Image file not found for: {stem}")
            return None

        image_uuid = str(uuid.uuid4())
        r2_path = f"datasets/{dataset_id}/images/{image_uuid}.jpg"
        thumb_r2_path = f"datasets/{dataset_id}/thumbnails/{image_uuid}.jpg"

        if not dry_run:
            with open(filepath, "rb") as f:
                image_bytes = f.read()

            # Upload full image
            r2_client.upload_file(image_bytes, r2_path, content_type="image/jpeg")

            # Generate and upload thumbnail
            try:
                img = Image.open(io.BytesIO(image_bytes))
                img.thumbnail((THUMBNAIL_MAX_SIZE, THUMBNAIL_MAX_SIZE), Image.LANCZOS)
                thumb_buf = io.BytesIO()
                img.save(thumb_buf, format="JPEG", quality=80)
                r2_client.upload_file(thumb_buf.getvalue(), thumb_r2_path, content_type="image/jpeg")
            except Exception as thumb_err:
                print(f"  [WARN] Thumbnail failed for {stem}: {thumb_err}")

        annotations = selected[stem]
        return {
            "filename": f"{stem}{ext}",
            "r2_path": r2_path,
            "annotations": annotations,
            "annotation_count": len(annotations),
            "labeled": True,
        }

    if dry_run:
        for stem in stems:
            rec = upload_one(stem)
            if rec:
                records.append(rec)
        return records

    # Parallel upload
    completed = 0
    total = len(stems)
    with ThreadPoolExecutor(max_workers=workers) as executor:
        futures = {executor.submit(upload_one, stem): stem for stem in stems}
        for future in as_completed(futures):
            result = future.result()
            if result:
                records.append(result)
            completed += 1
            if completed % 20 == 0 or completed == total:
                print(f"  [{completed}/{total}] uploaded")

    return records


# =============================================================================
# STEP 5: INSERT METADATA INTO SUPABASE
# =============================================================================

def insert_metadata(records: list[dict], dataset_id: str, dry_run: bool = False) -> int:
    """Insert image records into Supabase in batches."""
    if dry_run:
        print(f"  [DRY RUN] Would insert {len(records)} image records")
        return len(records)

    supabase = get_supabase()
    batch_size = 100
    inserted = 0

    for i in range(0, len(records), batch_size):
        batch = records[i:i + batch_size]
        db_records = [
            {
                "dataset_id": dataset_id,
                "filename": r["filename"],
                "r2_path": r["r2_path"],
                "annotations": r["annotations"],
                "annotation_count": r["annotation_count"],
                "labeled": True,
            }
            for r in batch
        ]
        supabase.table("images").insert(db_records).execute()
        inserted += len(batch)
        print(f"  Inserted batch {i // batch_size + 1} ({inserted}/{len(records)})")

    return inserted


# =============================================================================
# MAIN
# =============================================================================

def main():
    parser = argparse.ArgumentParser(description="Bulk upload evaluation dataset to SAFARI")
    parser.add_argument("--images-dir", required=True, help="Path to images folder")
    parser.add_argument("--labels-dir", required=True, help="Path to YOLO labels folder")
    parser.add_argument("--project-id", required=True, help="Supabase project UUID")
    parser.add_argument("--limit", type=int, default=500, help="Max images per class (default: 500)")
    parser.add_argument("--workers", type=int, default=8, help="Parallel upload workers (default: 8)")
    parser.add_argument("--dry-run", action="store_true", help="Preview only, no uploads")
    parser.add_argument("--dataset-name", default="Evaluation GT", help="Name for the new dataset")
    parser.add_argument("--seed", type=int, default=42, help="Random seed for reproducibility")
    args = parser.parse_args()

    random.seed(args.seed)

    if args.dry_run:
        print("=" * 60)
        print("  DRY RUN — No uploads will be performed")
        print("=" * 60)

    # ----- Step 1: Scan -----
    print(f"\n[1/5] Scanning labels in {args.labels_dir}...")
    candidates = scan_labels(args.labels_dir)
    if not candidates:
        print("  No images with target classes found. Exiting.")
        sys.exit(1)

    # ----- Step 2: Dedup -----
    print(f"\n[2/5] Deduplicating against training data...")
    candidates = deduplicate(candidates, args.project_id)
    if not candidates:
        print("  All images already in training. Exiting.")
        sys.exit(1)

    # ----- Step 3: Sample -----
    print(f"\n[3/5] Sampling {args.limit} per class...")
    selected = sample_per_class(candidates, args.limit)
    if not selected:
        print("  No images selected. Exiting.")
        sys.exit(1)

    # ----- Step 4: Create dataset + Upload -----
    print(f"\n[4/5] Creating dataset and uploading to R2 ({args.workers} workers)...")
    if args.dry_run:
        dataset_id = "dry-run-dataset-id"
        print(f"  [DRY RUN] Would create dataset '{args.dataset_name}'")
    else:
        dataset = create_dataset(
            project_id=args.project_id,
            name=args.dataset_name,
            type="image",
            usage_tag="evaluation",
        )
        if not dataset:
            print("  Failed to create dataset. Exiting.")
            sys.exit(1)
        dataset_id = dataset["id"]
        print(f"  Created dataset '{args.dataset_name}' (id={dataset_id})")

    records = upload_images(
        selected=selected,
        images_dir=args.images_dir,
        dataset_id=dataset_id,
        workers=args.workers,
        dry_run=args.dry_run,
    )

    # ----- Step 5: Insert metadata -----
    print(f"\n[5/5] Inserting metadata...")
    count = insert_metadata(records, dataset_id, dry_run=args.dry_run)

    # ----- Summary -----
    print(f"\n{'=' * 60}")
    print(f"  {'DRY RUN ' if args.dry_run else ''}COMPLETE ✅")
    print(f"  Dataset: {args.dataset_name} ({dataset_id})")
    print(f"  Images uploaded: {count}")
    print(f"  Annotations per class:")
    class_counts = defaultdict(int)
    for rec in records:
        for ann in rec["annotations"]:
            class_counts[ann["class_id"]] += 1
    for cls_id in sorted(class_counts.keys()):
        print(f"    {PROJECT_CLASSES[cls_id]}: {class_counts[cls_id]}")
    print(f"{'=' * 60}")


if __name__ == "__main__":
    main()
