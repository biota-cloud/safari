"""
Annotation Service — Centralized annotation access and mutation layer.

Provides a unified interface for:
- Reading annotations from images and keyframes
- Writing annotations with dual-storage (Supabase JSONB + R2 YOLO .txt)
- Computing class statistics across datasets
- Class rename and delete operations

This service consolidates annotation logic previously scattered across
supabase_client.py and state files.
"""

from typing import Generator, Literal

# Type aliases
Annotation = dict  # {id, class_id, class_name, x, y, width, height}
AnnotationMap = dict[str, list[Annotation]]  # item_id -> annotations
ItemType = Literal["image", "keyframe"]


# =============================================================================
# READ OPERATIONS
# =============================================================================


def get_annotations(
    item_id: str,
    item_type: ItemType,
    project_classes: list[str] = None
) -> list[Annotation]:
    """
    Retrieve annotations for a single image or keyframe.
    
    Args:
        item_id: UUID of the image or keyframe
        item_type: "image" or "keyframe"
        project_classes: Optional. If provided, resolves class_name from 
                        project_classes[class_id]. Required for new annotations
                        that don't have class_name stored.
        
    Returns:
        List of annotation dicts, or empty list if none found
    """
    from backend.supabase_client import get_supabase
    
    table = "images" if item_type == "image" else "keyframes"
    
    try:
        supabase = get_supabase()
        result = (
            supabase.table(table)
            .select("annotations")
            .eq("id", item_id)
            .single()
            .execute()
        )
        
        if result.data:
            annotations = result.data.get("annotations") or []
            # Resolve class names if project_classes provided
            if project_classes and annotations:
                annotations = resolve_class_names(annotations, project_classes)
            return annotations
        return []
    except Exception as e:
        print(f"[AnnotationService] Error fetching annotations for {item_type} {item_id}: {e}")
        return []


def get_dataset_annotations(
    dataset_id: str,
    dataset_type: str,
    project_classes: list[str] = None
) -> AnnotationMap:
    """
    Batch load all annotations for a dataset (single query).
    
    Args:
        dataset_id: UUID of the dataset
        dataset_type: "image" or "video"
        project_classes: Optional. If provided, resolves class_name from 
                        project_classes[class_id] for all annotations.
        
    Returns:
        Dict mapping item_id -> annotations list
    """
    from backend.supabase_client import get_supabase
    
    supabase = get_supabase()
    
    try:
        if dataset_type == "video":
            # For video datasets, get annotations from keyframes via videos
            videos_result = (
                supabase.table("videos")
                .select("id")
                .eq("dataset_id", dataset_id)
                .execute()
            )
            video_ids = [v["id"] for v in (videos_result.data or [])]
            
            if not video_ids:
                return {}
            
            keyframes_result = (
                supabase.table("keyframes")
                .select("id, annotations")
                .in_("video_id", video_ids)
                .execute()
            )
            
            annotations_map = {
                kf["id"]: kf["annotations"]
                for kf in (keyframes_result.data or [])
                if kf.get("annotations") is not None
            }
        else:
            # For image datasets, get annotations directly from images
            result = (
                supabase.table("images")
                .select("id, annotations")
                .eq("dataset_id", dataset_id)
                .execute()
            )
            
            annotations_map = {
                img["id"]: img["annotations"]
                for img in (result.data or [])
                if img.get("annotations") is not None
            }
        
        # Resolve class names if project_classes provided
        if project_classes:
            for item_id, annotations in annotations_map.items():
                if annotations:
                    annotations_map[item_id] = resolve_class_names(annotations, project_classes)
        
        return annotations_map
            
    except Exception as e:
        print(f"[AnnotationService] Error batch loading annotations for dataset {dataset_id}: {e}")
        return {}


