"""
API State — State management for API keys and models.

Manages:
- API key creation (with one-time raw key display)
- API key revocation
- API model listing and deactivation
"""

import reflex as rx
from typing import Optional
from pydantic import BaseModel
from backend.supabase_client import (
    create_api_key,
    get_user_api_keys,
    revoke_api_key,
    delete_api_key,
    get_project_api_models,
    deactivate_api_model,
    get_api_usage_stats,
    get_project,
)
from app_state import AuthState


class APIKeyModel(BaseModel):
    """Model for API key display (excludes key_hash for security)."""
    id: str = ""
    name: str = ""
    key_prefix: str = ""
    is_active: bool = True
    created_at: str = ""
    last_used_at: Optional[str] = None
    rate_limit_rpm: int = 60
    monthly_quota: Optional[int] = None
    requests_this_month: int = 0


class APIModelModel(BaseModel):
    """Model for API model display."""
    id: str = ""
    slug: str = ""
    display_name: str = ""
    description: Optional[str] = None
    model_type: str = "detection"
    backbone: str = "yolo"  # Detection engine: "yolo" or "convnext"
    classes_snapshot: list[str] = []
    is_active: bool = True
    total_requests: int = 0
    last_used_at: Optional[str] = None
    created_at: str = ""
    sam3_confidence: float = 0.25  # SAM3 detection threshold (classification models)
    sam3_imgsz: int = 640  # SAM3 inference resolution (classification models)



