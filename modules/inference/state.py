"""
Inference State — State management for the inference playground (Phase 3.4).

Handles:
- Model selection (built-in + custom models)
- Image and video upload with format detection
- Video time range selection and frame skipping
- Modal function invocation for both image and video inference
- Prediction result management and persistence
"""

import reflex as rx
import modal
import uuid
import json
from typing import Optional, TypedDict

from backend.supabase_client import (
    get_supabase, 
    create_inference_result, 
    get_user_inference_results,
    get_models_grouped_by_project,
    get_accessible_project_ids,
    delete_inference_result as db_delete_inference_result,
    create_pending_inference_result,
    complete_inference_result,
    get_inference_progress,
    get_user_preferences,
    update_user_preferences,
    get_user_local_machines,
)
from backend.r2_storage import R2Client
from backend.job_router import (
    get_project_id_from_model,
    dispatch_hybrid_inference,
    dispatch_hybrid_inference_batch,
    dispatch_hybrid_inference_video,
)
from backend.inference_router import dispatch_inference, InferenceConfig
from app_state import AuthState
from modules.training.state import _validate_numeric


# TypedDict for prediction bounding box (from Modal inference job)
class PredictionBox(TypedDict):
    class_id: int
    class_name: str
    confidence: float
    box: list[float]  # [x1, y1, x2, y2] normalized 0-1


# TypedDict for model data in grouped selector
class ModelInfo(TypedDict):
    id: str
    name: str
    original_name: str
    training_run_id: str | None
    training_run_alias: str | None
    weights_type: str | None  # "best", "last", or None
    run_model_type: str  # "detection" or "classification"
    backbone: str | None  # "convnext", "yolo", or None for detection
    metric_value: float | None  # top1_accuracy or mAP value
    metric_type: str  # "acc" or "mAP"
    dataset_name: str
    dataset_id: str
    mAP: float | None  # Kept for backward compat
    created_at: str
    is_active: bool


# TypedDict for project grouping
class ProjectModels(TypedDict):
    project_id: str
    project_name: str
    models: list[ModelInfo]


# =============================================================================
# R2 Media Cache (module-level, shared across sessions)
# =============================================================================
import time as _time

_url_cache: dict[str, tuple[str, float]] = {}       # r2_path → (presigned_url, timestamp)
_download_cache: dict[str, tuple[dict, float]] = {} # r2_path → (parsed_json, timestamp)
_CACHE_TTL = 50 * 60  # 50 minutes (presigned URLs expire at 60)
_URL_CACHE_MAX = 50
_DOWNLOAD_CACHE_MAX = 10


def _cached_presigned_url(r2_client, path: str, expires_in: int = 3600) -> str:
    """Generate presigned URL with cache. Same video across model runs → 1 generation."""
    now = _time.time()
    if path in _url_cache:
        url, ts = _url_cache[path]
        if now - ts < _CACHE_TTL:
            print(f"[Cache HIT] URL for {path.split('/')[-1]}")
            return url
    # Cache miss or expired
    url = r2_client.generate_presigned_url(path, expires_in=expires_in)
    # Evict oldest if at capacity
    if len(_url_cache) >= _URL_CACHE_MAX:
        oldest_key = min(_url_cache, key=lambda k: _url_cache[k][1])
        del _url_cache[oldest_key]
    _url_cache[path] = (url, now)
    print(f"[Cache MISS] URL for {path.split('/')[-1]}")
    return url


def _cached_download_json(r2_client, path: str) -> dict:
    """Download and parse JSON from R2 with cache. Re-opening same result → skip download."""
    now = _time.time()
    if path in _download_cache:
        data, ts = _download_cache[path]
        if now - ts < _CACHE_TTL:
            print(f"[Cache HIT] Download for {path.split('/')[-1]}")
            return data
    # Cache miss or expired
    raw = r2_client.download_file(path)
    data = json.loads(raw.decode('utf-8'))
    # Evict oldest if at capacity  
    if len(_download_cache) >= _DOWNLOAD_CACHE_MAX:
        oldest_key = min(_download_cache, key=lambda k: _download_cache[k][1])
        del _download_cache[oldest_key]
    _download_cache[path] = (data, now)
    print(f"[Cache MISS] Download for {path.split('/')[-1]}")
    return data


# =============================================================================
# Mask Rendering Helper (shared across single/batch/fullview)
# =============================================================================

def _masks_to_css(masks: list[dict]) -> list[dict]:
    """
    Convert polygon masks to CSS clip-path format.
    
    Used by all image mask rendering paths (single preview, batch preview, full view).
    Video uses JavaScript canvas rendering instead.
    
    Args:
        masks: List of mask dicts with 'polygon' (normalized [[x,y],...]), 'class_name', 'class_id'
    
    Returns:
        List of dicts with 'clip_path' (CSS format), 'class_name', 'class_id'
    """
    result = []
    for mask in masks:
        polygon = mask.get("polygon", [])
        class_name = mask.get("class_name", "")
        class_id = mask.get("class_id", 0)
        
        if polygon:
            points_css = ", ".join(f"{round(p[0] * 100, 2)}% {round(p[1] * 100, 2)}%" for p in polygon)
            clip_path = f"polygon({points_css})"
            result.append({
                "class_name": class_name,
                "class_id": class_id,
                "clip_path": clip_path,
            })
    return result


