#!/usr/bin/env python3
"""
Repair script to rename video label files in an exported dataset.
The bug: labels were copied with old video IDs but videos have new IDs.
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

# Source: Lince Validation dataset
source_dataset_id = '3cfeb142-f88e-408e-8f55-686b73e59573'

# Target: GEBIF test Validation dataset (the broken one)
target_dataset_id = 'b4ff2c03-f256-48d4-962c-20ae9b4ef9be'

# Get source videos
source_videos = supabase.table('videos').select('id, filename').eq('dataset_id', source_dataset_id).execute()
print(f"Source videos (Lince): {len(source_videos.data)}")

# Get target videos
target_videos = supabase.table('videos').select('id, filename').eq('dataset_id', target_dataset_id).execute()
print(f"Target videos (GEBIF): {len(target_videos.data)}")

# Build mapping by filename
source_by_name = {v['filename']: v['id'] for v in source_videos.data}
target_by_name = {v['filename']: v['id'] for v in target_videos.data}

print("\n=== Video ID Mapping (source -> target) ===")
old_to_new = {}
for name, old_id in source_by_name.items():
    if name in target_by_name:
        new_id = target_by_name[name]
        old_to_new[old_id] = new_id
        print(f"  {name}: {old_id} -> {new_id}")

# Now rename the label files
print(f"\n=== Renaming label files ===")
renamed_count = 0
for old_vid_id, new_vid_id in old_to_new.items():
    old_prefix = f"datasets/{target_dataset_id}/labels/{old_vid_id}_"
    
    response = r2.s3.list_objects_v2(Bucket=r2.bucket, Prefix=old_prefix, MaxKeys=500)
    
    for obj in response.get('Contents', []):
        old_key = obj['Key']
        frame_part = old_key.replace(old_prefix, "")
        new_key = f"datasets/{target_dataset_id}/labels/{new_vid_id}_{frame_part}"
        
        print(f"  Renaming: ...{old_key[-35:]} -> ...{new_key[-35:]}")
        r2.s3.copy_object(
            Bucket=r2.bucket,
            CopySource={'Bucket': r2.bucket, 'Key': old_key},
            Key=new_key
        )
        r2.delete_file(old_key)
        renamed_count += 1

print(f"\n=== Done! Renamed {renamed_count} label files ===")