class APIState(rx.State):
    """State for API management page."""
    
    # Data
    api_keys: list[APIKeyModel] = []
    api_models: list[APIModelModel] = []
    
    # Project context
    current_project_id: str = ""
    project_name: str = ""
    
    # Loading states
    is_loading: bool = False  # Default to False to prevent skeleton flash on re-navigation
    is_creating_key: bool = False
    is_revoking_key: bool = False
    is_deactivating_model: bool = False
    _has_loaded_once: bool = False  # Track first load for skeleton display
    
    # Create key modal
    show_create_key_modal: bool = False
    new_key_name: str = ""
    new_key_raw: str = ""  # Only populated once after creation
    new_key_created: bool = False
    
    # Revoke key modal
    show_revoke_modal: bool = False
    revoke_key_id: str = ""
    revoke_key_name: str = ""
    
    # Deactivate model modal
    show_deactivate_modal: bool = False
    deactivate_model_id: str = ""
    deactivate_model_name: str = ""
    
    # Usage stats
    usage_stats: dict = {}
    
    # =========================================================================
    # LOAD DATA
    # =========================================================================
    
    async def load_api_data(self):
        """Load API keys and models for the current project."""
        # Get project_id from URL params
        self.current_project_id = self.router.page.params.get("project_id", "")
        
        # Only show skeleton on first load to prevent flickering on re-navigation
        if not self._has_loaded_once:
            self.is_loading = True
            yield
        
        try:
            auth_state = await self.get_state(AuthState)
            user_id = auth_state.user.get("id", "") if auth_state.user else ""
            
            if not user_id or not self.current_project_id:
                self.is_loading = False
                return
            
            # Load project name
            project = get_project(self.current_project_id)
            if project:
                self.project_name = project.get("name", "")
            
            # Load API keys for this project
            raw_keys = get_user_api_keys(user_id, self.current_project_id)
            self.api_keys = [
                APIKeyModel(
                    id=str(k.get("id", "")),
                    name=str(k.get("name", "")),
                    key_prefix=str(k.get("key_prefix", "")),
                    is_active=k.get("is_active", True),
                    created_at=str(k.get("created_at", ""))[:10],
                    last_used_at=str(k.get("last_used_at", ""))[:10] if k.get("last_used_at") else None,
                    rate_limit_rpm=k.get("rate_limit_rpm", 60),
                    monthly_quota=k.get("monthly_quota"),
                    requests_this_month=k.get("requests_this_month", 0),
                )
                for k in raw_keys
            ]
            
            # Load API models for this project
            raw_models = get_project_api_models(self.current_project_id)
            self.api_models = [
                APIModelModel(
                    id=str(m.get("id", "")),
                    slug=str(m.get("slug", "")),
                    display_name=str(m.get("display_name", "")),
                    description=m.get("description"),
                    model_type=str(m.get("model_type", "detection")),
                    backbone=str(m.get("backbone", "yolo")),
                    classes_snapshot=m.get("classes_snapshot", []) or [],
                    is_active=m.get("is_active", True),
                    total_requests=m.get("total_requests", 0) or 0,
                    last_used_at=str(m.get("last_used_at", ""))[:10] if m.get("last_used_at") else None,
                    created_at=str(m.get("created_at", ""))[:10],
                    sam3_confidence=float(m.get("sam3_confidence", 0.25) or 0.25),
                    sam3_imgsz=int(m.get("sam3_imgsz", 640) or 640),
                )
                for m in raw_models
            ]
            
            # Load usage stats
            self.usage_stats = get_api_usage_stats(user_id, self.current_project_id)
            
        except Exception as e:
            print(f"[ERROR] Failed to load API data: {e}")
            self.api_keys = []
            self.api_models = []
        finally:
            self.is_loading = False
            self._has_loaded_once = True
    
    # =========================================================================
    # COMPUTED PROPERTIES
    # =========================================================================
    
    @rx.var
    def has_keys(self) -> bool:
        """Check if there are any API keys."""
        return len(self.api_keys) > 0
    
    @rx.var
    def has_models(self) -> bool:
        """Check if there are any API models."""
        return len(self.api_models) > 0
    
    @rx.var
    def active_keys_count(self) -> int:
        """Count of active API keys."""
        return sum(1 for k in self.api_keys if k.is_active)
    
    @rx.var
    def active_models_count(self) -> int:
        """Count of active API models."""
        return sum(1 for m in self.api_models if m.is_active)
    
    @rx.var
    def total_requests(self) -> int:
        """Total API requests from usage stats."""
        return self.usage_stats.get("total_requests", 0) if self.usage_stats else 0
    
    @rx.var
    def can_create_key(self) -> bool:
        """Check if key name is valid for creation."""
        return len(self.new_key_name.strip()) >= 2
    
    # =========================================================================
    # CREATE KEY MODAL
    # =========================================================================
    
    def open_create_key_modal(self):
        """Open the create key modal."""
        self.show_create_key_modal = True
        self.new_key_name = ""
        self.new_key_raw = ""
        self.new_key_created = False
    
    def close_create_key_modal(self):
        """Close the create key modal."""
        self.show_create_key_modal = False
        self.new_key_name = ""
        self.new_key_raw = ""
        self.new_key_created = False
    
    def set_new_key_name(self, value: str):
        """Update the new key name."""
        self.new_key_name = value
    
    async def create_new_key(self):
        """Create a new API key."""
        if not self.can_create_key:
            return
        
        self.is_creating_key = True
        yield
        
        try:
            auth_state = await self.get_state(AuthState)
            user_id = auth_state.user.get("id", "") if auth_state.user else ""
            
            if not user_id:
                yield rx.toast.error("You must be logged in to create API keys.")
                return
            
            result = create_api_key(
                user_id=user_id,
                name=self.new_key_name.strip(),
                project_id=self.current_project_id,
            )
            
            if result:
                raw_key, key_record = result
                self.new_key_raw = raw_key
                self.new_key_created = True
                
                # Reload keys list
                async for event in self.load_api_data():
                    yield event
                
                yield rx.toast.success(f"API key '{self.new_key_name}' created!")
            else:
                yield rx.toast.error("Failed to create API key.")
                
        except Exception as e:
            print(f"[ERROR] Failed to create API key: {e}")
            yield rx.toast.error(f"Error: {str(e)}")
        finally:
            self.is_creating_key = False
    
    def copy_key_to_clipboard(self):
        """Copy the new key to clipboard (browser-side)."""
        # This will be handled via rx.set_clipboard
        pass
    
    # =========================================================================
    # REVOKE KEY MODAL
    # =========================================================================
    
    def open_revoke_modal(self, key_id: str, key_name: str):
        """Open the revoke key confirmation modal."""
        self.show_revoke_modal = True
        self.revoke_key_id = key_id
        self.revoke_key_name = key_name
    
    def close_revoke_modal(self):
        """Close the revoke modal."""
        self.show_revoke_modal = False
        self.revoke_key_id = ""
        self.revoke_key_name = ""
    
    async def confirm_revoke_key(self):
        """Revoke the selected API key."""
        if not self.revoke_key_id:
            return
        
        self.is_revoking_key = True
        yield
        
        try:
            success = revoke_api_key(self.revoke_key_id)
            
            if success:
                self.close_revoke_modal()
                async for event in self.load_api_data():
                    yield event
                yield rx.toast.success(f"API key '{self.revoke_key_name}' revoked.")
            else:
                yield rx.toast.error("Failed to revoke API key.")
                
        except Exception as e:
            print(f"[ERROR] Failed to revoke API key: {e}")
            yield rx.toast.error(f"Error: {str(e)}")
        finally:
            self.is_revoking_key = False
    
    # =========================================================================
    # DEACTIVATE MODEL MODAL
    # =========================================================================
    
    def open_deactivate_modal(self, model_id: str, model_name: str):
        """Open the deactivate model confirmation modal."""
        self.show_deactivate_modal = True
        self.deactivate_model_id = model_id
        self.deactivate_model_name = model_name
    
    def close_deactivate_modal(self):
        """Close the deactivate modal."""
        self.show_deactivate_modal = False
        self.deactivate_model_id = ""
        self.deactivate_model_name = ""
    
    async def confirm_deactivate_model(self):
        """Deactivate the selected API model."""
        if not self.deactivate_model_id:
            return
        
        self.is_deactivating_model = True
        yield
        
        try:
            success = deactivate_api_model(self.deactivate_model_id)
            
            if success:
                self.close_deactivate_modal()
                async for event in self.load_api_data():
                    yield event
                yield rx.toast.success(f"Model '{self.deactivate_model_name}' deactivated.")
            else:
                yield rx.toast.error("Failed to deactivate model.")
                
        except Exception as e:
            print(f"[ERROR] Failed to deactivate model: {e}")
            yield rx.toast.error(f"Error: {str(e)}")
        finally:
            self.is_deactivating_model = False
    
    # =========================================================================
    # UPDATE MODEL SAM3 CONFIDENCE
    # =========================================================================
    
    # Track which model is currently being edited for SAM3 confidence
    editing_sam3_model_id: str = ""
    editing_sam3_value: str = ""  # Track the current input value
    
    def start_editing_sam3(self, model_id: str, current_value: float):
        """Start editing SAM3 confidence for a model."""
        self.editing_sam3_model_id = model_id
        self.editing_sam3_value = str(current_value)
    
    def set_editing_sam3_value(self, value: str):
        """Update the editing value as user types."""
        self.editing_sam3_value = value
    
    def cancel_editing_sam3(self):
        """Cancel editing SAM3 confidence."""
        self.editing_sam3_model_id = ""
        self.editing_sam3_value = ""
    
    async def update_model_sam3_confidence(self, model_id: str, value: str):
        """Update the SAM3 confidence for a model in the database."""
        from backend.supabase_client import get_supabase
        
        try:
            # Validate and parse the value
            conf = float(value)
            if conf < 0 or conf > 1:
                yield rx.toast.error("SAM3 confidence must be between 0 and 1")
                self.editing_sam3_model_id = ""
                self.editing_sam3_value = ""
                return
            
            # Update in database
            client = get_supabase()
            client.table("api_models").update({
                "sam3_confidence": conf
            }).eq("id", model_id).execute()
            
            # Update local state
            for i, m in enumerate(self.api_models):
                if m.id == model_id:
                    updated = m.model_copy(update={"sam3_confidence": conf})
                    self.api_models[i] = updated
                    break
            
            self.editing_sam3_model_id = ""
            self.editing_sam3_value = ""
            yield rx.toast.success(f"SAM3 confidence updated to {conf:.2f}")
            
        except ValueError:
            yield rx.toast.error("Invalid number format")
            self.editing_sam3_model_id = ""
            self.editing_sam3_value = ""
        except Exception as e:
            print(f"[ERROR] Failed to update SAM3 confidence: {e}")
            yield rx.toast.error(f"Failed to update: {str(e)}")
            self.editing_sam3_model_id = ""
            self.editing_sam3_value = ""
    
    async def save_sam3_on_enter(self, model_id: str, key: str):
        """Save SAM3 confidence when Enter key is pressed."""
        if key == "Enter":
            async for event in self.update_model_sam3_confidence(model_id, self.editing_sam3_value):
                yield event
    
    # =========================================================================
    # UPDATE MODEL SAM3 IMAGE SIZE
    # =========================================================================
    
    editing_imgsz_model_id: str = ""
    editing_imgsz_value: str = ""
    
    def start_editing_imgsz(self, model_id: str, current_value: int):
        """Start editing SAM3 imgsz for a model."""
        self.editing_imgsz_model_id = model_id
        self.editing_imgsz_value = str(current_value)
    
    def set_editing_imgsz_value(self, value: str):
        """Update the editing value as user types."""
        self.editing_imgsz_value = value
    
    async def update_model_sam3_imgsz(self, model_id: str, value: str):
        """Update the SAM3 imgsz for a model in the database."""
        from backend.supabase_client import get_supabase
        
        try:
            imgsz = int(value)
            if imgsz < 32 or imgsz > 2048:
                yield rx.toast.error("SAM3 resolution must be between 32 and 2048")
                self.editing_imgsz_model_id = ""
                self.editing_imgsz_value = ""
                return
            
            client = get_supabase()
            client.table("api_models").update({
                "sam3_imgsz": imgsz
            }).eq("id", model_id).execute()
            
            for i, m in enumerate(self.api_models):
                if m.id == model_id:
                    updated = m.model_copy(update={"sam3_imgsz": imgsz})
                    self.api_models[i] = updated
                    break
            
            self.editing_imgsz_model_id = ""
            self.editing_imgsz_value = ""
            yield rx.toast.success(f"SAM3 resolution updated to {imgsz}")
            
        except ValueError:
            yield rx.toast.error("Invalid number format")
            self.editing_imgsz_model_id = ""
            self.editing_imgsz_value = ""
        except Exception as e:
            print(f"[ERROR] Failed to update SAM3 imgsz: {e}")
            yield rx.toast.error(f"Failed to update: {str(e)}")
            self.editing_imgsz_model_id = ""
            self.editing_imgsz_value = ""
    
    async def save_imgsz_on_enter(self, model_id: str, key: str):
        """Save SAM3 imgsz when Enter key is pressed."""
        if key == "Enter":
            async for event in self.update_model_sam3_imgsz(model_id, self.editing_imgsz_value):
                yield event