def get_annotations_for_training(
    dataset_ids: list[str],
    dataset_types: dict[str, str]
) -> AnnotationMap:
    """
    Batch load annotations across multiple datasets for training.
    
    Optimized for training workflows - uses batched `.in_()` queries.
    
    Args:
        dataset_ids: List of dataset UUIDs
        dataset_types: Dict mapping dataset_id -> type ("image" or "video")
        
    Returns:
        Dict mapping item_id -> annotations list (for all items across all datasets)
    """
    if not dataset_ids:
        return {}
    
    from backend.supabase_client import get_supabase
    
    supabase = get_supabase()
    all_annotations: AnnotationMap = {}
    
    # Separate by type for efficient batching
    image_dataset_ids = [d for d in dataset_ids if dataset_types.get(d) != "video"]
    video_dataset_ids = [d for d in dataset_ids if dataset_types.get(d) == "video"]
    
    try:
        # Batch fetch all image annotations
        if image_dataset_ids:
            images_result = (
                supabase.table("images")
                .select("id, annotations")
                .in_("dataset_id", image_dataset_ids)
                .execute()
            )
            
            for img in (images_result.data or []):
                if img.get("annotations"):
                    all_annotations[img["id"]] = img["annotations"]
        
        # Batch fetch all keyframe annotations (via videos)
        if video_dataset_ids:
            videos_result = (
                supabase.table("videos")
                .select("id")
                .in_("dataset_id", video_dataset_ids)
                .execute()
            )
            video_ids = [v["id"] for v in (videos_result.data or [])]
            
            if video_ids:
                keyframes_result = (
                    supabase.table("keyframes")
                    .select("id, annotations")
                    .in_("video_id", video_ids)
                    .execute()
                )
                
                for kf in (keyframes_result.data or []):
                    if kf.get("annotations"):
                        all_annotations[kf["id"]] = kf["annotations"]
        
        return all_annotations
        
    except Exception as e:
        print(f"[AnnotationService] Error fetching annotations for training: {e}")
        return {}


# =============================================================================
# AGGREGATION OPERATIONS
# =============================================================================


def compute_class_counts(
    annotations_map: AnnotationMap,
    project_classes: list[str] = None
) -> dict[str, int]:
    """
    Compute class occurrence counts from an annotation map.
    
    Args:
        annotations_map: Dict mapping item_id -> annotations list
        project_classes: Optional. If provided, resolves class_name from 
                        class_id when annotations don't have class_name stored.
        
    Returns:
        Dict mapping class_name -> count
    """
    class_counts: dict[str, int] = {}
    
    for annotations in annotations_map.values():
        for ann in annotations:
            # Try class_name first (legacy annotations)
            class_name = ann.get("class_name")
            
            # If no class_name, resolve from class_id using project_classes
            if not class_name and project_classes:
                class_id = ann.get("class_id", 0)
                if 0 <= class_id < len(project_classes):
                    class_name = project_classes[class_id]
                else:
                    class_name = "Unknown"
            elif not class_name:
                class_name = "Unknown"
            
            class_counts[class_name] = class_counts.get(class_name, 0) + 1
    
    return class_counts


def compute_class_counts_for_datasets(
    dataset_ids: list[str],
    dataset_types: dict[str, str],
    project_classes: list[str] = None
) -> dict[str, int]:
    """
    Compute combined class counts across multiple datasets.
    
    Convenience function that combines fetching + aggregation.
    
    Args:
        dataset_ids: List of dataset UUIDs
        dataset_types: Dict mapping dataset_id -> type ("image" or "video")
        project_classes: Optional. If provided, resolves class_name from
                        class_id when annotations don't have class_name stored.
        
    Returns:
        Dict mapping class_name -> total count
    """
    annotations_map = get_annotations_for_training(dataset_ids, dataset_types)
    return compute_class_counts(annotations_map, project_classes=project_classes)


# =============================================================================
# RESOLUTION LAYER (Phase E: Tech Debt)
# =============================================================================


