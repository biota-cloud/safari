"""
Migration script to copy annotations from R2 to Supabase JSONB column.
Run once after adding annotations column to keyframes table.

This script:
1. Finds all keyframes that don't have annotations in Supabase yet (NULL)
2. Loads their annotations from R2 YOLO files
3. Parses the YOLO format to JSON
4. Saves to Supabase annotations column

Usage:
    python scripts/migrate_annotations_to_supabase.py
"""

import sys
from pathlib import Path

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from backend.supabase_client import get_supabase, update_keyframe
from backend.r2_storage import R2Client

def parse_yolo_line(line: str):
    """Parse a single YOLO format line into annotation dict."""
    parts = line.strip().split()
    if len(parts) < 5:
        return None
    
    return {
        "id": f"anno_{parts[0]}_{parts[1]}_{parts[2]}",  # Generate consistent ID
        "class_id": int(parts[0]),
        "x": float(parts[1]),
        "y": float(parts[2]),
        "width": float(parts[3]),
        "height": float(parts[4])
    }

def migrate_keyframe_annotations():
    """Migrate all keyframe annotations from R2 to Supabase."""
    
    supabase = get_supabase()
    r2 = R2Client()
    
    # Get all keyframes that don't have annotations yet
    result = supabase.table("keyframes")\
        .select("id, video_id, frame_number")\
        .is_("annotations", "null")\
        .execute()
    
    keyframes = result.data
    total = len(keyframes)
    
    print(f"Found {total} keyframes to migrate")
    
    migrated = 0
    failed = 0
    skipped = 0
    
    for idx, kf in enumerate(keyframes, 1):
        try:
            # Get dataset_id from video
            video = supabase.table("videos")\
                .select("dataset_id")\
                .eq("id", kf["video_id"])\
                .single()\
                .execute()
            
            dataset_id = video.data["dataset_id"]
            
            # Construct R2 label path
            label_path = f"datasets/{dataset_id}/labels/{kf['video_id']}_f{kf['frame_number']}.txt"
            
            # Check if R2 file exists
            if r2.file_exists(label_path):
                # Download and parse
                content = r2.download_file(label_path).decode('utf-8')
                
                # Parse YOLO format to annotation list
                annotations = []
                for line in content.strip().split('\n'):
                    if line.strip():
                        ann = parse_yolo_line(line)
                        if ann:
                            annotations.append(ann)
                
                # Update Supabase
                update_keyframe(kf["id"], annotations=annotations, annotation_count=len(annotations))
                
                migrated += 1
                print(f"[{idx}/{total}] ✓ Migrated {len(annotations)} annotations for keyframe {kf['id'][:8]} (frame {kf['frame_number']})")
            else:
                # No annotations, set empty array
                update_keyframe(kf["id"], annotations=[], annotation_count=0)
                skipped += 1
                if idx % 100 == 0:  # Only log every 100 to reduce noise
                    print(f"[{idx}/{total}] - No annotations for keyframe {kf['id'][:8]}")
                
        except Exception as e:
            failed += 1
            print(f"[{idx}/{total}] ✗ ERROR for keyframe {kf['id'][:8]}: {e}")
    
    print(f"\n{'='*60}")
    print(f"Migration complete!")
    print(f"{'='*60}")
    print(f"✓ Migrated with annotations: {migrated}")
    print(f"- Skipped (no annotations):  {skipped}")
    print(f"✗ Failed:                    {failed}")
    print(f"{'='*60}")

if __name__ == "__main__":
    print("Starting annotation migration from R2 to Supabase...")
    print("This may take a while depending on the number of keyframes.\n")
    migrate_keyframe_annotations()
