#!/usr/bin/env python3
"""
Backfill Thumbnails for Projects and Datasets

This script generates thumbnails for projects and datasets that were created
before the thumbnail functionality was added.

Logic:
- For each project without thumbnail: uses the LARGEST annotation across all datasets
- For each dataset without thumbnail: uses the SECOND LARGEST annotation (or largest if project already has one)
- This ensures distinct thumbnails for project vs dataset covers

Usage:
    # Dry run (default) - shows what would be generated
    python scripts/backfill_thumbnails.py
    
    # Actually generate thumbnails
    python scripts/backfill_thumbnails.py --generate
"""

import sys
import os

# Add project root to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import requests
from backend.r2_storage import R2Client
from backend.supabase_client import get_supabase, update_project, update_dataset
from backend.core.thumbnail_generator import generate_label_thumbnail


def get_projects_without_thumbnails() -> list[dict]:
    """Get all projects where thumbnail_r2_path is NULL."""
    supabase = get_supabase()
    result = supabase.table("projects").select("id, name").is_("thumbnail_r2_path", "null").execute()
    return result.data if result.data else []


def get_datasets_without_thumbnails() -> list[dict]:
    """Get all datasets where thumbnail_r2_path is NULL."""
    supabase = get_supabase()
    result = supabase.table("datasets").select("id, name, project_id").is_("thumbnail_r2_path", "null").execute()
    return result.data if result.data else []


def get_all_annotations_for_project(project_id: str) -> list[dict]:
    """
    Get all annotations from all images in all datasets of a project.
    Returns list of {annotation, image_id, dataset_id, r2_path, area}.
    """
    supabase = get_supabase()
    
    # Get all datasets for this project
    datasets = supabase.table("datasets").select("id").eq("project_id", project_id).execute()
    if not datasets.data:
        return []
    
    dataset_ids = [d["id"] for d in datasets.data]
    
    # Get all images with annotations from these datasets
    all_annotations = []
    
    for dataset_id in dataset_ids:
        images = supabase.table("images") \
            .select("id, r2_path, annotations") \
            .eq("dataset_id", dataset_id) \
            .not_.is_("annotations", "null") \
            .execute()
        
        if not images.data:
            continue
        
        for image in images.data:
            annotations = image.get("annotations") or []
            if not annotations:
                continue
            
            for ann in annotations:
                width = ann.get("width", 0)
                height = ann.get("height", 0)
                area = width * height
                
                if area > 0:
                    all_annotations.append({
                        "annotation": ann,
                        "image_id": image["id"],
                        "dataset_id": dataset_id,
                        "r2_path": image["r2_path"],
                        "area": area,
                    })
    
    # Sort by area descending
    all_annotations.sort(key=lambda x: x["area"], reverse=True)
    return all_annotations


def get_all_annotations_for_dataset(dataset_id: str) -> list[dict]:
    """
    Get all annotations from all images in a dataset.
    Returns list of {annotation, image_id, r2_path, area}.
    """
    supabase = get_supabase()
    
    images = supabase.table("images") \
        .select("id, r2_path, annotations") \
        .eq("dataset_id", dataset_id) \
        .not_.is_("annotations", "null") \
        .execute()
    
    if not images.data:
        return []
    
    all_annotations = []
    
    for image in images.data:
        annotations = image.get("annotations") or []
        if not annotations:
            continue
        
        for ann in annotations:
            width = ann.get("width", 0)
            height = ann.get("height", 0)
            area = width * height
            
            if area > 0:
                all_annotations.append({
                    "annotation": ann,
                    "image_id": image["id"],
                    "r2_path": image["r2_path"],
                    "area": area,
                })
    
    # Sort by area descending
    all_annotations.sort(key=lambda x: x["area"], reverse=True)
    return all_annotations


def generate_and_upload_thumbnail(
    r2: R2Client,
    annotation_data: dict,
    target_path: str,
) -> bool:
    """
    Generate thumbnail from annotation and upload to R2.
    Returns True on success.
    """
    try:
        # Get presigned URL for source image
        image_url = r2.generate_presigned_url(annotation_data["r2_path"])
        if not image_url:
            print(f"    ❌ Failed to get presigned URL for {annotation_data['r2_path']}")
            return False
        
        # Download image
        response = requests.get(image_url, timeout=30)
        if response.status_code != 200:
            print(f"    ❌ Failed to download image: HTTP {response.status_code}")
            return False
        
        image_bytes = response.content
        
        # Generate thumbnail
        thumb_bytes = generate_label_thumbnail(image_bytes, annotation_data["annotation"])
        if not thumb_bytes:
            print(f"    ❌ Failed to generate thumbnail")
            return False
        
        # Upload to R2
        r2.upload_file(thumb_bytes, target_path, content_type="image/jpeg")
        return True
        
    except Exception as e:
        print(f"    ❌ Error: {e}")
        return False


