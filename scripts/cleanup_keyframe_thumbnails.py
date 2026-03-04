#!/usr/bin/env python3
"""
R2 Cleanup Script — Remove orphaned keyframe thumbnails from R2 storage.

Since we've removed keyframe thumbnail functionality, existing thumbnails in R2 are 
orphaned and can be safely deleted. This script lists and optionally deletes them.

Usage:
    # Dry run - just list what would be deleted
    python scripts/cleanup_keyframe_thumbnails.py --dry-run
    
    # Actually delete the files
    python scripts/cleanup_keyframe_thumbnails.py --delete
"""

import argparse
import sys
from pathlib import Path

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

from backend.r2_storage import R2Client
from backend.supabase_client import get_supabase


def list_orphaned_keyframe_thumbnails() -> list[str]:
    """Find all keyframe thumbnail paths in R2 storage.
    
    Orphaned thumbnails are in paths like:
    - datasets/{dataset_id}/keyframes/{video_id}_f{frame}.jpg
    
    Returns:
        List of R2 paths to orphaned thumbnails
    """
    r2 = R2Client()
    
    # Get all datasets
    supabase = get_supabase()
    datasets = supabase.table("datasets").select("id").execute()
    
    orphaned_paths = []
    
    for dataset in datasets.data:
        dataset_id = dataset["id"]
        prefix = f"datasets/{dataset_id}/keyframes/"
        
        print(f"\n[Scanning] {prefix}")
        
        try:
            # List all files with this prefix
            files = r2.list_files(prefix)
            for key in files:
                if key.endswith(".jpg") or key.endswith(".jpeg"):
                    orphaned_paths.append(key)
                    print(f"  Found: {key}")
        except Exception as e:
            print(f"  Error listing: {e}")
    
    return orphaned_paths


def delete_keyframe_thumbnails(paths: list[str], dry_run: bool = True) -> int:
    """Delete orphaned keyframe thumbnails from R2.
    
    Args:
        paths: List of R2 paths to delete
        dry_run: If True, just print what would be deleted
        
    Returns:
        Number of files deleted (or would be deleted in dry run)
    """
    if not paths:
        print("\n[Info] No orphaned keyframe thumbnails found.")
        return 0
    
    r2 = R2Client()
    deleted_count = 0
    
    print(f"\n{'[DRY RUN] Would delete' if dry_run else '[Deleting]'} {len(paths)} files:")
    
    for path in paths:
        if dry_run:
            print(f"  Would delete: {path}")
            deleted_count += 1
        else:
            try:
                r2.delete_file(path)
                print(f"  Deleted: {path}")
                deleted_count += 1
            except Exception as e:
                print(f"  Error deleting {path}: {e}")
    
    return deleted_count


def main():
    parser = argparse.ArgumentParser(
        description="Clean up orphaned keyframe thumbnails from R2 storage."
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="List files that would be deleted without actually deleting them"
    )
    parser.add_argument(
        "--delete",
        action="store_true", 
        help="Actually delete the orphaned thumbnails"
    )
    
    args = parser.parse_args()
    
    if not args.dry_run and not args.delete:
        print("Error: Must specify either --dry-run or --delete")
        parser.print_help()
        sys.exit(1)
    
    if args.dry_run and args.delete:
        print("Error: Cannot specify both --dry-run and --delete")
        sys.exit(1)
    
    print("=" * 60)
    print("R2 Keyframe Thumbnail Cleanup")
    print("=" * 60)
    
    # Find orphaned thumbnails
    print("\n[Phase 1] Scanning for orphaned keyframe thumbnails...")
    paths = list_orphaned_keyframe_thumbnails()
    
    # Delete or show what would be deleted
    print(f"\n[Phase 2] {'Dry run' if args.dry_run else 'Cleanup'}...")
    deleted = delete_keyframe_thumbnails(paths, dry_run=args.dry_run)
    
    # Summary
    print("\n" + "=" * 60)
    print(f"Summary: {'Would delete' if args.dry_run else 'Deleted'} {deleted} files")
    if args.dry_run and deleted > 0:
        print("\nTo actually delete these files, run with --delete flag")
    print("=" * 60)


if __name__ == "__main__":
    main()
