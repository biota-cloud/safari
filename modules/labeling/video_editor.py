"""Video Labeling Editor Page — Video-based annotation interface.

Route: /projects/[project_id]/datasets/[dataset_id]/video-label
Layout: 3-panel (keyframes | video+canvas | tools)
"""

import reflex as rx
import styles
from app_state import require_auth
from modules.labeling.video_state import VideoLabelingState, VideoModel, KeyframeModel
from components.context_menu import annotation_context_menu
from components.compute_target_toggle import compute_target_toggle


# =============================================================================
# LEFT SIDEBAR — Video and Keyframe Lists
# =============================================================================

def video_thumbnail_item(video: VideoModel, idx: int) -> rx.Component:
    """Single video thumbnail in the sidebar list."""
    return rx.box(
        rx.hstack(
        # Thumbnail image (fixed size)
        rx.box(
            rx.cond(
                video.thumbnail_url != "",
                rx.image(
                    src=video.thumbnail_url,
                    width="64px",
                    height="64px",
                    object_fit="cover",
                    loading="lazy",
                    border_radius=styles.RADIUS_SM,
                ),
                # Fallback placeholder
                rx.center(
                    rx.icon("video", size=20, color=styles.TEXT_SECONDARY),
                    width="64px",
                    height="64px",
                    background=styles.BG_TERTIARY,
                    border_radius=styles.RADIUS_SM,
                ),
            ),
            # Duration Overlay
            rx.box(
                rx.text(
                    f"{video.duration_seconds:.1f}s",
                    size="1",
                    weight="medium",
                    color="white",
                    style={"font_size": "10px", "line_height": "1"},
                ),
                position="absolute",
                bottom="4px",
                right="4px",
                padding="2px 4px",
                background="rgba(0, 0, 0, 0.75)",
                border_radius="4px",
                backdrop_filter="blur(2px)",
            ),
            flex_shrink="0",
            position="relative",
        ),
        # Video info
        rx.vstack(
            # Filename (truncated with ellipsis, tooltip shows full name)
            rx.tooltip(
                rx.text(
                    video.filename,
                    size="1",
                    weight="medium",
                    style={
                        "color": styles.TEXT_PRIMARY,
                        "white_space": "nowrap",
                        "overflow": "hidden",
                        "text_overflow": "ellipsis",
                        "max_width": "120px",
                    },
                ),
                content=video.filename,
            ),
            # Frame count
            rx.text(
                f"{video.frame_count} frames",
                size="1",
                style={"color": styles.TEXT_SECONDARY},
            ),
            # Label count badge
            rx.cond(
                video.label_count > 0,
                rx.badge(
                    f"{video.label_count} labels",
                    color_scheme="green",
                    variant="outline",
                    size="1",
                ),
                rx.fragment(),
            ),
            spacing="1",
            align_items="flex-start",
            flex="1",
            overflow="hidden",
        ),
            spacing="2",
            align="center",
            width="100%",
            padding="6px",
        ),
        # Delete button overlay (top-right of container)
        rx.box(
            rx.icon_button(
                rx.icon("trash-2", size=12),
                size="1",
                variant="ghost",
                color_scheme="red",
                on_click=lambda: VideoLabelingState.request_delete_video(video.id),
                style={
                    "opacity": "0",
                    "transition": styles.TRANSITION_FAST,
                }
            ),
            position="absolute",
            top="4px",
            right="4px",
            class_name="video-delete-btn",
        ),
        position="relative",
        width="100%",
        border_radius=styles.RADIUS_SM,
        border=rx.cond(
            VideoLabelingState.current_video_idx == idx,
            f"2px solid {styles.ACCENT}",
            f"1px solid {styles.BORDER}",
        ),
        background=rx.cond(
            VideoLabelingState.current_video_idx == idx,
            styles.BG_TERTIARY,
            "transparent",
        ),
        cursor="pointer",
        on_click=lambda: VideoLabelingState.select_video(idx),
        _hover={
            "border_color": styles.ACCENT,
            "background": styles.BG_TERTIARY,
            "& .video-delete-btn button": {
                "opacity": "1",
            }
        },
        transition=styles.TRANSITION_FAST,
        id=f"vid-thumb-{video.id}",
)



def left_sidebar() -> rx.Component:
    """Left sidebar with video list (no keyframes tab - keyframes managed via timeline)."""
    
    return rx.box(
        rx.vstack(
            # Header with videos count
            rx.hstack(
                rx.text(
                    "Videos",
                    size="2",
                    weight="medium",
                    style={"color": styles.TEXT_PRIMARY}
                ),
                rx.icon_button(
                    rx.icon("bar-chart-2", size=14),
                    size="1",
                    variant="ghost",
                    on_click=VideoLabelingState.open_empty_stats_modal,
                    title="View video keyframe statistics",
                ),
                rx.spacer(),
                rx.text(
                    f"{VideoLabelingState.current_video_index}/{VideoLabelingState.video_count}",
                    size="1",
                    style={"color": styles.TEXT_SECONDARY}
                ),
                width="100%",
                align="center",
            ),
            # Keyframe count indicator for current video
            rx.cond(
                VideoLabelingState.has_keyframes,
                rx.hstack(
                    rx.icon("bookmark", size=12, color=styles.ACCENT),
                    rx.text(
                        f"{VideoLabelingState.keyframe_count} keyframes",
                        size="1",
                        style={"color": styles.ACCENT}
                    ),
                    rx.text(
                        f" ({VideoLabelingState.labeled_keyframe_count} labeled)",
                        size="1",
                        style={"color": styles.TEXT_SECONDARY}
                    ),
                    spacing="1",
                    align="center",
                ),
                rx.text(
                    "Press K to mark keyframes",
                    size="1",
                    style={"color": styles.TEXT_SECONDARY, "font_style": "italic"}
                ),
            ),
            rx.divider(style={"border_color": styles.BORDER}),
            # Scrollable video list
            rx.scroll_area(
                rx.vstack(
                    rx.foreach(
                        VideoLabelingState.videos,
                        video_thumbnail_item,
                    ),
                    spacing="2",
                    width="100%",
                ),
                type="auto",
                style={"flex": "1", "width": "100%", "min_height": "0"},
            ),
            spacing="3",
            height="100%",
            width="100%",
            padding=styles.SPACING_2,
        ),
        width="230px",
        min_width="230px",
        height="100%",
        background=styles.BG_SECONDARY,
        border_right=f"1px solid {styles.BORDER}",
    )


# =============================================================================
# CENTER — Video Player & Canvas
# =============================================================================

