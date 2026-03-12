"""
Labeling State — State management for the canvas-based labeling editor.

Handles:
- Loading images from a dataset (within a project)
- Managing annotation data
- Canvas state (zoom, pan, selection)
"""

import reflex as rx
from typing import Optional
from pydantic import BaseModel
import json
import uuid
import threading

from app_state import AuthState
from backend.supabase_client import get_project, get_dataset, get_dataset_images, update_dataset, update_project, update_image, delete_image as db_delete_image, get_user_preferences, update_user_preferences, get_dataset_image_annotations, get_image_annotations, update_image_annotations, touch_dataset_accessed, get_user_local_machines
from backend.r2_storage import R2Client


def _auto_generate_thumbnails(image_id: str, dataset_id: str, project_id: str, first_annotation: dict):
    """Auto-generate project/dataset thumbnails if missing (runs in background thread).
    
    Triggered when the user leaves an image that has annotations, ensuring the 
    thumbnail reflects the final corrected label rather than the first draft.
    """
    try:
        from backend.supabase_client import get_project, get_dataset, update_project, update_dataset, get_image
        from backend.core.thumbnail_generator import generate_label_thumbnail
        
        r2 = R2Client()
        
        # Check if project needs thumbnail
        project = get_project(project_id)
        project_needs_thumb = project and not project.get("thumbnail_r2_path")
        
        # Check if dataset needs thumbnail
        dataset = get_dataset(dataset_id)
        dataset_needs_thumb = dataset and not dataset.get("thumbnail_r2_path")
        
        if not project_needs_thumb and not dataset_needs_thumb:
            return  # Both already have thumbnails
        
        # Get image bytes for thumbnail generation
        image = get_image(image_id)
        if not image or not image.get("r2_path"):
            return
        
        image_url = r2.generate_presigned_url(image["r2_path"])
        if not image_url:
            return
        
        import requests
        response = requests.get(image_url, timeout=10)
        if response.status_code != 200:
            return
        image_bytes = response.content
        
        # Generate thumbnail
        thumb_bytes = generate_label_thumbnail(image_bytes, first_annotation)
        if not thumb_bytes:
            return
        
        # Save project thumbnail if needed
        if project_needs_thumb:
            thumb_path = f"projects/{project_id}/thumbnail.jpg"
            r2.upload_file(thumb_bytes, thumb_path, content_type="image/jpeg")
            update_project(project_id, thumbnail_r2_path=thumb_path)
            print(f"[AutoThumbnail] Generated project thumbnail for {project_id[:8]}...")
        
        # Save dataset thumbnail if needed
        if dataset_needs_thumb:
            thumb_path = f"datasets/{dataset_id}/thumbnail.jpg"
            r2.upload_file(thumb_bytes, thumb_path, content_type="image/jpeg")
            update_dataset(dataset_id, thumbnail_r2_path=thumb_path)
            print(f"[AutoThumbnail] Generated dataset thumbnail for {dataset_id[:8]}...")
            
    except Exception as e:
        print(f"[AutoThumbnail] Error: {e}")



class ImageModel(BaseModel):
    """Typed model for image data in the labeling context."""
    id: str = ""
    filename: str = ""
    r2_path: str = ""
    width: int = 0
    height: int = 0
    labeled: bool = False
    annotation_count: int = 0  # Number of annotations on this image
    thumbnail_url: str = ""
    full_url: str = ""