def main():
    dry_run = "--generate" not in sys.argv
    
    print("=" * 60)
    print("Thumbnail Backfill Script")
    print("=" * 60)
    
    if dry_run:
        print("\n🔍 DRY RUN MODE - No thumbnails will be generated")
        print("   Run with --generate flag to actually create thumbnails\n")
    else:
        print("\n🖼️  GENERATE MODE - Thumbnails will be created!\n")
    
    r2 = R2Client()
    
    # Track which datasets got thumbnails from project pass
    datasets_with_thumbs = set()
    
    # ==========================================================================
    # Phase 1: Projects without thumbnails
    # ==========================================================================
    
    projects = get_projects_without_thumbnails()
    print(f"📁 Found {len(projects)} project(s) without thumbnails\n")
    
    for project in projects:
        project_id = project["id"]
        project_name = project["name"]
        
        print(f"  🗂️  Project: {project_name} ({project_id[:8]}...)")
        
        # Get all annotations sorted by area
        annotations = get_all_annotations_for_project(project_id)
        
        if not annotations:
            print(f"      ⚠️  No annotations found - skipping")
            continue
        
        print(f"      Found {len(annotations)} annotation(s)")
        
        # LARGEST → Project thumbnail
        largest = annotations[0]
        print(f"      📌 Largest: area={largest['area']:.4f} from dataset {largest['dataset_id'][:8]}...")
        
        if not dry_run:
            project_thumb_path = f"projects/{project_id}/thumbnail.jpg"
            if generate_and_upload_thumbnail(r2, largest, project_thumb_path):
                update_project(project_id, thumbnail_r2_path=project_thumb_path)
                print(f"      ✅ Project thumbnail generated")
            else:
                print(f"      ❌ Failed to generate project thumbnail")
                continue
        
        # SECOND LARGEST → Dataset thumbnail (if dataset doesn't have one)
        if len(annotations) >= 2:
            second_largest = annotations[1]
            dataset_id = second_largest["dataset_id"]
            
            # Check if this dataset already has a thumbnail
            supabase = get_supabase()
            ds = supabase.table("datasets").select("thumbnail_r2_path").eq("id", dataset_id).single().execute()
            
            if ds.data and not ds.data.get("thumbnail_r2_path"):
                print(f"      📌 Second largest: area={second_largest['area']:.4f} → dataset {dataset_id[:8]}...")
                
                if not dry_run:
                    dataset_thumb_path = f"datasets/{dataset_id}/thumbnail.jpg"
                    if generate_and_upload_thumbnail(r2, second_largest, dataset_thumb_path):
                        update_dataset(dataset_id, thumbnail_r2_path=dataset_thumb_path)
                        datasets_with_thumbs.add(dataset_id)
                        print(f"      ✅ Dataset thumbnail generated")
                    else:
                        print(f"      ❌ Failed to generate dataset thumbnail")
                else:
                    datasets_with_thumbs.add(dataset_id)
        
        print()
    
    # ==========================================================================
    # Phase 2: Remaining datasets without thumbnails
    # ==========================================================================
    
    datasets = get_datasets_without_thumbnails()
    # Filter out datasets that already got thumbnails in Phase 1
    remaining_datasets = [d for d in datasets if d["id"] not in datasets_with_thumbs]
    
    print(f"\n📂 Found {len(remaining_datasets)} remaining dataset(s) without thumbnails\n")
    
    for dataset in remaining_datasets:
        dataset_id = dataset["id"]
        dataset_name = dataset["name"]
        
        print(f"  📁 Dataset: {dataset_name} ({dataset_id[:8]}...)")
        
        # Get annotations for this dataset
        annotations = get_all_annotations_for_dataset(dataset_id)
        
        if not annotations:
            print(f"      ⚠️  No annotations found - skipping")
            continue
        
        print(f"      Found {len(annotations)} annotation(s)")
        
        # Use LARGEST for dataset thumbnail
        largest = annotations[0]
        print(f"      📌 Largest: area={largest['area']:.4f}")
        
        if not dry_run:
            dataset_thumb_path = f"datasets/{dataset_id}/thumbnail.jpg"
            if generate_and_upload_thumbnail(r2, largest, dataset_thumb_path):
                update_dataset(dataset_id, thumbnail_r2_path=dataset_thumb_path)
                print(f"      ✅ Dataset thumbnail generated")
            else:
                print(f"      ❌ Failed to generate dataset thumbnail")
        
        print()
    
    # ==========================================================================
    # Summary
    # ==========================================================================
    
    print("=" * 60)
    print("SUMMARY")
    print("=" * 60)
    print(f"Projects processed:  {len(projects)}")
    print(f"Datasets processed:  {len(remaining_datasets) + len(datasets_with_thumbs)}")
    
    if dry_run:
        print(f"\nTo generate thumbnails, run:")
        print(f"  python scripts/backfill_thumbnails.py --generate")
    else:
        print("\n✅ Backfill complete!")


if __name__ == "__main__":
    main()