def video_controls() -> rx.Component:
    """Video playback controls below the canvas."""
    
    def keyframe_marker(kf_data: dict) -> rx.Component:
        """Single keyframe marker on the timeline."""
        return rx.box(
            position="absolute",
            left=f"{kf_data['percent']}%",
            top="0",
            width="4px",
            height="10px",
            background=rx.cond(
                kf_data["has_labels"],
                styles.ACCENT,  # Blue for keyframes with labels
                styles.TEXT_SECONDARY,  # Gray for empty keyframes
            ),
            border_radius="2px",
            transform="translateX(-50%)",
            cursor="pointer",
            on_click=lambda: VideoLabelingState.seek_to_frame(kf_data["frame"]),
            _hover={"transform": "translateX(-50%) scaleY(1.3)"},
            transition="transform 0.1s",
        )
    
    def interval_overlay(interval_data: dict) -> rx.Component:
        """Interval selection overlay on the timeline."""
        return rx.box(
            position="absolute",
            left=f"{interval_data['start_percent']}%",
            width=f"{interval_data['width_percent']}%",
            top="-12px",
            height="10px",
            background=f"{styles.ACCENT}4D",  # Green with transparency
            border=f"1px solid {styles.ACCENT}99",
            border_radius="2px",
            pointer_events="none",  # Don't interfere with slider interaction
        )

    return rx.vstack(
        # Timeline with keyframe markers and interval overlay
        rx.box(
            # Interval selection overlay - show as soon as start is set
            rx.cond(
                VideoLabelingState.interval_start_frame >= 0,
                rx.foreach(
                    VideoLabelingState.interval_positions,
                    interval_overlay,
                ),
                rx.fragment(),
            ),
            # Keyframe markers track - padded to align with slider thumb positions
            rx.box(
                rx.foreach(
                    VideoLabelingState.keyframe_positions,
                    keyframe_marker,
                ),
                position="absolute",
                top="-12px",
                left="6px",    # Account for slider thumb (half of thumb width)
                right="6px",   # Account for slider thumb (half of thumb width)
                height="10px",
            ),
            # Timeline slider
            rx.slider(
                value=[VideoLabelingState.current_frame],
                min=0,
                max=rx.cond(
                    VideoLabelingState.total_frames > 0,
                    VideoLabelingState.total_frames - 1,
                    100
                ),
                step=1,
                on_value_commit=VideoLabelingState.handle_slider_change,
                width="100%",
                size="1",
            ),
            position="relative",
            width="100%",
            padding_top="14px",  # Space for markers
            id="video-timeline-slider",
        ),
        # Control buttons
        rx.hstack(
            # Frame step buttons
            rx.hstack(
                rx.icon_button(
                    rx.icon("chevrons-left", size=14),
                    size="1",
                    variant="outline",
                    on_click=lambda: VideoLabelingState.step_frame(-10),
                    title="Back 10 frames (Shift+Z)",
                    id="btn-step-back-10",
                ),
                rx.icon_button(
                    rx.icon("chevron-left", size=14),
                    size="1",
                    variant="outline",
                    on_click=lambda: VideoLabelingState.step_frame(-1),
                    title="Previous frame (Z)",
                    id="btn-step-back-1",
                ),
                rx.icon_button(
                    rx.cond(
                        VideoLabelingState.is_playing,
                        rx.icon("pause", size=16),
                        rx.icon("play", size=16),
                    ),
                    size="2",
                    variant="solid",
                    color_scheme="green",
                    on_click=VideoLabelingState.toggle_playback,
                    title="Play/Pause (Space)",
                    id="btn-play-pause",
                ),
                rx.icon_button(
                    rx.icon("chevron-right", size=14),
                    size="1",
                    variant="outline",
                    on_click=lambda: VideoLabelingState.step_frame(1),
                    title="Next frame (C)",
                    id="btn-step-fwd-1",
                ),
                rx.icon_button(
                    rx.icon("chevrons-right", size=14),
                    size="1",
                    variant="outline",
                    on_click=lambda: VideoLabelingState.step_frame(10),
                    title="Forward 10 frames (Shift+C)",
                    id="btn-step-fwd-10",
                ),
                spacing="1",
                align="center",
            ),
            rx.spacer(),
            # Frame info
            rx.text(
                VideoLabelingState.frame_display,
                size="1",
                style={
                    "color": styles.TEXT_SECONDARY,
                    "font_family": "monospace",
                },
            ),
            rx.spacer(),
            rx.hstack(
                rx.button(
                    rx.icon("bookmark", size=14),
                    "Mark Keyframe (K)",
                    size="1",
                    variant="outline",
                    on_click=VideoLabelingState.mark_keyframe,
                    title="Mark current frame for labeling",
                ),
                spacing="2",
            ),
            width="100%",
            align="center",
        ),
        spacing="2",
        width="100%",
        padding=styles.SPACING_3,
        border_top=f"1px solid {styles.BORDER}",
    )


def keyframe_panel() -> rx.Component:
    """Permanent keyframe management panel below timeline with integrated interval creation."""
    
    def keyframe_row(kf: KeyframeModel, idx: int) -> rx.Component:
        """Single keyframe row with selection support."""
        is_selected = VideoLabelingState.selected_keyframe_ids.contains(kf.id)
        is_current = VideoLabelingState.selected_keyframe_idx == idx
        
        return rx.hstack(
            # Checkbox for selection - wrapped to stop propagation
            rx.box(
                rx.checkbox(
                    checked=is_selected,
                    on_change=lambda _: VideoLabelingState.toggle_keyframe_selection_by_id(kf.id),
                    size="1",
                ),
                on_click=rx.stop_propagation,
            ),
            # Frame info
            rx.text(
                f"Frame {kf.frame_number}",
                size="1",
                weight=rx.cond(is_current, "medium", "regular"),
                style={"color": rx.cond(is_current, styles.TEXT_PRIMARY, styles.TEXT_SECONDARY)},
            ),
            rx.spacer(),
            # Label count
            rx.cond(
                kf.annotation_count > 0,
                rx.badge(
                    f"{kf.annotation_count} labels",
                    color_scheme="green",
                    size="1",
                ),
                rx.badge(
                    "empty",
                    color_scheme="gray",
                    size="1",
                    variant="outline",
                ),
            ),
            # Jump to button
            rx.icon_button(
                rx.icon("play", size=12),
                size="1",
                variant="ghost",
                on_click=lambda: VideoLabelingState.select_keyframe(idx),
                title="Go to keyframe",
            ),
            spacing="2",
            align="center",
            width="100%",
            padding="4px 8px",
            border_radius=styles.RADIUS_SM,
            background=rx.cond(
                is_current,
                f"{styles.ACCENT}20",
                rx.cond(is_selected, f"{styles.SUCCESS}15", "transparent"),
            ),
            cursor="pointer",
            on_click=lambda: VideoLabelingState.handle_keyframe_row_click(kf.id, idx),
            custom_attrs={
                "data-keyframe-id": kf.id,
                "data-keyframe-idx": idx,
            },
            _hover={"background": styles.BG_TERTIARY},
        )
    
    # Wrap in fixed-height container
    return rx.box(
        # Hidden button for shift+click trigger - always rendered
        rx.el.button(
            id="shift-click-keyframe-trigger",
            on_click=rx.call_script(
                "window._shiftClickKeyframeData || '{}'",
                callback=VideoLabelingState.handle_shift_click_from_js,
            ),
            style={"display": "none"},
        ),
        # Script to intercept shift+clicks on keyframe rows - always rendered
        rx.script("""
            (function() {
                document.addEventListener('click', function(e) {
                    if (!e.shiftKey) return;
                    
                    // Find if click was on a keyframe row
                    let target = e.target;
                    while (target && target !== document) {
                        if (target.dataset && target.dataset.keyframeId) {
                            e.preventDefault();
                            e.stopPropagation();
                            
                            window._shiftClickKeyframeData = JSON.stringify({
                                keyframe_id: target.dataset.keyframeId,
                                idx: parseInt(target.dataset.keyframeIdx, 10)
                            });
                            
                            document.getElementById('shift-click-keyframe-trigger')?.click();
                            return;
                        }
                        target = target.parentElement;
                    }
                }, true);
            })();
        """),
        # Always visible content
        rx.vstack(
            # Header row with title and interval creation tools
            rx.hstack(
                # Left: Title with count
                rx.hstack(
                    rx.icon("bookmark", size=14, color=styles.ACCENT),
                    rx.text(
                        f"Keyframes ({VideoLabelingState.keyframe_count})",
                        size="1",
                        weight="medium",
                        style={"color": styles.TEXT_PRIMARY},
                    ),
                    spacing="1",
                    align="center",
                ),
                # Divider
                rx.box(
                    width="1px",
                    height="16px",
                    background=styles.BORDER,
                    margin_x="8px",
                ),
                # Center: Compact interval creation controls
                rx.hstack(
                    rx.text("Every", size="1", style={"color": styles.TEXT_SECONDARY}),
                    rx.input(
                        type="number",
                        value=VideoLabelingState.interval_step,
                        on_change=VideoLabelingState.set_interval_step,
                        on_key_down=VideoLabelingState.handle_interval_keydown,
                        min="1",
                        size="1",
                        style={"width": "50px", "text_align": "center"},
                    ),
                    rx.text("frames:", size="1", style={"color": styles.TEXT_SECONDARY}),
                    rx.icon_button(
                        rx.icon("play", size=12),
                        size="1",
                        variant=rx.cond(
                            VideoLabelingState.interval_start_frame >= 0,
                            "solid",
                            "outline"
                        ),
                        color_scheme=rx.cond(
                            VideoLabelingState.interval_start_frame >= 0,
                            "blue",
                            "gray"
                        ),
                        on_click=VideoLabelingState.set_interval_start,
                        title="Set start frame (I)",
                    ),
                    rx.icon_button(
                        rx.icon("square", size=12),
                        size="1",
                        variant=rx.cond(
                            VideoLabelingState.interval_end_frame >= 0,
                            "solid",
                            "outline"
                        ),
                        color_scheme=rx.cond(
                            VideoLabelingState.interval_end_frame >= 0,
                            "blue",
                            "gray"
                        ),
                        on_click=VideoLabelingState.set_interval_end,
                        title="Set end frame (O)",
                    ),
                    # Compact interval info
                    rx.cond(
                        VideoLabelingState.has_interval_selection,
                        rx.hstack(
                            rx.badge(
                                f"+{VideoLabelingState.interval_keyframe_count}",
                                color_scheme="green",
                                size="1",
                            ),
                            rx.icon_button(
                                rx.icon("zap", size=12),
                                size="1",
                                variant="solid",
                                color_scheme="green",
                                on_click=VideoLabelingState.create_interval_keyframes,
                                title="Create keyframes (P)",
                            ),
                            rx.icon_button(
                                rx.icon("x", size=10),
                                size="1",
                                variant="ghost",
                                on_click=VideoLabelingState.clear_interval,
                                title="Clear interval",
                            ),
                            spacing="1",
                            align="center",
                        ),
                        rx.fragment(),
                    ),
                    spacing="1",
                    align="center",
                ),
                rx.spacer(),
                # Right: Selection actions
                rx.cond(
                    VideoLabelingState.has_keyframe_selection,
                    rx.hstack(
                        rx.badge(
                            f"{VideoLabelingState.selected_keyframe_count} selected",
                            color_scheme="green",
                            size="1",
                        ),
                        rx.icon_button(
                            rx.icon("x", size=12),
                            size="1",
                            variant="ghost",
                            on_click=VideoLabelingState.clear_keyframe_selection,
                            title="Clear selection",
                        ),
                        rx.icon_button(
                            rx.icon("trash-2", size=14),
                            size="1",
                            variant="outline",
                            color_scheme="red",
                            on_click=VideoLabelingState.open_bulk_delete_keyframes_modal,
                            title="Delete selected keyframes",
                        ),
                        spacing="1",
                        align="center",
                    ),
                    rx.button(
                        "Select All",
                        size="1",
                        variant="ghost",
                        on_click=VideoLabelingState.select_all_keyframes,
                    ),
                ),
                width="100%",
                align="center",
                padding="6px 8px",
            ),
            # Scrollable keyframe list
            rx.scroll_area(
                rx.vstack(
                    rx.foreach(
                        VideoLabelingState.keyframes,
                        keyframe_row,
                    ),
                    spacing="1",
                    width="100%",
                ),
                type="auto",
                style={"flex": "1", "width": "100%"},
            ),
            spacing="1",
            width="100%",
            height="100%",
            background=styles.BG_SECONDARY,
            border_top=f"1px solid {styles.BORDER}",
        ),
        width="100%",
        height="220px",  # Slightly taller to accommodate new header
        flex_shrink="0",
    )