class LabelingState(rx.State):
    """State for the labeling editor."""
    
    # Project and Dataset context
    current_project_id: str = ""
    current_dataset_id: str = ""
    project_name: str = ""
    dataset_name: str = ""
    project_classes: list[str] = []
    
    # All images in the project (for sidebar navigation)
    images: list[ImageModel] = []
    
    # Currently loaded image
    current_image_id: str = ""
    current_image_url: str = ""
    image_width: int = 0
    image_height: int = 0
    
    # Annotations for current image
    annotations: list[dict] = []
    selected_annotation_id: Optional[str] = None
    
    # Internal store for all annotations: image_id -> list of annotations
    _saved_annotations: dict[str, list] = {}
    
    # Autosave state (Phase 1.9)
    save_status: str = ""  # "", "saving", "saved"
    is_dirty: bool = False  # Track if current image has unsaved changes
    _label_cache: dict[str, list] = {}  # Pre-fetched labels by image_id
    _pending_saves: dict[str, dict] = {}  # Queue of {image_id: {annotations, dataset_id}} to save
    _last_saved_annotations: dict[str, list] = {}  # Track last saved annotations for class count diff
    
    # Tool state
    current_tool: str = "select"  # "select" or "draw"
    is_drawing: bool = False
    
    # Class management
    current_class_id: int = 0
    new_class_name: str = ""  # For add class input
    show_delete_class_modal: bool = False
    class_to_delete_idx: int = -1
    class_to_delete_name: str = ""
    
    # Keyboard shortcuts help (1.11.8)
    show_shortcuts_help: bool = False
    
    # Multi-selection state
    selected_image_ids: list[str] = []  # List of selected image IDs
    last_clicked_image_idx: int = -1  # For shift-click range selection
    show_bulk_delete_modal: bool = False
    is_bulk_deleting: bool = False
    pending_longpress_image_id: str = ""  # Set by JS, read by toggle method
    
    # Auto-labeling state (SAM3 and YOLO modes)
    autolabel_prompt: str = ""
    autolabel_class_id: int = 0  # Class ID to assign to detections (SAM3 mode)
    autolabel_confidence: float = 0.5  # Confidence threshold (raised for better quality)
    is_autolabeling: bool = False
    autolabel_job_id: str = ""
    autolabel_logs: str = ""
    autolabel_error: str = ""
    show_autolabel_panel: bool = False  # Legacy - now using modal
    show_autolabel_logs: bool = False
    is_polling_autolabel: bool = False
    
    # Autolabel modal state (new)
    show_autolabel_modal: bool = False
    autolabel_mode: str = "sam3"  # "sam3" or "yolo"
    selected_autolabel_model_id: str = ""
    available_autolabel_models: list[dict] = []  # Models with volume_path
    
    # Compute target for autolabel (matches training/inference pattern)
    compute_target: str = "cloud"  # "cloud" or "local"
    selected_machine: str = ""     # machine name for local target
    local_machines: list[dict] = []  # cached list of user's machines
    
    # SAM3 prompt-to-class mapping
    autolabel_prompt_terms: list[str] = []  # Parsed prompt terms ["animal", "bird"]
    autolabel_class_mappings: list[int] = []  # Class ID for each term (-1 = unmapped)
    autolabel_bbox_padding: float = 0.03  # SAM3 box padding fraction (0.03 = 3%)
    
    # Mask generation options (SAM3 mode only)
    autolabel_generate_bboxes: bool = True
    autolabel_generate_masks: bool = False
    show_mask_overlays: bool = True  # Toggle mask visibility in editor
    
    # Focus mode and fullscreen state
    focus_mode: bool = False  # Hide all panels for pure annotation view
    is_fullscreen: bool = False  # Track browser fullscreen state
    
    # Empty images stats modal state
    show_empty_stats_modal: bool = False
    empty_delete_confirmation: str = ""  # User must type "delete" to confirm
    is_deleting_empty_images: bool = False
    
    # Right-click context menu state
    context_menu_open: bool = False
    context_menu_x: int = 0
    context_menu_y: int = 0
    context_menu_annotation_id: str = ""  # Annotation ID for context actions
    
    def toggle_focus_mode(self, _value=None):
        """Toggle focus mode - hide all panels for pure annotation view."""
        self.focus_mode = not self.focus_mode
        print(f"[Labeling] Focus mode: {self.focus_mode}")
        
        # Consistent zoom change (1.85 in focus, 1.0 back)
        target_scale = 1.85 if self.focus_mode else 1.0
        # Force canvas resize after the 300ms panel slide animation completes
        # by dispatching a native resize event, which the ResizeObserver picks up
        return rx.call_script(
            f"window.animateTransform && window.animateTransform({target_scale}, 0, 0);"
            " setTimeout(function() { window.dispatchEvent(new Event('resize')); }, 350);"
        )
    
    def reset_view(self):
        """Reset zoom and pan to default — delegates to JS."""
        target_scale = 1.85 if self.focus_mode else 1.0
        return rx.call_script(f"window.animateTransform && window.animateTransform({target_scale}, 0, 0)")
    
    def toggle_fullscreen(self, _value=None):
        """
        No longer used for triggering - called only if the hidden input is manually triggered.
        Actual toggle is handled in JS for Chrome compatibility.
        """
        pass
    
    def set_fullscreen_state(self, is_fullscreen: str):
        """Sync fullscreen state from browser (called when Escape exits fullscreen)."""
        self.is_fullscreen = is_fullscreen == "true"
        print(f"[Labeling] Fullscreen state synced: {self.is_fullscreen}")
    
    def set_pending_longpress_image_id(self, value: str):
        """Called from JS input element."""
        self.pending_longpress_image_id = value
    
    def toggle_image_selection_from_js(self):
        """Toggle selection for the image ID set by JS longpress handler."""
        if not self.pending_longpress_image_id:
            return
        
        image_id = self.pending_longpress_image_id
        self.pending_longpress_image_id = ""  # Clear
        
        # Toggle the selection
        if image_id in self.selected_image_ids:
            self.selected_image_ids = [id for id in self.selected_image_ids if id != image_id]
        else:
            self.selected_image_ids = self.selected_image_ids + [image_id]
        
        # Update last clicked index
        for i, img in enumerate(self.images):
            if img.id == image_id:
                self.last_clicked_image_idx = i
                break
    
    def toggle_image_selection_by_id(self, image_id: str):
        """Toggle selection for a specific image ID (called from rx.call_script callback)."""
        if not image_id:
            return
        
        print(f"[Labeling] Toggle selection for image: {image_id}")
        
        # Toggle the selection
        if image_id in self.selected_image_ids:
            self.selected_image_ids = [id for id in self.selected_image_ids if id != image_id]
        else:
            self.selected_image_ids = self.selected_image_ids + [image_id]
        
        # Update last clicked index
        for i, img in enumerate(self.images):
            if img.id == image_id:
                self.last_clicked_image_idx = i
                break

    def range_select_image_by_id(self, image_id: str):
        """Range verify logic from JS bridge."""
        if not image_id:
            return

        print(f"[Labeling] Range select to image: {image_id}")
        
        # Determine target index
        target_idx = -1
        for i, img in enumerate(self.images):
            if img.id == image_id:
                target_idx = i
                break
        
        if target_idx == -1:
            return

        if self.last_clicked_image_idx == -1:
            # No start point, treat as single toggle
            self.toggle_image_selection_by_id(image_id)
            return

        start = min(self.last_clicked_image_idx, target_idx)
        end = max(self.last_clicked_image_idx, target_idx)
        
        # Add all IDs in range to selection
        current_ids = set(self.selected_image_ids)
        for i in range(start, end + 1):
            if i < len(self.images):
                current_ids.add(self.images[i].id)
        
        self.selected_image_ids = list(current_ids)
        self.last_clicked_image_idx = target_idx

    def _update_current_image_annotation_count(self):
        """Update the annotation_count for the current image in the sidebar."""
        if not self.current_image_id:
            return
        
        for i, img in enumerate(self.images):
            if img.id == self.current_image_id:
                updated_img = ImageModel(
                    id=img.id,
                    filename=img.filename,
                    r2_path=img.r2_path,
                    width=img.width,
                    height=img.height,
                    labeled=len(self.annotations) > 0,
                    annotation_count=len(self.annotations),
                    thumbnail_url=img.thumbnail_url,
                    full_url=img.full_url,
                )
                self.images[i] = updated_img
                break
    
    def set_tool(self, tool: str):
        """Set the current tool."""
        self.current_tool = tool
        # Reset drawing state when switching tools
        self.is_drawing = False
        # Sync with JS
        return rx.call_script(f"window.setTool && window.setTool('{tool}')")

    def load_image(self, image: dict):
        """Select an image to label."""
        self.current_image = image
        self.current_image_url = image["url"]
        self.current_image_id = image["id"]
        
        # Load saved annotations for this image, or empty list
        self.annotations = self._saved_annotations.get(self.current_image_id, [])
        self.selected_annotation_id = None
        
        return [
            rx.call_script(f"window.loadCanvasImage('{self.current_image_url}')"),
            self.push_annotations_to_js()
        ]

    def handle_new_annotation(self, data_json: str):
        """Called from JS when a new box is drawn."""
        print(f"[Python] Received annotation data: {data_json}")
        try:
            data = json.loads(data_json)
            
            # Determine class name
            class_name = "Unknown"
            if 0 <= self.current_class_id < len(self.project_classes):
                class_name = self.project_classes[self.current_class_id]
            elif self.project_classes:
                class_name = self.project_classes[0]
            
            new_ann = {
                "id": str(uuid.uuid4()),
                "class_id": self.current_class_id,
                "class_name": class_name,
                "x": data["x"],
                "y": data["y"],
                "width": data["width"],
                "height": data["height"],
            }
            
            # Add to current view
            self.annotations.append(new_ann)
            self.selected_annotation_id = new_ann["id"]
            
            # Persist to memory store
            self._saved_annotations[self.current_image_id] = self.annotations
            
            # Mark as dirty for autosave
            self.is_dirty = True
            
            # Update annotation_count in sidebar (real-time update)
            self._update_current_image_annotation_count()
            
            print(f"[Python] Added annotation. Total for img {self.current_image_id}: {len(self.annotations)}")
            
            # Trigger autosave
            self.save_annotations()
            
            # Sync back to JS to ensure consistency
            return self.push_annotations_to_js()
        except Exception as e:
            print(f"[Error] Failed to parse annotation: {e}")

    def save_annotations(self):
        """Trigger autosave of annotations to R2 (NON-BLOCKING background thread)."""
        if not self.current_image_id or not self.current_dataset_id:
            return
        
        if not self.is_dirty:
            return
        
        # Capture snapshot of data for background save
        image_id = self.current_image_id
        dataset_id = self.current_dataset_id
        project_id = self.current_project_id  # Capture for background thread
        annotations = list(self.annotations)
        
        print(f"[Autosave] Launching background save for {len(annotations)} annotations on image {image_id}")
        
        # Update cache immediately (so subsequent loads are instant)
        self._label_cache[image_id] = annotations
        self._saved_annotations[image_id] = annotations
        self.is_dirty = False
        
        def _background_save():
            try:
                import time
                from backend.annotation_service import save_annotations as svc_save
                
                t0 = time.perf_counter()
                
                # Single call to service handles both Supabase and R2
                success = svc_save(
                    item_id=image_id,
                    item_type="image",
                    annotations=annotations,
                    dataset_id=dataset_id,
                    sync_r2=True
                )
                
                elapsed = (time.perf_counter() - t0) * 1000
                if success:
                    print(f"[BG Save] Complete in {elapsed:.0f}ms for image {image_id[:8]}...")
                else:
                    print(f"[BG Save] Failed for image {image_id[:8]}...")
                
            except Exception as e:
                print(f"[BG Save] Critical error: {e}")
        
        # Launch background thread
        thread = threading.Thread(target=_background_save, daemon=True)
        thread.start()
    
    async def handle_save_before_leave(self, _value: str):
        """Handle save-before-leave trigger from browser navigation (back button, close tab).
        
        This is called via hidden input when JS detects beforeunload/pagehide/popstate events.
        We save synchronously here to ensure data is persisted before leaving.
        """
        print("[Save Before Leave] Triggered - checking for unsaved changes")
        
        if not self.is_dirty:
            print("[Save Before Leave] No unsaved changes")
            return
        
        if not self.current_image_id or not self.current_dataset_id:
            print("[Save Before Leave] No image/dataset context")
            return
        
        print(f"[Save Before Leave] Saving {len(self.annotations)} annotations for {self.current_image_id}")
        
        # Use the same save logic as save_annotations_to_r2 but inline
        try:
            # Convert to YOLO format
            yolo_content = self.to_yolo_format()
            
            # Build R2 path
            label_path = f"datasets/{self.current_dataset_id}/labels/{self.current_image_id}.txt"
            
            # Upload to R2
            r2 = R2Client()
            r2.upload_file(
                file_bytes=yolo_content.encode('utf-8'),
                path=label_path,
                content_type='text/plain'
            )
            
            # Update labeled status and annotation_count in Supabase
            has_annotations = len(self.annotations) > 0
            update_image(
                self.current_image_id, 
                labeled=has_annotations,
                annotation_count=len(self.annotations)
            )
            
            self.is_dirty = False
            print(f"[Save Before Leave] Successfully saved annotations")
            
        except Exception as e:
            print(f"[Save Before Leave] Error: {e}")
            import traceback
            traceback.print_exc()
    
    async def navigate_back(self):
        """Navigate back to the dataset page, saving any unsaved changes first."""
        print("[Navigate Back] Saving before returning to dataset page")
        
        # Perform save if dirty
        if self.is_dirty and self.current_image_id and self.current_dataset_id:
            try:
                yolo_content = self.to_yolo_format()
                label_path = f"datasets/{self.current_dataset_id}/labels/{self.current_image_id}.txt"
                
                r2 = R2Client()
                r2.upload_file(
                    file_bytes=yolo_content.encode('utf-8'),
                    path=label_path,
                    content_type='text/plain'
                )
                
                has_annotations = len(self.annotations) > 0
                update_image(
                    self.current_image_id, 
                    labeled=has_annotations,
                    annotation_count=len(self.annotations)
                )
                self.is_dirty = False
                print("[Navigate Back] Saved successfully")
            except Exception as e:
                print(f"[Navigate Back] Save error: {e}")
        
        # Auto-generate thumbnails if leaving with annotations (runs in background)
        if self.current_image_id and self.annotations:
            leaving_image_id = self.current_image_id
            leaving_dataset_id = self.current_dataset_id
            leaving_project_id = self.current_project_id
            leaving_annotations = list(self.annotations)
            
            def _bg_thumbnail():
                _auto_generate_thumbnails(
                    image_id=leaving_image_id,
                    dataset_id=leaving_dataset_id,
                    project_id=leaving_project_id,
                    first_annotation=leaving_annotations[0]
                )
            
            thread = threading.Thread(target=_bg_thumbnail, daemon=True)
            thread.start()
        
        # Navigate back to dataset detail page
        return rx.redirect(f"/projects/{self.current_project_id}/datasets/{self.current_dataset_id}")
    
    # =========================================================================
    # YOLO FORMAT CONVERSION (Phase 1.9)
    # =========================================================================
    
    def to_yolo_format(self) -> str:
        """Convert all annotations to YOLO format string.
        
        YOLO format: class_id x_center y_center width height (all normalized 0-1)
        """
        lines = []
        for ann in self.annotations:
            x = ann.get("x", 0)
            y = ann.get("y", 0)
            w = ann.get("width", 0)
            h = ann.get("height", 0)
            class_id = ann.get("class_id", 0)
            
            # Convert from corner-based to center-based
            x_center = x + w / 2
            y_center = y + h / 2
            
            lines.append(f"{class_id} {x_center:.6f} {y_center:.6f} {w:.6f} {h:.6f}")
        
        return "\n".join(lines)
    
    def from_yolo_format(self, txt_content: str) -> list[dict]:
        """Parse YOLO format text and return list of annotation dicts."""
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
                
                # Convert from center-based to corner-based
                x = x_center - w / 2
                y = y_center - h / 2
                
                # Get class name
                class_name = "Unknown"
                if 0 <= class_id < len(self.project_classes):
                    class_name = self.project_classes[class_id]
                
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
                print(f"[YOLO Parse] Skipping invalid line: {line} - {e}")
                continue
        
        return annotations
    
    async def save_annotations_to_r2(self):
        """Save current annotations to R2 as YOLO .txt file."""
        if not self.current_image_id or not self.current_dataset_id:
            return
        
        # Skip if not dirty
        if not self.is_dirty:
            print(f"[Autosave] Skipping save - no changes")
            return
        
        self.save_status = "saving"
        yield
        
        try:
            from backend.annotation_service import save_annotations as svc_save
            
            # Single call to service handles both Supabase and R2
            success = svc_save(
                item_id=self.current_image_id,
                item_type="image",
                annotations=list(self.annotations),
                dataset_id=self.current_dataset_id,
                sync_r2=True
            )
            
            if success:
                has_annotations = len(self.annotations) > 0
                
                # Update local state (labeled + annotation_count)
                for i, img in enumerate(self.images):
                    if img.id == self.current_image_id:
                        updated_img = ImageModel(
                            id=img.id,
                            filename=img.filename,
                            r2_path=img.r2_path,
                            width=img.width,
                            height=img.height,
                            labeled=has_annotations,
                            annotation_count=len(self.annotations),
                            thumbnail_url=img.thumbnail_url,
                            full_url=img.full_url,
                        )
                        self.images[i] = updated_img
                        break
                
                # Update cache (for prefetch)
                self._label_cache[self.current_image_id] = list(self.annotations)
                
                print(f"[Autosave] Saved {len(self.annotations)} annotations")
                self.save_status = "saved"
                self.is_dirty = False
            else:
                print(f"[Autosave] Failed to save annotations")
                self.save_status = ""
            
            yield
            
            # Clear "saved" status after 2 seconds
            import asyncio
            await asyncio.sleep(2)
            if self.save_status == "saved":
                self.save_status = ""
            
        except Exception as e:
            print(f"[Autosave] Error saving: {e}")
            import traceback
            traceback.print_exc()
            self.save_status = ""
    
    @rx.event(background=True)
    async def process_pending_saves(self):
        """Background task to process queued saves without blocking navigation."""
        import asyncio
        from backend.annotation_service import save_annotations as svc_save
        
        async with self:
            if not self._pending_saves:
                return
            
            self.save_status = "saving"
        
        # Process all pending saves
        while True:
            async with self:
                if not self._pending_saves:
                    break
                
                # Pop one item from the queue
                image_id = next(iter(self._pending_saves))
                save_data = self._pending_saves.pop(image_id)
                annotations = save_data["annotations"]
                dataset_id = save_data["dataset_id"]
            
            # Perform save outside the state lock
            try:
                print(f"[Background Save] Saving {len(annotations)} annotations for {image_id}")
                
                # Single call to service handles both Supabase and R2
                success = svc_save(
                    item_id=image_id,
                    item_type="image",
                    annotations=annotations,
                    dataset_id=dataset_id,
                    sync_r2=True
                )
                
                if success:
                    has_annotations = len(annotations) > 0
                    
                    # Update local state inside lock
                    async with self:
                        for i, img in enumerate(self.images):
                            if img.id == image_id:
                                updated_img = ImageModel(
                                    id=img.id,
                                    filename=img.filename,
                                    r2_path=img.r2_path,
                                    width=img.width,
                                    height=img.height,
                                    labeled=has_annotations,
                                    annotation_count=len(annotations),
                                    thumbnail_url=img.thumbnail_url,
                                    full_url=img.full_url,
                                )
                                self.images[i] = updated_img
                                break
                        # Update cache
                        self._label_cache[image_id] = list(annotations)
                    
                    print(f"[Background Save] Completed for {image_id}")
                else:
                    print(f"[Background Save] Failed for {image_id}")
                
            except Exception as e:
                print(f"[Background Save] Error saving {image_id}: {e}")
                import traceback
                traceback.print_exc()
        
        # All saves complete
        async with self:
            self.save_status = "saved"
        
        # Clear "saved" status after 2 seconds
        await asyncio.sleep(2)
        async with self:
            if self.save_status == "saved":
                self.save_status = ""
    
    async def load_annotations_from_r2(self, image_id: str) -> list[dict]:
        """Load annotations with hybrid strategy: cache -> Supabase -> R2 fallback.
        
        OPTIMIZED: Matches video editor pattern. Most cases hit cache (instant).
        """
        # 1. Check pending saves first (for images queued but not yet saved)
        if image_id in self._pending_saves:
            print(f"[Labels] Using pending save queue for {image_id}")
            return list(self._pending_saves[image_id]["annotations"])
        
        # 2. Check cache (populated by batch load on project open)
        if image_id in self._label_cache:
            print(f"[Cache HIT] Loaded annotations for {image_id}")
            annotations = self._label_cache[image_id]
            # Track as "last saved" for class count diffing
            self._last_saved_annotations[image_id] = list(annotations)
            return annotations
        
        # 3. Try Supabase JSONB column (fast: 5-20ms)
        db_annotations = get_image_annotations(image_id)
        if db_annotations is not None:
            from backend.annotation_service import resolve_class_names
            # Resolve class_name from class_id using project_classes
            db_annotations = resolve_class_names(db_annotations, self.project_classes)
            print(f"[Supabase] Loaded {len(db_annotations)} annotations for {image_id}")
            self._label_cache[image_id] = db_annotations
            self._last_saved_annotations[image_id] = list(db_annotations)
            return db_annotations
        
        # 4. Fallback to R2 (slower: 50-200ms, for un-migrated data)
        label_path = f"datasets/{self.current_dataset_id}/labels/{image_id}.txt"
        
        try:
            r2 = R2Client()
            if r2.file_exists(label_path):
                print(f"[R2 Fallback] Downloading from R2: {label_path}")
                content = r2.download_file(label_path)
                txt_content = content.decode('utf-8')
                annotations = self.from_yolo_format(txt_content)
                
                # BACKFILL: Sync to Supabase for future fast loads
                update_image_annotations(image_id, annotations)
                print(f"[Backfill] Synced {len(annotations)} annotations to Supabase for {image_id}")
                
                # Cache for future use
                self._label_cache[image_id] = annotations
                self._last_saved_annotations[image_id] = list(annotations)
                return annotations
            else:
                print(f"[Labels] No labels found for {image_id}")
                self._label_cache[image_id] = []
                self._last_saved_annotations[image_id] = []
                return []
        except Exception as e:
            print(f"[Labels] Error loading from R2: {e}")
            return []
    
    def _batch_load_all_annotations(self):
        """Batch load all annotations from Supabase for this dataset (single query).
        
        OPTIMIZATION: Matches video editor pattern. Eliminates N individual R2 requests.
        """
        if not self.current_dataset_id:
            return
        
        try:
            from backend.annotation_service import resolve_class_names
            
            # Single query to fetch ALL annotations for this dataset
            all_annotations = get_dataset_image_annotations(self.current_dataset_id)
            
            # Populate cache with resolved class names
            for image_id, annotations in all_annotations.items():
                # Resolve class_name from class_id using project_classes
                resolved = resolve_class_names(annotations, self.project_classes)
                self._label_cache[image_id] = resolved
            
            # Mark images without annotations in Supabase as needing R2 check
            # (but most will be empty, so we set them to empty list to avoid R2 round-trip)
            images_in_supabase = set(all_annotations.keys())
            for img in self.images:
                if img.id not in images_in_supabase:
                    # Will trigger R2 fallback on first load (and backfill to Supabase)
                    pass  # Don't pre-cache as empty; let R2 fallback handle it
            
            print(f"[Batch Load] Cached {len(all_annotations)} image annotations from Supabase (class names resolved)")
            
        except Exception as e:
            print(f"[Batch Load] Error: {e}")
            import traceback
            traceback.print_exc()
    
    def push_annotations_to_js(self):
        """Send all annotations to JS for rendering."""
        return rx.call_script(f"window.renderAnnotations && window.renderAnnotations({json.dumps(self.annotations)})")



    def handle_selection_change(self, annotation_id: str):
        """Called from JS when selection changes."""
        self.selected_annotation_id = annotation_id if annotation_id else None
        print(f"[Python] Selection changed to: {self.selected_annotation_id}")

    def handle_annotation_deleted(self, annotation_id: str):
        """Called from JS when an annotation is deleted."""
        if not annotation_id:
            return
        
        print(f"[Python] Deleting annotation: {annotation_id}")
        
        # Remove from current annotations list
        self.annotations = [a for a in self.annotations if a.get("id") != annotation_id]
        
        # Update memory store
        self._saved_annotations[self.current_image_id] = self.annotations
        
        # Mark as dirty
        self.is_dirty = True
        
        # Update annotation_count in sidebar (real-time update)
        self._update_current_image_annotation_count()
        
        # Clear selection
        self.selected_annotation_id = None
        
        # Trigger autosave
        self.save_annotations()
        
        print(f"[Python] Remaining annotations: {len(self.annotations)}")

    def handle_annotation_updated(self, data_json: str):
        """Called from JS when an annotation is resized/moved."""
        if not data_json:
            return
        
        try:
            data = json.loads(data_json)
            annotation_id = data.get("id")
            
            if not annotation_id:
                print("[Python] No annotation ID in update data")
                return
            
            print(f"[Python] Updating annotation: {annotation_id}")
            
            # Find and update the annotation in self.annotations
            for i, ann in enumerate(self.annotations):
                if ann.get("id") == annotation_id:
                    # Update bounds, preserve other fields (class_id, class_name)
                    self.annotations[i] = {
                        **ann,
                        "x": data.get("x", ann.get("x")),
                        "y": data.get("y", ann.get("y")),
                        "width": data.get("width", ann.get("width")),
                        "height": data.get("height", ann.get("height")),
                    }
                    # Update mask_polygon if provided (from mask-edit mode)
                    if "mask_polygon" in data:
                        self.annotations[i]["mask_polygon"] = data["mask_polygon"]
                    break
            
            # Persist to memory store
            self._saved_annotations[self.current_image_id] = self.annotations
            
            # Mark as dirty
            self.is_dirty = True
            
            # Trigger autosave
            self.save_annotations()
            
            print(f"[Python] Annotation updated successfully")
        except Exception as e:
            print(f"[Error] Failed to update annotation: {e}")

    def delete_selected_annotation(self):
        """Delete the currently selected annotation (called from Delete button)."""
        return rx.call_script("window.deleteSelectedAnnotation && window.deleteSelectedAnnotation()")

    def delete_mask_from_annotation(self):
        """Remove mask_polygon from the currently selected annotation (keep bbox)."""
        if not self.selected_annotation_id:
            return
        
        for i, ann in enumerate(self.annotations):
            if ann.get("id") == self.selected_annotation_id:
                if "mask_polygon" in ann:
                    del self.annotations[i]["mask_polygon"]
                    print(f"[Python] Deleted mask from annotation: {self.selected_annotation_id}")
                    
                    # Persist to memory store
                    self._saved_annotations[self.current_image_id] = self.annotations
                    self.is_dirty = True
                    self.save_annotations()
                    
                    # Push updated annotations to JS (mask will disappear)
                    return self.push_annotations_to_js()
                break

    # =========================================================================
    # CLASS MANAGEMENT CRUD
    # =========================================================================

    def set_new_class_name(self, name: str):
        """Update the new class name input."""
        self.new_class_name = name

    def add_class(self):
        """Add a new class to the project with validation."""
        import re
        name = self.new_class_name.strip()
        
        if not name:
            return
        
        # Validate: only letters, numbers, underscores
        if not re.match(r'^[a-zA-Z0-9_]+$', name):
            return rx.toast.error("Class names can only contain letters, numbers, and underscores")
        
        if name in self.project_classes:
            return rx.toast.error(f"Class '{name}' already exists")
        
        self.project_classes = self.project_classes + [name]
        update_project(self.current_project_id, classes=self.project_classes)
        self.new_class_name = ""
        print(f"[Python] Added class: {name}. Total classes: {len(self.project_classes)}")

    def rename_class(self, idx: int, new_name: str):
        """Rename a class. Annotations reference by class_id, so only update class list."""
        if idx < 0 or idx >= len(self.project_classes):
            return
        
        old_name = self.project_classes[idx]
        new_name = new_name.strip()
        if not new_name or new_name == old_name:
            return
        
        # Update class list
        classes = list(self.project_classes)
        classes[idx] = new_name
        self.project_classes = classes
        
        # Update any annotations with this class_id to have new name
        updated_annotations = []
        for ann in self.annotations:
            if ann.get("class_id") == idx:
                ann = {**ann, "class_name": new_name}
            updated_annotations.append(ann)
        self.annotations = updated_annotations
        self._saved_annotations[self.current_image_id] = self.annotations
        
        # Persist to project DB
        update_project(self.current_project_id, classes=self.project_classes)
        
        # Mark as dirty and trigger autosave
        self.is_dirty = True
        self.save_annotations()
        
        # Sync with JS
        print(f"[Python] Renamed class {idx}: '{old_name}' -> '{new_name}'")
        return self.push_annotations_to_js()

    def set_current_class(self, idx: int):
        """Set the current class for new annotations."""
        self.current_class_id = idx
        class_name = self.project_classes[idx] if idx < len(self.project_classes) else "Unknown"
        print(f"[Python] Current class set to: {idx} ({class_name})")
        return rx.call_script(f"window.setCurrentClass && window.setCurrentClass({idx}, '{class_name}')")

    def handle_class_select(self, index_str: str):
        """Select class by keyboard shortcut (1-9 keys). Step 1.11.5."""
        try:
            idx = int(index_str)
            if 0 <= idx < len(self.project_classes):
                self.current_class_id = idx
                class_name = self.project_classes[idx]
                print(f"[Python] Class selected via keyboard: {idx} ({class_name})")
                return rx.call_script(f"window.setCurrentClass && window.setCurrentClass({idx}, '{class_name}')")
        except ValueError:
            pass

    def toggle_shortcuts_help(self, _: str = ""):
        """Toggle the keyboard shortcuts help overlay. Step 1.11.8."""
        self.show_shortcuts_help = not self.show_shortcuts_help
        print(f"[Python] Shortcuts help: {self.show_shortcuts_help}")

    def request_delete_class(self, idx: int):
        """Open confirmation modal for class deletion."""
        if idx < 0 or idx >= len(self.project_classes):
            return
        self.class_to_delete_idx = idx
        self.class_to_delete_name = self.project_classes[idx]
        self.show_delete_class_modal = True

    def cancel_delete_class(self):
        """Cancel class deletion."""
        self.show_delete_class_modal = False
        self.class_to_delete_idx = -1
        self.class_to_delete_name = ""

    def handle_add_class_keydown(self, key: str):
        """Handle Enter key in add class input."""
        if key == "Enter" and self.new_class_name.strip():
            self.add_class()

    def handle_rename_class_keydown(self, key: str):
        """Handle Enter key in rename class input."""
        if key == "Enter" and self.editing_class_name.strip():
            self.save_rename_class()

    def handle_delete_class_keydown(self, key: str):
        """Handle Enter key in delete class confirmation."""
        # Note: confirm_delete_class does not require "delete" text like video editor
        if key == "Enter":
            self.confirm_delete_class()

    async def handle_autolabel_keydown(self, key: str):
        """Handle Enter key in autolabel prompt."""
        if key == "Enter" and self.autolabel_prompt.strip() and not self.is_autolabeling:
            # Save prompt before starting
            await self.save_autolabel_prompt_pref()
            return type(self).start_autolabel

    def confirm_delete_class(self):
        """Delete class and all annotations that use it."""
        idx = self.class_to_delete_idx
        if idx < 0 or idx >= len(self.project_classes):
            self.show_delete_class_modal = False
            return
        
        print(f"[Python] Deleting class {idx}: {self.class_to_delete_name}")
        
        # Remove annotations with this class from current image
        self.annotations = [a for a in self.annotations if a.get("class_id") != idx]
        
        # Shift class_ids for annotations with higher indices
        updated = []
        for ann in self.annotations:
            cid = ann.get("class_id", 0)
            if cid > idx:
                # Shift down and update name
                new_cid = cid - 1
                new_name = self.project_classes[cid] if cid < len(self.project_classes) else "Unknown"
                ann = {**ann, "class_id": new_cid, "class_name": new_name}
            updated.append(ann)
        self.annotations = updated
        self._saved_annotations[self.current_image_id] = self.annotations
        
        # Also update all other images' annotations in memory
        for img_id, anns in self._saved_annotations.items():
            if img_id == self.current_image_id:
                continue
            updated_anns = []
            for ann in anns:
                cid = ann.get("class_id", 0)
                if cid == idx:
                    continue  # Remove this annotation
                if cid > idx:
                    new_cid = cid - 1
                    new_name = self.project_classes[cid] if cid < len(self.project_classes) else "Unknown"
                    ann = {**ann, "class_id": new_cid, "class_name": new_name}
                updated_anns.append(ann)
            self._saved_annotations[img_id] = updated_anns
        
        # Remove class from list
        classes = list(self.project_classes)
        classes.pop(idx)
        self.project_classes = classes
        
        # Adjust current_class_id if needed
        if self.current_class_id >= len(self.project_classes):
            self.current_class_id = max(0, len(self.project_classes) - 1)
        
        # Persist to project
        update_project(self.current_project_id, classes=self.project_classes)
        
        # Mark as dirty and trigger autosave
        self.is_dirty = True
        self.save_annotations()
        
        # Close modal
        self.show_delete_class_modal = False
        self.class_to_delete_idx = -1
        self.class_to_delete_name = ""
        
        print(f"[Python] Class deleted. Remaining classes: {len(self.project_classes)}")
        return self.push_annotations_to_js()

    def change_annotation_class(self, new_class_name: str):
        """Change the class of the selected annotation (1.8.7)."""
        if not self.selected_annotation_id:
            return
        if not new_class_name or new_class_name not in self.project_classes:
            return
        
        new_class_id = self.project_classes.index(new_class_name)
        
        # Update annotation
        updated = []
        for ann in self.annotations:
            if ann.get("id") == self.selected_annotation_id:
                ann = {**ann, "class_id": new_class_id, "class_name": new_class_name}
            updated.append(ann)
        self.annotations = updated
        self._saved_annotations[self.current_image_id] = self.annotations
        
        # Mark as dirty and trigger autosave
        self.is_dirty = True
        self.save_annotations()
        print(f"[Python] Changed annotation {self.selected_annotation_id} to class {new_class_id}: {new_class_name}")
        return self.push_annotations_to_js()
    
    def update_annotation_class(self, annotation_id: str, new_class_id: int):
        """Update a specific annotation's class by ID and class index (for popover UI)."""
        if new_class_id < 0 or new_class_id >= len(self.project_classes):
            return
        
        new_class_name = self.project_classes[new_class_id]
        
        # Update annotation
        updated = []
        for ann in self.annotations:
            if ann.get("id") == annotation_id:
                ann = {**ann, "class_id": new_class_id, "class_name": new_class_name}
            updated.append(ann)
        self.annotations = updated
        self._saved_annotations[self.current_image_id] = self.annotations
        
        # Mark as dirty and trigger autosave
        self.is_dirty = True
        self.save_annotations()
        print(f"[Python] Updated annotation {annotation_id} to class {new_class_id}: {new_class_name}")
        return self.push_annotations_to_js()
    
    def select_annotation_from_list(self, annotation_id: str):
        """Select an annotation from the sidebar list (1.8.8)."""
        self.selected_annotation_id = annotation_id
        # Sync with JS to highlight on canvas
        return rx.call_script(f"window.selectAnnotationById && window.selectAnnotationById('{annotation_id}')")
    
    # =========================================================================
    # RIGHT-CLICK CONTEXT MENU
    # =========================================================================
    
    def open_context_menu(self, data_json: str):
        """Open context menu at given position for annotation (called from JS)."""
        if not data_json:
            return
        
        try:
            import json
            data = json.loads(data_json)
            self.context_menu_x = int(data.get("x", 0))
            self.context_menu_y = int(data.get("y", 0))
            self.context_menu_annotation_id = data.get("annotation_id", "")
            self.context_menu_open = True
            print(f"[Context Menu] Opened at ({self.context_menu_x}, {self.context_menu_y}) for {self.context_menu_annotation_id}")
        except Exception as e:
            print(f"[Context Menu] Error parsing data: {e}")
    
    def close_context_menu(self):
        """Close the context menu."""
        self.context_menu_open = False
        self.context_menu_annotation_id = ""
    
    def context_menu_change_class(self, new_class_name: str):
        """Change class of context menu annotation (wrapper for change_annotation_class)."""
        if not self.context_menu_annotation_id:
            return
        
        # Temporarily set selected_annotation_id to the context menu target
        original_selection = self.selected_annotation_id
        self.selected_annotation_id = self.context_menu_annotation_id
        
        # Use existing class change logic
        result = self.change_annotation_class(new_class_name)
        
        # Restore original selection (or keep new if it was the same)
        if original_selection != self.context_menu_annotation_id:
            self.selected_annotation_id = original_selection
        
        self.close_context_menu()
        return result
    
    def set_as_project_thumbnail(self):
        """Generate thumbnail from context menu annotation and set as project cover."""
        if not self.context_menu_annotation_id:
            return rx.toast.error("No annotation selected")
        
        # Find annotation
        ann = next((a for a in self.annotations if a["id"] == self.context_menu_annotation_id), None)
        if not ann:
            return rx.toast.error("Annotation not found")
        
        # Find current image
        current_img = next((i for i in self.images if i.id == self.current_image_id), None)
        if not current_img:
            return rx.toast.error("Image not found")
        
        try:
            from backend.r2_storage import R2Client
            from backend.core.thumbnail_generator import generate_label_thumbnail
            from backend.supabase_client import update_project
            
            r2 = R2Client()
            
            # Download current image
            image_bytes = r2.download_file(current_img.r2_path)
            
            # Generate thumbnail
            thumb_bytes = generate_label_thumbnail(image_bytes, ann)
            if not thumb_bytes:
                return rx.toast.error("Failed to generate thumbnail")
            
            # Upload to R2
            thumb_path = f"projects/{self.current_project_id}/thumbnail.jpg"
            r2.upload_file(thumb_bytes, thumb_path, content_type="image/jpeg")
            
            # Update database
            update_project(self.current_project_id, thumbnail_r2_path=thumb_path)
            
            self.close_context_menu()
            print(f"[Context Menu] Set project thumbnail from annotation {ann['id']}")
            return rx.toast.success("Project thumbnail updated!")
            
        except Exception as e:
            print(f"[Context Menu] Error setting project thumbnail: {e}")
            import traceback
            traceback.print_exc()
            return rx.toast.error(f"Error: {str(e)}")
    
    def set_as_dataset_thumbnail(self):
        """Generate thumbnail from context menu annotation and set as dataset cover."""
        if not self.context_menu_annotation_id:
            return rx.toast.error("No annotation selected")
        
        # Find annotation
        ann = next((a for a in self.annotations if a["id"] == self.context_menu_annotation_id), None)
        if not ann:
            return rx.toast.error("Annotation not found")
        
        # Find current image
        current_img = next((i for i in self.images if i.id == self.current_image_id), None)
        if not current_img:
            return rx.toast.error("Image not found")
        
        try:
            from backend.r2_storage import R2Client
            from backend.core.thumbnail_generator import generate_label_thumbnail
            from backend.supabase_client import update_dataset
            
            r2 = R2Client()
            
            # Download current image
            image_bytes = r2.download_file(current_img.r2_path)
            
            # Generate thumbnail
            thumb_bytes = generate_label_thumbnail(image_bytes, ann)
            if not thumb_bytes:
                return rx.toast.error("Failed to generate thumbnail")
            
            # Upload to R2
            thumb_path = f"datasets/{self.current_dataset_id}/thumbnail.jpg"
            r2.upload_file(thumb_bytes, thumb_path, content_type="image/jpeg")
            
            # Update database
            update_dataset(self.current_dataset_id, thumbnail_r2_path=thumb_path)
            
            self.close_context_menu()
            print(f"[Context Menu] Set dataset thumbnail from annotation {ann['id']}")
            return rx.toast.success("Dataset thumbnail updated!")
            
        except Exception as e:
            print(f"[Context Menu] Error setting dataset thumbnail: {e}")
            import traceback
            traceback.print_exc()
            return rx.toast.error(f"Error: {str(e)}")
    
    # =========================================================================
    # INLINE CLASS RENAME (1.8.10)
    # =========================================================================
    
    editing_class_idx: int = -1
    editing_class_name: str = ""
    
    def start_rename_class(self, idx: int):
        """Begin inline editing of a class name."""
        if idx < 0 or idx >= len(self.project_classes):
            return
        self.editing_class_idx = idx
        self.editing_class_name = self.project_classes[idx]
    
    def set_editing_class_name(self, name: str):
        """Update the editing class name."""
        self.editing_class_name = name
    
    def save_rename_class(self):
        """Save the renamed class."""
        idx = self.editing_class_idx
        new_name = self.editing_class_name.strip()
        
        if idx < 0 or idx >= len(self.project_classes):
            self.cancel_rename_class()
            return
        
        if not new_name:
            self.cancel_rename_class()
            return
        
        # Use existing rename_class logic
        result = self.rename_class(idx, new_name)
        
        # Clear editing state
        self.editing_class_idx = -1
        self.editing_class_name = ""
        
        return result
    
    def cancel_rename_class(self):
        """Cancel inline editing."""
        self.editing_class_idx = -1
        self.editing_class_name = ""
    
    def handle_rename_key_down(self, key: str):
        """Handle key press in rename input. Enter saves, Escape cancels."""
        if key == "Enter":
            return self.save_rename_class()
        elif key == "Escape":
            self.cancel_rename_class()

    @staticmethod
    def get_class_color(idx: int) -> str:
        """Generate consistent color for a class using HSL rotation (golden angle).

        Must stay in sync with canvas.js getClassColor() and class list color dots.
        """
        hue = (idx * 137) % 360
        return f"hsl({hue}, 70%, 50%)"


    # View state (zoom & pan)
    zoom_level: float = 1.0
    pan_x: float = 0.0
    pan_y: float = 0.0
    is_panning: bool = False
    _pan_start_x: float = 0.0  # Internal: mouse position at pan start
    _pan_start_y: float = 0.0
    
    # Zoom constraints
    MIN_ZOOM: float = 1.0
    MAX_ZOOM: float = 10.0
    ZOOM_STEP: float = 0.25  # For button clicks
    WHEEL_ZOOM_FACTOR: float = 0.1  # For mouse wheel
    
    # Loading states
    is_loading: bool = False  # Default to False to prevent skeleton flash on re-navigation
    is_image_loading: bool = False
    _has_loaded_once: bool = False  # Track first load for skeleton display
    
    # Error handling
    error_message: str = ""
    
    async def on_load(self):
        """Page load handler."""
        async for event in self.load_project():
            yield event
        
    def restore_canvas_state(self):
        """Called on page mount to restore canvas state (image + annotations)."""
        if self.current_image_url:
            print(f"[Python] Restoring canvas state for image {self.current_image_id}")
            return [
                rx.call_script(f"window.loadCanvasImage('{self.current_image_url}')"),
                self.push_annotations_to_js()
            ]
    
    async def load_project(self):
        """Load dataset details and all images for labeling navigation."""
        # Only show skeleton on first load to prevent flickering on re-navigation
        if not self._has_loaded_once:
            self.is_loading = True
            yield
        self.error_message = ""
        
        try:
            # Get project_id and dataset_id from route
            params_project_id = self.router.page.params.get("project_id", "")
            params_dataset_id = self.router.page.params.get("dataset_id", "")
            
            # If we switched datasets or projects, clear current image context to avoid loading stale IDs
            if params_dataset_id != self.current_dataset_id or params_project_id != self.current_project_id:
                print(f"[Labeling] Context changed (Dataset: {self.current_dataset_id} -> {params_dataset_id}). Resetting image state.")
                self.current_image_id = ""
                self.current_image_url = ""
                self.annotations = []
                self.selected_annotation_id = None
                self.is_dirty = False
            
            self.current_project_id = params_project_id
            self.current_dataset_id = params_dataset_id
            
            if not self.current_project_id or not self.current_dataset_id:
                print("[Python] DEBUG: No project_id or dataset_id found in params")
                self.error_message = "No project or dataset ID provided."
                self.is_loading = False
                return
            
            print(f"[Python] DEBUG: Loading dataset {self.current_dataset_id} in project {self.current_project_id}")

            # Fetch project name for breadcrumbs
            project = get_project(self.current_project_id)
            if project:
                self.project_name = project.get("name", "")
            
            # Fetch dataset data (classes are stored at dataset level now)
            dataset = get_dataset(self.current_dataset_id)
            if not dataset:
                print(f"[Python] DEBUG: Dataset {self.current_dataset_id} not found in DB")
                self.error_message = "Dataset not found."
                self.is_loading = False
                return
            
            self.dataset_name = dataset.get("name", "")
            # Load classes from PROJECT (not dataset) - classes are project-wide
            self.project_classes = project.get("classes", []) or [] if project else []
            
            # Clear local caches on page load to ensure fresh data from R2
            self._saved_annotations = {}
            self._label_cache = {}
            self._pending_saves = {}
            self._last_saved_annotations = {}
            self.is_dirty = False
            
            print(f"[Python] DEBUG: Dataset loaded: {self.dataset_name}, Classes: {self.project_classes}")
            
            # Load all images for sidebar
            await self._load_images()
            print(f"[Python] DEBUG: Loaded {len(self.images)} images")
            
            # OPTIMIZATION: Batch load ALL annotations in single query (matches video editor)
            self._batch_load_all_annotations()
            
            # Touch access timestamp (for dashboard sorting)
            touch_dataset_accessed(self.current_dataset_id)

            
            # Auto-load first image if available AND no current image is selected
            if self.images and not self.current_image_id:
                initial_image_id = self.images[0].id
                print(f"[Python] DEBUG: Auto-selecting first image: {initial_image_id}")
                async for event in self._load_image_into_canvas(initial_image_id):
                    yield event
                
                # Pre-fetch the first 3 images
                prefetch_urls = [img.full_url for img in self.images[:3]]
                yield rx.call_script(f"window.prefetchImages && window.prefetchImages({prefetch_urls})")
            elif self.current_image_id:
                # If we already have an image selected (e.g. state persisted across refresh),
                # we MUST re-send it to the canvas because the DOM was reset.
                print(f"[Python] DEBUG: Restoring existing image state: {self.current_image_id}")
                async for event in self._load_image_into_canvas(self.current_image_id):
                    yield event
                
            elif not self.images:
                print("[Python] DEBUG: No images found for dataset")
            
        except Exception as e:
            print(f"[DEBUG] Error loading dataset for labeling: {e}")
            import traceback
            traceback.print_exc()
            self.error_message = f"Error loading dataset: {str(e)}"
        finally:
            self.is_loading = False
            self._has_loaded_once = True
    
    async def _load_images(self):
        """Load all images for the sidebar navigation."""
        try:
            raw_images = get_dataset_images(self.current_dataset_id)
            r2 = R2Client()
            
            self.images = []
            for img in raw_images:
                r2_path = img.get("r2_path", "")
                
                # Generate thumbnail URL for sidebar
                thumbnail_path = r2_path.replace("/images/", "/thumbnails/") if "/images/" in r2_path else r2_path
                thumbnail_url = ""
                full_url = ""
                
                if r2_path:
                    try:
                        # Generate both URLs upfront for caching
                        full_url = r2.generate_presigned_url(r2_path)
                        if thumbnail_path:
                            thumbnail_url = r2.generate_presigned_url(thumbnail_path)
                    except Exception as e:
                        print(f"[DEBUG] Error generating URLs: {e}")
                
                self.images.append(ImageModel(
                    id=str(img.get("id", "")),
                    filename=str(img.get("filename", "")),
                    r2_path=str(r2_path),
                    width=img.get("width") or 0,
                    height=img.get("height") or 0,
                    labeled=img.get("labeled", False),
                    annotation_count=img.get("annotation_count") or 0,  # Load from DB
                    thumbnail_url=thumbnail_url,
                    full_url=full_url,  # Cache full resolution URL
                ))
        except Exception as e:
            print(f"[DEBUG] Error loading images: {e}")
    
    async def select_image(self, image_id: str):
        """Called when user clicks an image in the sidebar."""
        async for event in self._load_image_into_canvas(image_id):
            yield event
    
    async def _load_image_into_canvas(self, image_id: str):
        """Load a specific image into the canvas."""
        self.is_image_loading = True
        
        # Queue save for current image before switching (Phase 1.9 - non-blocking)
        # Only queue if we have a current image AND it's different from the new one AND dirty
        if self.current_image_id and self.current_image_id != image_id and self.is_dirty:
            print(f"[Autosave] Queuing save for {self.current_image_id} before navigating to {image_id}")
            # Queue the save (don't block)
            self._pending_saves[self.current_image_id] = {
                "annotations": list(self.annotations),
                "dataset_id": self.current_dataset_id,
            }
            self._saved_annotations[self.current_image_id] = list(self.annotations)
            self.is_dirty = False
            # Fire background task (non-blocking) by yielding the method reference
            yield LabelingState.process_pending_saves
        
        # Auto-generate thumbnails if leaving an image with annotations (runs in background)
        if self.current_image_id and self.current_image_id != image_id and self.annotations:
            # Capture all values for background thread
            leaving_image_id = self.current_image_id
            leaving_dataset_id = self.current_dataset_id
            leaving_project_id = self.current_project_id
            leaving_annotations = list(self.annotations)
            
            def _bg_thumbnail():
                _auto_generate_thumbnails(
                    image_id=leaving_image_id,
                    dataset_id=leaving_dataset_id,
                    project_id=leaving_project_id,
                    first_annotation=leaving_annotations[0]
                )
            
            thread = threading.Thread(target=_bg_thumbnail, daemon=True)
            thread.start()
        
        # Now switch to the new image
        self.current_image_id = image_id
        
        # Update last clicked index for range selection
        for i, img in enumerate(self.images):
            if img.id == image_id:
                self.last_clicked_image_idx = i
                break
                
        self.selected_annotation_id = None
        
        # Reset view when loading new image
        self.zoom_level = 1.0
        self.pan_x = 0.0
        self.pan_y = 0.0
        
        try:
            # Find the image in our list
            target_image = None
            for img in self.images:
                if img.id == image_id:
                    target_image = img
                    break
            
            if not target_image:
                print(f"[Python] Error: Image {image_id} not found in list")
                # Fallback: if we have images but didn't find the requested one, load the first available
                if self.images:
                    print(f"[Python] Falling back to first available image: {self.images[0].id}")
                    self.current_image_id = self.images[0].id
                    async for event in self._load_image_into_canvas(self.images[0].id):
                        yield event
                    return
                
                self.error_message = "Image not found."
                return
            
            print(f"[Python] Loading image {image_id} into canvas. URL: {target_image.full_url[:50]}...")
            
            # Use cached full resolution URL (generated during load_project)
            self.current_image_url = target_image.full_url
            self.image_width = target_image.width
            self.image_height = target_image.height
            
            # Load annotations from R2 (or cache) - Phase 1.9
            self.annotations = await self.load_annotations_from_r2(image_id)
            self._saved_annotations[image_id] = list(self.annotations)
            self.is_dirty = False  # Fresh load, no unsaved changes
            
            # Update annotation_count for sidebar display
            for i, img in enumerate(self.images):
                if img.id == image_id:
                    updated_img = ImageModel(
                        id=img.id,
                        filename=img.filename,
                        r2_path=img.r2_path,
                        width=img.width,
                        height=img.height,
                        labeled=len(self.annotations) > 0,
                        annotation_count=len(self.annotations),
                        thumbnail_url=img.thumbnail_url,
                        full_url=img.full_url,
                    )
                    self.images[i] = updated_img
                    break
            
            # Call JS to load the image into canvas AND render annotations
            yield rx.call_script(f"window.loadCanvasImage && window.loadCanvasImage('{target_image.full_url}')")
            yield self.push_annotations_to_js()
            
            # Pre-fetch the next 3 images (labels already cached by batch load)
            current_idx = -1
            for i, img in enumerate(self.images):
                if img.id == image_id:
                    current_idx = i
                    break
            
            if current_idx != -1:
                next_images = self.images[current_idx + 1 : current_idx + 4]
                if next_images:
                    # Pre-fetch images only (labels already in cache from batch load)
                    next_urls = [img.full_url for img in next_images]
                    yield rx.call_script(f"window.prefetchImages && window.prefetchImages({next_urls})")

            # Scroll sidebar to show active thumbnail
            yield rx.call_script(
                f"document.getElementById('img-thumb-{image_id}')?.scrollIntoView({{block:'nearest',behavior:'smooth'}})"
            )

            
        except Exception as e:
            print(f"[DEBUG] Error loading image into canvas: {e}")
            self.error_message = f"Error loading image: {str(e)}"
        finally:
            self.is_image_loading = False
    
    async def next_image(self):
        """Navigate to the next image in the list."""
        if not self.images or not self.current_image_id:
            return
        
        # Find current index
        current_idx = -1
        for i, img in enumerate(self.images):
            if img.id == self.current_image_id:
                current_idx = i
                break
        
        if current_idx == -1 or current_idx >= len(self.images) - 1:
            print("[Python] Already at last image")
            return
        
        # Load next image
        next_image_id = self.images[current_idx + 1].id
        print(f"[Python] Navigating to next image: {next_image_id}")
        async for event in self._load_image_into_canvas(next_image_id):
            yield event
    
    async def prev_image(self):
        """Navigate to the previous image in the list."""
        if not self.images or not self.current_image_id:
            return
        
        # Find current index
        current_idx = -1
        for i, img in enumerate(self.images):
            if img.id == self.current_image_id:
                current_idx = i
                break
        
        if current_idx <= 0:
            print("[Python] Already at first image")
            return
        
        # Load previous image
        prev_image_id = self.images[current_idx - 1].id
        print(f"[Python] Navigating to previous image: {prev_image_id}")
        async for event in self._load_image_into_canvas(prev_image_id):
            yield event
    
    def handle_navigate_next(self, _: str):
        """Handler for hidden input trigger from JS."""
        return LabelingState.next_image
    
    def handle_navigate_prev(self, _: str):
        """Handler for hidden input trigger from JS."""
        return LabelingState.prev_image

    def navigate_next(self):
        """Navigate to next image (button click). Step 1.10.3."""
        return LabelingState.next_image

    def navigate_prev(self):
        """Navigate to previous image (button click). Step 1.10.3."""
        return LabelingState.prev_image

    async def delete_image(self, image_id: str):
        """Delete an image from R2 and database, including annotations."""
        try:
            # Find the image to get its R2 path
            image_to_delete = None
            image_idx = -1
            for i, img in enumerate(self.images):
                if img.id == image_id:
                    image_to_delete = img
                    image_idx = i
                    break
            
            if not image_to_delete:
                return
            
            print(f"[Labeling] Deleting image: {image_to_delete.filename}")
            
            r2 = R2Client()
            
            # 1. Delete image file from R2
            if image_to_delete.r2_path:
                try:
                    r2.delete_file(image_to_delete.r2_path)
                except Exception as e:
                    print(f"[DEBUG] Error deleting image from R2: {e}")
            
            # 2. Delete thumbnail from R2
            if image_to_delete.r2_path and "/images/" in image_to_delete.r2_path:
                thumbnail_path = image_to_delete.r2_path.replace("/images/", "/thumbnails/")
                try:
                    r2.delete_file(thumbnail_path)
                except Exception as e:
                    print(f"[DEBUG] Error deleting thumbnail from R2: {e}")
            
            # 3. Delete annotation file from R2
            label_path = f"datasets/{self.current_dataset_id}/labels/{image_id}.txt"
            try:
                r2.delete_file(label_path)
            except Exception as e:
                # Annotation file may not exist, that's okay
                pass
            
            # 4. Delete from database
            db_delete_image(image_id)
            
            # 5. Clean up local caches
            if image_id in self._saved_annotations:
                del self._saved_annotations[image_id]
            if image_id in self._label_cache:
                del self._label_cache[image_id]
            if image_id in self._pending_saves:
                del self._pending_saves[image_id]
            
            # 6. Remove from local state
            self.images = [img for img in self.images if img.id != image_id]
            
            # 7. Auto-navigate to next/prev image if we deleted the current one
            if self.current_image_id == image_id:
                if self.images:
                    # Try to go to same index or previous if at end
                    next_idx = min(image_idx, len(self.images) - 1)
                    next_image_id = self.images[next_idx].id
                    async for event in self._load_image_into_canvas(next_image_id):
                        yield event
                else:
                    # No more images
                    self.current_image_id = ""
                    self.current_image_url = ""
                    self.annotations = []
                    yield rx.call_script("window.renderAnnotations && window.renderAnnotations([])")
            
            yield rx.toast.success("Image deleted.")
            
        except Exception as e:
            print(f"[DEBUG] Error deleting image: {e}")
            import traceback
            traceback.print_exc()
            yield rx.toast.error("Failed to delete image.")
    
    # =========================================================================
    # MULTI-SELECTION & BULK DELETE
    # =========================================================================
    
    def handle_image_click(self, image_id: str, shift_key: bool):
        """Handle click on an image, supporting shift+click for range selection."""
        # Find the index of clicked image
        clicked_idx = -1
        for i, img in enumerate(self.images):
            if img.id == image_id:
                clicked_idx = i
                break
        
        if clicked_idx == -1:
            return
        
        if shift_key and self.last_clicked_image_idx >= 0:
            # Range selection from last clicked to current
            start_idx = min(self.last_clicked_image_idx, clicked_idx)
            end_idx = max(self.last_clicked_image_idx, clicked_idx)
            
            # Select all images in range
            range_ids = [self.images[i].id for i in range(start_idx, end_idx + 1)]
            
            # Add to existing selection (union)
            new_selection = list(set(self.selected_image_ids + range_ids))
            self.selected_image_ids = new_selection
        else:
            # Toggle single selection
            if image_id in self.selected_image_ids:
                self.selected_image_ids = [id for id in self.selected_image_ids if id != image_id]
            else:
                self.selected_image_ids = self.selected_image_ids + [image_id]
        
        self.last_clicked_image_idx = clicked_idx
        
        # Also select the image for viewing
        return LabelingState.select_image(image_id)
    
    def clear_image_selection(self):
        """Clear all selected images."""
        self.selected_image_ids = []
        self.last_clicked_image_idx = -1
    
    @rx.var
    def selected_image_count(self) -> int:
        """Number of selected images."""
        return len(self.selected_image_ids)
    
    @rx.var
    def has_image_selection(self) -> bool:
        """Check if any images are selected."""
        return len(self.selected_image_ids) > 0
    
    def open_bulk_delete_modal(self):
        """Open the bulk delete confirmation modal."""
        print(f"[Labeling] Open bulk delete modal. Selected: {len(self.selected_image_ids)}")
        if self.selected_image_ids:
            self.show_bulk_delete_modal = True
    
    def close_bulk_delete_modal(self):
        """Close the bulk delete modal."""
        self.show_bulk_delete_modal = False
    
    async def confirm_bulk_delete(self):
        """Delete all selected images."""
        print(f"[Labeling] Confirm bulk delete. Selected: {len(self.selected_image_ids)}")
        if not self.selected_image_ids:
            return
        
        self.is_bulk_deleting = True
        yield
        
        try:
            r2 = R2Client()
            deleted_count = 0
            ids_to_delete = list(self.selected_image_ids)  # Copy the list
            
            for image_id in ids_to_delete:
                # Find the image
                image_to_delete = None
                for img in self.images:
                    if img.id == image_id:
                        image_to_delete = img
                        break
                
                if not image_to_delete:
                    continue
                
                try:
                    # Delete from R2 (image)
                    if image_to_delete.r2_path:
                        try:
                            r2.delete_file(image_to_delete.r2_path)
                        except:
                            pass
                    
                    # Delete thumbnail
                    if image_to_delete.r2_path and "/images/" in image_to_delete.r2_path:
                        thumbnail_path = image_to_delete.r2_path.replace("/images/", "/thumbnails/")
                        try:
                            r2.delete_file(thumbnail_path)
                        except:
                            pass
                    
                    # Delete annotation file
                    label_path = f"datasets/{self.current_dataset_id}/labels/{image_id}.txt"
                    try:
                        r2.delete_file(label_path)
                    except:
                        pass
                    
                    # Delete from database
                    db_delete_image(image_id)
                    
                    # Clean up caches
                    if image_id in self._saved_annotations:
                        del self._saved_annotations[image_id]
                    if image_id in self._label_cache:
                        del self._label_cache[image_id]
                    if image_id in self._pending_saves:
                        del self._pending_saves[image_id]
                    
                    deleted_count += 1
                except Exception as e:
                    print(f"[Labeling] Error deleting image {image_id}: {e}")
            
            # Remove from local state
            self.images = [img for img in self.images if img.id not in ids_to_delete]
            
            # Clear selection
            self.selected_image_ids = []
            self.last_clicked_image_idx = -1
            
            # If current image was deleted, load another
            if self.current_image_id in ids_to_delete:
                if self.images:
                    async for event in self._load_image_into_canvas(self.images[0].id):
                        yield event
                else:
                    self.current_image_id = ""
                    self.current_image_url = ""
                    self.annotations = []
                    yield rx.call_script("window.renderAnnotations && window.renderAnnotations([])")
            
            self.show_bulk_delete_modal = False
            yield rx.toast.success(f"Deleted {deleted_count} image(s).")
            
        except Exception as e:
            print(f"[DEBUG] Error in bulk delete: {e}")
            yield rx.toast.error("Failed to delete some images.")
        finally:
            self.is_bulk_deleting = False


    # ZOOM & PAN HANDLERS (delegate to JS canvas)
    # =========================================================================
    
    def zoom_in(self):
        """Zoom in by one step (button click) — delegates to JS."""
        return rx.call_script("window.adjustZoom && window.adjustZoom(0.25)")
    
    def zoom_out(self):
        """Zoom out by one step (button click) — delegates to JS."""
        return rx.call_script("window.adjustZoom && window.adjustZoom(-0.25)")
    
    def reset_view(self):
        """Reset zoom and pan to default — delegates to JS."""
        return rx.call_script("window.resetView && window.resetView()")
    
    def sync_zoom_from_js(self, zoom_level: float):
        """Called from JS when zoom changes, to update UI display."""
        self.zoom_level = round(zoom_level, 2)
    
    # Note: Wheel zoom and Shift+drag pan are handled entirely in JS for 60fps.
    # The following handlers are kept for reference but no longer used:
    # - handle_wheel_zoom (replaced by JS handleWheel)
    # - start_pan / update_pan / stop_pan (replaced by JS pan handlers)

    
    @rx.var
    def zoom_percentage(self) -> str:
        """Zoom level as percentage string for display."""
        return f"{int(self.zoom_level * 100)}%"
    
    @rx.var
    def image_count(self) -> int:
        """Total number of images in project."""
        return len(self.images)

    @rx.var
    def current_image_index(self) -> int:
        """Index of current image (1-based for display)."""
        for i, img in enumerate(self.images):
            if img.id == self.current_image_id:
                return i + 1
        return 0
    
    @rx.var
    def has_images(self) -> bool:
        """Check if project has any images."""
        return len(self.images) > 0
    
    @rx.var
    def has_current_image(self) -> bool:
        """Check if an image is currently loaded."""
        return self.current_image_url != ""
    
    @rx.var
    def labeled_count(self) -> int:
        """Count of labeled images for progress display."""
        return sum(1 for img in self.images if img.labeled)
    
    # =========================================================================
    # AUTO-LABELING (SAM3)
    # =========================================================================
    
    @rx.var
    def empty_image_count(self) -> int:
        """Count images with zero annotations."""
        return sum(1 for img in self.images if img.annotation_count == 0)
    
    @rx.var
    def autolabel_target_count(self) -> int:
        """Count of images targeted for current autolabel config.
        
        - Both/bbox-only: empty images (no annotations)
        - Mask-only with annotated images: images with bboxes (fast path, scenario 2)
        - Mask-only without annotated images: empty images (text prompt, scenario 3)
        """
        if self.autolabel_generate_masks and not self.autolabel_generate_bboxes:
            # Mask-only: prefer annotated images (fast path), fall back to empty (text-prompt)
            annotated = sum(1 for img in self.images if img.annotation_count > 0)
            if annotated > 0:
                return annotated
            return self.empty_image_count
        return self.empty_image_count
    
    @rx.var
    def annotated_image_count(self) -> int:
        """Count images with at least one annotation."""
        return sum(1 for img in self.images if img.annotation_count > 0)
    
    @rx.var
    def autolabel_mask_fast_path(self) -> bool:
        """True when mask-only mode can use the bbox-prompt fast path.
        
        This means: masks only selected, AND annotated images exist.
        In this mode, no text prompt or class mapping is needed.
        """
        return (
            self.autolabel_generate_masks
            and not self.autolabel_generate_bboxes
            and self.annotated_image_count > 0
        )
    
    # =========================================================================
    # EMPTY IMAGES STATS MODAL
    # =========================================================================
    
    def open_empty_stats_modal(self):
        """Open the empty images stats modal."""
        self.show_empty_stats_modal = True
        self.empty_delete_confirmation = ""
    
    def close_empty_stats_modal(self):
        """Close the empty images stats modal."""
        self.show_empty_stats_modal = False
        self.empty_delete_confirmation = ""
    
    def set_empty_delete_confirmation(self, value: str):
        """Update the delete confirmation input."""
        self.empty_delete_confirmation = value
    
    @rx.var
    def can_confirm_delete_empty(self) -> bool:
        """Check if delete confirmation is valid."""
        return self.empty_delete_confirmation.lower() == "delete"
    
    @rx.var
    def annotated_image_count(self) -> int:
        """Count images with at least one annotation."""
        return sum(1 for img in self.images if img.annotation_count > 0)
    
    async def delete_empty_images(self):
        """Delete all images with zero annotations."""
        if self.empty_delete_confirmation.lower() != "delete":
            yield rx.toast.error("Please type 'delete' to confirm.")
            return
        
        self.is_deleting_empty_images = True
        yield
        
        try:
            r2 = R2Client()
            deleted_count = 0
            
            # Get list of empty image IDs
            empty_image_ids = [img.id for img in self.images if img.annotation_count == 0]
            
            if not empty_image_ids:
                self.is_deleting_empty_images = False
                self.show_empty_stats_modal = False
                yield rx.toast.info("No empty images to delete.")
                return
            
            for image_id in empty_image_ids:
                # Find the image
                image_to_delete = None
                for img in self.images:
                    if img.id == image_id:
                        image_to_delete = img
                        break
                
                if not image_to_delete:
                    continue
                
                try:
                    # Delete from R2 (image)
                    if image_to_delete.r2_path:
                        try:
                            r2.delete_file(image_to_delete.r2_path)
                        except:
                            pass
                    
                    # Delete thumbnail
                    if image_to_delete.r2_path and "/images/" in image_to_delete.r2_path:
                        thumbnail_path = image_to_delete.r2_path.replace("/images/", "/thumbnails/")
                        try:
                            r2.delete_file(thumbnail_path)
                        except:
                            pass
                    
                    # Delete annotation file (if any)
                    label_path = f"datasets/{self.current_dataset_id}/labels/{image_id}.txt"
                    try:
                        r2.delete_file(label_path)
                    except:
                        pass
                    
                    # Delete from database
                    db_delete_image(image_id)
                    
                    # Clean up caches
                    if image_id in self._saved_annotations:
                        del self._saved_annotations[image_id]
                    if image_id in self._label_cache:
                        del self._label_cache[image_id]
                    if image_id in self._pending_saves:
                        del self._pending_saves[image_id]
                    
                    deleted_count += 1
                except Exception as e:
                    print(f"[Labeling] Error deleting image {image_id}: {e}")
            
            # Remove from local state
            self.images = [img for img in self.images if img.id not in empty_image_ids]
            
            # If current image was deleted, load another
            if self.current_image_id in empty_image_ids:
                if self.images:
                    async for event in self._load_image_into_canvas(self.images[0].id):
                        yield event
                else:
                    self.current_image_id = ""
                    self.current_image_url = ""
                    self.annotations = []
                    yield rx.call_script("window.renderAnnotations && window.renderAnnotations([])")
            
            self.show_empty_stats_modal = False
            self.empty_delete_confirmation = ""
            yield rx.toast.success(f"Deleted {deleted_count} empty image(s).")
            
        except Exception as e:
            print(f"[DEBUG] Error in delete empty images: {e}")
            yield rx.toast.error("Failed to delete some images.")
        finally:
            self.is_deleting_empty_images = False

    @rx.var
    def can_autolabel(self) -> bool:
        """Check if auto-labeling can start (SAM3 mode)."""
        # At least one generation option must be selected
        if not self.autolabel_generate_bboxes and not self.autolabel_generate_masks:
            return False
        
        # Must have target images and not be currently running
        if self.autolabel_target_count <= 0 or self.is_autolabeling:
            return False
        
        # Fast path: mask-only with existing bboxes — no prompt needed
        if self.autolabel_mask_fast_path:
            return True
        
        # Standard path: require prompt + class mappings
        return (
            self.autolabel_prompt.strip() != ""
            and len(self.autolabel_prompt_terms) > 0
            and self.all_prompts_mapped
        )
    
    @rx.var
    def all_prompts_mapped(self) -> bool:
        """Check if all prompt terms have valid class mappings."""
        if not self.autolabel_prompt_terms:
            return False
        if len(self.autolabel_class_mappings) != len(self.autolabel_prompt_terms):
            return False
        # Check all mappings are valid (not -1 and within range)
        for mapping in self.autolabel_class_mappings:
            if mapping < 0 or mapping >= len(self.project_classes):
                return False
        return True
    
    def set_autolabel_prompt(self, prompt: str):
        """Update the auto-label prompt and parse terms."""
        self.autolabel_prompt = prompt
        # Parse comma-separated terms
        if prompt.strip():
            terms = [t.strip() for t in prompt.split(",") if t.strip()]
            self.autolabel_prompt_terms = terms
            # Initialize mappings with -1 (unmapped) for new terms
            # Preserve existing mappings for unchanged terms count
            if len(terms) != len(self.autolabel_class_mappings):
                self.autolabel_class_mappings = [-1] * len(terms)
        else:
            self.autolabel_prompt_terms = []
            self.autolabel_class_mappings = []

    async def save_autolabel_prompt_pref(self, _value: str = ""):
        """Save SAM3 prompt preference on blur."""
        auth_state = await self.get_state(AuthState)
        user_id = auth_state.user.get("id") if auth_state.user else None
        if user_id:
            update_user_preferences(user_id, "autolabel", {
                "sam3_prompt": self.autolabel_prompt,
            })

    async def save_autolabel_confidence_pref(self, value=None):
        """Save autolabel confidence preference."""
        auth_state = await self.get_state(AuthState)
        user_id = auth_state.user.get("id") if auth_state.user else None
        if user_id:
            update_user_preferences(user_id, "autolabel", {
                "confidence": self.autolabel_confidence,
            })
    
    def set_prompt_class_mapping(self, term_idx: int, class_name: str):
        """Set the class mapping for a specific prompt term."""
        if term_idx < 0 or term_idx >= len(self.autolabel_prompt_terms):
            return
        # Find class index by name
        try:
            class_idx = self.project_classes.index(class_name)
        except ValueError:
            class_idx = -1
        # Update mapping
        new_mappings = list(self.autolabel_class_mappings)
        while len(new_mappings) <= term_idx:
            new_mappings.append(-1)
        new_mappings[term_idx] = class_idx
        self.autolabel_class_mappings = new_mappings
    
    def set_autolabel_class_id(self, class_id: str):
        """Set the class ID for auto-labeling (legacy, kept for compatibility)."""
        try:
            self.autolabel_class_id = int(class_id)
        except ValueError:
            pass
    
    def set_autolabel_confidence(self, value: list[float]):
        """Set confidence threshold from slider."""
        if value:
            self.autolabel_confidence = value[0]
    
    @rx.var
    def autolabel_confidence_percentage(self) -> str:
        """Get confidence as percentage string for display."""
        return f"{int(self.autolabel_confidence * 100)}%"
    
    async def set_autolabel_bbox_padding(self, value: list[float]):
        """Set bbox padding from slider and persist preference."""
        if value:
            self.autolabel_bbox_padding = round(value[0], 2)
            # Persist preference
            auth_state = await self.get_state(AuthState)
            user_id = auth_state.user.get("id") if auth_state.user else None
            if user_id:
                update_user_preferences(user_id, "autolabel", {
                    "bbox_padding": self.autolabel_bbox_padding,
                })
    
    @rx.var
    def autolabel_bbox_padding_percentage(self) -> str:
        """Get bbox padding as percentage string for display."""
        return f"{int(self.autolabel_bbox_padding * 100)}%"
    
    def toggle_autolabel_logs(self):
        """Toggle log panel visibility."""
        self.show_autolabel_logs = not self.show_autolabel_logs
    
    def toggle_autolabel_panel(self):
        """Toggle autolabel panel visibility (legacy)."""
        self.show_autolabel_panel = not self.show_autolabel_panel
    
    # =========================================================================
    # AUTOLABEL MODAL CONTROLS
    # =========================================================================
    
    async def open_autolabel_modal(self, _value=None):
        """Open autolabel modal and load available models."""
        self.show_autolabel_modal = True
        self.autolabel_error = ""
        # Load available YOLO models for autolabeling
        await self._load_autolabel_models()
        # Load local machines for compute target toggle
        auth_state = await self.get_state(AuthState)
        user_id = auth_state.user.get("id") if auth_state.user else None
        if user_id:
            self.local_machines = get_user_local_machines(user_id)
            # Restore autolabel preferences
            prefs = get_user_preferences(user_id)
            autolabel_prefs = prefs.get("autolabel", {})
            saved_padding = autolabel_prefs.get("bbox_padding")
            if saved_padding is not None:
                self.autolabel_bbox_padding = float(saved_padding)
            saved_prompt = autolabel_prefs.get("sam3_prompt", "")
            if saved_prompt and not self.autolabel_prompt:
                self.set_autolabel_prompt(saved_prompt)
            saved_confidence = autolabel_prefs.get("confidence")
            if saved_confidence is not None:
                self.autolabel_confidence = float(saved_confidence)
    
    def set_compute_target(self, value):
        """Set compute target (cloud/local)."""
        target = value[0] if isinstance(value, list) else value
        self.compute_target = target
        if target != "local":
            self.selected_machine = ""
    
    def set_selected_machine(self, value: str):
        """Set the selected local machine."""
        self.selected_machine = value
    
    @rx.var
    def has_local_machines(self) -> bool:
        """Check if any local machines are configured."""
        return len(self.local_machines) > 0
    
    def close_autolabel_modal(self):
        """Close autolabel modal."""
        self.show_autolabel_modal = False
        # Don't reset state so user doesn't lose settings
    
    def set_show_autolabel_modal(self, open: bool):
        """Handle dialog open/close state change."""
        if open:
            return LabelingState.open_autolabel_modal
        else:
            self.show_autolabel_modal = False
    
    def set_autolabel_mode(self, mode: str):
        """Switch between SAM3 and YOLO modes."""
        self.autolabel_mode = mode
    
    def select_autolabel_model(self, model_id: str):
        """Select a YOLO model for autolabeling."""
        self.selected_autolabel_model_id = model_id
    
    async def _load_autolabel_models(self):
        """Load models with volume_path available for autolabeling."""
        from backend.supabase_client import get_autolabel_models, get_accessible_project_ids
        
        auth_state = await self.get_state(AuthState)
        user_id = auth_state.user.get("id") if auth_state.user else None
        
        if not user_id:
            self.available_autolabel_models = []
            return
        
        try:
            project_ids = get_accessible_project_ids(user_id)
            models = get_autolabel_models(project_ids)
            self.available_autolabel_models = models
            print(f"[AutoLabel] Loaded {len(models)} models with volume_path")
            
            # Restore saved model preference
            prefs = get_user_preferences(user_id)
            autolabel_prefs = prefs.get("autolabel", {})
            saved_model_id = autolabel_prefs.get("selected_model_id", "")
            if saved_model_id:
                # Verify model still exists
                if any(m.get("id") == saved_model_id for m in models):
                    self.selected_autolabel_model_id = saved_model_id
                    print(f"[AutoLabel] Restored saved model: {saved_model_id}")
        except Exception as e:
            print(f"[AutoLabel] Error loading models: {e}")
            self.available_autolabel_models = []
    
    @rx.var
    def has_autolabel_models(self) -> bool:
        """Check if any YOLO models are available for autolabeling."""
        return len(self.available_autolabel_models) > 0
    
    @rx.var
    def autolabel_model_names(self) -> list[str]:
        """Get list of model display names for select dropdown."""
        return [m.get("display_name", m.get("name", "")) for m in self.available_autolabel_models]
    
    @rx.var
    def selected_autolabel_model_name(self) -> str:
        """Get the display name of the currently selected autolabel model."""
        if not self.selected_autolabel_model_id:
            return ""
        for m in self.available_autolabel_models:
            if m.get("id") == self.selected_autolabel_model_id:
                return m.get("display_name", m.get("name", ""))
        return ""
    
    async def select_autolabel_model_by_name(self, name: str):
        """Select a YOLO model by its display name and persist preference."""
        for m in self.available_autolabel_models:
            display_name = m.get("display_name", m.get("name", ""))
            if display_name == name:
                self.selected_autolabel_model_id = m.get("id", "")
                # Persist preference
                auth_state = await self.get_state(AuthState)
                user_id = auth_state.user.get("id") if auth_state.user else None
                if user_id:
                    update_user_preferences(user_id, "autolabel", {
                        "selected_model_id": self.selected_autolabel_model_id,
                    })
                return
        self.selected_autolabel_model_id = ""
    
    @rx.var
    def can_autolabel_yolo(self) -> bool:
        """Check if YOLO autolabeling can start."""
        return (
            self.selected_autolabel_model_id != "" and
            self.empty_image_count > 0 and
            not self.is_autolabeling
        )
    
    @rx.var
    def current_masks_css(self) -> list[dict]:
        """Convert current annotations' mask_polygon to CSS clip-path format."""
        masks = []
        for ann in self.annotations:
            polygon = ann.get("mask_polygon")
            if not polygon:
                continue
            # Convert normalized points to CSS percentages
            points_css = ", ".join(
                f"{pt[0] * 100:.2f}% {pt[1] * 100:.2f}%"
                for pt in polygon
            )
            masks.append({
                "clip_path": f"polygon({points_css})",
                "class_name": ann.get("class_name", "Unknown"),
                "class_id": ann.get("class_id", 0),
            })
        return masks

    @rx.var
    def selected_annotation_has_mask(self) -> bool:
        """Check if the currently selected annotation has a mask_polygon."""
        if not self.selected_annotation_id:
            return False
        for ann in self.annotations:
            if ann.get("id") == self.selected_annotation_id:
                polygon = ann.get("mask_polygon")
                return polygon is not None and len(polygon) >= 3
        return False
    
    @rx.event(background=True)
    async def start_autolabel(self):
        """Start auto-labeling job on Modal (SAM3 or YOLO mode)."""
        import modal
        
        async with self:
            # Check the right condition based on mode
            mode = self.autolabel_mode
            if mode == "yolo":
                if not self.can_autolabel_yolo:
                    return
            else:
                if not self.can_autolabel:
                    return
            
            self.is_autolabeling = True
            self.autolabel_logs = ""
            self.autolabel_error = ""
            
            # Capture state for background execution
            dataset_id = self.current_dataset_id
            prompt = self.autolabel_prompt
            class_id = self.autolabel_class_id
            confidence = self.autolabel_confidence
            autolabel_mode = self.autolabel_mode
            selected_model_id = self.selected_autolabel_model_id
            target = self.compute_target
            machine_name = self.selected_machine if target == "local" else None
            bbox_padding = self.autolabel_bbox_padding
            generate_bboxes = self.autolabel_generate_bboxes
            generate_masks = self.autolabel_generate_masks
            
            # Build prompt_class_map from state mappings
            prompt_class_map = {}
            for i, term in enumerate(self.autolabel_prompt_terms):
                if i < len(self.autolabel_class_mappings):
                    prompt_class_map[term] = self.autolabel_class_mappings[i]
            
            # Get user context
            auth_state = await self.get_state(AuthState)
            user_id = auth_state.user.get("id") if auth_state.user else None
        
        yield
        
        try:
            if not user_id:
                raise Exception("User not authenticated")
            
            # Filter images based on generation mode
            async with self:
                mask_only_mode = generate_masks and not generate_bboxes
                if mask_only_mode:
                    # Mask-only: prefer images with existing bboxes (fast path, scenario 2)
                    annotated_images = [img for img in self.images if img.annotation_count > 0]
                    if annotated_images:
                        target_images = annotated_images
                        existing_annotations = None  # Will be loaded from DB below
                    else:
                        # No annotated images — text-prompt on empty images (scenario 3)
                        target_images = [img for img in self.images if img.annotation_count == 0]
                        existing_annotations = None
                else:
                    # Standard: empty images only (scenarios 1 & 4)
                    target_images = [img for img in self.images if img.annotation_count == 0]
                    existing_annotations = None
            
            # For mask-only mode with annotated images, fetch annotations from database
            if mask_only_mode and existing_annotations is None and target_images:
                # Only load annotations if we're targeting annotated images (fast path)
                has_annotated = any(img.annotation_count > 0 for img in target_images)
                if has_annotated:
                    from backend.supabase_client import get_image_annotations
                    existing_annotations = {}
                    for img in target_images:
                        if img.annotation_count > 0:
                            db_anns = get_image_annotations(img.id)
                            if db_anns:
                                existing_annotations[img.id] = db_anns
                            else:
                                print(f"[AutoLabel] Warning: no DB annotations for {img.id}, skipping")
                    # Filter out images where we couldn't load annotations
                    target_images = [img for img in target_images if img.id in existing_annotations]
            
            if not target_images:
                async with self:
                    self.is_autolabeling = False
                    self.autolabel_error = "No eligible images found"
                msg = "No images without masks" if mask_only_mode else "No empty images found"
                yield rx.toast.warning(msg)
                return
            
            print(f"[AutoLabel] Starting job for {len(target_images)} images (mask_only={mask_only_mode})")
            
            # Generate presigned URLs
            from backend.r2_storage import R2Client
            r2 = R2Client()
            image_urls = {}
            
            for img in target_images:
                try:
                    url = r2.generate_presigned_url(img.r2_path, expires_in=7200)  # 2 hours
                    image_urls[img.id] = url
                except Exception as e:
                    print(f"[AutoLabel] Failed to generate URL for {img.id}: {e}")
            
            if not image_urls:
                async with self:
                    self.is_autolabeling = False
                    self.autolabel_error = "Failed to generate image URLs"
                yield rx.toast.error("Failed to prepare images")
                return
            
            # Create job in Supabase
            from backend.supabase_client import create_autolabel_job
            job = create_autolabel_job(
                dataset_id=dataset_id,
                user_id=user_id,
                prompt_type="text",
                prompt_value=prompt,
                target_count=len(image_urls),
                class_id=class_id,
                confidence=confidence
            )
            
            if not job:
                raise Exception("Failed to create auto-label job in database")
            
            job_id = job["id"]
            
            async with self:
                self.autolabel_job_id = job_id
                self.autolabel_logs = f"Starting auto-labeling for {len(image_urls)} images...\n"
            
            yield
            
            # Dispatch autolabel job (routes to Modal or Local GPU)
            try:
                from backend.job_router import dispatch_autolabel_job
                
                # Different parameters based on mode
                if autolabel_mode == "yolo":
                    # YOLO mode: Use custom trained model
                    dispatch_autolabel_job(
                        dataset_id=dataset_id,
                        job_id=job_id,
                        image_urls=image_urls,
                        prompt_type="yolo",
                        confidence=confidence,
                        model_id=selected_model_id,
                        target=target,
                        user_id=user_id,
                        machine_name=machine_name,
                    )
                    print(f"[AutoLabel] Job dispatched (YOLO mode): {job_id}")
                else:
                    # SAM3 mode: Use text prompt with class mappings
                    dispatch_autolabel_job(
                        dataset_id=dataset_id,
                        job_id=job_id,
                        image_urls=image_urls,
                        prompt_type="text",
                        prompt_value=prompt,
                        class_id=class_id,
                        confidence=confidence,
                        prompt_class_map=prompt_class_map,
                        target=target,
                        user_id=user_id,
                        machine_name=machine_name,
                        generate_bboxes=generate_bboxes,
                        generate_masks=generate_masks,
                        existing_annotations=existing_annotations,
                    )
                    print(f"[AutoLabel] Job dispatched (SAM3 mode): {job_id}")
                    print(f"[AutoLabel] Prompt-class map: {prompt_class_map}, masks={generate_masks}, bboxes={generate_bboxes}")
                
                # Start polling
                yield LabelingState.poll_autolabel_status()
                
            except Exception as e:
                # If dispatch fails, update job status
                from backend.supabase_client import update_autolabel_job
                update_autolabel_job(
                    job_id,
                    status="failed",
                    error_message=f"Modal spawn failed: {str(e)}"
                )
                raise e
            
        except Exception as e:
            print(f"[AutoLabel] Error: {e}")
            async with self:
                self.is_autolabeling = False
                self.autolabel_error = str(e)
            yield rx.toast.error(f"Failed to start auto-labeling: {str(e)}")
    
    @rx.event(background=True)
    async def poll_autolabel_status(self):
        """Background polling for auto-label job status."""
        import asyncio
        from backend.supabase_client import get_autolabel_job
        
        async with self:
            if self.is_polling_autolabel:
                return
            self.is_polling_autolabel = True
            job_id = self.autolabel_job_id
        
        try:
            while True:
                # Poll every 2 seconds
                await asyncio.sleep(2)
                
                # Fetch job status
                job = get_autolabel_job(job_id)
                if not job:
                    print("[AutoLabel Poll] Job not found")
                    break
                
                status = job.get("status", "pending")
                logs = job.get("logs", "")
                
                async with self:
                    self.autolabel_logs = logs if logs else "Waiting for logs..."
                
                yield
                
                # Check if job is complete
                if status in ["completed", "failed"]:
                    print(f"[AutoLabel Poll] Job finished with status: {status}")
                    
                    async with self:
                        self.is_autolabeling = False
                        self.is_polling_autolabel = False
                        
                        if status == "completed":
                            detections_count = job.get("detections_count", 0)
                            processed_count = job.get("processed_count", 0)
                            self.autolabel_logs += f"\n\nCompleted! Processed {processed_count} images, created {detections_count} detections."
                            
                            # Reload images to update annotation counts
                            # Reset state
                            self.autolabel_prompt = ""
                            self.autolabel_job_id = ""
                        else:
                            # Failed
                            error_msg = job.get("error_message", "Unknown error")
                            self.autolabel_error = error_msg
                            self.autolabel_logs += f"\n\nFailed: {error_msg}"
                    
                    yield
                    
                    # Show toast notification
                    if status == "completed":
                        detections_count = job.get("detections_count", 0)
                        processed_count = job.get("processed_count", 0)
                        
                        if detections_count > 0 or processed_count > 0:
                            if detections_count > 0:
                                yield rx.toast.success(f"Auto-labeling completed: {detections_count} detections created")
                            else:
                                yield rx.toast.success(f"Mask generation completed for {processed_count} images")
                            
                            # Close modal and reload images (no page refresh needed)
                            async with self:
                                self.show_autolabel_modal = False
                            
                            # Reload images and annotations
                            yield LabelingState.reload_images()
                        else:
                            yield rx.toast.info("Auto-labeling completed: No detections found")
                    else:
                        yield rx.toast.error("Auto-labeling failed")
                    
                    break
                
        finally:
            async with self:
                self.is_polling_autolabel = False
    
    async def reload_images(self):
        """Reload annotation counts and current image annotations after auto-labeling."""
        try:
            from backend.supabase_client import get_dataset_images
            
            dataset_id = self.current_dataset_id
            if not dataset_id:
                return
            
            # Fetch fresh image data to get updated annotation counts
            raw_images = get_dataset_images(dataset_id)
            
            # Build a lookup of annotation counts by image ID
            counts_by_id = {
                str(img["id"]): img.get("annotation_count", 0)
                for img in raw_images
            }
            
            # Update annotation counts in existing images
            updated_images = []
            for img in self.images:
                new_count = counts_by_id.get(img.id, img.annotation_count)
                updated_images.append(ImageModel(
                    id=img.id,
                    filename=img.filename,
                    r2_path=img.r2_path,
                    width=img.width,
                    height=img.height,
                    labeled=new_count > 0,
                    annotation_count=new_count,
                    thumbnail_url=img.thumbnail_url,
                    full_url=img.full_url,
                ))
            
            self.images = updated_images
            print(f"[AutoLabel] Updated annotation counts for {len(updated_images)} images")
            
            # Clear annotation cache so fresh data is loaded from Supabase
            # (autolabel wrote new annotations that aren't in the cache)
            self._label_cache.clear()
            self._saved_annotations.clear()
            self._last_saved_annotations.clear()
            print("[AutoLabel] Cleared annotation cache for fresh reload")
            
            # Re-batch-load all annotations from Supabase (single query)
            self._batch_load_all_annotations()
            
            # Re-select current image to reload annotations into canvas
            if self.current_image_id:
                print(f"[AutoLabel] Re-selecting current image {self.current_image_id}")
                async for event in self._load_image_into_canvas(self.current_image_id):
                    yield event
            
        except Exception as e:
            print(f"[AutoLabel] Error reloading: {e}")
    
    def cancel_autolabel(self):
        """Cancel active auto-labeling (stop polling, UI reset)."""
        print("[AutoLabel] Cancelling auto-label job")
        self.is_autolabeling = False
        self.is_polling_autolabel = False
        self.autolabel_error = "Cancelled by user"
        # Note: Cannot stop Modal job once started, only stops frontend polling
