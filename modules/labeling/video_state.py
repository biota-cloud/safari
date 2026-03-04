"""
Video Labeling State — State management for the video-based labeling editor.

Handles:
- Loading videos from a dataset
- Video playback control (play, pause, seek)
- Keyframe marking and management
- Annotations on keyframes

Architecture:
- Videos uploaded to R2, played directly via presigned URL
- User marks specific frames as keyframes (K key)
- Each keyframe can have bounding box annotations
- Annotations saved per-keyframe in YOLO format
"""

import reflex as rx
from typing import Optional
from pydantic import BaseModel
import json
import uuid
import concurrent.futures
from concurrent.futures import ThreadPoolExecutor
import threading

from app_state import AuthState
from backend.supabase_client import (
    get_project, get_dataset, get_dataset_videos, update_dataset, update_project, get_video,
    create_keyframe, get_video_keyframes, update_keyframe, delete_keyframe as db_delete_keyframe,
    delete_video, get_keyframe, get_keyframe_annotations, get_video_keyframe_annotations,
    get_user_preferences, update_user_preferences, touch_dataset_accessed,
    get_user_local_machines
)

from backend.r2_storage import R2Client


# =============================================================================
# PROFILING FLAG - Set to True to enable timing output
# =============================================================================
PERF_PROFILING = False  # Toggle this to enable/disable timing logs


def perf_log(msg: str):
    """Conditional print for performance profiling. Only prints if PERF_PROFILING is True."""
    if PERF_PROFILING:
        print(msg)


# =============================================================================
# VIDEO CACHE HELPERS
# =============================================================================


def estimate_video_memory_mb(width: int, height: int) -> float:
    """Estimate decoded video memory usage in MB.
    
    Rough estimate: width * height * 3 (RGB) * 30 frames buffered
    """
    if width <= 0 or height <= 0:
        return 50  # Default estimate
    pixels = width * height
    estimated_mb = (pixels * 3 * 30) / (1024 * 1024)
    return estimated_mb

def calculate_cache_count(videos: list, target_mb: int = 400) -> int:
    """Calculate how many videos to cache given memory target.
    
    Returns a value between 2 and 10 based on average video size.
    """
    if not videos:
        return 4
    
    # Calculate average video size
    sizes = [estimate_video_memory_mb(v.width, v.height) for v in videos if v.width > 0]
    if not sizes:
        return 6
    
    avg_size = sum(sizes) / len(sizes)
    cache_count = int(target_mb / avg_size) if avg_size > 0 else 6
    return min(10, max(2, cache_count))


class VideoModel(BaseModel):
    """Typed model for video data in the labeling context."""
    id: str = ""
    filename: str = ""
    r2_path: str = ""
    proxy_r2_path: str = ""  # Web-optimized proxy (720p), empty = use original
    path: str = ""  # For R2 deletion
    thumbnail_path: str = ""  # For R2 deletion
    duration_seconds: float = 0.0
    frame_count: int = 0
    fps: float = 30.0
    width: int = 0
    height: int = 0
    thumbnail_url: str = ""
    video_url: str = ""
    keyframe_count: int = 0  # Number of keyframes
    label_count: int = 0  # Total annotations


class KeyframeModel(BaseModel):
    """Typed model for a marked keyframe (text-based, no thumbnails)."""
    id: str = ""
    video_id: str = ""
    frame_number: int = 0
    timestamp: float = 0.0
    annotation_count: int = 0