def zoom_controls() -> rx.Component:
    """Floating zoom controls overlay."""
    return rx.hstack(
        rx.icon_button(
            rx.icon("minus", size=14),
            variant="outline",
            size="1",
            on_click=VideoLabelingState.zoom_out,
            style={"cursor": "pointer"},
        ),
        rx.el.span(
            "100%",  # Initial value, updated by JS
            id="zoom-percentage",
            style={
                "font_size": "12px",
                "font_weight": "500",
                "color": styles.TEXT_PRIMARY,
                "min_width": "42px",
                "text_align": "center",
                "display": "inline-block",
            }
        ),
        rx.icon_button(
            rx.icon("plus", size=14),
            variant="outline",
            size="1",
            on_click=VideoLabelingState.zoom_in,
            style={"cursor": "pointer"},
        ),
        rx.icon_button(
            rx.icon("maximize-2", size=14),
            variant="outline",
            size="1",
            on_click=VideoLabelingState.reset_view,
            style={"cursor": "pointer"},
            title="Reset View",
        ),
        spacing="1",
        padding=styles.SPACING_2,
        background=styles.BG_SECONDARY,
        border_radius=styles.RADIUS_SM,
        border=f"1px solid {styles.BORDER}",
        style={
            "position": "absolute",
            "bottom": styles.SPACING_4,
            "right": styles.SPACING_4,
            "z_index": "100",
            "box_shadow": styles.SHADOW_MD,
        }
    )


def canvas_container() -> rx.Component:
    """Center panel with video player and annotation canvas."""
    return rx.box(
        # Header with video info
        rx.hstack(
            # Navigation breadcrumb: Home > Back to Dataset
            rx.hstack(
                rx.icon_button(
                    rx.icon("home", size=18),
                    variant="ghost",
                    size="2",
                    on_click=rx.redirect("/dashboard"),
                    title="Go to Dashboard",
                    style={
                        "color": styles.TEXT_SECONDARY,
                        "&:hover": {"background": styles.BG_TERTIARY},
                    }
                ),
                rx.text("/", size="1", style={"color": styles.BORDER, "margin_x": "2px"}),
                rx.icon_button(
                    rx.icon("arrow-left", size=18),
                    variant="ghost",
                    size="2",
                    on_click=VideoLabelingState.navigate_back,
                    title="Back to Dataset",
                    style={
                        "color": styles.TEXT_SECONDARY,
                        "&:hover": {"background": styles.BG_TERTIARY},
                    }
                ),
                spacing="0",
                align="center",
            ),
            rx.text(
                VideoLabelingState.dataset_name,
                size="3",
                weight="medium",
                style={"color": styles.TEXT_PRIMARY}
            ),
            rx.text(
                " — ",
                size="2",
                style={"color": styles.TEXT_SECONDARY}
            ),
            rx.text(
                VideoLabelingState.video_filename,
                size="2",
                style={"color": styles.TEXT_SECONDARY}
            ),
            rx.spacer(),
            # Save status indicator
            rx.cond(
                VideoLabelingState.save_status == "saving",
                rx.hstack(
                    rx.spinner(size="1"),
                    rx.text("Saving...", size="1", style={"color": styles.TEXT_SECONDARY}),
                    spacing="1",
                    align="center",
                ),
                rx.cond(
                    VideoLabelingState.save_status == "saved",
                    rx.hstack(
                        rx.icon("check", size=12, color=styles.SUCCESS),
                        rx.text("Saved", size="1", style={"color": styles.SUCCESS}),
                        spacing="1",
                        align="center",
                    ),
                    rx.fragment(),
                ),
            ),
            # Keyframe indicator
            rx.cond(
                VideoLabelingState.has_selected_keyframe,
                rx.badge("Editing Keyframe", color_scheme="green", size="1"),
                rx.badge("Live Preview", color_scheme="gray", size="1"),
            ),
            # Focus mode toggle button
            rx.icon_button(
                rx.cond(
                    VideoLabelingState.focus_mode,
                    rx.icon("eye", size=16),
                    rx.icon("eye-off", size=16),
                ),
                size="1",
                variant="ghost",
                on_click=VideoLabelingState.toggle_focus_mode,
                title=rx.cond(
                    VideoLabelingState.focus_mode,
                    "Exit Focus Mode (M)",
                    "Focus Mode (M)"
                ),
                style={
                    "color": rx.cond(
                        VideoLabelingState.focus_mode,
                        styles.ACCENT,
                        styles.TEXT_SECONDARY
                    ),
                },
            ),
            # Fullscreen toggle button
            rx.icon_button(
                rx.cond(
                    VideoLabelingState.is_fullscreen,
                    rx.icon("minimize", size=16),
                    rx.icon("maximize", size=16),
                ),
                size="1",
                variant="ghost",
                on_click=rx.call_script("window.toggleFullscreen && window.toggleFullscreen()"),
                title=rx.cond(
                    VideoLabelingState.is_fullscreen,
                    "Exit Fullscreen (F)",
                    "Fullscreen (F)"
                ),
                style={
                    "color": rx.cond(
                        VideoLabelingState.is_fullscreen,
                        styles.ACCENT,
                        styles.TEXT_SECONDARY
                    ),
                },
            ),
            width="100%",
            align="center",
            padding=styles.SPACING_3,
            border_bottom=f"1px solid {styles.BORDER}",
        ),
        # Video Loading Overlay
        rx.cond(
            VideoLabelingState.is_video_loading,
            rx.center(
                rx.vstack(
                    rx.spinner(size="3", color="white"),
                    rx.text(
                        "Loading video...",
                        size="2",
                        weight="medium",
                        color="white",
                    ),
                    spacing="3",
                    align="center",
                    padding="20px",
                    background="rgba(0, 0, 0, 0.7)",
                    border_radius="8px",
                    backdrop_filter="blur(4px)",
                ),
                position="absolute",
                top="48px", # Below header
                left="0",
                right="0",
                bottom="0",
                z_index="100",
                background="rgba(0, 0, 0, 0.3)",
            ),
            rx.fragment(),
        ),
        # Canvas area
        rx.box(
            # Hidden video element (source for frames)
            rx.el.video(
                id="source-video",
                # src is set by JS via loadVideo()
                style={
                    "position": "absolute",
                    "opacity": "0",
                    "pointer_events": "none",
                    "width": "1px",
                    "height": "1px",
                },
                preload="auto",
                muted=True,
                playsinline=True,
            ),
            # The HTML5 canvas element
            rx.el.canvas(
                id="labeling-canvas",
                style={
                    "width": "100%",
                    "height": "100%",
                    "display": "block",
                }
            ),
            # Zoom controls overlay (Bottom-Right)
            zoom_controls(),
            # Hidden inputs for JS→Python communication
            _hidden_inputs(),
            id="canvas-container",
            flex="1",
            width="100%",
            min_height="0",
            position="relative",
            overflow="hidden",
        ),
        # Bottom controls (Video controls + Keyframe panel)
        rx.box(
            video_controls(),
            keyframe_panel(),
            # Animate max-height for smooth transition (0 to ~300px)
            max_height=rx.cond(VideoLabelingState.focus_mode, "0px", "300px"),
            overflow="hidden",
            transition="max-height 0.3s ease-in-out",
            width="100%",
        ),
        display="flex",
        flex_direction="column",
        flex="1",
        height="100%",
        background=styles.BG_PRIMARY,
    )


