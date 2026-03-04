"""
Training State — State management for the training dashboard.

Handles project context, dataset selection, configuration, and training run history.
Training is at project level, allowing combining multiple datasets.
"""

import reflex as rx
from typing import Optional
from pydantic import BaseModel
import modal
from backend.supabase_client import (
    get_project,
    get_project_datasets,
    get_dataset_image_count,
    get_dataset_training_runs,
    get_dataset_videos,
    get_video_keyframes,
    get_dataset_images,
    create_training_run,
    get_project_training_runs,
    delete_training_run as db_delete_training_run,
    create_model,
    update_training_run,
    get_user_preferences,
    update_user_preferences,
    get_combined_class_counts_for_datasets,
    promote_model_to_api,
    get_user_local_machines,
)
from backend.r2_storage import R2Client
from app_state import AuthState


class DatasetOption(BaseModel):
    """Model for a dataset in the selection list."""
    id: str = ""
    name: str = ""
    type: str = "image"
    labeled_count: int = 0
    total_count: int = 0
    is_selected: bool = False
    usage_tag: str = "train"


class TrainingRunModel(BaseModel):
    """Model for a training run row."""
    id: str = ""
    status: str = "pending"
    target: str = "cloud"
    config: dict = {}
    metrics: Optional[dict] = None
    artifacts_r2_prefix: Optional[str] = None
    dataset_ids: list[str] = []  # List of dataset IDs used in training
    dataset_names: list[str] = []  # Dataset names at time of training (snapshot)
    created_at: str = ""
    started_at: Optional[str] = None
    completed_at: Optional[str] = None
    error_message: Optional[str] = None
    logs: Optional[str] = None
    # Metadata fields for run management
    alias: Optional[str] = None  # User-friendly name for dropdowns
    notes: Optional[str] = None  # Free-form notes
    tags: list[str] = []  # Tags for organizing runs
    classes: list[str] = []  # Model classes used in this training run (snapshot)
    model_type: str = "detection"  # "detection" or "classification"


