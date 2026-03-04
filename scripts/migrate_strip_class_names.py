#!/usr/bin/env python3
"""
Migration Script: Strip class_name from Annotations

Part of Phase E Tech Debt Cleanup. This script removes the redundant 
class_name field from all annotations in Supabase. After migration,
class_name is resolved at display time from project_classes[class_id].

Usage:
    python scripts/migrate_strip_class_names.py --dry-run   # Preview changes
    python scripts/migrate_strip_class_names.py              # Execute migration

Safety:
    - Use --dry-run first to see what would be changed
    - Script is idempotent (safe to run multiple times)
    - Progress is logged for each batch
"""

import argparse
import sys
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from backend.supabase_client import get_supabase


def strip_class_names_from_dict(annotations: list[dict]) -> tuple[list[dict], bool]:
    """
    Remove class_name from each annotation dict.
    
    Returns:
        (stripped_annotations, was_modified)
    """
    if not annotations:
        return [], False
    
    modified = False
    stripped = []
    
    for ann in annotations:
        if "class_name" in ann:
            new_ann = {k: v for k, v in ann.items() if k != "class_name"}
            stripped.append(new_ann)
            modified = True
        else:
            stripped.append(ann)
    
    return stripped, modified


def migrate_images(supabase, dry_run: bool) -> int:
    """Migrate all image annotations. Returns count of updated records."""
    print("\n📸 Migrating images...")
    
    result = supabase.table("images").select("id, annotations").execute()
    images = result.data or []
    
    updated_count = 0
    
    for i, img in enumerate(images):
        annotations = img.get("annotations") or []
        stripped, modified = strip_class_names_from_dict(annotations)
        
        if modified:
            if not dry_run:
                supabase.table("images").update({
                    "annotations": stripped
                }).eq("id", img["id"]).execute()
            updated_count += 1
        
        # Progress every 100 images
        if (i + 1) % 100 == 0:
            print(f"  Processed {i + 1}/{len(images)} images...")
    
    action = "Would update" if dry_run else "Updated"
    print(f"  {action} {updated_count}/{len(images)} images")
    return updated_count


def migrate_keyframes(supabase, dry_run: bool) -> int:
    """Migrate all keyframe annotations. Returns count of updated records."""
    print("\n🎬 Migrating keyframes...")
    
    result = supabase.table("keyframes").select("id, annotations").execute()
    keyframes = result.data or []
    
    updated_count = 0
    
    for i, kf in enumerate(keyframes):
        annotations = kf.get("annotations") or []
        stripped, modified = strip_class_names_from_dict(annotations)
        
        if modified:
            if not dry_run:
                supabase.table("keyframes").update({
                    "annotations": stripped
                }).eq("id", kf["id"]).execute()
            updated_count += 1
        
        # Progress every 100 keyframes
        if (i + 1) % 100 == 0:
            print(f"  Processed {i + 1}/{len(keyframes)} keyframes...")
    
    action = "Would update" if dry_run else "Updated"
    print(f"  {action} {updated_count}/{len(keyframes)} keyframes")
    return updated_count


def main():
    parser = argparse.ArgumentParser(
        description="Strip class_name from all annotations (Phase E migration)"
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Preview changes without updating database"
    )
    args = parser.parse_args()
    
    if args.dry_run:
        print("🔍 DRY RUN MODE — No changes will be made\n")
    else:
        print("⚡ LIVE MODE — Database will be updated\n")
        response = input("Are you sure you want to proceed? (yes/no): ")
        if response.lower() != "yes":
            print("Aborted.")
            return
    
    supabase = get_supabase()
    
    images_updated = migrate_images(supabase, args.dry_run)
    keyframes_updated = migrate_keyframes(supabase, args.dry_run)
    
    total = images_updated + keyframes_updated
    
    print(f"\n{'=' * 50}")
    if args.dry_run:
        print(f"🔍 DRY RUN COMPLETE: {total} records would be updated")
        print("Run without --dry-run to apply changes.")
    else:
        print(f"✅ MIGRATION COMPLETE: {total} records updated")
    print(f"{'=' * 50}")


if __name__ == "__main__":
    main()
