#!/usr/bin/env python3
"""
Clear all annotations from keyframes in a dataset.

This script clears the annotations JSONB column and resets annotation_count
for all keyframes in a specified dataset. Keyframes themselves are preserved.

Usage:
    python scripts/clear_dataset_annotations.py <dataset_id>
    python scripts/clear_dataset_annotations.py --all  # Clear ALL datasets (dangerous!)
"""

import sys
import os

# Add project root to path for imports
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from dotenv import load_dotenv
load_dotenv()

from backend.supabase_client import get_supabase, get_dataset_videos


def clear_dataset_annotations(dataset_id: str, dry_run: bool = False):
    """
    Clear all annotations from keyframes in a dataset.
    
    Args:
        dataset_id: UUID of the dataset to clear
        dry_run: If True, just print what would be done
    """
    supabase = get_supabase()
    
    # Get all videos in this dataset
    videos = get_dataset_videos(dataset_id)
    if not videos:
        print(f"No videos found in dataset {dataset_id}")
        return 0
    
    video_ids = [v["id"] for v in videos]
    print(f"Found {len(videos)} videos in dataset")
    
    # Get count of keyframes to be affected
    count_result = (
        supabase.table("keyframes")
        .select("id", count="exact")
        .in_("video_id", video_ids)
        .execute()
    )
    keyframe_count = count_result.count or 0
    print(f"Found {keyframe_count} keyframes to clear")
    
    if dry_run:
        print("DRY RUN - No changes made")
        return keyframe_count
    
    # Clear annotations and annotation_count in a single query
    result = (
        supabase.table("keyframes")
        .update({"annotations": None, "annotation_count": 0})
        .in_("video_id", video_ids)
        .execute()
    )
    
    cleared = len(result.data) if result.data else 0
    print(f"Cleared annotations from {cleared} keyframes")
    
    return cleared


def clear_all_datasets(dry_run: bool = False):
    """Clear annotations from ALL datasets (use with caution!)."""
    supabase = get_supabase()
    
    # Get all video datasets
    result = supabase.table("datasets").select("id, name").eq("type", "video").execute()
    datasets = result.data or []
    
    print(f"Found {len(datasets)} video datasets")
    
    total_cleared = 0
    for ds in datasets:
        print(f"\n--- Dataset: {ds['name']} ({ds['id']}) ---")
        cleared = clear_dataset_annotations(ds["id"], dry_run=dry_run)
        total_cleared += cleared
    
    print(f"\n=== Total: Cleared {total_cleared} keyframes across {len(datasets)} datasets ===")
    return total_cleared


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print(__doc__)
        sys.exit(1)
    
    arg = sys.argv[1]
    dry_run = "--dry-run" in sys.argv
    
    if arg == "--all":
        confirm = input("WARNING: This will clear ALL annotations in ALL datasets! Type 'YES' to confirm: ")
        if confirm != "YES":
            print("Aborted")
            sys.exit(1)
        clear_all_datasets(dry_run=dry_run)
    else:
        # Assume it's a dataset ID
        dataset_id = arg
        clear_dataset_annotations(dataset_id, dry_run=dry_run)