def _hidden_inputs() -> rx.Component:
    """Hidden inputs for JS→Python communication."""
    hidden_style = {
        "position": "absolute",
        "opacity": "0",
        "height": "0",
        "width": "0",
        "pointer_events": "none",
        "z_index": "-1",
    }
    return rx.fragment(
        # New annotation
        rx.input(
            id="new-annotation-data",
            on_change=VideoLabelingState.handle_new_annotation,
            type="text",
            style=hidden_style,
        ),
        # Selection change
        rx.input(
            id="selected-annotation-id",
            on_change=VideoLabelingState.handle_selection_change,
            type="text",
            style=hidden_style,
        ),
        # Deletion
        rx.input(
            id="deleted-annotation-id",
            on_change=VideoLabelingState.handle_annotation_deleted,
            type="text",
            style=hidden_style,
        ),
        # Annotation update (resize/move)
        rx.input(
            id="updated-annotation-data",
            on_change=VideoLabelingState.handle_annotation_updated,
            type="text",
            style=hidden_style,
        ),
        # Frame update from video playback
        rx.input(
            id="frame-update-data",
            on_change=VideoLabelingState.handle_frame_update,
            type="text",
            style=hidden_style,
        ),
        # Keyframe captured callback
        rx.input(
            id="keyframe-captured-data",
            on_change=VideoLabelingState.handle_keyframe_captured,
            type="text",
            style=hidden_style,
        ),
        # Tool change (V/R keys)
        rx.input(
            id="tool-change-trigger",
            on_change=VideoLabelingState.set_tool,
            type="text",
            style=hidden_style,
        ),
        # Class select (1-9 keys)
        rx.input(
            id="class-select-trigger",
            on_change=VideoLabelingState.handle_class_select,
            type="text",
            style=hidden_style,
        ),
        # Help toggle (? key)
        rx.input(
            id="help-toggle-trigger",
            on_change=VideoLabelingState.toggle_shortcuts_help,
            type="text",
            style=hidden_style,
        ),
        # Keyframe marking from keyboard shortcut (K key)
        rx.input(
            id="keyframe-mark-trigger",
            on_change=VideoLabelingState.handle_keyframe_mark,
            type="text",
            style=hidden_style,
        ),
        # Interval start (I key)
        rx.input(
            id="interval-start-trigger",
            on_change=lambda _: VideoLabelingState.set_interval_start(),
            type="text",
            style=hidden_style,
        ),
        # Interval end (O key)
        rx.input(
            id="interval-end-trigger",
            on_change=lambda _: VideoLabelingState.set_interval_end(),
            type="text",
            style=hidden_style,
        ),
        # Create interval keyframes (P key)
        rx.input(
            id="interval-create-trigger",
            on_change=lambda _: VideoLabelingState.create_interval_keyframes(),
            type="text",
            style=hidden_style,
        ),
        # Previous keyframe (Q key)
        rx.input(
            id="prev-keyframe-trigger",
            on_change=lambda _: VideoLabelingState.navigate_to_previous_keyframe(),
            type="text",
            style=hidden_style,
        ),
        # Next keyframe (E key)
        rx.input(
            id="next-keyframe-trigger",
            on_change=lambda _: VideoLabelingState.navigate_to_next_keyframe(),
            type="text",
            style=hidden_style,
        ),
        # Video loading status (start/complete)
        rx.input(
            id="video-loading-trigger",
            on_change=VideoLabelingState.handle_video_loading,
            type="text",
            style=hidden_style,
        ),
        # Focus mode toggle (M key)
        rx.input(
            id="focus-mode-trigger",
            on_change=VideoLabelingState.toggle_focus_mode,
            type="text",
            style=hidden_style,
        ),
        # Hidden input for autolabel shortcut (L key)
        rx.input(
            id="autolabel-trigger",
            on_change=VideoLabelingState.open_autolabel_modal,
            type="text",
            style=hidden_style,
        ),
        # Fullscreen toggle (F key)
        rx.input(
            id="fullscreen-trigger",
            on_change=VideoLabelingState.toggle_fullscreen,
            type="text",
            style=hidden_style,
        ),
        # Fullscreen state sync (browser fullscreenchange event)
        rx.input(
            id="fullscreen-state-sync",
            on_change=VideoLabelingState.set_fullscreen_state,
            type="text",
            style=hidden_style,
        ),
        # Context menu trigger (right-click on annotation)
        rx.input(
            id="context-menu-trigger",
            on_change=VideoLabelingState.open_context_menu,
            type="text",
            style=hidden_style,
        ),
    )


# =============================================================================
# RIGHT SIDEBAR — Tools & Classes
# =============================================================================


def class_item(cls: str, idx: int) -> rx.Component:
    """Single class item (read-only, class management is in Project Detail)."""
    return rx.hstack(
        # Radio button
        rx.box(
            rx.cond(
                VideoLabelingState.current_class_id == idx,
                rx.icon("circle-dot", size=14, color=styles.ACCENT),
                rx.icon("circle", size=14, color=styles.TEXT_SECONDARY),
            ),
            cursor="pointer",
            on_click=VideoLabelingState.set_current_class(idx),
        ),
        # Color dot
        rx.box(
            width="10px",
            height="10px",
            border_radius="50%",
            background=f"hsl({(idx * 137) % 360}, 70%, 50%)",
        ),
        # Class name
        rx.text(
            cls,
            size="2",
            style={"color": styles.TEXT_PRIMARY, "flex": "1"},
        ),
        spacing="2",
        align="center",
        width="100%",
        padding="4px",
        border_radius=styles.RADIUS_SM,
        background=rx.cond(
            VideoLabelingState.current_class_id == idx,
            styles.BG_TERTIARY,
            "transparent",
        ),
        _hover={"background": styles.BG_TERTIARY},
    )



def annotation_item(ann: dict) -> rx.Component:
    """Single annotation item with edit/delete controls."""
    return rx.hstack(
        rx.text(
            ann["class_name"],
            size="2",
            style={"color": styles.TEXT_PRIMARY},
        ),
        rx.spacer(),
        rx.popover.root(
            rx.popover.trigger(
                rx.icon_button(
                    rx.icon("pencil", size=14),
                    size="1",
                    variant="ghost",
                    color_scheme="gray",
                    # Allow propagation so row is selected when editing
                )
            ),
            rx.popover.content(
                rx.vstack(
                    rx.text("Change Class", size="1", weight="bold"),
                    rx.scroll_area(
                        rx.vstack(
                            rx.foreach(
                                VideoLabelingState.project_classes,
                                lambda cls_name, idx: rx.button(
                                    cls_name,
                                    on_click=lambda: VideoLabelingState.update_annotation_class(ann["id"], idx),
                                    size="1",
                                    variant="ghost",
                                    width="100%",
                                    justify="start",
                                )
                            ),
                            width="100%",
                        ),
                        type="auto",
                        style={"min_height": "120px", "max_height": "200px"},
                    ),
                    spacing="2",
                ),
                width="200px",
            ),
        ),
        rx.icon_button(
            rx.icon("trash-2", size=14),
            size="1",
            variant="ghost",
            color_scheme="red",
            on_click=[rx.stop_propagation, VideoLabelingState.delete_annotation(ann["id"])],
        ),
        width="100%",
        align="center",
        padding="6px",
        border_radius=styles.RADIUS_SM,
        background=rx.cond(
            VideoLabelingState.selected_annotation_id == ann["id"],
            styles.BG_TERTIARY,
            "transparent",
        ),
        border=rx.cond(
            VideoLabelingState.selected_annotation_id == ann["id"],
            f"1px solid {styles.ACCENT}",
            f"1px solid {styles.BORDER}",
        ),
        cursor="pointer",
        on_click=lambda: VideoLabelingState.handle_selection_change(ann["id"]),
        _hover={"background": styles.BG_TERTIARY},
    )


