"""
Hub State — State management for the dashboard hub page.

Manages:
- Project list and CRUD
- Active project selection (persisted in localStorage)
- Context-aware datasets and training runs for active project
"""

import reflex as rx
from typing import Optional
from pydantic import BaseModel as PydanticBaseModel

from backend.supabase_client import (
    get_project,
    get_user_projects,
    get_user_projects_with_stats,
    get_project_datasets,
    get_project_training_runs,
    get_user_stats,
    create_project as db_create_project,
    delete_project as db_delete_project,
    get_project_dataset_count,
    create_dataset as db_create_dataset,
    delete_dataset as db_delete_dataset,
    update_project,
    update_dataset,
    touch_project_accessed,
)
from app_state import AuthState
from modules.projects.models import ProjectModel, DatasetModel


class HubProjectModel(PydanticBaseModel):
    """Extended project model for hub display."""
    id: str = ""
    name: str = ""
    description: str = ""
    dataset_count: int = 0
    created_at: str = ""
    is_active: bool = False
    thumbnail_url: str = ""  # Presigned URL for thumbnail image
    classes: list[str] = []  # Project class names
    is_team: bool = False  # Team project flag


class HubDatasetModel(PydanticBaseModel):
    """Dataset model for hub labeling panel."""
    id: str = ""
    name: str = ""
    type: str = "image"  # "image" or "video"
    image_count: int = 0
    labeled_count: int = 0
    thumbnail_url: str = ""  # Presigned URL for thumbnail image


class HubTrainingRunModel(PydanticBaseModel):
    """Training run model for hub training panel."""
    id: str = ""
    status: str = "pending"
    alias: str = ""  # Training run alias for display
    epochs: int = 0
    model_size: str = "n"
    model_type: str = "detection"  # "detection" or "classification"
    backbone: str = ""  # "convnext", "yolo", or "" (for detection)
    # Pre-formatted metrics strings (avoid Reflex Var formatting issues)
    precision_str: str = ""  # e.g., "P:89%"
    recall_str: str = ""     # e.g., "R:97%"
    map_str: str = ""        # e.g., "mAP:96.6%"
    accuracy_str: str = ""   # e.g., "Acc:100%"
    created_at: str = ""
    # Usage flags
    used_in_playground: bool = False  # Has inference results
    used_in_autolabel: bool = False   # Has autolabel jobs


