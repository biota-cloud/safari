"""
Project Detail State — State management for the project detail page.

Handles:
- Loading project and images
- Uploading new images to R2
- Deleting images
"""

import reflex as rx
import uuid
from typing import Optional
from PIL import Image as PILImage
import io

from app_state import AuthState
from backend.supabase_client import (
    get_project,
    get_project_images,
    create_image,
    delete_image as db_delete_image,
    update_project,
    touch_project_accessed,
)
from backend.r2_storage import R2Client
from pydantic import BaseModel


class ImageModel(BaseModel):
    """Typed model for image data."""
    id: str = ""
    project_id: str = ""
    filename: str = ""
    r2_path: str = ""
    width: int = 0
    height: int = 0
    labeled: bool = False
    created_at: str = ""
    # Presigned URL for display (generated on load)
    display_url: str = ""


class ProjectDetailState(rx.State):
    """State for the project detail page with upload functionality."""
    
    # Project data (using current_project_id to avoid conflict with route param)
    current_project_id: str = ""
    project_name: str = ""
    project_classes: list[str] = []
    
    # Images
    images: list[ImageModel] = []
    
    # Loading states
    is_loading: bool = False  # Default to False to prevent skeleton flash on re-navigation
    is_uploading: bool = False
    _has_loaded_once: bool = False  # Track first load for skeleton display
    
    # Error handling
    error_message: str = ""
    
    # Class management
    new_class_name: str = ""
    show_delete_class_modal: bool = False
    class_to_delete_idx: int = -1
    class_to_delete_name: str = ""
    delete_class_confirmation_text: str = ""  # Type "delete" to confirm
    editing_class_idx: int = -1
    editing_class_name: str = ""
    is_renaming_class: bool = False  # Lock UI during rename operation
    
    async def load_project(self):
        """Load project details and images on page load."""
        # Only show skeleton on first load to prevent flickering on re-navigation
        if not self._has_loaded_once:
            self.is_loading = True
            yield
        self.error_message = ""
        
        try:
            # Get project_id from route
            self.current_project_id = self.router.page.params.get("project_id", "")
            
            if not self.current_project_id:
                self.error_message = "No project ID provided."
                self.is_loading = False
                return
            
            # Fetch project data
            project = get_project(self.current_project_id)
            if not project:
                self.error_message = "Project not found."
                self.is_loading = False
                return
            
            self.project_name = project.get("name", "")
            self.project_classes = project.get("classes", []) or []
            
            # Touch access timestamp (for dashboard sorting)
            touch_project_accessed(self.current_project_id)
            
            # Fetch images
            await self._load_images()
            
        except Exception as e:
            print(f"[DEBUG] Error loading project: {e}")
            self.error_message = f"Error loading project: {str(e)}"
        finally:
            self.is_loading = False
            self._has_loaded_once = True
    
    async def _load_images(self):
        """Load images for the current project with presigned URLs."""
        try:
            raw_images = get_project_images(self.current_project_id)
            r2 = R2Client()
            
            self.images = []
            for img in raw_images:
                # Generate presigned URL for display
                # Try to use thumbnail path if possible (convention: images/ -> thumbnails/)
                display_url = ""
                r2_path = img.get("r2_path", "")
                
                # Check if we should assume a thumbnail exists (if derived from images/*)
                # For backward compatibility, this might be risky if thumbnail doesn't exist,
                # but users can re-upload.
                thumbnail_path = r2_path.replace("/images/", "/thumbnails/") if "/images/" in r2_path else r2_path
                
                if thumbnail_path:
                    try:
                        # Use thumbnail for grid view
                        display_url = r2.generate_presigned_url(thumbnail_path)
                    except Exception as e:
                        print(f"[DEBUG] Error generating URL for {thumbnail_path}: {e}")
                
                self.images.append(ImageModel(
                    id=str(img.get("id", "")),
                    project_id=str(img.get("project_id", "")),
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
    
    async def handle_upload(self, files: list[rx.UploadFile]):
        """
        Handle uploaded files — save to R2 and database.
        
        Args:
            files: List of uploaded files from rx.upload
        """
        if not files:
            return
        
        self.is_uploading = True
        self.error_message = ""
        yield
        
        try:
            r2 = R2Client()
            uploaded_count = 0
            
            for file in files:
                try:
                    # Read file content
                    file_content = await file.read()
                    
                    # 1. Process Image and Generate Thumbnail
                    img = PILImage.open(io.BytesIO(file_content))
                    width, height = img.size
                    
                    # Generate unique filename
                    ext = file.filename.split(".")[-1].lower() if "." in file.filename else "jpg"
                    unique_id = str(uuid.uuid4())
                    
                    # Paths
                    original_key = f"projects/{self.current_project_id}/images/{unique_id}.{ext}"
                    thumbnail_key = f"projects/{self.current_project_id}/thumbnails/{unique_id}.{ext}"
                    
                    # Determine content type
                    content_type = self._get_content_type(ext)
                    
                    # 2. Upload Original
                    r2.upload_file(file_content, original_key, content_type=content_type)
                    
                    # 3. Create and Upload Thumbnail
                    thumb_io = io.BytesIO()
                    # Convert to RGB if needed (e.g., PNG with alpha) to save as JPEG safely?
                    # Or keep original format. Let's keep original format to preserve transparency if PNG.
                    img.thumbnail((400, 400)) # Resize in-place
                    img.save(thumb_io, format=img.format or "JPEG")
                    thumb_bytes = thumb_io.getvalue()
                    
                    r2.upload_file(thumb_bytes, thumbnail_key, content_type=content_type)
                    
                    # 4. Save to database
                    create_image(
                        project_id=self.current_project_id,
                        filename=file.filename,
                        r2_path=original_key,
                        width=width,
                        height=height,
                    )
                    
                    uploaded_count += 1
                    
                except Exception as e:
                    print(f"[DEBUG] Error uploading {file.filename}: {e}")
                    continue
            
            # Reload images to show new uploads
            await self._load_images()
            
            # Show success toast
            if uploaded_count > 0:
                yield rx.toast.success(f"{uploaded_count} image(s) uploaded successfully!")
                yield rx.clear_selected_files("project_images")
            
        except Exception as e:
            print(f"[DEBUG] Upload error: {e}")
            self.error_message = f"Upload failed: {str(e)}"
            yield rx.toast.error("Upload failed. Please try again.")
        finally:
            self.is_uploading = False
    
    def _get_image_dimensions(self, file_content: bytes) -> tuple[int, int]:
        """Extract width and height from image bytes."""
        try:
            img = PILImage.open(io.BytesIO(file_content))
            return img.size  # (width, height)
        except Exception:
            return (0, 0)
    
    def _get_content_type(self, ext: str) -> str:
        """Get MIME type for file extension."""
        types = {
            "jpg": "image/jpeg",
            "jpeg": "image/jpeg",
            "png": "image/png",
            "webp": "image/webp",
        }
        return types.get(ext.lower(), "image/jpeg")
    
    async def delete_image(self, image_id: str):
        """Delete an image from R2 and database."""
        try:
            # Find the image to get its R2 path
            image_to_delete = None
            for img in self.images:
                if img.id == image_id:
                    image_to_delete = img
                    break
            
            if not image_to_delete:
                return
            
            # Delete from R2
            if image_to_delete.r2_path:
                try:
                    r2 = R2Client()
                    # Delete original
                    r2.delete_file(image_to_delete.r2_path)
                    
                    # Delete thumbnail (derived path)
                    if "/images/" in image_to_delete.r2_path:
                        thumbnail_path = image_to_delete.r2_path.replace("/images/", "/thumbnails/")
                        r2.delete_file(thumbnail_path)
                        
                except Exception as e:
                    print(f"[DEBUG] Error deleting from R2: {e}")
            
            # Delete from database
            db_delete_image(image_id)
            
            # Remove from local state
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
        """Get number of labeled images."""
        return len([img for img in self.images if img.labeled])
    
    @rx.var
    def has_images(self) -> bool:
        """Check if project has any images."""
        return len(self.images) > 0

    # =========================================================================
    # CLASS MANAGEMENT
    # =========================================================================
    
    def set_new_class_name(self, name: str):
        """Update the new class name input."""
        self.new_class_name = name
    
    def add_class(self):
        """Add a new class to the project."""
        from modules.datasets.state import DatasetsState
        
        name = self.new_class_name.strip()
        if not name or name in self.project_classes:
            return
        
        self.project_classes = self.project_classes + [name]
        update_project(self.current_project_id, classes=self.project_classes)
        self.new_class_name = ""
        
        # Sync with DatasetsState to update the chart
        return DatasetsState.refresh_project_classes(self.project_classes)
    
    def handle_add_class_keydown(self, key: str):
        """Handle Enter key to add class."""
        if key == "Enter":
            return self.add_class()
    
    def start_edit_class(self, idx: int):
        """Start editing a class name."""
        if 0 <= idx < len(self.project_classes):
            self.editing_class_idx = idx
            self.editing_class_name = self.project_classes[idx]
    
    def set_editing_class_name(self, name: str):
        """Update the editing class name."""
        self.editing_class_name = name
    
    async def save_class_edit(self):
        """Save the edited class name and update counts + annotations.
        
        Supports two modes:
        1. Rename: new_name doesn't exist → rename class in project and annotations
        2. Merge: new_name exists → rename annotations to target class, then delete source class
        """
        from modules.datasets.state import DatasetsState
        from backend.supabase_client import rename_class_in_annotations
        
        idx = self.editing_class_idx
        new_name = self.editing_class_name.strip()
        
        if idx < 0 or idx >= len(self.project_classes):
            self.editing_class_idx = -1
            return
        
        if not new_name or new_name == self.project_classes[idx]:
            self.editing_class_idx = -1
            return
        
        # Get old name before update
        old_name = self.project_classes[idx]
        old_idx = idx
        
        # Detect merge vs rename
        is_merge = new_name in self.project_classes
        new_idx = self.project_classes.index(new_name) if is_merge else None
        
        # Lock UI during rename
        self.is_renaming_class = True
        self.editing_class_idx = -1  # Hide edit input immediately
        yield
        
        # Rename in all annotations with progress feedback
        total_updated = 0
        operation_label = "Merging" if is_merge else "Renaming"
        for updated, total in rename_class_in_annotations(
            self.current_project_id,
            old_name,
            new_name,
            old_idx=old_idx if is_merge else None,
            new_idx=new_idx,
            is_merge=is_merge,
        ):
            total_updated = updated
            if updated == 0:
                yield rx.toast.info(f"{operation_label} '{old_name}' → '{new_name}' in {total} labels...", id="rename_progress")
            else:
                yield rx.toast.info(f"{operation_label}... {updated}/{total} labels", id="rename_progress")
            yield
        
        # Update project classes list
        if is_merge:
            # Merge: remove the old class (annotations already point to new_name)
            classes = [c for c in self.project_classes if c != old_name]
        else:
            # Rename: replace old name with new name
            classes = list(self.project_classes)
            classes[idx] = new_name
        
        self.project_classes = classes
        update_project(self.current_project_id, classes=self.project_classes)
        
        # Unlock UI
        self.is_renaming_class = False
        
        # Show success toast with count
        if is_merge:
            yield rx.toast.success(f"Merged '{old_name}' → '{new_name}' ({total_updated} labels updated)")
        elif total_updated > 0:
            yield rx.toast.success(f"Renamed '{old_name}' → '{new_name}' in {total_updated} labels")
        else:
            yield rx.toast.success(f"Renamed class '{old_name}' → '{new_name}'")
        
        # Sync with DatasetsState
        yield DatasetsState.refresh_project_classes(self.project_classes)
    
    def cancel_class_edit(self):
        """Cancel editing a class."""
        self.editing_class_idx = -1
        self.editing_class_name = ""
    
    def handle_edit_class_keydown(self, key: str):
        """Handle keyboard shortcuts in edit mode."""
        if key == "Enter":
            return self.save_class_edit()
        elif key == "Escape":
            self.cancel_class_edit()
    
    def request_delete_class(self, idx: int):
        """Open delete confirmation modal for a class."""
        if 0 <= idx < len(self.project_classes):
            self.class_to_delete_idx = idx
            self.class_to_delete_name = self.project_classes[idx]
            self.show_delete_class_modal = True
    
    def cancel_delete_class(self):
        """Cancel class deletion."""
        self.show_delete_class_modal = False
        self.class_to_delete_idx = -1
        self.class_to_delete_name = ""
        self.delete_class_confirmation_text = ""
    
    @rx.var
    def can_confirm_delete_class(self) -> bool:
        """Check if user has typed 'delete' to confirm."""
        return self.delete_class_confirmation_text.strip().lower() == "delete"
    
    def set_delete_class_confirmation_text(self, text: str):
        """Set the delete confirmation text."""
        self.delete_class_confirmation_text = text
    
    def handle_delete_class_keydown(self, key: str):
        """Handle Enter key in delete confirmation input."""
        if key == "Enter" and self.can_confirm_delete_class:
            return self.confirm_delete_class()
    
    def confirm_delete_class(self):
        """Delete the class from project, clean up counts and annotations."""
        from modules.datasets.state import DatasetsState
        from backend.supabase_client import delete_class_from_annotations
        
        # Validate confirmation
        if not self.can_confirm_delete_class:
            return
        
        idx = self.class_to_delete_idx
        if idx < 0 or idx >= len(self.project_classes):
            self.show_delete_class_modal = False
            self.delete_class_confirmation_text = ""
            return
        
        # Get the class name before removal
        class_name = self.project_classes[idx]
        
        # Remove class from project classes list
        classes = list(self.project_classes)
        classes.pop(idx)
        self.project_classes = classes
        update_project(self.current_project_id, classes=self.project_classes)
        
        # Delete annotations with this class and shift remaining class IDs
        delete_class_from_annotations(self.current_project_id, class_name, idx, self.project_classes)
        
        # Close modal and reset state
        self.show_delete_class_modal = False
        self.class_to_delete_idx = -1
        self.class_to_delete_name = ""
        self.delete_class_confirmation_text = ""
        
        # Sync with DatasetsState to update chart
        return DatasetsState.refresh_project_classes(self.project_classes)