class TrainingState(rx.State):
    """State for the training dashboard page (project-level)."""
    
    # Project context
    current_project_id: str = ""
    project_name: str = ""
    
    # Datasets in this project (for selection)
    datasets: list[DatasetOption] = []
    selected_dataset_ids: list[str] = []
    
    # Aggregated stats from selected datasets
    total_labeled_count: int = 0
    total_images_count: int = 0
    combined_classes: list[str] = []
    class_distribution: dict[str, int] = {}  # class_name -> annotation count
    
    # Configuration
    epochs: int = 100
    model_size: str = "n"  # n/s/m/l
    batch_size: int = 16
    
    # Compute target (action-level selection)
    compute_target: str = "cloud"  # 'cloud' or 'local'
    selected_machine: str = ""     # machine name for local target
    local_machines: list[dict] = []  # cached list of user's machines
    
    # Training mode: 'detection', 'classification', or 'sam3_finetune'
    training_mode: str = "detection"
    
    # SAM3 Fine-Tuning configuration
    sam3_num_images: int = 10     # 0 = all, 10/50/100 for few-shot
    sam3_max_epochs: int = 3
    sam3_early_stop_patience: int = 2  # 0 = disabled
    sam3_lr_scale: float = 0.1
    sam3_resolution: int = 1008   # Display only (not configurable initially)
    sam3_prompt: str = "animal"   # SAM3 concept prompt (domain-level, not per-class)
    
    # Classification-specific configuration
    classify_image_size: int = 224  # 224/256/384/512
    classify_batch_size: int = 32   # Classification can use larger batches
    classifier_backbone: str = "yolo"  # "yolo" or "convnext"
    convnext_model_size: str = "tiny"  # tiny/small/base/large
    convnext_lr0: float = 0.0001  # ConvNeXt learning rate (1e-4 for fine-tuning)
    convnext_weight_decay: float = 0.05  # ConvNeXt weight decay (AdamW regularization)
    
    # Advanced Configuration (collapsible section)
    show_advanced_settings: bool = False
    patience: int = 50  # Early stopping patience
    optimizer: str = "auto"  # auto/SGD/Adam/AdamW
    lr0: float = 0.01  # Initial learning rate
    lrf: float = 0.01  # Final learning rate factor
    
    # Train/Val split configuration
    train_split_percentage: int = 80  # Default 80/20 split

    
    # Training runs history
    training_runs: list[TrainingRunModel] = []
    is_loading: bool = False  # Default to False to prevent skeleton flash on re-navigation
    _has_loaded_once: bool = False  # Track first load for skeleton display
    
    # UI state
    is_starting: bool = False
    start_error: str = ""
    is_polling: bool = False
    selected_run_id: str = ""
    
    # Delete modal state
    show_delete_modal: bool = False
    delete_run_id: str = ""
    delete_confirmation: str = ""
    
    # API Promote modal state (Phase A1)
    show_api_promote_modal: bool = False
    api_promote_run_id: str = ""
    api_slug: str = ""
    api_display_name: str = ""
    api_description: str = ""
    api_promoting: bool = False
    is_deleting: bool = False
    
    # Autolabel upload state
    is_uploading_to_autolabel: bool = False
    
    # Run metadata editing state (for run detail page)
    editing_alias: bool = False
    editing_notes: bool = False
    temp_alias: str = ""
    temp_notes: str = ""
    
    # Inline table editing state (for dashboard history table)
    table_editing_run_id: str = ""  # Which run is being edited
    table_editing_field: str = ""   # "alias" or "notes"
    table_temp_value: str = ""      # Temp value while editing
    
    # Sort & filter state for history table
    sort_column: str = "created_at"  # Column to sort by
    sort_ascending: bool = False     # False = newest first
    filter_status: str = "all"       # all, completed, running, failed
    filter_tag: str = "all"          # all, or specific tag
    filter_model_type: str = "all"   # all, detection, classification, sam3_finetune
    filter_backbone: str = "all"     # all, convnext, yolo
    
    # Continue training state
    continue_from_run: bool = False   # Checkbox: continue from existing run
    selected_parent_run_id: str = "" # Selected run to continue from
    
    # UI Section States
    is_datasets_collapsed: bool = True
    is_model_collapsed: bool = True  # Model card collapsed by default
    has_new_datasets: bool = False
    
    async def load_dashboard(self):
        """Load project info, datasets, and training history on page load."""
        # Only show skeleton on first load to prevent flickering on re-navigation
        if not self._has_loaded_once:
            async with self:
                self.is_loading = True
            yield
        
        try:
            # Get project_id from route
            async with self:
                project_id = self.router.page.params.get("project_id", "")
            
            if not project_id:
                print("[DEBUG] Missing project_id in route")
                return
            
            # Load project info
            project = get_project(project_id)
            project_name = ""
            if project:
                project_name = project.get("name", "")
            else:
                print(f"[DEBUG] Project {project_id} not found")
                return
            
            # Load user's local machines for compute target selection
            auth_state = await self.get_state(AuthState)
            user_id = auth_state.user.get("id", "") if auth_state.user else ""
            local_machines = []
            if user_id:
                local_machines = get_user_local_machines(user_id)
            
            # Load datasets in this project
            raw_datasets = get_project_datasets(project_id)
            datasets = []
            current_ids = []
            selected_ids = [] 
            
            # Restore training preferences to get project-specific dataset tracking
            auth_state = await self.get_state(AuthState)
            project_prefs = {}
            if auth_state.user_id:
                prefs = get_user_preferences(auth_state.user_id)
                # Structure: training.projects.<project_id> = { "known_ids": [], "selected_ids": [] }
                training_prefs = prefs.get("training", {})
                projects_prefs = training_prefs.get("projects", {})
                project_prefs = projects_prefs.get(project_id, {})
            
            known_ids = project_prefs.get("known_ids", [])
            saved_selected_ids = project_prefs.get("selected_ids", None) # None indicates no save yet
            
            # Collect IDs for detection
            dataset_map = {} # id -> is_labeled
            
            for d in raw_datasets:
                dataset_id = str(d.get("id", ""))
                current_ids.append(dataset_id)
                dataset_type = str(d.get("type", "image"))
                
                # Count based on dataset type
                if dataset_type == "video":
                    # For video datasets, count keyframes with annotations
                    videos = get_dataset_videos(dataset_id)
                    labeled = 0
                    total = 0
                    for v in videos:
                        keyframes = get_video_keyframes(v.get("id", ""))
                        total += len(keyframes)
                        # Count keyframes with annotations
                        labeled += sum(1 for kf in keyframes if (kf.get("annotation_count") or 0) > 0)
                else:
                    # For image datasets, count images
                    labeled = get_dataset_image_count(dataset_id, labeled_only=True)
                    total = get_dataset_image_count(dataset_id)
                
                is_labeled = labeled > 0
                dataset_map[dataset_id] = is_labeled
                
                # Determine "is_selected" status
                # Logic:
                # 1. If we have saved selection, use it (if ID still exists)
                # 2. If NO saved selection (first time), default to "all labeled"
                is_selected = False
                if saved_selected_ids is not None:
                    is_selected = dataset_id in saved_selected_ids
                else:
                    is_selected = is_labeled
                
                if is_selected:
                    selected_ids.append(dataset_id)
                
                datasets.append(DatasetOption(
                    id=dataset_id,
                    name=str(d.get("name", "")),
                    type=dataset_type,
                    labeled_count=labeled,
                    total_count=total,
                    is_selected=is_selected,
                    usage_tag=str(d.get("usage_tag", "train")),
                ))
            
            # Detect new datasets
            # New = present in current_ids but NOT in known_ids
            new_ids = set(current_ids) - set(known_ids)
            has_new = len(new_ids) > 0
            
            # Check if we have stale IDs in our known list (datasets deleted)
            # Stale = in known_ids but NOT in current_ids
            # We don't need to do anything immediately, they will be cleaned up next save
            
            async with self:
                self.current_project_id = project_id
                self.project_name = project_name
                self.local_machines = local_machines
                self.datasets = datasets
                self.selected_dataset_ids = selected_ids
                self.has_new_datasets = has_new
            
            await self._update_aggregated_stats()
            await self._update_class_distribution()
            
            # Update general training prefs (epochs, etc)
            if auth_state.user_id:
                # ... existing general pref loading ...
                if "epochs" in training_prefs:
                    self.epochs = training_prefs["epochs"]
                if "model_size" in training_prefs:
                    self.model_size = training_prefs["model_size"]
                if "batch_size" in training_prefs:
                    self.batch_size = training_prefs["batch_size"]
                if "patience" in training_prefs:
                    self.patience = training_prefs["patience"]
                if "optimizer" in training_prefs:
                    self.optimizer = training_prefs["optimizer"]
                if "lr0" in training_prefs:
                    self.lr0 = training_prefs["lr0"]
                if "lrf" in training_prefs:
                    self.lrf = training_prefs["lrf"]
                if "train_split_percentage" in training_prefs:
                    self.train_split_percentage = training_prefs["train_split_percentage"]
                # Classification settings
                if "classify_image_size" in training_prefs:
                    self.classify_image_size = training_prefs["classify_image_size"]
                if "classify_batch_size" in training_prefs:
                    self.classify_batch_size = training_prefs["classify_batch_size"]
                if "classifier_backbone" in training_prefs:
                    self.classifier_backbone = training_prefs["classifier_backbone"]
                if "convnext_model_size" in training_prefs:
                    self.convnext_model_size = training_prefs["convnext_model_size"]
                if "convnext_lr0" in training_prefs:
                    self.convnext_lr0 = training_prefs["convnext_lr0"]
                if "convnext_weight_decay" in training_prefs:
                    self.convnext_weight_decay = training_prefs["convnext_weight_decay"]
                # Training mode (detection/classification)
                if "training_mode" in training_prefs:
                    self.training_mode = training_prefs["training_mode"]

            
            # Load training runs for project
            runs = get_project_training_runs(project_id)
            history = [
                TrainingRunModel(
                    id=str(r.get("id", "")),
                    status=str(r.get("status", "pending")),
                    target=str(r.get("target", "cloud")),
                    config=r.get("config", {}),
                    metrics=r.get("metrics"),
                    artifacts_r2_prefix=r.get("artifacts_r2_prefix"),
                    dataset_ids=r.get("dataset_ids", []) or [],
                    dataset_names=r.get("dataset_names", []) or [],  # Dataset names snapshot
                    created_at=r.get("created_at", "").split(".")[0].replace("T", " "),
                    started_at=r.get("started_at"),
                    completed_at=r.get("completed_at"),
                    error_message=r.get("error_message"),
                    logs=r.get("logs"),
                    alias=r.get("alias"),
                    notes=r.get("notes"),
                    tags=r.get("tags", []) or [],
                    # Use classes_snapshot if available, fallback to config.classes
                    classes=r.get("classes_snapshot", []) or r.get("config", {}).get("classes", []) or [],
                    model_type=r.get("model_type", "detection"),
                ) for r in runs
            ]
            
            async with self:
                self.training_runs = history
                # Combine classes logic...
                all_classes = set()
                for d in raw_datasets:
                     d_classes = d.get("classes", []) or []
                     all_classes.update(d_classes)
                self.combined_classes = sorted(list(all_classes))

        except Exception as e:
            print(f"[DEBUG] Error loading training dashboard: {e}")
        finally:
            async with self:
                self.is_loading = False
                self._has_loaded_once = True
        
        # Trigger polling if needed
        should_poll = False
        async with self:
            should_poll = not self.is_polling and any(r.status in ["pending", "queued", "running"] for r in self.training_runs)
        
        if should_poll:
            yield TrainingState.poll_training_status()
    
    async def _update_aggregated_stats(self):
        """Update totals based on selected datasets."""
        labeled = 0
        total = 0
        async with self:
            for d in self.datasets:
                if d.id in self.selected_dataset_ids:
                    labeled += d.labeled_count
                    total += d.total_count
            self.total_labeled_count = labeled
            self.total_images_count = total
    
    async def _update_class_distribution(self):
        """Compute class distribution for selected datasets (batched query)."""
        if not self.selected_dataset_ids:
            async with self:
                self.class_distribution = {}
            return
        
        # Fetch project classes for class_id -> class_name resolution
        from backend.supabase_client import get_project
        project = get_project(self.current_project_id)
        project_classes = project.get("classes", []) if project else []
        
        # Build dataset_types mapping
        dataset_types = {d.id: d.type for d in self.datasets}
        
        # Use batched backend function (2-3 queries max)
        counts = get_combined_class_counts_for_datasets(
            self.selected_dataset_ids,
            dataset_types,
            project_classes=project_classes
        )
        
        async with self:
            self.class_distribution = counts
            
    async def save_project_prefs(self):
        """Save selected datasets and update known datasets list."""
        auth_state = await self.get_state(AuthState)
        if not auth_state.user_id or not self.current_project_id:
            return
            
        current_ids = [d.id for d in self.datasets]
        
        # Get existing prefs first to preserve other projects/settings
        prefs = get_user_preferences(auth_state.user_id)
        training_prefs = prefs.get("training", {})
        projects_prefs = training_prefs.get("projects", {})
        
        # Update current project prefs
        projects_prefs[self.current_project_id] = {
            "known_ids": current_ids, # Save ALL current as known (cleaning up stale ones implicit)
            "selected_ids": self.selected_dataset_ids
        }
        
        training_prefs["projects"] = projects_prefs
        update_user_preferences(auth_state.user_id, "training", training_prefs)

    async def toggle_dataset(self, dataset_id: str):
        """Toggle a dataset selection."""
        async with self:
            if dataset_id in self.selected_dataset_ids:
                self.selected_dataset_ids = [d for d in self.selected_dataset_ids if d != dataset_id]
            else:
                self.selected_dataset_ids = self.selected_dataset_ids + [dataset_id]
            
            # Update dataset's is_selected flag
            updated = []
            for d in self.datasets:
                if d.id == dataset_id:
                    updated.append(DatasetOption(
                        id=d.id,
                        name=d.name,
                        type=d.type,
                        labeled_count=d.labeled_count,
                        total_count=d.total_count,
                        is_selected=d.id in self.selected_dataset_ids,
                        usage_tag=d.usage_tag,
                    ))
                else:
                    updated.append(d)
            self.datasets = updated
        
        await self._update_aggregated_stats()
        await self._update_class_distribution()
        await self.save_project_prefs()
    
    async def toggle_datasets_collapsed(self):
        """Toggle datasets section visibility."""
        async with self:
            self.is_datasets_collapsed = not self.is_datasets_collapsed
            
            # If expanding and we have new datasets, acknowledge them being seen
            if not self.is_datasets_collapsed and self.has_new_datasets:
                self.has_new_datasets = False
                # Trigger save to update 'known_ids' so notification doesn't come back
                # We can fire and forget this effectively
        
        if not self.is_datasets_collapsed:
             await self.save_project_prefs()
    
    def toggle_model_collapsed(self):
        """Toggle model section visibility."""
        self.is_model_collapsed = not self.is_model_collapsed
    
    # =========================================================================
    # Configuration setters
    # =========================================================================
    
    async def save_training_prefs(self, _value=None):
        """Save current training configuration to preferences.
        
        Called on slider on_value_commit (when user releases slider).
        Accepts optional value arg to work with on_value_commit signature.
        """
        auth_state = await self.get_state(AuthState)
        if auth_state.user_id:
            update_user_preferences(auth_state.user_id, "training", {
                "epochs": self.epochs,
                "model_size": self.model_size,
                "batch_size": self.batch_size,
                "patience": self.patience,
                "optimizer": self.optimizer,
                "lr0": self.lr0,
                "lrf": self.lrf,
                "train_split_percentage": self.train_split_percentage,
                # Classification settings
                "classify_image_size": self.classify_image_size,
                "classify_batch_size": self.classify_batch_size,
                "classifier_backbone": self.classifier_backbone,
                "convnext_model_size": self.convnext_model_size,
                "convnext_lr0": self.convnext_lr0,
                "convnext_weight_decay": self.convnext_weight_decay,
                # Training mode
                "training_mode": self.training_mode,
            })
    
    def set_epochs(self, value: list[int]):
        """Set epochs from slider (live update, no save)."""
        if value:
            self.epochs = value[0]
    
    def set_sam3_max_epochs(self, value: list[int]):
        """Set SAM3 max epochs from slider (live update, no save)."""
        if value:
            self.sam3_max_epochs = value[0]
    
    def set_sam3_early_stop_patience(self, value: list[int]):
        """Set SAM3 early stopping patience from slider."""
        if value:
            self.sam3_early_stop_patience = value[0]
    
    def set_sam3_num_images(self, value: str):
        """Set SAM3 num images from select (passes string)."""
        self.sam3_num_images = int(value)
    
    def set_sam3_lr_scale(self, value: str):
        """Set SAM3 LR scale from select (passes string)."""
        self.sam3_lr_scale = float(value)
    
    async def set_model_size(self, value: str):
        """Set model size (n/s/m/l) and persist (select, not slider)."""
        self.model_size = value
        await self.save_training_prefs()
    
    async def set_batch_size(self, value: str):
        """Set batch size and persist (select, not slider)."""
        self.batch_size = int(value)
        await self.save_training_prefs()
    
    def set_compute_target(self, value: str | list[str]):
        """Set compute target (cloud/local)."""
        target = value[0] if isinstance(value, list) else value
        self.compute_target = target
        if target == "cloud":
            self.selected_machine = ""
    
    def set_selected_machine(self, value: str):
        """Set selected local machine."""
        self.selected_machine = value
    
    @rx.var
    def has_local_machines(self) -> bool:
        """Check if user has any local GPU machines configured."""
        return len(self.local_machines) > 0
    
    def toggle_advanced_settings(self):
        """Toggle advanced settings visibility."""
        self.show_advanced_settings = not self.show_advanced_settings
    
    def set_patience(self, value: list[int]):
        """Set early stopping patience from slider (live update, no save)."""
        if value:
            self.patience = value[0]
    
    async def set_optimizer(self, value: str):
        """Set optimizer (auto/SGD/Adam/AdamW) and persist (select, not slider)."""
        self.optimizer = value
        await self.save_training_prefs()
    
    def set_lr0(self, value: list[int]):
        """Set initial learning rate from slider (live update, no save)."""
        if value:
            # Map 0-100 to 0.001-0.1
            self.lr0 = round(0.001 + (value[0] / 100) * 0.099, 4)
    
    def set_lrf(self, value: list[int]):
        """Set final learning rate factor from slider (live update, no save)."""
        if value:
            # Map 0-100 to 0.001-0.1
            self.lrf = round(0.001 + (value[0] / 100) * 0.099, 4)
    
    def set_convnext_lr0_slider(self, value: list[int]):
        """Set ConvNeXt LR from slider (live update, no save). Range: 1e-5 to 1e-3."""
        if value:
            # Map 0-100 to 0.00001-0.001
            min_lr, max_lr = 0.00001, 0.001
            self.convnext_lr0 = round(min_lr + (value[0] / 100) * (max_lr - min_lr), 6)

    async def set_convnext_lr0_input(self, value: str):
        """Set ConvNeXt LR from direct text input. Parses string, clamps to valid range."""
        try:
            lr = float(value)
            lr = max(0.000001, min(0.01, lr))  # Clamp to reasonable range
            self.convnext_lr0 = round(lr, 6)
            await self.save_training_prefs()
        except (ValueError, TypeError):
            pass  # Ignore invalid input

    def set_convnext_weight_decay_slider(self, value: list[int]):
        """Set ConvNeXt weight decay from slider (live update, no save). Range: 0.01 to 0.2."""
        if value:
            # Map 0-100 to 0.01-0.2
            min_wd, max_wd = 0.01, 0.2
            self.convnext_weight_decay = round(min_wd + (value[0] / 100) * (max_wd - min_wd), 3)
    
    async def set_convnext_weight_decay_input(self, value: str):
        """Set ConvNeXt weight decay from direct text input. Parses string, clamps to valid range."""
        try:
            wd = float(value)
            wd = max(0.001, min(0.5, wd))  # Clamp to reasonable range
            self.convnext_weight_decay = round(wd, 4)
            await self.save_training_prefs()
        except (ValueError, TypeError):
            pass  # Ignore invalid input
    
    def set_train_split(self, value: list[int]):
        """Set train/val split percentage from slider (live update, no save)."""
        if value:
            self.train_split_percentage = value[0]
    
    async def set_training_mode(self, value: str | list[str]):
        """Set training mode (detection/classification) and persist."""
        if isinstance(value, list):
            self.training_mode = value[0] if value else "detection"
        else:
            self.training_mode = value
        await self.save_training_prefs()
    
    async def set_classify_image_size(self, value: str):
        """Set classification image size and persist."""
        self.classify_image_size = int(value)
        await self.save_training_prefs()
    
    async def set_classify_batch_size(self, value: str):
        """Set classification batch size and persist."""
        self.classify_batch_size = int(value)
        await self.save_training_prefs()
    
    async def set_classifier_backbone(self, value: str):
        """Set classifier backbone (yolo/convnext) and persist."""
        self.classifier_backbone = value
        await self.save_training_prefs()
    
    async def set_convnext_model_size(self, value: str):
        """Set ConvNeXt model size (tiny/small/base/large) and persist."""
        self.convnext_model_size = value
        await self.save_training_prefs()
    
    async def set_convnext_lr0(self, value: float):
        """Set ConvNeXt learning rate and persist."""
        self.convnext_lr0 = value
        await self.save_training_prefs()

    
    # =========================================================================
    # Computed properties
    # =========================================================================
    
    @rx.var
    def lr0_slider_value(self) -> int:
        """Convert lr0 float (0.001-0.1) back to slider value (0-100)."""
        # Reverse: (lr0 - 0.001) / 0.099 * 100
        return int(round((self.lr0 - 0.001) / 0.099 * 100))
    
    @rx.var
    def lrf_slider_value(self) -> int:
        """Convert lrf float (0.001-0.1) back to slider value (0-100)."""
        return int(round((self.lrf - 0.001) / 0.099 * 100))
    
    @rx.var
    def convnext_lr0_slider_value(self) -> int:
        """Convert convnext_lr0 to slider value (0-100) for range 0.00001-0.001."""
        # ConvNeXt uses much lower LR range: 1e-5 to 1e-3
        # Map 0.00001 -> 0, 0.001 -> 100
        min_lr, max_lr = 0.00001, 0.001
        normalized = (self.convnext_lr0 - min_lr) / (max_lr - min_lr)
        return int(round(max(0, min(100, normalized * 100))))

    @rx.var
    def convnext_weight_decay_slider_value(self) -> int:
        """Convert convnext_weight_decay to slider value (0-100) for range 0.01-0.2."""
        min_wd, max_wd = 0.01, 0.2
        normalized = (self.convnext_weight_decay - min_wd) / (max_wd - min_wd)
        return int(round(max(0, min(100, normalized * 100))))
    
    @rx.var
    def effective_lr_display(self) -> float:
        """Show the effective learning rate based on backbone selection."""
        if self.training_mode == "classification" and self.classifier_backbone == "convnext":
            return self.convnext_lr0
        return self.lr0
    
    @rx.var
    def has_explicit_validation_datasets(self) -> bool:
        """Check if any selected datasets are tagged as validation."""
        return any(
            d.usage_tag == "validation" and d.id in self.selected_dataset_ids
            for d in self.datasets
        )
    
    @rx.var
    def can_start_training(self) -> bool:
        """Check if training can be started (at least 1 labeled image selected)."""
        return self.total_labeled_count > 0
    
    @rx.var
    def class_distribution_sorted(self) -> list[tuple[str, int]]:
        """Get class distribution sorted by count descending."""
        return sorted(
            self.class_distribution.items(),
            key=lambda x: x[1],
            reverse=True
        )
    
    @rx.var
    def has_class_distribution(self) -> bool:
        """Check if there's any class distribution data."""
        return len(self.class_distribution) > 0
    
    @rx.var
    def model_size_display(self) -> str:
        """Human-readable model size."""
        sizes = {"n": "Nano", "s": "Small", "m": "Medium", "l": "Large"}
        return sizes.get(self.model_size, "Nano")
    
    @rx.var
    def has_runs(self) -> bool:
        """Check if there are any training runs."""
        return len(self.training_runs) > 0
    
    @rx.var
    def filtered_runs(self) -> list[TrainingRunModel]:
        """Get filtered and sorted training runs for display."""
        runs = list(self.training_runs)
        
        # Filter by status
        if self.filter_status != "all":
            runs = [r for r in runs if r.status == self.filter_status]
        
        # Filter by tag
        if self.filter_tag != "all":
            runs = [r for r in runs if self.filter_tag in r.tags]
        
        # Filter by model type
        if self.filter_model_type != "all":
            runs = [r for r in runs if r.model_type == self.filter_model_type]
        
        # Filter by backbone (only applies to classification runs)
        if self.filter_backbone != "all":
            runs = [r for r in runs if r.config.get("classifier_backbone", "yolo") == self.filter_backbone]
        
        # Sort (already sorted by created_at from DB, just reverse if needed)
        # Note: training_runs are loaded newest first from load_dashboard
        if self.sort_ascending:
            runs = list(reversed(runs))
        
        return runs
    
    def set_sort_column(self, column: str):
        """Set sort column and toggle direction if same column."""
        if self.sort_column == column:
            self.sort_ascending = not self.sort_ascending
        else:
            self.sort_column = column
            self.sort_ascending = False  # Default to newest/highest first
    
    def set_filter_status(self, status: str):
        """Set status filter."""
        self.filter_status = status
    
    def set_filter_tag(self, tag: str):
        """Set tag filter."""
        self.filter_tag = tag
    
    def set_filter_model_type(self, model_type: str):
        """Set model type filter."""
        self.filter_model_type = model_type
    
    def set_filter_backbone(self, backbone: str):
        """Set backbone filter."""
        self.filter_backbone = backbone
    
    def clear_filters(self):
        """Reset all filters."""
        self.filter_status = "all"
        self.filter_tag = "all"
        self.filter_model_type = "all"
        self.filter_backbone = "all"
    
    # =========================================================================
    # Continue Training Methods
    # =========================================================================
    
    def toggle_continue_from_run(self, checked: bool):
        """Toggle the 'continue from existing run' checkbox."""
        self.continue_from_run = checked
        if not checked:
            self.selected_parent_run_id = ""
    
    def select_parent_run(self, run_id: str):
        """Select a run to continue training from."""
        self.selected_parent_run_id = run_id
    
    def is_run_class_compatible(self, run: TrainingRunModel) -> bool:
        """Check if a run's classes match the current project classes.
        
        Returns True if the run can be used as a parent for continued training.
        """
        if not run.classes:
            return False
        if run.status != "completed":
            return False
        # Run classes must exactly match current project classes
        return set(run.classes) == set(self.combined_classes)
    
    @rx.var
    def selected_parent_run(self) -> Optional[TrainingRunModel]:
        """Get the currently selected parent run."""
        for run in self.training_runs:
            if run.id == self.selected_parent_run_id:
                return run
        return None
    
    @rx.var
    def selected_parent_run_alias(self) -> str:
        """Get display name for selected parent run."""
        for run in self.training_runs:
            if run.id == self.selected_parent_run_id:
                return run.alias if run.alias else f"run_{run.id[:8]}"
        return ""
    


    @rx.var
    def has_datasets(self) -> bool:
        """Check if project has any datasets."""
        return len(self.datasets) > 0
    
    @rx.var
    def selected_count(self) -> int:
        """Number of selected datasets."""
        return len(self.selected_dataset_ids)
    
    @rx.var
    def labeled_percentage(self) -> int:
        """Percentage of labeled images across selected datasets."""
        if self.total_images_count == 0:
            return 0
        return int((self.total_labeled_count / self.total_images_count) * 100)
    
    @rx.var
    def has_selected_run(self) -> bool:
        """Check if a run is selected."""
        return self.selected_run_id != ""
    
    @rx.var
    def selected_run(self) -> Optional[TrainingRunModel]:
        """Get the selected training run."""
        for run in self.training_runs:
            if run.id == self.selected_run_id:
                return run
        return None
    
    @rx.var
    def selected_run_is_completed(self) -> bool:
        """Check if selected run is completed."""
        if not self.selected_run_id:
            return False
        for run in self.training_runs:
            if run.id == self.selected_run_id:
                return run.status == "completed"
        return False
    
    @rx.var
    def selected_run_is_active(self) -> bool:
        """Check if selected run is still active (pending/queued/running)."""
        if not self.selected_run_id:
            return False
        for run in self.training_runs:
            if run.id == self.selected_run_id:
                return run.status in ["pending", "queued", "running"]
        return False
    
    @rx.var
    def selected_run_backbone(self) -> str:
        """Get selected run's classifier backbone (yolo/convnext)."""
        if not self.selected_run_id:
            return ""
        for run in self.training_runs:
            if run.id == self.selected_run_id:
                return run.config.get("classifier_backbone", "yolo")
        return ""
    
    @rx.var
    def selected_run_is_convnext(self) -> bool:
        """Check if the selected run used ConvNeXt backbone."""
        return self.selected_run_backbone == "convnext"
    
    @rx.var
    def selected_run_is_sam3(self) -> bool:
        """Check if the selected run is a SAM3 fine-tuning run."""
        if not self.selected_run_id:
            return False
        for run in self.training_runs:
            if run.id == self.selected_run_id:
                return run.model_type == "sam3_finetune"
        return False
    
    def select_run(self, run_id: str):
        """Select a training run to view details."""
        if self.selected_run_id == run_id:
            self.selected_run_id = ""  # Toggle off if clicking same run
        else:
            self.selected_run_id = run_id
    
    def get_artifact_url(self, artifact_name: str) -> str:
        """Generate presigned URL for a training artifact."""
        for run in self.training_runs:
            if run.id == self.selected_run_id and run.artifacts_r2_prefix:
                r2 = R2Client()
                path = f"{run.artifacts_r2_prefix}/{artifact_name}"
                return r2.generate_presigned_url(path)
        return ""
    
    # =========================================================================
    # Run Metadata Properties & Editing
    # =========================================================================
    
    @rx.var
    def selected_run_alias(self) -> str:
        """Get alias for selected run, or short ID fallback."""
        for run in self.training_runs:
            if run.id == self.selected_run_id:
                return run.alias if run.alias else f"run_{run.id[:8]}"
        return ""
    
    @rx.var
    def selected_run_alias_raw(self) -> str:
        """Get raw alias for selected run (empty if not set)."""
        for run in self.training_runs:
            if run.id == self.selected_run_id:
                return run.alias or ""
        return ""
    
    @rx.var
    def selected_run_notes(self) -> str:
        """Get notes for selected run."""
        for run in self.training_runs:
            if run.id == self.selected_run_id:
                return run.notes or ""
        return ""
    
    @rx.var
    def selected_run_tags(self) -> list[str]:
        """Get tags for selected run."""
        for run in self.training_runs:
            if run.id == self.selected_run_id:
                return run.tags
        return []
    
    def start_editing_alias(self):
        """Start editing the alias for the selected run."""
        self.editing_alias = True
        self.temp_alias = self.selected_run_alias_raw
    
    def cancel_editing_alias(self):
        """Cancel alias editing."""
        self.editing_alias = False
        self.temp_alias = ""
    
    def set_temp_alias(self, value: str):
        """Update temp alias while editing."""
        self.temp_alias = value
    
    async def save_alias(self):
        """Save the alias to Supabase."""
        if not self.selected_run_id:
            return
        
        try:
            update_training_run(self.selected_run_id, alias=self.temp_alias if self.temp_alias else None)
            # Update local state
            for i, run in enumerate(self.training_runs):
                if run.id == self.selected_run_id:
                    self.training_runs[i] = TrainingRunModel(
                        **{**run.model_dump(), "alias": self.temp_alias if self.temp_alias else None}
                    )
                    break
            self.editing_alias = False
            self.temp_alias = ""
            yield rx.toast.success("Alias saved")
        except Exception as e:
            print(f"[Training] Error saving alias: {e}")
            yield rx.toast.error(f"Failed to save: {e}")

    async def handle_alias_keydown(self, key: str):
        """Handle Enter key in alias input."""
        if key == "Enter":
            async for event in self.save_alias():
                yield event

    async def handle_notes_keydown(self, key: str):
        """Handle Enter key in notes input."""
        if key == "Enter":
            async for event in self.save_notes():
                yield event

    async def handle_table_edit_keydown(self, key: str):
        """Handle Enter key in table inline edit."""
        if key == "Enter":
            async for event in self.save_table_edit():
                yield event

    async def handle_delete_run_keydown(self, key: str):
        """Handle Enter key in delete run confirmation."""
        if key == "Enter" and self.can_delete_run:
            async for event in self.confirm_delete_run():
                yield event

    
    def start_editing_notes(self):
        """Start editing the notes for the selected run."""
        self.editing_notes = True
        self.temp_notes = self.selected_run_notes
    
    def cancel_editing_notes(self):
        """Cancel notes editing."""
        self.editing_notes = False
        self.temp_notes = ""
    
    def set_temp_notes(self, value: str):
        """Update temp notes while editing."""
        self.temp_notes = value
    
    async def save_notes(self):
        """Save the notes to Supabase."""
        if not self.selected_run_id:
            return
        
        try:
            update_training_run(self.selected_run_id, notes=self.temp_notes if self.temp_notes else None)
            # Update local state
            for i, run in enumerate(self.training_runs):
                if run.id == self.selected_run_id:
                    self.training_runs[i] = TrainingRunModel(
                        **{**run.model_dump(), "notes": self.temp_notes if self.temp_notes else None}
                    )
                    break
            self.editing_notes = False
            self.temp_notes = ""
            yield rx.toast.success("Notes saved")
        except Exception as e:
            print(f"[Training] Error saving notes: {e}")
            yield rx.toast.error(f"Failed to save: {e}")
    
    async def toggle_tag(self, tag: str):
        """Toggle a tag on/off for the selected run."""
        if not self.selected_run_id:
            return
        
        current_tags = list(self.selected_run_tags)
        if tag in current_tags:
            current_tags.remove(tag)
        else:
            current_tags.append(tag)
        
        try:
            update_training_run(self.selected_run_id, tags=current_tags)
            # Update local state
            for i, run in enumerate(self.training_runs):
                if run.id == self.selected_run_id:
                    self.training_runs[i] = TrainingRunModel(
                        **{**run.model_dump(), "tags": current_tags}
                    )
                    break
        except Exception as e:
            print(f"[Training] Error updating tags: {e}")
            yield rx.toast.error(f"Failed to update tags: {e}")
    
    # =========================================================================
    # Inline Table Editing (Dashboard History Table)
    # =========================================================================
    
    def start_table_edit(self, run_id: str, field: str):
        """Start editing alias or notes inline in the table."""
        # Find the current value
        current_value = ""
        for run in self.training_runs:
            if run.id == run_id:
                if field == "alias":
                    current_value = run.alias or ""
                elif field == "notes":
                    current_value = run.notes or ""
                break
        
        self.table_editing_run_id = run_id
        self.table_editing_field = field
        self.table_temp_value = current_value
    
    def cancel_table_edit(self):
        """Cancel inline table editing."""
        self.table_editing_run_id = ""
        self.table_editing_field = ""
        self.table_temp_value = ""
    
    def set_table_temp_value(self, value: str):
        """Update temp value while editing in table."""
        self.table_temp_value = value
    
    async def save_table_edit(self):
        """Save the inline table edit."""
        if not self.table_editing_run_id or not self.table_editing_field:
            return
        
        try:
            run_id = self.table_editing_run_id
            field = self.table_editing_field
            value = self.table_temp_value if self.table_temp_value else None
            
            # Update in Supabase
            if field == "alias":
                update_training_run(run_id, alias=value)
            elif field == "notes":
                update_training_run(run_id, notes=value)
            
            # Update local state
            for i, run in enumerate(self.training_runs):
                if run.id == run_id:
                    updated_data = run.model_dump()
                    updated_data[field] = value
                    self.training_runs[i] = TrainingRunModel(**updated_data)
                    break
            
            # Clear editing state
            self.table_editing_run_id = ""
            self.table_editing_field = ""
            self.table_temp_value = ""
            
            yield rx.toast.success(f"{field.capitalize()} updated")
        except Exception as e:
            print(f"[Training] Error saving table edit: {e}")
            yield rx.toast.error(f"Failed to save: {e}")
    
    @rx.var
    def is_editing_table(self) -> bool:
        """Check if currently editing in the table."""
        return self.table_editing_run_id != ""
    
    # =========================================================================
    # Delete Training Run
    # =========================================================================
    
    def open_delete_modal(self, run_id: str):
        """Open the delete confirmation modal for a training run."""
        self.show_delete_modal = True
        self.delete_run_id = run_id
        self.delete_confirmation = ""
    
    def close_delete_modal(self):
        """Close the delete modal and reset state."""
        self.show_delete_modal = False
        self.delete_run_id = ""
        self.delete_confirmation = ""
    
    def set_delete_confirmation(self, value: str):
        """Update the confirmation input."""
        self.delete_confirmation = value
    
    @rx.var
    def can_delete_run(self) -> bool:
        """Check if delete confirmation is valid."""
        return self.delete_confirmation.lower() == "delete"
    
    async def confirm_delete_run(self):
        """Delete the training run from Supabase and R2."""
        if not self.can_delete_run or not self.delete_run_id:
            return
        
        self.is_deleting = True
        yield
        
        try:
            # Get run to find artifacts prefix
            deleted_run = db_delete_training_run(self.delete_run_id)
            
            if deleted_run:
                # Clean up R2 artifacts if they exist
                artifacts_prefix = deleted_run.get("artifacts_r2_prefix")
                if artifacts_prefix:
                    try:
                        r2 = R2Client()
                        r2.delete_files_with_prefix(artifacts_prefix)
                        print(f"[Training] Deleted R2 artifacts at {artifacts_prefix}")
                    except Exception as e:
                        print(f"[Training] Failed to delete R2 artifacts: {e}")
                
                # Clean up SAM3 checkpoint from Modal volume if present
                run_metrics = deleted_run.get("metrics") or {}
                checkpoint_path = run_metrics.get("modal_checkpoint_path")
                if checkpoint_path:
                    try:
                        delete_fn = modal.Function.from_name(
                            "sam3-training", "delete_sam3_checkpoint"
                        )
                        deleted = delete_fn.remote(volume_path=checkpoint_path)
                        if deleted:
                            print(f"[Training] Deleted SAM3 checkpoint: {checkpoint_path}")
                        else:
                            print(f"[Training] SAM3 checkpoint not found: {checkpoint_path}")
                    except Exception as e:
                        print(f"[Training] Failed to delete SAM3 checkpoint: {e}")
                
                yield rx.toast.success("Training run deleted")
            else:
                yield rx.toast.error("Failed to delete training run")
            
            # Close modal and refresh
            self.show_delete_modal = False
            self.delete_run_id = ""
            self.delete_confirmation = ""
            
            # Clear selection if deleted run was selected
            if self.selected_run_id == self.delete_run_id:
                self.selected_run_id = ""
            
            # Refresh the run list
            yield TrainingState.refresh_run_history
            
        except Exception as e:
            print(f"[Training] Error deleting run: {e}")
            yield rx.toast.error(f"Delete failed: {str(e)}")
        finally:
            self.is_deleting = False
    
    # =========================================================================
    # API Model Promotion (Phase A1)
    # =========================================================================
    
    def open_api_promote_modal(self, run_id: str):
        """Open the API promotion modal for a completed training run."""
        self.show_api_promote_modal = True
        self.api_promote_run_id = run_id
        self.api_promoting = False
        
        # Auto-generate a suggested slug from the run's alias or ID
        for run in self.training_runs:
            if run.id == run_id:
                if run.alias:
                    # Convert alias to slug: lowercase, replace spaces with hyphens
                    suggested = run.alias.lower().replace(" ", "-")
                    # Remove any non-alphanumeric chars except hyphens
                    import re
                    suggested = re.sub(r'[^a-z0-9\-]', '', suggested)
                    self.api_slug = suggested
                    self.api_display_name = run.alias
                else:
                    self.api_slug = f"model-{run_id[:8]}"
                    self.api_display_name = f"Model {run_id[:8]}"
                break
        
        self.api_description = ""
    
    def close_api_promote_modal(self):
        """Close the API promotion modal and reset state."""
        self.show_api_promote_modal = False
        self.api_promote_run_id = ""
        self.api_slug = ""
        self.api_display_name = ""
        self.api_description = ""
        self.api_promoting = False
    
    def set_api_slug(self, value: str):
        """Update the API slug (sanitized to URL-safe)."""
        import re
        # Only allow lowercase letters, numbers, and hyphens
        sanitized = re.sub(r'[^a-z0-9\-]', '', value.lower())
        self.api_slug = sanitized
    
    def set_api_display_name(self, value: str):
        """Update the API display name."""
        self.api_display_name = value
    
    def set_api_description(self, value: str):
        """Update the API description."""
        self.api_description = value
    
    @rx.var
    def can_promote_to_api(self) -> bool:
        """Check if the promotion form is valid."""
        return (
            len(self.api_slug) >= 3 and
            len(self.api_display_name) >= 1 and
            not self.api_promoting
        )
    
    @rx.var
    def suggested_api_slug(self) -> str:
        """Get suggested slug based on current promote run."""
        for run in self.training_runs:
            if run.id == self.api_promote_run_id and run.alias:
                import re
                suggested = run.alias.lower().replace(" ", "-")
                return re.sub(r'[^a-z0-9\-]', '', suggested)
        return ""
    
    async def promote_run_to_api(self):
        """Promote the selected training run to the API registry."""
        if not self.can_promote_to_api or not self.api_promote_run_id:
            return
        
        self.api_promoting = True
        yield
        
        try:
            api_model = promote_model_to_api(
                training_run_id=self.api_promote_run_id,
                slug=self.api_slug,
                display_name=self.api_display_name,
                description=self.api_description,
            )
            
            if api_model:
                yield rx.toast.success(
                    f"Model promoted to API as '{self.api_slug}'",
                    duration=5000,
                )
                self.close_api_promote_modal()
            else:
                yield rx.toast.error("Failed to promote model to API")
                
        except ValueError as e:
            # Validation errors from the backend
            yield rx.toast.error(str(e))
        except Exception as e:
            print(f"[Training] Error promoting to API: {e}")
            yield rx.toast.error(f"Promotion failed: {str(e)}")
        finally:
            self.api_promoting = False
    
    # =========================================================================
    # Selected Run Computed Properties (for UI display)
    # =========================================================================
    
    @rx.var
    def selected_run_metrics(self) -> dict:
        """Get metrics for selected run."""
        for run in self.training_runs:
            if run.id == self.selected_run_id and run.metrics:
                return run.metrics
        return {}
    
    @rx.var
    def selected_run_logs(self) -> str:
        """Get logs for selected run."""
        for run in self.training_runs:
            if run.id == self.selected_run_id and run.logs:
                return run.logs
        return "No logs available."
    
    @rx.var
    def selected_run_config(self) -> dict:
        """Get config for selected run."""
        for run in self.training_runs:
            if run.id == self.selected_run_id:
                return run.config
        return {}
    
    @rx.var
    def selected_run_error(self) -> str:
        """Get error message for selected run."""
        for run in self.training_runs:
            if run.id == self.selected_run_id and run.error_message:
                return run.error_message
        return ""
    
    @rx.var
    def best_pt_url(self) -> str:
        """Presigned URL for best.pt weights."""
        return self.get_artifact_url("best.pt")
    
    @rx.var
    def last_pt_url(self) -> str:
        """Presigned URL for last.pt weights."""
        return self.get_artifact_url("last.pt")
    
    @rx.var
    def results_png_url(self) -> str:
        """Presigned URL for results.png."""
        return self.get_artifact_url("results.png")
    
    @rx.var
    def confusion_matrix_url(self) -> str:
        """Presigned URL for confusion_matrix.png."""
        return self.get_artifact_url("confusion_matrix.png")
    
    @rx.var
    def f1_curve_url(self) -> str:
        """Presigned URL for F1_curve.png."""
        return self.get_artifact_url("F1_curve.png")
    
    @rx.var
    def pr_curve_url(self) -> str:
        """Presigned URL for PR_curve.png."""
        return self.get_artifact_url("PR_curve.png")
    
    @rx.var
    def labels_jpg_url(self) -> str:
        """Presigned URL for labels.jpg (label distribution plot)."""
        return self.get_artifact_url("labels.jpg")
    
    @rx.var
    def train_batch0_url(self) -> str:
        """Presigned URL for train_batch0.jpg."""
        return self.get_artifact_url("train_batch0.jpg")
    
    @rx.var
    def train_batch1_url(self) -> str:
        """Presigned URL for train_batch1.jpg."""
        return self.get_artifact_url("train_batch1.jpg")
    
    @rx.var
    def train_batch2_url(self) -> str:
        """Presigned URL for train_batch2.jpg."""
        return self.get_artifact_url("train_batch2.jpg")
    
    @rx.var
    def confusion_matrix_normalized_url(self) -> str:
        """Presigned URL for confusion_matrix_normalized.png."""
        return self.get_artifact_url("confusion_matrix_normalized.png")
    
    @rx.var
    def val_batch_labels_url(self) -> str:
        """Presigned URL for val_batch0_labels.jpg (ground truth)."""
        return self.get_artifact_url("val_batch0_labels.jpg")
    
    @rx.var
    def val_batch_pred_url(self) -> str:
        """Presigned URL for val_batch0_pred.jpg (predictions)."""
        return self.get_artifact_url("val_batch0_pred.jpg")
    
    @rx.var
    def latest_run_logs(self) -> str:
        """Get logs for the latest (first) training run."""
        if self.training_runs:
            logs = self.training_runs[0].logs
            return logs if logs else "Waiting for logs..."
        return "No training runs yet."
    
    @rx.var
    def latest_run_is_active(self) -> bool:
        """Check if latest run is still active."""
        if self.training_runs:
            return self.training_runs[0].status in ["pending", "queued", "running"]
        return False
    
    # Results CSV data for charts
    results_csv_data: list[dict] = []
    
    # Confusion matrix data for ConvNeXt (fetched from confusion_matrix.json)
    confusion_matrix_data: list[list[int]] = []
    confusion_matrix_classes: list[str] = []
    
    # =========================================================================
    # Enhanced Metrics & Chart Data (Priority 1-3)
    # =========================================================================
    
    @rx.var
    def f1_score(self) -> float:
        """Calculate F1 score from final precision and recall."""
        metrics = self.selected_run_metrics
        precision = metrics.get("precision", 0)
        recall = metrics.get("recall", 0)
        
        if precision + recall == 0:
            return 0.0
        
        return 2 * (precision * recall) / (precision + recall)
    
    @rx.var
    def best_epoch(self) -> int:
        """Find epoch with best metric (mAP@50-95 for detection, accuracy_top1 for classification)."""
        if not self.results_csv_data:
            return 0
        
        # Determine which metric to use based on model type
        selected_run = None
        for run in self.training_runs:
            if run.id == self.selected_run_id:
                selected_run = run
                break
        
        is_classification = selected_run and selected_run.model_type == "classification"
        metric_key = "metrics/accuracy_top1" if is_classification else "metrics/mAP50-95(B)"
        
        best_epoch_num = 0
        best_value = 0.0
        
        for row in self.results_csv_data:
            try:
                metric_value = float(row.get(metric_key, 0))
                epoch = int(float(row.get("epoch", 0)))
                if metric_value > best_value:
                    best_value = metric_value
                    best_epoch_num = epoch
            except (ValueError, TypeError):
                continue
        
        return best_epoch_num
    
    @rx.var
    def training_duration(self) -> str:
        """Format total training duration from metrics."""
        metrics = self.selected_run_metrics
        total_time = metrics.get("total_training_time")
        
        if total_time:
            hours = int(total_time // 3600)
            minutes = int((total_time % 3600) // 60)
            seconds = int(total_time % 60)
            
            if hours > 0:
                return f"{hours}h {minutes}m"
            elif minutes > 0:
                return f"{minutes}m {seconds}s"
            else:
                return f"{seconds}s"
        
        # Fallback: calculate from results.csv if available
        if self.results_csv_data:
            try:
                last_row = self.results_csv_data[-1]
                time_val = float(last_row.get("time", 0))
                minutes = int(time_val // 60)
                seconds = int(time_val % 60)
                return f"{minutes}m {seconds}s"
            except (ValueError, TypeError, IndexError):
                pass
        
        return "N/A"
    
    @rx.var
    def avg_epoch_time(self) -> str:
        """Calculate average time per epoch."""
        if not self.results_csv_data or len(self.results_csv_data) == 0:
            return "N/A"
        
        try:
            total_time = float(self.results_csv_data[-1].get("time", 0))
            num_epochs = len(self.results_csv_data)
            avg = total_time / num_epochs if num_epochs > 0 else 0
            
            if avg >= 60:
                minutes = int(avg // 60)
                seconds = int(avg % 60)
                return f"{minutes}m {seconds}s"
            else:
                return f"{int(avg)}s"
        except (ValueError, TypeError, IndexError):
            return "N/A"
    
    @rx.var
    def f1_scores_data(self) -> list:
        """Calculate F1 scores from precision/recall for each epoch."""
        if not self.results_csv_data:
            return []
        
        data = []
        for row in self.results_csv_data:
            try:
                precision = float(row.get("metrics/precision(B)", 0))
                recall = float(row.get("metrics/recall(B)", 0))
                epoch = int(float(row.get("epoch", 0)))
                
                if precision + recall > 0:
                    f1 = 2 * (precision * recall) / (precision + recall)
                else:
                    f1 = 0.0
                
                data.append({
                    "epoch": epoch,
                    "f1_score": f1
                })
            except (ValueError, TypeError):
                continue
        
        return data
    
    @rx.var
    def learning_rate_data(self) -> list:
        """Extract learning rate schedule from results_csv."""
        if not self.results_csv_data:
            return []
        
        data = []
        for row in self.results_csv_data:
            try:
                epoch = int(float(row.get("epoch", 0)))
                # YOLO uses different column names: x/lr0, x/lr1, x/lr2, lr/pg0, lr/pg1, lr/pg2
                lr0 = row.get("x/lr0") or row.get("lr/pg0") or row.get("lr0") or row.get("lr")
                
                if lr0 is not None and lr0 != "":
                    lr_value = float(lr0)
                    data.append({
                        "epoch": epoch,
                        "learning_rate": lr_value
                    })
            except (ValueError, TypeError):
                continue
        
        return data
    
    @rx.var
    def epoch_improvements_data(self) -> list:
        """Calculate delta from previous epoch for key metrics."""
        if not self.results_csv_data or len(self.results_csv_data) < 2:
            return []
        
        data = []
        metrics_to_track = ["metrics/mAP50-95(B)", "metrics/mAP50(B)", "metrics/precision(B)", "metrics/recall(B)"]
        
        for i in range(1, len(self.results_csv_data)):
            prev_row = self.results_csv_data[i-1]
            curr_row = self.results_csv_data[i]
            
            try:
                epoch = float(curr_row.get("epoch", 0))
                row_data = {"epoch": epoch}
                
                for metric in metrics_to_track:
                    prev_val = float(prev_row.get(metric, 0))
                    curr_val = float(curr_row.get(metric, 0))
                    delta = curr_val - prev_val
                    
                    # Simplify metric name for display
                    display_name = metric.replace("metrics/", "").replace("(B)", "")
                    row_data[f"delta_{display_name}"] = delta
                
                data.append(row_data)
            except (ValueError, TypeError):
                continue
        
        return data
    
    @rx.var
    def train_val_loss_data(self) -> list:
        """Process train vs validation loss for comparison chart."""
        if not self.results_csv_data:
            return []
        
        data = []
        for row in self.results_csv_data:
            try:
                epoch = float(row.get("epoch", 0))
                
                # Training losses
                train_box = float(row.get("train/box_loss", 0))
                train_cls = float(row.get("train/cls_loss", 0))
                train_dfl = float(row.get("train/dfl_loss", 0))
                
                # Validation losses
                val_box = float(row.get("val/box_loss", 0))
                val_cls = float(row.get("val/cls_loss", 0))
                val_dfl = float(row.get("val/dfl_loss", 0))
                
                data.append({
                    "epoch": epoch,
                    "train_box_loss": train_box,
                    "val_box_loss": val_box,
                    "train_cls_loss": train_cls,
                    "val_cls_loss": val_cls,
                    "train_dfl_loss": train_dfl,
                    "val_dfl_loss": val_dfl,
                })
            except (ValueError, TypeError):
                continue
        
        return data
    
    @rx.var
    def loss_components_data(self) -> list:
        """Extract loss components for stacked area chart."""
        if not self.results_csv_data:
            return []
        
        data = []
        for row in self.results_csv_data:
            try:
                epoch = float(row.get("epoch", 0))
                box_loss = float(row.get("train/box_loss", 0))
                cls_loss = float(row.get("train/cls_loss", 0))
                dfl_loss = float(row.get("train/dfl_loss", 0))
                
                data.append({
                    "epoch": epoch,
                    "box_loss": box_loss,
                    "cls_loss": cls_loss,
                    "dfl_loss": dfl_loss,
                })
            except (ValueError, TypeError):
                continue
        
        return data
    
    @rx.var
    def training_efficiency_data(self) -> list:
        """Calculate time per epoch for efficiency tracking."""
        if not self.results_csv_data:
            return []
        
        data = []
        prev_time = 0
        
        for i, row in enumerate(self.results_csv_data):
            try:
                epoch = float(row.get("epoch", 0))
                total_time = float(row.get("time", 0))
                
                # Time for this specific epoch
                epoch_time = total_time - prev_time if i > 0 else total_time
                prev_time = total_time
                
                data.append({
                    "epoch": epoch,
                    "epoch_time": epoch_time,  # in seconds
                })
            except (ValueError, TypeError):
                continue
        
        return data
    
    # =========================================================================
    # Load Run Detail
    # =========================================================================

    async def load_run_detail(self):
        """Load a single training run for the detail page."""
        async with self:
            run_id = self.router.page.params.get("run_id", "")
            project_id = self.router.page.params.get("project_id", "")
            
        if not run_id or not project_id:
            return
        
        # Load project name
        project = get_project(project_id)
        project_name = ""
        if project:
            project_name = project.get("name", "")
        
        # Load the specific run
        from backend.supabase_client import get_training_run
        run_data = get_training_run(run_id)
        
        if not run_data:
            return
        
        run = TrainingRunModel(
            id=str(run_data.get("id", "")),
            status=str(run_data.get("status", "pending")),
            target=str(run_data.get("target", "cloud")),
            config=run_data.get("config", {}),
            metrics=run_data.get("metrics"),
            artifacts_r2_prefix=run_data.get("artifacts_r2_prefix"),
            dataset_ids=run_data.get("dataset_ids", []) or [],
            dataset_names=run_data.get("dataset_names", []) or [],
            created_at=run_data.get("created_at", "").split(".")[0].replace("T", " "),
            started_at=run_data.get("started_at"),
            completed_at=run_data.get("completed_at"),
            error_message=run_data.get("error_message"),
            logs=run_data.get("logs"),
            alias=run_data.get("alias"),
            notes=run_data.get("notes"),
            tags=run_data.get("tags", []) or [],
            classes=run_data.get("classes_snapshot", []) or run_data.get("config", {}).get("classes", []) or [],
            model_type=run_data.get("model_type", "detection"),
        )
        
        async with self:
            self.current_project_id = project_id
            self.project_name = project_name
            self.selected_run_id = run_id
            self.training_runs = [run]  # Put in list so computed properties work
        
        # Fetch results.csv for charts if completed
        if run.status == "completed" and run.artifacts_r2_prefix:
            await self._fetch_results_csv(run.artifacts_r2_prefix)
            # Fetch confusion matrix for ConvNeXt runs
            if run.config.get("classifier_backbone") == "convnext":
                await self._fetch_confusion_matrix(run.artifacts_r2_prefix)
    
    async def _fetch_results_csv(self, prefix: str):
        """Fetch and parse results.csv from R2."""
        import csv
        from io import StringIO
        
        try:
            r2 = R2Client()
            csv_path = f"{prefix}/results.csv"
            csv_bytes = r2.download_file(csv_path)
            
            if csv_bytes:
                csv_text = csv_bytes.decode('utf-8')
                reader = csv.DictReader(StringIO(csv_text))
                data = []
                for row in reader:
                    # Clean up column names and convert numeric values
                    cleaned = {}
                    for k, v in row.items():
                        key = k.strip()
                        val = v.strip()
                        # Try to convert to float for chart rendering
                        try:
                            cleaned[key] = float(val)
                        except (ValueError, TypeError):
                            cleaned[key] = val
                    data.append(cleaned)
                
                async with self:
                    self.results_csv_data = data
        except Exception as e:
            print(f"[DEBUG] Failed to fetch results.csv: {e}")
    
    async def _fetch_confusion_matrix(self, prefix: str):
        """Fetch and parse confusion_matrix.json from R2 for ConvNeXt runs."""
        import json as json_mod
        
        try:
            r2 = R2Client()
            json_path = f"{prefix}/confusion_matrix.json"
            json_bytes = r2.download_file(json_path)
            
            if json_bytes:
                cm = json_mod.loads(json_bytes.decode('utf-8'))
                async with self:
                    self.confusion_matrix_data = cm.get("matrix", [])
                    self.confusion_matrix_classes = cm.get("classes", [])
                print(f"[DEBUG] Loaded confusion matrix: {len(self.confusion_matrix_classes)} classes")
        except Exception as e:
            print(f"[DEBUG] Failed to fetch confusion_matrix.json: {e}")


    @rx.event(background=True)
    async def dispatch_training(self):
        """Unified training dispatcher - routes to correct handler based on training_mode."""
        async with self:
            mode = self.training_mode
        
        if mode == "sam3_finetune":
            yield TrainingState.start_sam3_training()
        elif mode == "classification":
            yield TrainingState.start_classification_training()
        else:
            yield TrainingState.start_training()

    @rx.event(background=True)
    async def start_training(self):
        """Launch the training process."""
        async with self:
            if not self.total_labeled_count:
                return

            self.is_starting = True
            self.start_error = ""
            # Reset polling flag to ensure fresh poll starts after dispatch
            self.is_polling = False
            # Capture state for background execution
            epochs = self.epochs
            model_size = self.model_size
            batch_size = self.batch_size
            target = self.compute_target
            machine_name = self.selected_machine if target == "local" else None
            selected_ids = self.selected_dataset_ids
            datasets = self.datasets
            project_id = self.current_project_id
            # Advanced settings
            patience = self.patience
            optimizer = self.optimizer
            lr0 = self.lr0
            lrf = self.lrf
            train_split_percentage = self.train_split_percentage  # NEW
            
            # Continue training settings
            continue_from_run = self.continue_from_run
            parent_run_id = self.selected_parent_run_id if continue_from_run else None
            parent_run = self.selected_parent_run if continue_from_run else None
            
            # Get user context safely
            auth_state = await self.get_state(AuthState)
            user_id = auth_state.user.get("id") if auth_state.user else None
        yield

        try:
            if not user_id:
                raise Exception("User not authenticated")

            # 2. Aggregated data containers
            image_urls = {}  # Training images
            label_urls = {}  # Training labels
            val_image_urls = {}  # NEW: Validation images
            val_label_urls = {}  # NEW: Validation labels
            all_classes = set()
            dataset_name_list = []  # Snapshot of dataset names
            
            # NEW: Separate datasets by usage tag
            train_dataset_ids = []
            val_dataset_ids = []
            for dataset_id in selected_ids:
                dataset = next((d for d in datasets if d.id == dataset_id), None)
                if dataset:
                    if dataset.usage_tag == "validation":
                        val_dataset_ids.append(dataset_id)
                    else:
                        train_dataset_ids.append(dataset_id)
            
            print(f"[Training] Train datasets: {len(train_dataset_ids)}, Val datasets: {len(val_dataset_ids)}")

            r2 = R2Client()
            
            # 2b. First gather dataset names
            from backend.supabase_client import get_dataset, get_project
            for dataset_id in selected_ids:
                dataset = next((d for d in datasets if d.id == dataset_id), None)
                if dataset:
                    dataset_name_list.append(dataset.name)
            
            # Get classes from PROJECT (not datasets - classes are project-level)
            project_data = get_project(project_id)
            if project_data and project_data.get("classes"):
                all_classes.update(project_data["classes"])
            
            print(f"[Training] Using {len(all_classes)} classes from project: {sorted(all_classes)}")

            # 3. Create training run in Supabase (status='pending')
            # Store classes as sorted list for consistent ordering
            classes_snapshot = sorted(list(all_classes))
            
            config = {
                "epochs": epochs,
                "model_size": model_size,
                "batch_size": batch_size,
                # Advanced settings
                "patience": patience,
                "optimizer": optimizer,
                "lr0": lr0,
                "lrf": lrf,
                "classes": classes_snapshot,  # Store classes in config for legacy support
            }
            
            run = create_training_run(
                project_id=project_id,
                dataset_ids=selected_ids,
                user_id=user_id,
                config=config,
                target=target,
                dataset_names=dataset_name_list,
                classes_snapshot=classes_snapshot,
            )
            
            if not run:
                raise Exception("Failed to create training run in database")
            
            run_id = run["id"]

            # 4. Gather image/label data from all selected datasets
            for dataset_id in selected_ids:
                dataset = next((d for d in datasets if d.id == dataset_id), None)
                if not dataset: continue

                if dataset.type == "video":
                    # For videos, we use keyframes at full resolution
                    from backend.frame_extractor import extract_and_store_full_frame
                    from backend.supabase_client import update_keyframe
                    
                    videos = get_dataset_videos(dataset_id)
                    for v in videos:
                        keyframes = get_video_keyframes(v["id"])
                        video_fps = v.get("fps") or 30.0
                        
                        for kf in keyframes:
                            # Prefer full-res image, fall back to thumbnail
                            kf_path = kf.get("full_image_path") or kf.get("thumbnail_path")
                            
                            # If no full-res exists, extract it now
                            if not kf.get("full_image_path"):
                                print(f"[Training] Extracting full-res frame {kf['frame_number']} from video {v['id']}...")
                                full_path = extract_and_store_full_frame(
                                    video_r2_path=v["r2_path"],
                                    frame_number=kf["frame_number"],
                                    fps=video_fps,
                                    dataset_id=dataset_id,
                                    video_id=v["id"]
                                )
                                if full_path:
                                    kf_path = full_path
                                    # Update DB for future use
                                    update_keyframe(kf["id"], full_image_path=full_path)
                                    print(f"[Training] Stored full-res frame at {full_path}")
                            
                            if not kf_path:
                                print(f"[System] Skipping keyframe {kf.get('id')} (frame {kf.get('frame_number')}): No image path")
                                continue
                            
                            # keyframe filename format: {video_id}_f{frame_number}.jpg
                            kf_filename = f"{v['id']}_f{kf['frame_number']}.jpg"
                            
                            try:
                                img_url = r2.generate_presigned_url(kf_path)
                                # Route to correct dictionary based on dataset usage tag
                                if dataset.usage_tag == "validation":
                                    val_image_urls[kf_filename] = img_url
                                else:
                                    image_urls[kf_filename] = img_url
                            except Exception as e:
                                print(f"[System] Error generating URL for {kf_path}: {e}")
                                continue
                            
                            # Always include label URL - empty files exist for unlabeled keyframes
                            lbl_filename = f"{kf_filename.rsplit('.', 1)[0]}.txt"
                            lbl_path = f"datasets/{dataset_id}/labels/{v['id']}_f{kf['frame_number']}.txt"
                            try:
                                lbl_url = r2.generate_presigned_url(lbl_path)
                                # Route to correct dictionary based on dataset usage tag
                                if dataset.usage_tag == "validation":
                                    val_label_urls[lbl_filename] = lbl_url
                                else:
                                    label_urls[lbl_filename] = lbl_url
                            except Exception as e:
                                print(f"[System] Error generating label URL for {lbl_path}: {e}")
                else:
                    # For images
                    images = get_dataset_images(dataset_id)
                    for img in images:
                        if not img.get("labeled"): continue
                        
                        img_url = r2.generate_presigned_url(img["r2_path"])
                        # Route to correct dictionary based on dataset usage tag
                        if dataset.usage_tag == "validation":
                            val_image_urls[img["filename"]] = img_url
                        else:
                            image_urls[img["filename"]] = img_url
                        
                        # Label filename must match image filename
                        lbl_filename = f"{img['filename'].rsplit('.', 1)[0]}.txt"
                        # Label in R2 is stored at datasets/{dataset_id}/labels/{image_id}.txt
                        lbl_path = f"datasets/{dataset_id}/labels/{img['id']}.txt"
                        lbl_url = r2.generate_presigned_url(lbl_path)
                        # Route to correct dictionary based on dataset usage tag
                        if dataset.usage_tag == "validation":
                            val_label_urls[lbl_filename] = lbl_url
                        else:
                            label_urls[lbl_filename] = lbl_url

            # 5. Dispatch training job (routes to Modal or Local GPU)
            try:
                # Determine base weights path if continuing from existing run
                base_weights_r2_path = None
                if continue_from_run and parent_run and parent_run.artifacts_r2_prefix:
                    base_weights_r2_path = f"{parent_run.artifacts_r2_prefix}/best.pt"
                    print(f"[Training] Continuing from run {parent_run_id}, weights: {base_weights_r2_path}")
                
                from backend.job_router import dispatch_training_job
                dispatch_training_job(
                    project_id=project_id,
                    run_id=run_id,
                    dataset_ids=selected_ids,
                    image_urls=image_urls,
                    label_urls=label_urls,
                    classes=sorted(list(all_classes)),
                    config=config,
                    train_split_ratio=train_split_percentage / 100,
                    val_image_urls=val_image_urls if val_dataset_ids else None,
                    val_label_urls=val_label_urls if val_dataset_ids else None,
                    base_weights_r2_path=base_weights_r2_path,
                    parent_run_id=parent_run_id,
                    # Action-level target selection
                    target=target,
                    user_id=user_id,
                    machine_name=machine_name,
                )
            except Exception as e:
                # Fallback to failed status if job dispatch fails
                from backend.supabase_client import update_training_run
                update_training_run(run_id, status="failed", error_message=f"Job dispatch failed: {str(e)}")
                raise e

            # Success toast/feedback (simulated by refreshing runs)
            async with self:
                self.is_starting = False
                # Reload history
            yield TrainingState.load_dashboard()
            # Polling will be triggered by load_dashboard return value if cloud run is active

        except Exception as e:
            print(f"[DEBUG] Error starting training: {e}")
            async with self:
                self.is_starting = False
                self.start_error = str(e)
            yield rx.toast.error(f"Failed to start training: {str(e)}")

    @rx.event(background=True)
    async def start_classification_training(self):
        """Launch classification training process.
        
        Unlike detection training, this:
        1. Gathers annotation data (bounding boxes) instead of label files
        2. Calls the classification Modal job which crops images
        3. Uses classification-specific config (image_size)
        """
        async with self:
            if not self.total_labeled_count:
                return

            self.is_starting = True
            self.start_error = ""
            # Reset polling flag to ensure fresh poll starts after dispatch
            self.is_polling = False
            # Capture state for background execution
            epochs = self.epochs
            model_size = self.model_size
            classify_batch_size = self.classify_batch_size
            classify_image_size = self.classify_image_size
            target = self.compute_target
            machine_name = self.selected_machine if target == "local" else None
            selected_ids = self.selected_dataset_ids
            datasets = self.datasets
            project_id = self.current_project_id
            # Advanced settings
            patience = self.patience
            optimizer = self.optimizer
            # Use backbone-specific learning rate
            classifier_backbone = self.classifier_backbone
            if classifier_backbone == "convnext":
                lr0 = self.convnext_lr0  # ConvNeXt uses smaller LR
            else:
                lr0 = self.lr0  # YOLO LR
            lrf = self.lrf
            train_split_percentage = self.train_split_percentage
            
            # Get user context safely
            auth_state = await self.get_state(AuthState)
            user_id = auth_state.user.get("id") if auth_state.user else None
        yield

        try:
            if not user_id:
                raise Exception("User not authenticated")

            # Data containers
            image_urls = {}      # {filename: presigned_url}
            annotations = {}     # {filename: [{class_name, x, y, width, height}, ...]}
            val_image_urls = {}
            val_annotations = {}
            all_classes = set()
            dataset_name_list = []
            
            # Separate datasets by usage tag
            train_dataset_ids = []
            val_dataset_ids = []
            for dataset_id in selected_ids:
                dataset = next((d for d in datasets if d.id == dataset_id), None)
                if dataset:
                    if dataset.usage_tag == "validation":
                        val_dataset_ids.append(dataset_id)
                    else:
                        train_dataset_ids.append(dataset_id)
            
            print(f"[Classification] Train datasets: {len(train_dataset_ids)}, Val datasets: {len(val_dataset_ids)}")

            r2 = R2Client()
            
            # Gather dataset names
            for dataset_id in selected_ids:
                dataset = next((d for d in datasets if d.id == dataset_id), None)
                if dataset:
                    dataset_name_list.append(dataset.name)
            
            # Get classes from PROJECT (preserves insertion order for class_id resolution)
            from backend.supabase_client import get_project
            project_data = get_project(project_id)
            project_classes = project_data.get("classes", []) if project_data else []
            all_classes.update(project_classes)
            
            print(f"[Classification] Using {len(all_classes)} classes from project: {project_classes}")
            classes_snapshot = sorted(list(all_classes))  # Sorted for display/config
            
            # Create class_id → class_name lookup (class_id is 0-indexed based on project.classes order)
            class_id_to_name = {i: name for i, name in enumerate(project_classes)}

            # Create training run in Supabase
            config = {
                "epochs": epochs,
                "model_size": model_size,
                "batch_size": classify_batch_size,
                "image_size": classify_image_size,
                "patience": patience,
                "optimizer": optimizer,
                "lr0": lr0,
                "lrf": lrf,
                "classes": classes_snapshot,
                "classifier_backbone": self.classifier_backbone,
                "convnext_model_size": self.convnext_model_size,
                "convnext_lr0": self.convnext_lr0,
                "convnext_weight_decay": self.convnext_weight_decay,
            }
            
            run = create_training_run(
                project_id=project_id,
                dataset_ids=selected_ids,
                user_id=user_id,
                config=config,
                target=target,
                dataset_names=dataset_name_list,
                classes_snapshot=classes_snapshot,
                model_type="classification",  # NEW: Mark as classification
            )
            
            if not run:
                raise Exception("Failed to create training run in database")
            
            run_id = run["id"]

            # Gather image URLs and annotations from all selected datasets
            for dataset_id in selected_ids:
                dataset = next((d for d in datasets if d.id == dataset_id), None)
                if not dataset:
                    continue
                
                is_validation = dataset.usage_tag == "validation"
                target_urls = val_image_urls if is_validation else image_urls
                target_anns = val_annotations if is_validation else annotations

                if dataset.type == "video":
                    # For videos, use keyframes
                    from backend.supabase_client import get_keyframe_annotations, update_keyframe
                    from backend.frame_extractor import extract_and_store_full_frame
                    
                    videos = get_dataset_videos(dataset_id)
                    for v in videos:
                        keyframes = get_video_keyframes(v["id"])
                        video_fps = v.get("fps") or 30.0
                        
                        for kf in keyframes:
                            kf_anns = kf.get("annotations", []) or []
                            if not kf_anns:
                                continue  # Skip unlabeled keyframes
                            
                            # Get image path - prefer full-res, fall back to thumbnail
                            kf_path = kf.get("full_image_path") or kf.get("thumbnail_path")
                            
                            # If no image exists, extract it now (same as detection training)
                            if not kf_path:
                                print(f"[Classification] Extracting frame {kf['frame_number']} from video {v['id']}...")
                                full_path = extract_and_store_full_frame(
                                    video_r2_path=v["r2_path"],
                                    frame_number=kf["frame_number"],
                                    fps=video_fps,
                                    dataset_id=dataset_id,
                                    video_id=v["id"]
                                )
                                if full_path:
                                    kf_path = full_path
                                    # Update DB for future use
                                    update_keyframe(kf["id"], full_image_path=full_path)
                                    print(f"[Classification] Stored frame at {full_path}")
                                else:
                                    print(f"[Classification] Failed to extract frame {kf['frame_number']}")
                                    continue
                            
                            kf_filename = f"{v['id']}_f{kf['frame_number']}.jpg"
                            
                            try:
                                img_url = r2.generate_presigned_url(kf_path)
                                target_urls[kf_filename] = img_url
                                
                                # Convert annotations to classification format
                                ann_list = []
                                for ann in kf_anns:
                                    # Resolve class_id to class_name (class_name no longer stored)
                                    class_id = ann.get("class_id")
                                    class_name = class_id_to_name.get(class_id, "") if class_id is not None else ""
                                    ann_list.append({
                                        "class_name": class_name,
                                        "x": ann.get("x", 0),
                                        "y": ann.get("y", 0),
                                        "width": ann.get("width", 0),
                                        "height": ann.get("height", 0),
                                    })
                                target_anns[kf_filename] = ann_list
                            except Exception as e:
                                print(f"[Classification] Error processing {kf_filename}: {e}")
                else:
                    # For images
                    from backend.supabase_client import get_dataset_images
                    
                    images = get_dataset_images(dataset_id)
                    for img in images:
                        img_anns = img.get("annotations", []) or []
                        if not img_anns:
                            continue  # Skip unlabeled images
                        
                        try:
                            img_url = r2.generate_presigned_url(img["r2_path"])
                            target_urls[img["filename"]] = img_url
                            
                            # Convert annotations
                            ann_list = []
                            for ann in img_anns:
                                # Resolve class_id to class_name (class_name no longer stored)
                                class_id = ann.get("class_id")
                                class_name = class_id_to_name.get(class_id, "") if class_id is not None else ""
                                ann_list.append({
                                    "class_name": class_name,
                                    "x": ann.get("x", 0),
                                    "y": ann.get("y", 0),
                                    "width": ann.get("width", 0),
                                    "height": ann.get("height", 0),
                                })
                            target_anns[img["filename"]] = ann_list
                        except Exception as e:
                            print(f"[Classification] Error processing {img['filename']}: {e}")

            print(f"[Classification] Gathered {len(image_urls)} train images, {len(val_image_urls)} val images")
            print(f"[Classification] Total annotations: {sum(len(a) for a in annotations.values())}")

            # Validate all classes have at least one annotation
            class_annotation_counts = {c: 0 for c in classes_snapshot}
            for ann_list in annotations.values():
                for ann in ann_list:
                    class_name = ann.get("class_name")
                    if class_name in class_annotation_counts:
                        class_annotation_counts[class_name] += 1
            
            empty_classes = [c for c, count in class_annotation_counts.items() if count == 0]
            if empty_classes:
                error_msg = f"Classes with no annotations: {', '.join(empty_classes)}. Remove them from the project or add labeled data."
                print(f"[Classification] Error: {error_msg}")
                from backend.supabase_client import update_training_run
                update_training_run(run_id, status="failed", error_message=error_msg)
                async with self:
                    self.is_starting = False
                    self.start_error = error_msg
                yield rx.toast.error(error_msg)
                return

            # Dispatch classification training job (routes to Modal or Local GPU)
            try:
                from backend.job_router import dispatch_classification_training_job
                dispatch_classification_training_job(
                    project_id=project_id,
                    run_id=run_id,
                    dataset_ids=selected_ids,
                    image_urls=image_urls,
                    annotations=annotations,
                    classes=classes_snapshot,
                    config=config,
                    train_split_ratio=train_split_percentage / 100,
                    val_image_urls=val_image_urls if val_dataset_ids else None,
                    val_annotations=val_annotations if val_dataset_ids else None,
                    # Action-level target selection
                    target=target,
                    user_id=user_id,
                    machine_name=machine_name,
                )
            except Exception as e:
                from backend.supabase_client import update_training_run
                update_training_run(run_id, status="failed", error_message=f"Job dispatch failed: {str(e)}")
                raise e

            async with self:
                self.is_starting = False
            yield TrainingState.load_dashboard()

        except Exception as e:
            print(f"[DEBUG] Error starting classification training: {e}")
            import traceback
            traceback.print_exc()
            async with self:
                self.is_starting = False
                self.start_error = str(e)
            yield rx.toast.error(f"Failed to start classification training: {str(e)}")


    @rx.event(background=True)
    async def start_sam3_training(self):
        """Launch SAM3 fine-tuning process.
        
        Unlike detection/classification training, this:
        1. Gathers annotations with mask_polygon from selected datasets
        2. Converts to COCO JSON format on-the-fly (class names as noun phrases)
        3. Generates presigned URLs for images
        4. Dispatches to cloud-only A100 Modal job
        """
        import json as json_mod
        
        async with self:
            if not self.total_labeled_count:
                return

            self.is_starting = True
            self.start_error = ""
            self.is_polling = False
            
            # Capture state for background execution
            sam3_num_images = self.sam3_num_images
            sam3_max_epochs = self.sam3_max_epochs
            sam3_lr_scale = self.sam3_lr_scale
            sam3_resolution = self.sam3_resolution
            selected_ids = self.selected_dataset_ids
            datasets = self.datasets
            project_id = self.current_project_id
            train_split_percentage = self.train_split_percentage
            
            auth_state = await self.get_state(AuthState)
            user_id = auth_state.user.get("id") if auth_state.user else None
        yield

        try:
            if not user_id:
                raise Exception("User not authenticated")

            r2 = R2Client()
            dataset_name_list = []
            image_records = []
            
            # Get classes from PROJECT
            from backend.supabase_client import get_project, get_dataset_images
            project_data = get_project(project_id)
            project_classes = project_data.get("classes", []) if project_data else []
            
            if not project_classes:
                raise Exception("No classes defined in project")
            
            print(f"[SAM3] Using {len(project_classes)} classes from project: {project_classes}")
            classes_snapshot = sorted(list(project_classes))
            
            # Gather dataset names
            for dataset_id in selected_ids:
                dataset = next((d for d in datasets if d.id == dataset_id), None)
                if dataset:
                    dataset_name_list.append(dataset.name)

            # Gather image records with annotations (bounding boxes required)
            for dataset_id in selected_ids:
                dataset = next((d for d in datasets if d.id == dataset_id), None)
                if not dataset:
                    continue
                
                if dataset.type == "video":
                    # For videos, use keyframes
                    from backend.supabase_client import get_dataset_videos, get_video_keyframes
                    
                    videos = get_dataset_videos(dataset_id)
                    for v in videos:
                        keyframes = get_video_keyframes(v["id"])
                        for kf in keyframes:
                            kf_anns = kf.get("annotations", []) or []
                            if not kf_anns:
                                continue
                            
                            kf_path = kf.get("full_image_path") or kf.get("thumbnail_path")
                            if not kf_path:
                                continue
                            
                            kf_filename = f"{v['id']}_f{kf['frame_number']}.jpg"
                            image_records.append({
                                "id": kf.get("id", ""),
                                "filename": kf_filename,
                                "r2_path": kf_path,
                                "width": kf.get("width", 1920),
                                "height": kf.get("height", 1080),
                                "annotations": kf_anns,
                            })
                else:
                    # For images
                    images = get_dataset_images(dataset_id)
                    for img in images:
                        img_anns = img.get("annotations", []) or []
                        if not img_anns:
                            continue
                        
                        image_records.append({
                            "id": img["id"],
                            "filename": img["filename"],
                            "r2_path": img["r2_path"],
                            "width": img.get("width", 1920),
                            "height": img.get("height", 1080),
                            "annotations": img_anns,
                        })
            
            if not image_records:
                raise Exception("No images with annotations found in selected datasets")
            
            # Apply num_images limit for few-shot training (stratified per class)
            if sam3_num_images > 0 and len(image_records) > sam3_num_images:
                import random
                from collections import defaultdict
                random.seed(42)
                
                # Group images by which classes they contain
                class_to_images: dict[int, list[int]] = defaultdict(list)
                for idx, rec in enumerate(image_records):
                    for ann in rec.get("annotations", []):
                        cid = ann.get("class_id")
                        if cid is not None:
                            class_to_images[cid].append(idx)
                
                # For each class, sample up to N images containing that class
                selected_indices: set[int] = set()
                for cid, indices in sorted(class_to_images.items()):
                    unique_indices = list(set(indices))
                    random.shuffle(unique_indices)
                    selected = unique_indices[:sam3_num_images]
                    selected_indices.update(selected)
                    class_name = project_classes[cid] if cid < len(project_classes) else f"class_{cid}"
                    print(f"[SAM3] Class '{class_name}': {len(selected)}/{len(unique_indices)} images selected")
                
                image_records = [image_records[i] for i in sorted(selected_indices)]
                print(f"[SAM3] Stratified few-shot: {len(image_records)} images ({sam3_num_images} per class)")
            
            print(f"[SAM3] Gathered {len(image_records)} images with annotations")
            
            # Build COCO dataset on-the-fly
            from backend.core.sam3_dataset_core import build_sam3_coco_dataset
            train_coco, test_coco, image_r2_mapping = build_sam3_coco_dataset(
                image_records=image_records,
                project_classes=project_classes,
                train_split=train_split_percentage / 100,
                prompt=self.sam3_prompt,
            )
            
            # Generate presigned URLs for all images in the dataset
            image_r2_urls = {}
            for filename, r2_path in image_r2_mapping.items():
                try:
                    image_r2_urls[filename] = r2.generate_presigned_url(r2_path)
                except Exception as e:
                    print(f"[SAM3] Error generating URL for {r2_path}: {e}")
            
            print(f"[SAM3] Generated {len(image_r2_urls)} presigned URLs")
            
            # Create training run config
            config = {
                "resolution": sam3_resolution,
                "max_epochs": sam3_max_epochs,
                "early_stop_patience": self.sam3_early_stop_patience,
                "num_images": sam3_num_images,
                "lr_scale": sam3_lr_scale,
                "prompt": self.sam3_prompt,
                "classes": classes_snapshot,
            }
            
            run = create_training_run(
                project_id=project_id,
                dataset_ids=selected_ids,
                user_id=user_id,
                config=config,
                target="cloud",  # SAM3 is cloud-only (A100)
                dataset_names=dataset_name_list,
                classes_snapshot=classes_snapshot,
                model_type="sam3_finetune",
            )
            
            if not run:
                raise Exception("Failed to create training run in database")
            
            run_id = run["id"]
            
            # Dispatch SAM3 training job (cloud-only)
            try:
                from backend.job_router import dispatch_sam3_training_job
                dispatch_sam3_training_job(
                    project_id=project_id,
                    run_id=run_id,
                    image_r2_urls=image_r2_urls,
                    train_coco_json=json_mod.dumps(train_coco),
                    test_coco_json=json_mod.dumps(test_coco),
                    classes=classes_snapshot,
                    config=config,
                )
            except Exception as e:
                from backend.supabase_client import update_training_run
                update_training_run(run_id, status="failed", error_message=f"Job dispatch failed: {str(e)}")
                raise e

            async with self:
                self.is_starting = False
            yield TrainingState.load_dashboard()

        except Exception as e:
            print(f"[DEBUG] Error starting SAM3 training: {e}")
            import traceback
            traceback.print_exc()
            async with self:
                self.is_starting = False
                self.start_error = str(e)
            yield rx.toast.error(f"Failed to start SAM3 training: {str(e)}")

    @rx.event(background=True)
    async def refresh_run_history(self):
        """Silently refresh training runs history."""
        # Capture project_id
        async with self:
            project_id = self.current_project_id
        
        if not project_id:
            return

        runs = get_project_training_runs(project_id)
        history = [
            TrainingRunModel(
                id=str(r.get("id", "")),
                status=str(r.get("status", "pending")),
                target=str(r.get("target", "cloud")),
                config=r.get("config", {}),
                metrics=r.get("metrics"),
                artifacts_r2_prefix=r.get("artifacts_r2_prefix"),
                dataset_ids=r.get("dataset_ids", []) or [],
                dataset_names=r.get("dataset_names", []) or [],
                created_at=r.get("created_at", "").split(".")[0].replace("T", " "),
                started_at=r.get("started_at"),
                completed_at=r.get("completed_at"),
                error_message=r.get("error_message"),
                logs=r.get("logs"),
                alias=r.get("alias"),
                notes=r.get("notes"),
                tags=r.get("tags", []) or [],
                classes=r.get("classes_snapshot", []) or r.get("config", {}).get("classes", []) or [],
                model_type=r.get("model_type", "detection"),
            ) for r in runs
        ]
        
        async with self:
            self.training_runs = history
        
        yield  # Trigger UI update

    @rx.event(background=True)
    async def poll_training_status(self):
        """Background task to poll for training status updates."""
        import asyncio
        
        async with self:
            if self.is_polling:
                return
            self.is_polling = True
        
        try:
            while True:
                # Wait 2 seconds before next poll (more responsive UI)
                await asyncio.sleep(2)
                
                # Refresh data from database
                yield TrainingState.refresh_run_history()
                
                # Small delay to let the refresh complete
                await asyncio.sleep(0.5)
                
                # Check if any training run is still active (pending, queued, running)
                async with self:
                    active_runs = [r for r in self.training_runs if r.status in ["pending", "queued", "running"]]
                    if not active_runs:
                        print("[Training Poll] No active runs. Stopping poll.")
                        self.is_polling = False
                        break
        finally:
            async with self:
                self.is_polling = False

    # =========================================================================
    # Add Model to Playground
    # =========================================================================

    async def add_model_to_playground(self, model_type: str):
        """
        Add a trained model (best or last) to the inference playground.
        
        Args:
            model_type: "best" or "last"
        """
        # Get current run info
        run = None
        run_id = ""
        async with self:
            run_id = self.selected_run_id
            for r in self.training_runs:
                if r.id == run_id:
                    run = r
                    break
        
        if not run or run.status != "completed":
            yield rx.toast.error("Can only add models from completed training runs")
            return
        
        if not run.artifacts_r2_prefix:
            yield rx.toast.error("No artifacts found for this training run")
            return
        
        # Get user_id
        auth_state = await self.get_state(AuthState)
        user_id = auth_state.user_id
        
        if not user_id:
            yield rx.toast.error("User not authenticated")
            return
        
        # Determine weights path
        weights_file = "best.pt" if model_type == "best" else "last.pt"
        weights_path = f"{run.artifacts_r2_prefix}/{weights_file}"
        
        # Get dataset_id from run (use first one if multiple)
        dataset_ids = run.dataset_ids
        dataset_id = dataset_ids[0] if dataset_ids else None
        
        if not dataset_id:
            yield rx.toast.error("No dataset associated with this training run")
            return
        
        # Create model name - use alias if set, otherwise use run ID
        run_alias = run.alias if run.alias else f"run_{run_id[:8]}"
        model_name = f"{run_alias}_{model_type}"
        
        # Get metrics for this model
        metrics = run.metrics or {}
        
        try:
            # Check for existing model with same training_run_id and weights_path
            from backend.supabase_client import get_supabase
            supabase = get_supabase()
            existing = supabase.table("models").select("id").eq("training_run_id", run_id).eq("weights_path", weights_path).execute()
            
            if existing.data and len(existing.data) > 0:
                yield rx.toast.info(f"{model_type}.pt is already in the Playground")
                return
            
            # Create model record in database
            model = create_model(
                training_run_id=run_id,
                dataset_id=dataset_id,
                user_id=user_id,
                name=model_name,
                weights_path=weights_path,
                metrics=metrics,
            )
            
            if model:
                yield rx.toast.success(f"Added {model_type}.pt to Playground")
            else:
                yield rx.toast.error("Failed to create model record")
                
        except Exception as e:
            print(f"Error adding model to playground: {e}")
            yield rx.toast.error(f"Failed: {str(e)}")

    # =========================================================================
    # Add Model to Autolabel (with Modal Volume Upload)
    # =========================================================================

    async def add_model_to_autolabel(self, model_type: str):
        """
        Add a trained model to autolabeling by uploading to Modal volume.
        
        Args:
            model_type: "best" or "last"
        """
        import modal
        
        # Get current run info
        run = None
        run_id = ""
        async with self:
            run_id = self.selected_run_id
            for r in self.training_runs:
                if r.id == run_id:
                    run = r
                    break
        
        if not run or run.status != "completed":
            yield rx.toast.error("Can only add models from completed training runs")
            return
        
        if not run.artifacts_r2_prefix:
            yield rx.toast.error("No artifacts found for this training run")
            return
        
        # Get user_id
        auth_state = await self.get_state(AuthState)
        user_id = auth_state.user_id
        
        if not user_id:
            yield rx.toast.error("User not authenticated")
            return
        
        # Set loading state
        async with self:
            self.is_uploading_to_autolabel = True
        yield
        
        try:
            # Determine weights path
            weights_file = "best.pt" if model_type == "best" else "last.pt"
            weights_path = f"{run.artifacts_r2_prefix}/{weights_file}"
            
            # CHECK FOR DUPLICATES - prevent adding the same model twice
            from backend.supabase_client import get_supabase
            supabase = get_supabase()
            existing = (
                supabase.table("models")
                .select("id, volume_path")
                .eq("training_run_id", run_id)
                .eq("weights_path", weights_path)
                .not_.is_("volume_path", "null")  # Already uploaded to autolabel
                .execute()
            )
            
            if existing.data and len(existing.data) > 0:
                yield rx.toast.info(f"{model_type}.pt is already available for Autolabeling")
                async with self:
                    self.is_uploading_to_autolabel = False
                return
            
            # Get dataset_id from run (use first one if multiple)
            dataset_ids = run.dataset_ids
            dataset_id = dataset_ids[0] if dataset_ids else None
            
            if not dataset_id:
                yield rx.toast.error("No dataset associated with this training run")
                return
            
            # Create model name - use alias if set, otherwise use run ID
            run_alias = run.alias if run.alias else f"run_{run_id[:8]}"
            model_name = f"autolabel_{run_alias}_{model_type}"
            
            # Get metrics for this model
            metrics = run.metrics or {}
            
            # Create model record with volume_path placeholder
            model = create_model(
                training_run_id=run_id,
                dataset_id=dataset_id,
                user_id=user_id,
                name=model_name,
                weights_path=weights_path,
                volume_path=f"/models/{run_id}_{model_type}.pt",  # Will be validated after upload
                metrics=metrics,
            )
            
            if not model:
                yield rx.toast.error("Failed to create model record")
                return
            
            model_id = model["id"]
            
            # Upload to Modal volume
            try:
                upload_fn = modal.Function.from_name("yolo-models", "upload_model_to_volume")
                # Use remote() for synchronous call (wait for upload)
                # Function signature: upload_model_to_volume(r2_weights_path: str, model_id: str) -> str
                volume_path = upload_fn.remote(r2_weights_path=weights_path, model_id=model_id)
                
                if volume_path:
                    # Update model record with actual volume path
                    from backend.supabase_client import update_model_volume_path
                    update_model_volume_path(model_id, volume_path)
                    
                    yield rx.toast.success(f"✨ Model ready for autolabeling!")
                else:
                    yield rx.toast.error("Upload failed: No volume path returned")
                    # Clean up failed model record
                    from backend.supabase_client import delete_model
                    delete_model(model_id)
                    
            except Exception as e:
                print(f"Error uploading to Modal volume: {e}")
                yield rx.toast.error(f"Volume upload failed: {str(e)}")
                # Clean up failed model record
                from backend.supabase_client import delete_model
                delete_model(model_id)
                
        except Exception as e:
            print(f"Error adding model to autolabel: {e}")
            yield rx.toast.error(f"Failed: {str(e)}")
        finally:
            async with self:
                self.is_uploading_to_autolabel = False
