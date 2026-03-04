
import os
import sys
import asyncio

# Ensure project root is in path
sys.path.append(os.path.abspath(os.path.dirname(os.path.dirname(__file__))))

from backend.supabase_client import get_supabase
from backend.r2_storage import R2Client

def cleanup_orphaned_files():
    print("Starting cleanup of orphaned R2 files...")
    
    # 1. Fetch all valid IDs from Database
    supabase = get_supabase()
    
    print("Fetching valid projects...")
    p_result = supabase.table("projects").select("id").execute()
    valid_project_ids = {p["id"] for p in p_result.data}
    print(f"Found {len(valid_project_ids)} valid projects.")
    
    print("Fetching valid datasets...")
    d_result = supabase.table("datasets").select("id").execute()
    valid_dataset_ids = {d["id"] for d in d_result.data}
    print(f"Found {len(valid_dataset_ids)} valid datasets.")
    
    # 2. List all files in R2
    r2 = R2Client()
    print("Listing all files in R2...")
    # Note: list_files returns a list of keys. If bucket is huge, this might need pagination,
    # but for now we rely on the implementation or assume manageable size.
    # The current R2Client.list_files uses list_objects_v2 but might not handle pagination for EVERYTHING 
    # if it exceeds 1000 without a loop in list_files itself. 
    # Let's check R2Client.list_files implementation details... 
    # It returns [obj['Key'] for obj in response['Contents']], no loop for continuation token.
    # So it only returns first 1000. 
    # I should use paginator here directly or update R2Client.list_files. 
    # For this script, I'll use boto3 direct access via r2.s3 to ensure I get EVERYTHING.
    
    paginator = r2.s3.get_paginator('list_objects_v2')
    pages = paginator.paginate(Bucket=r2.bucket)
    
    all_keys = []
    for page in pages:
        if 'Contents' in page:
            all_keys.extend([obj['Key'] for obj in page['Contents']])
            
    print(f"Found {len(all_keys)} total files in R2.")
    
    # 3. Identify Orphans
    orphaned_keys = []
    
    for key in all_keys:
        # Check Project Orphans: projects/{project_id}/...
        if key.startswith("projects/"):
            try:
                # projects/<id>/...
                parts = key.split("/")
                if len(parts) >= 2:
                    p_id = parts[1]
                    if p_id not in valid_project_ids:
                        orphaned_keys.append(key)
            except Exception:
                pass
                
        # Check Dataset Orphans: datasets/{dataset_id}/...
        elif key.startswith("datasets/"):
            try:
                # datasets/<id>/...
                parts = key.split("/")
                if len(parts) >= 2:
                    d_id = parts[1]
                    if d_id not in valid_dataset_ids:
                        orphaned_keys.append(key)
            except Exception:
                pass
    
    print(f"Found {len(orphaned_keys)} orphaned files.")
    
    if not orphaned_keys:
        print("No orphaned files found.")
        return

    # 4. Delete Orphans
    print("Deleting orphaned files...")
    
    # Delete in batches
    deleted_count = 0
    batch_size = 1000
    
    for i in range(0, len(orphaned_keys), batch_size):
        batch = orphaned_keys[i:i+batch_size]
        objects = [{'Key': k} for k in batch]
        
        r2.s3.delete_objects(
            Bucket=r2.bucket,
            Delete={'Objects': objects}
        )
        deleted_count += len(batch)
        print(f"Deleted batch {i // batch_size + 1}: {len(batch)} files")
        
    print(f"Successfully deleted {deleted_count} orphaned files.")

if __name__ == "__main__":
    cleanup_orphaned_files()