def autolabel_modal() -> rx.Component:
    """Auto-labeling modal dialog with SAM3 and YOLO modes for video editor."""
    
    def video_checkbox(video: VideoModel) -> rx.Component:
        """Checkbox row for a video in the selection list."""
        return rx.hstack(
            rx.checkbox(
                checked=VideoLabelingState.selected_video_ids_for_autolabel.contains(video.id),
                on_change=lambda _: VideoLabelingState.toggle_video_for_autolabel(video.id),
                disabled=VideoLabelingState.is_autolabeling,
                size="1",
            ),
            rx.text(
                video.filename,
                size="1",
                style={"max_width": "150px", "overflow": "hidden", "text_overflow": "ellipsis"}
            ),
            rx.spacer(),
            rx.text(f"{video.keyframe_count} kf", size="1", style={"color": styles.TEXT_SECONDARY}),
            spacing="2",
            width="100%",
            padding="4px",
        )
    
    def sam3_panel() -> rx.Component:
        """SAM3 text prompt panel with video selection and prompt-to-class mapping."""
        
        def prompt_mapping_row(term: str, idx: int) -> rx.Component:
            """A single row for mapping a prompt term to a class."""
            return rx.hstack(
                rx.text(
                    f'"{term}"',
                    size="1",
                    style={"color": styles.TEXT_PRIMARY, "min_width": "80px"},
                ),
                rx.icon("arrow-right", size=12, color=styles.TEXT_SECONDARY),
                rx.select(
                    VideoLabelingState.project_classes,
                    placeholder="Select class...",
                    on_change=lambda val: VideoLabelingState.set_prompt_class_mapping(idx, val),
                    disabled=VideoLabelingState.is_autolabeling,
                    size="1",
                    style={"flex": "1"},
                ),
                spacing="2",
                align="center",
                width="100%",
            )
        
        return rx.vstack(
            # Generation options checkboxes (always visible — user picks mode first)
            rx.vstack(
                rx.text("Generation Options", size="1", weight="medium", style={"color": styles.TEXT_SECONDARY}),
                rx.hstack(
                    rx.checkbox(
                        "Generate bounding boxes",
                        checked=VideoLabelingState.autolabel_generate_bboxes,
                        on_change=VideoLabelingState.set_autolabel_generate_bboxes,
                        disabled=VideoLabelingState.is_autolabeling,
                        size="1",
                    ),
                    spacing="2",
                    width="100%",
                ),
                rx.hstack(
                    rx.checkbox(
                        "Generate masks",
                        checked=VideoLabelingState.autolabel_generate_masks,
                        on_change=VideoLabelingState.set_autolabel_generate_masks,
                        disabled=VideoLabelingState.is_autolabeling,
                        size="1",
                    ),
                    spacing="2",
                    width="100%",
                ),
                # Contextual info text for mask-only mode
                rx.cond(
                    VideoLabelingState.autolabel_mask_fast_path,
                    rx.text(
                        f"Masks will be generated from {VideoLabelingState.labeled_keyframe_count} keyframes with existing bounding boxes",
                        size="1",
                        style={"color": styles.SUCCESS, "font_style": "italic"},
                    ),
                    rx.cond(
                        VideoLabelingState.autolabel_generate_masks & ~VideoLabelingState.autolabel_generate_bboxes,
                        rx.text(
                            "Masks will be generated from text prompts on empty keyframes",
                            size="1",
                            style={"color": styles.ACCENT, "font_style": "italic"},
                        ),
                    ),
                ),
                # Validation: at least one must be selected
                rx.cond(
                    ~VideoLabelingState.autolabel_generate_bboxes & ~VideoLabelingState.autolabel_generate_masks,
                    rx.text(
                        "⚠ Select at least one generation option",
                        size="1",
                        style={"color": styles.EARTH_SIENNA, "font_style": "italic"},
                    ),
                ),
                spacing="2",
                width="100%",
                padding="8px",
                background=styles.BG_TERTIARY,
                border_radius=styles.RADIUS_SM,
            ),
            # Prompt + class mapping + confidence (hidden on fast path)
            rx.cond(
                ~VideoLabelingState.autolabel_mask_fast_path,
                rx.vstack(
                    # Prompt input
                    rx.input(
                        placeholder="e.g., 'elephant, fox, red car'",
                        value=VideoLabelingState.autolabel_prompt,
                        on_change=VideoLabelingState.set_autolabel_prompt,
                        on_blur=VideoLabelingState.save_autolabel_prompt_pref,
                        on_key_down=VideoLabelingState.handle_autolabel_keydown,
                        disabled=VideoLabelingState.is_autolabeling,
                        size="2",
                        width="100%",
                    ),
                    # Dynamic mapping section (shown when prompt has terms)
                    rx.cond(
                        VideoLabelingState.autolabel_prompt_terms.length() > 0,
                        rx.vstack(
                            rx.text(
                                "Map prompts to classes:",
                                size="1",
                                weight="medium",
                                style={"color": styles.TEXT_SECONDARY}
                            ),
                            rx.vstack(
                                rx.foreach(
                                    VideoLabelingState.autolabel_prompt_terms,
                                    prompt_mapping_row,
                                ),
                                spacing="2",
                                width="100%",
                            ),
                            rx.cond(
                                ~VideoLabelingState.all_prompts_mapped,
                                rx.text(
                                    "⚠ All prompts must be mapped to proceed",
                                    size="1",
                                    style={"color": styles.WARNING, "font_style": "italic"}
                                ),
                            ),
                            spacing="2",
                            width="100%",
                            padding="8px",
                            background=styles.BG_TERTIARY,
                            border_radius=styles.RADIUS_SM,
                        ),
                        # Hint when no prompt entered
                        rx.text(
                            "Enter comma-separated prompts and map to existing classes",
                            size="1",
                            style={"color": styles.TEXT_SECONDARY, "font_style": "italic"}
                        ),
                    ),
                    # Confidence slider
                    rx.vstack(
                        rx.hstack(
                            rx.text("Confidence:", size="1", style={"color": styles.TEXT_SECONDARY}),
                            rx.spacer(),
                            rx.text(
                                VideoLabelingState.autolabel_confidence_percentage,
                                size="1",
                                weight="medium",
                            ),
                            width="100%",
                        ),
                        rx.slider(
                            value=[VideoLabelingState.autolabel_confidence],
                            on_change=VideoLabelingState.set_autolabel_confidence,
                            min=0.1,
                            max=0.9,
                            step=0.05,
                            disabled=VideoLabelingState.is_autolabeling,
                            size="1",
                            width="100%",
                        ),
                        spacing="1",
                        width="100%",
                    ),
                    spacing="3",
                    width="100%",
                ),
            ),
            rx.divider(),
            # Video selection
            rx.vstack(
                rx.hstack(
                    rx.text("Select Videos", size="2", weight="medium"),
                    rx.spacer(),
                    rx.hstack(
                        rx.button(
                            "All", size="1", variant="ghost",
                            on_click=VideoLabelingState.select_all_videos_for_autolabel,
                        ),
                        rx.button(
                            "None", size="1", variant="ghost",
                            on_click=VideoLabelingState.deselect_all_videos_for_autolabel,
                        ),
                        spacing="1",
                    ),
                    width="100%",
                ),
                rx.scroll_area(
                    rx.vstack(
                        rx.foreach(VideoLabelingState.videos, video_checkbox),
                        spacing="0",
                        width="100%",
                    ),
                    type="always",
                    scrollbars="vertical",
                    style={"max_height": "150px"},
                ),
                rx.text(
                    f"{VideoLabelingState.selected_video_count_for_autolabel} videos, ~{VideoLabelingState.total_keyframes_for_autolabel} keyframes",
                    size="1",
                    style={"color": styles.TEXT_SECONDARY}
                ),
                spacing="2",
                width="100%",
            ),
            spacing="3",
            width="100%",
        )
    
    def yolo_panel() -> rx.Component:
        """YOLO model selection panel."""
        return rx.vstack(
            rx.cond(
                VideoLabelingState.has_autolabel_models,
                rx.vstack(
                    rx.text("Select Model", size="2", weight="medium"),
                    rx.select(
                        VideoLabelingState.autolabel_model_names,
                        placeholder="Choose a trained model...",
                        value=VideoLabelingState.selected_autolabel_model_name,
                        on_change=VideoLabelingState.select_autolabel_model_by_name,
                        disabled=VideoLabelingState.is_autolabeling,
                        size="2",
                        width="100%",
                    ),
                    # Confidence slider
                    rx.vstack(
                        rx.hstack(
                            rx.text("Confidence:", size="1", style={"color": styles.TEXT_SECONDARY}),
                            rx.spacer(),
                            rx.text(
                                VideoLabelingState.autolabel_confidence_percentage,
                                size="1",
                                weight="medium",
                            ),
                            width="100%",
                        ),
                        rx.slider(
                            value=[VideoLabelingState.autolabel_confidence],
                            on_change=VideoLabelingState.set_autolabel_confidence,
                            min=0.1,
                            max=0.9,
                            step=0.05,
                            disabled=VideoLabelingState.is_autolabeling,
                            size="1",
                            width="100%",
                        ),
                        spacing="1",
                        width="100%",
                    ),
                    rx.divider(),
                    # Video selection (same as SAM3)
                    rx.vstack(
                        rx.hstack(
                            rx.text("Select Videos", size="2", weight="medium"),
                            rx.spacer(),
                            rx.hstack(
                                rx.button(
                                    "All", size="1", variant="ghost",
                                    on_click=VideoLabelingState.select_all_videos_for_autolabel,
                                ),
                                rx.button(
                                    "None", size="1", variant="ghost",
                                    on_click=VideoLabelingState.deselect_all_videos_for_autolabel,
                                ),
                                spacing="1",
                            ),
                            width="100%",
                        ),
                        rx.scroll_area(
                            rx.vstack(
                                rx.foreach(VideoLabelingState.videos, video_checkbox),
                                spacing="0",
                                width="100%",
                            ),
                            type="always",
                            scrollbars="vertical",
                            style={"max_height": "150px"},
                        ),
                        rx.text(
                            f"{VideoLabelingState.selected_video_count_for_autolabel} videos, ~{VideoLabelingState.total_keyframes_for_autolabel} keyframes",
                            size="1",
                            style={"color": styles.TEXT_SECONDARY}
                        ),
                        spacing="2",
                        width="100%",
                    ),
                    spacing="3",
                    width="100%",
                ),
                # No models available
                rx.vstack(
                    rx.icon("package-x", size=32, color=styles.TEXT_SECONDARY),
                    rx.text("No models available", weight="medium"),
                    rx.text(
                        "Train a model and add it to autolabel from the Training dashboard.",
                        size="1",
                        style={"color": styles.TEXT_SECONDARY, "text_align": "center"},
                    ),
                    align="center",
                    padding="24px",
                    spacing="2",
                ),
            ),
            width="100%",
        )
    
    def future_tab_placeholder(icon: str, title: str, description: str) -> rx.Component:
        """Placeholder for future features."""
        return rx.vstack(
            rx.icon(icon, size=48, color=styles.TEXT_SECONDARY),
            rx.text(title, weight="medium"),
            rx.text(
                description,
                size="1",
                style={"color": styles.TEXT_SECONDARY, "text_align": "center"},
            ),
            rx.badge("Coming Soon", size="2", variant="outline"),
            align="center",
            padding="32px",
            spacing="2",
        )
    
    return rx.dialog.root(
        rx.dialog.content(
            rx.dialog.title(
                rx.hstack(
                    rx.icon("sparkles", size=20, color=styles.ACCENT),
                    rx.text("Auto-Label Videos"),
                    spacing="2",
                    align="center",
                ),
            ),
            rx.vstack(
                # Mode selector tabs
                rx.tabs.root(
                    rx.tabs.list(
                        rx.tabs.trigger("SAM3", value="sam3"),
                        rx.tabs.trigger("YOLO Model", value="yolo"),
                        size="1",
                    ),
                    rx.tabs.content(sam3_panel(), value="sam3", padding_top="16px"),
                    rx.tabs.content(yolo_panel(), value="yolo", padding_top="16px"),
                    value=VideoLabelingState.autolabel_mode,
                    on_change=VideoLabelingState.set_autolabel_mode,
                    width="100%",
                ),
                # Compute target toggle (Cloud / Local GPU)
                compute_target_toggle(
                    value=VideoLabelingState.compute_target,
                    on_change=VideoLabelingState.set_compute_target,
                    machines=VideoLabelingState.local_machines,
                    selected_machine=VideoLabelingState.selected_machine,
                    on_machine_change=VideoLabelingState.set_selected_machine,
                ),
                rx.divider(),
                # Progress/Log area (when running)
                rx.cond(
                    VideoLabelingState.is_autolabeling,
                    rx.vstack(
                        rx.hstack(
                            rx.spinner(size="2"),
                            rx.text("Processing...", weight="medium"),
                            spacing="2",
                        ),
                        rx.cond(
                            VideoLabelingState.autolabel_logs != "",
                            rx.box(
                                rx.scroll_area(
                                    rx.text(
                                        VideoLabelingState.autolabel_logs,
                                        font_family="JetBrains Mono, monospace",
                                        white_space="pre-wrap",
                                        size="1",
                                        style={"color": styles.CODE_TEXT, "line_height": "1.4"},
                                    ),
                                    type="always",
                                    scrollbars="vertical",
                                    style={"height": "110px"},  # Fixed height for scroll area
                                    id="video-autolabel-logs-scroll",
                                ),
                                style={
                                    "background": styles.CODE_BG,
                                    "padding": "8px",
                                    "border_radius": styles.RADIUS_SM,
                                    "height": "120px",  # Fixed height instead of max_height
                                    "width": "100%",
                                    "overflow": "hidden",  # Prevent spill
                                },
                            ),
                        ),
                        spacing="3",
                        width="100%",
                    ),
                ),
                # Action buttons
                rx.hstack(
                    rx.button(
                        "Cancel",
                        variant="outline",
                        color_scheme="gray",
                        on_click=VideoLabelingState.close_autolabel_modal,
                        disabled=VideoLabelingState.is_autolabeling,
                    ),
                    rx.button(
                        rx.cond(
                            VideoLabelingState.is_autolabeling,
                            rx.hstack(rx.spinner(size="1"), rx.text("Running..."), spacing="2"),
                            rx.hstack(rx.icon("play", size=14), rx.text("Start Auto-Label"), spacing="2"),
                        ),
                        on_click=VideoLabelingState.start_autolabel,
                        disabled=rx.cond(
                            VideoLabelingState.autolabel_mode == "sam3",
                            ~VideoLabelingState.can_autolabel,
                            ~VideoLabelingState.can_autolabel_yolo,
                        ),
                        variant="solid",
                        color_scheme="green",
                    ),
                    spacing="3",
                    justify="end",
                    width="100%",
                ),
                spacing="4",
                width="100%",
            ),
            style={"max_width": "480px"},
        ),
        open=VideoLabelingState.show_autolabel_modal,
        on_open_change=VideoLabelingState.set_show_autolabel_modal,
    )

