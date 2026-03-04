"""
Datasets State — State management for datasets within a project.

Datasets contain images or videos for labeling. Classes are defined at the dataset level.
"""

import reflex as rx
import uuid
import tempfile
import os
import json
import io
import zipfile
from typing import Optional
from PIL import Image as PILImage
from backend.supabase_client import (
    get_project,
    get_project_datasets,
    create_dataset as db_create_dataset,
    delete_dataset as db_delete_dataset,
    get_dataset_image_count,
    bulk_create_images,
    update_project as db_update_project,
    get_user_projects,
    get_dataset_images,
    get_dataset_videos,
    get_video_keyframes,
    promote_to_team_project,
    demote_from_team_project,
)
from backend.r2_storage import R2Client
from backend.zip_processor import (
    extract_and_parse_zip,
    parse_yolo_label,
    YOLODatasetInfo,
    ZipProcessorError,
)
from app_state import AuthState
from modules.projects.models import DatasetModel


class DatasetsState(rx.State):

    """State for the project detail page showing datasets."""
    
    # Current project context
    current_project_id: str = ""
    project_name: str = ""
    project_description: str = ""
    project_classes: list[str] = []
    is_team_project: bool = False
    project_owner_id: str = ""
    
    # Datasets list
    datasets: list[DatasetModel] = []
    is_loading: bool = False  # Default to False to prevent skeleton flash on re-navigation
    _has_loaded_once: bool = False  # Track first load for skeleton display
    
    # Create Modal state
    show_modal: bool = False
    new_dataset_name: str = ""
    new_dataset_type: str = "image"
    new_dataset_classes: str = ""
    is_creating: bool = False
    create_error: str = ""
    
    # Delete Modal state
    show_delete_modal: bool = False
    delete_dataset_id: str = ""
    delete_dataset_name: str = ""
    delete_dataset_image_count: int = 0
    delete_confirmation_text: str = ""
    is_deleting: bool = False
    delete_error: str = ""
    
    # Edit Project Modal state
    show_edit_project_modal: bool = False
    edit_project_name: str = ""
    edit_project_description: str = ""
    is_saving_project: bool = False
    edit_project_error: str = ""
    

    
    async def load_project_and_datasets(self):
        """Load project info and all datasets on page load."""
        # Only show skeleton on first load to prevent flickering on re-navigation
        if not self._has_loaded_once:
            self.is_loading = True
            yield
        
        try:
            # Get project_id from route
            project_id = self.router.page.params.get("project_id", "")
            if not project_id:
                print("[DEBUG] No project_id in route")
                return
            
            self.current_project_id = project_id
            
            # Load project details
            project = get_project(project_id)
            if project:
                self.project_name = project.get("name", "")
                self.project_description = project.get("description", "") or ""
                self.project_classes = project.get("classes", []) or []
                self.is_team_project = project.get("is_company", False) or False
                self.project_owner_id = project.get("user_id", "")

            else:
                print(f"[DEBUG] Project {project_id} not found")
                return
            
            # Load datasets with thumbnails
            raw_datasets = get_project_datasets(project_id)
            print(f"[DEBUG] Got {len(raw_datasets)} datasets for project {project_id}")
            r2 = R2Client()
            datasets = []
            for d in raw_datasets:
                thumb_r2_path = d.get("thumbnail_r2_path", "")
                thumb_url = ""
                if thumb_r2_path:
                    thumb_url = r2.generate_presigned_url(thumb_r2_path, expires_in=3600) or ""
                datasets.append(DatasetModel(
                    id=str(d.get("id", "")),
                    project_id=str(d.get("project_id", "")),
                    name=str(d.get("name", "")),
                    type=str(d.get("type", "image")),
                    description=str(d.get("description", "") or ""),
                    created_at=str(d.get("created_at", "")),
                    usage_tag=str(d.get("usage_tag", "train")),
                    thumbnail_url=thumb_url,
                ))
            self.datasets = datasets
            
            # Load annotation statistics
            async for event in self.load_annotation_stats():
                yield event
            

                
        except Exception as e:
            print(f"[DEBUG] Error loading datasets: {e}")
            self.datasets = []
        finally:
            self.is_loading = False
            self._has_loaded_once = True
    
    # =========================================================================
    # CREATE MODAL
    # =========================================================================
    
    def open_modal(self):
        """Open the new dataset modal."""
        self.show_modal = True
        self.new_dataset_name = ""
        self.new_dataset_type = "image"
        self.new_dataset_classes = ""
        self.create_error = ""
    
    def close_modal(self):
        """Close the new dataset modal."""
        self.show_modal = False
        self.new_dataset_name = ""
        self.new_dataset_type = "image"
        self.new_dataset_classes = ""
        self.create_error = ""
    
    def set_dataset_name(self, value: str):
        """Update the new dataset name."""
        self.new_dataset_name = value
    
    def set_dataset_type(self, value: str):
        """Update the new dataset type."""
        self.new_dataset_type = value
    
    def set_dataset_classes(self, value: str):
        """Update the new dataset classes."""
        self.new_dataset_classes = value
    
    async def create_dataset(self):
        """Create a new dataset and redirect to it."""
        if not self.new_dataset_name.strip():
            self.create_error = "Dataset name is required."
            return
        
        self.is_creating = True
        self.create_error = ""
        yield
        
        try:
            # Parse classes from comma-separated string (these will be added to project, not dataset)
            new_classes = []
            if self.new_dataset_classes.strip():
                new_classes = [c.strip() for c in self.new_dataset_classes.split(",") if c.strip()]
            
            # Create dataset in database (classes are project-level, not dataset-level)
            dataset = db_create_dataset(
                project_id=self.current_project_id,
                name=self.new_dataset_name.strip(),
                type=self.new_dataset_type,
            )
            
            if dataset:
                # If new classes were specified, merge them into project classes
                if new_classes:
                    existing = set(self.project_classes)
                    classes_to_add = [c for c in new_classes if c not in existing]
                    if classes_to_add:
                        updated_classes = self.project_classes + classes_to_add
                        db_update_project(self.current_project_id, classes=updated_classes)
                        self.project_classes = updated_classes
                
                self.close_modal()
                # Redirect to the new dataset detail page
                yield rx.redirect(f"/projects/{self.current_project_id}/datasets/{dataset['id']}")
            else:
                self.create_error = "Failed to create dataset. Please try again."
                
        except Exception as e:
            self.create_error = f"Error: {str(e)}"
        finally:
            self.is_creating = False
    
    # =========================================================================
    # DELETE MODAL
    # =========================================================================
    
    def open_delete_modal(self, dataset_id: str, dataset_name: str, image_count: int):
        """Open the delete confirmation modal."""
        self.show_delete_modal = True
        self.delete_dataset_id = dataset_id
        self.delete_dataset_name = dataset_name
        self.delete_dataset_image_count = image_count
        self.delete_confirmation_text = ""
        self.delete_error = ""
    
    def close_delete_modal(self):
        """Close the delete confirmation modal."""
        self.show_delete_modal = False
        self.delete_dataset_id = ""
        self.delete_dataset_name = ""
        self.delete_dataset_image_count = 0
        self.delete_confirmation_text = ""
        self.delete_error = ""
    
    def set_delete_confirmation_text(self, value: str):
        """Update the delete confirmation text."""
        self.delete_confirmation_text = value
    
    @rx.var
    def can_delete(self) -> bool:
        """Check if the delete confirmation text matches 'delete'."""
        return self.delete_confirmation_text.lower().strip() == "delete"
    
    async def confirm_delete_dataset(self):
        """Delete the dataset after confirmation."""
        if not self.can_delete:
            self.delete_error = "Please type 'delete' to confirm."
            return
        
        self.is_deleting = True
        self.delete_error = ""
        yield
        
        try:
            # 1. Cleanup R2 files for this dataset (best-effort)
            try:
                r2 = R2Client()
                deleted_count = r2.delete_files_with_prefix(f"datasets/{self.delete_dataset_id}/")
                print(f"[DEBUG] Deleted {deleted_count} files from R2 for dataset {self.delete_dataset_id}")
            except Exception as r2_err:
                print(f"[DEBUG] R2 cleanup skipped (empty dataset or R2 error): {r2_err}")
            
            # 2. Delete from database (cascades to images via FK)
            success = db_delete_dataset(self.delete_dataset_id)
            
            if success:
                self.close_delete_modal()
                # Reload datasets list
                async for event in self.load_project_and_datasets():
                    yield event
                yield rx.toast.success(f"Dataset '{self.delete_dataset_name}' deleted.")
            else:
                self.delete_error = "Failed to delete dataset. Please try again."
                
        except Exception as e:
            print(f"[DEBUG] Error deleting dataset: {e}")
            self.delete_error = f"Error: {str(e)}"
        finally:
            self.is_deleting = False
    
    @rx.var
    def has_datasets(self) -> bool:
        """Check if project has any datasets."""
        return len(self.datasets) > 0
    
    @rx.var
    def image_dataset_count(self) -> int:
        """Count of image datasets."""
        return sum(1 for d in self.datasets if d.type == "image")
    
    @rx.var
    def video_dataset_count(self) -> int:
        """Count of video datasets."""
        return sum(1 for d in self.datasets if d.type == "video")
    
    @rx.var
    def total_class_count(self) -> int:
        """Total count of project classes (classes are project-level, not dataset-level)."""
        return len(self.project_classes)
    
    # =========================================================================
    # ANNOTATION STATISTICS
    # =========================================================================
    
    annotation_stats: dict = {}
    is_loading_stats: bool = False
    
    @rx.var
    def total_items(self) -> int:
        """Total images + keyframes across all datasets."""
        return self.annotation_stats.get("total_images", 0) + self.annotation_stats.get("total_keyframes", 0)
    
    @rx.var
    def labeled_items(self) -> int:
        """Total labeled images + keyframes."""
        return self.annotation_stats.get("labeled_images", 0) + self.annotation_stats.get("labeled_keyframes", 0)
    
    @rx.var
    def labeling_progress(self) -> int:
        """Percentage of items labeled (rounded to whole number)."""
        total = self.total_items
        if total == 0:
            return 0
        return round((self.labeled_items / total) * 100)
    
    @rx.var
    def class_distribution_data(self) -> list[dict]:
        """Format class distribution for recharts - includes all project classes."""
        dist = self.annotation_stats.get("class_distribution", {})
        
        # Include all project classes (even with 0 count)
        all_classes = {}
        for class_name in self.project_classes:
            all_classes[class_name] = dist.get(class_name, 0)
        
        # Also include any classes from annotations not in project classes
        for class_name, count in dist.items():
            if class_name not in all_classes:
                all_classes[class_name] = count
        
        # Sort by count descending, limit to 15
        sorted_items = sorted(all_classes.items(), key=lambda x: x[1], reverse=True)[:15]
        return [
            {
                "class_name": (name[:12] + "…") if len(name) > 12 else name,
                "count": int(count),
            }
            for name, count in sorted_items
        ]
    
    @rx.var
    def dataset_breakdown(self) -> list[dict]:
        """Get dataset breakdown list for iteration."""
        return self.annotation_stats.get("dataset_breakdown", [])
    
    async def load_annotation_stats(self):
        """Load annotation statistics for the current project."""
        if not self.current_project_id:
            return
        
        self.is_loading_stats = True
        yield
        
        try:
            from backend.supabase_client import get_project_annotation_stats
            stats = get_project_annotation_stats(self.current_project_id)
            self.annotation_stats = stats
            
            # Update dataset annotation counts from breakdown
            breakdown = stats.get("dataset_breakdown", [])
            breakdown_by_id = {b["dataset_id"]: b.get("annotation_count", 0) for b in breakdown}
            
            updated_datasets = []
            for ds in self.datasets:
                count = breakdown_by_id.get(ds.id, 0)
                updated_datasets.append(DatasetModel(
                    id=ds.id,
                    project_id=ds.project_id,
                    name=ds.name,
                    type=ds.type,
                    description=ds.description,
                    created_at=ds.created_at,
                    usage_tag=ds.usage_tag,
                    annotation_count=count,
                    thumbnail_url=ds.thumbnail_url,
                ))
            self.datasets = updated_datasets
            
        except Exception as e:
            print(f"[DEBUG] Error loading annotation stats: {e}")
            self.annotation_stats = {}
        finally:
            self.is_loading_stats = False

    def refresh_project_classes(self, classes: list[str]):
        """Update project classes and reload stats for chart refresh."""
        self.project_classes = classes
        # Reload annotation stats to compute fresh class counts from annotations
        return DatasetsState.load_annotation_stats
    
    # =========================================================================
    # EDIT PROJECT MODAL
    # =========================================================================
    
    def open_edit_project_modal(self):
        """Open the edit project modal with current values."""
        self.show_edit_project_modal = True
        self.edit_project_name = self.project_name
        self.edit_project_description = self.project_description
        self.edit_project_error = ""
    
    def close_edit_project_modal(self):
        """Close the edit project modal."""
        self.show_edit_project_modal = False
        self.edit_project_name = ""
        self.edit_project_description = ""
        self.edit_project_error = ""
    
    def set_edit_project_name(self, value: str):
        """Update the edit project name."""
        self.edit_project_name = value
    
    def set_edit_project_description(self, value: str):
        """Update the edit project description."""
        self.edit_project_description = value
    
    async def save_project_edits(self):
        """Save project name and description edits."""
        if not self.edit_project_name.strip():
            self.edit_project_error = "Project name is required."
            return
        
        self.is_saving_project = True
        self.edit_project_error = ""
        yield
        
        try:
            # Update in database
            result = db_update_project(
                self.current_project_id,
                name=self.edit_project_name.strip(),
                description=self.edit_project_description.strip(),
            )
            
            if result:
                # Update local state
                self.project_name = self.edit_project_name.strip()
                self.project_description = self.edit_project_description.strip()
                self.close_edit_project_modal()
                yield rx.toast.success("Project updated successfully")
            else:
                self.edit_project_error = "Failed to update project. Please try again."
        except Exception as e:
            print(f"[DEBUG] Error updating project: {e}")
            self.edit_project_error = f"Error: {str(e)}"
        finally:
            self.is_saving_project = False

    async def toggle_team_status(self):
        """Toggle company project status.
        
        - Any owner/admin can PROMOTE to team project
        - Only admins can DEMOTE from team project
        """
        if not self.current_project_id:
            return
        
        auth_state = await self.get_state(AuthState)
        
        if self.is_team_project:
            # Demotion — admin only
            if auth_state.is_admin:
                demote_from_team_project(self.current_project_id)
                self.is_team_project = False
        else:
            # Promotion — owner or admin
            promote_to_team_project(self.current_project_id)
            self.is_team_project = True


    # =========================================================================
    # Enter Key Handlers
    # =========================================================================

    async def handle_create_dataset_keydown(self, key: str):
        """Handle Enter key in create dataset modal."""
        if key == "Enter" and not self.is_creating:
            async for event in self.create_dataset():
                yield event

    async def handle_delete_dataset_keydown(self, key: str):
        """Handle Enter key in delete dataset confirmation."""
        if key == "Enter" and self.can_delete and not self.is_deleting:
            async for event in self.confirm_delete_dataset():
                yield event

    async def handle_edit_project_keydown(self, key: str):
        """Handle Enter key in edit project modal."""
        if key == "Enter" and not self.is_saving_project:
            async for event in self.save_project_edits():
                yield event
    
    # =========================================================================
    # ZIP UPLOAD (YOLO Dataset Import)
    # =========================================================================
    
    show_import_modal: bool = False
    is_uploading_zip: bool = False
    zip_upload_progress: str = ""
    
    def open_import_modal(self):
        """Open the import modal."""
        self.show_import_modal = True
    
    def close_import_modal(self):
        """Close the import modal."""
        self.show_import_modal = False
        self.zip_upload_progress = ""
    
    def _get_content_type(self, ext: str) -> str:
        """Get MIME type for file extension."""
        types = {
            "jpg": "image/jpeg",
            "jpeg": "image/jpeg",
            "png": "image/png",
            "webp": "image/webp",
        }
        return types.get(ext.lower(), "application/octet-stream")
    
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
            
            # 3. Create new dataset (classes are project-level, not dataset-level)
            self.zip_upload_progress = f"Creating dataset '{dataset_info.dataset_name}'..."
            yield
            
            new_dataset = db_create_dataset(
                project_id=self.current_project_id,
                name=dataset_info.dataset_name,
                type="image",
            )
            
            if not new_dataset:
                yield rx.toast.error("Failed to create dataset")
                return
            
            new_dataset_id = new_dataset["id"]
            print(f"[ZIP UPLOAD] Created dataset: {new_dataset_id}")
            
            # Merge discovered classes into project classes
            if dataset_info.classes:
                existing = set(self.project_classes)
                classes_to_add = [c for c in dataset_info.classes if c not in existing]
                if classes_to_add:
                    updated_classes = self.project_classes + classes_to_add
                    db_update_project(self.current_project_id, classes=updated_classes)
                    self.project_classes = updated_classes
                    print(f"[ZIP UPLOAD] Added {len(classes_to_add)} classes to project: {classes_to_add}")
            
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
                    annotations = []
                    
                    # If has label, upload annotations JSON
                    if has_label:
                        label_path = dataset_info.label_files[basename]
                        annotations = parse_yolo_label(label_path, width, height)
                        
                        if annotations:
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
                        "labeled": has_label and len(annotations) > 0,
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
    # EXPORT MODAL (YOLO Dataset Export)
    # =========================================================================
    
    show_export_modal: bool = False
    export_selected_datasets: list[str] = []
    export_mode: str = "download"  # "download" or "project"
    export_target_project_id: str = ""
    user_projects: list[dict] = []
    is_exporting: bool = False
    export_progress: str = ""
    
    async def open_export_modal(self):
        """Open the export modal and load user's projects."""
        self.show_export_modal = True
        self.export_selected_datasets = []
        self.export_mode = "download"
        self.export_target_project_id = ""
        self.export_progress = ""
        
        # Load user's other projects for export target selection
        try:
            auth_state = await self.get_state(AuthState)
            if auth_state.user_id:
                all_projects = get_user_projects(auth_state.user_id)
                # Filter out current project
                self.user_projects = [
                    {"id": p["id"], "name": p["name"]}
                    for p in all_projects
                    if p["id"] != self.current_project_id
                ]
        except Exception as e:
            print(f"[EXPORT] Error loading user projects: {e}")
            self.user_projects = []
    
    def close_export_modal(self):
        """Close the export modal and reset state."""
        self.show_export_modal = False
        self.export_selected_datasets = []
        self.export_mode = "download"
        self.export_target_project_id = ""
        self.export_progress = ""
        self.is_exporting = False
    
    def toggle_dataset_selection(self, dataset_id: str):
        """Toggle a dataset's selection state."""
        if dataset_id in self.export_selected_datasets:
            self.export_selected_datasets = [
                d for d in self.export_selected_datasets if d != dataset_id
            ]
        else:
            self.export_selected_datasets = self.export_selected_datasets + [dataset_id]
    
    def select_all_datasets(self):
        """Select all datasets."""
        self.export_selected_datasets = [d.id for d in self.datasets]
    
    def select_no_datasets(self):
        """Deselect all datasets."""
        self.export_selected_datasets = []
    
    def set_export_mode(self, mode: str):
        """Set the export mode (download or project)."""
        self.export_mode = mode
    
    def set_export_target_project(self, project_id: str):
        """Set the target project for export."""
        self.export_target_project_id = project_id
    
    def set_export_target_by_name(self, project_name: str):
        """Set the target project by looking up the name in user_projects."""
        for p in self.user_projects:
            if p.get("name") == project_name:
                self.export_target_project_id = p.get("id", "")
                return
        self.export_target_project_id = ""

    
    @rx.var
    def can_export(self) -> bool:
        """Check if export can proceed."""
        if not self.export_selected_datasets:
            return False
        if self.export_mode == "project" and not self.export_target_project_id:
            return False
        return True
    
    @rx.var
    def export_target_project_options(self) -> list[str]:
        """Get list of project names for select dropdown."""
        return [p["name"] for p in self.user_projects]
    
    async def download_yolo_zip(self):
        """Generate and download a YOLO-formatted ZIP file."""
        if not self.export_selected_datasets:
            yield rx.toast.error("Please select at least one dataset")
            return
        
        self.is_exporting = True
        self.export_progress = "Preparing export..."
        yield
        
        try:
            r2 = R2Client()
            
            # Cleanup old exports (older than 1 hour)
            import time
            exports_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), "assets", "exports")
            if os.path.exists(exports_dir):
                cutoff_time = time.time() - 3600  # 1 hour ago
                for filename in os.listdir(exports_dir):
                    filepath = os.path.join(exports_dir, filename)
                    try:
                        if os.path.isfile(filepath) and os.path.getmtime(filepath) < cutoff_time:
                            os.unlink(filepath)
                            print(f"[EXPORT] Cleaned up old export: {filename}")
                    except Exception:
                        pass
            
            # Create a temporary file for the ZIP
            with tempfile.NamedTemporaryFile(suffix=".zip", delete=False) as tmp_file:
                zip_path = tmp_file.name
            
            with zipfile.ZipFile(zip_path, 'w', zipfile.ZIP_DEFLATED) as zf:
                all_classes = set()
                file_index = 0

                
                for dataset_id in self.export_selected_datasets:
                    # Find dataset info
                    dataset = next((d for d in self.datasets if d.id == dataset_id), None)
                    if not dataset:
                        continue
                    
                    self.export_progress = f"Exporting {dataset.name}..."
                    yield
                    
                    if dataset.type == "image":
                        # Get all images for this dataset
                        images = get_dataset_images(dataset_id)
                        total_images = len(images)
                        print(f"[EXPORT ZIP] Starting export of {total_images} images from {dataset.name}")
                        
                        for idx, img in enumerate(images):
                            file_index += 1
                            filename = img.get("filename", "")
                            r2_path = img.get("r2_path", "")
                            image_id = img.get("id", "")
                            width = img.get("width", 1)
                            height = img.get("height", 1)
                            
                            # Update progress every 5 images
                            if idx % 5 == 0:
                                self.export_progress = f"Exporting {dataset.name}: {idx+1}/{total_images} images..."
                                yield
                            
                            # Generate unique name to avoid conflicts
                            ext = os.path.splitext(filename)[1] or ".jpg"
                            base_name = f"{file_index:06d}"
                            
                            try:
                                # Download image from R2
                                img_bytes = r2.download_file(r2_path)
                                zf.writestr(f"images/train/{base_name}{ext}", img_bytes)
                                
                                # Get annotations from R2 label file (uses image_id.txt format)
                                label_path = f"datasets/{dataset_id}/labels/{image_id}.txt"
                                label_lines = []
                                
                                try:
                                    label_bytes = r2.download_file(label_path)
                                    # Labels are stored in YOLO format already: class_name x_center y_center w h
                                    label_content = label_bytes.decode('utf-8')
                                    
                                    for line in label_content.strip().split('\n'):
                                        if line.strip():
                                            parts = line.strip().split()
                                            if len(parts) >= 5:
                                                class_name = parts[0]
                                                if class_name:
                                                    all_classes.add(class_name)
                                                label_lines.append(line.strip())
                                except Exception:
                                    # No label file or error reading
                                    pass
                                
                                # Write label file
                                if label_lines:
                                    zf.writestr(f"labels/train/{base_name}.txt", "\n".join(label_lines))
                                    
                            except Exception as e:
                                print(f"[EXPORT] Error exporting {filename}: {e}")
                                continue

                    
                    elif dataset.type == "video":
                        # Get all videos and their keyframes
                        videos = get_dataset_videos(dataset_id)
                        
                        for video in videos:
                            video_id = video.get("id", "")
                            keyframes = get_video_keyframes(video_id)
                            
                            for kf in keyframes:
                                file_index += 1
                                thumbnail_path = kf.get("thumbnail_path", "")
                                annotations = kf.get("annotations") or []
                                
                                if not thumbnail_path:
                                    continue
                                
                                base_name = f"{file_index:06d}"
                                
                                try:
                                    # Download keyframe thumbnail from R2
                                    img_bytes = r2.download_file(thumbnail_path)
                                    
                                    # Determine extension from path
                                    ext = os.path.splitext(thumbnail_path)[1] or ".jpg"
                                    zf.writestr(f"images/train/{base_name}{ext}", img_bytes)
                                    
                                    # Get dimensions from video or default
                                    width = video.get("width", 1920)
                                    height = video.get("height", 1080)
                                    
                                    # Process annotations
                                    label_lines = []
                                    for ann in annotations:
                                        class_name = ann.get("class_name", "")
                                        if class_name:
                                            all_classes.add(class_name)
                                        
                                        x = ann.get("x", 0)
                                        y = ann.get("y", 0)
                                        w = ann.get("width", 0)
                                        h = ann.get("height", 0)
                                        
                                        x_center = (x + w / 2) / width
                                        y_center = (y + h / 2) / height
                                        norm_w = w / width
                                        norm_h = h / height
                                        
                                        label_lines.append(f"{class_name} {x_center:.6f} {y_center:.6f} {norm_w:.6f} {norm_h:.6f}")
                                    
                                    if label_lines:
                                        zf.writestr(f"labels/train/{base_name}.txt", "\n".join(label_lines))
                                        
                                except Exception as e:
                                    print(f"[EXPORT] Error exporting keyframe {kf.get('id')}: {e}")
                                    continue
                
                # Generate data.yaml from project classes
                # (labels already use numeric class_id indices)
                yaml_content = f"path: .\ntrain: images/train\nval: images/train\n\nnames:\n"
                for idx, name in enumerate(self.project_classes):
                    yaml_content += f"  {idx}: {name}\n"
                
                zf.writestr("data.yaml", yaml_content)
            
            # Move ZIP to public assets for download
            self.export_progress = "Preparing download..."
            yield
            
            # Create exports directory in assets
            import shutil
            exports_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), "assets", "exports")
            os.makedirs(exports_dir, exist_ok=True)
            
            # Generate unique filename
            export_filename = f"{self.project_name.replace(' ', '_')}_{uuid.uuid4().hex[:8]}_export.zip"
            final_path = os.path.join(exports_dir, export_filename)
            
            # Move temp ZIP to assets
            shutil.move(zip_path, final_path)
            
            zip_size_mb = os.path.getsize(final_path) / (1024 * 1024)
            print(f"[EXPORT ZIP] ZIP saved: {final_path} ({zip_size_mb:.2f} MB)")
            
            # Provide download URL
            download_url = f"/exports/{export_filename}"
            
            self.close_export_modal()
            yield rx.toast.success(f"Exported {file_index} items to YOLO format ({zip_size_mb:.1f} MB)")
            yield rx.redirect(download_url)
            
        except Exception as e:
            print(f"[EXPORT] Error: {e}")
            import traceback
            traceback.print_exc()
            yield rx.toast.error(f"Export failed: {str(e)}")
        finally:
            self.is_exporting = False
            self.export_progress = ""



    async def export_to_project(self):
        """Copy selected datasets to another project with full data copy."""
        if not self.export_selected_datasets:
            yield rx.toast.error("Please select at least one dataset")
            return
        
        if not self.export_target_project_id:
            yield rx.toast.error("Please select a target project")
            return
        
        self.is_exporting = True
        self.export_progress = "Starting copy..."
        yield
        
        try:
            from backend.supabase_client import (
                create_dataset as db_create_dataset,
                bulk_create_images,
                bulk_create_videos,
                bulk_create_keyframes,
                get_project,
                update_project as db_update_project,
            )
            
            r2 = R2Client()
            copied_datasets = 0
            total_datasets = len(self.export_selected_datasets)
            
            # Merge classes from source project to target project
            self.export_progress = "Merging classes..."
            yield
            
            target_project = get_project(self.export_target_project_id)
            if target_project:
                target_classes = set(target_project.get("classes", []) or [])
                source_classes = set(self.project_classes)
                new_classes = source_classes - target_classes
                
                if new_classes:
                    merged_classes = list(target_classes) + list(new_classes)
                    db_update_project(self.export_target_project_id, classes=merged_classes)
                    print(f"[EXPORT] Added {len(new_classes)} new classes to target project: {new_classes}")
            
            for idx, dataset_id in enumerate(self.export_selected_datasets):
                dataset = next((d for d in self.datasets if d.id == dataset_id), None)
                if not dataset:
                    continue
                
                self.export_progress = f"Copying dataset {idx+1}/{total_datasets}: {dataset.name}..."
                yield
                
                # 1. Create new dataset in target project
                new_dataset = db_create_dataset(
                    project_id=self.export_target_project_id,
                    name=f"{dataset.name}",
                    type=dataset.type,
                    description=f"Copied from {self.project_name}",
                    usage_tag=dataset.usage_tag,

                )
                
                if not new_dataset:
                    print(f"[EXPORT] Failed to create dataset {dataset.name}")
                    continue
                
                new_dataset_id = new_dataset["id"]
                
                # 2. Copy all R2 files from old dataset to new dataset
                source_prefix = f"datasets/{dataset_id}/"
                dest_prefix = f"datasets/{new_dataset_id}/"
                
                self.export_progress = f"Copying files for {dataset.name}..."
                yield
                
                copy_result = r2.copy_files_with_prefix(source_prefix, dest_prefix)
                path_mapping = copy_result.get("path_mapping", {})
                
                print(f"[EXPORT] Copied {copy_result['copied_count']} files for dataset {dataset.name}")
                
                # 3. Copy database records with updated paths
                if dataset.type == "image":
                    self.export_progress = f"Copying image records for {dataset.name}..."
                    yield
                    
                    # Get source images
                    images = get_dataset_images(dataset_id)
                    
                    if images:
                        # Prepare records with updated paths
                        new_image_records = []
                        for img in images:
                            old_r2_path = img.get("r2_path", "")
                            new_r2_path = path_mapping.get(old_r2_path, old_r2_path.replace(f"datasets/{dataset_id}/", f"datasets/{new_dataset_id}/"))
                            
                            new_image_records.append({
                                "filename": img.get("filename", ""),
                                "r2_path": new_r2_path,
                                "width": img.get("width"),
                                "height": img.get("height"),
                                "labeled": img.get("labeled", False),
                                "annotations": img.get("annotations"),
                                "annotation_count": img.get("annotation_count", 0),
                            })
                        
                        # Bulk insert and get created records with new IDs
                        created_images = bulk_create_images(new_dataset_id, new_image_records)
                        print(f"[EXPORT] Copied {len(created_images)} image records")
                        
                        # Rename label files to match new image IDs
                        # Image labels are stored as datasets/{dataset_id}/labels/{image_id}.txt
                        self.export_progress = f"Remapping label files for {dataset.name}..."
                        yield
                        
                        renamed_count = 0
                        for i, created_img in enumerate(created_images):
                            if i < len(images):
                                old_img = images[i]
                                old_img_id = old_img.get("id", "")
                                new_img_id = created_img.get("id", "")
                                
                                if old_img_id and new_img_id:
                                    # Copy label file with new name
                                    old_label_path = f"datasets/{new_dataset_id}/labels/{old_img_id}.txt"
                                    new_label_path = f"datasets/{new_dataset_id}/labels/{new_img_id}.txt"
                                    
                                    try:
                                        # Copy from old name to new name using S3 copy
                                        r2.s3.copy_object(
                                            Bucket=r2.bucket,
                                            CopySource={'Bucket': r2.bucket, 'Key': old_label_path},
                                            Key=new_label_path
                                        )
                                        # Delete old label file
                                        r2.delete_file(old_label_path)
                                        renamed_count += 1
                                    except Exception as e:
                                        # Label might not exist (unlabeled image)
                                        pass
                        
                        print(f"[EXPORT] Renamed {renamed_count} label files")

                
                elif dataset.type == "video":
                    self.export_progress = f"Copying video records for {dataset.name}..."
                    yield
                    
                    # Get source videos
                    videos = get_dataset_videos(dataset_id)
                    
                    if videos:
                        # Create mapping from old video ID to new video ID
                        old_to_new_video_id = {}
                        
                        # Prepare video records with updated paths
                        new_video_records = []
                        for vid in videos:
                            old_r2_path = vid.get("r2_path", "")
                            old_thumb_path = vid.get("thumbnail_path", "")
                            
                            new_r2_path = path_mapping.get(old_r2_path, old_r2_path.replace(f"datasets/{dataset_id}/", f"datasets/{new_dataset_id}/"))
                            new_thumb_path = path_mapping.get(old_thumb_path, old_thumb_path.replace(f"datasets/{dataset_id}/", f"datasets/{new_dataset_id}/")) if old_thumb_path else None
                            
                            new_video_records.append({
                                "filename": vid.get("filename", ""),
                                "r2_path": new_r2_path,
                                "duration_seconds": vid.get("duration_seconds"),
                                "frame_count": vid.get("frame_count"),
                                "fps": vid.get("fps"),
                                "width": vid.get("width"),
                                "height": vid.get("height"),
                                "thumbnail_path": new_thumb_path,
                                "_old_id": vid.get("id"),  # Temp field for mapping
                            })
                        
                        # Bulk insert videos
                        created_videos = bulk_create_videos(new_dataset_id, new_video_records)
                        
                        # Build old->new video ID mapping
                        for i, created_vid in enumerate(created_videos):
                            if i < len(new_video_records):
                                old_id = new_video_records[i].get("_old_id")
                                if old_id:
                                    old_to_new_video_id[old_id] = created_vid["id"]
                        
                        print(f"[EXPORT] Copied {len(created_videos)} video records")
                        
                        # Rename label files from old video IDs to new video IDs
                        # Label files are named: {video_id}_f{frame_number}.txt
                        self.export_progress = f"Remapping label files for {dataset.name}..."
                        yield
                        
                        renamed_label_count = 0
                        for old_vid_id, new_vid_id in old_to_new_video_id.items():
                            # List all label files with old video ID prefix
                            old_prefix = f"datasets/{new_dataset_id}/labels/{old_vid_id}_"
                            try:
                                response = r2.s3.list_objects_v2(
                                    Bucket=r2.bucket,
                                    Prefix=old_prefix,
                                    MaxKeys=500
                                )
                                
                                for obj in response.get('Contents', []):
                                    old_key = obj['Key']
                                    # Extract the frame part (e.g., _f0.txt, _f10.txt)
                                    frame_part = old_key.replace(old_prefix, "")  # Gets "f0.txt" etc
                                    new_key = f"datasets/{new_dataset_id}/labels/{new_vid_id}_{frame_part}"
                                    
                                    try:
                                        r2.s3.copy_object(
                                            Bucket=r2.bucket,
                                            CopySource={'Bucket': r2.bucket, 'Key': old_key},
                                            Key=new_key
                                        )
                                        r2.delete_file(old_key)
                                        renamed_label_count += 1
                                    except Exception as e:
                                        print(f"[EXPORT] Failed to rename label {old_key}: {e}")
                            except Exception as e:
                                print(f"[EXPORT] Error listing labels for video {old_vid_id}: {e}")
                        
                        print(f"[EXPORT] Renamed {renamed_label_count} video label files")
                        
                        # Now copy keyframes for each video
                        self.export_progress = f"Copying keyframes for {dataset.name}..."
                        yield
                        
                        all_keyframe_records = []
                        for old_vid_id, new_vid_id in old_to_new_video_id.items():
                            keyframes = get_video_keyframes(old_vid_id)
                            
                            for kf in keyframes:
                                old_thumb = kf.get("thumbnail_path", "")
                                new_thumb = path_mapping.get(old_thumb, old_thumb.replace(f"datasets/{dataset_id}/", f"datasets/{new_dataset_id}/")) if old_thumb else None
                                
                                all_keyframe_records.append({
                                    "video_id": new_vid_id,
                                    "frame_number": kf.get("frame_number"),
                                    "timestamp": kf.get("timestamp"),
                                    "thumbnail_path": new_thumb,
                                    "annotations": kf.get("annotations"),
                                    "annotation_count": kf.get("annotation_count", 0),
                                })
                        
                        # Bulk insert keyframes
                        if all_keyframe_records:
                            bulk_create_keyframes(all_keyframe_records)
                            print(f"[EXPORT] Copied {len(all_keyframe_records)} keyframe records")

                
                copied_datasets += 1
            
            self.close_export_modal()
            yield rx.toast.success(f"Copied {copied_datasets} dataset(s) with all data to target project")
            
        except Exception as e:
            print(f"[EXPORT] Error copying: {e}")
            import traceback
            traceback.print_exc()
            yield rx.toast.error(f"Copy failed: {str(e)}")
        finally:
            self.is_exporting = False
            self.export_progress = ""
