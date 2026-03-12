"""
Backfill EXIF Metadata — Populate captured_at, camera_make, camera_model, is_night_shot
for images that don't have EXIF data yet.

Usage:
    python scripts/backfill_exif.py                         # All projects
    python scripts/backfill_exif.py --project-id <uuid>     # Specific project
    python scripts/backfill_exif.py --dataset-id <uuid>     # Specific dataset
"""

import sys
import os
import argparse

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from backend.supabase_client import get_supabase
from backend.r2_storage import R2Client
from backend.exif_utils import extract_exif_metadata


def backfill_dataset(dataset_id: str, r2: R2Client, supabase) -> dict:
    """Backfill EXIF for all images in a dataset missing captured_at.
    
    Returns dict with counts: {total, updated, skipped, errors}
    """
    # Get images without EXIF data
    result = (
        supabase.table("images")
        .select("id, filename, r2_path")
        .eq("dataset_id", dataset_id)
        .is_("captured_at", "null")
        .execute()
    )
    images = result.data or []
    
    stats = {"total": len(images), "updated": 0, "skipped": 0, "errors": 0}
    
    for img in images:
        try:
            # Download image from R2
            image_bytes = r2.download_file(img["r2_path"])
            
            # Extract EXIF
            exif_meta = extract_exif_metadata(image_bytes)
            
            if not exif_meta:
                stats["skipped"] += 1
                continue
            
            # Build update dict
            update = {}
            if exif_meta.get("captured_at"):
                update["captured_at"] = exif_meta["captured_at"].isoformat()
            if exif_meta.get("camera_make"):
                update["camera_make"] = exif_meta["camera_make"]
            if exif_meta.get("camera_model"):
                update["camera_model"] = exif_meta["camera_model"]
            if exif_meta.get("is_night_shot") is not None:
                update["is_night_shot"] = exif_meta["is_night_shot"]
            
            if update:
                supabase.table("images").update(update).eq("id", img["id"]).execute()
                stats["updated"] += 1
                print(f"  ✅ {img['filename']}: {exif_meta.get('camera_model', '?')} | {exif_meta.get('captured_at', '?')} | night={exif_meta.get('is_night_shot', '?')}")
            else:
                stats["skipped"] += 1
                
        except Exception as e:
            stats["errors"] += 1
            print(f"  ❌ {img['filename']}: {e}")
    
    return stats


def main():
    parser = argparse.ArgumentParser(description="Backfill EXIF metadata for images")
    parser.add_argument("--project-id", help="Backfill specific project")
    parser.add_argument("--dataset-id", help="Backfill specific dataset")
    args = parser.parse_args()
    
    supabase = get_supabase()
    r2 = R2Client()
    
    if args.dataset_id:
        # Single dataset
        dataset = supabase.table("datasets").select("id, name").eq("id", args.dataset_id).single().execute()
        if not dataset.data:
            print(f"Dataset {args.dataset_id} not found")
            return
        print(f"\n📂 Dataset: {dataset.data['name']}")
        stats = backfill_dataset(args.dataset_id, r2, supabase)
        print(f"   Total: {stats['total']} | Updated: {stats['updated']} | Skipped: {stats['skipped']} | Errors: {stats['errors']}")
        
    elif args.project_id:
        # All datasets in a project
        datasets = (
            supabase.table("datasets")
            .select("id, name, type")
            .eq("project_id", args.project_id)
            .execute()
        )
        image_datasets = [d for d in (datasets.data or []) if d.get("type") != "video"]
        print(f"\n🔍 Project {args.project_id}: {len(image_datasets)} image dataset(s)")
        
        total_stats = {"total": 0, "updated": 0, "skipped": 0, "errors": 0}
        for ds in image_datasets:
            print(f"\n📂 Dataset: {ds['name']}")
            stats = backfill_dataset(ds["id"], r2, supabase)
            for k in total_stats:
                total_stats[k] += stats[k]
            print(f"   Total: {stats['total']} | Updated: {stats['updated']} | Skipped: {stats['skipped']} | Errors: {stats['errors']}")
        
        print(f"\n{'='*50}")
        print(f"TOTAL: {total_stats['total']} | Updated: {total_stats['updated']} | Skipped: {total_stats['skipped']} | Errors: {total_stats['errors']}")
    
    else:
        print("Please specify --project-id or --dataset-id")
        parser.print_help()


if __name__ == "__main__":
    main()
