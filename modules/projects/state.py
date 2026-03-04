"""
Projects State — State management for project container CRUD operations.

Projects are containers for datasets. Classes are now stored at the dataset level.
"""

import reflex as rx
from typing import Optional
from backend.supabase_client import (
    get_user_projects,
    create_project as db_create_project,
    delete_project as db_delete_project,
    get_project_dataset_count,
    get_project_datasets,
)
from backend.r2_storage import R2Client
from app_state import AuthState
from modules.projects.models import ProjectModel


class ProjectsState(rx.State):
    """State for the projects page and creation modal."""
    
    # Projects list (typed for rx.foreach)
    projects: list[ProjectModel] = []
    is_loading: bool = False  # Default to False to prevent skeleton flash on re-navigation
    _has_loaded_once: bool = False  # Track first load for skeleton display
    
    # Create Modal state
    show_modal: bool = False
    new_project_name: str = ""
    new_project_description: str = ""
    is_creating: bool = False
    
    create_error: str = ""
    
    # Delete Modal state
    show_delete_modal: bool = False
    delete_project_id: str = ""
    delete_project_name: str = ""
    delete_project_dataset_count: int = 0
    delete_confirmation_text: str = ""
    is_deleting: bool = False
    delete_error: str = ""
    
    async def load_projects(self):
        """Fetch all project containers for the current user."""
        # Only show skeleton on first load to prevent flickering on re-navigation
        if not self._has_loaded_once:
            self.is_loading = True
            yield
        
        try:
            # Access AuthState to get user_id
            auth_state = await self.get_state(AuthState)
            user_id = auth_state.user.get("id", "") if auth_state.user else ""
            print(f"[DEBUG] Loading projects for user_id={user_id}")
            if user_id:
                raw_projects = get_user_projects(user_id)
                print(f"[DEBUG] Got {len(raw_projects)} projects from DB")
                self.projects = [
                    ProjectModel(
                        id=str(p.get("id", "")),
                        name=str(p.get("name", "")),
                        description=str(p.get("description", "") or ""),
                        dataset_count=get_project_dataset_count(p.get("id", "")),
                        created_at=str(p.get("created_at", "")),
                    )
                    for p in raw_projects
                ]
            else:
                print("[DEBUG] No user_id, setting empty projects")
                self.projects = []
        except Exception as e:
            print(f"[DEBUG] Error loading projects: {e}")
            self.projects = []
        finally:
            self.is_loading = False
            self._has_loaded_once = True
    
    # =========================================================================
    # CREATE MODAL
    # =========================================================================
    
    def open_modal(self):
        """Open the new project modal."""
        self.show_modal = True
        self.new_project_name = ""
        self.new_project_description = ""
        self.create_error = ""
    
    def close_modal(self):
        """Close the new project modal."""
        self.show_modal = False
        self.new_project_name = ""
        self.new_project_description = ""
        self.create_error = ""
    
    def set_project_name(self, value: str):
        """Update the new project name."""
        self.new_project_name = value
    
    def set_project_description(self, value: str):
        """Update the new project description."""
        self.new_project_description = value
    
    @rx.var
    def can_create_project(self) -> bool:
        """Check if all required fields are filled for project creation."""
        return bool(self.new_project_name.strip())
    
    async def create_project(self):
        """Create a new project container and redirect to it."""
        if not self.new_project_name.strip():
            self.create_error = "Project name is required."
            return
        
        self.is_creating = True
        self.create_error = ""
        yield
        
        try:
            # Access AuthState to get user_id
            auth_state = await self.get_state(AuthState)
            user_id = auth_state.user.get("id", "") if auth_state.user else ""
            
            if not user_id:
                self.create_error = "You must be logged in to create a project."
                return
            
            # Create in database
            project = db_create_project(
                user_id=user_id,
                name=self.new_project_name.strip(),
                description=self.new_project_description.strip(),
            )
            
            if project:
                self.close_modal()
                # Redirect to the new project
                yield rx.redirect(f"/projects/{project['id']}")
            else:
                self.create_error = "Failed to create project. Please try again."
                
        except Exception as e:
            self.create_error = f"Error: {str(e)}"
        finally:
            self.is_creating = False
    
    # =========================================================================
    # DELETE MODAL
    # =========================================================================
    
    def open_delete_modal(self, project_id: str, project_name: str, dataset_count: int):
        """Open the delete confirmation modal."""
        self.show_delete_modal = True
        self.delete_project_id = project_id
        self.delete_project_name = project_name
        self.delete_project_dataset_count = dataset_count
        self.delete_confirmation_text = ""
        self.delete_error = ""
    
    def close_delete_modal(self):
        """Close the delete confirmation modal."""
        self.show_delete_modal = False
        self.delete_project_id = ""
        self.delete_project_name = ""
        self.delete_project_dataset_count = 0
        self.delete_confirmation_text = ""
        self.delete_error = ""
    
    def set_delete_confirmation_text(self, value: str):
        """Update the delete confirmation text."""
        self.delete_confirmation_text = value
    
    @rx.var
    def can_delete(self) -> bool:
        """Check if the delete confirmation text matches 'delete'."""
        return self.delete_confirmation_text.lower().strip() == "delete"
    
    async def confirm_delete_project(self):
        """Delete the project after confirmation."""
        if not self.can_delete:
            self.delete_error = "Please type 'delete' to confirm."
            return
        
        self.is_deleting = True
        self.delete_error = ""
        yield
        
        try:
            # 1. Cleanup R2 Files
            # This includes all datasets' files and project-level files
            r2 = R2Client()
            total_deleted = 0
            
            # Fetch datasets to delete their files
            datasets = get_project_datasets(self.delete_project_id)
            print(f"[DEBUG] Found {len(datasets)} datasets to cleanup")
            
            for dataset in datasets:
                d_id = dataset.get("id")
                if d_id:
                    # Delete dataset folder: datasets/{dataset_id}/
                    count = r2.delete_files_with_prefix(f"datasets/{d_id}/")
                    total_deleted += count
                    print(f"[DEBUG] Deleted {count} files for dataset {d_id}")
            
            # Delete project-level folder: projects/{project_id}/
            # (In case there are legacy files or project-level uploads)
            project_count = r2.delete_files_with_prefix(f"projects/{self.delete_project_id}/")
            total_deleted += project_count
            print(f"[DEBUG] Deleted {project_count} project-level files")
            print(f"[DEBUG] Total files deleted from R2: {total_deleted}")
            
            # 2. Delete from database (cascades to datasets and images via FK)
            success = db_delete_project(self.delete_project_id)
            
            if success:
                self.close_delete_modal()
                # Reload projects list
                async for event in self.load_projects():
                    yield event
                yield rx.toast.success(f"Project '{self.delete_project_name}' deleted.")
            else:
                self.delete_error = "Failed to delete project. Please try again."
                
        except Exception as e:
            print(f"[DEBUG] Error deleting project: {e}")
            self.delete_error = f"Error: {str(e)}"
        finally:
            self.is_deleting = False

    # =========================================================================
    # Enter Key Handlers
    # =========================================================================

    async def handle_create_keydown(self, key: str):
        """Handle Enter key in create project modal."""
        if key == "Enter" and not self.is_creating:
            async for event in self.create_project():
                yield event

    async def handle_delete_keydown(self, key: str):
        """Handle Enter key in delete project confirmation."""
        if key == "Enter" and self.can_delete and not self.is_deleting:
            async for event in self.confirm_delete_project():
                yield event