def right_sidebar() -> rx.Component:
    """Right sidebar with tools and class selector."""
    return rx.box(
        rx.vstack(
            # Tools section
            rx.vstack(
                rx.text(
                    "Tools",
                    size="2",
                    weight="medium",
                    style={"color": styles.TEXT_PRIMARY}
                ),
                rx.hstack(
                    rx.icon_button(
                        rx.icon("mouse-pointer-2", size=20),
                        on_click=lambda: VideoLabelingState.set_tool("select"),
                        variant="solid",
                        color_scheme=rx.cond(
                            VideoLabelingState.current_tool == "select",
                            "blue",
                            "gray"
                        ),
                        size="2",
                        title="Select Tool (V)",
                    ),
                    rx.icon_button(
                        rx.icon("square", size=20),
                        on_click=lambda: VideoLabelingState.set_tool("draw"),
                        variant="solid",
                        color_scheme=rx.cond(
                            VideoLabelingState.current_tool == "draw",
                            "blue",
                            "gray"
                        ),
                        size="2",
                        title="Draw Rectangle (R)",
                    ),
                    # Mask Edit Tool
                    rx.icon_button(
                        rx.icon("pentagon", size=20),
                        on_click=lambda: VideoLabelingState.set_tool("mask_edit"),
                        variant="solid",
                        color_scheme=rx.cond(
                            VideoLabelingState.current_tool == "mask_edit",
                            "blue",
                            "gray"
                        ),
                        size="2",
                        cursor="pointer",
                        title="Edit Masks (C)"
                    ),
                    # Auto-Label Tool (opens modal)
                    rx.icon_button(
                        rx.icon("sparkles", size=20),
                        on_click=VideoLabelingState.open_autolabel_modal,
                        variant="outline",
                        color_scheme="green",
                        size="2",
                        cursor="pointer",
                        title="Auto-Label (L)"
                    ),
                    spacing="2",
                ),
                spacing="2",
                width="100%",
                padding_bottom=styles.SPACING_4,
                border_bottom=f"1px solid {styles.BORDER}",
            ),
            # Classes section
            rx.vstack(
                rx.hstack(
                    rx.text(
                        "Classes",
                        size="2",
                        weight="medium",
                        style={"color": styles.TEXT_PRIMARY}
                    ),
                    rx.spacer(),
                    rx.text(
                        VideoLabelingState.project_classes.length(),
                        size="1",
                        style={"color": styles.TEXT_SECONDARY}
                    ),
                    width="100%",
                    align="center",
                ),
                # Class list
                rx.cond(
                    VideoLabelingState.project_classes.length() > 0,
                    rx.vstack(
                        rx.foreach(
                            VideoLabelingState.project_classes,
                            class_item,
                        ),
                        spacing="1",
                        width="100%",
                    ),
                    rx.text(
                        "No classes defined",
                        size="1",
                        style={"color": styles.TEXT_SECONDARY, "font_style": "italic"}
                    ),
                ),
                # Add class input
                rx.hstack(
                    rx.input(
                        placeholder="New class...",
                        value=VideoLabelingState.new_class_name,
                        on_change=VideoLabelingState.set_new_class_name,
                        on_key_down=VideoLabelingState.handle_add_class_keydown,
                        size="1",
                        style={"flex": "1"},
                    ),
                    rx.icon_button(
                        rx.icon("plus", size=14),
                        size="1",
                        variant="outline",
                        on_click=VideoLabelingState.add_class,
                        disabled=VideoLabelingState.new_class_name.strip() == "",
                        title="Add class",
                    ),
                    spacing="2",
                    width="100%",
                ),
                spacing="3",
                width="100%",
                padding_bottom=styles.SPACING_4,
                border_bottom=f"1px solid {styles.BORDER}",
            ),
            # Current annotations section
            rx.cond(
                VideoLabelingState.has_selected_keyframe,
                rx.fragment(
                    rx.vstack(
                        rx.hstack(
                            rx.text(
                                "Annotations",
                                size="2",
                                weight="medium",
                                style={"color": styles.TEXT_PRIMARY}
                            ),
                            rx.spacer(),
                            rx.text(
                                VideoLabelingState.annotations.length(),
                                size="1",
                                style={"color": styles.TEXT_SECONDARY}
                            ),
                            width="100%",
                            align="center",
                        ),
                        rx.divider(style={"border_color": styles.BORDER}),
                        rx.scroll_area(
                            rx.vstack(
                                rx.foreach(
                                    VideoLabelingState.annotations,
                                    annotation_item,
                                ),
                                spacing="1",
                                width="100%",
                            ),
                            type="auto",
                            style={"flex": "1", "width": "100%", "min_height": "0"},
                        ),
                        # Delete Mask button (only shown when selected annotation has mask)
                        rx.cond(
                            VideoLabelingState.selected_annotation_has_mask,
                            rx.button(
                                rx.icon("eraser", size=14),
                                "Delete Mask",
                                variant="outline",
                                color_scheme="gray",
                                size="1",
                                width="100%",
                                on_click=VideoLabelingState.delete_mask_from_annotation,
                                cursor="pointer",
                            ),
                        ),
                        spacing="2",
                        height="100%",
                        width="100%",
                        min_height="0",
                    ),
                ),
            ),
            spacing="4",
            height="100%",
            width="100%",
            padding=styles.SPACING_3,
        ),
        width="220px",
        min_width="220px",
        height="100%",
        background=styles.BG_SECONDARY,
        border_left=f"1px solid {styles.BORDER}",
    )


