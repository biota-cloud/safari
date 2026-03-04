#!/usr/bin/env python3
"""
Repair script to rename image label files in an exported dataset.
The bug: labels were copied with old image IDs but images have new IDs.
Maps by filename between source and target datasets.
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from dotenv import load_dotenv
load_dotenv()

from backend.supabase_client import get_supabase
from backend.r2_storage import R2Client

supabase = get_supabase()
r2 = R2Client()

# Source and target dataset mappings (by matching dataset names)
# GBIF (source) -> GBIF 1 0-50 and GBIF 2 50-100 (targets)
source_dataset_id = '7fab141d-9c1f-49b0-b967-105d19ec5d95'  # Lince GBIF
target_datasets = [
    ('c95c13cf-24f7-4597-8f97-bebdae9c5d57', 'GBIF 1 0-50'),
    ('f75b53f1-5455-4f6d-84af-080b927e24b1', 'GBIF 2 50-100'),
]

# Get source images
source_images = supabase.table('images').select('id, filename').eq('dataset_id', source_dataset_id).execute()
source_by_name = {img['filename']: img['id'] for img in source_images.data or []}
print(f"Source images (Lince GBIF): {len(source_by_name)}")

# Process each target dataset
for target_dataset_id, target_name in target_datasets:
    print(f"\n=== Processing {target_name} ({target_dataset_id}) ===")
    
    # Get target images
    target_images = supabase.table('images').select('id, filename').eq('dataset_id', target_dataset_id).execute()
    target_by_name = {img['filename']: img['id'] for img in target_images.data or []}
    print(f"Target images: {len(target_by_name)}")
    
    # Build old->new ID mapping by filename
    renamed_count = 0
    for filename, new_id in target_by_name.items():
        old_id = source_by_name.get(filename)
        if not old_id:
            continue
        
        if old_id == new_id:
            continue  # Same ID, no rename needed
        
        # Check if old label exists in target dataset
        old_label_path = f"datasets/{target_dataset_id}/labels/{old_id}.txt"
        new_label_path = f"datasets/{target_dataset_id}/labels/{new_id}.txt"
        
        try:
            # Check if old label exists
            r2.s3.head_object(Bucket=r2.bucket, Key=old_label_path)
            
            # Copy to new path
            r2.s3.copy_object(
                Bucket=r2.bucket,
                CopySource={'Bucket': r2.bucket, 'Key': old_label_path},
                Key=new_label_path
            )
            # Delete old
            r2.delete_file(old_label_path)
            renamed_count += 1
            if renamed_count <= 5:
                print(f"  Renamed: {old_id[:8]}... -> {new_id[:8]}...")
        except Exception as e:
            # Label doesn't exist (unlabeled image) or already renamed
            pass
    
    print(f"  Renamed {renamed_count} labels")

print("\n=== Done! ===")