class HubState(rx.State):
    """State for the dashboard hub page."""
    
    # Stats (quick overview)
    project_count: int = 0
    dataset_count: int = 0
    image_count: int = 0
    labeled_count: int = 0
    
    # Projects list
    projects: list[HubProjectModel] = []
    
    # Active project (persisted to localStorage)
    active_project_id: str = ""
    
    # Context data for active project
    active_project_datasets: list[HubDatasetModel] = []
    active_project_runs: list[HubTrainingRunModel] = []
    
    # Loading states
    is_loading: bool = False  # Default to False to prevent skeleton flash on re-navigation
    is_loading_context: bool = False
    _has_loaded_once: bool = False  # Track first load for skeleton display
    
    # New project modal
    show_new_project_modal: bool = False
    new_project_name: str = ""
    new_project_description: str = ""
    is_creating_project: bool = False
    
    # Delete project modal
    show_delete_modal: bool = False
    delete_project_id: str = ""
    delete_project_name: str = ""
    delete_confirmation: str = ""
    delete_confirmation: str = ""
    is_deleting: bool = False

    # New Dataset Modal state
    show_dataset_modal: bool = False
    new_dataset_name: str = ""
    new_dataset_type: str = "image"
    new_dataset_classes: str = ""
    is_creating_dataset: bool = False
    create_dataset_error: str = ""

    # Delete Dataset Modal state
    show_delete_dataset_modal: bool = False
    delete_dataset_id: str = ""
    delete_dataset_name: str = ""
    delete_dataset_confirmation: str = ""
    is_deleting_dataset: bool = False

    # Inline editing state for project names
    editing_project_id: str = ""
    editing_project_name: str = ""
    
    # Inline editing state for dataset names
    editing_dataset_id: str = ""
    editing_dataset_name: str = ""
    
    # Thumbnail URL cache (R2 path -> presigned URL)
    # Avoids regenerating presigned URLs on every page load
    _thumbnail_url_cache: dict[str, str] = {}
    
    def invalidate_thumbnail_cache(self, r2_path: str):
        """Remove a specific thumbnail from cache (e.g., after override)."""
        if r2_path in self._thumbnail_url_cache:
            del self._thumbnail_url_cache[r2_path]
            print(f"[ThumbnailCache] Invalidated: {r2_path}")
    
    def clear_all_thumbnail_cache(self):
        """Clear all cached thumbnail URLs (forces regeneration)."""
        self._thumbnail_url_cache.clear()

    @rx.var
    def can_delete_dataset(self) -> bool:
        """Check if dataset delete confirmation is valid."""
        return self.delete_dataset_confirmation.lower() == "delete"

    async def load_hub_data(self):
        """Load all dashboard hub data with progressive class count loading."""
        # Only show skeleton on first load to prevent flickering on re-navigation
        if not self._has_loaded_once:
            self.is_loading = True
            yield
        
        # Clear thumbnail cache to ensure fresh URLs
        self.clear_all_thumbnail_cache()
        
        # Get auth state
        auth_state = await self.get_state(AuthState)
        user_id = auth_state.user_id
        
        if not user_id:
            self.is_loading = False
            return
        
        try:
            # Phase 1: Load stats and projects quickly (2-3 fast queries)
            stats = get_user_stats(user_id)
            self.project_count = stats.get("project_count", 0)
            self.dataset_count = stats.get("dataset_count", 0)
            self.image_count = stats.get("image_count", 0)
            self.labeled_count = stats.get("labeled_count", 0)
            
            # Load projects with basic info only (fast - no annotation fetching)
            raw_projects = get_user_projects(user_id)
            
            # Get dataset counts per project in one query
            from backend.supabase_client import get_supabase
            supabase = get_supabase()
            project_ids = [p["id"] for p in raw_projects]
            
            dataset_counts_by_project = {}
            if project_ids:
                datasets_result = (
                    supabase.table("datasets")
                    .select("id, project_id")
                    .in_("project_id", project_ids)
                    .execute()
                )
                for ds in (datasets_result.data or []):
                    pid = ds.get("project_id")
                    dataset_counts_by_project[pid] = dataset_counts_by_project.get(pid, 0) + 1
            
            # Build projects list with thumbnails
            from backend.r2_storage import R2Client
            r2 = R2Client()
            
            projects = []
            for p in raw_projects:
                project_id = p.get("id", "")
                thumb_r2_path = p.get("thumbnail_r2_path", "")
                
                # Get thumbnail URL (cached or generate new)
                thumb_url = ""
                if thumb_r2_path:
                    cached = self._thumbnail_url_cache.get(thumb_r2_path, "")
                    if cached:
                        thumb_url = cached
                    else:
                        thumb_url = r2.generate_presigned_url(thumb_r2_path, expires_in=3600)
                        if thumb_url:
                            self._thumbnail_url_cache[thumb_r2_path] = thumb_url
                
                projects.append(HubProjectModel(
                    id=project_id,
                    name=p.get("name", ""),
                    description=p.get("description", ""),
                    dataset_count=dataset_counts_by_project.get(project_id, 0),
                    created_at=p.get("created_at", "")[:10] if p.get("created_at") else "",
                    is_active=False,
                    thumbnail_url=thumb_url,
                    classes=p.get("classes") or [],
                    is_team=p.get("is_company", False) or False,
                ))
            
            self.projects = projects
            
            # Always sync active project to the most recently accessed (first in sorted list)
            if projects:
                self.active_project_id = projects[0].id
            
            # Mark active project
            self._update_active_markers()
            
        except Exception as e:
            print(f"[ERROR] Failed to load hub data: {e}")
        finally:
            self.is_loading = False
            self._has_loaded_once = True
        
        # Load context for active project
        if self.active_project_id:
            async for event in self.load_active_project_context():
                yield event
    
    
    def _update_active_markers(self):
        """Update is_active flag on all projects."""
        updated = []
        for p in self.projects:
            updated.append(HubProjectModel(
                id=p.id,
                name=p.name,
                description=p.description,
                dataset_count=p.dataset_count,
                created_at=p.created_at,
                is_active=(p.id == self.active_project_id),
                thumbnail_url=p.thumbnail_url,
                classes=p.classes,
                is_team=p.is_team,
            ))
        self.projects = updated
    
    async def load_active_project_context(self):
        """Load datasets and training runs for the active project."""
        if not self.active_project_id:
            self.active_project_datasets = []
            self.active_project_runs = []
            return
        
        self.is_loading_context = True
        yield
        
        try:
            project_id = self.active_project_id
            
            # Load datasets with thumbnails
            raw_datasets = get_project_datasets(project_id)
            from backend.r2_storage import R2Client
            r2 = R2Client()
            
            datasets = []
            for d in raw_datasets:
                from backend.supabase_client import get_dataset_image_count, get_dataset_video_count
                ds_id = d.get("id", "")
                ds_type = d.get("type", "image")
                thumb_r2_path = d.get("thumbnail_r2_path", "")
                
                if ds_type == "video":
                    total = get_dataset_video_count(ds_id)
                    labeled = 0  # Videos use keyframes, simplified for hub
                else:
                    total = get_dataset_image_count(ds_id)
                    labeled = get_dataset_image_count(ds_id, labeled_only=True)
                
                # Get thumbnail URL (cached or generate new)
                thumb_url = ""
                if thumb_r2_path:
                    if thumb_r2_path in self._thumbnail_url_cache:
                        thumb_url = self._thumbnail_url_cache[thumb_r2_path]
                    else:
                        thumb_url = r2.generate_presigned_url(thumb_r2_path, expires_in=3600)
                        if thumb_url:
                            self._thumbnail_url_cache[thumb_r2_path] = thumb_url
                
                datasets.append(HubDatasetModel(
                    id=ds_id,
                    name=d.get("name", ""),
                    type=ds_type,
                    image_count=total,
                    labeled_count=labeled,
                    thumbnail_url=thumb_url,
                ))
            
            self.active_project_datasets = datasets
            
            # Load all training runs (filter out failed ones for dashboard)
            raw_runs = get_project_training_runs(project_id)
            
            # Collect run IDs for batch usage detection
            run_ids = [r.get("id") for r in raw_runs if r.get("status") != "failed"]
            
            # Batch query: Get all models linked to these training runs
            # Then check if any have been used in inference_results or autolabel_jobs
            playground_runs = set()  # Run IDs with playground usage
            autolabel_runs = set()   # Run IDs with autolabel usage
            
            if run_ids:
                from backend.supabase_client import get_supabase
                supabase = get_supabase()
                
                # Get models for all training runs in one query
                models_result = (
                    supabase.table("models")
                    .select("id, training_run_id")
                    .in_("training_run_id", run_ids)
                    .execute()
                )
                models = models_result.data or []
                model_ids = [m["id"] for m in models]
                model_to_run = {m["id"]: m["training_run_id"] for m in models}
                
                if model_ids:
                    # Check inference_results usage (playground)
                    inference_result = (
                        supabase.table("inference_results")
                        .select("model_id")
                        .in_("model_id", model_ids)
                        .execute()
                    )
                    for ir in (inference_result.data or []):
                        run_id = model_to_run.get(ir.get("model_id"))
                        if run_id:
                            playground_runs.add(run_id)
                    
                    # Check autolabel_jobs usage
                    autolabel_result = (
                        supabase.table("autolabel_jobs")
                        .select("model_id")
                        .in_("model_id", model_ids)
                        .execute()
                    )
                    for aj in (autolabel_result.data or []):
                        run_id = model_to_run.get(aj.get("model_id"))
                        if run_id:
                            autolabel_runs.add(run_id)
            
            # Build run models with usage flags
            runs = []
            for r in raw_runs:
                # Skip failed runs
                if r.get("status") == "failed":
                    continue
                    
                config = r.get("config") or {}
                metrics = r.get("metrics") or {}
                run_id = r.get("id", "")
                
                # Pre-format detection metrics
                precision = metrics.get("precision")
                recall = metrics.get("recall")
                map_val = metrics.get("mAP50")
                precision_str = f"P:{int(precision * 100)}%" if precision else ""
                recall_str = f"R:{int(recall * 100)}%" if recall else ""
                map_str = f"mAP:{map_val * 100:.1f}%" if map_val else ""
                
                # Pre-format classification metric
                accuracy = metrics.get("top1_accuracy")
                accuracy_str = f"Acc:{int(accuracy * 100)}%" if accuracy else ""
                
                # Get backbone (only relevant for classification)
                backbone = config.get("classifier_backbone") or ""
                
                runs.append(HubTrainingRunModel(
                    id=run_id,
                    status=r.get("status", "pending"),
                    alias=r.get("alias") or "",  # Handle None from database
                    epochs=config.get("epochs", 0),
                    model_size=config.get("model_size", "n"),
                    model_type=r.get("model_type", "detection"),
                    backbone=backbone,
                    precision_str=precision_str,
                    recall_str=recall_str,
                    map_str=map_str,
                    accuracy_str=accuracy_str,
                    created_at=r.get("created_at", "")[:10] if r.get("created_at") else "",
                    used_in_playground=run_id in playground_runs,
                    used_in_autolabel=run_id in autolabel_runs,
                ))
            
            self.active_project_runs = runs
            
        except Exception as e:
            print(f"[ERROR] Failed to load active project context: {e}")
        finally:
            self.is_loading_context = False
    
    async def set_active_project(self, project_id: str):
        """Set the active project, touch timestamp, and reorder list."""
        import asyncio
        
        # Set active immediately for responsive UI
        self.active_project_id = project_id
        self._update_active_markers()
        yield  # Update UI to show active state
        
        # Touch the access timestamp (updates DB)
        touch_project_accessed(project_id)
        
        # Load datasets for the newly active project
        async for event in self.load_active_project_context():
            yield event
        
        # Brief delay for smooth animation effect
        await asyncio.sleep(0.15)
        
        # Reorder projects: move active project to top
        active_project = None
        other_projects = []
        for p in self.projects:
            if p.id == project_id:
                active_project = p
            else:
                other_projects.append(p)
        
        if active_project:
            self.projects = [active_project] + other_projects
            self._update_active_markers()

    async def select_and_navigate_to_project(self, project_id: str):
        """Set project active with visual feedback, then navigate to details."""
        import asyncio
        
        # Set active and update UI markers
        self.active_project_id = project_id
        self._update_active_markers()
        yield  # Allow UI to reflect the active state
        
        # Brief delay for user to see the selection feedback
        await asyncio.sleep(0.15)
        
        # Navigate to project details
        yield rx.redirect(f"/projects/{project_id}")
    
    # =========================================================================
    # Computed properties
    # =========================================================================
    
    @rx.var
    def has_projects(self) -> bool:
        """Check if user has any projects."""
        return len(self.projects) > 0
    
    @rx.var
    def has_active_project(self) -> bool:
        """Check if an active project is selected."""
        return self.active_project_id != ""
    
    @rx.var
    def active_project_name(self) -> str:
        """Get name of active project."""
        for p in self.projects:
            if p.id == self.active_project_id:
                return p.name
        return ""
    
    @rx.var
    def has_datasets(self) -> bool:
        """Check if active project has datasets."""
        return len(self.active_project_datasets) > 0
    
    @rx.var
    def has_runs(self) -> bool:
        """Check if active project has training runs."""
        return len(self.active_project_runs) > 0
    
    @rx.var
    def can_delete(self) -> bool:
        """Check if delete confirmation is valid."""
        return self.delete_confirmation.lower() == "delete"
    
    # =========================================================================
    # Project CRUD
    # =========================================================================
    
    def open_new_project_modal(self):
        """Open the new project modal."""
        self.show_new_project_modal = True
        self.new_project_name = ""
        self.new_project_description = ""
    
    def close_new_project_modal(self):
        """Close the new project modal."""
        self.show_new_project_modal = False
    
    async def create_project(self):
        """Create a new project."""
        if not self.new_project_name.strip():
            return
        
        self.is_creating_project = True
        yield
        
        try:
            auth_state = await self.get_state(AuthState)
            user_id = auth_state.user_id
            
            result = db_create_project(
                user_id=user_id,
                name=self.new_project_name.strip(),
                description=self.new_project_description.strip(),
            )
            
            if result:
                self.show_new_project_modal = False
                self.new_project_name = ""
                self.new_project_description = ""
                # Reload hub
                yield HubState.load_hub_data
        except Exception as e:
            print(f"[ERROR] Failed to create project: {e}")
        finally:
            self.is_creating_project = False
    
    def open_delete_modal(self, project_id: str, project_name: str):
        """Open delete confirmation modal."""
        self.show_delete_modal = True
        self.delete_project_id = project_id
        self.delete_project_name = project_name
        self.delete_confirmation = ""
    
    def close_delete_modal(self):
        """Close delete modal."""
        self.show_delete_modal = False
        self.delete_project_id = ""
        self.delete_project_name = ""
        self.delete_confirmation = ""
    
    async def confirm_delete_project(self):
        """Delete the project after confirmation."""
        if not self.can_delete:
            return
        
        self.is_deleting = True
        yield
        
        try:
            # Guard: team projects can only be deleted by admins
            auth_state = await self.get_state(AuthState)
            project = get_project(self.delete_project_id)
            if project and project.get("is_company") and not auth_state.is_admin:
                self.show_delete_modal = False
                yield rx.toast.error("Team projects can only be deleted by admins.")
                return
            
            # If deleting active project, clear selection
            if self.delete_project_id == self.active_project_id:
                self.active_project_id = ""
            
            db_delete_project(self.delete_project_id)
            self.show_delete_modal = False
            yield HubState.load_hub_data
        except Exception as e:
            print(f"[ERROR] Failed to delete project: {e}")
        finally:
            self.is_deleting = False

    # =========================================================================
    # Dataset Creation
    # =========================================================================

    def open_dataset_modal(self):
        """Open the new dataset modal."""
        if not self.active_project_id:
            return
        self.show_dataset_modal = True
        self.new_dataset_name = ""
        self.new_dataset_type = "image"
        self.new_dataset_classes = ""
        self.create_dataset_error = ""

    def close_dataset_modal(self):
        """Close the new dataset modal."""
        self.show_dataset_modal = False
        self.new_dataset_name = ""
        self.new_dataset_type = "image"
        self.new_dataset_classes = ""
        self.create_dataset_error = ""

    def set_dataset_name(self, value: str):
        self.new_dataset_name = value

    def set_dataset_type(self, value: str):
        self.new_dataset_type = value

    def set_dataset_classes(self, value: str):
        self.new_dataset_classes = value

    async def create_dataset(self):
        """Create a new dataset and redirect to it."""
        if not self.new_dataset_name.strip():
            self.create_dataset_error = "Dataset name is required."
            return

        self.is_creating_dataset = True
        self.create_dataset_error = ""
        yield

        try:
            # Parse classes from comma-separated string
            classes = []
            if self.new_dataset_classes.strip():
                classes = [c.strip() for c in self.new_dataset_classes.split(",") if c.strip()]

            # Create in database
            dataset = db_create_dataset(
                project_id=self.active_project_id,
                name=self.new_dataset_name.strip(),
                type=self.new_dataset_type,
                classes=classes,
            )

            if dataset:
                self.close_dataset_modal()
                # Redirect to the new dataset detail page
                yield rx.redirect(f"/projects/{self.active_project_id}/datasets/{dataset['id']}")
            else:
                self.create_dataset_error = "Failed to create dataset. Please try again."

        except Exception as e:
            self.create_dataset_error = f"Error: {str(e)}"
        finally:
            self.is_creating_dataset = False

    def open_delete_dataset_modal(self, dataset_id: str, dataset_name: str):
        """Open delete dataset confirmation modal."""
        self.show_delete_dataset_modal = True
        self.delete_dataset_id = dataset_id
        self.delete_dataset_name = dataset_name
        self.delete_dataset_confirmation = ""
        
    def close_delete_dataset_modal(self):
        """Close delete dataset modal."""
        self.show_delete_dataset_modal = False
        self.delete_dataset_id = ""
        self.delete_dataset_name = ""
        self.delete_dataset_confirmation = ""
        
    def set_delete_dataset_confirmation(self, value: str):
        self.delete_dataset_confirmation = value
        
    async def confirm_delete_dataset(self):
        """Delete the dataset after confirmation."""
        if not self.can_delete_dataset:
            return
            
        self.is_deleting_dataset = True
        yield
        
        try:
            # 1. Cleanup R2 files for this dataset
            from backend.r2_storage import R2Client
            r2 = R2Client()
            deleted_count = r2.delete_files_with_prefix(f"datasets/{self.delete_dataset_id}/")
            print(f"[DEBUG] Deleted {deleted_count} files from R2 for dataset {self.delete_dataset_id}")
            
            # 2. Delete from database
            db_delete_dataset(self.delete_dataset_id)
            self.show_delete_dataset_modal = False
            # Reload context
            yield HubState.load_active_project_context
        except Exception as e:
            print(f"[ERROR] Failed to delete dataset: {e}")
            yield rx.toast.error("Failed to delete dataset")
        finally:
            self.is_deleting_dataset = False

    # =========================================================================
    # Enter Key Handlers
    # =========================================================================

    async def handle_new_project_keydown(self, key: str):
        """Handle Enter key in new project modal."""
        if key == "Enter" and not self.is_creating_project:
            async for event in self.create_project():
                yield event

    async def handle_delete_project_keydown(self, key: str):
        """Handle Enter key in delete project confirmation."""
        if key == "Enter" and self.can_delete and not self.is_deleting:
            async for event in self.confirm_delete_project():
                yield event

    async def handle_new_dataset_keydown(self, key: str):
        """Handle Enter key in new dataset modal."""
        if key == "Enter" and not self.is_creating_dataset:
            async for event in self.create_dataset():
                yield event

    async def handle_delete_dataset_keydown(self, key: str):
        """Handle Enter key in delete dataset confirmation."""
        if key == "Enter" and self.can_delete_dataset and not self.is_deleting_dataset:
            async for event in self.confirm_delete_dataset():
                yield event

    # =========================================================================
    # Inline Name Editing - Projects
    # =========================================================================

    def start_edit_project_name(self, project_id: str, current_name: str):
        """Start editing a project name."""
        self.editing_project_id = project_id
        self.editing_project_name = current_name

    def set_editing_project_name(self, name: str):
        """Update the editing project name."""
        self.editing_project_name = name

    async def save_project_name(self):
        """Save the edited project name."""
        if not self.editing_project_id or not self.editing_project_name.strip():
            self.cancel_edit_project_name()
            return
        
        try:
            update_project(self.editing_project_id, name=self.editing_project_name.strip())
            # Reload to reflect changes
            yield HubState.load_hub_data
        except Exception as e:
            print(f"[ERROR] Failed to update project name: {e}")
            yield rx.toast.error("Failed to update project name")
        finally:
            self.editing_project_id = ""
            self.editing_project_name = ""

    def cancel_edit_project_name(self):
        """Cancel editing project name."""
        self.editing_project_id = ""
        self.editing_project_name = ""

    async def handle_project_name_keydown(self, key: str):
        """Handle keyboard shortcuts for project name editing."""
        if key == "Enter":
            async for event in self.save_project_name():
                yield event
        elif key == "Escape":
            self.cancel_edit_project_name()

    # =========================================================================
    # Inline Name Editing - Datasets
    # =========================================================================

    def start_edit_dataset_name(self, dataset_id: str, current_name: str):
        """Start editing a dataset name."""
        self.editing_dataset_id = dataset_id
        self.editing_dataset_name = current_name

    def set_editing_dataset_name(self, name: str):
        """Update the editing dataset name."""
        self.editing_dataset_name = name

    async def save_dataset_name(self):
        """Save the edited dataset name."""
        if not self.editing_dataset_id or not self.editing_dataset_name.strip():
            self.cancel_edit_dataset_name()
            return
        
        try:
            update_dataset(self.editing_dataset_id, name=self.editing_dataset_name.strip())
            # Reload to reflect changes
            yield HubState.load_active_project_context
        except Exception as e:
            print(f"[ERROR] Failed to update dataset name: {e}")
            yield rx.toast.error("Failed to update dataset name")
        finally:
            self.editing_dataset_id = ""
            self.editing_dataset_name = ""

    def cancel_edit_dataset_name(self):
        """Cancel editing dataset name."""
        self.editing_dataset_id = ""
        self.editing_dataset_name = ""

    async def handle_dataset_name_keydown(self, key: str):
        """Handle keyboard shortcuts for dataset name editing."""
        if key == "Enter":
            async for event in self.save_dataset_name():
                yield event
        elif key == "Escape":
            self.cancel_edit_dataset_name()