# =============================================================================
# MAIN LAYOUT
# =============================================================================

def loading_skeleton() -> rx.Component:
    """Loading skeleton for the editor."""
    return rx.center(
        rx.vstack(
            rx.spinner(size="3"),
            rx.text("Loading video editor...", size="2", style={"color": styles.TEXT_SECONDARY}),
            spacing="3",
        ),
        width="100%",
        height="100%",
    )


def shortcuts_help_modal() -> rx.Component:
    """Keyboard shortcuts help modal for video editor."""
    def shortcut_row(key: str, description: str) -> rx.Component:
        return rx.hstack(
            rx.box(
                rx.text(
                    key,
                    size="1",
                    weight="medium",
                    style={
                        "font_family": "JetBrains Mono, monospace",
                        "color": styles.TEXT_PRIMARY,
                    },
                ),
                background=styles.BG_TERTIARY,
                padding="4px 8px",
                border_radius=styles.RADIUS_SM,
                min_width="80px",
                text_align="center",
            ),
            rx.text(description, size="2", style={"color": styles.TEXT_SECONDARY}),
            width="100%",
            spacing="3",
            align="center",
        )
    
    return rx.dialog.root(
        rx.dialog.content(
            rx.dialog.title("Keyboard Shortcuts"),
            rx.vstack(
                rx.text("Video Navigation", size="2", weight="medium"),
                shortcut_row("Space", "Play/Pause video"),
                shortcut_row("Z", "Previous frame"),
                shortcut_row("C", "Next frame"),
                shortcut_row("Shift+Z", "Back 10 frames"),
                shortcut_row("Shift+C", "Forward 10 frames"),
                rx.divider(),
                rx.text("Keyframes", size="2", weight="medium"),
                shortcut_row("K", "Mark current frame"),
                shortcut_row("Q", "Previous keyframe"),
                shortcut_row("E", "Next keyframe"),
                shortcut_row("I", "Set interval start"),
                shortcut_row("O", "Set interval end"),
                shortcut_row("P", "Create interval keyframes"),
                rx.divider(),
                rx.text("Annotation", size="2", weight="medium"),
                shortcut_row("V", "Select tool"),
                shortcut_row("R", "Draw rectangle"),
                shortcut_row("⬠", "Edit masks (button only)"),
                shortcut_row("L", "Open Auto-Label"),
                shortcut_row("Delete", "Delete selected"),
                shortcut_row("1-9", "Select class"),
                rx.divider(),
                rx.text("General", size="2", weight="medium"),
                shortcut_row("M", "Toggle Focus Mode"),
                shortcut_row("F", "Toggle Fullscreen"),
                shortcut_row("H", "Go to Dashboard"),
                shortcut_row("?", "Toggle this help"),
                shortcut_row("Esc", "Deselect / Cancel"),
                spacing="2",
                width="100%",
            ),
            rx.dialog.close(
                rx.button("Close", variant="outline", size="2"),
            ),
            style={"max_width": "400px"},
        ),
        open=VideoLabelingState.show_shortcuts_help,
        on_open_change=lambda _: VideoLabelingState.toggle_shortcuts_help(),
    )









def editor_layout() -> rx.Component:
    """Main 3-panel editor layout with focus mode support."""
    return rx.hstack(
        # Left sidebar - hidden in focus mode with slide animation
        rx.box(
            left_sidebar(),
            width=rx.cond(VideoLabelingState.focus_mode, "0px", "230px"),
            min_width=rx.cond(VideoLabelingState.focus_mode, "0px", "230px"),
            height="100%",
            overflow="hidden",
            transition="all 0.3s ease-in-out",
        ),
        canvas_container(),
        # Right sidebar - hidden in focus mode with slide animation
        rx.box(
            right_sidebar(),
            width=rx.cond(VideoLabelingState.focus_mode, "0px", "220px"),
            min_width=rx.cond(VideoLabelingState.focus_mode, "0px", "220px"),
            height="100%",
            overflow="hidden",
            transition="all 0.3s ease-in-out",
        ),
        spacing="0",
        width="100%",
        height="100vh",
    )