class InferenceState(rx.State):
    """State for the inference playground."""
    
    # Model selection
    available_models: list[dict] = []
    models_by_project: list[ProjectModels] = []  # Typed for nested foreach
    builtin_models: list[str] = []  # Built-in YOLO models
    selected_model_type: str = "builtin"  # "builtin" or "custom"
    selected_model_id: str = ""  # For custom models
    selected_model_name: str = "yolo11s.pt"  # Default to YOLO11s
    
    @rx.var
    def model_names(self) -> list[str]:
        """Get list of available model names (built-in + custom)."""
        names = self.builtin_models.copy()
        names.extend([m["name"] for m in self.available_models])
        return names
    
    # Upload and format detection
    uploaded_file_type: str = ""  # "image" or "video"
    uploaded_filename: str = ""
    uploaded_r2_path: str = ""
    uploaded_presigned_url: str = ""
    
    # Image-specific
    uploaded_image_data: str = ""  # Base64 for preview
    image_width: int = 0
    image_height: int = 0
    
    # Batch Image Upload
    batch_mode: bool = False  # True when multiple images uploaded
    uploaded_images: list[dict] = []  # [{filename, r2_path, presigned_url, base64_preview, width, height}, ...]
    batch_progress_current: int = 0
    batch_progress_total: int = 0
    
    # Video-specific
    uploaded_video_data: str = ""  # Presigned URL for video preview
    video_duration: float = 0.0
    video_fps: float = 0.0
    video_frame_count: int = 0
    video_start_time: float = 0.0
    video_end_time: float = 0.0
    enable_frame_skip: bool = False  # OFF by default
    frame_skip_interval: int = 5  # Process every 5th frame
    
    # Predictions
    predictions: list[PredictionBox] = []
    predictions_by_frame: dict[str, list[PredictionBox]] = {}  # For videos
    labels_txt: str = ""  # YOLO format labels
    is_predicting: bool = False
    prediction_error: str = ""
    
    # Last inference result ID (for viewing in gallery)
    last_result_id: str = ""
    
    # Upload progress
    upload_progress: int = 0  # 0-100 percentage
    is_uploading: bool = False
    upload_stage: str = ""  # "reading", "extracting_metadata", "uploading_storage", "ready"
    
    # Video thumbnail
    video_thumbnail_url: str = ""  # Base64 thumbnail for preview
    
    # Configuration
    confidence_threshold: float = 0.25
    
    # Video Playback (for viewing saved inference results - Phase 3.4.5)
    current_result_id: str = ""
    current_result_input_type: str = ""  # "image" or "video"
    current_result_video_url: str = ""
    current_result_image_url: str = ""  # For image results
    current_result_predictions: list[PredictionBox] = []  # For image results
    current_result_masks: list[dict] = []  # Segmentation masks for full view
    current_result_model_name: str = ""
    current_result_confidence: float = 0.25
    current_frame_number: int = 0
    labels_by_frame: dict[int, list[PredictionBox]] = {}  # Frame -> list of boxes
    masks_by_frame: dict[int, list[dict]] = {}  # Frame -> list of masks for video
    is_playing: bool = False
    playback_speed: float = 1.0
    show_masks_fullview: bool = True  # Toggle mask visibility in full view
    
    # Gallery of saved inference results
    inference_results: list[dict] = []
    
    # Progress tracking
    processing_inference_id: str = ""
    inference_progress_current: int = 0
    inference_progress_total: int = 0
    inference_progress_status: str = "idle"
    is_polling_inference: bool = False
    inference_stage: str = ""  # "initializing", "loading_model", "processing", "saving", ""

    # Hybrid Inference (SAM3 + Classifier)
    is_hybrid_mode: bool = False  # True when classifier model is selected
    selected_classifier_type: str = "detection"  # "detection" or "classification"
    classifier_classes: list[str] = []  # Class names the classifier was trained on
    classifier_r2_path: str = ""  # R2 path to classifier weights
    sam3_prompts_input: str = "mammal, bird"  # Comma-separated SAM3 prompts
    # prompt_class_map: UI for mapping prompts to classifier classes
    prompt_class_assignments: dict[str, list[str]] = {}  # {sam3_prompt: [valid_class1, class2, ...]}
    classifier_confidence: float = 0.5  # Minimum classifier confidence to accept
    show_hybrid_config: bool = False  # Toggle for advanced configuration section
    show_masks_preview: bool = True  # Toggle mask visibility in preview
    video_target_resolution: str = "644"  # Video resize before upload ("644" or "1036")
    video_target_fps: str = "original"  # Target FPS for video upload ("original", "30", "15", "10")
    sam3_imgsz: str = "644"  # SAM3 inference resolution ("644" or "1036")
    classify_top_k: int = 3  # Number of frames per track for classification voting

    # SAM3 model selection (fine-tuned vs pretrained)
    sam3_available_models: list[dict] = []  # [{alias, filename, volume_path, size_gb}]
    selected_sam3_model: str = "sam3.pt"  # Default pretrained

    # Debug: first crop from last SAM3 run (shown below inference card)
    debug_crop_url: str = ""  # Presigned URL to the first SAM3 crop (single/batch)
    classification_crop_urls: list[dict] = []  # K crop gallery [{"url", "class_name", "confidence", "track_id"}]

    # Compute target (action-level selection)
    compute_target: str = "cloud"  # "cloud" or "local"
    selected_machine: str = ""     # machine name for local target
    local_machines: list[dict] = []  # cached list of user's machines

    # Model Selector UI State
    project_filter: str = ""
    is_builtin_expanded: bool = False
    is_results_expanded: bool = True  # Collapsible results section
    model_dropdown_open: bool = False  # Controlled popover state
    
    # Preview Modal State
    is_preview_open: bool = False
    preview_result_id: str = ""
    preview_filename: str = ""
    preview_model_name: str = ""
    preview_input_type: str = ""
    preview_input_url: str = ""
    preview_predictions: list[PredictionBox] = []
    preview_detection_count: int = 0
    preview_labels_by_frame: dict[int, list[PredictionBox]] = {}  # For video preview
    preview_video_fps: float = 30.0
    preview_masks: list[dict] = []  # Segmentation masks: [{"class_name": str, "polygon": [[x, y], ...]}]
    preview_masks_by_frame: dict[int, list[dict]] = {}  # Video masks: {frame_num: [{"class_name": str, "polygon": [...]}]}
    
    # Batch preview state
    preview_batch_images: list[dict] = []  # [{filename, r2_path, width, height}, ...]
    preview_batch_predictions: list[list] = []  # [[predictions for img 0], [predictions for img 1], ...]
    preview_batch_masks: list[list] = []  # [[masks for img 0], [masks for img 1], ...]
    preview_batch_index: int = 0  # Current image index in batch
    preview_batch_urls: list[str] = []  # Presigned URLs for batch images
    
    # Video Hybrid Thumbnail Cache (on-demand generation)
    thumbnail_urls: dict[str, str] = {}  # result_id -> presigned thumbnail URL
    
    @rx.var
    def preview_predictions_json(self) -> str:
        """JSON serialized predictions for JavaScript canvas rendering."""
        import json
        return json.dumps(self.preview_predictions)
    
    @rx.var
    def preview_masks_css(self) -> list[dict]:
        """Format preview masks with CSS clip-path polygon format."""
        return _masks_to_css(self.preview_masks)
    
    @rx.var
    def preview_batch_current_url(self) -> str:
        """Get presigned URL for current batch image."""
        if self.preview_batch_urls and 0 <= self.preview_batch_index < len(self.preview_batch_urls):
            return self.preview_batch_urls[self.preview_batch_index]
        return ""
    
    @rx.var
    def preview_batch_current_filename(self) -> str:
        """Get filename for current batch image."""
        if self.preview_batch_images and 0 <= self.preview_batch_index < len(self.preview_batch_images):
            return self.preview_batch_images[self.preview_batch_index].get("filename", "")
        return ""
    
    @rx.var
    def preview_batch_current_predictions(self) -> list[PredictionBox]:
        """Get predictions for current batch image."""
        if self.preview_batch_predictions and 0 <= self.preview_batch_index < len(self.preview_batch_predictions):
            return self.preview_batch_predictions[self.preview_batch_index]
        return []
    
    @rx.var
    def preview_batch_count(self) -> int:
        """Get total number of images in batch."""
        return len(self.preview_batch_images)
    
    @rx.var
    def preview_batch_current_masks_css(self) -> list[dict]:
        """Get CSS-formatted masks for current batch image."""
        if not self.preview_batch_masks or self.preview_batch_index >= len(self.preview_batch_masks):
            return []
        return _masks_to_css(self.preview_batch_masks[self.preview_batch_index])
    
    @rx.var
    def fullview_masks_css(self) -> list[dict]:
        """Format full view masks with CSS clip-path polygon format."""
        return _masks_to_css(self.current_result_masks)
    
    @rx.var
    def project_names(self) -> list[str]:
        """Get unique project names"""
        return [p["project_name"] for p in self.models_by_project]
        
    @rx.var
    def filtered_projects(self) -> list[ProjectModels]:
        """Filter projects and models by text search (case-insensitive)."""
        if not self.project_filter:
            return self.models_by_project
        
        search = self.project_filter.lower()
        result = []
        
        for project in self.models_by_project:
            # Check if project name matches
            project_matches = search in project["project_name"].lower()
            
            # Filter models by name match
            matching_models = [
                m for m in project["models"]
                if search in m["name"].lower() or project_matches
            ]
            
            if matching_models:
                result.append({
                    **project,
                    "models": matching_models if not project_matches else project["models"],
                })
        
        return result
        
    def set_project_filter(self, value: str):
        self.project_filter = value

    @rx.var
    def formatted_confidence(self) -> str:
        """Get formatted confidence as string (e.g. 25%)"""
        return f"{int(round(self.confidence_threshold * 100))}%"
    
    @rx.var
    def sam3_prompts(self) -> list[str]:
        """Parse SAM3 prompts from input string."""
        if not self.sam3_prompts_input:
            return []
        return [p.strip() for p in self.sam3_prompts_input.split(",") if p.strip()]
    
    @rx.var
    def prompt_class_map(self) -> dict[str, list[str]]:
        """Build prompt-to-class mapping from assignments."""
        # If no assignments, auto-assign all classes to all prompts
        if not self.prompt_class_assignments:
            return {p: self.classifier_classes for p in self.sam3_prompts}
        return self.prompt_class_assignments
    
    def toggle_builtin_expanded(self):
        self.is_builtin_expanded = not self.is_builtin_expanded
    
    def set_model_dropdown_open(self, open: bool):
        """Control the model dropdown popover open state."""
        self.model_dropdown_open = open
    
    def toggle_results_expanded(self):
        """Toggle the results section expanded/collapsed state."""
        self.is_results_expanded = not self.is_results_expanded
    
    def toggle_hybrid_config(self):
        """Toggle hybrid config section visibility."""
        self.show_hybrid_config = not self.show_hybrid_config
    
    @rx.var
    def sam3_model_options(self) -> list[str]:
        """Get display labels for SAM3 model dropdown."""
        return [m.get("alias", m.get("filename", "")) for m in self.sam3_available_models]
    
    @rx.var
    def selected_sam3_display(self) -> str:
        """Display label for currently selected SAM3 model."""
        for m in self.sam3_available_models:
            if m.get("filename") == self.selected_sam3_model:
                return m.get("alias", m.get("filename", ""))
        return "Pretrained (Meta)"
    
    async def load_sam3_models(self):
        """Load SAM3 models from Modal volume, cross-ref with training run aliases."""
        import modal as _modal
        
        try:
            list_fn = _modal.Function.from_name("sam3-training", "list_sam3_volume_models")
            volume_models = list_fn.remote()
            
            # Cross-reference with Supabase training runs for aliases
            supabase = get_supabase()
            sam3_runs = (
                supabase.table("training_runs")
                .select("id, alias, metrics, status")
                .eq("model_type", "sam3")
                .eq("status", "completed")
                .order("created_at", desc=True)
                .execute()
            )
            
            # Build short_id → alias map from training runs
            alias_map = {}  # filename → alias
            for run in (sam3_runs.data or []):
                metrics = run.get("metrics") or {}
                checkpoint_path = metrics.get("modal_checkpoint_path", "")
                # Extract filename from path like "/sam3_weights/sam3_finetuned_72e923fe.pt"
                if checkpoint_path:
                    fname = checkpoint_path.split("/")[-1]
                    alias_map[fname] = run.get("alias") or fname
            
            # Also map latest symlink
            if "sam3_finetuned.pt" not in alias_map:
                alias_map["sam3_finetuned.pt"] = "Latest Fine-tuned"
            
            # Build model list with aliases
            models = []
            for vm in volume_models:
                fname = vm["filename"]
                if fname == "sam3.pt":
                    alias = "Pretrained (Meta)"
                else:
                    alias = alias_map.get(fname, fname.replace(".pt", "").replace("sam3_finetuned_", "ft-"))
                
                models.append({
                    "alias": alias,
                    "filename": fname,
                    "volume_path": vm["volume_path"],
                    "size_gb": vm["size_gb"],
                })
            
            self.sam3_available_models = models
            print(f"[SAM3 Models] Loaded {len(models)} models: {[m['alias'] for m in models]}")
            
        except Exception as e:
            print(f"[SAM3 Models] Error loading models: {e}")
            # Fallback: at least show pretrained
            self.sam3_available_models = [{
                "alias": "Pretrained (Meta)",
                "filename": "sam3.pt",
                "volume_path": "/models/sam3.pt",
                "size_gb": 3.2,
            }]
    
    async def set_selected_sam3_model(self, display_alias: str):
        """Set selected SAM3 model by display alias and save preference."""
        # Find filename from alias
        for m in self.sam3_available_models:
            if m.get("alias") == display_alias:
                self.selected_sam3_model = m["filename"]
                break
        
        # Save preference
        auth_state = await self.get_state(AuthState)
        if auth_state.user_id:
            update_user_preferences(auth_state.user_id, "playground", {
                "selected_sam3_model": self.selected_sam3_model,
            })
    
    def set_sam3_prompts_input(self, value: str):
        """Update SAM3 prompts input."""
        self.sam3_prompts_input = value
    
    def set_classifier_confidence(self, value: list[float]):
        """Update classifier confidence from slider (legacy)."""
        self.classifier_confidence = value[0]
    
    async def set_classifier_confidence_input(self, value: str):
        """Set classifier confidence from text input."""
        v = _validate_numeric(value, 0.1, 1.0, 0.05, is_float=True)
        if v is not None:
            self.classifier_confidence = v
            await self.save_classifier_confidence_pref()
    
    async def increment_classifier_confidence(self):
        self.classifier_confidence = round(min(1.0, self.classifier_confidence + 0.05), 2)
        await self.save_classifier_confidence_pref()
    
    async def decrement_classifier_confidence(self):
        self.classifier_confidence = round(max(0.1, self.classifier_confidence - 0.05), 2)
        await self.save_classifier_confidence_pref()
    
    async def save_sam3_prompts_pref(self):
        """Save SAM3 prompts preference on blur."""
        auth_state = await self.get_state(AuthState)
        if auth_state.user_id:
            update_user_preferences(auth_state.user_id, "playground", {
                "sam3_prompts": self.sam3_prompts_input,
            })
    
    async def save_classifier_confidence_pref(self, _value=None):
        """Save classifier confidence preference on slider release."""
        auth_state = await self.get_state(AuthState)
        if auth_state.user_id:
            update_user_preferences(auth_state.user_id, "playground", {
                "classifier_confidence": self.classifier_confidence,
            })
    
    async def set_video_target_resolution(self, value: str):
        """Update video target resolution from dropdown and save preference."""
        self.video_target_resolution = value
        auth_state = await self.get_state(AuthState)
        if auth_state.user_id:
            update_user_preferences(auth_state.user_id, "playground", {
                "video_target_resolution": value,
            })
    
    async def set_video_target_fps(self, value: str):
        """Update video target FPS from dropdown and save preference."""
        self.video_target_fps = value
        auth_state = await self.get_state(AuthState)
        if auth_state.user_id:
            update_user_preferences(auth_state.user_id, "playground", {
                "video_target_fps": value,
            })
    
    async def set_sam3_imgsz(self, value: str):
        """Update SAM3 inference resolution from dropdown and save preference."""
        self.sam3_imgsz = value
        auth_state = await self.get_state(AuthState)
        if auth_state.user_id:
            update_user_preferences(auth_state.user_id, "playground", {
                "sam3_imgsz": value,
            })
    
    def toggle_mask_visibility(self):
        """Toggle mask visibility in preview."""
        self.show_masks_preview = not self.show_masks_preview
        # For video previews, also toggle via JS
        return rx.call_script(f"window.setMasksVisible && window.setMasksVisible({str(self.show_masks_preview).lower()})")
    
    def toggle_fullview_mask_visibility(self):
        """Toggle mask visibility in full view."""
        self.show_masks_fullview = not self.show_masks_fullview
        # For video results, also toggle via JS
        return rx.call_script(f"window.setMasksVisible && window.setMasksVisible({str(self.show_masks_fullview).lower()})")
    
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
    
    async def preview_result(self, result_id: str):
        """Load and show preview modal for a result."""
        import time
        try:
            t0 = time.time()
            supabase = get_supabase()
            result = supabase.table("inference_results").select("*").eq("id", result_id).single().execute()
            t1 = time.time()
            print(f"[Preview Timer] Supabase fetch: {(t1-t0)*1000:.1f}ms")
            
            if not result.data:
                return
            
            record = result.data
            self.preview_result_id = result_id
            self.preview_filename = record.get("input_filename", "Unknown")
            self.classification_crop_urls = []  # Clear stale crops from previous inference
            self.preview_model_name = record.get("model_name", "Unknown")
            self.preview_input_type = record.get("input_type", "image")
            self.preview_detection_count = record.get("detection_count", 0)
            
            # Get presigned URL for input (cached by r2_path)
            t2 = time.time()
            r2_client = R2Client()
            self.preview_input_url = _cached_presigned_url(
                r2_client, record.get("input_r2_path", "")
            )
            t3 = time.time()
            print(f"[Preview Timer] Input URL: {(t3-t2)*1000:.1f}ms")
            
            # For videos, also load labels for preview rendering
            if self.preview_input_type == "video":
                labels_path = record.get("labels_r2_path", "")
                if labels_path:
                    try:
                        t_labels = time.time()
                        labels_json = _cached_download_json(r2_client, labels_path)
                        
                        # Handle both formats:
                        # - Hybrid: {"predictions_by_frame": {...}, "masks_by_frame": {...}}
                        # - Regular: {frame_num: predictions, ...}
                        if "predictions_by_frame" in labels_json:
                            # Hybrid format
                            predictions_data = labels_json.get("predictions_by_frame", {})
                            self.preview_labels_by_frame = {int(k): v for k, v in predictions_data.items()}
                            # Also store masks for video preview
                            masks_data = labels_json.get("masks_by_frame", {})
                            self.preview_masks_by_frame = {int(k): v for k, v in masks_data.items()}
                            
                            # Reload classification crops with fresh presigned URLs
                            saved_crops = labels_json.get("classification_crops", [])
                            if saved_crops:
                                crop_urls = []
                                for crop in saved_crops:
                                    r2_path = crop.get("r2_path", "")
                                    if r2_path:
                                        try:
                                            url = _cached_presigned_url(r2_client, r2_path)
                                            crop_urls.append({
                                                "url": url,
                                                "class_name": crop.get("class_name", "Unknown"),
                                                "confidence": crop.get("confidence", 0.0),
                                                "track_id": crop.get("track_id", 0),
                                            })
                                        except Exception as e:
                                            print(f"[Preview] Failed to sign crop URL {r2_path}: {e}")
                                self.classification_crop_urls = crop_urls
                                print(f"[Preview] Loaded {len(crop_urls)} classification crops")
                        else:
                            # Regular flat format
                            self.preview_labels_by_frame = {int(k): v for k, v in labels_json.items()}
                            self.preview_masks_by_frame = {}
                        
                        self.preview_video_fps = record.get("video_fps", 30.0)
                        
                        # Debug: log what we loaded
                        print(f"[Preview] Loaded {len(self.preview_labels_by_frame)} frames in {(time.time()-t_labels)*1000:.1f}ms")
                        if self.preview_labels_by_frame:
                            first_frame = list(self.preview_labels_by_frame.keys())[0]
                            print(f"[Preview] First frame {first_frame}: {len(self.preview_labels_by_frame[first_frame])} predictions")
                    except Exception as e:
                        print(f"Error loading preview labels: {e}")
                        self.preview_labels_by_frame = {}
                        self.preview_masks_by_frame = {}
                else:
                    self.preview_labels_by_frame = {}
                    self.preview_masks_by_frame = {}
            
            # Handle batch type - load batch images and predictions
            elif self.preview_input_type == "batch":
                t_batch = time.time()
                batch_images = record.get("batch_images", [])
                predictions_json = record.get("predictions_json", {})
                batch_predictions = predictions_json.get("batch_predictions", [])
                batch_masks = predictions_json.get("batch_masks", [])
                
                self.preview_batch_images = batch_images
                self.preview_batch_predictions = batch_predictions
                self.preview_batch_masks = batch_masks
                self.preview_batch_index = 0
                
                # Generate presigned URLs for batch images (prefer thumbnails for fast loading)
                t_urls = time.time()
                self.preview_batch_urls = []
                for i, img in enumerate(batch_images):
                    # Use thumbnail if available, otherwise fallback to full-size
                    thumb_path = img.get("thumbnail_r2_path", "")
                    r2_path = thumb_path if thumb_path else img.get("r2_path", "")
                    if r2_path:
                        t_url = time.time()
                        url = _cached_presigned_url(r2_client, r2_path)
                        self.preview_batch_urls.append(url)
                        print(f"[Preview Timer] URL {i+1}/{len(batch_images)}: {(time.time()-t_url)*1000:.1f}ms ({'thumb' if thumb_path else 'full'})")
                    else:
                        self.preview_batch_urls.append("")
                
                print(f"[Preview Timer] All {len(batch_images)} URLs: {(time.time()-t_urls)*1000:.1f}ms total")
                print(f"[Preview Timer] Batch total: {(time.time()-t_batch)*1000:.1f}ms")
            
            # Get predictions from predictions_json (for single images)
            predictions_json = record.get("predictions_json", {})
            if isinstance(predictions_json, dict):
                self.preview_predictions = predictions_json.get("predictions", [])
                # Load masks if available (from hybrid inference with include_masks=True)
                self.preview_masks = predictions_json.get("masks", [])
            else:
                self.preview_predictions = []
                self.preview_masks = []
            
            self.is_preview_open = True
            
            # For videos, trigger JS to set up the preview player after modal opens
            if self.preview_input_type == "video" and self.preview_labels_by_frame:
                labels_json_str = json.dumps(self.preview_labels_by_frame)
                masks_json_str = json.dumps(self.preview_masks_by_frame)
                # Use setTimeout to ensure DOM elements exist after modal renders
                return [
                    rx.call_script(f"setTimeout(() => {{ window.setInferenceFps && window.setInferenceFps({self.preview_video_fps}); }}, 100)"),
                    rx.call_script(f"setTimeout(() => {{ window.setInferenceLabels && window.setInferenceLabels({labels_json_str}); }}, 100)"),
                    rx.call_script(f"setTimeout(() => {{ window.setInferenceMasks && window.setInferenceMasks({masks_json_str}); }}, 100)"),
                    rx.call_script(f"setTimeout(() => {{ window.loadInferenceVideo && window.loadInferenceVideo('{self.preview_input_url}'); }}, 150)"),
                ]
            
        except Exception as e:
            print(f"Error loading preview: {e}")
    
    def close_preview(self):
        """Close the preview modal and cleanup JS player + key listener."""
        self.is_preview_open = False
        return rx.call_script(
            "if (window._previewKeyHandler) { document.removeEventListener('keydown', window._previewKeyHandler); window._previewKeyHandler = null; }"
            " window.cleanupInferencePlayer && window.cleanupInferencePlayer()"
        )
    
    def set_preview_open(self, open: bool):
        """Set preview modal open state."""
        self.is_preview_open = open
        # Cleanup JS player + key listener when closing
        if not open:
            return rx.call_script(
                "if (window._previewKeyHandler) { document.removeEventListener('keydown', window._previewKeyHandler); window._previewKeyHandler = null; }"
                " window.cleanupInferencePlayer && window.cleanupInferencePlayer()"
            )
    
    def batch_preview_next(self):
        """Go to next image in batch preview."""
        if self.preview_batch_index < len(self.preview_batch_images) - 1:
            self.preview_batch_index += 1
    
    def batch_preview_prev(self):
        """Go to previous image in batch preview."""
        if self.preview_batch_index > 0:
            self.preview_batch_index -= 1

    def batch_preview_next_trigger(self, _value: str = ""):
        """Trigger: go to next image in batch preview (from hidden input)."""
        self.batch_preview_next()

    def batch_preview_prev_trigger(self, _value: str = ""):
        """Trigger: go to previous image in batch preview (from hidden input)."""
        self.batch_preview_prev()
    
    async def load_models(self):
        """Load all available models (built-in + custom) from Supabase."""
        try:
            # CRITICAL: Close any stale preview modal on page load
            # This prevents the modal from appearing when navigating back from full view
            self.is_preview_open = False
            
            # Cleanup any stale JS player references
            yield rx.call_script("window.cleanupInferencePlayer && window.cleanupInferencePlayer()")
            
            # Built-in models from Ultralytics
            self.builtin_models = [
                "yolo11n.pt",  # Nano - fastest
                "yolo11s.pt",  # Small - balanced (default)
                "yolo11m.pt",  # Medium - accurate
            ]
            
            # Get user ID
            auth_state = await self.get_state(AuthState)
            user_id = auth_state.user_id
            
            print(f"[DEBUG] load_models called, user_id={user_id}")
            
            if user_id:
                # Load user's local machines for compute target selection
                self.local_machines = get_user_local_machines(user_id)
                
                # Get models grouped by project for selector
                project_ids = get_accessible_project_ids(user_id)
                grouped = get_models_grouped_by_project(project_ids)
                print(f"[DEBUG] grouped result: {grouped}")
                self.models_by_project = grouped.get("projects", [])
                print(f"[DEBUG] models_by_project: {self.models_by_project}")
                
                # Also keep flat list for backwards compat
                self.available_models = []
                for proj in self.models_by_project:
                    self.available_models.extend(proj.get("models", []))
                print(f"[DEBUG] available_models count: {len(self.available_models)}")
                # Load user preferences
                prefs = get_user_preferences(user_id)
                playground_prefs = prefs.get("playground", {})
                if "confidence_threshold" in playground_prefs:
                    self.confidence_threshold = playground_prefs["confidence_threshold"]
                if "selected_model_name" in playground_prefs:
                    saved_model = playground_prefs["selected_model_name"]
                    # Only restore if model exists (built-in or custom)
                    all_model_names = self.builtin_models + [m["name"] for m in self.available_models]
                    if saved_model in all_model_names:
                        self.selected_model_name = saved_model
                        if "selected_model_type" in playground_prefs:
                            self.selected_model_type = playground_prefs["selected_model_type"]
                            if self.selected_model_type == "custom":
                                for model in self.available_models:
                                    if model["name"] == saved_model:
                                        self.selected_model_id = model["id"]
                                        
                                        # Check if this is a classifier model (set hybrid mode)
                                        training_run_id = model.get("training_run_id")
                                        if training_run_id:
                                            try:
                                                supabase = get_supabase()
                                                run_result = supabase.table("training_runs").select(
                                                    "model_type, classes_snapshot, artifacts_r2_prefix, config"
                                                ).eq("id", training_run_id).single().execute()
                                                
                                                if run_result.data:
                                                    run_model_type = run_result.data.get("model_type", "detection")
                                                    if run_model_type == "classification":
                                                        self.is_hybrid_mode = True
                                                        self.selected_classifier_type = "classification"
                                                        self.classifier_classes = run_result.data.get("classes_snapshot", []) or []
                                                        prefix = run_result.data.get("artifacts_r2_prefix", "")
                                                        if prefix:
                                                            # Use .pth for ConvNeXt, .pt for YOLO
                                                            run_config = run_result.data.get("config", {}) or {}
                                                            ext = ".pth" if run_config.get("classifier_backbone") == "convnext" else ".pt"
                                                            self.classifier_r2_path = f"{prefix}/best{ext}"
                                                        print(f"[Preferences] Classifier detected from preferences: {self.classifier_classes}")
                                            except Exception as e:
                                                print(f"Warning: Could not check model type from preferences: {e}")
                                        break
                
                # Load hybrid mode preferences (after model detection)
                if "sam3_prompts" in playground_prefs:
                    self.sam3_prompts_input = playground_prefs["sam3_prompts"]
                if "classifier_confidence" in playground_prefs:
                    self.classifier_confidence = playground_prefs["classifier_confidence"]
                # Stride-14 migration: map old values to new aligned values
                _res_migration = {"480": "490", "640": "644", "1024": "1036", "1280": "1288"}
                if "video_target_resolution" in playground_prefs:
                    val = str(playground_prefs["video_target_resolution"])
                    self.video_target_resolution = _res_migration.get(val, val)
                if "sam3_imgsz" in playground_prefs:
                    val = str(playground_prefs["sam3_imgsz"])
                    self.sam3_imgsz = _res_migration.get(val, val)
                if "video_target_fps" in playground_prefs:
                    self.video_target_fps = str(playground_prefs["video_target_fps"])
                if "classify_top_k" in playground_prefs:
                    self.classify_top_k = int(playground_prefs["classify_top_k"])
                if "selected_sam3_model" in playground_prefs:
                    self.selected_sam3_model = playground_prefs["selected_sam3_model"]
                
                print(f"[Preferences] Restored playground preferences")
                
                # Load SAM3 models from volume asynchronously
                try:
                    await self.load_sam3_models()
                except Exception as e:
                    print(f"[SAM3 Models] Failed to load: {e}")
            else:
                print("[DEBUG] No user_id, clearing models")
                self.models_by_project = []
                self.available_models = []
                
            # Load user's inference results
            await self.load_user_results()
                
        except Exception as e:
            print(f"Error loading models: {e}")
            import traceback
            traceback.print_exc()
            self.models_by_project = []
            self.available_models = []
    async def remove_model_from_playground(self, model_id: str):
        """Remove a model from the playground (deletes DB record, preserves training run/weights)."""
        from backend.supabase_client import delete_model
        
        try:
            deleted = delete_model(model_id)
            if deleted:
                # If the removed model was selected, reset to default
                deleted_name = deleted.get("name", "")
                if self.selected_model_name == deleted_name:
                    self.selected_model_name = "yolo11s.pt"
                    self.selected_model_type = "builtin"
                    self.selected_model_id = ""
                    self.is_hybrid_mode = False
                
                # Reload models to refresh dropdown
                yield InferenceState.load_models
                yield rx.toast.success(f"Removed from Playground")
            else:
                yield rx.toast.error("Model not found")
        except Exception as e:
            print(f"Error removing model from playground: {e}")
            yield rx.toast.error(f"Failed to remove: {str(e)}")
    
    async def load_user_results(self):
        """Load user's inference results for the results list."""
        try:
            # Get user_id from AuthState
            auth_state = await self.get_state(AuthState)
            user_id = auth_state.user_id
            
            if not user_id:
                self.inference_results = []
                return
            
            results = get_user_inference_results(user_id=user_id, limit=10)
            if results:
                r2_client = R2Client()
                
                # Process each result to add thumbnail_url field
                processed_results = []
                for result in results:
                    result_id = result.get("id", "")
                    input_type = result.get("input_type", "")
                    labels_path = result.get("labels_r2_path", "")
                    existing_thumb = result.get("thumbnail_r2_path", "")
                    predictions_json = result.get("predictions_json", {})
                    
                    # Initialize thumbnail_url to empty
                    result["thumbnail_url"] = ""
                    
                    # Normalize inference_settings (old results may have None)
                    settings = result.get("inference_settings") or {}
                    result["inference_settings"] = settings
                    # Pre-format settings for display
                    if "species_conf" in settings:
                        result["settings_display"] = (
                            f"Sp {int(settings['species_conf'] * 100)}%"
                            f" · SAM3 {int(settings['sam3_conf'] * 100)}%"
                            f" · {settings.get('resize_px', '')} · {settings.get('sam3_px', '')}px"
                        )
                    elif "sam3_conf" in settings:
                        result["settings_display"] = f"Conf {int(settings['sam3_conf'] * 100)}%"
                    else:
                        result["settings_display"] = ""
                    # Normalize created_at (should always exist but be safe)
                    if not result.get("created_at"):
                        result["created_at"] = ""
                    
                    # If already has thumbnail, just get URL
                    if existing_thumb:
                        result["thumbnail_url"] = r2_client.generate_presigned_url(existing_thumb)
                    # Check if this is a video hybrid result (on-demand generation)
                    elif input_type == "video" and labels_path and "_hybrid_labels.json" in labels_path:
                        thumb_url = await self._generate_video_hybrid_thumbnail_internal(result, r2_client)
                        if thumb_url:
                            result["thumbnail_url"] = thumb_url
                    # Single image hybrid with masks (on-demand generation)
                    elif input_type == "image" and predictions_json.get("masks"):
                        thumb_url = await self._generate_image_hybrid_thumbnail_internal(result, r2_client)
                        if thumb_url:
                            result["thumbnail_url"] = thumb_url
                    # Batch hybrid with masks (on-demand generation)
                    elif input_type == "batch" and predictions_json.get("batch_masks"):
                        thumb_url = await self._generate_batch_hybrid_thumbnail_internal(result, r2_client)
                        if thumb_url:
                            result["thumbnail_url"] = thumb_url
                    # Single image detection-only (on-demand generation)
                    elif input_type == "image" and predictions_json.get("predictions") and not predictions_json.get("masks"):
                        thumb_url = await self._generate_image_detection_thumbnail_internal(result, r2_client)
                        if thumb_url:
                            result["thumbnail_url"] = thumb_url
                    # Batch detection-only (on-demand generation)
                    elif input_type == "batch" and predictions_json.get("batch_predictions") and not predictions_json.get("batch_masks"):
                        thumb_url = await self._generate_batch_detection_thumbnail_internal(result, r2_client)
                        if thumb_url:
                            result["thumbnail_url"] = thumb_url
                    
                    processed_results.append(result)
                
                self.inference_results = processed_results
            else:
                self.inference_results = []
        except Exception as e:
            print(f"Error loading inference results: {e}")
            import traceback
            traceback.print_exc()
            self.inference_results = []
    
    async def generate_video_hybrid_thumbnail(self, result_id: str):
        """
        Generate thumbnail on-demand for video hybrid results that have masks but no thumbnail.
        Caches the URL in thumbnail_urls dict for subsequent renders.
        """
        # Skip if already cached
        if result_id in self.thumbnail_urls:
            return
        
        try:
            # Fetch the result record
            supabase = get_supabase()
            result = supabase.table("inference_results").select("*").eq("id", result_id).single().execute()
            
            if not result.data:
                return
            
            record = result.data
            
            # Only process video hybrid results
            if record.get("input_type") != "video":
                return
            
            labels_path = record.get("labels_r2_path", "")
            if not labels_path or "_hybrid_labels.json" not in labels_path:
                return  # Not a hybrid result
            
            # Check if thumbnail already exists in DB
            existing_thumb = record.get("thumbnail_r2_path", "")
            if existing_thumb:
                r2_client = R2Client()
                self.thumbnail_urls[result_id] = r2_client.generate_presigned_url(existing_thumb)
                return
            
            print(f"[Thumbnail] Generating thumbnail for video hybrid result {result_id}")
            
            # Load labels JSON from R2
            r2_client = R2Client()
            labels_data = r2_client.download_file(labels_path)
            labels_json = json.loads(labels_data.decode('utf-8'))
            
            masks_by_frame = labels_json.get("masks_by_frame", {})
            predictions_by_frame = labels_json.get("predictions_by_frame", {})
            
            if not masks_by_frame:
                print(f"[Thumbnail] No masks found in {labels_path}")
                return
            
            # Generate thumbnail from existing data
            from backend.core.thumbnail_generator import (
                select_best_frame_detection,
                generate_hybrid_thumbnail,
                extract_video_frame,
            )
            
            best_frame, best_pred, best_mask = select_best_frame_detection(
                predictions_by_frame, masks_by_frame
            )
            
            if best_frame is None or not best_mask:
                print(f"[Thumbnail] No valid detection found for thumbnail")
                return
            
            # Extract frame from video
            video_url = r2_client.generate_presigned_url(record["input_r2_path"])
            fps = record.get("video_fps", 30)
            frame_bytes = extract_video_frame(video_url, best_frame, fps)
            
            if not frame_bytes:
                print(f"[Thumbnail] Failed to extract frame {best_frame}")
                return
            
            thumb_bytes = generate_hybrid_thumbnail(frame_bytes, best_pred, best_mask)
            
            if thumb_bytes:
                # Upload to R2
                thumb_path = record["input_r2_path"].replace(".mp4", "_thumb.jpg")
                r2_client.upload_file(thumb_bytes, thumb_path)
                
                # Update DB with thumbnail path
                supabase.table("inference_results").update({
                    "thumbnail_r2_path": thumb_path
                }).eq("id", result_id).execute()
                
                # Cache the URL
                self.thumbnail_urls[result_id] = r2_client.generate_presigned_url(thumb_path)
                print(f"[Thumbnail] Successfully generated thumbnail for {result_id}")
            
        except Exception as e:
            print(f"[Thumbnail] Error generating thumbnail for {result_id}: {e}")
            import traceback
            traceback.print_exc()
    
    async def _generate_video_hybrid_thumbnail_internal(self, result: dict, r2_client) -> str | None:
        """
        Internal method to generate thumbnail from result dict.
        Returns presigned URL on success, None on failure.
        """
        try:
            result_id = result.get("id", "")
            labels_path = result.get("labels_r2_path", "")
            
            print(f"[Thumbnail] Generating thumbnail for video hybrid result {result_id}")
            
            # Load labels JSON from R2
            labels_data = r2_client.download_file(labels_path)
            labels_json = json.loads(labels_data.decode('utf-8'))
            
            masks_by_frame = labels_json.get("masks_by_frame", {})
            predictions_by_frame = labels_json.get("predictions_by_frame", {})
            
            if not masks_by_frame:
                print(f"[Thumbnail] No masks found in {labels_path}")
                return None
            
            # Generate thumbnail from existing data
            from backend.core.thumbnail_generator import (
                select_best_frame_detection,
                generate_hybrid_thumbnail,
                extract_video_frame,
            )
            
            best_frame, best_pred, best_mask = select_best_frame_detection(
                predictions_by_frame, masks_by_frame
            )
            
            if best_frame is None or not best_mask:
                print(f"[Thumbnail] No valid detection found for thumbnail")
                return None
            
            # Extract frame from video
            video_url = r2_client.generate_presigned_url(result["input_r2_path"])
            fps = result.get("video_fps", 30)
            frame_bytes = extract_video_frame(video_url, best_frame, fps)
            
            if not frame_bytes:
                print(f"[Thumbnail] Failed to extract frame {best_frame}")
                return None
            
            thumb_bytes = generate_hybrid_thumbnail(frame_bytes, best_pred, best_mask)
            
            if thumb_bytes:
                # Upload to R2
                thumb_path = result["input_r2_path"].replace(".mp4", "_thumb.jpg")
                r2_client.upload_file(thumb_bytes, thumb_path)
                
                # Update DB with thumbnail path
                supabase = get_supabase()
                supabase.table("inference_results").update({
                    "thumbnail_r2_path": thumb_path
                }).eq("id", result_id).execute()
                
                print(f"[Thumbnail] Successfully generated thumbnail for {result_id}")
                return r2_client.generate_presigned_url(thumb_path)
            
            return None
            
        except Exception as e:
            print(f"[Thumbnail] Error generating thumbnail: {e}")
            import traceback
            traceback.print_exc()
            return None
    
    async def _generate_image_hybrid_thumbnail_internal(self, result: dict, r2_client) -> str | None:
        """
        Generate thumbnail on-demand for single image hybrid results.
        Returns presigned URL on success, None on failure.
        """
        try:
            result_id = result.get("id", "")
            predictions_json = result.get("predictions_json", {})
            input_r2_path = result.get("input_r2_path", "")
            
            predictions = predictions_json.get("predictions", [])
            masks = predictions_json.get("masks", [])
            
            if not masks:
                return None
            
            from backend.core.thumbnail_generator import (
                select_largest_detection,
                generate_hybrid_thumbnail,
            )
            
            best_pred, best_mask = select_largest_detection(predictions, masks)
            
            if not best_pred or not best_mask:
                return None
            
            # Download image from R2
            image_bytes = r2_client.download_file(input_r2_path)
            if not image_bytes:
                print(f"[Thumbnail] Failed to download image for {result_id}")
                return None
            
            thumb_bytes = generate_hybrid_thumbnail(image_bytes, best_pred, best_mask)
            
            if thumb_bytes:
                thumb_path = input_r2_path.replace(".jpg", "_thumb.jpg").replace(".png", "_thumb.jpg")
                r2_client.upload_file(thumb_bytes, thumb_path)
                
                supabase = get_supabase()
                supabase.table("inference_results").update({
                    "thumbnail_r2_path": thumb_path
                }).eq("id", result_id).execute()
                
                print(f"[Thumbnail] Generated thumbnail for image {result_id}")
                return r2_client.generate_presigned_url(thumb_path)
            
            return None
            
        except Exception as e:
            print(f"[Thumbnail] Error generating image thumbnail: {e}")
            return None
    
    async def _generate_batch_hybrid_thumbnail_internal(self, result: dict, r2_client) -> str | None:
        """
        Generate thumbnail on-demand for batch hybrid results.
        Returns presigned URL on success, None on failure.
        """
        try:
            result_id = result.get("id", "")
            predictions_json = result.get("predictions_json", {})
            batch_images = result.get("batch_images", [])
            
            predictions_list = predictions_json.get("batch_predictions", [])
            masks_list = predictions_json.get("batch_masks", [])
            
            if not masks_list or not any(masks_list):
                return None
            
            from backend.core.thumbnail_generator import (
                select_best_batch_detection,
                generate_hybrid_thumbnail,
            )
            
            best_idx, best_pred, best_mask = select_best_batch_detection(predictions_list, masks_list)
            
            if best_idx is None or not best_pred or not best_mask:
                return None
            
            # Get the winning image's R2 path
            if best_idx >= len(batch_images):
                return None
            img_r2_path = batch_images[best_idx].get("r2_path", "")
            
            # Download image from R2
            image_bytes = r2_client.download_file(img_r2_path)
            if not image_bytes:
                print(f"[Thumbnail] Failed to download batch image for {result_id}")
                return None
            
            thumb_bytes = generate_hybrid_thumbnail(image_bytes, best_pred, best_mask)
            
            if thumb_bytes:
                thumb_path = f"inference_temp/batch_thumb_{result_id}.jpg"
                r2_client.upload_file(thumb_bytes, thumb_path)
                
                supabase = get_supabase()
                supabase.table("inference_results").update({
                    "thumbnail_r2_path": thumb_path
                }).eq("id", result_id).execute()
                
                print(f"[Thumbnail] Generated thumbnail for batch {result_id}")
                return r2_client.generate_presigned_url(thumb_path)
            
            return None
            
        except Exception as e:
            print(f"[Thumbnail] Error generating batch thumbnail: {e}")
            return None
    
    async def _generate_image_detection_thumbnail_internal(self, result: dict, r2_client) -> str | None:
        """
        Generate thumbnail on-demand for single image detection results (no masks).
        Returns presigned URL on success, None on failure.
        """
        try:
            result_id = result.get("id", "")
            predictions_json = result.get("predictions_json", {})
            input_r2_path = result.get("input_r2_path", "")
            
            predictions = predictions_json.get("predictions", [])
            
            if not predictions:
                return None
            
            from backend.core.thumbnail_generator import (
                select_largest_detection,
                generate_detection_thumbnail,
            )
            
            best_pred, _ = select_largest_detection(predictions)
            
            if not best_pred:
                return None
            
            image_bytes = r2_client.download_file(input_r2_path)
            if not image_bytes:
                return None
            
            thumb_bytes = generate_detection_thumbnail(image_bytes, best_pred)
            
            if thumb_bytes:
                thumb_path = input_r2_path.replace(".jpg", "_thumb.jpg").replace(".png", "_thumb.jpg")
                r2_client.upload_file(thumb_bytes, thumb_path)
                
                supabase = get_supabase()
                supabase.table("inference_results").update({
                    "thumbnail_r2_path": thumb_path
                }).eq("id", result_id).execute()
                
                print(f"[Thumbnail] Generated detection thumbnail for {result_id}")
                return r2_client.generate_presigned_url(thumb_path)
            
            return None
            
        except Exception as e:
            print(f"[Thumbnail] Error generating detection thumbnail: {e}")
            return None
    
    async def _generate_batch_detection_thumbnail_internal(self, result: dict, r2_client) -> str | None:
        """
        Generate thumbnail on-demand for batch detection results (no masks).
        Returns presigned URL on success, None on failure.
        """
        try:
            result_id = result.get("id", "")
            predictions_json = result.get("predictions_json", {})
            batch_images = result.get("batch_images", [])
            
            predictions_list = predictions_json.get("batch_predictions", [])
            
            if not predictions_list or not any(predictions_list):
                return None
            
            from backend.core.thumbnail_generator import (
                select_best_batch_detection,
                generate_detection_thumbnail,
            )
            
            best_idx, best_pred, _ = select_best_batch_detection(predictions_list)
            
            if best_idx is None or not best_pred:
                return None
            
            if best_idx >= len(batch_images):
                return None
            img_r2_path = batch_images[best_idx].get("r2_path", "")
            
            image_bytes = r2_client.download_file(img_r2_path)
            if not image_bytes:
                return None
            
            thumb_bytes = generate_detection_thumbnail(image_bytes, best_pred)
            
            if thumb_bytes:
                thumb_path = f"inference_temp/batch_thumb_{result_id}.jpg"
                r2_client.upload_file(thumb_bytes, thumb_path)
                
                supabase = get_supabase()
                supabase.table("inference_results").update({
                    "thumbnail_r2_path": thumb_path
                }).eq("id", result_id).execute()
                
                print(f"[Thumbnail] Generated detection thumbnail for batch {result_id}")
                return r2_client.generate_presigned_url(thumb_path)
            
            return None
            
        except Exception as e:
            print(f"[Thumbnail] Error generating batch detection thumbnail: {e}")
            return None
    
    async def delete_inference_result(self, result_id: str):
        """Delete an inference result with R2 cleanup."""
        try:
            # Delete from database and get record for cleanup
            deleted = db_delete_inference_result(result_id)
            
            if deleted:
                # Clean up R2 files
                r2_client = R2Client()
                
                # Delete input file
                if deleted.get("input_r2_path"):
                    try:
                        r2_client.delete_file(deleted["input_r2_path"])
                    except Exception as e:
                        print(f"Warning: Failed to delete input file: {e}")
                
                # Delete labels file
                if deleted.get("labels_r2_path"):
                    try:
                        r2_client.delete_file(deleted["labels_r2_path"])
                    except Exception as e:
                        print(f"Warning: Failed to delete labels file: {e}")
                
                print(f"Deleted inference result: {result_id}")
            
            # Refresh results list
            await self.load_user_results()
            
        except Exception as e:
            print(f"Error deleting inference result: {e}")
            import traceback
            traceback.print_exc()
    
    async def select_model_by_name(self, name: str):
        """Select a model by its name and persist preference."""
        self.selected_model_name = name
        self.model_dropdown_open = False  # Close dropdown on selection
        
        # Reset hybrid mode
        self.is_hybrid_mode = False
        self.selected_classifier_type = "detection"
        self.classifier_classes = []
        self.classifier_r2_path = ""
        
        # Check if it's a built-in model
        if name in self.builtin_models:
            self.selected_model_type = "builtin"
            self.selected_model_id = ""
        else:
            # Custom model
            self.selected_model_type = "custom"
            for model in self.available_models:
                if model["name"] == name:
                    self.selected_model_id = model["id"]
                    
                    # Check if this is a classifier model
                    # Need to query the training run to get model_type
                    training_run_id = model.get("training_run_id")
                    if training_run_id:
                        try:
                            supabase = get_supabase()
                            run_result = supabase.table("training_runs").select(
                                "model_type, classes_snapshot, artifacts_r2_prefix, config"
                            ).eq("id", training_run_id).single().execute()
                            
                            if run_result.data:
                                run_model_type = run_result.data.get("model_type", "detection")
                                if run_model_type == "classification":
                                    self.is_hybrid_mode = True
                                    self.selected_classifier_type = "classification"
                                    self.classifier_classes = run_result.data.get("classes_snapshot", []) or []
                                    # Get R2 path for classifier weights
                                    prefix = run_result.data.get("artifacts_r2_prefix", "")
                                    if prefix:
                                        # Use .pth for ConvNeXt, .pt for YOLO
                                        run_config = run_result.data.get("config", {}) or {}
                                        ext = ".pth" if run_config.get("classifier_backbone") == "convnext" else ".pt"
                                        self.classifier_r2_path = f"{prefix}/best{ext}"
                                    print(f"[Hybrid] Classifier detected: {self.classifier_classes}")
                        except Exception as e:
                            print(f"Warning: Could not check model type: {e}")
                    break
        
        # Clear previous predictions
        self.predictions = []
        self.predictions_by_frame = {}
        
        # Persist preference
        auth_state = await self.get_state(AuthState)
        if auth_state.user_id:
            update_user_preferences(auth_state.user_id, "playground", {
                "selected_model_name": name,
                "selected_model_type": self.selected_model_type,
            })
    
    async def handle_upload(self, files: list[rx.UploadFile]):
        """Handle file upload with format detection (image or video).
        
        Supports:
        - Single image → standard flow
        - Multiple images → batch mode
        - Single video → video flow
        """
        if not files:
            return
        
        # Set uploading state IMMEDIATELY
        self.is_uploading = True
        self.upload_stage = "reading"
        self.upload_progress = 0
        yield  # Force UI update to show progress
        
        try:
            # Check if multiple images uploaded
            image_files = [f for f in files if f.filename.lower().endswith(('.jpg', '.jpeg', '.png', '.webp', '.bmp'))]
            video_files = [f for f in files if f.filename.lower().endswith(('.mp4', '.mov', '.avi', '.webm', '.mkv'))]
            
            if len(image_files) > 1:
                # BATCH MODE: Multiple images
                self.batch_mode = True
                self.uploaded_file_type = "image"
                self.upload_stage = "processing"
                yield
                
                await self._handle_batch_image_upload(image_files)
                
            elif len(image_files) == 1:
                # Single image (original flow)
                self.batch_mode = False
                self.uploaded_images = []
                file = image_files[0]
                self.uploaded_filename = file.filename
                self.uploaded_file_type = "image"
                self.upload_stage = "processing"
                yield
                await self._handle_image_upload(file)
                
            elif len(video_files) >= 1:
                # Video (take first one)
                self.batch_mode = False
                self.uploaded_images = []
                file = video_files[0]
                self.uploaded_filename = file.filename
                self.uploaded_file_type = "video"
                self.upload_stage = "extracting_metadata"
                yield
                await self._handle_video_upload(file)
                
            else:
                self.prediction_error = f"Unsupported file format"
                return
            
        except Exception as e:
            print(f"Error handling upload: {e}")
            import traceback
            traceback.print_exc()
            self.prediction_error = f"Failed to upload file: {str(e)}"
        finally:
            self.is_uploading = False
    
    async def _handle_batch_image_upload(self, files: list[rx.UploadFile]):
        """Process multiple image uploads for batch inference."""
        from PIL import Image
        import io
        import base64
        
        auth_state = await self.get_state(AuthState)
        user_id = auth_state.user_id
        r2_client = R2Client()
        
        self.uploaded_images = []
        
        for idx, file in enumerate(files):
            self.upload_stage = f"Processing {idx+1}/{len(files)}"
            
            # Read file data
            file_data = await file.read()
            
            # Get image dimensions
            img = Image.open(io.BytesIO(file_data))
            width, height = img.size
            
            # Create thumbnail for preview (400px for gallery - fast loading)
            thumb = img.copy()
            thumb.thumbnail((400, 400))
            # Convert RGBA to RGB (JPEG doesn't support alpha channel)
            if thumb.mode in ('RGBA', 'LA', 'P'):
                thumb = thumb.convert('RGB')
            thumb_io = io.BytesIO()
            thumb.save(thumb_io, format="JPEG", quality=80)
            thumb_bytes = thumb_io.getvalue()
            base64_preview = f"data:image/jpeg;base64,{base64.b64encode(thumb_bytes).decode()}"
            
            # Upload original to R2
            r2_path = f"inference_temp/{user_id}/{uuid.uuid4()}.jpg"
            r2_client.upload_file(file_data, r2_path)
            
            # Upload thumbnail to R2 for fast gallery preview
            thumb_r2_path = f"inference_temp/{user_id}/thumb_{uuid.uuid4()}.jpg"
            r2_client.upload_file(thumb_bytes, thumb_r2_path)
            
            # Generate presigned URL for original (used for Modal inference)
            presigned_url = r2_client.generate_presigned_url(r2_path, expires_in=3600)
            
            self.uploaded_images.append({
                "filename": file.filename,
                "r2_path": r2_path,
                "thumbnail_r2_path": thumb_r2_path,  # For fast gallery preview
                "presigned_url": presigned_url,
                "base64_preview": base64_preview,
                "width": width,
                "height": height,
            })
        
        # Clear previous predictions
        self.predictions = []
        self.prediction_error = ""
        self.upload_stage = "ready"
        
        print(f"Batch upload complete: {len(self.uploaded_images)} images (with thumbnails)")
    
    async def _handle_image_upload(self, file: rx.UploadFile):
        """Process image upload."""
        # Read file data
        self.upload_stage = "reading"
        file_data = await file.read()
        
        # Get image dimensions
        self.upload_stage = "processing"
        from PIL import Image
        import io
        img = Image.open(io.BytesIO(file_data))
        self.image_width, self.image_height = img.size
        
        # Convert to base64 for preview
        import base64
        self.uploaded_image_data = f"data:image/jpeg;base64,{base64.b64encode(file_data).decode()}"
        
        # Upload to R2
        self.upload_stage = "uploading_storage"
        r2_client = R2Client()
        # Use authenticated user ID from AuthState
        auth_state = await self.get_state(AuthState)
        user_id = auth_state.user_id
        self.uploaded_r2_path = f"inference_temp/{user_id}/{uuid.uuid4()}.jpg"
        r2_client.upload_file(file_data, self.uploaded_r2_path)
        
        # Generate presigned URL
        self.uploaded_presigned_url = r2_client.generate_presigned_url(self.uploaded_r2_path, expires_in=3600)
        
        # Clear previous predictions
        self.predictions = []
        self.prediction_error = ""
        self.upload_stage = "ready"
        
        print(f"Image uploaded: {self.image_width}x{self.image_height}")
    
    async def _handle_video_upload(self, file: rx.UploadFile):
        """Process video upload and extract metadata + thumbnail."""
        import subprocess
        import tempfile
        import base64
        
        # Read file data
        self.upload_stage = "reading"
        file_data = await file.read()
        
        # Save to temp file for ffprobe
        with tempfile.NamedTemporaryFile(suffix=".mp4", delete=False) as tmp:
            tmp.write(file_data)
            temp_path = tmp.name
        
        try:
            # Extract metadata with ffprobe
            self.upload_stage = "extracting_metadata"
            result = subprocess.run(
                [
                    "ffprobe",
                    "-v", "quiet",
                    "-print_format", "json",
                    "-show_format",
                    "-show_streams",
                    temp_path
                ],
                capture_output=True,
                text=True,
                check=True
            )
            
            metadata = json.loads(result.stdout)
            
            # Get video stream info
            video_stream = next((s for s in metadata["streams"] if s["codec_type"] == "video"), None)
            if not video_stream:
                raise ValueError("No video stream found")
            
            # Extract metadata
            self.video_duration = float(metadata["format"]["duration"])
            
            # Parse FPS (can be in different formats like "30/1")
            fps_parts = video_stream["r_frame_rate"].split("/")
            self.video_fps = float(fps_parts[0]) / float(fps_parts[1])
            
            self.video_frame_count = int(video_stream.get("nb_frames", self.video_duration * self.video_fps))
            
            # Set default time range to full video
            self.video_start_time = 0.0
            self.video_end_time = self.video_duration
            
            print(f"Video metadata: {self.video_duration}s, {self.video_fps} FPS, {self.video_frame_count} frames")
            
            # Extract first frame as thumbnail
            thumbnail_path = temp_path.replace(".mp4", "_thumb.jpg")
            subprocess.run(
                [
                    "ffmpeg",
                    "-i", temp_path,
                    "-vframes", "1",
                    "-f", "image2",
                    "-y",
                    thumbnail_path
                ],
                capture_output=True,
                check=True
            )
            
            # Convert thumbnail to base64
            with open(thumbnail_path, "rb") as thumb_file:
                thumb_data = thumb_file.read()
                self.video_thumbnail_url = f"data:image/jpeg;base64,{base64.b64encode(thumb_data).decode()}"
            
            # Cleanup thumbnail
            import os
            os.unlink(thumbnail_path)
            
            # Resize video before upload (aspect-ratio preserving, no distortion)
            if self.video_target_resolution and int(self.video_target_resolution) > 0:
                resized_path = temp_path.replace(".mp4", "_resized.mp4")
                res = int(self.video_target_resolution)
                # Scale longest side to target, other proportionally (-2 ensures even numbers)
                # Apply target FPS if user selected non-original (via filter chain, not -r flag)
                target_fps = self.video_target_fps
                scale_filter = f"scale='if(gt(iw,ih),{res},-2)':'if(gt(iw,ih),-2,{res})'"
                if target_fps != "original" and target_fps.isdigit():
                    vf = f"{scale_filter},fps={target_fps}"
                else:
                    vf = scale_filter
                ffmpeg_cmd = [
                    "ffmpeg", "-i", temp_path,
                    "-vf", vf,
                    "-c:v", "libx264", "-preset", "fast", "-crf", "23",
                    "-c:a", "copy", "-y", resized_path
                ]
                try:
                    subprocess.run(ffmpeg_cmd, capture_output=True, check=True)
                    with open(resized_path, "rb") as rf:
                        file_data = rf.read()
                    fps_note = f" ({target_fps}fps)" if target_fps != "original" else ""
                    print(f"Video resized to {res}px{fps_note}: {len(file_data)} bytes")
                    os.unlink(resized_path)
                except subprocess.CalledProcessError as e:
                    print(f"Warning: ffmpeg resize failed, uploading original. stderr: {e.stderr}")

        finally:
            # Cleanup temp file
            import os
            os.unlink(temp_path)
        
        # Upload to R2
        self.upload_stage = "uploading_storage"
        r2_client = R2Client()
        # Use authenticated user ID from AuthState
        auth_state = await self.get_state(AuthState)
        user_id = auth_state.user_id
        self.uploaded_r2_path = f"inference_temp/{user_id}/{uuid.uuid4()}.mp4"
        r2_client.upload_file(file_data, self.uploaded_r2_path)
        
        # Generate presigned URL (for playback and inference)
        self.uploaded_presigned_url = r2_client.generate_presigned_url(self.uploaded_r2_path, expires_in=3600)
        self.uploaded_video_data = self.uploaded_presigned_url
        
        # Clear previous predictions
        self.predictions = []
        self.predictions_by_frame = {}
        self.prediction_error = ""
        self.upload_stage = "ready"
    
    def update_video_start_time(self, value: list[float]):
        """Update video start time from slider (legacy)."""
        self.video_start_time = value[0]
    
    def set_video_start_input(self, value: str):
        """Set video start time from text input."""
        try:
            v = round(max(0.0, min(self.video_duration, float(value))), 1)
            self.video_start_time = v
        except (ValueError, TypeError):
            pass
    
    def increment_video_start(self):
        self.video_start_time = round(min(self.video_duration, self.video_start_time + 0.5), 1)
    
    def decrement_video_start(self):
        self.video_start_time = round(max(0.0, self.video_start_time - 0.5), 1)
    
    def update_video_end_time(self, value: list[float]):
        """Update video end time from slider (legacy)."""
        self.video_end_time = value[0]
    
    def set_video_end_input(self, value: str):
        """Set video end time from text input."""
        try:
            v = round(max(0.0, min(self.video_duration, float(value))), 1)
            self.video_end_time = v
        except (ValueError, TypeError):
            pass
    
    def increment_video_end(self):
        self.video_end_time = round(min(self.video_duration, self.video_end_time + 0.5), 1)
    
    def decrement_video_end(self):
        self.video_end_time = round(max(0.0, self.video_end_time - 0.5), 1)
    
    def toggle_frame_skip(self):
        """Toggle frame skip on/off."""
        self.enable_frame_skip = not self.enable_frame_skip
    
    def update_frame_skip_interval(self, value: list[float]):
        """Update frame skip interval from slider."""
        self.frame_skip_interval = int(value[0])
    
    def set_frame_skip_interval(self, value: str):
        """Set frame skip interval from text input, clamped to 2-60."""
        try:
            val = int(value) if value else 5
            self.frame_skip_interval = max(2, min(60, val))
        except ValueError:
            pass  # Keep current value on invalid input
    
    async def set_classify_top_k(self, value: str):
        """Set classify_top_k from text input, clamped to 1-10, and save preference."""
        try:
            val = int(value) if value else 3
            self.classify_top_k = max(1, min(10, val))
            auth_state = await self.get_state(AuthState)
            if auth_state.user_id:
                update_user_preferences(auth_state.user_id, "playground", {
                    "classify_top_k": self.classify_top_k,
                })
        except ValueError:
            pass  # Keep current value on invalid input
    
    async def run_inference(self):
        """Route to image or video inference based on file type and model type."""
        if self.uploaded_file_type == "image":
            # Check for batch mode first
            if self.batch_mode and len(self.uploaded_images) > 0:
                # Batch inference
                if self.is_hybrid_mode:
                    async for _ in self._run_hybrid_batch_inference():
                        yield
                else:
                    async for _ in self._run_batch_inference():
                        yield
            elif self.is_hybrid_mode:
                # Single image hybrid
                async for _ in self._run_hybrid_image_inference():
                    yield
            else:
                # Single image detection
                async for _ in self._run_image_inference():
                    yield
        elif self.uploaded_file_type == "video":
            # Check if we're in hybrid mode (classifier selected)
            if self.is_hybrid_mode:
                yield InferenceState.start_hybrid_video_inference()
            else:
                # Standard detection inference
                yield InferenceState.start_video_inference()
        else:
            self.prediction_error = "Please upload an image or video first"
    
    async def _run_image_inference(self):
        """Run inference on image and save results to DB."""
        if not self.uploaded_presigned_url:
            self.prediction_error = "Please upload an image first"
            return
        
        self.is_predicting = True
        self.prediction_error = ""
        self.predictions = []
        self.inference_stage = "initializing"
        yield
        
        try:
            # Determine model ID
            self.inference_stage = "loading_model"
            yield
            model_id = self.selected_model_id if self.selected_model_type == "custom" else None
            model_name_or_id = self.selected_model_id if self.selected_model_type == "custom" else self.selected_model_name
            
            print(f"Running image inference: {self.selected_model_type} / {model_name_or_id}")
            
            # Build config and dispatch via router
            self.inference_stage = "processing"
            yield
            config = InferenceConfig(
                model_type="yolo-detect",
                input_type="image",
                model_name_or_id=model_name_or_id,
                # project_id could be added here for Local GPU support
            )
            result = dispatch_inference(
                config,
                image_url=self.uploaded_presigned_url,
                confidence=self.confidence_threshold,
            )
            
            # Update predictions
            self.predictions = result["predictions"]
            self.labels_txt = result["labels_txt"]
            
            print(f"Received {len(self.predictions)} predictions")
            
            # Save to database
            self.inference_stage = "saving"
            yield
            supabase = get_supabase()
            auth_state = await self.get_state(AuthState)
            user_id = auth_state.user_id
            
            # Save labels to R2
            r2_client = R2Client()
            labels_path = self.uploaded_r2_path.replace(".jpg", ".txt")
            r2_client.upload_file(self.labels_txt.encode('utf-8'), labels_path)
            
            # Create inference result record
            inference_record = create_inference_result(
                user_id=user_id,
                model_id=model_id,
                model_name=self.selected_model_name,
                input_type="image",
                input_filename=self.uploaded_filename,
                input_r2_path=self.uploaded_r2_path,
                predictions_json={"predictions": self.predictions},
                confidence_threshold=self.confidence_threshold,
                labels_r2_path=labels_path,
                detection_count=len(self.predictions),
                inference_settings={"sam3_conf": self.confidence_threshold},
            )
            
            if inference_record:
                self.last_result_id = inference_record["id"]
                print(f"Saved inference result: {self.last_result_id}")
                
                # Generate styled thumbnail from largest bounding box
                if self.predictions:
                    try:
                        from backend.core.thumbnail_generator import (
                            select_largest_detection,
                            generate_detection_thumbnail,
                        )
                        
                        best_pred, _ = select_largest_detection(self.predictions)
                        
                        if best_pred:
                            image_bytes = r2_client.download_file(self.uploaded_r2_path)
                            
                            if image_bytes:
                                thumb_bytes = generate_detection_thumbnail(image_bytes, best_pred)
                                
                                if thumb_bytes:
                                    thumb_path = self.uploaded_r2_path.replace(".jpg", "_thumb.jpg").replace(".png", "_thumb.jpg")
                                    r2_client.upload_file(thumb_bytes, thumb_path)
                                    
                                    supabase.table("inference_results").update({
                                        "thumbnail_r2_path": thumb_path
                                    }).eq("id", self.last_result_id).execute()
                                    
                                    print(f"[Thumbnail] Saved styled thumbnail for {self.last_result_id}")
                    except Exception as thumb_error:
                        print(f"[Thumbnail] Error generating thumbnail: {thumb_error}")
            
            # Refresh results list so new result appears
            await self.load_user_results()
            
        except Exception as e:
            print(f"Image inference error: {e}")
            import traceback
            traceback.print_exc()
            self.prediction_error = f"Inference failed: {str(e)}"
        
        finally:
            self.is_predicting = False
            self.inference_stage = ""
    
    async def _run_batch_inference(self):
        """Run batch inference on multiple images using YOLO detection and save to DB."""
        if not self.uploaded_images:
            self.prediction_error = "No images uploaded for batch inference"
            return
        
        self.is_predicting = True
        self.prediction_error = ""
        self.batch_progress_current = 0
        self.batch_progress_total = len(self.uploaded_images)
        self.inference_stage = "initializing"
        yield
        
        try:
            # Determine model
            self.inference_stage = "loading_model"
            yield
            model_name_or_id = self.selected_model_id if self.selected_model_type == "custom" else self.selected_model_name
            
            # Collect all presigned URLs
            image_urls = [img["presigned_url"] for img in self.uploaded_images]
            
            print(f"Running batch inference on {len(image_urls)} images...")
            
            # Build config and dispatch via router
            self.inference_stage = "processing"
            yield
            config = InferenceConfig(
                model_type="yolo-detect",
                input_type="batch",
                model_name_or_id=model_name_or_id,
                # project_id could be added here for Local GPU support
            )
            results = dispatch_inference(
                config,
                image_urls=image_urls,
                confidence=self.confidence_threshold,
            )
            
            # Build batch_images list for DB storage
            batch_images = []
            predictions_list = []
            total_detections = 0
            
            for result in results:
                idx = result.get("index", 0)
                if idx < len(self.uploaded_images):
                    img_meta = self.uploaded_images[idx]
                    batch_images.append({
                        "filename": img_meta["filename"],
                        "r2_path": img_meta["r2_path"],
                        "thumbnail_r2_path": img_meta.get("thumbnail_r2_path", ""),
                        "width": img_meta.get("width", 0),
                        "height": img_meta.get("height", 0),
                    })
                    predictions_list.append(result.get("predictions", []))
                    total_detections += result.get("detection_count", 0)
            
            print(f"Batch inference complete: {len(batch_images)} images, {total_detections} total detections")
            
            # Save to Supabase
            self.inference_stage = "saving"
            yield
            
            auth_state = await self.get_state(AuthState)
            user_id = auth_state.user_id
            
            inference_record = create_inference_result(
                user_id=user_id,
                model_id=self.selected_model_id if self.selected_model_type == "custom" else None,
                model_name=self.selected_model_name,
                input_type="batch",
                input_filename=f"{len(batch_images)} images",
                input_r2_path=batch_images[0]["r2_path"] if batch_images else "",
                predictions_json={"batch_predictions": predictions_list},
                confidence_threshold=self.confidence_threshold,
                detection_count=total_detections,
                batch_images=batch_images,
                inference_settings={"sam3_conf": self.confidence_threshold},
            )
            
            if inference_record:
                self.last_result_id = inference_record["id"]
                print(f"Saved batch inference result: {self.last_result_id}")
                
                # Generate styled thumbnail from largest bounding box across batch
                if any(predictions_list):
                    try:
                        from backend.core.thumbnail_generator import (
                            select_best_batch_detection,
                            generate_detection_thumbnail,
                        )
                        
                        r2_client = R2Client()
                        best_idx, best_pred, _ = select_best_batch_detection(predictions_list)
                        
                        if best_idx is not None and best_pred:
                            img_r2_path = batch_images[best_idx]["r2_path"]
                            image_bytes = r2_client.download_file(img_r2_path)
                            
                            if image_bytes:
                                thumb_bytes = generate_detection_thumbnail(image_bytes, best_pred)
                                
                                if thumb_bytes:
                                    thumb_path = f"inference_temp/{user_id}/batch_thumb_{self.last_result_id}.jpg"
                                    r2_client.upload_file(thumb_bytes, thumb_path)
                                    
                                    supabase = get_supabase()
                                    supabase.table("inference_results").update({
                                        "thumbnail_r2_path": thumb_path
                                    }).eq("id", self.last_result_id).execute()
                                    
                                    print(f"[Thumbnail] Saved styled thumbnail for batch {self.last_result_id}")
                    except Exception as thumb_error:
                        print(f"[Thumbnail] Error generating batch thumbnail: {thumb_error}")
            
            # Refresh results list
            await self.load_user_results()
            
            # Clear batch mode state
            self.batch_mode = False
            self.uploaded_images = []
            
            self.inference_stage = "complete"
            
        except Exception as e:
            print(f"Batch inference error: {e}")
            import traceback
            traceback.print_exc()
            self.prediction_error = f"Batch inference failed: {str(e)}"
        
        finally:
            self.is_predicting = False
            self.inference_stage = ""
    
    async def _run_hybrid_batch_inference(self):
        """Run batch hybrid inference (SAM3 + Classifier) and save to DB."""
        if not self.uploaded_images:
            self.prediction_error = "No images uploaded for batch inference"
            return
        
        self.is_predicting = True
        self.prediction_error = ""
        self.batch_progress_current = 0
        self.batch_progress_total = len(self.uploaded_images)
        self.debug_crop_url = ""  # Clear previous debug crop
        self.inference_stage = "initializing"
        yield
        
        try:
            # Determine project for routing
            self.inference_stage = "loading_model"
            yield
            project_id = get_project_id_from_model(self.selected_model_id)
            
            # Get auth state for user_id (needed for job dispatch and saving)
            auth_state = await self.get_state(AuthState)
            user_id = auth_state.user_id
            
            # Fallback: extract project_id from classifier R2 path (format: projects/{uuid}/runs/...)
            if not project_id and self.classifier_r2_path.startswith("projects/"):
                parts = self.classifier_r2_path.split("/")
                if len(parts) >= 2:
                    project_id = parts[1]
                    print(f"[Hybrid Batch] Extracted project_id from R2 path: {project_id}")
            
            # Collect all presigned URLs
            image_urls = [img["presigned_url"] for img in self.uploaded_images]
            
            print(f"Running hybrid batch inference on {len(image_urls)} images...")
            print(f"SAM3 prompts: {self.sam3_prompts}")
            print(f"Classifier classes: {self.classifier_classes}")
            print(f"Routing via project: {project_id}")
            
            if not project_id:
                raise Exception("Cannot determine project for model routing. Please select a model from a project.")
            
            # Dispatch through job router (routes to Modal or local GPU)
            self.inference_stage = "processing"
            yield
            # Determine SAM3 model path (None = pretrained default)
            _sam3_model_path = f"/models/{self.selected_sam3_model}" if self.selected_sam3_model != "sam3.pt" else None
            
            results = dispatch_hybrid_inference_batch(
                project_id=project_id,
                image_urls=image_urls,
                sam3_prompts=self.sam3_prompts,
                classifier_r2_path=self.classifier_r2_path,
                classifier_classes=self.classifier_classes,
                prompt_class_map=self.prompt_class_map,
                confidence_threshold=self.confidence_threshold,
                classifier_confidence=self.classifier_confidence,
                # Action-level target selection
                target=self.compute_target,
                user_id=user_id,
                machine_name=self.selected_machine if self.compute_target == "local" else None,
                sam3_model_path=_sam3_model_path,
                sam3_imgsz=int(self.sam3_imgsz),
            )
            
            # Build batch_images list for DB storage
            batch_images = []
            predictions_list = []
            masks_list = []  # Store masks per image
            total_detections = 0
            
            for result in results:
                idx = result.get("index", 0)
                if idx < len(self.uploaded_images):
                    img_meta = self.uploaded_images[idx]
                    batch_images.append({
                        "filename": img_meta["filename"],
                        "r2_path": img_meta["r2_path"],
                        "thumbnail_r2_path": img_meta.get("thumbnail_r2_path", ""),
                        "width": img_meta.get("width", 0),
                        "height": img_meta.get("height", 0),
                    })
                    preds = result.get("predictions", [])
                    masks = result.get("masks", [])
                    predictions_list.append(preds)
                    masks_list.append(masks)
                    total_detections += len(preds)
            
            print(f"Hybrid batch inference complete: {len(batch_images)} images, {total_detections} total detections")
            
            # Upload debug crop from first image with detections
            for result in results:
                debug_crop_b64 = result.get("debug_crop")
                if debug_crop_b64:
                    import base64
                    debug_crop_bytes = base64.b64decode(debug_crop_b64)
                    try:
                        r2_client_dc = R2Client()
                        crop_path = f"inference_temp/{self.uploaded_images[0]['r2_path'].split('/')[-1].split('.')[0]}_debug_crop.jpg"
                        r2_client_dc.upload_file(debug_crop_bytes, crop_path, content_type="image/jpeg")
                        self.debug_crop_url = r2_client_dc.generate_presigned_url(crop_path, expires_in=3600)
                        print(f"[Debug Crop] Saved first batch crop to {crop_path}")
                    except Exception as dc_err:
                        print(f"[Debug Crop] Error saving batch crop: {dc_err}")
                    break  # Only need the first crop)
            
            # Save to Supabase
            self.inference_stage = "saving"
            yield
            
            # auth_state and user_id already retrieved above
            
            print(f"[Batch Save] Saving {len(batch_images)} images, {total_detections} detections to Supabase...")
            print(f"[Batch Save] user_id={user_id}, model_name={self.selected_model_name}")
            
            try:
                inference_record = create_inference_result(
                    user_id=user_id,
                    model_id=self.selected_model_id if self.selected_model_type == "custom" else None,
                    model_name=self.selected_model_name,
                    input_type="batch",
                    input_filename=f"{len(batch_images)} images",
                    input_r2_path=batch_images[0]["r2_path"] if batch_images else "",
                    predictions_json={"batch_predictions": predictions_list, "batch_masks": masks_list},
                    confidence_threshold=self.confidence_threshold,
                    detection_count=total_detections,
                    batch_images=batch_images,
                    inference_settings={"species_conf": self.classifier_confidence, "sam3_conf": self.confidence_threshold, "resize_px": int(self.video_target_resolution), "sam3_px": int(self.sam3_imgsz)},
                )
                
                if inference_record:
                    self.last_result_id = inference_record["id"]
                    print(f"[Batch Save] SUCCESS: Saved hybrid batch inference result: {self.last_result_id}")
                    
                    # Generate styled thumbnail from largest mask across batch
                    if any(masks_list):
                        try:
                            from backend.core.thumbnail_generator import (
                                select_best_batch_detection,
                                generate_hybrid_thumbnail,
                            )
                            
                            best_idx, best_pred, best_mask = select_best_batch_detection(
                                predictions_list, masks_list
                            )
                            
                            if best_idx is not None and best_pred and best_mask:
                                # Download the winning image from R2
                                r2_client = R2Client()
                                img_r2_path = batch_images[best_idx]["r2_path"]
                                image_bytes = r2_client.download_file(img_r2_path)
                                
                                if image_bytes:
                                    thumb_bytes = generate_hybrid_thumbnail(image_bytes, best_pred, best_mask)
                                    
                                    if thumb_bytes:
                                        # Upload thumbnail to R2
                                        thumb_path = f"inference_temp/{user_id}/batch_thumb_{self.last_result_id}.jpg"
                                        r2_client.upload_file(thumb_bytes, thumb_path)
                                        
                                        # Update DB with thumbnail path
                                        supabase = get_supabase()
                                        supabase.table("inference_results").update({
                                            "thumbnail_r2_path": thumb_path
                                        }).eq("id", self.last_result_id).execute()
                                        
                                        print(f"[Thumbnail] Saved styled thumbnail for batch {self.last_result_id}")
                        except Exception as thumb_error:
                            print(f"[Thumbnail] Error generating batch thumbnail: {thumb_error}")
                else:
                    print(f"[Batch Save] WARNING: create_inference_result returned None")
            except Exception as save_error:
                print(f"[Batch Save] ERROR: Failed to save to Supabase: {save_error}")
                import traceback
                traceback.print_exc()
            
            # Refresh results list
            await self.load_user_results()
            
            # Clear batch mode state
            self.batch_mode = False
            self.uploaded_images = []
            
            self.inference_stage = "complete"
            
        except Exception as e:
            print(f"Hybrid batch inference error: {e}")
            import traceback
            traceback.print_exc()
            self.prediction_error = f"Hybrid batch inference failed: {str(e)}"
        
        finally:
            self.is_predicting = False
            self.inference_stage = ""
    
    async def _run_video_inference(self):
        """Legacy method - now handled by start_video_inference background event."""
        # This should not be called directly anymore
        pass

    @rx.event(background=True)
    async def start_video_inference(self):
        """Background event to run video inference with progress tracking."""
        import asyncio
        
        async with self:
            if not self.uploaded_presigned_url:
                self.prediction_error = "Please upload a video first"
                return
            
            self.is_predicting = True
            self.prediction_error = ""
            self.predictions_by_frame = {}
            self.inference_stage = "initializing"
        yield # Push to frontend
        
        try:
            # Get the Modal function
            cls = modal.Cls.from_name("yolo-inference", "YOLOInference")
            
            async with self:
                # Determine model type and ID
                model_id = self.selected_model_id if self.selected_model_type == "custom" else None
                model_name_or_id = self.selected_model_id if self.selected_model_type == "custom" else self.selected_model_name
                
                frame_skip = self.frame_skip_interval if self.enable_frame_skip else 1
                
                print(f"Running video inference: {self.selected_model_type} / {model_name_or_id}")
                print(f"Time range: {self.video_start_time}s - {self.video_end_time}s, frame skip: {frame_skip}")
                
                # 1. Create pending record
                auth_state = await self.get_state(AuthState)
                user_id = auth_state.user_id
                
                pending_record = create_pending_inference_result(
                    user_id=user_id,
                    model_id=model_id,
                    model_name=self.selected_model_name,
                    input_type="video",
                    input_filename=self.uploaded_filename,
                    input_r2_path=self.uploaded_r2_path,
                    confidence_threshold=self.confidence_threshold,
                    video_start_time=self.video_start_time,
                    video_end_time=self.video_end_time,
                    inference_settings={"sam3_conf": self.confidence_threshold},
                )
                
                if not pending_record:
                    raise Exception("Failed to create pending record")
                
                inference_id = pending_record["id"]
                
                # Start polling state
                self.processing_inference_id = inference_id
                self.is_polling_inference = True
                self.inference_progress_current = 0
                self.inference_progress_total = 100
                self.inference_progress_status = "processing"
                self.inference_stage = "processing"
                
                # Store values needed outside async with
                _model_type = self.selected_model_type
                _confidence = self.confidence_threshold
                _start_time = self.video_start_time
                _end_time = self.video_end_time
                _r2_path = self.uploaded_r2_path
            yield # Push to frontend
            
            # Regenerate fresh presigned URL to avoid expiration issues
            r2_client = R2Client()
            _presigned_url = r2_client.generate_presigned_url(_r2_path, expires_in=3600)
            
            # 2. Start Modal function in a separate thread to avoid blocking the loop
            print(f"[Inference] Starting Modal job for {inference_id}")
            # Use create_task so we can check .done() in the polling loop
            modal_task = asyncio.create_task(
                asyncio.to_thread(
                    cls().predict_video.remote,
                    model_type=_model_type,
                    model_name_or_id=model_name_or_id,
                    video_url=_presigned_url,
                    confidence=_confidence,
                    start_time=_start_time,
                    end_time=_end_time,
                    frame_skip=frame_skip,
                    inference_result_id=inference_id,
                )
            )
            
            # 3. Poll for progress while Modal job is running
            supabase = get_supabase()
            while not modal_task.done():
                try:
                    res = supabase.table("inference_results").select(
                        "progress_current, progress_total, inference_status"
                    ).eq("id", inference_id).single().execute()
                    
                    if res.data:
                        progress_current = res.data.get("progress_current", 0)
                        progress_total = res.data.get("progress_total", 100)
                        db_status = res.data.get("inference_status", "processing")
                        
                        async with self:
                            self.inference_progress_current = progress_current
                            self.inference_progress_total = progress_total
                            self.inference_progress_status = db_status
                        yield # Force UI update
                except Exception as poll_err:
                    print(f"[Polling Error] {poll_err}")
                
                await asyncio.sleep(0.5)
            
            # 4. Wait for Modal job to complete and get final result
            result = await modal_task
            
            async with self:
                # Update predictions
                self.predictions_by_frame = result["predictions_by_frame"]
                total_detections = result["total_detections"]
                frames_processed = result["total_frames_processed"]
                
                print(f"Processed {frames_processed} frames, {total_detections} detections")
                
                # Save predictions_by_frame as JSON to R2
                r2_client = R2Client()
                labels_path = _r2_path.replace(".mp4", "_labels.json")
                labels_json = json.dumps(result["predictions_by_frame"])
                r2_client.upload_file(labels_json.encode('utf-8'), labels_path)
                
                # 5. Mark as complete
                complete_inference_result(
                    result_id=inference_id,
                    predictions_json=self.predictions_by_frame,
                    labels_r2_path=labels_path,
                    video_fps=result["fps"],
                    video_total_frames=frames_processed,
                    detection_count=total_detections,
                )
                
                self.last_result_id = inference_id
                
                # Refresh results list
                await self.load_user_results()
                
                self.is_predicting = False
                self.is_polling_inference = False
                self.inference_progress_current = frames_processed
                self.inference_progress_total = frames_processed
                self.inference_progress_status = "completed"
                self.inference_stage = ""
            yield # Final UI update
                
        except Exception as e:
            print(f"Video inference error: {e}")
            import traceback
            traceback.print_exc()
            async with self:
                self.prediction_error = f"Inference failed: {str(e)}"
                self.is_predicting = False
                self.is_polling_inference = False
                self.inference_stage = ""
                if self.processing_inference_id:
                     complete_inference_result(
                         result_id=self.processing_inference_id,
                         predictions_json={},
                         error_message=str(e)
                     )

    async def _run_native_hybrid_video_inference(self):
        """
        Run hybrid video inference using SAM3's native video tracking.
        
        Uses SAM3VideoSemanticPredictor for temporal consistency:
        - Processes ALL frames with memory-based tracking
        - Each unique track is classified once
        - Classifications propagate to all frames via track IDs
        """
        import asyncio
        
        async with self:
            print(f"[Hybrid Video] Native SAM3 video tracking approach")
            print(f"  SAM3 prompts: {self.sam3_prompts}")
            print(f"  Classifier: {self.classifier_r2_path}")
            print(f"  Time range: {self.video_start_time}s - {self.video_end_time}s")
            
            # Create pending record
            auth_state = await self.get_state(AuthState)
            user_id = auth_state.user_id
            
            pending_record = create_pending_inference_result(
                user_id=user_id,
                model_id=self.selected_model_id if self.selected_model_type == "custom" else None,
                model_name=f"Hybrid ({self.selected_model_name})",
                input_type="video",
                input_filename=self.uploaded_filename,
                input_r2_path=self.uploaded_r2_path,
                confidence_threshold=self.confidence_threshold,
                video_start_time=self.video_start_time,
                video_end_time=self.video_end_time,
                inference_settings={"species_conf": self.classifier_confidence, "sam3_conf": self.confidence_threshold, "resize_px": int(self.video_target_resolution), "sam3_px": int(self.sam3_imgsz)},
            )
            
            if not pending_record:
                raise Exception("Failed to create pending record")
            
            inference_id = pending_record["id"]
            self.processing_inference_id = inference_id
            self.is_polling_inference = True
            self.inference_progress_current = 0
            self.inference_progress_total = 100
            self.inference_progress_status = "processing video (SAM3 tracking)"
            self.inference_stage = "processing"
            
            # Store values for use outside async with
            _sam3_prompts = self.sam3_prompts
            _classifier_r2_path = self.classifier_r2_path
            _classifier_classes = self.classifier_classes
            _prompt_class_map = self.prompt_class_map
            _confidence = self.confidence_threshold
            _classifier_confidence = self.classifier_confidence
            _start_time = self.video_start_time
            _end_time = self.video_end_time
            _r2_path = self.uploaded_r2_path
            _video_fps = self.video_fps
            _sam3_imgsz = int(self.sam3_imgsz)
            # Action-level target selection
            _compute_target = self.compute_target
            _user_id = user_id
            _machine_name = self.selected_machine if self.compute_target == "local" else None
        yield
        
        try:
            # Generate fresh presigned URL
            r2_client = R2Client()
            video_url = r2_client.generate_presigned_url(_r2_path, expires_in=3600)
            
            # Dispatch through job router (routes to Modal or local GPU)
            project_id = get_project_id_from_model(self.selected_model_id)
            
            # Fallback: extract project_id from classifier R2 path (format: projects/{uuid}/runs/...)
            if not project_id and _classifier_r2_path.startswith("projects/"):
                parts = _classifier_r2_path.split("/")
                if len(parts) >= 2:
                    project_id = parts[1]
                    print(f"[Hybrid Video] Extracted project_id from R2 path: {project_id}")
            
            print(f"[Hybrid Video] Dispatching hybrid_inference_video (project: {project_id})...")
            
            if not project_id:
                raise Exception("Cannot determine project for model routing. Please select a model from a project.")
            
            # Determine SAM3 model path (None = pretrained default)
            _sam3_model_path = f"/models/{self.selected_sam3_model}" if self.selected_sam3_model != "sam3.pt" else None
            
            dispatch_result = await asyncio.to_thread(
                dispatch_hybrid_inference_video,
                project_id=project_id,
                video_url=video_url,
                sam3_prompts=_sam3_prompts,
                classifier_r2_path=_classifier_r2_path,
                classifier_classes=_classifier_classes,
                prompt_class_map=_prompt_class_map,
                confidence_threshold=_confidence,
                classifier_confidence=_classifier_confidence,
                start_time=_start_time,
                end_time=_end_time,
                frame_skip=1,  # Always 1 for native video
                classify_top_k=self.classify_top_k,
                sam3_imgsz=_sam3_imgsz,
                # Action-level target selection
                target=_compute_target,
                user_id=_user_id,
                machine_name=_machine_name,
                result_id=inference_id,  # For Modal progress tracking
                sam3_model_path=_sam3_model_path,
            )
            
            # Both SSH and Modal now return async — poll for progress
            if isinstance(dispatch_result, dict) and dispatch_result.get("async"):
                
                if dispatch_result.get("modal"):
                    # ── Modal cloud path: poll Supabase DB ──
                    print(f"[Hybrid Video] Modal job spawned, polling Supabase for progress...")
                    
                    import time
                    result = None
                    poll_start = time.monotonic()
                    ever_progressed = False  # True once status moves past 'queued'
                    
                    while True:
                        await asyncio.sleep(2)
                        
                        db_progress = await asyncio.to_thread(
                            get_inference_progress, inference_id
                        )
                        
                        if db_progress:
                            status = db_progress.get("inference_status", "processing")
                            progress_status = db_progress.get("progress_status", "queued")
                            current = db_progress.get("progress_current", 0)
                            total = db_progress.get("progress_total", 0)
                            
                            # Track if we ever got past 'queued'
                            if status != "processing" or progress_status != "queued":
                                if current > 0 or progress_status not in ("queued", "processing"):
                                    ever_progressed = True
                            
                            async with self:
                                if total > 0:
                                    self.inference_progress_current = current
                                    self.inference_progress_total = total
                                self.inference_progress_status = progress_status
                            yield
                            
                            if status == "completed":
                                # predictions_json contains the full result dict
                                # written by the Modal job — use it directly
                                predictions_json = db_progress.get("predictions_json", {})
                                result = predictions_json if isinstance(predictions_json, dict) else {"success": True, "frame_results": []}
                                break
                            elif status == "failed":
                                error_msg = progress_status if progress_status.startswith("failed:") else "Modal inference job failed"
                                raise Exception(error_msg)
                            
                            # Stale-queued detection: if job stays 'queued' for 60s
                            # without any progress, the Modal container likely crashed
                            # before it could write to DB
                            if not ever_progressed and (time.monotonic() - poll_start) > 60:
                                raise Exception(
                                    "Modal job appears to have crashed — no progress received after 60s. "
                                    "Check Modal dashboard for container logs."
                                )
                    
                else:
                    # ── SSH local path: poll log file ──
                    job_ref = dispatch_result["job_ref"]
                    ssh_config = dispatch_result["ssh_config"]
                
                    print(f"[Hybrid Video] Async SSH job started: {job_ref}")
                    print(f"[Hybrid Video] Polling SSH for progress...")
                    
                    from backend.ssh_client import SSHWorkerClient
                
                    # Poll until job completes
                    result = None
                    poll_client = SSHWorkerClient(
                        host=ssh_config["host"],
                        port=ssh_config["port"],
                        user=ssh_config["user"],
                    )
                
                    try:
                        poll_client.connect()
                    
                        while True:
                            await asyncio.sleep(2)
                        
                            job_status = await asyncio.to_thread(
                                poll_client.check_async_job, job_ref
                            )
                        
                            # Update progress from PROGRESS: lines
                            progress = job_status.get("progress")
                            if progress:
                                async with self:
                                    current = progress.get("current", 0)
                                    total = progress.get("total", 0)
                                    status = progress.get("status", "processing")
                                    
                                    if total > 0:
                                        self.inference_progress_current = current
                                        self.inference_progress_total = total
                                    self.inference_progress_status = status
                                yield
                            
                            if not job_status["running"]:
                                result = job_status.get("result")
                                if not result:
                                    # Try to get error from output
                                    output = job_status.get("output", "")
                                    raise Exception(
                                        f"Remote inference job finished with no result.\n"
                                        f"Last output: {output[-500:] if output else 'none'}"
                                    )
                                break
                    finally:
                        poll_client.close()
            else:
                # Synchronous result (should not happen anymore, but keep as fallback)
                result = dispatch_result
            
            if not result.get("success", False):
                raise Exception(result.get("error", "Unknown error in hybrid_inference_video"))
            
            # If the result contains an R2 reference (large video results),
            # download the full result from R2
            if "r2_result_path" in result:
                r2_result_path = result["r2_result_path"]
                print(f"[Hybrid Video] Downloading full result from R2: {r2_result_path}")
                full_result_bytes = r2_client.download_file(r2_result_path)
                result = json.loads(full_result_bytes)
                # Clean up the temp R2 file
                try:
                    r2_client.delete_file(r2_result_path)
                except Exception:
                    pass  # Non-critical cleanup
            
            print(f"[Hybrid Video] Native inference complete")
            print(f"  Frames: {result.get('processed_frames', 0)}")
            print(f"  Predictions: {result.get('total_predictions', 0)}")
            print(f"  Unique tracks: {result.get('unique_tracks', 0)}")
            print(f"  Classified tracks: {result.get('classified_tracks', 0)}")
            
            # Convert frame_results format to predictions_by_frame dict
            predictions_by_frame = {}
            masks_by_frame = {}
            total_detections = 0
            
            for frame_data in result.get("frame_results", []):
                frame_num = frame_data.get("frame_number", 0)
                preds = frame_data.get("predictions", [])
                masks = frame_data.get("masks", [])
                
                # Use string keys for Reflex state compatibility (dict[str, ...])
                frame_key = str(frame_num)
                predictions_by_frame[frame_key] = preds
                masks_by_frame[frame_key] = masks
                total_detections += len(preds)
            
            # Save results to R2 (labels file)
            labels_path = _r2_path.replace(".mp4", "_hybrid_labels.json")
            
            # Build crop metadata for persistence (r2_path only, no bytes/URLs)
            classification_crops = result.get("classification_crops", [])
            crop_metadata = [
                {
                    "r2_path": c.get("r2_path", ""),
                    "class_name": c.get("class_name", "Unknown"),
                    "confidence": c.get("confidence", 0.0),
                    "track_id": c.get("track_id", 0),
                }
                for c in classification_crops
                if c.get("r2_path")
            ]
            
            labels_json = json.dumps({
                "predictions_by_frame": predictions_by_frame,
                "masks_by_frame": masks_by_frame,
                "classification_crops": crop_metadata,
            })
            r2_client.upload_file(labels_json.encode('utf-8'), labels_path)
            
            # Mark inference as complete in DB
            # For Modal path, the job already wrote predictions_json to DB,
            # but we still need to set labels_r2_path
            complete_inference_result(
                result_id=inference_id,
                predictions_json=predictions_by_frame,
                labels_r2_path=labels_path,
                video_fps=result.get("fps", _video_fps),
                video_total_frames=result.get("processed_frames", 0),
                detection_count=total_detections,
            )
            
            async with self:
                self.predictions_by_frame = predictions_by_frame
                self.last_result_id = inference_id
                await self.load_user_results()
                
                # Use classification crop URLs from result (uploaded directly by inference machine)
                classification_crops = result.get("classification_crops", [])
                if classification_crops:
                    # Regenerate presigned URLs locally — the remote machine's
                    # presigned URLs use its own R2 endpoint which may not have
                    # browser-compatible CORS headers, causing OpaqueResponseBlocking.
                    r2_client_crops = R2Client()
                    crop_urls = []
                    for crop in classification_crops:
                        r2_path = crop.get("r2_path", "")
                        if r2_path:
                            try:
                                local_url = r2_client_crops.generate_presigned_url(r2_path, expires_in=3600)
                            except Exception as e:
                                print(f"[Classification Crops] Failed to generate URL for {r2_path}: {e}")
                                local_url = crop.get("url", "")
                        else:
                            local_url = crop.get("url", "")
                        if local_url:
                            crop_urls.append({
                                "url": local_url,
                                "class_name": crop.get("class_name", "Unknown"),
                                "confidence": crop.get("confidence", 0.0),
                                "track_id": crop.get("track_id", 0),
                            })
                    self.classification_crop_urls = crop_urls
                    print(f"[Classification Crops] {len(self.classification_crop_urls)} crops (locally signed URLs)")
                
                self.is_predicting = False
                self.is_polling_inference = False
                self.inference_progress_current = result.get("processed_frames", 0)
                self.inference_progress_total = result.get("processed_frames", 0)
                self.inference_progress_status = "completed"
                self.inference_stage = ""
            yield
            
            print(f"[Hybrid Video] Native mode complete! {total_detections} detections")
            
        except Exception as e:
            print(f"Native hybrid video inference error: {e}")
            import traceback
            traceback.print_exc()
            async with self:
                self.prediction_error = f"Hybrid inference failed: {str(e)}"
                self.is_predicting = False
                self.is_polling_inference = False
                self.inference_stage = ""
                if self.processing_inference_id:
                    complete_inference_result(
                        result_id=self.processing_inference_id,
                        predictions_json={},
                        error_message=str(e)
                    )

    @rx.event(background=True)
    async def start_hybrid_video_inference(self):
        """
        Background event to run hybrid SAM3 + Classifier video inference.
        
        Routes based on frame_skip setting:
        - frame_skip=1: Use hybrid_inference_video (SAM3 native video tracking)
        - frame_skip>1: Use hybrid_inference_batch (extract frames, batch process)
        """
        import asyncio
        import subprocess
        import tempfile
        import uuid
        from pathlib import Path
        
        async with self:
            if not self.uploaded_r2_path:
                self.prediction_error = "Please upload a video first"
                return
            
            if not self.classifier_r2_path:
                self.prediction_error = "No classifier model path found"
                return
            
            if not self.sam3_prompts:
                self.prediction_error = "Please enter SAM3 prompts (e.g., 'mammal, bird')"
                return
            
            self.is_predicting = True
            self.prediction_error = ""
            self.predictions_by_frame = {}
            self.classification_crop_urls = []  # Clear previous crop gallery
            self.inference_stage = "initializing"
        yield
        
        # Determine routing: native video vs batch
        async with self:
            frame_skip = self.frame_skip_interval if self.enable_frame_skip else 1
            use_native_video = (frame_skip == 1)  # Use SAM3 video tracking when no skip
        
        if use_native_video:
            # === NATIVE VIDEO PATH: Use SAM3VideoSemanticPredictor ===
            async for _ in self._run_native_hybrid_video_inference():
                yield
            return
        
        # === BATCH PATH: Extract frames, upload, batch process ===
        # Create temp directory for frame extraction
        temp_dir = Path(tempfile.mkdtemp(prefix="hybrid_frames_"))
        session_id = str(uuid.uuid4())[:8]
        
        try:
            async with self:
                print(f"[Hybrid Video] Batch extraction approach (frame_skip={frame_skip})")
                print(f"  SAM3 prompts: {self.sam3_prompts}")
                print(f"  Classifier: {self.classifier_r2_path}")
                print(f"  Time range: {self.video_start_time}s - {self.video_end_time}s")
                print(f"  Frame skip: {frame_skip}")
                
                # Create pending record
                auth_state = await self.get_state(AuthState)
                user_id = auth_state.user_id
                
                pending_record = create_pending_inference_result(
                    user_id=user_id,
                    model_id=self.selected_model_id if self.selected_model_type == "custom" else None,
                    model_name=f"Hybrid ({self.selected_model_name})",
                    input_type="video",
                    input_filename=self.uploaded_filename,
                    input_r2_path=self.uploaded_r2_path,
                    confidence_threshold=self.confidence_threshold,
                    video_start_time=self.video_start_time,
                    video_end_time=self.video_end_time,
                    inference_settings={"species_conf": self.classifier_confidence, "sam3_conf": self.confidence_threshold, "resize_px": int(self.video_target_resolution), "sam3_px": int(self.sam3_imgsz)},
                )
                
                if not pending_record:
                    raise Exception("Failed to create pending record")
                
                inference_id = pending_record["id"]
                self.processing_inference_id = inference_id
                self.is_polling_inference = True
                self.inference_progress_current = 0
                self.inference_progress_total = 100
                self.inference_progress_status = "downloading video"
                self.inference_stage = "downloading"
                
                # Store values for use outside async with
                _sam3_prompts = self.sam3_prompts
                _classifier_r2_path = self.classifier_r2_path
                _classifier_classes = self.classifier_classes
                _prompt_class_map = self.prompt_class_map
                _confidence = self.confidence_threshold
                _classifier_confidence = self.classifier_confidence
                _start_time = self.video_start_time
                _end_time = self.video_end_time
                _r2_path = self.uploaded_r2_path
                _video_fps = self.video_fps
            yield
            
            # === Step 1: Download video from R2 ===
            r2_client = R2Client()
            video_path = temp_dir / "video.mp4"
            
            print(f"[Step 1/5] Downloading video from R2...")
            video_bytes = r2_client.download_file(_r2_path)
            video_path.write_bytes(video_bytes)
            print(f"  Downloaded {len(video_bytes)} bytes")
            
            async with self:
                self.inference_progress_current = 10
                self.inference_progress_status = "extracting frames"
                self.inference_stage = "extracting"
            yield
            
            # === Step 2: Extract frames with FFmpeg ===
            frames_dir = temp_dir / "frames"
            frames_dir.mkdir()
            
            # Build FFmpeg command for frame extraction with skip
            # -ss: start time, -to: end time
            # -vf select: pick every Nth frame
            # -q:v 2: high quality JPEG (1-31, lower is better)
            ffmpeg_cmd = [
                "ffmpeg",
                "-ss", str(_start_time),
                "-to", str(_end_time),
                "-i", str(video_path),
                "-vf", f"select=not(mod(n\\,{frame_skip}))",
                "-vsync", "vfr",
                "-q:v", "2",  # Low loss JPEG
                str(frames_dir / "frame_%05d.jpg"),
                "-y",
            ]
            
            print(f"[Step 2/5] Extracting frames with FFmpeg...")
            print(f"  Command: {' '.join(ffmpeg_cmd)}")
            
            result = await asyncio.to_thread(
                subprocess.run,
                ffmpeg_cmd,
                capture_output=True,
                text=True,
            )
            
            if result.returncode != 0:
                print(f"  FFmpeg stderr: {result.stderr}")
                raise Exception(f"FFmpeg failed: {result.stderr[:500]}")
            
            # Get list of extracted frames
            frame_files = sorted(frames_dir.glob("frame_*.jpg"))
            num_frames = len(frame_files)
            
            print(f"  Extracted {num_frames} frames")
            
            if num_frames == 0:
                raise Exception("No frames extracted from video")
            
            async with self:
                self.inference_progress_current = 20
                self.inference_progress_total = 20 + num_frames + 10  # Upload + processing + save
                self.inference_progress_status = f"uploading {num_frames} frames"
                self.inference_stage = "uploading"
            yield
            
            # === Step 3: Upload frames to R2 ===
            # Use a session-specific prefix for temp frames (cleaned up at end)
            temp_r2_prefix = f"inference_temp/{user_id}/frames_{session_id}/"
            
            # Upload frames to R2
            print(f"[Step 3/5] Uploading {num_frames} frames to R2...")
            frame_urls = []
            frame_r2_paths = []
            
            for idx, frame_path in enumerate(frame_files):
                frame_bytes = frame_path.read_bytes()
                r2_frame_path = f"{temp_r2_prefix}frame_{idx:05d}.jpg"
                r2_client.upload_file(frame_bytes, r2_frame_path, content_type="image/jpeg")
                
                # Generate presigned URL
                presigned_url = r2_client.generate_presigned_url(r2_frame_path, expires_in=3600)
                frame_urls.append(presigned_url)
                frame_r2_paths.append(r2_frame_path)
                
                # Update progress periodically
                if idx % 10 == 0:
                    async with self:
                        self.inference_progress_current = 20 + idx
                        self.inference_progress_status = f"uploading frame {idx+1}/{num_frames}"
                    yield
            
            print(f"  Uploaded {len(frame_urls)} frames")
            
            async with self:
                self.inference_progress_current = 20 + num_frames
                self.inference_progress_status = f"processing {num_frames} frames (SAM3 + Classifier)"
                self.inference_stage = "processing"
            yield
            
            # === Step 4: Dispatch batch inference via job router ===
            project_id = get_project_id_from_model(self.selected_model_id)
            
            # Fallback: extract project_id from classifier R2 path (format: projects/{uuid}/runs/...)
            if not project_id and _classifier_r2_path.startswith("projects/"):
                parts = _classifier_r2_path.split("/")
                if len(parts) >= 2:
                    project_id = parts[1]
                    print(f"[Hybrid Video Batch] Extracted project_id from R2 path: {project_id}")
            
            print(f"[Step 4/5] Dispatching hybrid_inference_batch for {num_frames} frames (project: {project_id})...")
            
            if not project_id:
                raise Exception("Cannot determine project for model routing. Please select a model from a project.")
            
            # Determine SAM3 model path (None = pretrained default)
            _sam3_model_path_vol = f"/models/{self.selected_sam3_model}" if self.selected_sam3_model != "sam3.pt" else None
            
            batch_results = await asyncio.to_thread(
                dispatch_hybrid_inference_batch,
                project_id=project_id,
                image_urls=frame_urls,
                sam3_prompts=_sam3_prompts,
                classifier_r2_path=_classifier_r2_path,
                classifier_classes=_classifier_classes,
                prompt_class_map=_prompt_class_map,
                confidence_threshold=_confidence,
                classifier_confidence=_classifier_confidence,
                sam3_model_path=_sam3_model_path_vol,
                sam3_imgsz=int(self.sam3_imgsz),
            )
            
            print(f"  Batch inference complete: {len(batch_results)} results")
            
            async with self:
                self.inference_progress_current = 20 + num_frames + 5
                self.inference_progress_status = "saving results"
                self.inference_stage = "saving"
            yield
            
            # === Step 5: Aggregate results into predictions_by_frame ===
            print(f"[Step 5/5] Aggregating results...")
            
            predictions_by_frame = {}
            masks_by_frame = {}
            total_detections = 0
            
            for batch_result in batch_results:
                idx = batch_result.get("index", 0)
                
                # Calculate original frame number based on skip
                # Frame 0 in batch = frame (start_time * fps)
                # Frame 1 in batch = frame (start_time * fps) + skip
                # etc.
                start_frame = int(_start_time * _video_fps) if _video_fps > 0 else 0
                original_frame_num = start_frame + (idx * frame_skip)
                
                preds = batch_result.get("predictions", [])
                # Use string keys for Reflex state compatibility (dict[str, ...])
                frame_key = str(original_frame_num)
                predictions_by_frame[frame_key] = preds
                total_detections += len(preds)
                
                # Note: batch inference doesn't return masks currently
                masks_by_frame[frame_key] = []
            
            print(f"  Total detections: {total_detections}")
            print(f"  Frames with predictions: {len(predictions_by_frame)}")
            
            # Save predictions to R2
            labels_path = _r2_path.replace(".mp4", "_hybrid_labels.json")
            labels_json = json.dumps({
                "predictions_by_frame": predictions_by_frame,
                "masks_by_frame": masks_by_frame,
            })
            r2_client.upload_file(labels_json.encode('utf-8'), labels_path)
            
            # Mark inference as complete
            complete_inference_result(
                result_id=inference_id,
                predictions_json=predictions_by_frame,
                labels_r2_path=labels_path,
                video_fps=_video_fps,
                video_total_frames=num_frames,
                detection_count=total_detections,
            )
            
            # Cleanup temp frames from R2
            print(f"  Cleaning up temp frames from R2...")
            r2_client.delete_files_with_prefix(temp_r2_prefix)
            
            async with self:
                self.predictions_by_frame = predictions_by_frame
                self.last_result_id = inference_id
                await self.load_user_results()
                
                self.is_predicting = False
                self.is_polling_inference = False
                self.inference_progress_current = num_frames
                self.inference_progress_total = num_frames
                self.inference_progress_status = "completed"
                self.inference_stage = ""
            yield
            
            print(f"[Hybrid Video] Complete! {num_frames} frames, {total_detections} detections")
                
        except Exception as e:
            print(f"Hybrid video inference error: {e}")
            import traceback
            traceback.print_exc()
            async with self:
                self.prediction_error = f"Hybrid inference failed: {str(e)}"
                self.is_predicting = False
                self.is_polling_inference = False
                self.inference_stage = ""
                if self.processing_inference_id:
                    complete_inference_result(
                        result_id=self.processing_inference_id,
                        predictions_json={},
                        error_message=str(e)
                    )
        
        finally:
            # Cleanup local temp directory
            import shutil
            shutil.rmtree(temp_dir, ignore_errors=True)

    @rx.event(background=True)
    async def polling_inference(self):
        """Poll for inference progress."""
        import asyncio
        
        print("[Polling] Started polling for inference progress")
        
        # Track the inference ID at start - retry a few times since state setup takes time
        inference_id = ""
        for attempt in range(10):  # Try up to 10 times over 1 second
            async with self:
                inference_id = self.processing_inference_id
                if inference_id:
                    break
            await asyncio.sleep(0.1)
        
        if not inference_id:
            print("[Polling] No inference ID found after 1s, stopping")
            return
        
        print(f"[Polling] Tracking inference: {inference_id}")
        
        while True:
            # First check local state to see if we should stop
            should_stop = False
            async with self:
                if not self.is_polling_inference:
                    should_stop = True
            
            if should_stop:
                print("[Polling] Stopped by local state")
                return

            # Fetch progress from Supabase (outside async with for speed)
            supabase = get_supabase()
            try:
                res = supabase.table("inference_results").select(
                    "progress_current, progress_total, inference_status"
                ).eq("id", inference_id).single().execute()
                
                if res.data:
                    db_status = res.data.get("inference_status", "processing")
                    progress_current = res.data.get("progress_current", 0)
                    progress_total = res.data.get("progress_total", 100)
                    
                    # Update local state
                    async with self:
                        self.inference_progress_current = progress_current
                        self.inference_progress_total = progress_total
                        self.inference_progress_status = db_status
                    yield # Push updates to frontend
                    
                    print(f"[Polling] Progress: {progress_current}/{progress_total}, status: {db_status}")
                    
                    # Stop if DB shows completed or failed
                    if db_status in ["completed", "failed"]:
                        print(f"[Polling] Inference {db_status}, stopping")
                        return
                        
            except Exception as e:
                print(f"[Polling] Error: {e}")
            
            await asyncio.sleep(0.4)  # Poll slightly faster
    
    def update_confidence_threshold(self, value: list[float]):
        """Update confidence threshold from slider (legacy)."""
        self.confidence_threshold = round(float(value[0]), 2)
    
    async def set_confidence_input(self, value: str):
        """Set confidence from text input."""
        v = _validate_numeric(value, 0.0, 1.0, 0.01, is_float=True)
        if v is not None:
            self.confidence_threshold = v
            await self.save_confidence_pref()
    
    async def increment_confidence(self):
        self.confidence_threshold = round(min(1.0, self.confidence_threshold + 0.05), 2)
        await self.save_confidence_pref()
    
    async def decrement_confidence(self):
        self.confidence_threshold = round(max(0.0, self.confidence_threshold - 0.05), 2)
        await self.save_confidence_pref()
    
    async def save_confidence_pref(self, _value=None):
        """Save confidence preference on slider release.
        
        Called via on_value_commit to avoid saving on every drag value.
        Accepts optional value arg to work with on_value_commit signature.
        """
        auth_state = await self.get_state(AuthState)
        if auth_state.user_id:
            update_user_preferences(auth_state.user_id, "playground", {
                "confidence_threshold": self.confidence_threshold,
            })
    
    def clear_results(self):
        """Clear all results and reset state."""
        self.uploaded_file_type = ""
        self.uploaded_filename = ""
        self.uploaded_r2_path = ""
        self.uploaded_presigned_url = ""
        self.uploaded_image_data = ""
        self.uploaded_video_data = ""
        self.predictions = []
        self.predictions_by_frame = {}
        self.labels_txt = ""
        self.prediction_error = ""
        self.image_width = 0
        self.image_height = 0
        self.video_duration = 0.0
        self.video_fps = 0.0
        self.video_frame_count = 0
        self.classification_crop_urls = []
    
    @rx.var
    def results_json(self) -> str:
        """Prepare results for JSON download."""
        if self.uploaded_file_type == "image":
            results = {
                "model_name": self.selected_model_name,
                "input_type": "image",
                "image_width": self.image_width,
                "image_height": self.image_height,
                "predictions": self.predictions,
                "labels_yolo": self.labels_txt,
                "confidence_threshold": self.confidence_threshold,
            }
        else:  # video
            results = {
                "model_name": self.selected_model_name,
                "input_type": "video",
                "video_fps": self.video_fps,
                "time_range": [self.video_start_time, self.video_end_time],
                "predictions_by_frame": self.predictions_by_frame,
                "confidence_threshold": self.confidence_threshold,
            }
        
        return json.dumps(results, indent=2)
    
    # =========================================================================
    # Video Playback Methods (Phase 3.4.5)
    # =========================================================================
    
    async def load_inference_result(self):
        """Load an inference result for playback."""
        try:
            # Get result_id from router query params
            result_id = self.router.page.params.get("result_id", "")
            
            if not result_id:
                self.prediction_error = "No result ID provided"
                return
            
            # Fetch result from Supabase
            supabase = get_supabase()
            result = supabase.table("inference_results").select("*").eq("id", result_id).single().execute()
            
            if not result.data:
                self.prediction_error = "Inference result not found"
                return
            
            record = result.data
            
            # Set common playback state
            self.current_result_id = result_id
            self.current_result_input_type = record["input_type"]
            self.current_result_model_name = record["model_name"]
            self.current_result_confidence = record["confidence_threshold"]
            
            r2_client = R2Client()
            
            if record["input_type"] == "video":
                # Video result
                self.current_result_video_url = r2_client.generate_presigned_url(
                    record["input_r2_path"],
                    expires_in=3600
                )
                
                # Load labels JSON from R2
                labels_path = record["labels_r2_path"]
                labels_data = r2_client.download_file(labels_path)
                labels_json = json.loads(labels_data.decode('utf-8'))
                
                # Handle both formats:
                # - Hybrid: {"predictions_by_frame": {...}, "masks_by_frame": {...}}
                # - Regular: {frame_num: predictions, ...}
                if "predictions_by_frame" in labels_json:
                    # Hybrid format
                    predictions_data = labels_json.get("predictions_by_frame", {})
                    self.labels_by_frame = {int(k): v for k, v in predictions_data.items()}
                    # Also store masks for potential future rendering
                    masks_data = labels_json.get("masks_by_frame", {})
                    self.masks_by_frame = {int(k): v for k, v in masks_data.items()}
                else:
                    # Regular flat format
                    self.labels_by_frame = {int(k): v for k, v in labels_json.items()}
                    self.masks_by_frame = {}
                
                # Get FPS from record
                video_fps = record.get("video_fps", 30.0)
                
                print(f"Loaded {len(self.labels_by_frame)} frames of labels, FPS: {video_fps}")
                
                # Serialize labels and masks for JavaScript
                labels_json_str = json.dumps(self.labels_by_frame)
                masks_json_str = json.dumps(self.masks_by_frame)
                
                # Trigger JS to initialize video player
                init_script = f"""
                    function initInferencePlayer() {{
                        const video = document.getElementById('inference-video');
                        const canvas = document.getElementById('inference-canvas');
                        if (!video || !canvas) {{
                            console.log('[InferencePlayer] DOM not ready, retrying...');
                            setTimeout(initInferencePlayer, 100);
                            return;
                        }}
                        console.log('[InferencePlayer] DOM ready, initializing...');
                        window.setInferenceFps && window.setInferenceFps({video_fps});
                        window.setInferenceLabels && window.setInferenceLabels({labels_json_str});
                        window.setInferenceMasks && window.setInferenceMasks({masks_json_str});
                        window.loadInferenceVideo && window.loadInferenceVideo('{self.current_result_video_url}');
                    }}
                    setTimeout(initInferencePlayer, 50);
                """
                return rx.call_script(init_script)
            
            elif record["input_type"] == "image":
                # Image result
                self.current_result_image_url = r2_client.generate_presigned_url(
                    record["input_r2_path"],
                    expires_in=3600
                )
                
                # Load predictions from record
                predictions_json = record.get("predictions_json", {})
                if isinstance(predictions_json, dict):
                    self.current_result_predictions = predictions_json.get("predictions", [])
                    self.current_result_masks = predictions_json.get("masks", [])
                else:
                    self.current_result_predictions = []
                    self.current_result_masks = []
                
                print(f"Loaded image result with {len(self.current_result_predictions)} predictions, {len(self.current_result_masks)} masks")
            
            elif record["input_type"] == "batch":
                # Batch result - reuse preview_batch_* state vars
                batch_images = record.get("batch_images", [])
                predictions_json = record.get("predictions_json", {})
                batch_predictions = predictions_json.get("batch_predictions", [])
                batch_masks = predictions_json.get("batch_masks", [])
                
                self.preview_batch_images = batch_images
                self.preview_batch_predictions = batch_predictions
                self.preview_batch_masks = batch_masks
                self.preview_batch_index = 0
                
                # Generate presigned URLs for full-size images
                self.preview_batch_urls = []
                for img in batch_images:
                    r2_path = img.get("r2_path", "")
                    if r2_path:
                        url = r2_client.generate_presigned_url(r2_path, expires_in=3600)
                        self.preview_batch_urls.append(url)
                    else:
                        self.preview_batch_urls.append("")
                
                print(f"Loaded batch result with {len(batch_images)} images, {len(batch_predictions)} prediction sets")
        
        except Exception as e:
            print(f"Error loading inference result: {e}")
            import traceback
            traceback.print_exc()
            self.prediction_error = f"Failed to load result: {str(e)}"
    
    def toggle_playback(self):
        """Toggle play/pause state."""
        self.is_playing = not self.is_playing
        return rx.call_script(f"toggleInferencePlayback({str(self.is_playing).lower()})")
    
    def step_frame(self, delta: int):
        """Step forward or backward by delta frames."""
        self.current_frame_number = max(0, self.current_frame_number + delta)
        return rx.call_script(f"stepInferenceFrame({delta})")
    
    def set_playback_speed(self, speed_str: str):
        """Set playback speed (e.g. '0.5x', '1x', '2x')."""
        speed = float(speed_str.replace('x', ''))
        self.playback_speed = speed
        return rx.call_script(f"setInferencePlaybackSpeed({speed})")
    
    async def _run_hybrid_image_inference(self):
        """Run hybrid SAM3 + Classifier inference on image."""
        if not self.uploaded_presigned_url:
            self.prediction_error = "Please upload an image first"
            return
        
        if not self.classifier_r2_path:
            self.prediction_error = "No classifier model path found"
            return
        
        if not self.sam3_prompts:
            self.prediction_error = "Please enter SAM3 prompts (e.g., 'mammal, bird')"
            return
        
        self.is_predicting = True
        self.prediction_error = ""
        self.predictions = []
        self.debug_crop_url = ""  # Clear previous debug crop
        self.inference_stage = "initializing"
        yield
        
        try:
            # Determine project for routing
            self.inference_stage = "loading_model"
            yield
            project_id = get_project_id_from_model(self.selected_model_id)
            
            # Get auth state for user_id (needed for job dispatch and saving)
            auth_state = await self.get_state(AuthState)
            user_id = auth_state.user_id
            
            print(f"Running hybrid inference:")
            print(f"  SAM3 prompts: {self.sam3_prompts}")
            print(f"  SAM3 model: {self.selected_sam3_model}")
            print(f"  Classifier: {self.classifier_r2_path}")
            print(f"  Classes: {self.classifier_classes}")
            print(f"  Prompt map: {self.prompt_class_map}")
            print(f"  Routing via project: {project_id}")
            
            # Dispatch through job router (routes to Modal or local GPU)
            self.inference_stage = "processing"
            yield
            # Determine SAM3 model path (None = pretrained default)
            _sam3_model_path = f"/models/{self.selected_sam3_model}" if self.selected_sam3_model != "sam3.pt" else None
            print(f"  SAM3 model path sent to Modal: {_sam3_model_path or '/models/sam3.pt (default)'}")
            
            result = dispatch_hybrid_inference(
                project_id=project_id or "",
                image_url=self.uploaded_presigned_url,
                sam3_prompts=self.sam3_prompts,
                classifier_r2_path=self.classifier_r2_path,
                classifier_classes=self.classifier_classes,
                prompt_class_map=self.prompt_class_map,
                confidence_threshold=self.confidence_threshold,
                classifier_confidence=self.classifier_confidence,
                # Action-level target selection
                target=self.compute_target,
                user_id=user_id,
                machine_name=self.selected_machine if self.compute_target == "local" else None,
                sam3_model_path=_sam3_model_path,
                sam3_imgsz=int(self.sam3_imgsz),
            )
            
            if not result.get("success"):
                raise Exception(result.get("error", "Unknown error"))
            
            # Convert predictions to our format
            self.predictions = result.get("predictions", [])
            self.labels_txt = result.get("yolo_labels", "")
            masks = result.get("masks", [])  # Segmentation mask polygons
            
            print(f"Hybrid inference complete: {len(self.predictions)} predictions")
            print(f"  SAM3 detections: {result.get('sam3_detections', 0)}")
            print(f"  Final filtered: {result.get('filtered_detections', 0)}")
            print(f"  Masks extracted: {len(masks)}")
            
            # Upload debug crop to R2 (first SAM3 crop for debugging)
            debug_crop_b64 = result.get("debug_crop")
            if debug_crop_b64:
                import base64
                debug_crop_bytes = base64.b64decode(debug_crop_b64)
                try:
                    r2_client_dc = R2Client()
                    crop_path = self.uploaded_r2_path.replace(".jpg", "_debug_crop.jpg").replace(".png", "_debug_crop.jpg")
                    r2_client_dc.upload_file(debug_crop_bytes, crop_path, content_type="image/jpeg")
                    self.debug_crop_url = r2_client_dc.generate_presigned_url(crop_path, expires_in=3600)
                    print(f"[Debug Crop] Saved first crop to {crop_path}")
                except Exception as dc_err:
                    print(f"[Debug Crop] Error saving: {dc_err}")
            
            # Save to database
            self.inference_stage = "saving"
            yield
            
            # auth_state and user_id already retrieved above
            
            # Save labels to R2
            r2_client = R2Client()
            labels_path = self.uploaded_r2_path.replace(".jpg", "_hybrid.txt")
            r2_client.upload_file(self.labels_txt.encode('utf-8'), labels_path)
            
            # Create inference result record (include masks for rendering)
            inference_record = create_inference_result(
                user_id=user_id,
                model_id=self.selected_model_id,
                model_name=f"Hybrid ({self.selected_model_name})",
                input_type="image",
                input_filename=self.uploaded_filename,
                input_r2_path=self.uploaded_r2_path,
                predictions_json={"predictions": self.predictions, "masks": masks},
                confidence_threshold=self.confidence_threshold,
                labels_r2_path=labels_path,
                detection_count=len(self.predictions),
                inference_settings={"species_conf": self.classifier_confidence, "sam3_conf": self.confidence_threshold, "resize_px": int(self.video_target_resolution), "sam3_px": int(self.sam3_imgsz)},
            )
            
            if inference_record:
                self.last_result_id = inference_record["id"]
                print(f"Saved hybrid inference result: {self.last_result_id}")
                
                # Generate styled thumbnail from largest mask
                if masks:
                    try:
                        from backend.core.thumbnail_generator import (
                            select_largest_detection,
                            generate_hybrid_thumbnail,
                        )
                        
                        best_pred, best_mask = select_largest_detection(self.predictions, masks)
                        
                        if best_pred and best_mask:
                            # Download original image from R2
                            image_bytes = r2_client.download_file(self.uploaded_r2_path)
                            
                            if image_bytes:
                                thumb_bytes = generate_hybrid_thumbnail(image_bytes, best_pred, best_mask)
                                
                                if thumb_bytes:
                                    # Upload thumbnail to R2
                                    thumb_path = self.uploaded_r2_path.replace(".jpg", "_thumb.jpg").replace(".png", "_thumb.jpg")
                                    r2_client.upload_file(thumb_bytes, thumb_path)
                                    
                                    # Update DB with thumbnail path
                                    supabase = get_supabase()
                                    supabase.table("inference_results").update({
                                        "thumbnail_r2_path": thumb_path
                                    }).eq("id", self.last_result_id).execute()
                                    
                                    print(f"[Thumbnail] Saved styled thumbnail for {self.last_result_id}")
                    except Exception as thumb_error:
                        print(f"[Thumbnail] Error generating thumbnail: {thumb_error}")
            
            # Refresh results list
            await self.load_user_results()
            
        except Exception as e:
            print(f"Hybrid inference error: {e}")
            import traceback
            traceback.print_exc()
            self.prediction_error = f"Hybrid inference failed: {str(e)}"
        
        finally:
            self.is_predicting = False
            self.inference_stage = ""