def resolve_class_names(
    annotations: list[Annotation],
    project_classes: list[str]
) -> list[Annotation]:
    """
    Resolve class_name from class_id using project classes.
    
    This is the foundation for Phase E tech debt cleanup. Instead of storing
    class_name in annotations, we resolve it at display time from the 
    project's class registry.
    
    Args:
        annotations: List of annotation dicts (may or may not have class_name)
        project_classes: Project's class list where index = class_id
        
    Returns:
        Annotations with class_name populated from project_classes[class_id]
    """
    resolved = []
    for ann in annotations:
        # Create shallow copy to avoid mutating original
        resolved_ann = dict(ann)
        class_id = resolved_ann.get("class_id", 0)
        
        # Resolve class_name from project_classes
        if 0 <= class_id < len(project_classes):
            resolved_ann["class_name"] = project_classes[class_id]
        else:
            resolved_ann["class_name"] = "Unknown"
        
        resolved.append(resolved_ann)
    
    return resolved


def strip_class_names(annotations: list[Annotation]) -> list[Annotation]:
    """
    Remove class_name from annotations before storage.
    
    Used to clean up redundant class_name data during write operations.
    The class_name will be resolved at read/display time via resolve_class_names().
    
    Args:
        annotations: List of annotation dicts
        
    Returns:
        Annotations with class_name removed (class_id retained)
    """
    stripped = []
    for ann in annotations:
        # Create shallow copy to avoid mutating original
        stripped_ann = {k: v for k, v in ann.items() if k != "class_name"}
        stripped.append(stripped_ann)
    
    return stripped


# =============================================================================
# VALIDATION LAYER (Phase E2: Coordinate Standardization)
# =============================================================================


def validate_annotation_coordinates(annotation: Annotation) -> tuple[bool, str]:
    """
    Validate that annotation coordinates are in the correct format.
    
    Expected format: {x, y, width, height} all normalized 0-1.
    - x, y = top-left corner
    - width, height = size
    
    Args:
        annotation: Annotation dict to validate
        
    Returns:
        Tuple of (is_valid, error_message)
    """
    required = ["x", "y", "width", "height"]
    
    for field in required:
        if field not in annotation:
            return False, f"Missing field: {field}"
        
        value = annotation[field]
        if not isinstance(value, (int, float)):
            return False, f"Field '{field}' must be numeric, got {type(value).__name__}"
        
        if not (0.0 <= value <= 1.0):
            return False, f"Field '{field}' must be 0-1, got {value}"
    
    # Validate box doesn't extend beyond image (with small tolerance for float precision)
    if annotation["x"] + annotation["width"] > 1.01:
        return False, f"Box extends beyond right edge (x={annotation['x']}, width={annotation['width']})"
    if annotation["y"] + annotation["height"] > 1.01:
        return False, f"Box extends beyond bottom edge (y={annotation['y']}, height={annotation['height']})"
    
    return True, ""


def validate_annotations_batch(annotations: list[Annotation]) -> list[tuple[int, str]]:
    """
    Validate a batch of annotations.
    
    Args:
        annotations: List of annotation dicts to validate
        
    Returns:
        List of (index, error_message) for invalid annotations.
        Empty list if all valid.
    """
    errors = []
    for i, ann in enumerate(annotations):
        is_valid, error = validate_annotation_coordinates(ann)
        if not is_valid:
            errors.append((i, error))
    return errors


# =============================================================================
# WRITE OPERATIONS
# =============================================================================


