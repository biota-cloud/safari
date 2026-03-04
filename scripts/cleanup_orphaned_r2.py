#!/usr/bin/env python3
"""
Cleanup Orphaned R2 Dataset Files

This script finds dataset folders in R2 that no longer have corresponding
database records and deletes them.

Usage:
    # Dry run (default) - shows what would be deleted
    python scripts/cleanup_orphaned_r2.py
    
    # Actually delete orphaned files
    python scripts/cleanup_orphaned_r2.py --delete
"""

import sys
import os

# Add project root to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from backend.r2_storage import R2Client
from backend.supabase_client import get_supabase


def get_all_dataset_ids_from_db() -> set[str]:
    """Get all dataset IDs that exist in the database."""
    supabase = get_supabase()
    result = supabase.table("datasets").select("id").execute()
    return {row["id"] for row in result.data} if result.data else set()


def get_dataset_ids_from_r2(r2: R2Client) -> set[str]:
    """Get all dataset IDs that have folders in R2."""
    # List all objects with 'datasets/' prefix
    paginator = r2.s3.get_paginator('list_objects_v2')
    pages = paginator.paginate(Bucket=r2.bucket, Prefix="datasets/", Delimiter="/")
    
    dataset_ids = set()
    for page in pages:
        # CommonPrefixes contains the "folders" at this level
        for prefix in page.get("CommonPrefixes", []):
            # prefix["Prefix"] looks like "datasets/{uuid}/"
            folder = prefix["Prefix"]
            # Extract the UUID
            parts = folder.strip("/").split("/")
            if len(parts) >= 2:
                dataset_ids.add(parts[1])
    
    return dataset_ids


def count_files_with_prefix(r2: R2Client, prefix: str) -> int:
    """Count files under a prefix without deleting."""
    paginator = r2.s3.get_paginator('list_objects_v2')
    pages = paginator.paginate(Bucket=r2.bucket, Prefix=prefix)
    
    count = 0
    for page in pages:
        count += len(page.get("Contents", []))
    return count


def main():
    dry_run = "--delete" not in sys.argv
    
    print("=" * 60)
    print("R2 Orphaned Dataset Cleanup Script")
    print("=" * 60)
    
    if dry_run:
        print("\n🔍 DRY RUN MODE - No files will be deleted")
        print("   Run with --delete flag to actually delete files\n")
    else:
        print("\n⚠️  DELETE MODE - Files will be permanently deleted!\n")
    
    # Initialize clients
    r2 = R2Client()
    
    # Get dataset IDs from both sources
    print("Fetching dataset IDs from database...")
    db_ids = get_all_dataset_ids_from_db()
    print(f"  Found {len(db_ids)} datasets in database")
    
    print("Fetching dataset folders from R2...")
    r2_ids = get_dataset_ids_from_r2(r2)
    print(f"  Found {len(r2_ids)} dataset folders in R2")
    
    # Find orphaned datasets (in R2 but not in DB)
    orphaned_ids = r2_ids - db_ids
    
    if not orphaned_ids:
        print("\n✅ No orphaned dataset folders found. R2 is clean!")
        return
    
    print(f"\n🗑️  Found {len(orphaned_ids)} orphaned dataset folder(s):\n")
    
    total_files = 0
    total_deleted = 0
    
    for dataset_id in sorted(orphaned_ids):
        prefix = f"datasets/{dataset_id}/"
        file_count = count_files_with_prefix(r2, prefix)
        total_files += file_count
        
        print(f"  📁 {dataset_id}")
        print(f"     Files: {file_count}")
        
        if not dry_run:
            deleted = r2.delete_files_with_prefix(prefix)
            total_deleted += deleted
            print(f"     Status: ✅ Deleted {deleted} files")
        else:
            print(f"     Status: Would delete {file_count} files")
        print()
    
    # Summary
    print("=" * 60)
    print("SUMMARY")
    print("=" * 60)
    print(f"Orphaned datasets:  {len(orphaned_ids)}")
    print(f"Total files:        {total_files}")
    
    if dry_run:
        print(f"\nTo delete these files, run:")
        print(f"  python scripts/cleanup_orphaned_r2.py --delete")
    else:
        print(f"Files deleted:      {total_deleted}")
        print("\n✅ Cleanup complete!")


if __name__ == "__main__":
    main()