def bulk_delete_keyframes_modal() -> rx.Component:
    """Modal for confirming bulk keyframe deletion."""
    return rx.dialog.root(
        rx.dialog.content(
            rx.dialog.title("Delete Keyframes", style={"color": styles.ERROR}),
            rx.vstack(
                rx.text(
                    f"Are you sure you want to delete {VideoLabelingState.selected_keyframe_count} keyframe(s)?",
                    style={"color": styles.TEXT_PRIMARY}
                ),
                rx.text(
                    "This will permanently delete the selected keyframes and their annotations.",
                    size="2",
                    style={"color": styles.TEXT_SECONDARY}
                ),
                rx.hstack(
                    rx.dialog.close(
                        rx.button(
                            "Cancel",
                            variant="outline",
                            color_scheme="gray",
                            on_click=VideoLabelingState.close_bulk_delete_keyframes_modal,
                        ),
                    ),
                    rx.button(
                        "Delete",
                        color_scheme="red",
                        loading=VideoLabelingState.is_bulk_deleting_keyframes,
                        on_click=VideoLabelingState.confirm_bulk_delete_keyframes,
                    ),
                    spacing="3",
                    justify="end",
                    width="100%",
                ),
                spacing="3",
                width="100%",
            ),
            style={"max_width": "400px"},
        ),
        open=VideoLabelingState.show_bulk_delete_keyframes_modal,
    )


def delete_video_modal() -> rx.Component:
    """Modal for confirming video deletion."""
    return rx.dialog.root(
        rx.dialog.content(
            rx.vstack(
                rx.hstack(
                    rx.icon("alert-triangle", size=20, color=styles.WARNING),
                    rx.text(
                        "Remove this video?",
                        weight="medium",
                        style={"color": styles.TEXT_PRIMARY}
                    ),
                    spacing="2",
                    align="center",
                ),
                rx.text(
                    VideoLabelingState.video_to_delete_name,
                    size="2",
                    weight="medium",
                    style={
                        "color": styles.TEXT_SECONDARY,
                        "max_width": "100%",
                        "overflow": "hidden",
                        "text_overflow": "ellipsis",
                        "white_space": "nowrap",
                    }
                ),
                rx.text(
                    "This will also delete all keyframes and annotations.",
                    size="1",
                    style={"color": styles.TEXT_SECONDARY}
                ),
                rx.hstack(
                    rx.dialog.close(
                        rx.button(
                            "Cancel",
                            variant="outline",
                            color_scheme="gray",
                            on_click=VideoLabelingState.close_delete_video_modal,
                        ),
                    ),
                    rx.button(
                        "Confirm",
                        color_scheme="red",
                        on_click=VideoLabelingState.confirm_delete_video,
                    ),
                    spacing="3",
                    justify="end",
                    width="100%",
                ),
                spacing="3",
                width="100%",
            ),
            style={"max_width": "320px"},
        ),
        open=VideoLabelingState.show_delete_video_modal,
    )


def empty_stats_modal() -> rx.Component:
    """Modal showing stats about unannotated keyframes/images with option to delete them."""
    return rx.dialog.root(
        rx.dialog.content(
            rx.dialog.title(
                rx.hstack(
                    rx.icon("bar-chart-2", size=18, color=styles.ACCENT),
                    "Video Statistics",
                    spacing="2",
                    align="center",
                )
            ),
            rx.vstack(
                # Stats section
                rx.vstack(
                    rx.hstack(
                        rx.icon("film", size=16, color=styles.TEXT_SECONDARY),
                        rx.text("Total keyframes:", size="2"),
                        rx.spacer(),
                        rx.text(
                            VideoLabelingState.keyframe_count,
                            size="2",
                            weight="bold",
                            style={"color": styles.TEXT_PRIMARY}
                        ),
                        width="100%",
                        align="center",
                    ),
                    rx.hstack(
                        rx.icon("check-circle", size=16, color=styles.SUCCESS),
                        rx.text("Annotated:", size="2"),
                        rx.spacer(),
                        rx.text(
                            VideoLabelingState.labeled_keyframe_count,
                            size="2",
                            weight="bold",
                            style={"color": styles.SUCCESS}
                        ),
                        width="100%",
                        align="center",
                    ),
                    rx.hstack(
                        rx.icon("circle-x", size=16, color=styles.WARNING),
                        rx.text("Not annotated:", size="2"),
                        rx.spacer(),
                        rx.text(
                            VideoLabelingState.unlabeled_keyframe_count,
                            size="2",
                            weight="bold",
                            style={"color": styles.WARNING}
                        ),
                        width="100%",
                        align="center",
                    ),
                    spacing="2",
                    width="100%",
                    padding="12px",
                    background=styles.BG_TERTIARY,
                    border_radius=styles.RADIUS_SM,
                ),
                rx.divider(),
                # Delete empty keyframes section
                rx.cond(
                    VideoLabelingState.unlabeled_keyframe_count > 0,
                    rx.vstack(
                        rx.callout(
                            rx.text(
                                f"You can delete all {VideoLabelingState.unlabeled_keyframe_count} unannotated keyframe(s). "
                                "This action is permanent and cannot be undone.",
                            ),
                            icon="triangle-alert",
                            color="brown",
                            size="2",
                        ),
                        rx.text(
                            "To confirm, please type 'delete' below:",
                            size="2",
                            weight="medium",
                        ),
                        rx.input(
                            value=VideoLabelingState.empty_delete_confirmation,
                            on_change=VideoLabelingState.set_empty_delete_confirmation,
                            placeholder="Type 'delete'",
                            width="100%",
                        ),
                        rx.hstack(
                            rx.dialog.close(
                                rx.button(
                                    "Cancel",
                                    variant="outline",
                                    color_scheme="gray",
                                    on_click=VideoLabelingState.close_empty_stats_modal,
                                ),
                            ),
                            rx.button(
                                rx.cond(
                                    VideoLabelingState.is_deleting_empty_keyframes,
                                    rx.hstack(rx.spinner(size="1"), rx.text("Deleting..."), spacing="2"),
                                    rx.hstack(rx.icon("trash-2", size=14), rx.text("Delete Empty Keyframes"), spacing="2"),
                                ),
                                color_scheme="red",
                                on_click=VideoLabelingState.delete_empty_keyframes,
                                disabled=~VideoLabelingState.can_confirm_delete_empty,
                            ),
                            spacing="3",
                            justify="end",
                            width="100%",
                        ),
                        spacing="3",
                        width="100%",
                    ),
                    # No empty keyframes
                    rx.vstack(
                        rx.hstack(
                            rx.icon("check-circle", size=20, color=styles.SUCCESS),
                            rx.text(
                                "All keyframes have annotations!",
                                weight="medium",
                                style={"color": styles.SUCCESS}
                            ),
                            spacing="2",
                            align="center",
                        ),
                        rx.dialog.close(
                            rx.button(
                                "Close",
                                variant="outline",
                                width="100%",
                                on_click=VideoLabelingState.close_empty_stats_modal,
                            ),
                        ),
                        spacing="3",
                        width="100%",
                        align="center",
                    ),
                ),
                spacing="4",
                width="100%",
            ),
            style={"max_width": "450px"},
        ),
        open=VideoLabelingState.show_empty_stats_modal,
    )


def editor_content() -> rx.Component:
    """Content wrapper with loading state."""
    return rx.box(
        rx.cond(
            VideoLabelingState.is_loading,
            loading_skeleton(),
            rx.cond(
                VideoLabelingState.error_message != "",
                rx.center(
                    rx.vstack(
                        rx.icon("alert-circle", size=32, color=styles.ERROR),
                        rx.text(VideoLabelingState.error_message, style={"color": styles.ERROR}),
                        spacing="2",
                    ),
                ),
                editor_layout(),
            ),
        ),
        shortcuts_help_modal(),
        bulk_delete_keyframes_modal(),
        delete_video_modal(),
        autolabel_modal(),
        empty_stats_modal(),
        # Right-click context menu for annotations
        annotation_context_menu(
            is_open=VideoLabelingState.context_menu_open,
            position_x=VideoLabelingState.context_menu_x,
            position_y=VideoLabelingState.context_menu_y,
            classes=VideoLabelingState.project_classes,
            on_class_change=VideoLabelingState.context_menu_change_class,
            on_project_thumbnail=VideoLabelingState.set_as_project_thumbnail,
            on_dataset_thumbnail=VideoLabelingState.set_as_dataset_thumbnail,
            on_close=VideoLabelingState.close_context_menu,
        ),
        width="100%",
        height="100vh",
        background=styles.BG_PRIMARY,
    )


@rx.page(
    route="/projects/[project_id]/datasets/[dataset_id]/video-label",
    title="Video Labeling",
    on_load=[VideoLabelingState.restore_canvas_state, VideoLabelingState.load_project],
)
def video_labeling_editor() -> rx.Component:
    """The video labeling editor page (protected)."""
    return require_auth(editor_content())