def save_annotations(
    item_id: str,
    item_type: ItemType,
    annotations: list[Annotation],
    dataset_id: str,
    sync_r2: bool = True,
    video_id: str = None,
    frame_number: int = None
) -> bool:
    """
    Save annotations with dual-write to Supabase and R2.
    
    Args:
        item_id: UUID of the image or keyframe
        item_type: "image" or "keyframe"
        annotations: List of annotation dicts
        dataset_id: UUID of the parent dataset (for R2 path)
        sync_r2: If True, also write YOLO format to R2
        video_id: Required for keyframes if sync_r2=True
        frame_number: Required for keyframes if sync_r2=True
        
    Returns:
        True if successful, False otherwise
    """
    from backend.supabase_client import get_supabase
    
    table = "images" if item_type == "image" else "keyframes"
    
    try:
        # Validate coordinates (warning only, don't block save)
        validation_errors = validate_annotations_batch(annotations)
        if validation_errors:
            for idx, error in validation_errors[:3]:  # Log first 3 errors
                print(f"[AnnotationService] Warning: Annotation {idx} has invalid coordinates: {error}")
            if len(validation_errors) > 3:
                print(f"[AnnotationService] Warning: ... and {len(validation_errors) - 3} more invalid annotations")
        
        # 1. Write to Supabase JSONB (strip class_name - it's resolved at read time)
        supabase = get_supabase()
        
        # Strip class_name before storage (Phase E tech debt cleanup)
        # class_name will be resolved at display time via project_classes[class_id]
        storage_annotations = strip_class_names(annotations)

        
        # Build update payload - keyframes don't have 'labeled' column
        update_data = {
            "annotations": storage_annotations,
            "annotation_count": len(storage_annotations),
        }
        if item_type == "image":
            update_data["labeled"] = len(storage_annotations) > 0
        
        supabase.table(table).update(update_data).eq("id", item_id).execute()
        
        # 2. Write to R2 in YOLO format
        if sync_r2:
            _sync_annotations_to_r2(
                item_id=item_id,
                item_type=item_type,
                annotations=annotations,
                dataset_id=dataset_id,
                video_id=video_id,
                frame_number=frame_number
            )
        
        return True
        
    except Exception as e:
        print(f"[AnnotationService] Error saving annotations for {item_type} {item_id}: {e}")
        return False


def _sync_annotations_to_r2(
    item_id: str,
    item_type: ItemType,
    annotations: list[Annotation],
    dataset_id: str,
    video_id: str = None,
    frame_number: int = None
) -> None:
    """
    Sync annotations to R2 in YOLO format.
    
    Internal helper for save_annotations().
    """
    from backend.r2_storage import R2Client
    
    # Build R2 path based on item type
    if item_type == "image":
        label_path = f"datasets/{dataset_id}/labels/{item_id}.txt"
    else:
        # Keyframe path includes video_id and frame_number
        if video_id and frame_number is not None:
            label_path = f"datasets/{dataset_id}/labels/{video_id}_f{frame_number}.txt"
        else:
            # Fallback: use keyframe_id
            label_path = f"datasets/{dataset_id}/labels/{item_id}.txt"
    
    # Convert to YOLO format
    yolo_content = _annotations_to_yolo(annotations)
    
    try:
        r2 = R2Client()
        r2.upload_file(
            file_bytes=yolo_content.encode('utf-8'),
            path=label_path,
            content_type='text/plain'
        )
    except Exception as e:
        print(f"[AnnotationService] R2 sync error for {label_path}: {e}")


def _annotations_to_yolo(annotations: list[Annotation]) -> str:
    """
    Convert annotations to YOLO format string.
    
    YOLO format: class_id x_center y_center width height (normalized 0-1)
    """
    lines = []
    for ann in annotations:
        class_id = ann.get("class_id", 0)
        x = ann.get("x", 0)
        y = ann.get("y", 0)
        w = ann.get("width", 0)
        h = ann.get("height", 0)
        
        # Convert corner coords to center coords
        x_center = x + w / 2
        y_center = y + h / 2
        
        lines.append(f"{class_id} {x_center:.6f} {y_center:.6f} {w:.6f} {h:.6f}")
    
    return "\n".join(lines)