class VideoLabelingState(rx.State):
    """State for the video labeling editor."""
    
    # Project and Dataset context
    current_project_id: str = ""
    current_dataset_id: str = ""
    project_name: str = ""
    dataset_name: str = ""
    project_classes: list[str] = []
    
    # All videos in the dataset (for sidebar navigation)
    videos: list[VideoModel] = []
    current_video_idx: int = 0  # Index of currently loaded video
    
    # Currently loaded video
    current_video_id: str = ""
    current_video_url: str = ""
    video_filename: str = ""
    video_width: int = 0
    video_height: int = 0
    total_frames: int = 0
    fps: float = 30.0
    duration_seconds: float = 0.0
    
    # Playback state
    current_frame: int = 0
    current_timestamp: float = 0.0
    is_playing: bool = False
    
    # Keyframes for current video
    keyframes: list[KeyframeModel] = []
    selected_keyframe_idx: int = -1  # -1 = no keyframe selected, viewing live video
    
    # Annotations for current keyframe
    annotations: list[dict] = []
    selected_annotation_id: Optional[str] = None
    pending_annotation_data: Optional[str] = None  # Stores annotation data while keyframe is being created
    
    # Autosave state
    save_status: str = ""  # "", "saving", "saved"
    is_dirty: bool = False
    
    # Tool state
    current_tool: str = "select"  # "select" or "draw"
    is_drawing: bool = False
    
    # Class management
    current_class_id: int = 0
    new_class_name: str = ""
    show_delete_class_modal: bool = False
    class_to_delete_idx: int = -1
    class_to_delete_name: str = ""
    
    # UI state
    left_sidebar_tab: str = "videos"  # Start on videos tab
    
    # Keyboard shortcuts help
    show_shortcuts_help: bool = False
    
    # Keyframe interval creation
    interval_start_frame: int = -1  # -1 means not set
    interval_end_frame: int = -1    # -1 means not set
    interval_step: int = 10         # Default to every 10 frames
    interval_frames_queue: list[int] = []  # Queue of frames to create keyframes for
    interval_total_count: int = 0   # Total keyframes to create
    interval_skipped_count: int = 0 # Keyframes that were skipped
    
    # Multi-selection state for keyframes
    selected_keyframe_ids: list[str] = []  # List of selected keyframe IDs
    last_clicked_keyframe_idx: int = -1  # For shift-click range selection
    show_bulk_delete_keyframes_modal: bool = False
    is_bulk_deleting_keyframes: bool = False
    pending_longpress_keyframe_id: str = ""  # Set by JS, read by toggle method
    
    # Keyframe panel state
    show_keyframe_panel: bool = True  # Collapsed panel below timeline
    
    # Focus mode and fullscreen state
    focus_mode: bool = False  # Hide all panels for pure annotation view
    is_fullscreen: bool = False  # Track browser fullscreen state
    
    # Empty keyframes stats modal state
    show_empty_stats_modal: bool = False
    empty_delete_confirmation: str = ""  # User must type "delete" to confirm
    is_deleting_empty_keyframes: bool = False
    
    # Video delete confirmation state
    show_delete_video_modal: bool = False
    video_to_delete_id: str = ""
    video_to_delete_name: str = ""
    
    # Right-click context menu state
    context_menu_open: bool = False
    context_menu_x: int = 0
    context_menu_y: int = 0
    context_menu_annotation_id: str = ""  # Annotation ID for context actions
    
    def set_pending_longpress_keyframe_id(self, value: str):
        """Called from JS input element."""
        self.pending_longpress_keyframe_id = value
    
    def toggle_keyframe_selection_from_js(self):
        """Toggle selection for the keyframe ID set by JS longpress handler."""
        if not self.pending_longpress_keyframe_id:
            return
        
        keyframe_id = self.pending_longpress_keyframe_id
        self.pending_longpress_keyframe_id = ""  # Clear
        
        # Toggle the selection
        if keyframe_id in self.selected_keyframe_ids:
            self.selected_keyframe_ids = [id for id in self.selected_keyframe_ids if id != keyframe_id]
        else:
            self.selected_keyframe_ids = self.selected_keyframe_ids + [keyframe_id]
        
        # Update last clicked index
        for i, kf in enumerate(self.keyframes):
            if kf.id == keyframe_id:
                self.last_clicked_keyframe_idx = i
                break
    
    def toggle_keyframe_selection_by_id(self, keyframe_id: str):
        """Toggle selection for a specific keyframe ID (called from rx.call_script callback)."""
        if not keyframe_id:
            return
        
        print(f"[VideoLabeling] Toggle selection for keyframe: {keyframe_id}")
        
        # Toggle the selection
        if keyframe_id in self.selected_keyframe_ids:
            self.selected_keyframe_ids = [id for id in self.selected_keyframe_ids if id != keyframe_id]
        else:
            self.selected_keyframe_ids = self.selected_keyframe_ids + [keyframe_id]
        
        # Update last clicked index
        for i, kf in enumerate(self.keyframes):
            if kf.id == keyframe_id:
                self.last_clicked_keyframe_idx = i
                break

    def range_select_keyframe_by_id(self, keyframe_id: str):
        """Range selection logic from JS bridge."""
        if not keyframe_id:
            return
            
        print(f"[VideoLabeling] Range select to keyframe: {keyframe_id}")
        
        target_idx = -1
        for i, kf in enumerate(self.keyframes):
            if kf.id == keyframe_id:
                target_idx = i
                break
        
        if target_idx == -1:
            return
            
        if self.last_clicked_keyframe_idx == -1:
            self.toggle_keyframe_selection_by_id(keyframe_id)
            return
            
        start = min(self.last_clicked_keyframe_idx, target_idx)
        end = max(self.last_clicked_keyframe_idx, target_idx)
        
        current_ids = set(self.selected_keyframe_ids)
        for i in range(start, end + 1):
            if i < len(self.keyframes):
                current_ids.add(self.keyframes[i].id)
                
        self.selected_keyframe_ids = list(current_ids)
        self.last_clicked_keyframe_idx = target_idx
    
    # Loading state
    is_loading: bool = False  # Default to False to prevent skeleton flash on re-navigation
    error_message: str = ""
    is_loading_annotations: bool = False  # Background annotation fetching
    is_video_loading: bool = False  # True while video is buffering
    _has_loaded_once: bool = False  # Track first load for skeleton display
    
    # Annotation caching (for fast keyframe navigation)
    annotation_cache: dict[str, list] = {}  # keyframe_id -> annotations list
    cache_max_size: int = 100  # Cache up to 100 keyframes
    
    # Auto-labeling state (SAM3 and YOLO modes) for keyframes
    autolabel_prompt: str = ""
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
    
    # Mask generation options (SAM3 mode only)
    autolabel_generate_bboxes: bool = True
    autolabel_generate_masks: bool = False
    show_mask_overlays: bool = True  # Toggle mask visibility in editor
    
    # Video selection for dataset-wide autolabeling
    selected_video_ids_for_autolabel: list[str] = []  # Empty = all videos
    
    # =========================================================================
    # COMPUTED PROPERTIES
    # =========================================================================
    
    @rx.var
    def video_count(self) -> int:
        """Total number of videos in dataset."""
        return len(self.videos)
    
    @rx.var
    def labeled_video_count(self) -> int:
        """Number of videos with at least one keyframe."""
        # Note: We need to track this from the database, not local state
        # For now, just return 0 as a placeholder
        return 0
    
    @rx.var
    def current_video_index(self) -> int:
        """1-based index of current video for display."""
        return self.current_video_idx + 1
    
    @rx.var
    def keyframe_count(self) -> int:
        """Number of keyframes for current video."""
        return len(self.keyframes)
    
    @rx.var
    def labeled_keyframe_count(self) -> int:
        """Number of keyframes with at least one annotation."""
        return sum(1 for kf in self.keyframes if kf.annotation_count > 0)
    
    @rx.var
    def autolabel_mask_fast_path(self) -> bool:
        """True when mask-only mode can use the bbox-prompt fast path.
        
        This means: masks only selected, AND keyframes with annotations exist.
        In this mode, no text prompt or class mapping is needed.
        """
        return (
            self.autolabel_generate_masks
            and not self.autolabel_generate_bboxes
            and self.labeled_keyframe_count > 0
        )
    
    @rx.var
    def has_keyframes(self) -> bool:
        """Check if current video has any keyframes."""
        return len(self.keyframes) > 0
    
    @rx.var
    def keyframe_positions(self) -> list[dict]:
        """Get keyframe positions as percentages for timeline markers."""
        if self.total_frames <= 1:
            return []
        max_frame = self.total_frames - 1
        return [
            {
                "frame": kf.frame_number,
                # Round to align with slider step positions
                "percent": round((kf.frame_number / max_frame) * 100, 2),
                "has_labels": kf.annotation_count > 0
            }
            for kf in self.keyframes
        ]
    
    @rx.var
    def has_selected_keyframe(self) -> bool:
        """Check if a keyframe is currently selected."""
        return self.selected_keyframe_idx >= 0
    
    @rx.var
    def frame_display(self) -> str:
        """Format current frame for display."""
        return f"Frame {self.current_frame + 1} / {self.total_frames}"
    
    @rx.var
    def has_interval_selection(self) -> bool:
        """Check if both start and end frames are set."""
        return self.interval_start_frame >= 0 and self.interval_end_frame >= 0
    
    @rx.var
    def interval_positions(self) -> list[dict]:
        """Get interval range as percentage positions for timeline visualization."""
        if self.total_frames <= 1:
            return []
        
        # Show visualization if at least start is set
        if self.interval_start_frame < 0:
            return []
        
        max_frame = self.total_frames - 1
        start_percent = (self.interval_start_frame / max_frame) * 100
        
        # If end is set, use it; otherwise use current frame for preview
        if self.interval_end_frame >= 0:
            end_percent = (self.interval_end_frame / max_frame) * 100
        else:
            end_percent = (self.current_frame / max_frame) * 100
        
        return [{
            "start_percent": min(start_percent, end_percent),
            "end_percent": max(start_percent, end_percent),
            "width_percent": abs(end_percent - start_percent),
        }]
    
    @rx.var
    def interval_keyframe_count(self) -> int:
        """Calculate how many keyframes will be created in the interval."""
        if not self.has_interval_selection or self.interval_step <= 0:
            return 0
        
        start = min(self.interval_start_frame, self.interval_end_frame)
        end = max(self.interval_start_frame, self.interval_end_frame)
        
        count = 0
        frame = start
        while frame <= end:
            # Check if this frame is already a keyframe
            is_existing = any(kf.frame_number == frame for kf in self.keyframes)
            if not is_existing:
                count += 1
            frame += self.interval_step
        
        return count
    
    # =========================================================================
    # LIFECYCLE & LOADING
    # =========================================================================
    
    async def restore_canvas_state(self):
        """Called on page mount to initialize the video labeling editor."""
        pass  # No restore needed for videos
    
    async def load_project(self):
        """Load dataset details and all videos for labeling navigation."""
        # Only show skeleton on first load to prevent flickering on re-navigation
        if not self._has_loaded_once:
            self.is_loading = True
        
        try:
            # Get IDs from route
            self.current_project_id = self.router.page.params.get("project_id", "")
            self.current_dataset_id = self.router.page.params.get("dataset_id", "")
            
            if not self.current_project_id or not self.current_dataset_id:
                self.error_message = "No project or dataset ID provided."
                self.is_loading = False
                return
            
            # Fetch project name for breadcrumb
            project = get_project(self.current_project_id)
            if project:
                self.project_name = project.get("name", "")
            
            # Fetch dataset data
            dataset = get_dataset(self.current_dataset_id)
            if not dataset:
                self.error_message = "Dataset not found."
                self.is_loading = False
                return
            
            self.dataset_name = dataset.get("name", "")
            # Load classes from PROJECT (not dataset) - classes are project-wide
            self.project_classes = project.get("classes", []) or [] if project else []
            
            # Load videos (sync method, no await needed)
            self._load_videos_sync()
            
            # Touch access timestamp (for dashboard sorting)
            touch_dataset_accessed(self.current_dataset_id)
            
            # Auto-load first video if available
            if self.videos:
                self.current_video_idx = 0
                self._load_video_sync(self.videos[0])
                
                # Check if frame 0 is a keyframe and auto-select it
                for i, kf in enumerate(self.keyframes):
                    if kf.frame_number == 0:
                        self.selected_keyframe_idx = i
                        self._load_keyframe_annotations_sync(kf.id)
                        print(f"[VideoLabeling] Auto-selected frame 0 keyframe with {len(self.annotations)} annotations")
                        break
            
        except Exception as e:
            print(f"[VideoLabeling] Error loading project: {e}")
            import traceback
            traceback.print_exc()
            self.error_message = f"Error loading dataset: {str(e)}"
        finally:
            self.is_loading = False
            self._has_loaded_once = True
        
        # Return JS call to load video (after state update) with delay for canvas.js to initialize
        if self.current_video_url and self.videos:
            print(f"[VideoLabeling] Triggering JS loadVideoWithThumbnail call...")
            initial_class = self.project_classes[0] if self.project_classes else "Unknown"
            
            # Get current video thumbnail for placeholder
            current_video = self.videos[self.current_video_idx] if self.videos else None
            thumbnail_url = current_video.thumbnail_url if current_video and current_video.thumbnail_url else ""
            video_id = current_video.id if current_video else ""
            
            # Build annotation rendering call if we have annotations for frame 0
            annotation_render = ""
            if self.annotations:
                annotation_render = f"window.renderAnnotations && window.renderAnnotations({json.dumps(self.annotations)}); "
                annotation_render += "window.setKeyframeSelected && window.setKeyframeSelected(true); "
            
            # Calculate and set cache size
            cache_size = calculate_cache_count(self.videos)
            cache_size_script = f"window.setVideoCacheSize && window.setVideoCacheSize({cache_size}); "
            
            # Build preload list for adjacent videos  
            preload_list = self._get_videos_to_preload(self.current_video_idx)
            preload_script = f"window.preloadVideos && window.preloadVideos({json.dumps(preload_list)}); " if preload_list else ""
            print(f"[VideoLabeling] Initial load: video_id={video_id}, thumb={bool(thumbnail_url)}, preload={len(preload_list)}")
            
            return rx.call_script(
                f"setTimeout(function() {{ "
                f"  {cache_size_script}"
                f"  if (window.loadVideoWithThumbnail) {{ "
                f"    window.loadVideoWithThumbnail('{self.current_video_url}', '{thumbnail_url}', '{video_id}'); "
                f"  }} else if (window.loadVideo) {{ "
                f"    window.loadVideo('{self.current_video_url}'); "
                f"  }} else {{ "
                f"    console.error('[Python->JS] loadVideo not found after delay!'); "
                f"  }} "
                f"  window.setCurrentClass && window.setCurrentClass(0, '{initial_class}'); "
                f"  {annotation_render}"
                f"  setTimeout(function() {{ {preload_script} }}, 1000); "
                f"}}, 100);"
            )

    
    async def _load_videos(self):
        """Load videos for the current dataset with presigned URLs."""
        try:
            raw_videos = get_dataset_videos(self.current_dataset_id)
            r2 = R2Client()
            
            self.videos = []
            for vid in raw_videos:
                # Generate presigned URL for thumbnail display
                thumbnail_url = ""
                thumbnail_path = vid.get("thumbnail_path", "")
                
                if thumbnail_path:
                    try:
                        thumbnail_url = r2.generate_presigned_url(thumbnail_path)
                    except Exception as e:
                        print(f"[VideoLabeling] Error generating thumbnail URL: {e}")
                
                # Video URL for playback — prefer proxy if available
                video_url = ""
                r2_path = vid.get("r2_path", "")
                proxy_r2_path = vid.get("proxy_r2_path", "") or ""
                playback_path = proxy_r2_path if proxy_r2_path else r2_path
                if playback_path:
                    try:
                        video_url = r2.generate_presigned_url(playback_path, expires_in=7200)  # 2 hours
                    except Exception as e:
                        print(f"[VideoLabeling] Error generating video URL: {e}")
                
                self.videos.append(VideoModel(
                    id=str(vid.get("id", "")),
                    filename=str(vid.get("filename", "")),
                    r2_path=str(r2_path),
                    proxy_r2_path=str(proxy_r2_path),
                    duration_seconds=vid.get("duration_seconds") or 0.0,
                    frame_count=vid.get("frame_count") or 0,
                    fps=vid.get("fps") or 30.0,
                    width=vid.get("width") or 0,
                    height=vid.get("height") or 0,
                    thumbnail_url=thumbnail_url,
                    video_url=video_url,
                ))
            
            print(f"[VideoLabeling] Loaded {len(self.videos)} videos")
        except Exception as e:
            print(f"[VideoLabeling] Error loading videos: {e}")
    
    def _load_videos_sync(self):
        """Load videos for the current dataset (optimized)."""
        try:
            raw_videos = get_dataset_videos(self.current_dataset_id)
            r2 = R2Client()
            
            # 1. Batch fetch all keyframes for all videos in one query (if possible)
            # For now, we'll loop but use the lightweight DB query instead of R2 downloads
            
            self.videos = []
            for vid in raw_videos:
                # Generate presigned URL for thumbnail display
                thumbnail_url = ""
                thumbnail_path = vid.get("thumbnail_path", "")
                
                if thumbnail_path:
                    try:
                        thumbnail_url = r2.generate_presigned_url(thumbnail_path)
                    except Exception as e:
                        print(f"[VideoLabeling] Error generating thumbnail URL: {e}")
                
                # Video URL for playback — prefer proxy if available
                video_url = ""
                r2_path = vid.get("r2_path", "")
                proxy_r2_path = vid.get("proxy_r2_path", "") or ""
                playback_path = proxy_r2_path if proxy_r2_path else r2_path
                if playback_path:
                    try:
                        video_url = r2.generate_presigned_url(playback_path, expires_in=7200)  # 2 hours
                    except Exception as e:
                        print(f"[VideoLabeling] Error generating video URL: {e}")
                
                # Get video ID and populate keyframe/label counts efficiently
                video_id = str(vid.get("id", ""))
                keyframe_count = 0
                label_count = 0
                
                try:
                    # Get all keyframes for this video (fast DB query)
                    keyframes = get_video_keyframes(video_id)
                    keyframe_count = len(keyframes)
                    
                    # Sum annotation_count from DB - NO R2 DOWNLOADS required!
                    # This reduces load time from ~10s to ~200ms
                    label_count = sum(kf.get("annotation_count", 0) for kf in keyframes)
                
                except Exception as e:
                    print(f"[VideoLabeling] Error counting keyframes/labels for video {video_id}: {e}")
                
                self.videos.append(VideoModel(
                    id=video_id,
                    filename=str(vid.get("filename", "")),
                    r2_path=str(r2_path),
                    proxy_r2_path=str(proxy_r2_path),
                    path=str(r2_path),  
                    thumbnail_path=thumbnail_path,
                    duration_seconds=vid.get("duration_seconds") or 0.0,
                    frame_count=vid.get("frame_count") or 0,
                    fps=vid.get("fps") or 30.0,
                    width=vid.get("width") or 0,
                    height=vid.get("height") or 0,
                    thumbnail_url=thumbnail_url,
                    video_url=video_url,
                    keyframe_count=keyframe_count,
                    label_count=label_count,
                ))
            
            print(f"[VideoLabeling] Loaded {len(self.videos)} videos (Fast Mode)")
        except Exception as e:
            print(f"[VideoLabeling] Error loading videos: {e}")
    
    # _refresh_video_counts removed (not needed, counts are accurate from DB)
    def _load_video_sync(self, video: VideoModel):
        """Load a video into the editor (sync version, sets state only, no JS trigger)."""
        import time
        t_start = time.perf_counter()
        
        # Set video info
        self.current_video_id = video.id
        self.current_video_url = video.video_url
        self.video_filename = video.filename
        self.video_width = video.width
        self.video_height = video.height
        self.total_frames = video.frame_count
        self.fps = video.fps if video.fps > 0 else 30.0
        self.duration_seconds = video.duration_seconds
        
        # Reset playback state
        self.current_frame = 0
        self.current_timestamp = 0.0
        self.is_playing = False
        
        # Reset annotation state
        self.annotations = []
        self.selected_annotation_id = None
        self.selected_keyframe_idx = -1
        self.is_dirty = False
        perf_log(f"[PERF]   3a. Set video state vars: {(time.perf_counter()-t_start)*1000:.1f}ms")
        
        # Clear annotation cache when switching videos
        t1 = time.perf_counter()
        self._clear_annotation_cache()
        perf_log(f"[PERF]   3b. Clear cache: {(time.perf_counter()-t1)*1000:.1f}ms")
        
        # OPTIMIZED: Single query to load keyframes AND annotations together
        t2 = time.perf_counter()
        self._load_keyframes_and_annotations_sync()
        perf_log(f"[PERF]   3c. _load_keyframes_and_annotations_sync (COMBINED): {(time.perf_counter()-t2)*1000:.1f}ms")
        
        # Debug logging
        print(f"[VideoLabeling] Loaded video: {video.filename}")
        print(f"[VideoLabeling]   - URL: {self.current_video_url[:100]}..." if self.current_video_url else "[VideoLabeling]   - URL: EMPTY!")
        print(f"[VideoLabeling]   - Dimensions: {self.video_width}x{self.video_height}")
        print(f"[VideoLabeling]   - Frames: {self.total_frames} @ {self.fps}fps")


    def _load_keyframes_and_annotations_sync(self):
        """Load keyframes AND annotations in a single Supabase query.
        
        OPTIMIZED: This replaces two separate queries with one, cutting
        network latency by ~50% for video switching.
        
        The keyframes table already has an 'annotations' JSONB column,
        so SELECT * returns everything we need in one round-trip.
        """
        import time
        if not self.current_video_id:
            return
        
        try:
            from backend.annotation_service import resolve_class_names
            
            t0 = time.perf_counter()
            # Single query - get_video_keyframes uses SELECT * which includes annotations
            raw_keyframes = get_video_keyframes(self.current_video_id)
            perf_log(f"[PERF]     3c-1. Supabase query (keyframes + annotations): {(time.perf_counter()-t0)*1000:.1f}ms")
            
            t1 = time.perf_counter()
            self.keyframes = []
            for kf in raw_keyframes:
                # Build keyframe model
                self.keyframes.append(KeyframeModel(
                    id=str(kf.get("id", "")),
                    video_id=str(kf.get("video_id", "")),
                    frame_number=kf.get("frame_number") or 0,
                    timestamp=kf.get("timestamp") or 0.0,
                    annotation_count=kf.get("annotation_count") or 0,
                ))
                
                # Populate annotation cache directly from the same query result
                kf_id = str(kf.get("id", ""))
                annotations = kf.get("annotations")
                if annotations is not None:
                    # Resolve class_name from class_id using project_classes
                    resolved = resolve_class_names(annotations, self.project_classes)
                    self.annotation_cache[kf_id] = resolved
                else:
                    self.annotation_cache[kf_id] = []
            
            # Sort by frame number
            self.keyframes = sorted(self.keyframes, key=lambda k: k.frame_number)
            perf_log(f"[PERF]     3c-2. Build models + populate cache (class names resolved): {(time.perf_counter()-t1)*1000:.1f}ms")
            
            print(f"[VideoLabeling] Loaded {len(self.keyframes)} keyframes with annotations (single query)")
            print(f"[Cache] All {len(self.annotation_cache)} keyframes cached.")
            
        except Exception as e:
            print(f"[VideoLabeling] Error loading keyframes and annotations: {e}")

    
    def _load_keyframes_sync(self):
        """Load keyframes for the current video from database (sync version, no thumbnails).
        
        NOTE: This is the OLD method, kept for backward compatibility.
        Use _load_keyframes_and_annotations_sync() for optimized single-query loading.
        """
        import time
        if not self.current_video_id:
            return
        
        try:
            t0 = time.perf_counter()
            raw_keyframes = get_video_keyframes(self.current_video_id)
            perf_log(f"[PERF]     3c-1. Supabase get_video_keyframes: {(time.perf_counter()-t0)*1000:.1f}ms")
            
            t1 = time.perf_counter()
            self.keyframes = []
            for kf in raw_keyframes:
                self.keyframes.append(KeyframeModel(
                    id=str(kf.get("id", "")),
                    video_id=str(kf.get("video_id", "")),
                    frame_number=kf.get("frame_number") or 0,
                    timestamp=kf.get("timestamp") or 0.0,
                    annotation_count=kf.get("annotation_count") or 0,
                ))
            
            # Sort by frame number
            self.keyframes = sorted(self.keyframes, key=lambda k: k.frame_number)
            perf_log(f"[PERF]     3c-2. Build KeyframeModel list: {(time.perf_counter()-t1)*1000:.1f}ms")
            
            print(f"[VideoLabeling] Loaded {len(self.keyframes)} keyframes")
        except Exception as e:
            print(f"[VideoLabeling] Error loading keyframes: {e}")

    
    def _batch_load_annotations_sync(self):
        """Batch load all annotations for this video in a single query and pre-populate cache."""
        import time
        if not self.current_video_id or not self.keyframes:
            return
        
        try:
            self.is_loading_annotations = True
            print(f"[Batch Load] Fetching annotations for {len(self.keyframes)} keyframes...")
            
            # Single query to fetch ALL annotations for this video from Supabase
            t0 = time.perf_counter()
            supabase_annotations = get_video_keyframe_annotations(self.current_video_id)
            perf_log(f"[PERF]     3d-1. Supabase query: {(time.perf_counter()-t0)*1000:.1f}ms")
            
            # Populate the cache instantly with Supabase data
            t1 = time.perf_counter()
            for keyframe_id, annotations in supabase_annotations.items():
                self.annotation_cache[keyframe_id] = annotations
            perf_log(f"[PERF]     3d-2. Populate cache: {(time.perf_counter()-t1)*1000:.1f}ms")
            
            # OPTIMIZATION: Skip R2 check if all keyframes are already in Supabase
            keyframes_in_cache = set(self.annotation_cache.keys())
            keyframes_needed = set(kf.id for kf in self.keyframes)
            missing_from_supabase = keyframes_needed - keyframes_in_cache
            
            if not missing_from_supabase:
                # All keyframes have annotations in Supabase, skip R2 entirely
                perf_log(f"[PERF]     3d-3. R2 list_files: SKIPPED (all in Supabase)")
                self.is_loading_annotations = False
                print(f"[Batch Load] ✓ Ready: {len(supabase_annotations)} from Supabase, 0 synced from R2")
                print(f"[Cache] All {len(self.annotation_cache)} keyframes cached.")
                return
            
            # List ALL label files in R2 for this video's prefix to avoid N head requests
            t2 = time.perf_counter()
            r2 = R2Client()
            label_prefix = f"datasets/{self.current_dataset_id}/labels/{self.current_video_id}_f"
            all_r2_files = r2.list_files(label_prefix)
            r2_file_map = {fpath: True for fpath in all_r2_files}
            perf_log(f"[PERF]     3d-3. R2 list_files: {(time.perf_counter()-t2)*1000:.1f}ms ({len(all_r2_files)} files)")
            
            # Identify keyframes that are NOT in Supabase but have a file in R2
            to_download = []
            for kf in self.keyframes:
                if kf.id not in self.annotation_cache:
                    label_path = f"{label_prefix}{kf.frame_number}.txt"
                    if label_path in r2_file_map:
                        to_download.append((kf.id, label_path))
                    else:
                        # No label in DB or R2
                        self.annotation_cache[kf.id] = []
            
            # Download missing labels in parallel
            if to_download:
                t3 = time.perf_counter()
                print(f"[Batch Load] Parallel downloading {len(to_download)} labels from R2...")
                downloaded = {}
                def download_and_parse(kf_id, path):
                    try:
                        content = r2.download_file(path)
                        txt_content = content.decode("utf-8")
                        return kf_id, self._from_yolo_format(txt_content)
                    except Exception as e:
                        print(f"[R2 Download Error] {path}: {e}")
                        return kf_id, []

                with ThreadPoolExecutor(max_workers=10) as executor:
                    futures = [executor.submit(download_and_parse, kf_id, path) for kf_id, path in to_download]
                    for future in concurrent.futures.as_completed(futures):
                        kf_id, annotations = future.result()
                        self.annotation_cache[kf_id] = annotations
                        downloaded[kf_id] = annotations
                perf_log(f"[PERF]     3d-4. R2 downloads: {(time.perf_counter()-t3)*1000:.1f}ms")

                # BACKFILL SUPABASE: Sync downloaded R2 labels to database for future fast loads
                t4 = time.perf_counter()
                print(f"[Batch Load] Synced {len(downloaded)} labels from R2 back to Supabase")
                for kf_id, annotations in downloaded.items():
                    try:
                        update_keyframe(kf_id, annotations=annotations, annotation_count=len(annotations))
                    except Exception as e:
                        print(f"[Backfill Error] Failed to sync keyframe {kf_id}: {e}")
                perf_log(f"[PERF]     3d-5. Supabase backfill: {(time.perf_counter()-t4)*1000:.1f}ms")

            self.is_loading_annotations = False
            print(f"[Batch Load] ✓ Ready: {len(supabase_annotations)} from Supabase, {len(to_download)} synced from R2")
            print(f"[Cache] All {len(self.annotation_cache)} keyframes cached.")
            
        except Exception as e:
            print(f"[Batch Load] Error: {e}")
            self.is_loading_annotations = False

    
    async def _load_video_by_index(self, idx: int):
        """Load a video by its index in the videos list."""
        if idx < 0 or idx >= len(self.videos):
            return
        
        video = self.videos[idx]
        await self._load_video(video)
    
    async def _load_video(self, video: VideoModel):
        """Load a video into the editor (sets state, does NOT trigger JS)."""
        # Save current keyframe annotations if dirty
        if self.is_dirty and self.selected_keyframe_idx >= 0:
            await self._save_current_keyframe_annotations()
        
        # Set video info
        self.current_video_id = video.id
        self.current_video_url = video.video_url
        self.video_filename = video.filename
        self.video_width = video.width
        self.video_height = video.height
        self.total_frames = video.frame_count
        self.fps = video.fps if video.fps > 0 else 30.0
        self.duration_seconds = video.duration_seconds
        
        # Reset playback state
        self.current_frame = 0
        self.current_timestamp = 0.0
        self.is_playing = False
        
        # Reset annotation state
        self.annotations = []
        self.selected_annotation_id = None
        self.selected_keyframe_idx = -1
        self.is_dirty = False
        
        # Load keyframes for this video
        await self._load_keyframes()
        
        # Debug logging
        print(f"[VideoLabeling] Loaded video: {video.filename}")
        print(f"[VideoLabeling]   - URL: {self.current_video_url[:100]}..." if self.current_video_url else "[VideoLabeling]   - URL: EMPTY!")
        print(f"[VideoLabeling]   - Dimensions: {self.video_width}x{self.video_height}")
        print(f"[VideoLabeling]   - Frames: {self.total_frames} @ {self.fps}fps")
        # Note: JS call is triggered from calling function (load_project)
    
    async def _load_keyframes(self):
        """Load keyframes for the current video from database (no thumbnails)."""
        if not self.current_video_id:
            return
        
        try:
            raw_keyframes = get_video_keyframes(self.current_video_id)
            
            self.keyframes = []
            for kf in raw_keyframes:
                self.keyframes.append(KeyframeModel(
                    id=str(kf.get("id", "")),
                    video_id=str(kf.get("video_id", "")),
                    frame_number=kf.get("frame_number") or 0,
                    timestamp=kf.get("timestamp") or 0.0,
                    annotation_count=kf.get("annotation_count") or 0,
                ))
            
            # Sort by frame number
            self.keyframes = sorted(self.keyframes, key=lambda k: k.frame_number)
            
            print(f"[VideoLabeling] Loaded {len(self.keyframes)} keyframes")
        except Exception as e:
            print(f"[VideoLabeling] Error loading keyframes: {e}")
    
    def load_video(self, video_dict: dict):
        """Select a video to label (called from sidebar click)."""
        # Find the video in our list
        for i, v in enumerate(self.videos):
            if v.id == video_dict.get("id"):
                return VideoLabelingState._load_video_by_index(i)
        return None
    
    def select_video(self, idx: int):
        """Select a video by index from the sidebar."""
        import time
        t_start = time.perf_counter()
        print(f"\n[PERF] ═══════════════════════════════════════════════════════")
        perf_log(f"[PERF] select_video({idx}) STARTED")
        
        if idx < 0 or idx >= len(self.videos):
            return
        
        # Save current keyframe annotations if dirty before switching (ASYNC - non-blocking)
        t0 = time.perf_counter()
        if self.is_dirty and self.selected_keyframe_idx >= 0 and self.selected_keyframe_idx < len(self.keyframes):
            current_kf = self.keyframes[self.selected_keyframe_idx]
            # Get old annotations BEFORE updating cache
            old_anns = self.annotation_cache.get(current_kf.id, [])
            # Capture snapshot of data for background save (avoids race conditions)
            self._save_keyframe_background(
                keyframe_id=current_kf.id,
                frame_number=current_kf.frame_number,
                annotations=self.annotations.copy(),  # Copy to avoid mutation
                old_annotations=list(old_anns),  # Copy old annotations for class count diff
                dataset_id=self.current_dataset_id,
                video_id=self.current_video_id,
            )
            # Update cache and local state immediately (sync)
            self._update_cache(current_kf.id, self.annotations.copy())
            for i, kf in enumerate(self.keyframes):
                if kf.id == current_kf.id:
                    self.keyframes[i] = KeyframeModel(
                        **{**kf.model_dump(), "annotation_count": len(self.annotations)}
                    )
                    break
            self.is_dirty = False
            perf_log(f"[PERF] 1. Async save + cache update: {(time.perf_counter()-t0)*1000:.1f}ms")
        else:
            perf_log(f"[PERF] 1. No dirty state (skipped): {(time.perf_counter()-t0)*1000:.1f}ms")
        
        # Update current video index
        t1 = time.perf_counter()
        self.current_video_idx = idx
        video = self.videos[idx]
        perf_log(f"[PERF] 2. Set current_video_idx: {(time.perf_counter()-t1)*1000:.1f}ms")
        
        # Load the new video (sync version)
        t2 = time.perf_counter()
        self._load_video_sync(video)
        perf_log(f"[PERF] 3. _load_video_sync: {(time.perf_counter()-t2)*1000:.1f}ms")
        
        # Auto-switch to Keyframes tab
        t3 = time.perf_counter()
        self.left_sidebar_tab = "keyframes"
        perf_log(f"[PERF] 4. Set sidebar tab: {(time.perf_counter()-t3)*1000:.1f}ms")
        
        # Check if frame 0 is a keyframe and auto-select it
        t4 = time.perf_counter()
        frame0_annotations = []
        for i, kf in enumerate(self.keyframes):
            if kf.frame_number == 0:
                self.selected_keyframe_idx = i
                self._load_keyframe_annotations_sync(kf.id)
                frame0_annotations = self.annotations
                perf_log(f"[PERF] 5. Auto-select frame 0 + load annotations: {(time.perf_counter()-t4)*1000:.1f}ms ({len(self.annotations)} annotations)")
                break
        else:
            perf_log(f"[PERF] 5. No frame 0 keyframe: {(time.perf_counter()-t4)*1000:.1f}ms")
        
        # Trigger JS to load the new video and render frame 0 annotations if any
        t5 = time.perf_counter()
        if self.current_video_url:
            print(f"[VideoLabeling] Switching to video {idx}: {video.filename}")
            
            # Get thumbnail URL for placeholder
            thumbnail_url = video.thumbnail_url if video.thumbnail_url else ""
            video_id = video.id
            
            # Build annotation rendering call if we have annotations for frame 0
            annotation_render = "window.renderAnnotations && window.renderAnnotations([]); "  # Clear first
            if frame0_annotations:
                annotation_render = f"window.renderAnnotations && window.renderAnnotations({json.dumps(frame0_annotations)}); "
                annotation_render += "window.setKeyframeSelected && window.setKeyframeSelected(true); "
            
            # Build preload list for adjacent videos
            preload_list = self._get_videos_to_preload(idx)
            preload_script = ""
            if preload_list:
                preload_script = f"window.preloadVideos && window.preloadVideos({json.dumps(preload_list)}); "
            
            # Calculate and set cache size based on video resolution
            cache_size = calculate_cache_count(self.videos)
            cache_size_script = f"window.setVideoCacheSize && window.setVideoCacheSize({cache_size}); "
            
            perf_log(f"[PERF] 6. Build JS script: {(time.perf_counter()-t5)*1000:.1f}ms")
            
            total_time = (time.perf_counter() - t_start) * 1000
            perf_log(f"[PERF] ═══════════════════════════════════════════════════════")
            perf_log(f"[PERF] TOTAL Python select_video: {total_time:.1f}ms")
            perf_log(f"[PERF] ═══════════════════════════════════════════════════════\n")
            
            # Build JS timing calls (only if profiling enabled)
            js_time_start = "console.time('[PERF] JS video load'); " if PERF_PROFILING else ""
            js_time_end = "console.timeEnd('[PERF] JS video load'); " if PERF_PROFILING else ""
            
            return rx.call_script(
                f"{js_time_start}"
                f"setTimeout(function() {{ "
                f"  {cache_size_script}"
                f"  if (window.loadVideoWithThumbnail) {{ "
                f"    window.loadVideoWithThumbnail('{self.current_video_url}', '{thumbnail_url}', '{video_id}'); "
                f"  }} else if (window.loadVideo) {{ "
                f"    window.loadVideo('{self.current_video_url}', '{video_id}'); "
                f"  }} else {{ "
                f"    console.error('[Python->JS] loadVideo not found!'); "
                f"  }} "
                f"  {annotation_render}"
                f"  {js_time_end}"
                f"  setTimeout(function() {{ {preload_script} }}, 1000); "  # Preload after 1s
                f"}}, 100);"
            )


    
    def _get_videos_to_preload(self, current_idx: int) -> list[dict]:
        """Get list of adjacent videos to preload."""
        preload_list = []
        cache_size = calculate_cache_count(self.videos)
        half_cache = cache_size // 2
        
        # Preload videos before and after current
        for offset in range(-half_cache, half_cache + 1):
            if offset == 0:
                continue  # Skip current video
            
            adj_idx = current_idx + offset
            if 0 <= adj_idx < len(self.videos):
                v = self.videos[adj_idx]
                if v.video_url:
                    preload_list.append({"id": v.id, "url": v.video_url})
        
        print(f"[VideoCache] Preload list for idx {current_idx}: {len(preload_list)} videos")
        return preload_list
    
    def set_sidebar_tab(self, tab: str):
        """Switch between Videos and Keyframes tabs."""
        if tab in ["videos", "keyframes"]:
            # Save current keyframe annotations if dirty before switching tabs (NON-BLOCKING)
            if self.is_dirty and self.selected_keyframe_idx >= 0 and self.selected_keyframe_idx < len(self.keyframes):
                current_kf = self.keyframes[self.selected_keyframe_idx]
                old_anns = self.annotation_cache.get(current_kf.id, [])
                self._save_keyframe_background(
                    keyframe_id=current_kf.id,
                    frame_number=current_kf.frame_number,
                    annotations=self.annotations.copy(),
                    old_annotations=list(old_anns),
                    dataset_id=self.current_dataset_id,
                    video_id=self.current_video_id,
                )
                self._update_cache(current_kf.id, self.annotations.copy())
                self.is_dirty = False
                print(f"[VideoLabeling] Queued background save before tab switch")
            
            self.left_sidebar_tab = tab
            
            # Recalculate label counts when switching to Videos tab
            if tab == "videos":
                self._refresh_video_label_counts()
    
    def _refresh_video_label_counts(self):
        """Fast refresh of video label counts using local state."""
        try:
            # Only refresh if we have a current video and its keyframes ready
            if not (self.current_video_id and self.keyframes):
                return
                
            current_label_count = sum(kf.annotation_count for kf in self.keyframes)
            current_keyframe_count = len(self.keyframes)
            
            # Find the video in the list (usually at current_video_idx)
            # We check both the index-based access (fastest) and ID-based (safest)
            target_idx = -1
            if 0 <= self.current_video_idx < len(self.videos):
                if self.videos[self.current_video_idx].id == self.current_video_id:
                    target_idx = self.current_video_idx
            
            if target_idx == -1:
                # Fallback: search by ID
                for i, vid in enumerate(self.videos):
                    if vid.id == self.current_video_id:
                        target_idx = i
                        break
            
            if target_idx != -1:
                vid = self.videos[target_idx]
                # Only update if changed
                if vid.label_count != current_label_count or vid.keyframe_count != current_keyframe_count:
                    # Update local state
                    new_vid = VideoModel(**{
                        **vid.model_dump(),
                        "label_count": current_label_count,
                        "keyframe_count": current_keyframe_count
                    })
                    # Use index-based assignment for Reflex reactivity
                    self.videos[target_idx] = new_vid
                    print(f"[VideoLabeling] Updated sidebar label count for '{vid.filename}': {current_label_count}")
        except Exception as e:
            print(f"[VideoLabeling] Error refreshing counts: {e}")
    
    def _refresh_all_video_label_counts(self):
        """Refresh label counts for ALL videos from database (used after autolabel)."""
        try:
            from backend.supabase_client import get_video_keyframes
            
            if not self.videos:
                return
            
            print("[VideoLabeling] Refreshing all video label counts from database...")
            updated_videos = []
            
            for vid in self.videos:
                # Get fresh keyframe data from database
                keyframes = get_video_keyframes(vid.id)
                label_count = sum(kf.get("annotation_count", 0) for kf in keyframes)
                keyframe_count = len(keyframes)
                
                # Create updated video model
                updated_vid = VideoModel(**{
                    **vid.model_dump(),
                    "label_count": label_count,
                    "keyframe_count": keyframe_count
                })
                updated_videos.append(updated_vid)
                
                if label_count != vid.label_count:
                    print(f"[VideoLabeling] Updated '{vid.filename}': {vid.label_count} → {label_count} labels")
            
            # Replace entire videos list for Reflex reactivity
            self.videos = updated_videos
            print(f"[VideoLabeling] Refreshed {len(updated_videos)} video thumbnails")
            
        except Exception as e:
            print(f"[VideoLabeling] Error refreshing all video counts: {e}")
            import traceback
            traceback.print_exc()

    
    # =========================================================================
    # VIDEO PLAYBACK CONTROL
    # =========================================================================
    
    def toggle_playback(self):
        """Toggle play/pause state."""
        self.is_playing = not self.is_playing
        return rx.call_script(
            f"window.toggleVideoPlayback && window.toggleVideoPlayback({str(self.is_playing).lower()})"
        )
    
    def seek_to_frame(self, frame: int):
        """Seek to a specific frame number."""
        if frame < 0:
            frame = 0
        if self.total_frames > 0 and frame >= self.total_frames:
            frame = self.total_frames - 1
        
        # Save current keyframe annotations if dirty before moving (NON-BLOCKING)
        if self.is_dirty and self.selected_keyframe_idx >= 0 and self.selected_keyframe_idx < len(self.keyframes):
            current_kf = self.keyframes[self.selected_keyframe_idx]
            old_anns = self.annotation_cache.get(current_kf.id, [])
            self._save_keyframe_background(
                keyframe_id=current_kf.id,
                frame_number=current_kf.frame_number,
                annotations=self.annotations.copy(),
                old_annotations=list(old_anns),
                dataset_id=self.current_dataset_id,
                video_id=self.current_video_id,
            )
            self._update_cache(current_kf.id, self.annotations.copy())
            self.is_dirty = False
        
        self.current_frame = frame
        self.current_timestamp = frame / self.fps if self.fps > 0 else 0
        
        # Check if this frame is a keyframe
        keyframe_found = False
        for i, kf in enumerate(self.keyframes):
            if kf.frame_number == frame:
                # This frame is a keyframe - load its annotations
                self.selected_keyframe_idx = i
                self._load_keyframe_annotations_sync(kf.id)
                keyframe_found = True
                print(f"[VideoLabeling] Navigated to keyframe at frame {frame}, annotations={len(self.annotations)}")
                break
        
        if not keyframe_found:
            # Not a keyframe - clear selection and annotations
            self.selected_keyframe_idx = -1
            self.annotations = []
            self.selected_annotation_id = None
        
        # Yield JS calls for seek and annotation rendering
        yield rx.call_script(f"window.seekToFrame && window.seekToFrame({frame}, {self.fps})")
        yield rx.call_script(f"window.renderAnnotations && window.renderAnnotations({json.dumps(self.annotations)})")
        
        # Auto-scroll to keyframe in sidebar if navigated to one
        if keyframe_found:
            yield rx.call_script(
                f"document.getElementById('keyframe-{frame}')"
                f"?.scrollIntoView({{ behavior: 'smooth', block: 'nearest' }})"
            )
    
    def step_frame(self, delta: int):
        """Step forward or backward by delta frames."""
        new_frame = self.current_frame + delta
        yield from self.seek_to_frame(new_frame)

    
    def handle_frame_update(self, data_json: str):
        """Called from JS when the video frame changes during playback."""
        try:
            data = json.loads(data_json)
            new_frame = data.get("frame", 0)
            self.current_frame = new_frame
            self.current_timestamp = data.get("timestamp", 0.0)
            
            # Check if new frame is a keyframe and load/clear annotations
            keyframe_found = False
            for i, kf in enumerate(self.keyframes):
                if kf.frame_number == new_frame:
                    # Frame is a keyframe - load annotations from cache
                    self.selected_keyframe_idx = i
                    if kf.id in self.annotation_cache:
                        self.annotations = self.annotation_cache[kf.id].copy()
                    else:
                        self.annotations = []
                    self.selected_annotation_id = None
                    keyframe_found = True
                    break
            
            if not keyframe_found:
                # Not a keyframe - clear annotations
                self.selected_keyframe_idx = -1
                self.annotations = []
                self.selected_annotation_id = None
            
            # Render annotations on canvas
            return rx.call_script(f"window.renderAnnotations && window.renderAnnotations({json.dumps(self.annotations)})")
            
        except Exception as e:
            print(f"[VideoLabeling] Error parsing frame update: {e}")
    
    def handle_slider_change(self, value: list):
        """Handle slider value change for seeking."""
        if value and len(value) > 0:
            frame = int(value[0])
            return self.seek_to_frame(frame)
    
    def handle_slider_drag(self, value: list):
        """Handle slider dragging - update position and render annotations in real-time."""
        if value and len(value) > 0:
            frame = int(value[0])
            self.current_frame = frame
            self.current_timestamp = frame / self.fps if self.fps > 0 else 0
            
            # Check if this frame is a keyframe and load annotations from cache
            keyframe_found = False
            for i, kf in enumerate(self.keyframes):
                if kf.frame_number == frame:
                    # This frame is a keyframe - load annotations from cache
                    self.selected_keyframe_idx = i
                    if kf.id in self.annotation_cache:
                        self.annotations = self.annotation_cache[kf.id].copy()
                    else:
                        self.annotations = []
                    self.selected_annotation_id = None
                    keyframe_found = True
                    break
            
            if not keyframe_found:
                # Not a keyframe - clear annotations
                self.selected_keyframe_idx = -1
                self.annotations = []
                self.selected_annotation_id = None
            
            # Seek video and render annotations
            return [
                rx.call_script(f"window.seekToFrame && window.seekToFrame({frame}, {self.fps})"),
                rx.call_script(f"window.renderAnnotations && window.renderAnnotations({json.dumps(self.annotations)})"),
            ]
            
    def handle_video_loading(self, status: str):
        """Handle video loading status updates from JS.
        Status comes as 'start:N' or 'complete:N' with a uniquifier counter.
        """
        if status.startswith("start"):
            self.is_video_loading = True
            print("[VideoLabeling] Video loading started...")
        elif status.startswith("complete"):
            self.is_video_loading = False
            print("[VideoLabeling] Video loading complete!")
    
    # =========================================================================
    # KEYFRAME MARKING
    # =========================================================================
    
    async def mark_keyframe(self):
        """Mark the current frame as a keyframe (no thumbnail capture)."""
        if not self.current_video_id:
            return
        
        # Check if this frame is already a keyframe
        for kf in self.keyframes:
            if kf.frame_number == self.current_frame:
                print(f"[VideoLabeling] Frame {self.current_frame} is already a keyframe")
                return
        
        self.save_status = "saving"
        yield
        
        try:
            video = None
            for v in self.videos:
                if v.id == self.current_video_id:
                    video = v
                    break
            
            if not video:
                return
            
            # Create keyframe - no thumbnail capture needed
            keyframe_id = str(uuid.uuid4())
            
            # Trigger JS to notify Python (simplified - no thumbnail capture)
            yield rx.call_script(
                f"window.notifyKeyframeCreated && window.notifyKeyframeCreated({self.current_frame}, '{keyframe_id}')"
            )
            
        except Exception as e:
            print(f"[VideoLabeling] Error marking keyframe: {e}")
            self.save_status = ""
    
    async def handle_keyframe_captured(self, data_json: str):
        """Called from JS after a keyframe is created (no thumbnail upload)."""
        try:
            data = json.loads(data_json)
            keyframe_id = data.get("keyframe_id")
            frame_number = data.get("frame_number", 0)
            timestamp = data.get("timestamp", 0.0)
            success = data.get("success", False)
            
            if not success:
                print(f"[VideoLabeling] Failed to create keyframe")
                self.save_status = ""
                return
            
            # Create empty label file for YOLO training (background samples)
            r2 = R2Client()
            label_path = f"datasets/{self.current_dataset_id}/labels/{self.current_video_id}_f{frame_number}.txt"
            try:
                r2.upload_file(
                    file_bytes=b"",  # Empty file - will be populated when annotations are added
                    path=label_path,
                    content_type='text/plain'
                )
                print(f"[VideoLabeling] Created empty label file at {label_path}")
            except Exception as e:
                print(f"[VideoLabeling] Error creating label file: {e}")
            
            # Create keyframe record in database (no thumbnail_path)
            kf_data = create_keyframe(
                video_id=self.current_video_id,
                frame_number=frame_number,
                timestamp=timestamp,
            )
            
            if kf_data:
                # Add to local state
                new_keyframe = KeyframeModel(
                    id=str(kf_data.get("id", keyframe_id)),
                    video_id=self.current_video_id,
                    frame_number=frame_number,
                    timestamp=timestamp,
                    annotation_count=0,
                )
                
                self.keyframes = sorted(
                    self.keyframes + [new_keyframe],
                    key=lambda k: k.frame_number
                )
                
                # Auto-select the newly created keyframe
                for i, kf in enumerate(self.keyframes):
                    if kf.frame_number == frame_number:
                        self.selected_keyframe_idx = i
                        self.annotations = []  # New keyframe has no annotations yet
                        break
                
                print(f"[VideoLabeling] Keyframe marked at frame {frame_number}, auto-selected idx={self.selected_keyframe_idx}")
                
                # Refresh video counts to update keyframe_count on sidebar
                self._refresh_video_label_counts()
                
                # Notify JavaScript that a keyframe is now selected
                yield rx.call_script("window.setKeyframeSelected && window.setKeyframeSelected(true)")
                
                # Process pending annotation if one was waiting
                if self.pending_annotation_data:
                    print(f"[VideoLabeling] Processing pending annotation after keyframe creation")
                    try:
                        data = json.loads(self.pending_annotation_data)
                        
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
                        
                        self.annotations.append(new_ann)
                        self.selected_annotation_id = new_ann["id"]
                        self.is_dirty = True
                        
                        # Update keyframe annotation count
                        self._update_keyframe_annotation_count()
                        
                        print(f"[VideoLabeling] Added pending annotation. Total: {len(self.annotations)}")
                        print(f"[VideoLabeling] Pending annotation data: {json.dumps(new_ann)}")
                        
                        # Push to JS
                        yield rx.call_script(f"window.renderAnnotations && window.renderAnnotations({json.dumps(self.annotations)})")
                        
                        # Save
                        # Save
                        await self.save_annotations()
                        
                    except Exception as e:
                        print(f"[VideoLabeling] Error processing pending annotation: {e}")
                    finally:
                        self.pending_annotation_data = None
            
            self.save_status = "saved"
            yield
            
            # Process next keyframe in interval queue if any
            async for result in self._process_next_interval_keyframe():
                yield result
            
            # Only show "saved" status and clear it if not processing interval queue
            if not self.interval_frames_queue:
                import asyncio
                await asyncio.sleep(2)
                if self.save_status == "saved":
                    self.save_status = ""
            
        except Exception as e:
            print(f"[VideoLabeling] Error handling captured keyframe: {e}")
            import traceback
            traceback.print_exc()
            self.save_status = ""
            # Clear interval queue on error
            self.interval_frames_queue = []
            self.interval_total_count = 0
            self.interval_skipped_count = 0
    
    def select_keyframe(self, idx: int):
        """Select a keyframe to edit annotations."""
        # Save current keyframe annotations if dirty before switching (NON-BLOCKING)
        if self.is_dirty and self.selected_keyframe_idx >= 0 and self.selected_keyframe_idx < len(self.keyframes):
            current_kf = self.keyframes[self.selected_keyframe_idx]
            old_anns = self.annotation_cache.get(current_kf.id, [])
            self._save_keyframe_background(
                keyframe_id=current_kf.id,
                frame_number=current_kf.frame_number,
                annotations=self.annotations.copy(),
                old_annotations=list(old_anns),
                dataset_id=self.current_dataset_id,
                video_id=self.current_video_id,
            )
            self._update_cache(current_kf.id, self.annotations.copy())
            self.is_dirty = False
        
        if idx < 0 or idx >= len(self.keyframes):
            # Deselect - go back to live video view
            self.selected_keyframe_idx = -1
            self.annotations = []
            self.selected_annotation_id = None
            # Clear canvas annotations and notify JS that no keyframe is selected
            yield rx.call_script("window.renderAnnotations && window.renderAnnotations([])")
            yield rx.call_script("window.setKeyframeSelected && window.setKeyframeSelected(false)")
            return
        
        self.selected_keyframe_idx = idx
        self.last_clicked_keyframe_idx = idx
        kf = self.keyframes[idx]
        
        # Seek video to this frame
        self.current_frame = kf.frame_number
        self.current_timestamp = kf.timestamp
        
        # Load annotations for this keyframe (sync)
        self._load_keyframe_annotations_sync(kf.id)
        
        print(f"[VideoLabeling] Selected keyframe idx={idx}, frame={kf.frame_number}, annotations={len(self.annotations)}")
        
        # Yield JS calls to seek, push annotations, and notify that keyframe is selected
        yield rx.call_script(f"window.seekToFrame && window.seekToFrame({kf.frame_number}, {self.fps})")
        yield rx.call_script(f"window.renderAnnotations && window.renderAnnotations({json.dumps(self.annotations)})")
        yield rx.call_script("window.setKeyframeSelected && window.setKeyframeSelected(true)")
        # Auto-scroll to keep selected keyframe visible in sidebar
        yield rx.call_script(
            f"document.getElementById('keyframe-{kf.frame_number}')"
            f"?.scrollIntoView({{ behavior: 'smooth', block: 'nearest' }})"
        )
    
    async def _load_keyframe_annotations(self, keyframe_id: str):
        """Load annotations from R2 for a specific keyframe."""
        if not keyframe_id:
            self.annotations = []
            return
        
        # Find the keyframe
        keyframe = None
        for kf in self.keyframes:
            if kf.id == keyframe_id:
                keyframe = kf
                break
        
        if not keyframe:
            self.annotations = []
            return
        
        # Try to load from R2
        label_path = f"datasets/{self.current_dataset_id}/labels/{self.current_video_id}_f{keyframe.frame_number}.txt"
        
        try:
            r2 = R2Client()
            if r2.file_exists(label_path):
                content = r2.download_file(label_path)
                txt_content = content.decode('utf-8')
                self.annotations = self._from_yolo_format(txt_content)
                print(f"[VideoLabeling] Loaded {len(self.annotations)} annotations for keyframe {keyframe.frame_number}")
            else:
                self.annotations = []
                print(f"[VideoLabeling] No annotations found for keyframe {keyframe.frame_number}")
        except Exception as e:
            print(f"[VideoLabeling] Error loading annotations: {e}")
            self.annotations = []
        
        self.selected_annotation_id = None
        self.is_dirty = False
        
        # Push to JS
        return self.push_annotations_to_js()
    
    def _load_keyframe_annotations_sync(self, keyframe_id: str):
        """Load annotations with hybrid strategy: cache -> Supabase -> R2 fallback."""
        if not keyframe_id:
            self.annotations = []
            return
        
        # 1. Check cache first (instant: <1ms)
        if keyframe_id in self.annotation_cache:
            self.annotations = self.annotation_cache[keyframe_id].copy()
            print(f"[Cache HIT] Loaded {len(self.annotations)} annotations")
            self.selected_annotation_id = None
            self.is_dirty = False
            return
        
        # 2. Try Supabase JSONB column (fast: 5-20ms)
        db_annotations = get_keyframe_annotations(keyframe_id)
        
        if db_annotations is not None:
            self.annotations = db_annotations
            self._update_cache(keyframe_id, db_annotations)
            print(f"[Supabase] Loaded {len(self.annotations)} annotations")
            self.selected_annotation_id = None
            self.is_dirty = False
            return
        
        # 3. Fallback to R2 (slower: 50-200ms, for un-migrated data)
        keyframe = self._find_keyframe_by_id(keyframe_id)
        if not keyframe:
            self.annotations = []
            self.selected_annotation_id = None
            self.is_dirty = False
            return
        
        label_path = f"datasets/{self.current_dataset_id}/labels/{self.current_video_id}_f{keyframe.frame_number}.txt"
        
        try:
            r2 = R2Client()
            if r2.file_exists(label_path):
                content = r2.download_file(label_path)
                txt_content = content.decode("utf-8")
                self.annotations = self._from_yolo_format(txt_content)
                self._update_cache(keyframe_id, self.annotations)
                print(f"[R2 Fallback] Loaded {len(self.annotations)} annotations for keyframe {keyframe.frame_number}")
            else:
                self.annotations = []
        except Exception as e:
            print(f"[VideoLabeling] Error loading annotations from R2: {e}")
            self.annotations = []
        
        self.selected_annotation_id = None
        self.is_dirty = False
    
    async def _save_current_keyframe_annotations(self):
        """Save annotations for the currently selected keyframe."""
        if self.selected_keyframe_idx < 0 or self.selected_keyframe_idx >= len(self.keyframes):
            return
        
        kf = self.keyframes[self.selected_keyframe_idx]
        await self._save_keyframe_annotations(kf)
    
    async def _save_keyframe_annotations(self, keyframe: KeyframeModel):
        """Save annotations for a keyframe to R2 and Supabase."""
        if not keyframe:
            return
        
        try:
            from backend.annotation_service import save_annotations as svc_save
            
            # Handle empty annotations - need to delete R2 file if it exists
            if not self.annotations:
                r2 = R2Client()
                label_path = f"datasets/{self.current_dataset_id}/labels/{self.current_video_id}_f{keyframe.frame_number}.txt"
                try:
                    if r2.file_exists(label_path):
                        r2.delete_file(label_path)
                except Exception:
                    pass
                # Still save empty annotations to Supabase
                svc_save(
                    item_id=keyframe.id,
                    item_type="keyframe",
                    annotations=[],
                    dataset_id=self.current_dataset_id,
                    sync_r2=False  # Already handled deletion above
                )
            else:
                # Use service for dual-write
                svc_save(
                    item_id=keyframe.id,
                    item_type="keyframe",
                    annotations=list(self.annotations),
                    dataset_id=self.current_dataset_id,
                    sync_r2=True,
                    video_id=self.current_video_id,
                    frame_number=keyframe.frame_number
                )
            
            # Update cache
            self._update_cache(keyframe.id, self.annotations.copy())
            
            # Update local state
            for i, kf in enumerate(self.keyframes):
                if kf.id == keyframe.id:
                    self.keyframes[i] = KeyframeModel(
                        **{**kf.model_dump(), "annotation_count": len(self.annotations)}
                    )
                    break
            
            self.is_dirty = False
            print(f"[VideoLabeling] Saved {len(self.annotations)} annotations for keyframe {keyframe.frame_number}")
            
            # Auto-generate thumbnails if missing (first annotation triggers this)
            if self.annotations:
                self._auto_generate_video_thumbnails(keyframe, self.annotations[0])
                
        except Exception as e:
            print(f"[VideoLabeling] Error saving annotations: {e}")
    
    def _save_keyframe_annotations_sync(self, keyframe: KeyframeModel):
        """Save annotations to BOTH Supabase (primary) and R2 (export).
        
        This is the central save function - all annotation saves flow through here.
        """
        if not keyframe:
            return
        
        from backend.annotation_service import save_annotations as svc_save
        
        try:
            # Handle empty annotations - need to delete R2 file if it exists
            if not self.annotations:
                r2 = R2Client()
                label_path = f"datasets/{self.current_dataset_id}/labels/{self.current_video_id}_f{keyframe.frame_number}.txt"
                try:
                    if r2.file_exists(label_path):
                        r2.delete_file(label_path)
                except Exception:
                    pass
                # Still save empty annotations to Supabase
                svc_save(
                    item_id=keyframe.id,
                    item_type="keyframe",
                    annotations=[],
                    dataset_id=self.current_dataset_id,
                    sync_r2=False
                )
            else:
                # Use service for dual-write
                svc_save(
                    item_id=keyframe.id,
                    item_type="keyframe",
                    annotations=list(self.annotations),
                    dataset_id=self.current_dataset_id,
                    sync_r2=True,
                    video_id=self.current_video_id,
                    frame_number=keyframe.frame_number
                )
            
            print(f"[VideoLabeling] Saved {len(self.annotations)} annotations for keyframe {keyframe.frame_number}")
        except Exception as e:
            print(f"[VideoLabeling] Error saving annotations: {e}")
        
        # Update cache (ensures subsequent loads are instant)
        self._update_cache(keyframe.id, self.annotations.copy())
        
        # Update local keyframe state
        for i, kf in enumerate(self.keyframes):
            if kf.id == keyframe.id:
                self.keyframes[i] = KeyframeModel(
                    **{**kf.model_dump(), "annotation_count": len(self.annotations)}
                )
                break
        
        # Note: Video label counts are refreshed when switching to Videos tab
        self.is_dirty = False
    
    def _queue_save_keyframe_annotations(self):
        """Queue save for background processing."""
        if self.selected_keyframe_idx >= 0:
            return VideoLabelingState._save_current_keyframe_annotations
        return None
    
    def _save_keyframe_background(
        self,
        keyframe_id: str,
        frame_number: int,
        annotations: list,
        old_annotations: list,
        dataset_id: str,
        video_id: str,
    ):
        """Save keyframe annotations in a background thread (non-blocking).
        
        This method takes a snapshot of all required data and performs the
        save operation without blocking the main thread. Used during video
        switching to avoid 50-150ms blocking delay.
        
        Args:
            keyframe_id: UUID of the keyframe
            frame_number: Frame number (for R2 path)
            annotations: Copy of annotations list (to avoid mutation)
            old_annotations: Previous annotations for class count diff
            dataset_id: Current dataset ID (for R2 path)
            video_id: Current video ID (for R2 path)
        """
        def _background_save():
            try:
                import time
                t0 = time.perf_counter()
                
                # 1. Save to Supabase JSONB column (primary storage)
                try:
                    update_keyframe(keyframe_id, annotations=annotations, annotation_count=len(annotations))
                    print(f"[BG Save] Supabase: {len(annotations)} annotations for keyframe {frame_number}")
                except Exception as e:
                    print(f"[BG Save] Supabase error: {e}")
                
                # 2. Save to R2 in YOLO format (for training export)
                label_path = f"datasets/{dataset_id}/labels/{video_id}_f{frame_number}.txt"
                try:
                    r2 = R2Client()
                    if annotations:
                        yolo_content = self._annotations_to_yolo_static(annotations)
                        r2.upload_file(
                            file_bytes=yolo_content.encode("utf-8"),
                            path=label_path,
                            content_type="text/plain"
                        )
                    else:
                        # Delete empty annotation files
                        if r2.file_exists(label_path):
                            r2.delete_file(label_path)
                    print(f"[BG Save] R2: {len(annotations)} annotations for keyframe {frame_number}")
                except Exception as e:
                    print(f"[BG Save] R2 error: {e}")
                

                
                elapsed = (time.perf_counter() - t0) * 1000
                print(f"[BG Save] Complete in {elapsed:.0f}ms (would have blocked main thread)")
                
            except Exception as e:
                print(f"[BG Save] Critical error: {e}")
        
        # Launch background thread
        thread = threading.Thread(target=_background_save, daemon=True)
        thread.start()
        print(f"[BG Save] Launched background save for keyframe {frame_number}")
    
    @staticmethod
    def _annotations_to_yolo_static(annotations: list) -> str:
        """Convert annotations to YOLO format (static method for background thread).
        
        Format: class_id center_x center_y width height (normalized 0-1)
        """
        lines = []
        for ann in annotations:
            class_id = ann.get("class_id", 0)
            x = ann.get("x", 0)
            y = ann.get("y", 0)
            w = ann.get("w", 0)
            h = ann.get("h", 0)
            
            # Convert from corner-based to center-based
            center_x = x + w / 2
            center_y = y + h / 2
            
            lines.append(f"{class_id} {center_x:.6f} {center_y:.6f} {w:.6f} {h:.6f}")
        
        return "\n".join(lines)

    
    def _update_cache(self, keyframe_id: str, annotations: list):
        """Update annotation cache with LRU eviction."""
        # Evict oldest entry if cache is full
        if len(self.annotation_cache) >= self.cache_max_size:
            # Remove first (oldest) entry
            oldest_key = next(iter(self.annotation_cache))
            self.annotation_cache.pop(oldest_key)
            print(f"[Cache] Evicted oldest entry, cache size: {len(self.annotation_cache)}")
        
        self.annotation_cache[keyframe_id] = annotations.copy()
    
    def _find_keyframe_by_id(self, keyframe_id: str):
        """Helper to find keyframe by ID."""
        for kf in self.keyframes:
            if kf.id == keyframe_id:
                return kf
        return None
    
    def _clear_annotation_cache(self):
        """Clear annotation cache (call when switching videos)."""
        self.annotation_cache = {}
        print("[Cache] Cleared annotation cache")
    
    def delete_keyframe(self, keyframe_id: str):
        """Delete a keyframe and its annotations."""
        # Find the keyframe
        keyframe = None
        for kf in self.keyframes:
            if kf.id == keyframe_id:
                keyframe = kf
                break
        
        if not keyframe:
            return
        
        try:
            # Delete from R2 (thumbnail and labels)
            r2 = R2Client()
            
            # Delete thumbnail
            thumbnail_path = f"datasets/{self.current_dataset_id}/keyframes/{self.current_video_id}_f{keyframe.frame_number}.jpg"
            try:
                r2.delete_file(thumbnail_path)
            except Exception:
                pass
            
            # Delete labels
            label_path = f"datasets/{self.current_dataset_id}/labels/{self.current_video_id}_f{keyframe.frame_number}.txt"
            try:
                r2.delete_file(label_path)
            except Exception:
                pass
            
            # Delete from database
            db_delete_keyframe(keyframe_id)
            
            # Check if this was the currently selected keyframe BEFORE removing from list
            was_selected = False
            if self.selected_keyframe_idx >= 0 and self.selected_keyframe_idx < len(self.keyframes):
                if self.keyframes[self.selected_keyframe_idx].id == keyframe_id:
                    was_selected = True
            
            # Remove from local state
            self.keyframes = [kf for kf in self.keyframes if kf.id != keyframe_id]
            
            # Remove from annotation cache
            if keyframe_id in self.annotation_cache:
                del self.annotation_cache[keyframe_id]
            
            # Clear selection and canvas if the deleted keyframe was selected
            if was_selected:
                self.selected_keyframe_idx = -1
                self.annotations = []
                # Push empty annotations to JS to clear canvas
                return [
                    rx.call_script("window.renderAnnotations && window.renderAnnotations([])"),
                    rx.toast.success("Keyframe deleted"),
                ]
            
            print(f"[VideoLabeling] Deleted keyframe at frame {keyframe.frame_number}")
            
            # Refresh video counts in sidebar
            self._refresh_video_label_counts()
            
            return rx.toast.success("Keyframe deleted")
            
        except Exception as e:
            print(f"[VideoLabeling] Error deleting keyframe: {e}")
            return rx.toast.error("Failed to delete keyframe")
    
    # =========================================================================
    # KEYFRAME MULTI-SELECTION & BULK DELETE
    # =========================================================================
    
    def handle_keyframe_click(self, keyframe_id: str, shift_key: bool):
        """Handle click on a keyframe, supporting shift+click for range selection."""
        # Find the index of clicked keyframe
        clicked_idx = -1
        for i, kf in enumerate(self.keyframes):
            if kf.id == keyframe_id:
                clicked_idx = i
                break
        
        if clicked_idx == -1:
            return
        
        if shift_key and self.last_clicked_keyframe_idx >= 0:
            # Range selection
            start_idx = min(self.last_clicked_keyframe_idx, clicked_idx)
            end_idx = max(self.last_clicked_keyframe_idx, clicked_idx)
            
            range_ids = [self.keyframes[i].id for i in range(start_idx, end_idx + 1)]
            new_selection = list(set(self.selected_keyframe_ids + range_ids))
            self.selected_keyframe_ids = new_selection
        else:
            # Toggle single selection
            if keyframe_id in self.selected_keyframe_ids:
                self.selected_keyframe_ids = [id for id in self.selected_keyframe_ids if id != keyframe_id]
            else:
                self.selected_keyframe_ids = self.selected_keyframe_ids + [keyframe_id]
        
        self.last_clicked_keyframe_idx = clicked_idx
        
        # Also select the keyframe for viewing
        return VideoLabelingState.select_keyframe(clicked_idx)
    
    def clear_keyframe_selection(self):
        """Clear all selected keyframes."""
        self.selected_keyframe_ids = []
        self.last_clicked_keyframe_idx = -1
    
    @rx.var
    def selected_keyframe_count(self) -> int:
        """Number of selected keyframes."""
        return len(self.selected_keyframe_ids)
    
    @rx.var
    def has_keyframe_selection(self) -> bool:
        """Check if any keyframes are selected."""
        return len(self.selected_keyframe_ids) > 0
    
    def toggle_keyframe_panel(self):
        """Toggle the keyframe panel visibility."""
        print(f"[VideoLabeling] toggle_keyframe_panel called. Current: {self.show_keyframe_panel}")
        self.show_keyframe_panel = not self.show_keyframe_panel
        print(f"[VideoLabeling] toggle_keyframe_panel done. New: {self.show_keyframe_panel}")
    
    def toggle_focus_mode(self, _value=None):
        """Toggle focus mode - hide all panels for pure annotation view."""
        self.focus_mode = not self.focus_mode
        print(f"[VideoLabeling] Focus mode: {self.focus_mode}")
        
        # Consistent zoom change (1.85 in focus, 1.0 back)
        target_scale = 1.85 if self.focus_mode else 1.0
        return rx.call_script(f"window.animateTransform && window.animateTransform({target_scale}, 0, 0)")

    def reset_view(self):
        """Reset zoom and pan to default — delegates to JS."""
        target_scale = 1.85 if self.focus_mode else 1.0
        return rx.call_script(f"window.animateTransform && window.animateTransform({target_scale}, 0, 0)")

    def zoom_in(self):
        """Zoom in by one step (button click) — delegates to JS."""
        return rx.call_script("window.adjustZoom && window.adjustZoom(0.25)")
    
    def zoom_out(self):
        """Zoom out by one step (button click) — delegates to JS."""
        return rx.call_script("window.adjustZoom && window.adjustZoom(-0.25)")
    
    def toggle_fullscreen(self, _value=None):
        """
        No longer used for triggering - called only if the hidden input is manually triggered.
        Actual toggle is handled in JS for Chrome compatibility.
        """
        pass
    
    def set_fullscreen_state(self, is_fullscreen: str):
        """Sync fullscreen state from browser (called when Escape exits fullscreen)."""
        self.is_fullscreen = is_fullscreen == "true"
        print(f"[VideoLabeling] Fullscreen state synced: {self.is_fullscreen}")
    
    def select_all_keyframes(self):
        """Select all keyframes in the current video."""
        self.selected_keyframe_ids = [kf.id for kf in self.keyframes]
        if self.keyframes:
            self.last_clicked_keyframe_idx = len(self.keyframes) - 1
    
    def handle_keyframe_row_click(self, keyframe_id: str, idx: int):
        """Handle click on keyframe row - toggle selection."""
        if keyframe_id in self.selected_keyframe_ids:
            self.selected_keyframe_ids = [kid for kid in self.selected_keyframe_ids if kid != keyframe_id]
        else:
            self.selected_keyframe_ids = self.selected_keyframe_ids + [keyframe_id]
        self.last_clicked_keyframe_idx = idx
    
    def handle_keyframe_row_shift_click(self, keyframe_id: str, idx: int):
        """Handle shift+click for range selection."""
        if self.last_clicked_keyframe_idx < 0:
            # No previous selection, just select this one
            self.selected_keyframe_ids = [keyframe_id]
            self.last_clicked_keyframe_idx = idx
            return
        
        # Get range bounds
        start_idx = min(self.last_clicked_keyframe_idx, idx)
        end_idx = max(self.last_clicked_keyframe_idx, idx)
        
        # Select all keyframes in range
        new_selected = []
        for i, kf in enumerate(self.keyframes):
            if start_idx <= i <= end_idx:
                if kf.id not in new_selected:
                    new_selected.append(kf.id)
        
        self.selected_keyframe_ids = new_selected
        # Don't update last_clicked_keyframe_idx on shift-click to allow extending range
    
    def handle_shift_click_from_js(self, data: str):
        """Handle shift+click data from JavaScript."""
        import json
        try:
            parsed = json.loads(data)
            keyframe_id = parsed.get("keyframe_id", "")
            idx = parsed.get("idx", -1)
            if keyframe_id and idx >= 0:
                self.handle_keyframe_row_shift_click(keyframe_id, idx)
        except Exception as e:
            print(f"[VideoLabeling] Error parsing shift-click data: {e}")
    
    def open_bulk_delete_keyframes_modal(self):
        """Open the bulk delete confirmation modal."""
        print(f"[VideoLabeling] Open bulk delete modal. Selected: {len(self.selected_keyframe_ids)}")
        if self.selected_keyframe_ids:
            self.show_bulk_delete_keyframes_modal = True
    
    def close_bulk_delete_keyframes_modal(self):
        """Close the bulk delete modal."""
        self.show_bulk_delete_keyframes_modal = False
    
    async def confirm_bulk_delete_keyframes(self):
        """Delete all selected keyframes."""
        print(f"[VideoLabeling] Confirm bulk delete keyframes. Selected: {len(self.selected_keyframe_ids)}")
        if not self.selected_keyframe_ids:
            return
        
        self.is_bulk_deleting_keyframes = True
        yield
        
        try:
            r2 = R2Client()
            deleted_count = 0
            ids_to_delete = list(self.selected_keyframe_ids)
            
            for keyframe_id in ids_to_delete:
                keyframe = None
                for kf in self.keyframes:
                    if kf.id == keyframe_id:
                        keyframe = kf
                        break
                
                if not keyframe:
                    continue
                
                try:
                    # Delete thumbnail from R2
                    thumbnail_path = f"datasets/{self.current_dataset_id}/keyframes/{self.current_video_id}_f{keyframe.frame_number}.jpg"
                    try:
                        r2.delete_file(thumbnail_path)
                    except:
                        pass
                    
                    # Delete labels from R2
                    label_path = f"datasets/{self.current_dataset_id}/labels/{self.current_video_id}_f{keyframe.frame_number}.txt"
                    try:
                        r2.delete_file(label_path)
                    except:
                        pass
                    
                    # Delete from database
                    db_delete_keyframe(keyframe_id)
                    deleted_count += 1
                except Exception as e:
                    print(f"[VideoLabeling] Error deleting keyframe {keyframe_id}: {e}")
            
            # Remove from local state
            self.keyframes = [kf for kf in self.keyframes if kf.id not in ids_to_delete]
            
            # Remove from annotation cache
            for kf_id in ids_to_delete:
                if kf_id in self.annotation_cache:
                    del self.annotation_cache[kf_id]
            
            # Clear selection
            self.selected_keyframe_ids = []
            self.last_clicked_keyframe_idx = -1
            
            # Reset selected keyframe if it was deleted
            if self.selected_keyframe_idx >= 0:
                self.selected_keyframe_idx = -1
                self.annotations = []
            
            self.show_bulk_delete_keyframes_modal = False
            
            # Refresh video counts in sidebar
            self._refresh_video_label_counts()
            
            # Clear canvas if any keyframe was selected
            yield rx.call_script("window.renderAnnotations && window.renderAnnotations([])")
            yield rx.toast.success(f"Deleted {deleted_count} keyframe(s).")
            
        except Exception as e:
            print(f"[VideoLabeling] Error in bulk delete: {e}")
            yield rx.toast.error("Failed to delete some keyframes.")
        finally:
            self.is_bulk_deleting_keyframes = False

    # =========================================================================
    # KEYFRAME NAVIGATION
    # =========================================================================
    
    def navigate_to_previous_keyframe(self):
        """Navigate to the previous keyframe (Q shortcut)."""
        if not self.keyframes:
            return rx.toast.info("No keyframes available")
        
        # Find the closest keyframe before current frame
        previous_kf = None
        for kf in reversed(self.keyframes):
            if kf.frame_number < self.current_frame:
                previous_kf = kf
                break
        
        if previous_kf:
            return self.seek_to_frame(previous_kf.frame_number)
        else:
            return rx.toast.info("No previous keyframe")
    
    def navigate_to_next_keyframe(self):
        """Navigate to the next keyframe (E shortcut)."""
        if not self.keyframes:
            return rx.toast.info("No keyframes available")
        
        # Find the closest keyframe after current frame
        next_kf = None
        for kf in self.keyframes:
            if kf.frame_number > self.current_frame:
                next_kf = kf
                break
        
        if next_kf:
            return self.seek_to_frame(next_kf.frame_number)
        else:
            return rx.toast.info("No next keyframe")
    
    # =========================================================================
    # KEYFRAME INTERVAL CREATION
    # =========================================================================
    
    def set_interval_start(self):
        """Set the start frame for interval creation (I shortcut)."""
        self.interval_start_frame = self.current_frame
        print(f"[VideoLabeling] Set interval start to frame {self.current_frame}")
        return rx.toast.info(f"Start set to frame {self.current_frame + 1}")
    
    def set_interval_end(self):
        """Set the end frame for interval creation (O shortcut)."""
        self.interval_end_frame = self.current_frame
        print(f"[VideoLabeling] Set interval end to frame {self.current_frame}")
        return rx.toast.info(f"End set to frame {self.current_frame + 1}")
    
    def set_interval_step(self, step: str):
        """Update the interval step size."""
        try:
            step_value = int(step)
            if step_value > 0:
                self.interval_step = step_value
        except (ValueError, TypeError):
            pass
    
    def clear_interval(self):
        """Clear the interval selection."""
        self.interval_start_frame = -1
        self.interval_end_frame = -1
        return rx.toast.info("Interval cleared")
    
    async def create_interval_keyframes(self):
        """Create keyframes at regular intervals between start and end frames (P shortcut)."""
        if not self.has_interval_selection:
            yield rx.toast.warning("Please set both start and end frames first")
            return
        
        if self.interval_step <= 0:
            yield rx.toast.error("Step size must be greater than 0")
            return
        
        # Determine the iteration direction and range
        start = min(self.interval_start_frame, self.interval_end_frame)
        end = max(self.interval_start_frame, self.interval_end_frame)
        
        # Build list of frames to process
        frames_to_process = []
        frame = start
        while frame <= end:
            # Check if this frame is already a keyframe
            is_existing = any(kf.frame_number == frame for kf in self.keyframes)
            if not is_existing:
                frames_to_process.append(frame)
            frame += self.interval_step
        
        skipped_count = ((end - start) // self.interval_step + 1) - len(frames_to_process)
        
        if not frames_to_process:
            yield rx.toast.info("All frames in range already have keyframes")
            # Clear interval selection
            self.interval_start_frame = -1
            self.interval_end_frame = -1
            return
        
        print(f"[VideoLabeling] Creating {len(frames_to_process)} keyframes from frame {start} to {end} every {self.interval_step} frames")
        
        # Set up the queue for event-driven processing
        self.interval_frames_queue = frames_to_process
        self.interval_total_count = len(frames_to_process)
        self.interval_skipped_count = skipped_count
        
        self.save_status = "saving"
        yield
        
        # Start processing the first frame
        # The callback (handle_keyframe_captured) will process the rest
        if self.interval_frames_queue:
            next_frame = self.interval_frames_queue[0]
            for result in self.seek_to_frame(next_frame):
                yield result
            async for result in self.mark_keyframe():
                yield result
    
    async def _process_next_interval_keyframe(self):
        """Process the next keyframe in the interval queue (called from handle_keyframe_captured)."""
        if not self.interval_frames_queue:
            return
        
        # Remove the frame we just processed
        self.interval_frames_queue.pop(0)
        
        # Check if there are more frames to process
        if self.interval_frames_queue:
            next_frame = self.interval_frames_queue[0]
            remaining = len(self.interval_frames_queue)
            completed = self.interval_total_count - remaining
            print(f"[VideoLabeling] Progress: {completed}/{self.interval_total_count}")
            
            # Seek to the next frame (regular generator)
            for result in self.seek_to_frame(next_frame):
                yield result
            
            # Mark as keyframe (async generator)
            async for result in self.mark_keyframe():
                yield result
        else:
            # All done!
            print(f"[VideoLabeling] Interval keyframe creation complete")
            
            # Clear interval selection
            self.interval_start_frame = -1
            self.interval_end_frame = -1
            
            # Show success message
            message = f"Created {self.interval_total_count} keyframes"
            if self.interval_skipped_count > 0:
                message += f" ({self.interval_skipped_count} already existed)"
            
            # Reset queue
            self.interval_frames_queue = []
            self.interval_total_count = 0
            self.interval_skipped_count = 0
            
            yield rx.toast.success(message)
    
    # =========================================================================
    # VIDEO MANAGEMENT
    # =========================================================================
    
    def request_delete_video(self, video_id: str):
        """Open delete confirmation modal for a video."""
        # Find the video to get its name
        for v in self.videos:
            if v.id == video_id:
                self.video_to_delete_id = video_id
                self.video_to_delete_name = v.filename
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
    
    def delete_video(self, video_id: str):
        """Delete a video and all its associated data (keyframes, labels, files)."""
        try:
            # Find the video
            video = None
            video_idx = -1
            for i, v in enumerate(self.videos):
                if v.id == video_id:
                    video = v
                    video_idx = i
                    break
            
            if not video:
                return rx.toast.error("Video not found")
            
            # Delete from R2 (video file, thumbnail, and all keyframes/labels)
            r2 = R2Client()
            try:
                # Delete video file
                if video.path:
                    r2.delete_file(video.path)
                
                # Delete thumbnail
                if video.thumbnail_path:
                    r2.delete_file(video.thumbnail_path)
                
                # Delete all keyframes and labels for this video
                for kf in self.keyframes:
                    if kf.video_id == video_id:
                        # Delete keyframe thumbnail
                        keyframe_record = get_keyframe(kf.id)
                        if keyframe_record and keyframe_record.get("thumbnail_path"):
                            r2.delete_file(keyframe_record["thumbnail_path"])
                        
                        # Delete label file
                        label_path = f"datasets/{self.current_dataset_id}/labels/{video_id}_f{kf.frame_number}.txt"
                        try:
                            r2.delete_file(label_path)
                        except Exception:
                            pass  # Label might not exist
                        
                        # Delete keyframe from database
                        delete_keyframe(kf.id)
            except Exception as e:
                print(f"[VideoLabeling] Error deleting R2 files: {e}")
            
            # Delete video from database
            delete_video(video_id)
            
            # Remove from local state
            self.videos.pop(video_idx)
            
            # If this was the current video, switch to another one
            if self.current_video_id == video_id:
                if self.videos:
                    # Select the first video
                    return self.select_video(0)
                else:
                    # No videos left
                    self.current_video_id = ""
                    self.keyframes = []
                    self.annotations = []
            
            print(f"[VideoLabeling] Deleted video: {video.filename}")
            return rx.toast.success(f"Deleted {video.filename}")
            
        except Exception as e:
            print(f"[VideoLabeling] Error deleting video: {e}")
            return rx.toast.error("Failed to delete video")
    
    # =========================================================================
    # YOLO FORMAT CONVERSION
    # =========================================================================
    
    def _to_yolo_format(self) -> str:
        """Convert annotations to YOLO format string."""
        lines = []
        for ann in self.annotations:
            x = ann.get("x", 0)
            y = ann.get("y", 0)
            w = ann.get("width", 0)
            h = ann.get("height", 0)
            class_id = ann.get("class_id", 0)
            
            x_center = x + w / 2
            y_center = y + h / 2
            
            lines.append(f"{class_id} {x_center:.6f} {y_center:.6f} {w:.6f} {h:.6f}")
        
        return "\n".join(lines)
    
    def _from_yolo_format(self, txt_content: str) -> list[dict]:
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
                
                x = x_center - w / 2
                y = y_center - h / 2
                
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
            except (ValueError, IndexError):
                continue
        
        return annotations
    
    # =========================================================================
    # ANNOTATION HANDLING (reused from LabelingState pattern)
    # =========================================================================
    
    def set_tool(self, tool: str):
        """Set the current tool."""
        self.current_tool = tool
        self.is_drawing = False
        return rx.call_script(f"window.setTool && window.setTool('{tool}')")
    
    async def handle_new_annotation(self, data_json: str):
        """Called from JS when a new box is drawn."""
        # Check if current frame is already a keyframe
        # If not, auto-create one
        if self.selected_keyframe_idx < 0:
            # Check if this frame already exists as a keyframe (but not selected)
            keyframe_exists = False
            for i, kf in enumerate(self.keyframes):
                if kf.frame_number == self.current_frame:
                    # This frame is a keyframe, just not selected - select it
                    self.selected_keyframe_idx = i
                    self._load_keyframe_annotations_sync(kf.id)
                    keyframe_exists = True
                    print(f"[VideoLabeling] Auto-selected existing keyframe at frame {self.current_frame}")
                    # Notify JS that keyframe is selected and render existing annotations
                    yield rx.call_script("window.setKeyframeSelected && window.setKeyframeSelected(true)")
                    yield rx.call_script(f"window.renderAnnotations && window.renderAnnotations({json.dumps(self.annotations)})")
                    # Now process the annotation normally (fall through)
                    break
            
            if not keyframe_exists:
                # Need to create a new keyframe for this frame
                # Store the annotation data to add after keyframe is created
                self.pending_annotation_data = data_json
                print(f"[VideoLabeling] Auto-creating keyframe for frame {self.current_frame}, will add annotation after")
                # Call mark_keyframe and yield its results
                async for result in self.mark_keyframe():
                    yield result
                # After keyframe is created, handle_keyframe_captured will process pending_annotation_data
                return
        
        try:
            data = json.loads(data_json)
            
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
            
            self.annotations.append(new_ann)
            self.selected_annotation_id = new_ann["id"]
            self.is_dirty = True
            
            # Update keyframe annotation count
            self._update_keyframe_annotation_count()
            
            print(f"[VideoLabeling] Added annotation. Total: {len(self.annotations)}")
            print(f"[VideoLabeling] New annotation data: {json.dumps(new_ann)}")
            
            # Render immediately for visual feedback
            yield self.push_annotations_to_js()
            
            # Trigger autosave
            # Trigger autosave
            await self.save_annotations()
            
        except Exception as e:
            print(f"[VideoLabeling] Error adding annotation: {e}")
    
    def _update_keyframe_annotation_count(self):
        """Update annotation count for the selected keyframe."""
        if self.selected_keyframe_idx < 0 or self.selected_keyframe_idx >= len(self.keyframes):
            return
        
        kf = self.keyframes[self.selected_keyframe_idx]
        updated_kf = KeyframeModel(
            **{**kf.model_dump(), "annotation_count": len(self.annotations)}
        )
        self.keyframes[self.selected_keyframe_idx] = updated_kf
        
        # Refresh current video counts in sidebar (shows updated "labels" badge)
        self._refresh_video_label_counts()
    
    def handle_selection_change(self, annotation_id: str):
        """Called from JS when selection changes."""
        self.selected_annotation_id = annotation_id if annotation_id else None
    
    async def handle_annotation_deleted(self, annotation_id: str):
        """Called from JS when an annotation is deleted."""
        print(f"[VideoLabeling] handle_annotation_deleted: {annotation_id}")
        if not annotation_id:
            return
        
        self.annotations = [a for a in self.annotations if a.get("id") != annotation_id]
        self.is_dirty = True
        self._update_keyframe_annotation_count()
        self.selected_annotation_id = None
        print(f"[VideoLabeling] Calling save_annotations...")
        await self.save_annotations()
    
    async def handle_annotation_updated(self, data_json: str):
        """Called from JS when an annotation is resized/moved."""
        if not data_json:
            return
        
        try:
            data = json.loads(data_json)
            annotation_id = data.get("id")
            
            if not annotation_id:
                return
            
            for i, ann in enumerate(self.annotations):
                if ann.get("id") == annotation_id:
                    self.annotations[i] = {
                        **ann,
                        "x": data.get("x", ann.get("x")),
                        "y": data.get("y", ann.get("y")),
                        "width": data.get("width", ann.get("width")),
                        "height": data.get("height", ann.get("height")),
                    }
                    break
            
            self.is_dirty = True
            await self.save_annotations()
        except Exception as e:
            print(f"[VideoLabeling] Error updating annotation: {e}")
    
    def delete_selected_annotation(self):
        """Delete the currently selected annotation."""
        return rx.call_script("window.deleteSelectedAnnotation && window.deleteSelectedAnnotation()")
    
    async def delete_annotation(self, annotation_id: str):
        """Delete a specific annotation by ID."""
        if not annotation_id:
            return
            
        self.annotations = [a for a in self.annotations if a.get("id") != annotation_id]
        
        # If the deleted one was selected, clear selection
        if self.selected_annotation_id == annotation_id:
            self.selected_annotation_id = None
            
        self.is_dirty = True
        self._update_keyframe_annotation_count()
        
        # Sync to JS
        yield self.push_annotations_to_js()
        
        # Save
        await self.save_annotations()

    async def update_annotation_class(self, annotation_id: str, new_class_id: int):
        """Update the class of an annotation."""
        # Validate class_id
        if not (0 <= new_class_id < len(self.project_classes)):
            return
            
        class_name = self.project_classes[new_class_id]
        
        updated = False
        new_annotations = []
        for ann in self.annotations:
            if ann.get("id") == annotation_id:
                new_annotations.append({
                    **ann,
                    "class_id": new_class_id,
                    "class_name": class_name
                })
                updated = True
            else:
                new_annotations.append(ann)
        
        if updated:
            self.annotations = new_annotations
            self.is_dirty = True
            yield self.push_annotations_to_js()
            await self.save_annotations()
    
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
    
    async def context_menu_change_class(self, new_class_name: str):
        """Change class of context menu annotation (wrapper for update_annotation_class)."""
        if not self.context_menu_annotation_id:
            return
        
        # Find class_id from class_name
        if new_class_name not in self.project_classes:
            return
        
        new_class_id = self.project_classes.index(new_class_name)
        
        # Use existing class change logic
        async for result in self.update_annotation_class(self.context_menu_annotation_id, new_class_id):
            yield result
        
        self.close_context_menu()
    
    def set_as_project_thumbnail(self):
        """Generate thumbnail from context menu annotation and set as project cover."""
        if not self.context_menu_annotation_id:
            return rx.toast.error("No annotation selected")
        
        # Find annotation
        ann = next((a for a in self.annotations if a["id"] == self.context_menu_annotation_id), None)
        if not ann:
            return rx.toast.error("Annotation not found")
        
        # Get current keyframe
        if self.selected_keyframe_idx < 0 or self.selected_keyframe_idx >= len(self.keyframes):
            return rx.toast.error("No keyframe selected")
        
        keyframe = self.keyframes[self.selected_keyframe_idx]
        
        # Find current video
        current_vid = next((v for v in self.videos if v.id == self.current_video_id), None)
        if not current_vid:
            return rx.toast.error("Video not found")
        
        try:
            from backend.r2_storage import R2Client
            from backend.core.thumbnail_generator import generate_label_thumbnail, extract_video_frame
            from backend.supabase_client import update_project
            
            r2 = R2Client()
            
            # Extract frame from video at keyframe frame_number
            frame_bytes = extract_video_frame(current_vid.video_url, keyframe.frame_number, self.fps)
            if not frame_bytes:
                return rx.toast.error("Failed to extract video frame")
            
            # Generate thumbnail
            thumb_bytes = generate_label_thumbnail(frame_bytes, ann)
            if not thumb_bytes:
                return rx.toast.error("Failed to generate thumbnail")
            
            # Upload to R2
            thumb_path = f"projects/{self.current_project_id}/thumbnail.jpg"
            r2.upload_file(thumb_bytes, thumb_path, content_type="image/jpeg")
            
            # Update database
            update_project(self.current_project_id, thumbnail_r2_path=thumb_path)
            
            self.close_context_menu()
            print(f"[Context Menu] Set project thumbnail from video annotation {ann['id']}")
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
        
        # Get current keyframe
        if self.selected_keyframe_idx < 0 or self.selected_keyframe_idx >= len(self.keyframes):
            return rx.toast.error("No keyframe selected")
        
        keyframe = self.keyframes[self.selected_keyframe_idx]
        
        # Find current video
        current_vid = next((v for v in self.videos if v.id == self.current_video_id), None)
        if not current_vid:
            return rx.toast.error("Video not found")
        
        try:
            from backend.r2_storage import R2Client
            from backend.core.thumbnail_generator import generate_label_thumbnail, extract_video_frame
            from backend.supabase_client import update_dataset
            
            r2 = R2Client()
            
            # Extract frame from video at keyframe frame_number
            frame_bytes = extract_video_frame(current_vid.video_url, keyframe.frame_number, self.fps)
            if not frame_bytes:
                return rx.toast.error("Failed to extract video frame")
            
            # Generate thumbnail
            thumb_bytes = generate_label_thumbnail(frame_bytes, ann)
            if not thumb_bytes:
                return rx.toast.error("Failed to generate thumbnail")
            
            # Upload to R2
            thumb_path = f"datasets/{self.current_dataset_id}/thumbnail.jpg"
            r2.upload_file(thumb_bytes, thumb_path, content_type="image/jpeg")
            
            # Update database
            update_dataset(self.current_dataset_id, thumbnail_r2_path=thumb_path)
            
            self.close_context_menu()
            print(f"[Context Menu] Set dataset thumbnail from video annotation {ann['id']}")
            return rx.toast.success("Dataset thumbnail updated!")
            
        except Exception as e:
            print(f"[Context Menu] Error setting dataset thumbnail: {e}")
            import traceback
            traceback.print_exc()
            return rx.toast.error(f"Error: {str(e)}")
    
    def _auto_generate_video_thumbnails(self, keyframe: "KeyframeModel", first_annotation: dict):
        """Auto-generate project/dataset thumbnails from video keyframe if missing."""
        try:
            from backend.supabase_client import get_project, get_dataset, update_project, update_dataset
            from backend.core.thumbnail_generator import generate_label_thumbnail, extract_video_frame
            from backend.r2_storage import R2Client
            
            r2 = R2Client()
            
            # Check if project needs thumbnail
            project = get_project(self.current_project_id)
            project_needs_thumb = project and not project.get("thumbnail_r2_path")
            
            # Check if dataset needs thumbnail
            dataset = get_dataset(self.current_dataset_id)
            dataset_needs_thumb = dataset and not dataset.get("thumbnail_r2_path")
            
            if not project_needs_thumb and not dataset_needs_thumb:
                return  # Both already have thumbnails
            
            # Get current video for URL
            current_vid = next((v for v in self.videos if v.id == self.current_video_id), None)
            if not current_vid or not current_vid.video_url:
                return
            
            # Extract frame from video
            frame_bytes = extract_video_frame(current_vid.video_url, keyframe.frame_number, self.fps)
            if not frame_bytes:
                print("[AutoThumbnail] Failed to extract video frame")
                return
            
            # Generate thumbnail
            thumb_bytes = generate_label_thumbnail(frame_bytes, first_annotation)
            if not thumb_bytes:
                return
            
            # Save project thumbnail if needed
            if project_needs_thumb:
                thumb_path = f"projects/{self.current_project_id}/thumbnail.jpg"
                r2.upload_file(thumb_bytes, thumb_path, content_type="image/jpeg")
                update_project(self.current_project_id, thumbnail_r2_path=thumb_path)
                print(f"[AutoThumbnail] Generated project thumbnail for {self.current_project_id[:8]}...")
            
            # Save dataset thumbnail if needed
            if dataset_needs_thumb:
                thumb_path = f"datasets/{self.current_dataset_id}/thumbnail.jpg"
                r2.upload_file(thumb_bytes, thumb_path, content_type="image/jpeg")
                update_dataset(self.current_dataset_id, thumbnail_r2_path=thumb_path)
                print(f"[AutoThumbnail] Generated dataset thumbnail for {self.current_dataset_id[:8]}...")
                
        except Exception as e:
            print(f"[AutoThumbnail] Error: {e}")
    
    async def save_annotations(self):
        """Trigger autosave of annotations."""
        print(f"[VideoLabeling] save_annotations called. idx={self.selected_keyframe_idx}")
        if self.selected_keyframe_idx < 0:
            print("[VideoLabeling] No keyframe selected, skipping save")
            return
        await self._save_current_keyframe_annotations()
    
    def push_annotations_to_js(self):
        """Send all annotations to JS for rendering."""
        return rx.call_script(f"window.renderAnnotations && window.renderAnnotations({json.dumps(self.annotations)})")
    
    # =========================================================================
    # CLASS MANAGEMENT
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
    
    def set_current_class(self, idx: int):
        """Set the current class for new annotations."""
        self.current_class_id = idx
        # Sync to JavaScript for optimistic annotation rendering
        class_name = self.project_classes[idx] if 0 <= idx < len(self.project_classes) else "Unknown"
        return rx.call_script(f"window.setCurrentClass && window.setCurrentClass({idx}, '{class_name}')")
    
    # Class Renaming State
    show_rename_class_modal: bool = False
    class_to_rename_idx: int = -1
    class_rename_old_name: str = ""
    class_rename_new_name: str = ""
    
    # Class Deletion State
    delete_confirmation_input: str = ""
    
    @rx.var
    def can_confirm_delete_class(self) -> bool:
        """Check if delete confirmation input is valid."""
        return self.delete_confirmation_input.lower() == "delete"

    def handle_class_select(self, index_str: str):
        """Select class by keyboard shortcut (1-9 keys)."""
        try:
            idx = int(index_str)
            if 0 <= idx < len(self.project_classes):
                self.current_class_id = idx
                class_name = self.project_classes[idx]
                return rx.call_script(f"window.setCurrentClass && window.setCurrentClass({idx}, '{class_name}')")
        except ValueError:
            pass
    
    def prompt_rename_class(self, idx: int):
        """Open modal to rename a class."""
        if 0 <= idx < len(self.project_classes):
            self.class_to_rename_idx = idx
            self.class_rename_old_name = self.project_classes[idx]
            self.class_rename_new_name = self.project_classes[idx]
            self.show_rename_class_modal = True
            
    def cancel_rename_class(self):
        """Close rename class modal."""
        self.show_rename_class_modal = False
        self.class_to_rename_idx = -1
        
    async def handle_rename_keydown(self, key: str):
        """Handle keydown in rename input."""
        if key == "Enter":
            await self.confirm_rename_class()
            
    def set_rename_new_name(self, name: str):
        """Update the new name for renaming."""
        self.class_rename_new_name = name

    def handle_add_class_keydown(self, key: str):
        """Handle Enter key in add class input."""
        if key == "Enter" and self.new_class_name.strip():
            self.add_class()

    async def handle_delete_class_keydown(self, key: str):
        """Handle Enter key in delete class confirmation."""
        if key == "Enter" and self.delete_confirmation_input.lower() == "delete":
            async for event in self.confirm_delete_class():
                yield event

    async def handle_interval_keydown(self, key: str):
        """Handle Enter key in interval step input."""
        if key == "Enter" and self.has_interval_selection:
            async for event in self.create_interval_keyframes():
                yield event

    async def handle_autolabel_keydown(self, key: str):
        """Handle Enter key in autolabel prompt."""
        if key == "Enter" and self.autolabel_prompt.strip() and not self.is_autolabeling:
            async for event in self.start_autolabel():
                yield event

    async def confirm_rename_class(self):
        """Execute class renaming."""
        idx = self.class_to_rename_idx
        new_name = self.class_rename_new_name.strip()
        
        if idx < 0 or idx >= len(self.project_classes):
            return
            
        if not new_name:
            yield rx.toast.error("Class name cannot be empty")
            return
            
        if new_name in self.project_classes and self.project_classes[idx] != new_name:
            yield rx.toast.error("Class name already exists")
            return
            
        self.project_classes[idx] = new_name
        update_project(self.current_project_id, classes=self.project_classes)
        
        # If this is the current class, update JS
        if self.current_class_id == idx:
            yield rx.call_script(f"window.setCurrentClass && window.setCurrentClass({idx}, '{new_name}')")
        
        # Refresh local annotations to reflect new name
        if self.annotations:
            for i, ann in enumerate(self.annotations):
                if ann.get("class_id") == idx:
                    self.annotations[i] = {**ann, "class_name": new_name}
            yield self.push_annotations_to_js()
        
        yield rx.toast.success("Class renamed")
        self.show_rename_class_modal = False

    def prompt_delete_class(self, idx: int):
        """Open modal to confirm class deletion."""
        if 0 <= idx < len(self.project_classes):
            self.class_to_delete_idx = idx
            self.class_to_delete_name = self.project_classes[idx]
            self.delete_confirmation_input = ""  # Reset confirmation input
            self.show_delete_class_modal = True

    def cancel_delete_class(self):
        """Close delete class modal."""
        self.show_delete_class_modal = False
        self.class_to_delete_idx = -1
        self.delete_confirmation_input = ""
        
    def set_delete_confirmation(self, value: str):
        """Update delete confirmation input."""
        self.delete_confirmation_input = value

    async def confirm_delete_class(self):
        """Execute class deletion and cleanup - simplified approach matching dataset detail."""
        if self.delete_confirmation_input.lower() != "delete":
            yield rx.toast.error("Please type 'delete' to confirm.")
            return

        idx = self.class_to_delete_idx
        if idx < 0 or idx >= len(self.project_classes):
            return
        
        deleted_class_name = self.class_to_delete_name
        
        # Close modal immediately
        self.show_delete_class_modal = False
        self.class_to_delete_idx = -1
        self.delete_confirmation_input = ""
        yield
        
        try:
            from backend.supabase_client import delete_class_from_annotations, update_project
            
            # Get new classes list (with deleted class removed)
            new_classes = [c for c in self.project_classes if c != deleted_class_name]
            
            # Delete from annotations in database
            count = delete_class_from_annotations(
                self.current_project_id, deleted_class_name, idx, new_classes
            )
            
            # Update project classes in database (persist the deletion)
            update_project(self.current_project_id, classes=new_classes)
            
            # Update local state
            self.project_classes = new_classes
            
            # Adjust current_class_id if needed
            if self.current_class_id == idx:
                self.current_class_id = 0
            elif self.current_class_id > idx:
                self.current_class_id -= 1
            
            # Clear annotations for current keyframe and reload from DATABASE (not R2)
            # delete_class_from_annotations only updates the database, not R2 files
            if self.selected_keyframe_idx >= 0 and self.selected_keyframe_idx < len(self.keyframes):
                kf = self.keyframes[self.selected_keyframe_idx]
                # Clear the cache entry so it gets reloaded
                if kf.id in self.annotation_cache:
                    del self.annotation_cache[kf.id]
                
                # Load annotations directly from database (not R2)
                from backend.supabase_client import get_supabase
                supabase = get_supabase()
                result = supabase.table("keyframes").select("annotations").eq("id", kf.id).execute()
                if result.data and result.data[0].get("annotations"):
                    self.annotations = result.data[0]["annotations"]
                else:
                    self.annotations = []
                
                # Update cache with fresh data
                self.annotation_cache[kf.id] = self.annotations.copy()
                
                # Push to JS canvas
                yield rx.call_script(f"window.renderAnnotations && window.renderAnnotations({json.dumps(self.annotations)})")
            
            # Refresh video label counts
            self._refresh_video_label_counts()
            
            yield rx.toast.success(f"Deleted class '{deleted_class_name}' ({count} keyframes updated)")
            
        except Exception as e:
            print(f"[VideoLabeling] Error deleting class: {e}")
            import traceback
            traceback.print_exc()
            yield rx.toast.error(f"Failed to delete class: {e}")

    
    def toggle_shortcuts_help(self, _: str = ""):
        """Toggle the keyboard shortcuts help overlay."""
        self.show_shortcuts_help = not self.show_shortcuts_help
    
    def handle_keyframe_mark(self, data_json: str):
        """Handle keyframe marking triggered from keyboard shortcut (K key)."""
        try:
            # Just mark the keyframe - no longer need to parse isEmpty
            return VideoLabelingState.mark_keyframe
        except Exception as e:
            print(f"[VideoLabeling] Error parsing keyframe mark: {e}")
    
    async def navigate_back(self):
        """Navigate back to the dataset page, saving any unsaved changes first."""
        if self.is_dirty and self.selected_keyframe_idx >= 0:
            await self._save_current_keyframe_annotations()
        
        return rx.redirect(f"/projects/{self.current_project_id}/datasets/{self.current_dataset_id}")

    
    # =========================================================================
    # COMPUTED PROPERTIES
    # =========================================================================
    
    @rx.var
    def frame_display(self) -> str:
        """Display current frame and timestamp."""
        mins = int(self.current_timestamp // 60)
        secs = self.current_timestamp % 60
        return f"f:{self.current_frame:04d} / {mins}:{secs:05.2f}s"
    
    @rx.var
    def progress_percent(self) -> float:
        """Calculate progress through the video."""
        if self.total_frames <= 0:
            return 0
        return (self.current_frame / self.total_frames) * 100
    
    @rx.var
    def keyframe_count(self) -> int:
        """Get number of keyframes."""
        return len(self.keyframes)
    
    @rx.var
    def has_keyframes(self) -> bool:
        """Check if video has any keyframes."""
        return len(self.keyframes) > 0
    
    @rx.var
    def labeled_keyframe_count(self) -> int:
        """Get number of keyframes with annotations."""
        return len([kf for kf in self.keyframes if kf.annotation_count > 0])
    
    @rx.var
    def current_image_url(self) -> str:
        """For compatibility with existing canvas.js - returns empty for video mode."""
        return ""
    
    @rx.var
    def has_selected_keyframe(self) -> bool:
        """Check if a keyframe is currently selected."""
        return self.selected_keyframe_idx >= 0
    
    # =========================================================================
    # AUTO-LABELING (SAM3) FOR KEYFRAMES
    # =========================================================================
    
    @rx.var
    def unlabeled_keyframe_count(self) -> int:
        """Count keyframes without annotations."""
        return len([kf for kf in self.keyframes if kf.annotation_count == 0])
    
    # =========================================================================
    # EMPTY KEYFRAMES STATS MODAL
    # =========================================================================
    
    def open_empty_stats_modal(self):
        """Open the empty keyframes stats modal."""
        self.show_empty_stats_modal = True
        self.empty_delete_confirmation = ""
    
    def close_empty_stats_modal(self):
        """Close the empty keyframes stats modal."""
        self.show_empty_stats_modal = False
        self.empty_delete_confirmation = ""
    
    def set_empty_delete_confirmation(self, value: str):
        """Update the delete confirmation input."""
        self.empty_delete_confirmation = value
    
    @rx.var
    def can_confirm_delete_empty(self) -> bool:
        """Check if delete confirmation is valid."""
        return self.empty_delete_confirmation.lower() == "delete"
    
    async def delete_empty_keyframes(self):
        """Delete all keyframes with zero annotations."""
        if self.empty_delete_confirmation.lower() != "delete":
            yield rx.toast.error("Please type 'delete' to confirm.")
            return
        
        self.is_deleting_empty_keyframes = True
        yield
        
        try:
            # Get list of empty keyframe IDs
            empty_kf_ids = [kf.id for kf in self.keyframes if kf.annotation_count == 0]
            
            if not empty_kf_ids:
                self.is_deleting_empty_keyframes = False
                self.show_empty_stats_modal = False
                yield rx.toast.info("No empty keyframes to delete.")
                return
            
            deleted_count = 0
            for kf_id in empty_kf_ids:
                try:
                    # Delete from database
                    db_delete_keyframe(kf_id)
                    
                    # Clean up local caches
                    if kf_id in self.annotation_cache:
                        del self.annotation_cache[kf_id]
                    
                    deleted_count += 1
                except Exception as e:
                    print(f"[VideoLabeling] Error deleting keyframe {kf_id}: {e}")
            
            # Find if current keyframe was deleted
            current_kf_id = ""
            if self.selected_keyframe_idx >= 0 and self.selected_keyframe_idx < len(self.keyframes):
                current_kf_id = self.keyframes[self.selected_keyframe_idx].id

            # Remove from local state
            self.keyframes = [kf for kf in self.keyframes if kf.id not in empty_kf_ids]
            
            # Clear selection if needed
            self.selected_keyframe_ids = [id for id in self.selected_keyframe_ids if id not in empty_kf_ids]
            
            # Handle current keyframe deletion
            if current_kf_id in empty_kf_ids:
                 # Go back to live view
                 self.selected_keyframe_idx = -1
                 self.annotations = []
                 yield rx.call_script("window.setKeyframeSelected && window.setKeyframeSelected(false)")
                 yield rx.call_script("window.renderAnnotations && window.renderAnnotations([])")
            else:
                # Update selected_keyframe_idx if it shifted
                if current_kf_id:
                    for i, kf in enumerate(self.keyframes):
                        if kf.id == current_kf_id:
                            self.selected_keyframe_idx = i
                            break
            
            self.show_empty_stats_modal = False
            self.empty_delete_confirmation = ""
            yield rx.toast.success(f"Deleted {deleted_count} empty keyframe(s).")
            
        except Exception as e:
            print(f"[DEBUG] Error in delete empty keyframes: {e}")
            yield rx.toast.error("Failed to delete some keyframes.")
        finally:
            self.is_deleting_empty_keyframes = False
    
    @rx.var
    def can_autolabel(self) -> bool:
        """Check if auto-labeling can be started (SAM3 mode)."""
        # At least one generation option must be selected
        if not self.autolabel_generate_bboxes and not self.autolabel_generate_masks:
            return False
        
        # Must have keyframes and not be currently running
        if len(self.keyframes) <= 0 or self.is_autolabeling:
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
    
    @rx.var
    def autolabel_confidence_percentage(self) -> str:
        """Get confidence as percentage string for display."""
        return f"{int(self.autolabel_confidence * 100)}%"
    
    def set_autolabel_prompt(self, value: str):
        """Set the autolabel prompt text and parse terms."""
        self.autolabel_prompt = value
        # Parse comma-separated terms
        if value.strip():
            terms = [t.strip() for t in value.split(",") if t.strip()]
            self.autolabel_prompt_terms = terms
            # Initialize mappings with -1 (unmapped) for new terms
            if len(terms) != len(self.autolabel_class_mappings):
                self.autolabel_class_mappings = [-1] * len(terms)
        else:
            self.autolabel_prompt_terms = []
            self.autolabel_class_mappings = []
    
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
    
    def set_autolabel_confidence(self, value: list[float]):
        """Set confidence from slider (receives list from Radix slider)."""
        if value and len(value) > 0:
            self.autolabel_confidence = value[0]
    
    def toggle_autolabel_logs(self):
        """Toggle log panel visibility."""
        self.show_autolabel_logs = not self.show_autolabel_logs
    
    def toggle_autolabel_panel(self):
        """Toggle autolabel panel visibility (legacy)."""
        self.show_autolabel_panel = not self.show_autolabel_panel
    
    # =========================================================================
    # AUTOLABEL MODAL CONTROLS
    # =========================================================================
    
    async def open_autolabel_modal(self):
        """Open autolabel modal and load available models."""
        self.show_autolabel_modal = True
        self.autolabel_error = ""
        # Initialize video selection (all videos selected by default)
        if not self.selected_video_ids_for_autolabel:
            self.selected_video_ids_for_autolabel = [v.id for v in self.videos]
        # Load available YOLO models for autolabeling
        await self._load_autolabel_models()
        # Load local machines for compute target toggle
        auth_state = await self.get_state(AuthState)
        user_id = auth_state.user.get("id") if auth_state.user else None
        if user_id:
            self.local_machines = get_user_local_machines(user_id)
    
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
    
    def set_autolabel_mode(self, mode: str):
        """Switch between SAM3 and YOLO modes."""
        self.autolabel_mode = mode
    
    def select_autolabel_model(self, model_id: str):
        """Select a YOLO model for autolabeling."""
        self.selected_autolabel_model_id = model_id
    
    def toggle_video_for_autolabel(self, video_id: str):
        """Toggle a video's selection for autolabeling."""
        if video_id in self.selected_video_ids_for_autolabel:
            self.selected_video_ids_for_autolabel = [
                vid for vid in self.selected_video_ids_for_autolabel if vid != video_id
            ]
        else:
            self.selected_video_ids_for_autolabel = self.selected_video_ids_for_autolabel + [video_id]
    
    def select_all_videos_for_autolabel(self):
        """Select all videos for autolabeling."""
        self.selected_video_ids_for_autolabel = [v.id for v in self.videos]
    
    def deselect_all_videos_for_autolabel(self):
        """Deselect all videos for autolabeling."""
        self.selected_video_ids_for_autolabel = []
    
    async def _load_autolabel_models(self):
        """Load models with volume_path available for autolabeling."""
        from backend.supabase_client import get_autolabel_models
        
        auth_state = await self.get_state(AuthState)
        user_id = auth_state.user.get("id") if auth_state.user else None
        
        if not user_id:
            self.available_autolabel_models = []
            return
        
        try:
            models = get_autolabel_models(user_id)
            self.available_autolabel_models = models
            print(f"[AutoLabel/Video] Loaded {len(models)} models with volume_path")
            
            # Restore saved model preference
            prefs = get_user_preferences(user_id)
            autolabel_prefs = prefs.get("autolabel", {})
            saved_model_id = autolabel_prefs.get("selected_model_id", "")
            if saved_model_id:
                # Verify model still exists
                if any(m.get("id") == saved_model_id for m in models):
                    self.selected_autolabel_model_id = saved_model_id
                    print(f"[AutoLabel/Video] Restored saved model: {saved_model_id}")
        except Exception as e:
            print(f"[AutoLabel/Video] Error loading models: {e}")
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
            len(self.selected_video_ids_for_autolabel) > 0 and
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
    def selected_video_count_for_autolabel(self) -> int:
        """Number of videos selected for autolabeling."""
        return len(self.selected_video_ids_for_autolabel)
    
    @rx.var
    def total_keyframes_for_autolabel(self) -> int:
        """Total keyframe count across selected videos."""
        return sum(
            v.keyframe_count for v in self.videos 
            if v.id in self.selected_video_ids_for_autolabel
        )
    
    @rx.event(background=True)
    async def start_autolabel(self):
        """Start auto-labeling job on Modal for unlabeled keyframes across all selected datasets.
        
        Enhanced to:
        - Process ALL unlabeled keyframes from ALL videos in current dataset
        - Create large frames automatically for keyframes that don't have them yet
        - Skip keyframes that already have annotations (annotation_count > 0)
        """
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
            
            # Reset state
            self.is_autolabeling = True
            self.autolabel_error = ""
            self.autolabel_logs = f"Starting auto-labeling job ({mode.upper()} mode)...\n"
            self.show_autolabel_logs = True
            self.show_autolabel_panel = True
            
            # Capture mode-specific settings
            autolabel_mode = self.autolabel_mode
            selected_model_id = self.selected_autolabel_model_id
            selected_video_ids = self.selected_video_ids_for_autolabel
            target = self.compute_target
            machine_name = self.selected_machine if target == "local" else None
            
            # Build prompt_class_map from state mappings
            prompt_class_map = {}
            for i, term in enumerate(self.autolabel_prompt_terms):
                if i < len(self.autolabel_class_mappings):
                    prompt_class_map[term] = self.autolabel_class_mappings[i]
            
            generate_bboxes = self.autolabel_generate_bboxes
            generate_masks = self.autolabel_generate_masks
        
        yield
        
        try:
            from backend.supabase_client import (
                create_autolabel_job,
                get_dataset_videos,
                get_video_keyframes,
                update_keyframe,
                get_keyframe
            )
            from backend.r2_storage import R2Client
            from backend.frame_extractor import extract_and_store_full_frame
            
            r2 = R2Client()
            
            # Collection structures for all keyframes across all videos
            keyframe_urls = {}
            keyframe_meta = {}
            
            async with self:
                dataset_id = self.current_dataset_id
                prompt = self.autolabel_prompt
                confidence = self.autolabel_confidence
                
                # Get user context - MUST be inside async with self
                from app_state import AuthState
                auth_state = await self.get_state(AuthState)
                user_id = auth_state.user.get("id") if auth_state.user else None
                
                if not user_id:
                    self.autolabel_error = "User not authenticated"
                    self.is_autolabeling = False
                    return
                
                self.autolabel_logs += f"Processing dataset: {dataset_id}\n"
            
            yield
            
            # Get all videos in the current dataset
            all_videos = get_dataset_videos(dataset_id)
            
            # Filter to only selected videos if any are selected
            if selected_video_ids:
                all_videos = [v for v in all_videos if v["id"] in selected_video_ids]
            
            async with self:
                self.autolabel_logs += f"Found {len(all_videos)} videos to process\n"
            
            yield
            
            # Process each video to find target keyframes
            mask_only_mode = generate_masks and not generate_bboxes
            total_target_count = 0
            existing_annotations = {}  # kf_id -> annotations list (for fast path)
            
            for video in all_videos:
                video_id = video["id"]
                video_r2_path = video.get("r2_path", "")
                video_fps = video.get("fps", 30.0)
                
                # Get all keyframes for this video
                all_keyframes = get_video_keyframes(video_id)
                
                # Filter keyframes based on mode
                if mask_only_mode:
                    # Fast path: target keyframes WITH annotations (to add masks from bboxes)
                    target_keyframes = [
                        kf for kf in all_keyframes 
                        if kf.get("annotation_count", 0) > 0
                    ]
                    filter_label = "annotated"
                else:
                    # Standard: target keyframes WITHOUT annotations
                    target_keyframes = [
                        kf for kf in all_keyframes 
                        if kf.get("annotation_count", 0) == 0
                    ]
                    filter_label = "unlabeled"
                
                if not target_keyframes:
                    async with self:
                        self.autolabel_logs += f"Video {video.get('filename', video_id)}: No {filter_label} keyframes\n"
                    yield
                    continue
                
                async with self:
                    self.autolabel_logs += f"Video {video.get('filename', video_id)}: {len(target_keyframes)} {filter_label} keyframes\n"
                
                yield
                
                # For mask-only fast path, load existing annotations from DB
                if mask_only_mode:
                    from backend.supabase_client import get_keyframe_annotations
                    for kf in target_keyframes:
                        kf_id = kf["id"]
                        db_anns = get_keyframe_annotations(kf_id)
                        if db_anns:
                            existing_annotations[kf_id] = db_anns
                        else:
                            async with self:
                                self.autolabel_logs += f"  ⚠️ No DB annotations for keyframe {kf.get('frame_number', '?')}, skipping\n"
                            yield
                    # Filter out keyframes where we couldn't load annotations
                    target_keyframes = [kf for kf in target_keyframes if kf["id"] in existing_annotations]
                
                # Process each target keyframe
                for kf in target_keyframes:
                    kf_id = kf["id"]
                    kf_frame_number = kf["frame_number"]
                    
                    # Check if we have a full-resolution frame
                    full_image_path = kf.get("full_image_path")
                    
                    if not full_image_path and video_r2_path:
                        # Extract full-res frame on demand (for SAM3/YOLO inference quality)
                        async with self:
                            self.autolabel_logs += f"  Creating large frame for f{kf_frame_number}...\n"
                        
                        yield
                        
                        try:
                            full_image_path = extract_and_store_full_frame(
                                video_r2_path=video_r2_path,
                                frame_number=kf_frame_number,
                                fps=video_fps,
                                dataset_id=dataset_id,
                                video_id=video_id
                            )
                            if full_image_path:
                                # Save to DB for future use
                                update_keyframe(kf_id, full_image_path=full_image_path)
                                async with self:
                                    self.autolabel_logs += f"  ✓ Created: {full_image_path}\n"
                                yield
                        except Exception as e:
                            async with self:
                                self.autolabel_logs += f"  ⚠️ Frame extraction failed for f{kf_frame_number}: {e}\n"
                            yield
                            # Continue with thumbnail fallback
                    
                    # Use full-res if available, fall back to thumbnail
                    image_path = full_image_path or f"datasets/{dataset_id}/keyframes/{video_id}_f{kf_frame_number}.jpg"
                    
                    try:
                        presigned_url = r2.generate_presigned_url(image_path, expires_in=3600)
                        keyframe_urls[kf_id] = presigned_url
                        
                        # Build metadata for this keyframe
                        keyframe_meta[kf_id] = {
                            "video_id": video_id,
                            "frame_number": kf_frame_number,
                            "dataset_id": dataset_id
                        }
                        total_target_count += 1
                    except Exception as e:
                        async with self:
                            self.autolabel_logs += f"  ⚠️ URL generation failed for f{kf_frame_number}: {e}\n"
                        yield
            
            async with self:
                self.autolabel_logs += f"\nTotal keyframes to process: {total_target_count}\n"
            
            yield
            
            if not keyframe_urls:
                async with self:
                    self.autolabel_error = "No eligible keyframes found to process"
                    self.is_autolabeling = False
                msg = "All keyframes already have masks" if mask_only_mode else "All keyframes are already labeled"
                yield rx.toast.info(msg)
                return
            
            # Create job record in Supabase
            async with self:
                job_data = create_autolabel_job(
                    dataset_id=dataset_id,
                    user_id=user_id,
                    prompt_type="text" if autolabel_mode != "yolo" else "yolo",
                    prompt_value=prompt if autolabel_mode != "yolo" else f"YOLO model: {selected_model_id}",
                    target_count=len(keyframe_urls),
                    class_id=0,  # Will be auto-assigned based on prompt
                    confidence=confidence,
                )
                
                if not job_data:
                    self.autolabel_error = "Failed to create job record"
                    self.is_autolabeling = False
                    return
                
                job_id = job_data["id"]
                self.autolabel_job_id = job_id
                self.autolabel_logs += f"Job ID: {job_id}\n"
                self.autolabel_logs += "Sending to Modal GPU...\n"
            
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
                        image_urls=keyframe_urls,
                        prompt_type="yolo",
                        confidence=confidence,
                        video_mode=True,
                        keyframe_meta=keyframe_meta,
                        model_id=selected_model_id,
                        target=target,
                        user_id=user_id,
                        machine_name=machine_name,
                    )
                    
                    async with self:
                        self.autolabel_logs += f"Job dispatched successfully\n"
                        self.autolabel_logs += f"Processing {len(keyframe_urls)} keyframes with YOLO model\n"
                else:
                    # SAM3 mode: Use text prompt with class mappings
                    dispatch_autolabel_job(
                        dataset_id=dataset_id,
                        job_id=job_id,
                        image_urls=keyframe_urls,
                        prompt_type="text",
                        prompt_value=prompt,
                        class_id=0,
                        confidence=confidence,
                        video_mode=True,
                        keyframe_meta=keyframe_meta,
                        prompt_class_map=prompt_class_map,
                        target=target,
                        user_id=user_id,
                        machine_name=machine_name,
                        generate_bboxes=generate_bboxes,
                        generate_masks=generate_masks,
                        existing_annotations=existing_annotations if mask_only_mode else None,
                    )
                    
                    async with self:
                        self.autolabel_logs += f"Job dispatched successfully\n"
                        self.autolabel_logs += f"Processing {len(keyframe_urls)} keyframes with prompt: {prompt}\n"
                        self.autolabel_logs += f"Prompt-class map: {prompt_class_map}\n"
                
            except Exception as e:
                async with self:
                    self.autolabel_error = f"Dispatch error: {str(e)}"
                    self.autolabel_logs += f"\nError: {str(e)}\n"
                    self.is_autolabeling = False
                return
            
            yield
            
            # Start polling for status
            yield VideoLabelingState.poll_autolabel_status()
            
        except Exception as e:
            async with self:
                self.autolabel_error = f"Error: {str(e)}"
                self.autolabel_logs += f"\nError: {str(e)}\n"
                self.is_autolabeling = False

    
    @rx.event(background=True)
    async def poll_autolabel_status(self):
        """Poll for auto-labeling job status updates."""
        import asyncio
        from backend.supabase_client import get_autolabel_job
        
        async with self:
            if self.is_polling_autolabel:
                return  # Already polling
            self.is_polling_autolabel = True
        
        try:
            while True:
                await asyncio.sleep(2)  # Poll every 2 seconds
                
                async with self:
                    job_id = self.autolabel_job_id
                    if not job_id:
                        break
                
                # Fetch job status
                job = get_autolabel_job(job_id)
                if not job:
                    async with self:
                        self.autolabel_error = "Job not found"
                        self.is_autolabeling = False
                    break
                
                # Update logs
                async with self:
                    if job.get("logs"):
                        self.autolabel_logs = job["logs"]
                
                yield
                
                status = job.get("status", "")
                if status in ["completed", "failed"]:
                    async with self:
                        self.is_autolabeling = False
                        
                        if status == "completed":
                            # Success
                            self.autolabel_logs += "\n\nCompleted successfully!"
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
                            
                            # Clear cache and reload annotations from Supabase (no page refresh needed)
                            async with self:
                                self._clear_annotation_cache()
                                self.show_autolabel_modal = False
                                
                                # Reload keyframes and annotations (sync method within async with self)
                                self._load_keyframes_and_annotations_sync()
                                
                                # Re-select current keyframe to refresh the canvas
                                if self.selected_keyframe_idx >= 0 and self.selected_keyframe_idx < len(self.keyframes):
                                    current_kf = self.keyframes[self.selected_keyframe_idx]
                                    if current_kf.id in self.annotation_cache:
                                        self.annotations = self.annotation_cache[current_kf.id].copy()
                                        print(f"[AutoLabel] Refreshed view with {len(self.annotations)} annotations")
                                
                                # Refresh ALL video thumbnails from database (not just current video)
                                self._refresh_all_video_label_counts()
                            
                            # Push annotations to JS canvas
                            yield self.push_annotations_to_js()
                        else:
                            yield rx.toast.info("Auto-labeling completed: No detections found")
                    else:
                        yield rx.toast.error("Auto-labeling failed")
                    
                    break
                
        finally:
            async with self:
                self.is_polling_autolabel = False
    
    def cancel_autolabel(self):
        """Cancel active auto-labeling (stop polling, UI reset)."""
        print("[AutoLabel] Cancelling auto-label job")
        self.is_autolabeling = False
        self.is_polling_autolabel = False
        self.autolabel_error = "Cancelled by user"
        # Note: Cannot stop Modal job once started, only stops frontend polling
