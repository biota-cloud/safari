"""
Dataset Detail State — State management for the dataset detail page.

Handles:
- Loading dataset and images/videos
- Uploading new images/videos to R2
- Deleting images/videos

Note: This replaces the old ProjectDetailState for image management.
"""

import reflex as rx
import uuid
import subprocess
import tempfile
import os
import json
from typing import Optional
from PIL import Image as PILImage
import io

from app_state import AuthState
from backend.supabase_client import (
    get_project,
    get_dataset,
    get_dataset_images,
    get_dataset_videos,
    get_project_datasets,
    create_image,
    create_video,
    create_dataset,
    bulk_create_images,
    delete_image as db_delete_image,
    delete_video as db_delete_video,
    delete_video_keyframes,
    update_dataset as db_update_dataset,
    touch_dataset_accessed,
)
from backend.r2_storage import R2Client
from backend.zip_processor import (
    extract_and_parse_zip,
    parse_yolo_label,
    YOLODatasetInfo,
    ZipProcessorError,
)
from pydantic import BaseModel


# =============================================================================
# VIDEO PROXY CONFIG
# =============================================================================
# Max height before generating a web-optimized proxy on upload.
# Videos taller than this will be transcoded to this height.
# Change this single value to adjust (e.g., 640 for more aggressive compression).
VIDEO_PROXY_MAX_HEIGHT = 720


class ImageModel(BaseModel):
    """Typed model for image data."""
    id: str = ""
    dataset_id: str = ""
    filename: str = ""
    r2_path: str = ""
    width: int = 0
    height: int = 0
    labeled: bool = False
    created_at: str = ""
    # Presigned URL for display (generated on load)
    display_url: str = ""

class VideoModel(BaseModel):
    """Typed model for video data."""
    id: str = ""
    dataset_id: str = ""
    filename: str = ""
    r2_path: str = ""
    duration_seconds: float = 0.0
    frame_count: int = 0
    fps: float = 0.0
    width: int = 0
    height: int = 0
    thumbnail_path: str = ""
    created_at: str = ""
    # Presigned URL for display (generated on load)
    display_url: str = ""
    # Pre-formatted duration string (e.g., "1:23")
    duration_display: str = ""


class VideoLabelsBreakdown(BaseModel):
    """Typed model for video labels breakdown."""
    video_id: str = ""
    video_name: str = ""
    label_count: int = 0
    labels: dict[str, int] = {}  # class_name -> count