def _yolo_to_annotations(txt_content: str, project_classes: list[str]) -> list[Annotation]:
    """
    Parse YOLO format text and return list of annotation dicts.
    
    Args:
        txt_content: YOLO format string
        project_classes: List of class names for resolving class_id -> class_name
        
    Returns:
        List of annotation dicts
    """
    import uuid
    
    annotations = []
    if not txt_content or not txt_content.strip():
        return annotations
    
    for line in txt_content.strip().split("\n"):
        line = line.strip()
        if not line:
            continue
        
        try:
            parts = line.split()
            if len(parts) < 5:
                continue
            
            class_id = int(parts[0])
            x_center = float(parts[1])
            y_center = float(parts[2])
            w = float(parts[3])
            h = float(parts[4])
            
            # Convert center coords to corner coords
            x = x_center - w / 2
            y = y_center - h / 2
            
            # Resolve class name
            class_name = "Unknown"
            if 0 <= class_id < len(project_classes):
                class_name = project_classes[class_id]
            
            annotations.append({
                "id": str(uuid.uuid4()),
                "class_id": class_id,
                "class_name": class_name,
                "x": x,
                "y": y,
                "width": w,
                "height": h,
            })
        except (ValueError, IndexError) as e:
            print(f"[AnnotationService] Skipping invalid YOLO line: {line} - {e}")
            continue
    
    return annotations


# =============================================================================
# CLASS MANAGEMENT OPERATIONS
# =============================================================================


def rename_class_in_project(
    project_id: str,
    old_name: str,
    new_name: str,
    old_idx: int = None,
    new_idx: int = None,
    is_merge: bool = False,
) -> Generator[tuple[int, int], None, None]:
    """
    Rename or merge a class across all annotations in a project.
    
    After Phase E migration (class_name removed from storage):
    - Simple rename (A → A'): No annotation updates needed (O(1))
    - Merge (A → B): Still updates class_id in annotations (O(n))
    
    Yields progress updates as (updated_count, total) tuples.
    
    Args:
        project_id: UUID of the project
        old_name: Current class name (used for legacy annotations with class_name)
        new_name: New class name (used for legacy annotations with class_name)
        old_idx: Index of the old class (REQUIRED for merge operations)
        new_idx: Index of the target class (REQUIRED for merge operations)
        is_merge: If True, this is a merge operation requiring ID updates
    """
    # Simple renames don't require annotation updates after Phase E
    # Class name is resolved from project_classes[class_id] at display time
    if not is_merge:
        print(f"[AnnotationService] Simple rename '{old_name}' to '{new_name}' — no annotation updates needed")
        return
    from backend.supabase_client import get_supabase, get_project_datasets
    
    supabase = get_supabase()
    
    try:
        datasets = get_project_datasets(project_id)
        items_to_update = []  # List of (table_name, record_id, updated_annotations)
        
        for dataset in datasets:
            dataset_id = dataset["id"]
            dataset_type = dataset.get("type", "image")
            
            if dataset_type == "video":
                _collect_keyframe_renames(
                    supabase, dataset_id, old_name, new_name,
                    old_idx, new_idx, is_merge, items_to_update
                )
            else:
                _collect_image_renames(
                    supabase, dataset_id, old_name, new_name,
                    old_idx, new_idx, is_merge, items_to_update
                )
        
        total = len(items_to_update)
        if total > 0:
            yield (0, total)
        
        # Apply updates with progress
        for i, (table_name, record_id, annotations) in enumerate(items_to_update):
            supabase.table(table_name).update({"annotations": annotations}).eq("id", record_id).execute()
            
            if (i + 1) % 25 == 0 or (i + 1) == total:
                yield (i + 1, total)
        
        print(f"[AnnotationService] Renamed class '{old_name}' to '{new_name}' in {total} items")
        
    except Exception as e:
        print(f"[AnnotationService] Error renaming class: {e}")
        import traceback
        traceback.print_exc()