class DatasetDetailState(rx.State):
    """State for the dataset detail page with upload functionality."""
    
    # Context
    current_project_id: str = ""
    current_dataset_id: str = ""
    project_name: str = ""
    dataset_name: str = ""
    dataset_type: str = "image"
    dataset_classes: list[str] = []
    usage_tag: str = "train"
    
    # Images
    images: list[ImageModel] = []
    
    # Videos
    videos: list[VideoModel] = []
    
    # Loading states
    is_loading: bool = False  # Default to False to prevent skeleton flash on re-navigation
    is_uploading: bool = False
    _has_loaded_once: bool = False  # Track first load for skeleton display
    
    # Error handling
    error_message: str = ""
    
    # Edit Dataset Modal state
    show_edit_modal: bool = False
    edit_dataset_name: str = ""
    edit_dataset_description: str = ""
    is_saving_dataset: bool = False
    edit_dataset_error: str = ""
    
    # Duplicate detection modal state
    show_duplicate_warning: bool = False
    duplicate_filenames: list[str] = []
    pending_files: list = []
    pending_upload_type: str = ""  # "image" or "video"
    
    # Selection state for batch actions
    selected_image_ids: list[str] = []
    selected_video_ids: list[str] = []
    
    # Class distribution from dataset
    class_counts: dict[str, int] = {}
    
    # Camera / EXIF stats (secondary insights, typed for Reflex foreach)
    exif_cameras: list[dict[str, str]] = []
    exif_date_min: str = ""
    exif_date_max: str = ""
    exif_day_count: int = 0
    exif_night_count: int = 0
    exif_total: int = 0
    
    # Labels breakdown by video (for video datasets)
    video_labels_breakdown: list[VideoLabelsBreakdown] = []
    
    # Project classes (from project level, for class management)
    project_classes: list[str] = []

    is_processing_class: bool = False
    
    # Batch label operations state
    target_video_id: str = ""
    target_class_name: str = ""
    show_reassign_modal: bool = False
    show_delete_labels_modal: bool = False
    reassign_to_class: str = ""
    
    # Image/Video delete confirmation state
    show_delete_image_modal: bool = False
    image_to_delete_id: str = ""
    image_to_delete_name: str = ""
    show_delete_video_modal: bool = False
    video_to_delete_id: str = ""
    video_to_delete_name: str = ""
    
    # Delete class annotations modal state (high-impact: requires typing "delete")
    show_delete_class_annotations_modal: bool = False
    delete_class_annotations_name: str = ""
    delete_class_annotations_count: int = 0
    delete_class_confirmation: str = ""
    is_deleting_class_annotations: bool = False
    
    async def load_dataset(self):
        """Load dataset details and images on page load."""
        # Only show skeleton on first load to prevent flickering on re-navigation
        if not self._has_loaded_once:
            self.is_loading = True
            yield
        self.error_message = ""
        
        try:
            # Get IDs from route
            self.current_project_id = self.router.page.params.get("project_id", "")
            self.current_dataset_id = self.router.page.params.get("dataset_id", "")
            
            if not self.current_project_id or not self.current_dataset_id:
                self.error_message = "No project or dataset ID provided."
                self.is_loading = False
                return
            
            # Fetch project name and classes for breadcrumb and class management
            project = get_project(self.current_project_id)
            if project:
                self.project_name = project.get("name", "")
                self.project_classes = project.get("classes", []) or []
            
            # Fetch dataset data
            dataset = get_dataset(self.current_dataset_id)
            if not dataset:
                self.error_message = "Dataset not found."
                self.is_loading = False
                return
            
            self.dataset_name = dataset.get("name", "")
            self.dataset_type = dataset.get("type", "image")
            self.dataset_classes = dataset.get("classes", []) or []
            self.usage_tag = dataset.get("usage_tag", "train")
            # Initialize empty - will be populated from annotations below
            self.class_counts = {}
            
            # Reset selection state
            self.selected_image_ids = []
            self.selected_video_ids = []
            
            # Fetch content based on dataset type
            if self.dataset_type == "video":
                await self._load_videos()
                await self._load_video_labels_breakdown()
            else:
                await self._load_images()
            
        except Exception as e:
            print(f"[DEBUG] Error loading dataset: {e}")
            self.error_message = f"Error loading dataset: {str(e)}"
        finally:
            self.is_loading = False
            self._has_loaded_once = True
        
        # Touch dataset for last_accessed_at sorting
        if self.current_dataset_id:
            touch_dataset_accessed(self.current_dataset_id)
        
        # Compute fresh class counts from annotations (after page renders)
        if self.current_dataset_id:
            try:
                if self.dataset_type == "video":
                    from backend.supabase_client import get_dataset_class_counts_from_keyframes
                    # Pass project_classes for resolving class names from class_id
                    fresh_counts = get_dataset_class_counts_from_keyframes(
                        self.current_dataset_id,
                        project_classes=self.project_classes
                    )
                else:
                    from backend.supabase_client import get_image_class_counts_from_annotations
                    # Pass project_classes for resolving class names from class_id
                    fresh_counts = get_image_class_counts_from_annotations(
                        self.current_dataset_id,
                        project_classes=self.project_classes
                    )
                
                if fresh_counts:
                    self.class_counts = fresh_counts
                    print(f"[DEBUG] Computed class counts from annotations: {fresh_counts}")
            except Exception as e:
                print(f"[DEBUG] Error computing class counts from annotations: {e}")
        
        # Load camera / EXIF stats (secondary, after page renders)
        if self.current_dataset_id and self.dataset_type != "video":
            try:
                from backend.supabase_client import get_dataset_camera_stats
                stats = get_dataset_camera_stats(self.current_dataset_id)
                self.exif_cameras = [
                    {"model": c["model"], "count": str(c["count"])}
                    for c in stats.get("cameras", [])
                ]
                self.exif_date_min = (stats.get("date_min") or "")[:10]
                self.exif_date_max = (stats.get("date_max") or "")[:10]
                self.exif_day_count = stats.get("day_count", 0)
                self.exif_night_count = stats.get("night_count", 0)
                self.exif_total = stats.get("total_with_exif", 0)
                print(f"[DEBUG] Camera stats loaded: {self.exif_total} images with EXIF, {len(self.exif_cameras)} cameras")
                yield
            except Exception as e:
                print(f"[DEBUG] Error loading camera stats: {e}")
                import traceback
                traceback.print_exc()
    
    
    async def _load_images(self):
        """Load images for the current dataset with presigned URLs."""
        try:
            raw_images = get_dataset_images(self.current_dataset_id)
            r2 = R2Client()
            
            self.images = []
            for img in raw_images:
                # Generate presigned URL for display
                display_url = ""
                r2_path = img.get("r2_path", "")
                
                # Try thumbnail path first
                thumbnail_path = r2_path.replace("/images/", "/thumbnails/") if "/images/" in r2_path else r2_path
                
                if thumbnail_path:
                    try:
                        display_url = r2.generate_presigned_url(thumbnail_path)
                    except Exception as e:
                        print(f"[DEBUG] Error generating URL for {thumbnail_path}: {e}")
                
                self.images.append(ImageModel(
                    id=str(img.get("id", "")),
                    dataset_id=str(img.get("dataset_id", "")),
                    filename=str(img.get("filename", "")),
                    r2_path=str(r2_path),
                    width=img.get("width") or 0,
                    height=img.get("height") or 0,
                    labeled=img.get("labeled", False),
                    created_at=str(img.get("created_at", "")),
                    display_url=display_url,
                ))
        except Exception as e:
            print(f"[DEBUG] Error loading images: {e}")
    
    def _get_project_filenames(self) -> set[str]:
        """Get all filenames (images + videos) from all datasets in current project."""
        filenames = set()
        try:
            datasets = get_project_datasets(self.current_project_id)
            for ds in datasets:
                if ds.get("type") == "video":
                    videos = get_dataset_videos(ds["id"])
                    filenames.update(v.get("filename", "") for v in videos)
                else:
                    images = get_dataset_images(ds["id"])
                    filenames.update(i.get("filename", "") for i in images)
        except Exception as e:
            print(f"[DEBUG] Error fetching project filenames: {e}")
        return filenames
    
    def _clear_pending(self):
        """Clear pending upload state."""
        self.pending_files = []
        self.pending_upload_type = ""
        self.duplicate_filenames = []
    
    async def handle_upload(self, files: list[rx.UploadFile]):
        """
        Handle uploaded files — check for duplicates first, then upload.
        
        Args:
            files: List of uploaded files from rx.upload
        """
        print(f"[UPLOAD DEBUG] handle_upload called with {len(files) if files else 0} files")
        print(f"[UPLOAD DEBUG] current_dataset_id: {self.current_dataset_id}")
        
        if not files:
            print("[UPLOAD DEBUG] No files provided, returning")
            return
        
        if not self.current_dataset_id:
            print("[UPLOAD DEBUG] ERROR: No dataset_id set!")
            yield rx.toast.error("No dataset selected. Please reload the page.")
            return
        
        # Check for duplicates across the project
        incoming_filenames = {f.filename for f in files}
        existing_filenames = self._get_project_filenames()
        duplicates = incoming_filenames & existing_filenames
        
        if duplicates:
            # Store pending state and show warning modal
            self.pending_files = files
            self.pending_upload_type = "image"
            self.duplicate_filenames = sorted(list(duplicates))
            self.show_duplicate_warning = True
            print(f"[UPLOAD DEBUG] Found {len(duplicates)} duplicates: {duplicates}")
            return
        
        # No duplicates, proceed with upload
        async for event in self._do_image_upload(files):
            yield event
    
    async def _do_image_upload(self, files: list):
        """
        Perform the actual image upload to R2 and database.
        
        Args:
            files: List of files to upload
        """
        self.is_uploading = True
        self.error_message = ""
        yield
        
        try:
            r2 = R2Client()
            uploaded_count = 0
            
            for i, file in enumerate(files):
                try:
                    print(f"[UPLOAD DEBUG] Processing file {i+1}: {file.filename}")
                    
                    # Read file content
                    file_content = await file.read()
                    print(f"[UPLOAD DEBUG] Read {len(file_content)} bytes")
                    
                    # Extract EXIF metadata before any processing
                    from backend.exif_utils import extract_exif_metadata
                    exif_meta = extract_exif_metadata(file_content)
                    if exif_meta:
                        print(f"[UPLOAD DEBUG] EXIF: {exif_meta}")
                    
                    # 1. Process Image and Generate Thumbnail
                    img = PILImage.open(io.BytesIO(file_content))
                    width, height = img.size
                    print(f"[UPLOAD DEBUG] Image dimensions: {width}x{height}")
                    
                    # Generate unique filename
                    ext = file.filename.split(".")[-1].lower() if "." in file.filename else "jpg"
                    unique_id = str(uuid.uuid4())
                    
                    # Paths (now using datasets/ instead of projects/)
                    original_key = f"datasets/{self.current_dataset_id}/images/{unique_id}.{ext}"
                    thumbnail_key = f"datasets/{self.current_dataset_id}/thumbnails/{unique_id}.{ext}"
                    print(f"[UPLOAD DEBUG] R2 paths: {original_key}, {thumbnail_key}")
                    
                    # Determine content type
                    content_type = self._get_content_type(ext)
                    
                    # 2. Upload Original
                    print("[UPLOAD DEBUG] Uploading original to R2...")
                    r2.upload_file(file_content, original_key, content_type=content_type)
                    print("[UPLOAD DEBUG] Original uploaded successfully")
                    
                    # 3. Create and Upload Thumbnail
                    thumb_io = io.BytesIO()
                    img.thumbnail((400, 400))
                    img.save(thumb_io, format=img.format or "JPEG")
                    thumb_bytes = thumb_io.getvalue()
                    
                    print("[UPLOAD DEBUG] Uploading thumbnail to R2...")
                    r2.upload_file(thumb_bytes, thumbnail_key, content_type=content_type)
                    print("[UPLOAD DEBUG] Thumbnail uploaded successfully")
                    
                    # 4. Save to database (with EXIF metadata)
                    print("[UPLOAD DEBUG] Saving to database...")
                    create_image(
                        dataset_id=self.current_dataset_id,
                        filename=file.filename,
                        r2_path=original_key,
                        width=width,
                        height=height,
                        captured_at=exif_meta.get("captured_at").isoformat() if exif_meta.get("captured_at") else None,
                        camera_make=exif_meta.get("camera_make"),
                        camera_model=exif_meta.get("camera_model"),
                        is_night_shot=exif_meta.get("is_night_shot"),
                    )
                    print("[UPLOAD DEBUG] Database record created")
                    
                    uploaded_count += 1
                    
                except Exception as e:
                    print(f"[UPLOAD DEBUG] Error uploading {file.filename}: {e}")
                    import traceback
                    traceback.print_exc()
                    continue
            
            # Reload images to show new uploads
            print(f"[UPLOAD DEBUG] Reloading images after uploading {uploaded_count} files")
            await self._load_images()
            
            # Show success toast
            if uploaded_count > 0:
                print(f"[UPLOAD DEBUG] Upload complete, {uploaded_count} files uploaded")
                yield rx.toast.success(f"{uploaded_count} image(s) uploaded successfully!")
                yield rx.clear_selected_files("dataset_images")
            else:
                print("[UPLOAD DEBUG] No files were uploaded successfully")
            
        except Exception as e:
            print(f"[UPLOAD DEBUG] Upload error: {e}")
            import traceback
            traceback.print_exc()
            self.error_message = f"Upload failed: {str(e)}"
            yield rx.toast.error("Upload failed. Please try again.")
        finally:
            self.is_uploading = False
    
    def _get_content_type(self, ext: str) -> str:
        """Get MIME type for file extension."""
        types = {
            "jpg": "image/jpeg",
            "jpeg": "image/jpeg",
            "png": "image/png",
            "webp": "image/webp",
            "mp4": "video/mp4",
            "mov": "video/quicktime",
            "webm": "video/webm",
        }
        return types.get(ext.lower(), "application/octet-stream")
    
    # =========================================================================
    # R2 CLEANUP HELPERS (shared by single + bulk delete)
    # =========================================================================
    
    def _delete_image_r2_files(self, r2: "R2Client", r2_path: str):
        """Delete an image's original + thumbnail from R2."""
        if not r2_path:
            return
        try:
            r2.delete_file(r2_path)
            # Thumbnail lives at the same path with /images/ → /thumbnails/
            if "/images/" in r2_path:
                r2.delete_file(r2_path.replace("/images/", "/thumbnails/"))
        except Exception as e:
            print(f"[DEBUG] R2 cleanup error (image): {e}")
    
    def _delete_video_r2_files(self, r2: "R2Client", video: "VideoModel"):
        """Delete a video's original, thumbnail, and proxy from R2."""
        try:
            if video.r2_path:
                r2.delete_file(video.r2_path)
            if video.thumbnail_path:
                r2.delete_file(video.thumbnail_path)
            # Proxy path convention: /videos/ → /video_proxies/, ext → .mp4
            if video.r2_path and "/videos/" in video.r2_path:
                proxy_path = video.r2_path.replace("/videos/", "/video_proxies/")
                proxy_path = proxy_path.rsplit(".", 1)[0] + ".mp4"
                try:
                    r2.delete_file(proxy_path)
                except Exception:
                    pass  # Proxy may not exist
        except Exception as e:
            print(f"[DEBUG] R2 cleanup error (video): {e}")
    
    # =========================================================================
    # IMAGE DELETE CONFIRMATION
    # =========================================================================
    
    def request_delete_image(self, image_id: str):
        """Open delete confirmation modal for an image."""
        for img in self.images:
            if img.id == image_id:
                self.image_to_delete_id = image_id
                self.image_to_delete_name = img.filename
                self.show_delete_image_modal = True
                return
    
    def close_delete_image_modal(self):
        """Close the delete image confirmation modal."""
        self.show_delete_image_modal = False
        self.image_to_delete_id = ""
        self.image_to_delete_name = ""
    
    def confirm_delete_image(self):
        """Confirm and execute the image deletion."""
        image_id = self.image_to_delete_id
        self.show_delete_image_modal = False
        self.image_to_delete_id = ""
        self.image_to_delete_name = ""
        
        if image_id:
            return self.delete_image(image_id)
    
    async def delete_image(self, image_id: str):
        """Delete an image from R2 and database."""
        try:
            image_to_delete = next((img for img in self.images if img.id == image_id), None)
            if not image_to_delete:
                return
            
            r2 = R2Client()
            self._delete_image_r2_files(r2, image_to_delete.r2_path)
            db_delete_image(image_id)
            
            self.images = [img for img in self.images if img.id != image_id]
            yield rx.toast.success("Image deleted.")
            
        except Exception as e:
            print(f"[DEBUG] Error deleting image: {e}")
            yield rx.toast.error("Failed to delete image.")
    
    @rx.var
    def image_count(self) -> int:
        """Get total number of images."""
        return len(self.images)
    
    @rx.var
    def labeled_count(self) -> int:
        """Get number of labeled items (images or videos with annotations)."""
        if self.dataset_type == "video":
            # Count videos that have at least one label
            return len([v for v in self.video_labels_breakdown if v.label_count > 0])
        return len([img for img in self.images if img.labeled])
    
    @rx.var
    def has_images(self) -> bool:
        """Check if dataset has any images."""
        return len(self.images) >  0
    
    async def set_usage_tag(self, tag: str):
        """Update dataset usage tag in database and local state."""
        if tag not in ["train", "validation"]:
            return
        
        try:
            from backend.supabase_client import update_dataset
            update_dataset(self.current_dataset_id, usage_tag=tag)
            async with self:
                self.usage_tag = tag
            yield rx.toast.success(f"Dataset tagged as {tag}")
        except Exception as e:
            print(f"[DEBUG] Error updating usage tag: {e}")
            yield rx.toast.error(f"Failed to update tag: {e}")
    
    # =========================================================================
    # EDIT DATASET MODAL
    # =========================================================================
    
    def open_edit_modal(self):
        """Open the edit dataset modal with current values."""
        self.show_edit_modal = True
        self.edit_dataset_name = self.dataset_name
        # Datasets don't have a description field in the model, so we'll skip it
        self.edit_dataset_error = ""
    
    def close_edit_modal(self):
        """Close the edit dataset modal."""
        self.show_edit_modal = False
        self.edit_dataset_name = ""
        self.edit_dataset_error = ""
    
    def set_edit_dataset_name(self, value: str):
        """Update the edit dataset name."""
        self.edit_dataset_name = value
    
    async def save_dataset_edits(self):
        """Save dataset name edits."""
        if not self.edit_dataset_name.strip():
            self.edit_dataset_error = "Dataset name is required."
            return
        
        self.is_saving_dataset = True
        self.edit_dataset_error = ""
        yield
        
        try:
            # Update in database
            result = db_update_dataset(
                self.current_dataset_id,
                name=self.edit_dataset_name.strip(),
            )
            
            if result:
                # Update local state
                self.dataset_name = self.edit_dataset_name.strip()
                self.close_edit_modal()
                yield rx.toast.success("Dataset updated successfully")
            else:
                self.edit_dataset_error = "Failed to update dataset. Please try again."
        except Exception as e:
            print(f"[DEBUG] Error updating dataset: {e}")
            self.edit_dataset_error = f"Error: {str(e)}"
        finally:
            self.is_saving_dataset = False

    async def handle_edit_keydown(self, key: str):
        """Handle Enter key in dataset edit modal."""
        if key == "Enter" and not self.is_saving_dataset:
            async for event in self.save_dataset_edits():
                yield event
    
    @rx.var
    def video_count(self) -> int:
        """Get total number of videos."""
        return len(self.videos)
    
    @rx.var
    def has_videos(self) -> bool:
        """Check if dataset has any videos."""
        return len(self.videos) > 0
    
    async def _load_videos(self):
        """Load videos for the current dataset with presigned URLs."""
        try:
            raw_videos = get_dataset_videos(self.current_dataset_id)
            r2 = R2Client()
            
            self.videos = []
            for vid in raw_videos:
                # Generate presigned URL for thumbnail display
                display_url = ""
                thumbnail_path = vid.get("thumbnail_path", "")
                
                if thumbnail_path:
                    try:
                        display_url = r2.generate_presigned_url(thumbnail_path)
                    except Exception as e:
                        print(f"[DEBUG] Error generating URL for {thumbnail_path}: {e}")
                
                # Format duration for display (e.g., "1:23")
                duration_secs = vid.get("duration_seconds") or 0.0
                mins = int(duration_secs // 60)
                secs = int(duration_secs % 60)
                duration_display = f"{mins}:{secs:02d}" if duration_secs > 0 else ""
                
                self.videos.append(VideoModel(
                    id=str(vid.get("id", "")),
                    dataset_id=str(vid.get("dataset_id", "")),
                    filename=str(vid.get("filename", "")),
                    r2_path=str(vid.get("r2_path", "")),
                    duration_seconds=duration_secs,
                    frame_count=vid.get("frame_count") or 0,
                    fps=vid.get("fps") or 0.0,
                    width=vid.get("width") or 0,
                    height=vid.get("height") or 0,
                    thumbnail_path=str(vid.get("thumbnail_path", "")),
                    created_at=str(vid.get("created_at", "")),
                    display_url=display_url,
                    duration_display=duration_display,
                ))
        except Exception as e:
            print(f"[DEBUG] Error loading videos: {e}")
    
    async def handle_video_upload(self, files: list[rx.UploadFile]):
        """
        Handle uploaded video files — check for duplicates first, then upload.
        Uses ffmpeg to extract first frame as thumbnail and get metadata.
        """
        print(f"[VIDEO UPLOAD] handle_video_upload called with {len(files) if files else 0} files")
        
        if not files:
            return
        
        if not self.current_dataset_id:
            yield rx.toast.error("No dataset selected. Please reload the page.")
            return
        
        # Check for duplicates across the project
        incoming_filenames = {f.filename for f in files}
        existing_filenames = self._get_project_filenames()
        duplicates = incoming_filenames & existing_filenames
        
        if duplicates:
            # Store pending state and show warning modal
            self.pending_files = files
            self.pending_upload_type = "video"
            self.duplicate_filenames = sorted(list(duplicates))
            self.show_duplicate_warning = True
            print(f"[VIDEO UPLOAD] Found {len(duplicates)} duplicates: {duplicates}")
            return
        
        # No duplicates, proceed with upload
        async for event in self._do_video_upload(files):
            yield event
    
    async def _do_video_upload(self, files: list):
        """
        Perform the actual video upload to R2 and database.
        Uses ffmpeg to extract first frame as thumbnail and get metadata.
        """
        self.is_uploading = True
        self.error_message = ""
        yield
        
        try:
            r2 = R2Client()
            uploaded_count = 0
            
            for i, file in enumerate(files):
                try:
                    print(f"[VIDEO UPLOAD] Processing file {i+1}: {file.filename}")
                    
                    # Read file content
                    file_content = await file.read()
                    file_size_mb = len(file_content) / (1024 * 1024)
                    print(f"[VIDEO UPLOAD] Read {file_size_mb:.1f} MB")
                    
                    # Generate unique filename
                    ext = file.filename.split(".")[-1].lower() if "." in file.filename else "mp4"
                    unique_id = str(uuid.uuid4())
                    
                    # R2 paths
                    video_key = f"datasets/{self.current_dataset_id}/videos/{unique_id}.{ext}"
                    thumbnail_key = f"datasets/{self.current_dataset_id}/video_thumbnails/{unique_id}.jpg"
                    
                    # Determine content type
                    content_type = self._get_content_type(ext)
                    
                    # 1. Upload video to R2
                    print(f"[VIDEO UPLOAD] Uploading video to R2: {video_key}")
                    r2.upload_file(file_content, video_key, content_type=content_type)
                    print("[VIDEO UPLOAD] Video uploaded successfully")
                    
                    # 2. Extract metadata and thumbnail using ffmpeg
                    duration_seconds = None
                    frame_count = None
                    fps = None
                    width = None
                    height = None
                    thumbnail_uploaded = False
                    
                    # Save to temp file for ffmpeg processing
                    with tempfile.NamedTemporaryFile(suffix=f".{ext}", delete=False) as tmp_video:
                        tmp_video.write(file_content)
                        tmp_video_path = tmp_video.name
                    
                    try:
                        # Get video metadata with ffprobe
                        probe_cmd = [
                            "ffprobe", "-v", "quiet",
                            "-print_format", "json",
                            "-show_format", "-show_streams",
                            tmp_video_path
                        ]
                        probe_result = subprocess.run(probe_cmd, capture_output=True, text=True, timeout=30)
                        
                        if probe_result.returncode == 0:
                            probe_data = json.loads(probe_result.stdout)
                            
                            # Extract format info
                            format_info = probe_data.get("format", {})
                            duration_seconds = float(format_info.get("duration", 0))
                            
                            # Find video stream
                            for stream in probe_data.get("streams", []):
                                if stream.get("codec_type") == "video":
                                    width = stream.get("width")
                                    height = stream.get("height")
                                    
                                    # Calculate FPS from rational
                                    fps_str = stream.get("r_frame_rate", "0/1")
                                    if "/" in fps_str:
                                        num, den = fps_str.split("/")
                                        fps = float(num) / float(den) if float(den) > 0 else 0
                                    
                                    # Calculate frame count
                                    nb_frames = stream.get("nb_frames")
                                    if nb_frames:
                                        frame_count = int(nb_frames)
                                    elif duration_seconds and fps:
                                        frame_count = int(duration_seconds * fps)
                                    break
                            
                            print(f"[VIDEO UPLOAD] Metadata: {width}x{height}, {duration_seconds:.1f}s, {fps:.1f}fps, {frame_count} frames")
                        
                        # Extract first frame as thumbnail
                        with tempfile.NamedTemporaryFile(suffix=".jpg", delete=False) as tmp_thumb:
                            tmp_thumb_path = tmp_thumb.name
                        
                        thumb_cmd = [
                            "ffmpeg", "-y", "-i", tmp_video_path,
                            "-ss", "0", "-vframes", "1",
                            "-vf", "scale=400:-1",  # Max width 400, preserve aspect
                            "-f", "image2",
                            tmp_thumb_path
                        ]
                        thumb_result = subprocess.run(thumb_cmd, capture_output=True, timeout=30)
                        
                        if thumb_result.returncode == 0 and os.path.exists(tmp_thumb_path):
                            with open(tmp_thumb_path, "rb") as f:
                                thumb_bytes = f.read()
                            r2.upload_file(thumb_bytes, thumbnail_key, content_type="image/jpeg")
                            thumbnail_uploaded = True
                            print("[VIDEO UPLOAD] Thumbnail extracted and uploaded")
                            os.unlink(tmp_thumb_path)
                        
                    except subprocess.TimeoutExpired:
                        print("[VIDEO UPLOAD] ffmpeg timeout - skipping metadata extraction")
                    except Exception as e:
                        print(f"[VIDEO UPLOAD] ffmpeg error: {e}")
                    
                    # 3. Generate web proxy if video exceeds max height
                    proxy_r2_path = None
                    if width and height and height > VIDEO_PROXY_MAX_HEIGHT:
                        try:
                            proxy_tmp_path = tmp_video_path + "_proxy.mp4"
                            proxy_cmd = [
                                "ffmpeg", "-y", "-i", tmp_video_path,
                                "-vf", f"scale=-2:{VIDEO_PROXY_MAX_HEIGHT}",
                                "-c:v", "libx264", "-preset", "fast", "-crf", "28",
                                "-movflags", "+faststart",
                                "-an",  # Strip audio — not needed for labeling
                                proxy_tmp_path
                            ]
                            print(f"[VIDEO UPLOAD] Transcoding proxy ({width}x{height} → {VIDEO_PROXY_MAX_HEIGHT}p)...")
                            proxy_result = subprocess.run(proxy_cmd, capture_output=True, timeout=300)
                            
                            if proxy_result.returncode == 0 and os.path.exists(proxy_tmp_path):
                                proxy_size_mb = os.path.getsize(proxy_tmp_path) / (1024 * 1024)
                                print(f"[VIDEO UPLOAD] Proxy generated: {proxy_size_mb:.1f} MB (original: {file_size_mb:.1f} MB)")
                                
                                # Upload proxy to R2
                                proxy_key = f"datasets/{self.current_dataset_id}/video_proxies/{unique_id}.mp4"
                                with open(proxy_tmp_path, "rb") as pf:
                                    proxy_bytes = pf.read()
                                r2.upload_file(proxy_bytes, proxy_key, content_type="video/mp4")
                                proxy_r2_path = proxy_key
                                print(f"[VIDEO UPLOAD] Proxy uploaded: {proxy_key}")
                            else:
                                print(f"[VIDEO UPLOAD] Proxy transcoding failed (rc={proxy_result.returncode})")
                                if proxy_result.stderr:
                                    print(f"[VIDEO UPLOAD] FFmpeg stderr: {proxy_result.stderr.decode()[:500]}")
                        except subprocess.TimeoutExpired:
                            print("[VIDEO UPLOAD] Proxy transcoding timeout (300s) - skipping proxy")
                        except Exception as e:
                            print(f"[VIDEO UPLOAD] Proxy generation error: {e}")
                        finally:
                            # Clean up proxy temp file if it exists
                            proxy_tmp = tmp_video_path + "_proxy.mp4"
                            if os.path.exists(proxy_tmp):
                                os.unlink(proxy_tmp)
                    else:
                        if width and height:
                            print(f"[VIDEO UPLOAD] No proxy needed ({width}x{height} ≤ {VIDEO_PROXY_MAX_HEIGHT}p)")
                    
                    # Clean up temp video file
                    if os.path.exists(tmp_video_path):
                        os.unlink(tmp_video_path)
                    
                    # 4. Save to database
                    print("[VIDEO UPLOAD] Saving to database...")
                    create_video(
                        dataset_id=self.current_dataset_id,
                        filename=file.filename,
                        r2_path=video_key,
                        duration_seconds=duration_seconds,
                        frame_count=frame_count,
                        fps=fps,
                        width=width,
                        height=height,
                        thumbnail_path=thumbnail_key if thumbnail_uploaded else None,
                        proxy_r2_path=proxy_r2_path,
                    )
                    print("[VIDEO UPLOAD] Database record created")
                    
                    uploaded_count += 1
                    
                except Exception as e:
                    print(f"[VIDEO UPLOAD] Error uploading {file.filename}: {e}")
                    import traceback
                    traceback.print_exc()
                    continue
            
            # Reload videos to show new uploads
            await self._load_videos()
            
            # Show success toast
            if uploaded_count > 0:
                yield rx.toast.success(f"{uploaded_count} video(s) uploaded successfully!")
                yield rx.clear_selected_files("dataset_videos")
            
        except Exception as e:
            print(f"[VIDEO UPLOAD] Upload error: {e}")
            import traceback
            traceback.print_exc()
            self.error_message = f"Upload failed: {str(e)}"
            yield rx.toast.error("Upload failed. Please try again.")
        finally:
            self.is_uploading = False
    
    # =========================================================================
    # DUPLICATE UPLOAD HANDLERS
    # =========================================================================
    
    async def confirm_upload_all(self):
        """User chose to proceed with all files including duplicates."""
        self.show_duplicate_warning = False
        files = self.pending_files
        upload_type = self.pending_upload_type
        self._clear_pending()
        
        if upload_type == "image":
            async for event in self._do_image_upload(files):
                yield event
        else:
            async for event in self._do_video_upload(files):
                yield event
    
    async def confirm_upload_excluding_duplicates(self):
        """User chose to skip duplicate files."""
        self.show_duplicate_warning = False
        duplicates_set = set(self.duplicate_filenames)
        filtered = [f for f in self.pending_files if f.filename not in duplicates_set]
        upload_type = self.pending_upload_type
        self._clear_pending()
        
        if not filtered:
            yield rx.toast.info("No files remain after excluding duplicates.")
            yield rx.clear_selected_files("dataset_images" if upload_type == "image" else "dataset_videos")
            return
        
        if upload_type == "image":
            async for event in self._do_image_upload(filtered):
                yield event
        else:
            async for event in self._do_video_upload(filtered):
                yield event
    
    def cancel_upload(self):
        """User cancelled the upload."""
        self.show_duplicate_warning = False
        upload_type = self.pending_upload_type
        self._clear_pending()
        # Clear the file selection
        return rx.clear_selected_files("dataset_images" if upload_type == "image" else "dataset_videos")
    
    # =========================================================================
    # VIDEO DELETE CONFIRMATION
    # =========================================================================
    
    def request_delete_video(self, video_id: str):
        """Open delete confirmation modal for a video."""
        for vid in self.videos:
            if vid.id == video_id:
                self.video_to_delete_id = video_id
                self.video_to_delete_name = vid.filename
                self.show_delete_video_modal = True
                return
    
    def close_delete_video_modal(self):
        """Close the delete video confirmation modal."""
        self.show_delete_video_modal = False
        self.video_to_delete_id = ""
        self.video_to_delete_name = ""
    
    def confirm_delete_video(self):
        """Confirm and execute the video deletion."""
        video_id = self.video_to_delete_id
        self.show_delete_video_modal = False
        self.video_to_delete_id = ""
        self.video_to_delete_name = ""
        
        if video_id:
            return self.delete_video(video_id)
    
    async def delete_video(self, video_id: str):
        """Delete a video from R2 and database, including all keyframes and annotations."""
        try:
            # Find the video to get its R2 path
            video_to_delete = None
            for vid in self.videos:
                if vid.id == video_id:
                    video_to_delete = vid
                    break
            
            if not video_to_delete:
                return
            
            r2 = R2Client()
            
            # 1. Delete all keyframes and their R2 data first
            try:
                # Get and delete keyframes from database (returns list for R2 cleanup)
                keyframes = delete_video_keyframes(video_id)
                print(f"[DEBUG] Deleting {len(keyframes)} keyframes for video {video_id}")
                
                for kf in keyframes:
                    # Delete keyframe thumbnail from R2
                    thumbnail_path = kf.get("thumbnail_path")
                    if thumbnail_path:
                        try:
                            r2.delete_file(thumbnail_path)
                        except Exception as e:
                            print(f"[DEBUG] Error deleting keyframe thumbnail: {e}")
                    
                    # Delete annotation JSON from R2
                    # Path pattern: datasets/{dataset_id}/labels/{keyframe_id}.json
                    keyframe_id = kf.get("id")
                    if keyframe_id and self.current_dataset_id:
                        annotation_path = f"datasets/{self.current_dataset_id}/labels/{keyframe_id}.json"
                        try:
                            r2.delete_file(annotation_path)
                        except Exception as e:
                            # Annotation file may not exist, that's okay
                            pass
                            
            except Exception as e:
                print(f"[DEBUG] Error deleting keyframes: {e}")
            
            # 2. Delete video file, proxy, and thumbnail from R2
            try:
                if video_to_delete.r2_path:
                    r2.delete_file(video_to_delete.r2_path)
                
                if video_to_delete.thumbnail_path:
                    r2.delete_file(video_to_delete.thumbnail_path)
                
                # Delete proxy if it exists (query DB since VideoModel may not have it)
                try:
                    from backend.supabase_client import get_video as db_get_video
                    db_vid = db_get_video(video_id)
                    proxy_path = db_vid.get("proxy_r2_path", "") if db_vid else ""
                    if proxy_path:
                        r2.delete_file(proxy_path)
                        print(f"[DEBUG] Deleted proxy: {proxy_path}")
                except Exception as e:
                    print(f"[DEBUG] Error cleaning up proxy: {e}")
                    
            except Exception as e:
                print(f"[DEBUG] Error deleting video from R2: {e}")
            
            # 3. Delete video from database
            db_delete_video(video_id)
            
            # 4. Remove from local state
            self.videos = [vid for vid in self.videos if vid.id != video_id]
            
            yield rx.toast.success("Video and all keyframes deleted.")
            
        except Exception as e:
            print(f"[DEBUG] Error deleting video: {e}")
            yield rx.toast.error("Failed to delete video.")
    
    # =========================================================================
    # ZIP UPLOAD (YOLO Dataset Import)
    # =========================================================================
    
    is_uploading_zip: bool = False
    zip_upload_progress: str = ""
    
    async def handle_zip_upload(self, files: list[rx.UploadFile]):
        """
        Handle YOLO dataset ZIP upload.
        Creates new dataset and imports all images with labels.
        """
        print(f"[ZIP UPLOAD] handle_zip_upload called with {len(files) if files else 0} files")
        
        if not files or len(files) == 0:
            return
        
        file = files[0]  # Only process first file
        
        if not file.filename.lower().endswith('.zip'):
            yield rx.toast.error("Please upload a ZIP file")
            return
        
        self.is_uploading_zip = True
        self.zip_upload_progress = "Reading ZIP file..."
        yield
        
        dataset_info = None
        
        try:
            # 1. Save ZIP to temp file
            file_content = await file.read()
            print(f"[ZIP UPLOAD] Read {len(file_content)} bytes")
            
            with tempfile.NamedTemporaryFile(suffix=".zip", delete=False) as tmp:
                tmp.write(file_content)
                tmp_path = tmp.name
            
            # 2. Extract and parse ZIP structure
            self.zip_upload_progress = "Extracting dataset..."
            yield
            
            try:
                dataset_info = extract_and_parse_zip(tmp_path, file.filename)
            except ZipProcessorError as e:
                yield rx.toast.error(str(e))
                return
            finally:
                os.unlink(tmp_path)
            
            print(f"[ZIP UPLOAD] Parsed: {dataset_info.image_count} images, {dataset_info.labeled_count} labels, {len(dataset_info.classes)} classes")
            
            if dataset_info.image_count == 0:
                yield rx.toast.error("No images found in ZIP")
                return
            
            # 3. Create new dataset
            self.zip_upload_progress = f"Creating dataset '{dataset_info.dataset_name}'..."
            yield
            
            new_dataset = create_dataset(
                project_id=self.current_project_id,
                name=dataset_info.dataset_name,
                type="image",
                classes=dataset_info.classes,
            )
            
            if not new_dataset:
                yield rx.toast.error("Failed to create dataset")
                return
            
            new_dataset_id = new_dataset["id"]
            print(f"[ZIP UPLOAD] Created dataset: {new_dataset_id}")
            
            # 4. Upload images and labels
            r2 = R2Client()
            image_records = []
            
            for i, img_path in enumerate(dataset_info.image_files):
                basename = os.path.splitext(os.path.basename(img_path))[0]
                filename = os.path.basename(img_path)
                
                self.zip_upload_progress = f"Uploading {i+1}/{dataset_info.image_count}: {filename}"
                yield
                
                try:
                    # Read image
                    with open(img_path, 'rb') as f:
                        img_content = f.read()
                    
                    # Get dimensions
                    img = PILImage.open(io.BytesIO(img_content))
                    width, height = img.size
                    
                    # Generate paths
                    ext = filename.split(".")[-1].lower()
                    unique_id = str(uuid.uuid4())
                    original_key = f"datasets/{new_dataset_id}/images/{unique_id}.{ext}"
                    thumbnail_key = f"datasets/{new_dataset_id}/thumbnails/{unique_id}.{ext}"
                    
                    # Upload original
                    content_type = self._get_content_type(ext)
                    r2.upload_file(img_content, original_key, content_type=content_type)
                    
                    # Create and upload thumbnail
                    thumb_io = io.BytesIO()
                    img.thumbnail((400, 400))
                    img.save(thumb_io, format=img.format or "JPEG")
                    r2.upload_file(thumb_io.getvalue(), thumbnail_key, content_type=content_type)
                    
                    # Check for label
                    has_label = basename in dataset_info.label_files
                    
                    # If has label, upload annotations JSON
                    if has_label:
                        label_path = dataset_info.label_files[basename]
                        annotations = parse_yolo_label(label_path, width, height)
                        
                        if annotations:
                            # We'll create a placeholder image_id for now
                            # The actual ID will be assigned by Supabase
                            label_key = f"datasets/{new_dataset_id}/labels/{unique_id}.json"
                            label_json = json.dumps(annotations)
                            r2.upload_file(
                                label_json.encode('utf-8'),
                                label_key,
                                content_type="application/json"
                            )
                    
                    image_records.append({
                        "filename": filename,
                        "r2_path": original_key,
                        "width": width,
                        "height": height,
                        "labeled": has_label and len(annotations) > 0 if has_label else False,
                    })
                    
                except Exception as e:
                    print(f"[ZIP UPLOAD] Error uploading {filename}: {e}")
                    continue
            
            # 5. Bulk create database records
            self.zip_upload_progress = "Saving to database..."
            yield
            
            if image_records:
                bulk_create_images(new_dataset_id, image_records)
            
            # 6. Clean up
            dataset_info.cleanup()
            
            # Success!
            yield rx.toast.success(
                f"Imported '{dataset_info.dataset_name}': {len(image_records)} images, {dataset_info.labeled_count} labeled"
            )
            yield rx.clear_selected_files("dataset_zip")
            
            # Redirect to new dataset
            yield rx.redirect(f"/projects/{self.current_project_id}/datasets/{new_dataset_id}")
            
        except Exception as e:
            print(f"[ZIP UPLOAD] Error: {e}")
            import traceback
            traceback.print_exc()
            yield rx.toast.error(f"Import failed: {str(e)}")
        finally:
            if dataset_info:
                dataset_info.cleanup()
            self.is_uploading_zip = False
            self.zip_upload_progress = ""

    # =========================================================================
    # COMPUTED VARS FOR STATS
    # =========================================================================
    
    @rx.var
    def total_items(self) -> int:
        """Total number of items (images or videos) in the dataset."""
        if self.dataset_type == "video":
            return len(self.videos)
        return len(self.images)
    
    @rx.var
    def labeling_progress(self) -> int:
        """Percentage of items that are labeled."""
        total = self.total_items
        if total == 0:
            return 0
        labeled = self.labeled_count
        return int((labeled / total) * 100)
    
    @rx.var
    def class_distribution_data(self) -> list[dict]:
        """Class counts formatted for chart display."""
        return [
            {
                "class_name": (name[:12] + "…") if len(name) > 12 else name,
                "count": count,
            }
            for name, count in sorted(self.class_counts.items(), key=lambda x: x[1], reverse=True)
        ]
    
    @rx.var
    def has_selection(self) -> bool:
        """Check if any items are selected."""
        return len(self.selected_image_ids) > 0 or len(self.selected_video_ids) > 0
    
    @rx.var
    def selection_count(self) -> int:
        """Count of selected items."""
        return len(self.selected_image_ids) + len(self.selected_video_ids)
    
    # =========================================================================
    # SELECTION METHODS
    # =========================================================================
    
    def toggle_image_selection(self, image_id: str):
        """Toggle selection for an image."""
        if image_id in self.selected_image_ids:
            self.selected_image_ids = [id for id in self.selected_image_ids if id != image_id]
        else:
            self.selected_image_ids = self.selected_image_ids + [image_id]
    
    def toggle_video_selection(self, video_id: str):
        """Toggle selection for a video."""
        if video_id in self.selected_video_ids:
            self.selected_video_ids = [id for id in self.selected_video_ids if id != video_id]
        else:
            self.selected_video_ids = self.selected_video_ids + [video_id]
    
    def select_all_items(self):
        """Select all items in the current dataset."""
        if self.dataset_type == "video":
            self.selected_video_ids = [v.id for v in self.videos]
        else:
            self.selected_image_ids = [img.id for img in self.images]
    
    def clear_selection(self):
        """Clear all selections."""
        self.selected_image_ids = []
        self.selected_video_ids = []
    
    # =========================================================================
    # BULK DELETE METHODS
    # =========================================================================
    
    async def bulk_delete_selected(self):
        """Delete all selected items (R2 files + database rows) in bulk."""
        from backend.supabase_client import bulk_delete_images, bulk_delete_videos
        
        try:
            r2 = R2Client()
            
            if self.dataset_type == "video" and self.selected_video_ids:
                # R2 cleanup (shared helper)
                for vid in (v for v in self.videos if v.id in self.selected_video_ids):
                    self._delete_video_r2_files(r2, vid)
                
                deleted_count = bulk_delete_videos(self.selected_video_ids)
                deleted_ids = set(self.selected_video_ids)
                self.videos = [v for v in self.videos if v.id not in deleted_ids]
                self.selected_video_ids = []
                yield rx.toast.success(f"Deleted {deleted_count} video(s)")
                
            elif self.selected_image_ids:
                # R2 cleanup (shared helper)
                for img in (i for i in self.images if i.id in self.selected_image_ids):
                    self._delete_image_r2_files(r2, img.r2_path)
                
                deleted_count = bulk_delete_images(self.selected_image_ids)
                deleted_ids = set(self.selected_image_ids)
                self.images = [img for img in self.images if img.id not in deleted_ids]
                self.selected_image_ids = []
                yield rx.toast.success(f"Deleted {deleted_count} image(s)")
                
        except Exception as e:
            print(f"[DEBUG] Error bulk deleting: {e}")
            yield rx.toast.error(f"Failed to delete items: {e}")
    
    # =========================================================================
    # VIDEO LABELS BREAKDOWN
    # =========================================================================
    
    async def _load_video_labels_breakdown(self):
        """Load label counts grouped by video for video datasets."""
        try:
            from backend.supabase_client import get_video_keyframes
            
            breakdown = []
            for video in self.videos:
                # Get all keyframes for this video
                keyframes = get_video_keyframes(video.id)
                
                # Count labels per class from keyframes
                labels = {}
                total_labels = 0
                for kf in keyframes:
                    annotations = kf.get("annotations") or []
                    for ann in annotations:
                        class_name = ann.get("class_name", "Unknown")
                        labels[class_name] = labels.get(class_name, 0) + 1
                        total_labels += 1
                
                breakdown.append(VideoLabelsBreakdown(
                    video_id=video.id,
                    video_name=video.filename,
                    label_count=total_labels,
                    labels=labels,
                ))
            
            self.video_labels_breakdown = breakdown
        except Exception as e:
            print(f"[DEBUG] Error loading video labels breakdown: {e}")
    

    
    # =========================================================================
    # BATCH LABEL OPERATIONS
    # =========================================================================
    
    def open_reassign_labels_modal(self, video_id: str, class_name: str):
        """Open modal to reassign all labels of a class in a video to a different class."""
        self.target_video_id = video_id
        self.target_class_name = class_name
        self.reassign_to_class = ""
        self.show_reassign_modal = True
    
    def close_reassign_modal(self):
        """Close the reassign labels modal."""
        self.show_reassign_modal = False
        self.target_video_id = ""
        self.target_class_name = ""
        self.reassign_to_class = ""
    
    def set_reassign_to_class(self, class_name: str):
        """Set the target class for reassignment."""
        self.reassign_to_class = class_name
    
    async def confirm_reassign_labels(self):
        """Reassign all labels of target class in target video to the new class."""
        if not self.reassign_to_class or self.reassign_to_class == self.target_class_name:
            self.close_reassign_modal()
            return
        
        self.is_processing_class = True
        yield
        
        try:
            from backend.supabase_client import get_supabase
            supabase = get_supabase()
            
            old_class = self.target_class_name
            new_class = self.reassign_to_class
            video_id = self.target_video_id
            
            # Get new class index
            new_class_idx = self.project_classes.index(new_class) if new_class in self.project_classes else 0
            
            # Get all keyframes for this video
            keyframes_result = (
                supabase.table("keyframes")
                .select("id, annotations")
                .eq("video_id", video_id)
                .execute()
            )
            
            updated_count = 0
            for kf in (keyframes_result.data or []):
                annotations = kf.get("annotations", []) or []
                modified = False
                
                for ann in annotations:
                    if ann.get("class_name") == old_class:
                        ann["class_name"] = new_class
                        ann["class_id"] = new_class_idx
                        modified = True
                
                if modified:
                    supabase.table("keyframes").update({"annotations": annotations}).eq("id", kf["id"]).execute()
                    updated_count += 1
            
            # Update class_counts locally
            if old_class in self.class_counts:
                old_count = self.class_counts.get(old_class, 0)
                new_counts = dict(self.class_counts)
                # Move counts from old class to new class
                new_counts[new_class] = new_counts.get(new_class, 0) + old_count
                new_counts[old_class] = 0
                # Clean up zero counts
                self.class_counts = {k: v for k, v in new_counts.items() if v > 0}
            
            # Reload video labels breakdown
            if self.dataset_type == "video":
                await self._load_video_labels_breakdown()
            
            self.close_reassign_modal()
            yield rx.toast.success(f"Reassigned labels from '{old_class}' to '{new_class}' in {updated_count} keyframes")
            
        except Exception as e:
            print(f"[DEBUG] Error reassigning labels: {e}")
            import traceback
            traceback.print_exc()
            yield rx.toast.error(f"Failed to reassign labels: {e}")
        finally:
            self.is_processing_class = False
    
    def open_delete_labels_modal(self, video_id: str, class_name: str):
        """Open modal to delete all labels of a class in a video."""
        self.target_video_id = video_id
        self.target_class_name = class_name
        self.show_delete_labels_modal = True
    
    def close_delete_labels_modal(self):
        """Close the delete labels modal."""
        self.show_delete_labels_modal = False
        self.target_video_id = ""
        self.target_class_name = ""
    
    async def confirm_delete_labels(self):
        """Delete all labels of target class in target video."""
        self.is_processing_class = True
        yield
        
        try:
            from backend.supabase_client import get_supabase
            supabase = get_supabase()
            
            class_name = self.target_class_name
            video_id = self.target_video_id
            
            # Get all keyframes for this video
            keyframes_result = (
                supabase.table("keyframes")
                .select("id, annotations, annotation_count")
                .eq("video_id", video_id)
                .execute()
            )
            
            updated_count = 0
            deleted_annotations = 0
            for kf in (keyframes_result.data or []):
                annotations = kf.get("annotations", []) or []
                original_count = len(annotations)
                
                # Filter out annotations with target class
                new_annotations = [ann for ann in annotations if ann.get("class_name") != class_name]
                
                if len(new_annotations) < original_count:
                    deleted_annotations += original_count - len(new_annotations)
                    supabase.table("keyframes").update({
                        "annotations": new_annotations,
                        "annotation_count": len(new_annotations)
                    }).eq("id", kf["id"]).execute()
                    updated_count += 1
            
            # Update class_counts locally (subtract deleted annotations)
            if class_name in self.class_counts:
                new_counts = dict(self.class_counts)
                new_counts[class_name] = max(0, new_counts.get(class_name, 0) - deleted_annotations)
                if new_counts[class_name] == 0:
                    del new_counts[class_name]
                self.class_counts = new_counts
            
            # Reload video labels breakdown
            if self.dataset_type == "video":
                await self._load_video_labels_breakdown()
            
            self.close_delete_labels_modal()
            yield rx.toast.success(f"Deleted {deleted_annotations} '{class_name}' labels from {updated_count} keyframes")
            
        except Exception as e:
            print(f"[DEBUG] Error deleting labels: {e}")
            import traceback
            traceback.print_exc()
            yield rx.toast.error(f"Failed to delete labels: {e}")
        finally:
            self.is_processing_class = False
    
    @rx.var
    def available_classes_for_reassign(self) -> list[str]:
        """Get list of classes available for reassignment (excluding target class)."""
        return [c for c in self.project_classes if c != self.target_class_name]

    # =========================================================================
    # DELETE CLASS ANNOTATIONS (DATASET-WIDE)
    # =========================================================================
    
    @rx.var
    def can_confirm_delete_class_annotations(self) -> bool:
        """Returns True if user has typed 'delete' to confirm."""
        return self.delete_class_confirmation.lower().strip() == "delete"
    
    def open_delete_class_annotations_modal(self, class_name: str):
        """Open modal to delete all annotations for a class in this dataset."""
        self.delete_class_annotations_name = class_name
        self.delete_class_annotations_count = self.class_counts.get(class_name, 0)
        self.delete_class_confirmation = ""
        self.show_delete_class_annotations_modal = True
    
    def close_delete_class_annotations_modal(self):
        """Close the delete class annotations modal."""
        self.show_delete_class_annotations_modal = False
        self.delete_class_annotations_name = ""
        self.delete_class_annotations_count = 0
        self.delete_class_confirmation = ""
    
    def set_delete_class_confirmation(self, value: str):
        """Set the confirmation text for delete class annotations."""
        self.delete_class_confirmation = value
    
    async def confirm_delete_class_annotations(self):
        """Delete all annotations for target class in current dataset."""
        if not self.can_confirm_delete_class_annotations:
            return
        
        self.is_deleting_class_annotations = True
        yield
        
        try:
            from backend.supabase_client import get_supabase
            supabase = get_supabase()
            
            class_name = self.delete_class_annotations_name
            deleted_annotations = 0
            updated_count = 0
            
            if self.dataset_type == "video":
                # Delete from keyframes for all videos in this dataset
                for video in self.videos:
                    keyframes_result = (
                        supabase.table("keyframes")
                        .select("id, annotations, annotation_count")
                        .eq("video_id", video.id)
                        .execute()
                    )
                    
                    for kf in (keyframes_result.data or []):
                        annotations = kf.get("annotations", []) or []
                        original_count = len(annotations)
                        
                        # Filter out annotations with target class
                        new_annotations = [ann for ann in annotations if ann.get("class_name") != class_name]
                        
                        if len(new_annotations) < original_count:
                            deleted_annotations += original_count - len(new_annotations)
                            supabase.table("keyframes").update({
                                "annotations": new_annotations,
                                "annotation_count": len(new_annotations)
                            }).eq("id", kf["id"]).execute()
                            updated_count += 1
            else:
                # Delete from images in this dataset
                from backend.r2_storage import R2Client
                r2 = R2Client()
                
                images_result = (
                    supabase.table("images")
                    .select("id, annotations")
                    .eq("dataset_id", self.current_dataset_id)
                    .execute()
                )
                
                for img in (images_result.data or []):
                    annotations = img.get("annotations", []) or []
                    original_count = len(annotations)
                    
                    # Filter out annotations with target class
                    new_annotations = [ann for ann in annotations if ann.get("class_name") != class_name]
                    
                    if len(new_annotations) < original_count:
                        deleted_annotations += original_count - len(new_annotations)
                        update_data = {
                            "annotations": new_annotations,
                            "annotation_count": len(new_annotations),  # CRITICAL: Update count for autolabel
                        }
                        # Update labeled flag if no annotations remain
                        if len(new_annotations) == 0:
                            update_data["labeled"] = False
                        supabase.table("images").update(update_data).eq("id", img["id"]).execute()
                        updated_count += 1
                        
                        # Update R2 label file
                        label_path = f"datasets/{self.current_dataset_id}/labels/{img['id']}.txt"
                        try:
                            if len(new_annotations) == 0:
                                # Delete the label file if no annotations remain
                                r2.delete_file(label_path)
                            else:
                                # Rewrite label file with remaining annotations
                                yolo_lines = []
                                for ann in new_annotations:
                                    c_id = ann.get("class_id", 0)
                                    x = ann.get("x", 0)
                                    y = ann.get("y", 0)
                                    w = ann.get("width", 0)
                                    h = ann.get("height", 0)
                                    # Convert to YOLO format (center x, center y, width, height)
                                    x_center = x + w / 2
                                    y_center = y + h / 2
                                    yolo_lines.append(f"{c_id} {x_center:.6f} {y_center:.6f} {w:.6f} {h:.6f}")
                                
                                new_content = "\n".join(yolo_lines)
                                r2.upload_file(
                                    file_bytes=new_content.encode('utf-8'),
                                    path=label_path,
                                    content_type='text/plain'
                                )
                        except Exception as r2_err:
                            print(f"[WARN] Failed to update R2 label file {label_path}: {r2_err}")
            
            # Update local class_counts
            if class_name in self.class_counts:
                new_counts = dict(self.class_counts)
                del new_counts[class_name]
                self.class_counts = new_counts
            
            # Reload video labels breakdown if video dataset
            if self.dataset_type == "video":
                await self._load_video_labels_breakdown()
            else:
                # Reload images to refresh labeled flags
                await self._load_images()
            
            self.close_delete_class_annotations_modal()
            yield rx.toast.success(f"Deleted {deleted_annotations} '{class_name}' annotations from {updated_count} items")
            
        except Exception as e:
            print(f"[DEBUG] Error deleting class annotations: {e}")
            import traceback
            traceback.print_exc()
            yield rx.toast.error(f"Failed to delete annotations: {e}")
        finally:
            self.is_deleting_class_annotations = False