def _collect_image_renames(
    supabase,
    dataset_id: str,
    old_name: str,
    new_name: str,
    old_idx: int,
    new_idx: int,
    is_merge: bool,
    items_to_update: list
) -> None:
    """Helper to collect image annotation renames."""
    images_result = (
        supabase.table("images")
        .select("id, annotations")
        .eq("dataset_id", dataset_id)
        .execute()
    )
    
    for img in (images_result.data or []):
        annotations = img.get("annotations", []) or []
        modified = _rename_in_annotations(
            annotations, old_name, new_name, old_idx, new_idx, is_merge
        )
        if modified:
            items_to_update.append(("images", img["id"], annotations))


def _collect_keyframe_renames(
    supabase,
    dataset_id: str,
    old_name: str,
    new_name: str,
    old_idx: int,
    new_idx: int,
    is_merge: bool,
    items_to_update: list
) -> None:
    """Helper to collect keyframe annotation renames."""
    videos_result = supabase.table("videos").select("id").eq("dataset_id", dataset_id).execute()
    video_ids = [v["id"] for v in (videos_result.data or [])]
    
    if not video_ids:
        return
    
    keyframes_result = (
        supabase.table("keyframes")
        .select("id, annotations")
        .in_("video_id", video_ids)
        .execute()
    )
    
    for kf in (keyframes_result.data or []):
        annotations = kf.get("annotations", []) or []
        modified = _rename_in_annotations(
            annotations, old_name, new_name, old_idx, new_idx, is_merge
        )
        if modified:
            items_to_update.append(("keyframes", kf["id"], annotations))


def _rename_in_annotations(
    annotations: list[Annotation],
    old_name: str,
    new_name: str,
    old_idx: int,
    new_idx: int,
    is_merge: bool
) -> bool:
    """
    Update class IDs in annotations list for merge operations (mutates in place).
    
    After Phase E migration:
    - Matches by class_id (primary) or class_name (fallback for legacy)
    - Only updates class_id, not class_name (resolved at display time)
    
    Returns True if any modifications were made.
    """
    modified = False
    
    for ann in annotations:
        c_id = ann.get("class_id", 0)
        c_name = ann.get("class_name")
        
        # Match by class_id (primary) or class_name (fallback for legacy annotations)
        if c_id == old_idx or c_name == old_name:
            # For merges, update class_id to target
            if new_idx is not None:
                ann["class_id"] = new_idx
            # Update legacy class_name if present (backwards compatibility)
            if c_name and new_name:
                ann["class_name"] = new_name
            modified = True
        elif is_merge and old_idx is not None:
            # Shift down class_ids higher than removed class
            if c_id > old_idx:
                ann["class_id"] = c_id - 1
                modified = True
    
    return modified


def delete_class_from_project(
    project_id: str,
    class_name: str,
    class_idx: int,
    new_classes: list[str]
) -> int:
    """
    Delete a class from all annotations in a project.
    
    Removes annotations with the deleted class and shifts remaining class IDs.
    Also updates R2 label files.
    
    Args:
        project_id: UUID of the project
        class_name: Name of the class to delete
        class_idx: Index of the class being deleted
        new_classes: Updated classes list (after deletion)
        
    Returns:
        Number of items updated
    """
    from backend.supabase_client import get_supabase, get_project_datasets
    from backend.r2_storage import R2Client
    
    supabase = get_supabase()
    r2 = R2Client()
    updated_count = 0
    
    try:
        datasets = get_project_datasets(project_id)
        
        for dataset in datasets:
            dataset_id = dataset["id"]
            dataset_type = dataset.get("type", "image")
            
            if dataset_type == "video":
                updated_count += _delete_from_keyframes(
                    supabase, r2, dataset_id, class_name, class_idx, new_classes
                )
            else:
                updated_count += _delete_from_images(
                    supabase, r2, dataset_id, class_name, class_idx, new_classes
                )
        
        print(f"[AnnotationService] Deleted class '{class_name}' from {updated_count} items")
        return updated_count
        
    except Exception as e:
        print(f"[AnnotationService] Error deleting class: {e}")
        import traceback
        traceback.print_exc()
        return 0


def _delete_from_images(
    supabase,
    r2,
    dataset_id: str,
    class_name: str,
    class_idx: int,
    new_classes: list[str]
) -> int:
    """Helper to delete class from image annotations."""
    images_result = (
        supabase.table("images")
        .select("id, annotations")
        .eq("dataset_id", dataset_id)
        .execute()
    )
    
    updated_count = 0
    
    for img in (images_result.data or []):
        annotations = img.get("annotations", []) or []
        if not annotations:
            continue
        
        new_annotations, modified = _filter_and_shift_annotations(
            annotations, class_name, class_idx, new_classes
        )
        
        if modified:
            # Update database
            supabase.table("images").update({
                "annotations": new_annotations,
                "annotation_count": len(new_annotations)
            }).eq("id", img["id"]).execute()
            
            # Update R2
            label_path = f"datasets/{dataset_id}/labels/{img['id']}.txt"
            _upload_yolo_to_r2(r2, label_path, new_annotations)
            
            updated_count += 1
    
    return updated_count


def _delete_from_keyframes(
    supabase,
    r2,
    dataset_id: str,
    class_name: str,
    class_idx: int,
    new_classes: list[str]
) -> int:
    """Helper to delete class from keyframe annotations."""
    videos_result = supabase.table("videos").select("id").eq("dataset_id", dataset_id).execute()
    video_ids = [v["id"] for v in (videos_result.data or [])]
    
    if not video_ids:
        return 0
    
    keyframes_result = (
        supabase.table("keyframes")
        .select("id, video_id, frame_number, annotations")
        .in_("video_id", video_ids)
        .execute()
    )
    
    updated_count = 0
    
    for kf in (keyframes_result.data or []):
        annotations = kf.get("annotations", []) or []
        if not annotations:
            continue
        
        new_annotations, modified = _filter_and_shift_annotations(
            annotations, class_name, class_idx, new_classes
        )
        
        if modified:
            # Update database
            supabase.table("keyframes").update({
                "annotations": new_annotations,
                "annotation_count": len(new_annotations)
            }).eq("id", kf["id"]).execute()
            
            # Update R2
            video_id = kf.get("video_id")
            frame_number = kf.get("frame_number", 0)
            label_path = f"datasets/{dataset_id}/labels/{video_id}_f{frame_number}.txt"
            _upload_yolo_to_r2(r2, label_path, new_annotations)
            
            updated_count += 1
    
    return updated_count


def _filter_and_shift_annotations(
    annotations: list[Annotation],
    class_name: str,
    class_idx: int,
    new_classes: list[str]
) -> tuple[list[Annotation], bool]:
    """
    Filter out deleted class and shift remaining class IDs.
    
    Returns:
        (new_annotations, was_modified)
    """
    new_annotations = []
    modified = False
    
    for ann in annotations:
        c_id = ann.get("class_id", 0)
        c_name = ann.get("class_name")
        
        # Match by class_id (primary) or class_name (fallback for legacy)
        if c_id == class_idx or c_name == class_name:
            # Skip deleted class
            modified = True
            continue
        
        # Shift class_id if higher than deleted
        if c_id > class_idx:
            ann["class_id"] = c_id - 1
            # Update legacy class_name if present
            if c_name and (c_id - 1) < len(new_classes):
                ann["class_name"] = new_classes[c_id - 1]
            modified = True
        
        new_annotations.append(ann)
    
    return new_annotations, modified


def _upload_yolo_to_r2(r2, label_path: str, annotations: list[Annotation]) -> None:
    """Upload annotations to R2 in YOLO format."""
    try:
        yolo_content = _annotations_to_yolo(annotations)
        r2.upload_file(
            file_bytes=yolo_content.encode('utf-8'),
            path=label_path,
            content_type='text/plain'
        )
    except Exception as e:
        print(f"[AnnotationService] R2 upload error for {label_path}: {e}")
