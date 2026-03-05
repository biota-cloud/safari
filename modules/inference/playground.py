"""
Inference Playground — Interactive UI for testing trained models.

Route: /playground

Compact, elegant layout:
- Card with header + compact upload zone
- Collapsible model selector with built-in models hidden by default
- Inline controls with proper spacing
- Results grid with in-place preview modal
"""

import reflex as rx
import styles
from modules.inference.state import InferenceState
from components.compute_target_toggle import compute_target_toggle
from modules.training.dashboard import numeric_stepper


# =============================================================================
# Shared Mask Overlay Component
# =============================================================================

def mask_overlays(masks_css_var) -> rx.Component:
    """
    Render segmentation masks as CSS clip-path overlays.
    
    Single source of truth for mask rendering style.
    Used by single image, batch image, and full view.
    
    Args:
        masks_css_var: Reflex var containing list of dicts with 'clip_path'
    
    Returns:
        Fragment with absolute-positioned mask overlays
    """
    return rx.foreach(
        masks_css_var,
        lambda mask: rx.box(
            style={
                "position": "absolute",
                "top": "0",
                "left": "0",
                "width": "100%",
                "height": "100%",
                "background": "rgba(0, 255, 0, 0.3)",
                "clip_path": mask["clip_path"],
                "pointer_events": "none",
            },
        ),
    )


# =============================================================================
# Result Card (Compact)
# =============================================================================

def result_card(result: dict) -> rx.Component:
    """Professional result card with thumbnail and clean layout."""
    result_id = result["id"]
    
    # Check if this result has a thumbnail URL (embedded in result by load_user_results)
    thumbnail_url = result["thumbnail_url"]
    
    return rx.box(
        rx.hstack(
            # Left: Thumbnail or placeholder (60x60)
            rx.cond(
                thumbnail_url != "",
                # Show actual thumbnail image
                rx.image(
                    src=thumbnail_url,
                    width="60px",
                    height="60px",
                    object_fit="cover",
                    border_radius=styles.RADIUS_SM,
                    style={"border": f"1px solid {styles.BORDER}"},
                ),
                # Fallback to icon placeholder
                rx.center(
                    rx.icon(
                        rx.match(
                            result["input_type"],
                            ("batch", "layers"),
                            ("video", "film"),
                            "image",
                        ),
                        size=24,
                        style={"color": styles.TEXT_SECONDARY, "opacity": "0.5"},
                    ),
                    width="60px",
                    height="60px",
                    background=styles.BG_PRIMARY,
                    border_radius=styles.RADIUS_SM,
                    flex_shrink="0",
                ),
            ),
            
            # Middle: Content (filename + model + settings + timestamp)
            rx.vstack(
                rx.text(
                    result["input_filename"],
                    size="2",
                    weight="medium",
                    style={
                        "color": styles.TEXT_PRIMARY,
                        "overflow": "hidden",
                        "text_overflow": "ellipsis",
                        "white_space": "nowrap",
                    },
                ),
                rx.text(
                    result["model_name"],
                    size="1",
                    style={
                        "color": styles.TEXT_SECONDARY,
                        "overflow": "hidden",
                        "text_overflow": "ellipsis",
                        "white_space": "nowrap",
                    },
                ),
                # Settings + timestamp line
                rx.hstack(
                    # Settings (pre-formatted server-side)
                    rx.cond(
                        result["settings_display"] != "",
                        rx.text(
                            result["settings_display"],
                            size="1",
                            style={
                                "color": styles.TEXT_SECONDARY,
                                "opacity": "0.7",
                                "font_size": "10px",
                                "overflow": "hidden",
                                "text_overflow": "ellipsis",
                                "white_space": "nowrap",
                            },
                        ),
                        rx.fragment(),
                    ),
                    # Timestamp
                    rx.cond(
                        result["created_at"] != "",
                        rx.el.span(
                            rx.moment(
                                result["created_at"],
                                from_now=True,
                            ),
                            style={
                                "color": styles.TEXT_SECONDARY,
                                "opacity": "0.5",
                                "font_size": "10px",
                            },
                        ),
                        rx.fragment(),
                    ),
                    spacing="1",
                    align="center",
                ),
                spacing="0",
                align_items="start",
                flex="1",
                min_width="0",  # Allow text truncation
            ),
            
            # Right: Badge + Actions (vertically centered)
            rx.hstack(
                rx.badge(
                    result["detection_count"].to_string() + " det",
                    color_scheme="green",
                    variant="outline",
                    size="1",
                ),
                rx.icon_button(
                    rx.icon("eye", size=14),
                    size="1",
                    variant="ghost",
                    on_click=InferenceState.preview_result(result_id),
                ),
                rx.link(
                    rx.icon_button(
                        rx.icon("external-link", size=14),
                        size="1",
                        variant="ghost",
                    ),
                    href=f"/inference/result/{result['id']}",
                    style={"display": "flex", "align_items": "center"},
                ),
                rx.icon_button(
                    rx.icon("trash-2", size=14),
                    size="1",
                    variant="ghost",
                    color_scheme="red",
                    on_click=[
                        rx.stop_propagation,
                        InferenceState.delete_inference_result(result_id),
                    ],
                    class_name="delete-btn",
                ),
                spacing="2",
                align="center",
                flex_shrink="0",
            ),
            
            spacing="3",
            width="100%",
            align="center",
        ),
        padding=styles.SPACING_3,
        background=styles.CARD_BG,
        border_radius=styles.RADIUS_MD,
        border=f"1px solid {styles.BORDER}",
        _hover={
            "border_color": styles.ACCENT,
            "& .delete-btn": {"opacity": "1"},
        },
        transition="all 0.15s ease",
        cursor="pointer",
        on_click=InferenceState.preview_result(result_id),
    )


# =============================================================================
# Model Dropdown (Compact with collapsible built-in)
# =============================================================================

def model_dropdown() -> rx.Component:
    """
    Compact model selector with two-row layout per model.
    
    Row 1: Alias + weights badge (best/last) + checkmark
    Row 2: Mini badges for type, backbone, metric
    """
    # Shared width for trigger and dropdown alignment
    dropdown_width = "340px"
    
    return rx.popover.root(
        rx.popover.trigger(
            rx.box(
                rx.hstack(
                    rx.icon(
                        rx.cond(InferenceState.is_hybrid_mode, "layers", "cpu"),
                        size=14,
                        style={"color": rx.cond(InferenceState.is_hybrid_mode, styles.PURPLE, styles.ACCENT)},
                    ),
                    rx.text(
                        InferenceState.selected_model_name,
                        size="2",
                        weight="medium",
                        style={
                            "color": styles.TEXT_PRIMARY,
                            "overflow": "hidden",
                            "text_overflow": "ellipsis",
                            "white_space": "nowrap",
                            "flex": "1",
                        },
                    ),
                    # Mode indicator badge
                    rx.cond(
                        InferenceState.is_hybrid_mode,
                        rx.badge("Hybrid", color_scheme="purple", size="1", variant="outline"),
                        rx.badge("Detect", color_scheme="green", size="1", variant="outline"),
                    ),
                    rx.icon("chevron-down", size=12, style={"color": styles.TEXT_SECONDARY}),
                    spacing="2",
                    align="center",
                    width="100%",
                ),
                padding="6px 10px",
                background=styles.BG_TERTIARY,
                border_radius=styles.RADIUS_SM,
                border=f"1px solid {styles.BORDER}",
                cursor="pointer",
                min_width=dropdown_width,
                _hover={"border_color": styles.ACCENT},
            ),
        ),
        rx.popover.content(
            rx.vstack(
                # Text search filter
                rx.input(
                    placeholder="Search models...",
                    value=InferenceState.project_filter,
                    on_change=InferenceState.set_project_filter,
                    size="1",
                    width="100%",
                    style={
                        "background": styles.BG_PRIMARY,
                        "border": f"1px solid {styles.BORDER}",
                    },
                ),
                
                # Custom models grouped by project
                rx.cond(
                    InferenceState.filtered_projects.length() > 0,
                    rx.vstack(
                        rx.foreach(
                            InferenceState.filtered_projects,
                            lambda project: rx.vstack(
                                # Project header
                                rx.text(
                                    project["project_name"],
                                    size="1",
                                    weight="medium",
                                    style={"color": styles.TEXT_SECONDARY, "padding_top": "4px"},
                                ),
                                # Model cards
                                rx.foreach(
                                    project["models"],
                                    lambda m: rx.box(
                                        rx.vstack(
                                            # Row 1: Name + weights badge + checkmark
                                            rx.hstack(
                                                rx.text(m["name"], size="2", weight="medium", style={
                                                    "color": styles.TEXT_PRIMARY,
                                                    "overflow": "hidden",
                                                    "text_overflow": "ellipsis",
                                                    "white_space": "nowrap",
                                                    "flex": "1",
                                                }),
                                                # Weights type badge (best/last)
                                                rx.cond(
                                                    m["weights_type"] == "best",
                                                    rx.box("best", style=styles.BADGE_MINI | {
                                                                "background": f"{styles.SUCCESS}26",
                                                        "color": styles.SUCCESS,
                                                        "font_weight": "500",
                                                    }),
                                                    rx.cond(
                                                        m["weights_type"] == "last",
                                                        rx.box("last", style=styles.BADGE_MINI | {
                                                            "background": f"{styles.WARNING}26",
                                                            "color": styles.WARNING,
                                                            "font_weight": "500",
                                                        }),
                                                        rx.fragment(),
                                                    ),
                                                ),
                                                # Selection checkmark
                                                rx.cond(
                                                    InferenceState.selected_model_name == m["name"],
                                                    rx.icon("check", size=12, style={"color": styles.ACCENT}),
                                                    rx.fragment(),
                                                ),
                                                # Remove from playground
                                                rx.icon_button(
                                                    rx.icon("trash-2", size=12),
                                                    size="1",
                                                    variant="ghost",
                                                    color_scheme="red",
                                                    on_click=[
                                                        rx.stop_propagation,
                                                        InferenceState.remove_model_from_playground(m["id"]),
                                                    ],
                                                    class_name="delete-model-btn",
                                                    style={"opacity": "0", "transition": "opacity 0.15s ease"},
                                                ),
                                                width="100%",
                                                align="center",
                                                spacing="2",
                                            ),
                                            # Row 2: Type + backbone + metric (mini badges)
                                            rx.hstack(
                                                # Model type badge (Detect/Classify)
                                                rx.cond(
                                                    m["run_model_type"] == "classification",
                                                    rx.box("Classify", style=styles.BADGE_MINI | {
                                                        "background": f"{styles.PURPLE}26",
                                                        "color": styles.PURPLE,
                                                        "font_weight": "500",
                                                    }),
                                                    rx.box("Detect", style=styles.BADGE_MINI | {
                                                        "background": f"{styles.ACCENT}26",
                                                        "color": styles.ACCENT,
                                                        "font_weight": "500",
                                                    }),
                                                ),
                                                # Backbone badge (only for classification)
                                                rx.cond(
                                                    m["backbone"] == "convnext",
                                                    rx.box("CNX", style=styles.BADGE_MINI | {
                                                        "background": styles.BG_TERTIARY,
                                                        "color": styles.TEXT_PRIMARY,
                                                        "border": f"1px solid {styles.BORDER}",
                                                        "font_weight": "500",
                                                    }),
                                                    rx.cond(
                                                        m["backbone"] == "yolo",
                                                        rx.box("YOLO", style=styles.BADGE_MINI | {
                                                            "background": styles.BG_TERTIARY,
                                                            "color": styles.TEXT_PRIMARY,
                                                            "border": f"1px solid {styles.BORDER}",
                                                            "font_weight": "500",
                                                        }),
                                                        rx.fragment(),  # No backbone for detection models
                                                    ),
                                                ),
                                                # Metric badge (mAP or Acc)
                                                rx.cond(
                                                    m["metric_value"] != None,
                                                    rx.cond(
                                                        m["run_model_type"] == "classification",
                                                        rx.box(
                                                            "Acc: " + m["metric_value"].to_string(),
                                                            style=styles.BADGE_MINI | {
                                                                        "background": f"{styles.SUCCESS}26",
                                                                "color": styles.SUCCESS,
                                                                "font_weight": "500",
                                                            },
                                                        ),
                                                        rx.box(
                                                            "mAP: " + m["metric_value"].to_string(),
                                                            style=styles.BADGE_MINI | {
                                                                        "background": f"{styles.SUCCESS}26",
                                                                "color": styles.SUCCESS,
                                                                "font_weight": "500",
                                                            },
                                                        ),
                                                    ),
                                                    rx.fragment(),
                                                ),
                                                spacing="1",
                                                align="center",
                                            ),
                                            spacing="1",
                                            align_items="start",
                                            width="100%",
                                        ),
                                        padding="8px 10px",
                                        background=styles.POPOVER_ITEM_BG,
                                        border_radius=styles.RADIUS_SM,
                                        border=f"1px solid {styles.BORDER}",
                                        cursor="pointer",
                                        width="100%",
                                        _hover={
                                            "border_color": styles.ACCENT,
                                            "& .delete-model-btn": {"opacity": "1"},
                                        },
                                        on_click=InferenceState.select_model_by_name(m["name"]),
                                    ),
                                ),
                                spacing="2",
                                width="100%",
                            ),
                        ),
                        spacing="3",
                        width="100%",
                    ),
                    rx.text("No models found", size="1", style={"color": styles.TEXT_SECONDARY}),
                ),
                
                # Divider
                rx.divider(style={"border_color": styles.BORDER}),
                
                # Built-in models (collapsible)
                rx.vstack(
                    rx.hstack(
                        rx.icon("zap", size=10, style={"color": styles.WARNING}),
                        rx.text("Built-in Models", size="1", style={"color": styles.TEXT_SECONDARY}),
                        rx.spacer(),
                        rx.icon(
                            rx.cond(InferenceState.is_builtin_expanded, "chevron-up", "chevron-down"),
                            size=12,
                            style={"color": styles.TEXT_SECONDARY}
                        ),
                        width="100%",
                        align="center",
                        cursor="pointer",
                        on_click=InferenceState.toggle_builtin_expanded,
                    ),
                    rx.cond(
                        InferenceState.is_builtin_expanded,
                        rx.vstack(
                            rx.foreach(
                                InferenceState.builtin_models,
                                lambda name: rx.box(
                                    rx.hstack(
                                        rx.text(name, size="2", style={"color": styles.TEXT_PRIMARY}),
                                        rx.spacer(),
                                        rx.cond(
                                            InferenceState.selected_model_name == name,
                                            rx.icon("check", size=12, style={"color": styles.ACCENT}),
                                            rx.fragment(),
                                        ),
                                        width="100%",
                                    ),
                                    padding="6px 10px",
                                    background=styles.POPOVER_ITEM_BG,
                                    border_radius=styles.RADIUS_SM,
                                    border=f"1px solid {styles.BORDER}",
                                    cursor="pointer",
                                    width="100%",
                                    _hover={"border_color": styles.ACCENT},
                                    on_click=InferenceState.select_model_by_name(name),
                                ),
                            ),
                            spacing="2",
                            width="100%",
                        ),
                        rx.fragment(),
                    ),
                    spacing="2",
                    width="100%",
                ),
                
                spacing="3",
                width="100%",
                # Scrollable container - max height for ~6 cards
                max_height="360px",
                overflow_y="auto",
            ),
            style={
                "background": styles.POPOVER_BG,
                "border": f"1px solid {styles.BORDER}",
                "border_radius": styles.RADIUS_MD,
                "padding": styles.SPACING_3,
                "min_width": dropdown_width,
            },
        ),
        open=InferenceState.model_dropdown_open,
        on_open_change=InferenceState.set_model_dropdown_open,
    )


# =============================================================================
# Main Inference Card
# =============================================================================

def inference_card() -> rx.Component:
    """Main card with header, upload zone, and controls."""
    return rx.box(
        rx.vstack(
            # Header row
            rx.hstack(
                rx.hstack(
                    rx.icon("zap", size=20, style={"color": styles.ACCENT}),
                    rx.text("Run Inference", size="4", weight="bold", style={"color": styles.TEXT_PRIMARY}),
                    spacing="2",
                    align="center",
                ),
                rx.spacer(),
                # Model selector
                model_dropdown(),
                width="100%",
                align="center",
            ),
            
            # Upload zone (compact)
            rx.upload(
                rx.box(
                    rx.cond(
                        # Batch mode: show thumbnail grid
                        InferenceState.batch_mode & (InferenceState.uploaded_images.length() > 0),
                        rx.vstack(
                            rx.hstack(
                                rx.icon("images", size=14, style={"color": styles.ACCENT}),
                                rx.text(
                                    InferenceState.uploaded_images.length().to_string() + " images uploaded",
                                    size="2",
                                    weight="medium",
                                    style={"color": styles.TEXT_PRIMARY},
                                ),
                                spacing="2",
                                align="center",
                            ),
                            # Thumbnail grid
                            rx.box(
                                rx.foreach(
                                    InferenceState.uploaded_images,
                                    lambda img: rx.image(
                                        src=img["base64_preview"],
                                        width="60px",
                                        height="60px",
                                        object_fit="cover",
                                        border_radius=styles.RADIUS_SM,
                                        style={"border": f"1px solid {styles.BORDER}"},
                                    ),
                                ),
                                style={
                                    "display": "flex",
                                    "flex_wrap": "wrap",
                                    "gap": "4px",
                                    "max_height": "140px",
                                    "overflow_y": "auto",
                                },
                            ),
                            spacing="2",
                            align="start",
                            width="100%",
                        ),
                        # Single file or empty
                        rx.cond(
                            (InferenceState.uploaded_image_data != "") | (InferenceState.uploaded_video_data != ""),
                            # Single file preview
                            rx.cond(
                                InferenceState.uploaded_file_type == "image",
                                rx.center(
                                    rx.image(
                                        src=InferenceState.uploaded_image_data,
                                        max_width="100%",
                                        max_height="180px",
                                        object_fit="contain",
                                        border_radius=styles.RADIUS_SM,
                                    ),
                                ),
                                # Video preview
                                rx.box(
                                    rx.image(
                                        src=InferenceState.video_thumbnail_url,
                                        width="100%",
                                        max_height="180px",
                                        object_fit="contain",
                                        border_radius=styles.RADIUS_SM,
                                    ),
                                    rx.box(
                                        rx.hstack(
                                            rx.icon("video", size=12, style={"color": "white"}),
                                            rx.text(
                                                f"{InferenceState.video_duration:.1f}s",
                                                size="1",
                                                style={"color": "white"},
                                            ),
                                            spacing="1",
                                            align="center",
                                        ),
                                        position="absolute",
                                        bottom="4px",
                                        right="4px",
                                        padding="2px 6px",
                                        background="rgba(0,0,0,0.7)",
                                        border_radius=styles.RADIUS_SM,
                                    ),
                                    position="relative",
                                ),
                            ),
                            # Empty state
                            rx.vstack(
                                rx.icon("upload", size=28, style={"color": styles.TEXT_SECONDARY, "opacity": "0.5"}),
                                rx.text("Drop images or video", size="2", style={"color": styles.TEXT_SECONDARY}),
                                rx.text("(multiple images supported)", size="1", style={"color": styles.TEXT_SECONDARY, "opacity": "0.6"}),
                                spacing="2",
                                align="center",
                                justify="center",
                                min_height="100px",
                            ),
                        ),
                    ),
                ),
                id="inference_upload",
                accept={
                    "image/*": [".jpg", ".jpeg", ".png", ".webp"],
                    "video/*": [".mp4", ".mov", ".avi", ".webm"],
                },
                multiple=True,  # Enable batch image upload
                border=f"1px dashed {styles.BORDER}",
                border_radius=styles.RADIUS_MD,
                background=styles.BG_PRIMARY,
                width="100%",
                padding=styles.SPACING_3,
                _hover={"border_color": styles.ACCENT},
                cursor="pointer",
            ),
            
            # Upload button (when file selected)
            rx.cond(
                rx.selected_files("inference_upload").length() > 0,
                rx.hstack(
                    # Show file count or single filename
                    rx.cond(
                        rx.selected_files("inference_upload").length() > 1,
                        rx.hstack(
                            rx.icon("images", size=12, style={"color": styles.ACCENT}),
                            rx.text(
                                rx.selected_files("inference_upload").length().to_string() + " files selected",
                                size="1",
                                weight="medium",
                                style={"color": styles.TEXT_PRIMARY},
                            ),
                            spacing="1",
                            align="center",
                        ),
                        rx.text(
                            rx.selected_files("inference_upload")[0],
                            size="1",
                            style={"color": styles.TEXT_SECONDARY, "max_width": "200px", "overflow": "hidden", "text_overflow": "ellipsis"},
                        ),
                    ),
                    rx.spacer(),
                    rx.button(
                        rx.hstack(rx.icon("upload", size=12), rx.text("Upload"), spacing="1"),
                        on_click=lambda: InferenceState.handle_upload(rx.upload_files(upload_id="inference_upload")),
                        size="1",
                        style={"background": styles.ACCENT, "color": "white"},
                    ),
                    width="100%",
                    align="center",
                    padding=styles.SPACING_2,
                    background=styles.BG_PRIMARY,
                    border_radius=styles.RADIUS_SM,
                ),
                rx.fragment(),
            ),
            
            # Upload/inference progress
            rx.cond(
                InferenceState.is_uploading,
                rx.hstack(
                    rx.spinner(size="1"),
                    rx.text(InferenceState.upload_stage, size="1", style={"color": styles.TEXT_SECONDARY}),
                    spacing="2",
                    align="center",
                    padding=styles.SPACING_2,
                ),
                rx.fragment(),
            ),
            
            # Video controls (compact, only for videos)
            rx.cond(
                InferenceState.uploaded_file_type == "video",
                rx.hstack(
                    # Start time — label tight to controls
                    rx.hstack(
                        rx.text("Start", size="1", weight="medium", style={"color": styles.TEXT_SECONDARY}),
                        rx.icon_button(
                            rx.icon("minus", size=12), size="1", variant="ghost",
                            on_click=InferenceState.decrement_video_start,
                            style={"color": styles.TEXT_SECONDARY, "&:hover": {"background": styles.BG_TERTIARY, "color": styles.TEXT_PRIMARY}},
                        ),
                        rx.input(
                            key=InferenceState.video_start_time.to(str),
                            default_value=InferenceState.video_start_time.to(str),
                            on_blur=InferenceState.set_video_start_input,
                            on_key_down=rx.call_script("if (event.key === 'Enter') event.target.blur()"),
                            size="1",
                            style={"width": "52px", "text_align": "center", "color": styles.ACCENT, "font_weight": "bold",
                                   "font_family": styles.FONT_FAMILY_MONO, "background": "transparent",
                                   "border": f"1px solid {styles.BORDER}", "border_radius": styles.RADIUS_SM},
                        ),
                        rx.icon_button(
                            rx.icon("plus", size=12), size="1", variant="ghost",
                            on_click=InferenceState.increment_video_start,
                            style={"color": styles.TEXT_SECONDARY, "&:hover": {"background": styles.BG_TERTIARY, "color": styles.TEXT_PRIMARY}},
                        ),
                        spacing="1",
                        align="center",
                    ),
                    rx.text("→", size="1", style={"color": styles.TEXT_SECONDARY}),
                    # End time — label tight to controls
                    rx.hstack(
                        rx.text("End", size="1", weight="medium", style={"color": styles.TEXT_SECONDARY}),
                        rx.icon_button(
                            rx.icon("minus", size=12), size="1", variant="ghost",
                            on_click=InferenceState.decrement_video_end,
                            style={"color": styles.TEXT_SECONDARY, "&:hover": {"background": styles.BG_TERTIARY, "color": styles.TEXT_PRIMARY}},
                        ),
                        rx.input(
                            key=InferenceState.video_end_time.to(str),
                            default_value=InferenceState.video_end_time.to(str),
                            on_blur=InferenceState.set_video_end_input,
                            on_key_down=rx.call_script("if (event.key === 'Enter') event.target.blur()"),
                            size="1",
                            style={"width": "52px", "text_align": "center", "color": styles.ACCENT, "font_weight": "bold",
                                   "font_family": styles.FONT_FAMILY_MONO, "background": "transparent",
                                   "border": f"1px solid {styles.BORDER}", "border_radius": styles.RADIUS_SM},
                        ),
                        rx.icon_button(
                            rx.icon("plus", size=12), size="1", variant="ghost",
                            on_click=InferenceState.increment_video_end,
                            style={"color": styles.TEXT_SECONDARY, "&:hover": {"background": styles.BG_TERTIARY, "color": styles.TEXT_PRIMARY}},
                        ),
                        spacing="1",
                        align="center",
                    ),
                    rx.divider(orientation="vertical", style={"height": "16px"}),
                    rx.text("Skip:", size="1", style={"color": styles.TEXT_SECONDARY}),
                    rx.switch(
                        checked=InferenceState.enable_frame_skip,
                        on_change=InferenceState.toggle_frame_skip,
                        size="1",
                    ),
                    rx.cond(
                        InferenceState.enable_frame_skip,
                        rx.hstack(
                            rx.text("/", size="1", style={"color": styles.TEXT_SECONDARY}),
                            rx.input(
                                value=InferenceState.frame_skip_interval.to_string(),
                                on_change=InferenceState.set_frame_skip_interval,
                                type="number",
                                min="2",
                                max="60",
                                size="1",
                                style={
                                    "width": "42px",
                                    "text_align": "center",
                                    "padding": "2px 4px",
                                },
                            ),
                            spacing="1",
                            align="center",
                        ),
                        rx.fragment(),
                    ),
                    spacing="2",
                    align="center",
                    width="100%",
                    padding=styles.SPACING_2,
                    background=styles.BG_PRIMARY,
                    border_radius=styles.RADIUS_SM,
                ),
                rx.fragment(),
            ),
            
            # Hybrid Inference Configuration (shown when classifier is selected)
            rx.cond(
                InferenceState.is_hybrid_mode,
                rx.vstack(
                    # Header with toggle - compact inline style
                    rx.hstack(
                        rx.icon("settings-2", size=12, style={"color": styles.TEXT_SECONDARY}),
                        rx.text("Hybrid Settings", size="1", weight="medium", style={"color": styles.TEXT_SECONDARY}),
                        rx.spacer(),
                        rx.icon_button(
                            rx.icon(
                                rx.cond(InferenceState.show_hybrid_config, "chevron-up", "chevron-down"),
                                size=12,
                            ),
                            size="1",
                            variant="ghost",
                            on_click=InferenceState.toggle_hybrid_config,
                        ),
                        width="100%",
                        align="center",
                    ),
                    
                    # Expandable config
                    rx.cond(
                        InferenceState.show_hybrid_config,
                        rx.vstack(
                            # SAM3 model selector (fine-tuned vs pretrained)
                            rx.hstack(
                                rx.tooltip(
                                    rx.text("SAM3 Model", size="1", style={"color": styles.TEXT_SECONDARY, "white_space": "nowrap", "cursor": "help"}),
                                    content="Select pretrained or fine-tuned SAM3 weights",
                                ),
                                rx.select(
                                    InferenceState.sam3_model_options,
                                    value=InferenceState.selected_sam3_display,
                                    on_change=InferenceState.set_selected_sam3_model,
                                    size="1",
                                    style={"flex": "1"},
                                ),
                                spacing="2",
                                align="center",
                                width="100%",
                            ),
                            
                            # SAM3 prompts input
                            rx.hstack(
                                rx.text("Object Types", size="1", style={"color": styles.TEXT_SECONDARY, "white_space": "nowrap"}),
                                rx.input(
                                    placeholder="animal, bird, mammal",
                                    value=InferenceState.sam3_prompts_input,
                                    on_change=InferenceState.set_sam3_prompts_input,
                                    on_blur=InferenceState.save_sam3_prompts_pref,
                                    size="1",
                                    style={"flex": "1"},
                                ),
                                spacing="2",
                                align="center",
                                width="100%",
                            ),
                            
                            # Classifier confidence stepper
                            numeric_stepper(
                                label="Species Conf.",
                                value=InferenceState.classifier_confidence,
                                on_blur_handler=InferenceState.set_classifier_confidence_input,
                                on_increment=InferenceState.increment_classifier_confidence,
                                on_decrement=InferenceState.decrement_classifier_confidence,
                                display_width="52px",
                            ),
                            
                            # Classify Top-K input
                            rx.hstack(
                                rx.tooltip(
                                    rx.text("Classify K", size="1", style={"color": styles.TEXT_SECONDARY, "white_space": "nowrap", "cursor": "help"}),
                                    content="Number of frames per track for classification voting (1-10)",
                                ),
                                rx.input(
                                    value=InferenceState.classify_top_k.to(str),
                                    type="number",
                                    min="1",
                                    max="10",
                                    on_change=InferenceState.set_classify_top_k,
                                    size="1",
                                    style={"width": "60px"},
                                ),
                                spacing="2",
                                align="center",
                                width="100%",
                            ),
                            
                            # Classifier classes info (compact)
                            rx.hstack(
                                rx.icon("tag", size=10, style={"color": styles.TEXT_SECONDARY}),
                                rx.text(
                                    InferenceState.classifier_classes.length().to_string() + " species in classifier",
                                    size="1", 
                                    style={"color": styles.TEXT_SECONDARY, "font_style": "italic"}
                                ),
                                spacing="1",
                                align="center",
                            ),
                            
                            # Video resize resolution
                            rx.hstack(
                                rx.text("Video Resize", size="1", style={"color": styles.TEXT_SECONDARY, "white_space": "nowrap"}),
                                rx.select(
                                    ["490", "644", "1036", "1288", "1918"],
                                    value=InferenceState.video_target_resolution,
                                    on_change=InferenceState.set_video_target_resolution,
                                    size="1",
                                    style={"flex": "1", "max_width": "100px"},
                                ),
                                rx.text("px", size="1", style={"color": styles.TEXT_SECONDARY}),
                                spacing="2",
                                align="center",
                                width="100%",
                            ),
                            
                            # SAM3 inference resolution
                            rx.hstack(
                                rx.text("SAM3 imgsz", size="1", style={"color": styles.TEXT_SECONDARY, "white_space": "nowrap"}),
                                rx.select(
                                    ["490", "644", "1036", "1288", "1918"],
                                    value=InferenceState.sam3_imgsz,
                                    on_change=InferenceState.set_sam3_imgsz,
                                    size="1",
                                    style={"flex": "1", "max_width": "100px"},
                                ),
                                rx.text("px", size="1", style={"color": styles.TEXT_SECONDARY}),
                                spacing="2",
                                align="center",
                                width="100%",
                            ),
                            
                            # Target FPS
                            rx.hstack(
                                rx.text("Target FPS", size="1", style={"color": styles.TEXT_SECONDARY, "white_space": "nowrap"}),
                                rx.select(
                                    ["original", "30", "15", "10"],
                                    value=InferenceState.video_target_fps,
                                    on_change=InferenceState.set_video_target_fps,
                                    size="1",
                                    style={"flex": "1", "max_width": "100px"},
                                ),
                                spacing="2",
                                align="center",
                                width="100%",
                            ),
                            
                            spacing="2",
                            width="100%",
                        ),
                        rx.fragment(),
                    ),
                    
                    spacing="2",
                    width="100%",
                    padding=styles.SPACING_2,
                    background=styles.BG_PRIMARY,
                    border_radius=styles.RADIUS_SM,
                ),
                rx.fragment(),
            ),
            
            rx.divider(style={"border_color": styles.BORDER}),
            
            # Compute target row (action-level selection)
            rx.hstack(
                rx.text("Run on:", size="1", style={"color": styles.TEXT_SECONDARY}),
                compute_target_toggle(
                    value=InferenceState.compute_target,
                    on_change=InferenceState.set_compute_target,
                    machines=InferenceState.local_machines,
                    selected_machine=InferenceState.selected_machine,
                    on_machine_change=InferenceState.set_selected_machine,
                ),
                spacing="2",
                align="center",
                width="100%",
            ),
            
            rx.divider(style={"border_color": styles.BORDER}),
            
            # Bottom row: Confidence + Actions
            rx.hstack(
                # Confidence stepper
                rx.box(
                    numeric_stepper(
                        label=rx.cond(InferenceState.is_hybrid_mode, "SAM3 Conf", "Confidence"),
                        value=InferenceState.confidence_threshold,
                        on_blur_handler=InferenceState.set_confidence_input,
                        on_increment=InferenceState.increment_confidence,
                        on_decrement=InferenceState.decrement_confidence,
                        display_width="52px",
                    ),
                    min_width="180px",
                    flex="1",
                ),
                
                rx.spacer(),
                
                # Clear button
                rx.icon_button(
                    rx.icon("trash-2", size=14),
                    on_click=InferenceState.clear_results,
                    variant="ghost",
                    size="1",
                    disabled=(InferenceState.uploaded_image_data == "") & (InferenceState.uploaded_video_data == ""),
                ),
                
                # Run button
                rx.button(
                    rx.cond(
                        InferenceState.is_predicting,
                        rx.hstack(rx.spinner(size="1"), rx.text("Running..."), spacing="2"),
                        rx.cond(
                            InferenceState.batch_mode,
                            rx.hstack(rx.icon("zap", size=14), rx.text("Run Batch"), spacing="2"),
                            rx.hstack(rx.icon("zap", size=14), rx.text("Run"), spacing="2"),
                        ),
                    ),
                    on_click=InferenceState.run_inference,
                    # Disabled if: no content uploaded AND not in batch mode, OR already predicting
                    disabled=(
                        ((InferenceState.uploaded_image_data == "") & (InferenceState.uploaded_video_data == "") & ~InferenceState.batch_mode)
                        | (InferenceState.batch_mode & (InferenceState.uploaded_images.length() == 0))
                        | InferenceState.is_predicting
                    ),
                    size="2",
                    style={"background": styles.ACCENT, "color": "white"},
                ),
                
                spacing="3",
                width="100%",
                align="center",
            ),
            
            # Inference progress - stage-based for images, frame-based for videos
            rx.cond(
                InferenceState.is_predicting,
                rx.cond(
                    InferenceState.is_polling_inference,
                    # Video: frame-based progress
                    rx.hstack(
                        rx.spinner(size="1"),
                        rx.text(
                            InferenceState.inference_progress_status,
                            size="1",
                            style={"color": styles.TEXT_SECONDARY}
                        ),
                        rx.progress(
                            value=InferenceState.inference_progress_current,
                            max=InferenceState.inference_progress_total,
                            style={"flex": "1"},
                            color_scheme="green",
                        ),
                        spacing="2",
                        align="center",
                        width="100%",
                        padding=styles.SPACING_2,
                        background=styles.BG_PRIMARY,
                        border_radius=styles.RADIUS_SM,
                    ),
                    # Image: stage-based progress
                    rx.hstack(
                        rx.spinner(size="1"),
                        rx.match(
                            InferenceState.inference_stage,
                            ("initializing", rx.text("Initializing...", size="1", style={"color": styles.TEXT_SECONDARY})),
                            ("loading_model", rx.text("Loading model...", size="1", style={"color": styles.TEXT_SECONDARY})),
                            ("processing", rx.text("Processing image...", size="1", style={"color": styles.TEXT_SECONDARY})),
                            ("saving", rx.text("Saving results...", size="1", style={"color": styles.TEXT_SECONDARY})),
                            rx.text("Processing...", size="1", style={"color": styles.TEXT_SECONDARY}),
                        ),
                        rx.box(
                            rx.progress(
                                value=None,  # Indeterminate progress
                                style={"flex": "1"},
                                color_scheme="green",
                            ),
                            flex="1",
                        ),
                        spacing="2",
                        align="center",
                        width="100%",
                        padding=styles.SPACING_2,
                        background=styles.BG_PRIMARY,
                        border_radius=styles.RADIUS_SM,
                    ),
                ),
                rx.fragment(),
            ),
            
            spacing="3",
            width="100%",
        ),
        padding=styles.SPACING_4,
        background=styles.BG_SECONDARY,
        border_radius=styles.RADIUS_LG,
        border=f"1px solid {styles.BORDER}",
    )







# =============================================================================
# Results Section
# =============================================================================

def results_section() -> rx.Component:
    """Collapsible recent results section."""
    return rx.box(
        rx.vstack(
            # Header
            rx.hstack(
                rx.hstack(
                    rx.icon("history", size=16, style={"color": styles.ACCENT}),
                    rx.text("Recent Results", size="3", weight="medium", style={"color": styles.TEXT_PRIMARY}),
                    rx.cond(
                        InferenceState.inference_results.length() > 0,
                        rx.badge(
                            InferenceState.inference_results.length().to_string(),
                            color_scheme="green",
                            variant="outline",
                            size="1",
                        ),
                        rx.fragment(),
                    ),
                    spacing="2",
                    align="center",
                ),
                rx.spacer(),
                rx.icon(
                    rx.cond(InferenceState.is_results_expanded, "chevron-up", "chevron-down"),
                    size=16,
                    style={"color": styles.TEXT_SECONDARY}
                ),
                width="100%",
                align="center",
                cursor="pointer",
                on_click=InferenceState.toggle_results_expanded,
            ),
            
            # Results grid
            rx.cond(
                InferenceState.is_results_expanded,
                rx.cond(
                    InferenceState.inference_results.length() > 0,
                    rx.box(
                        rx.foreach(InferenceState.inference_results, result_card),
                        width="100%",
                        style={
                            "display": "grid",
                            "grid_template_columns": "repeat(auto-fill, minmax(280px, 1fr))",
                            "gap": styles.SPACING_2,
                            "max_height": "520px",
                            "overflow_y": "auto",
                            "padding_top": styles.SPACING_3,
                        },
                    ),
                    rx.center(
                        rx.vstack(
                            rx.icon("folder-open", size=20, style={"color": styles.TEXT_SECONDARY, "opacity": "0.4"}),
                            rx.text("No results yet", size="2", style={"color": styles.TEXT_SECONDARY}),
                            spacing="1",
                            align="center",
                        ),
                        padding=styles.SPACING_4,
                    ),
                ),
                rx.fragment(),
            ),
            
            spacing="2",
            width="100%",
        ),
        padding=styles.SPACING_4,
        background=styles.BG_SECONDARY,
        border_radius=styles.RADIUS_LG,
        border=f"1px solid {styles.BORDER}",
        min_height="600px",  # Match inference card height
    )


# =============================================================================
# Classification Crops Gallery (K candidate crops)
# =============================================================================

def classification_crops_gallery() -> rx.Component:
    """Gallery of K candidate crop thumbnails with class badges."""
    return rx.cond(
        InferenceState.classification_crop_urls.length() > 0,
        rx.box(
            rx.hstack(
                rx.icon("scan-search", size=14, style={"color": styles.TEXT_SECONDARY}),
                rx.text("Classification Crops", size="1", style={"color": styles.TEXT_SECONDARY}),
                spacing="1",
                align="center",
            ),
            rx.box(
                rx.hstack(
                    rx.foreach(
                        InferenceState.classification_crop_urls,
                        lambda crop: rx.box(
                            rx.image(
                                src=crop["url"],
                                height="100px",
                                width="auto",
                                object_fit="contain",
                                border_radius=styles.RADIUS_SM,
                            ),
                            rx.hstack(
                                rx.badge(
                                    crop["class_name"],
                                    color_scheme=rx.cond(
                                        crop["class_name"].to(str) == "Unknown",
                                        "gray",
                                        "green",
                                    ),
                                    size="1",
                                    variant="outline",
                                ),
                                rx.text(
                                    round(crop["confidence"].to(float) * 100).to(str) + "%",
                                    size="1",
                                    style={"color": styles.ACCENT},
                                ),
                                spacing="1",
                                align="center",
                                margin_top="2px",
                            ),
                            display="flex",
                            flex_direction="column",
                            align_items="center",
                            min_width="80px",
                        ),
                    ),
                    spacing="3",
                    flex_wrap="wrap",
                    padding_y=styles.SPACING_2,
                ),
                width="100%",
            ),
            padding=styles.SPACING_3,
            border_radius=styles.RADIUS_MD,
            background=styles.CARD_BG,
            border=f"1px solid {styles.BORDER}",
            margin_top=styles.SPACING_3,
            width="100%",
        ),
        rx.fragment(),
    )


# =============================================================================
# Preview Modal (In-place result viewer)
# =============================================================================

def preview_modal() -> rx.Component:
    """Modal for previewing inference results in-place."""
    return rx.dialog.root(
        rx.dialog.content(
            rx.vstack(
                # Header
                rx.hstack(
                    rx.hstack(
                        rx.icon(
                            rx.match(
                                InferenceState.preview_input_type,
                                ("batch", "images"),
                                ("video", "video"),
                                "image",
                            ),
                            size=18,
                            style={"color": styles.ACCENT}
                        ),
                        rx.text(
                            InferenceState.preview_filename,
                            size="3",
                            weight="medium",
                            style={"color": styles.TEXT_PRIMARY},
                        ),
                        spacing="2",
                        align="center",
                    ),
                    rx.spacer(),
                    rx.hstack(
                        rx.badge(
                            InferenceState.preview_model_name,
                            color_scheme="green",
                            variant="outline",
                        ),
                        rx.badge(
                            f"{InferenceState.preview_detection_count} detections",
                            color_scheme="green",
                            variant="outline",
                        ),
                        # Mask toggle (show for images/batch/videos with masks)
                        rx.cond(
                            (InferenceState.preview_masks_css.length() > 0) | 
                            (InferenceState.preview_batch_current_masks_css.length() > 0) |
                            ((InferenceState.preview_input_type == "video") & (InferenceState.preview_masks_by_frame.length() > 0)),
                            rx.tooltip(
                                rx.icon_button(
                                    rx.icon(
                                        rx.cond(InferenceState.show_masks_preview, "eye", "eye-off"),
                                        size=14,
                                    ),
                                    size="1",
                                    variant=rx.cond(InferenceState.show_masks_preview, "soft", "ghost"),
                                    color_scheme="green",
                                    on_click=InferenceState.toggle_mask_visibility,
                                ),
                                content=rx.cond(InferenceState.show_masks_preview, "Hide Masks", "Show Masks"),
                            ),
                            rx.fragment(),
                        ),
                        spacing="2",
                    ),
                    rx.icon_button(
                        rx.icon("x", size=16),
                        size="1",
                        variant="ghost",
                        on_click=InferenceState.close_preview,
                    ),
                    width="100%",
                    align="center",
                ),
                
                rx.divider(style={"border_color": styles.BORDER}),
                
                # Preview content - image, video, or batch
                rx.match(
                    InferenceState.preview_input_type,
                    # Single image preview
                    ("image", rx.center(
                        rx.box(
                            rx.image(
                                src=InferenceState.preview_input_url,
                                style={
                                    "max_width": "100%",
                                    "max_height": "50vh",
                                    "width": "auto",
                                    "height": "auto",
                                    "display": "block",
                                },
                                border_radius=styles.RADIUS_MD,
                                id="inference-preview-image",
                            ),
                            # Render segmentation masks as CSS clip-path overlays
                            rx.cond(
                                InferenceState.show_masks_preview & (InferenceState.preview_masks_css.length() > 0),
                                mask_overlays(InferenceState.preview_masks_css),
                                rx.fragment(),
                            ),
                            # Render bounding boxes as CSS overlays
                            rx.foreach(
                                InferenceState.preview_predictions,
                                lambda pred: rx.box(
                                    rx.text(
                                        pred["class_name"].to(str) + " " + round(pred["confidence"].to(float) * 100).to(str) + "%",
                                        size="1",
                                        style={
                                            "color": "#000",
                                            "background": "rgba(0, 255, 0, 0.85)",
                                            "padding": "1px 4px",
                                            "font_size": "10px",
                                            "white_space": "nowrap",
                                            "position": "absolute",
                                            "top": "-16px",
                                            "left": "0",
                                        },
                                    ),
                                    style={
                                        "position": "absolute",
                                        "left": (pred["box"][0].to(float) * 100).to(str) + "%",
                                        "top": (pred["box"][1].to(float) * 100).to(str) + "%",
                                        "width": ((pred["box"][2].to(float) - pred["box"][0].to(float)) * 100).to(str) + "%",
                                        "height": ((pred["box"][3].to(float) - pred["box"][1].to(float)) * 100).to(str) + "%",
                                        "border": "2px solid #00ff00",
                                        "pointer_events": "none",
                                    },
                                ),
                            ),
                            position="relative",
                            display="inline-block",
                        ),
                        width="100%",
                    )),
                    # Video preview
                    ("video", rx.center(
                        rx.box(
                            rx.el.video(
                                id="inference-video",
                                src=InferenceState.preview_input_url,
                                controls=True,
                                style={
                                    "width": "100%",
                                    "max_height": "400px",
                                    "display": "block",
                                    "border_radius": styles.RADIUS_MD,
                                },
                                preload="auto",
                                muted=True,
                                playsinline=True,
                            ),
                            rx.el.canvas(
                                id="inference-canvas",
                                style={
                                    "position": "absolute",
                                    "top": "0",
                                    "left": "0",
                                    "width": "100%",
                                    "height": "100%",
                                    "pointer_events": "none",
                                    "z_index": "10",
                                },
                            ),
                            position="relative",
                            width="100%",
                        ),
                    )),
                    # Batch preview with navigation
                    ("batch", rx.vstack(
                        # Navigation header
                        rx.hstack(
                            rx.icon_button(
                                rx.icon("chevron-left", size=18),
                                size="2",
                                variant="ghost",
                                on_click=InferenceState.batch_preview_prev,
                                disabled=InferenceState.preview_batch_index == 0,
                            ),
                            rx.text(
                                (InferenceState.preview_batch_index + 1).to(str) + " / " + InferenceState.preview_batch_count.to(str),
                                size="2",
                                weight="medium",
                                style={"color": styles.TEXT_SECONDARY, "min_width": "50px", "text_align": "center"},
                            ),
                            rx.icon_button(
                                rx.icon("chevron-right", size=18),
                                size="2",
                                variant="ghost",
                                on_click=InferenceState.batch_preview_next,
                                disabled=InferenceState.preview_batch_index >= InferenceState.preview_batch_count - 1,
                            ),
                            rx.spacer(),
                            rx.text(
                                InferenceState.preview_batch_current_filename,
                                size="1",
                                style={"color": styles.TEXT_SECONDARY, "max_width": "200px", "overflow": "hidden", "text_overflow": "ellipsis"},
                            ),
                            width="100%",
                            align="center",
                            padding_x=styles.SPACING_2,
                        ),
                        # Image display
                        rx.center(
                            rx.box(
                                rx.image(
                                    src=InferenceState.preview_batch_current_url,
                                    style={
                                        "max_width": "100%",
                                        "max_height": "45vh",
                                        "width": "auto",
                                        "height": "auto",
                                        "display": "block",
                                    },
                                    border_radius=styles.RADIUS_MD,
                                ),
                                # Segmentation masks for current batch image
                                rx.cond(
                                    InferenceState.show_masks_preview & (InferenceState.preview_batch_current_masks_css.length() > 0),
                                    mask_overlays(InferenceState.preview_batch_current_masks_css),
                                    rx.fragment(),
                                ),
                                # Bounding boxes for current batch image
                                rx.foreach(
                                    InferenceState.preview_batch_current_predictions,
                                    lambda pred: rx.box(
                                        rx.text(
                                            pred["class_name"].to(str) + " " + round(pred["confidence"].to(float) * 100).to(str) + "%",
                                            size="1",
                                            style={
                                                "color": "#000",
                                                "background": "rgba(0, 255, 0, 0.85)",
                                                "padding": "1px 4px",
                                                "font_size": "10px",
                                                "white_space": "nowrap",
                                                "position": "absolute",
                                                "top": "-16px",
                                                "left": "0",
                                            },
                                        ),
                                        style={
                                            "position": "absolute",
                                            "left": (pred["box"][0].to(float) * 100).to(str) + "%",
                                            "top": (pred["box"][1].to(float) * 100).to(str) + "%",
                                            "width": ((pred["box"][2].to(float) - pred["box"][0].to(float)) * 100).to(str) + "%",
                                            "height": ((pred["box"][3].to(float) - pred["box"][1].to(float)) * 100).to(str) + "%",
                                            "border": "2px solid #00ff00",
                                            "pointer_events": "none",
                                        },
                                    ),
                                ),
                                position="relative",
                                display="inline-block",
                            ),
                            width="100%",
                        ),
                        spacing="2",
                        width="100%",
                    )),
                    # Default fallback
                    rx.text("Unsupported preview type", style={"color": styles.TEXT_SECONDARY}),
                ),
                
                # Classification crops gallery (K candidate crops)
                classification_crops_gallery(),
                
                # Detection list (scrollable)
                rx.cond(
                    InferenceState.preview_predictions.length() > 0,
                    rx.box(
                        rx.vstack(
                            rx.text("Detections", size="2", weight="medium", style={"color": styles.TEXT_SECONDARY}),
                            rx.foreach(
                                InferenceState.preview_predictions[:10],  # Show first 10
                                lambda pred: rx.hstack(
                                    rx.badge(pred["class_name"], color_scheme="gray", size="1"),
                                    rx.text(round(pred["confidence"].to(float) * 100).to(str) + "%", size="1", style={"color": styles.ACCENT}),
                                    spacing="2",
                                ),
                            ),
                            rx.cond(
                                InferenceState.preview_predictions.length() > 10,
                                rx.text(
                                    f"+ {InferenceState.preview_predictions.length() - 10} more",
                                    size="1",
                                    style={"color": styles.TEXT_SECONDARY}
                                ),
                                rx.fragment(),
                            ),
                            spacing="1",
                            align_items="start",
                        ),
                        padding=styles.SPACING_3,
                        background=styles.BG_PRIMARY,
                        border_radius=styles.RADIUS_MD,
                        max_height="150px",
                        overflow_y="auto",
                        width="100%",
                    ),
                    rx.fragment(),
                ),
                
                # Actions
                rx.hstack(
                    rx.spacer(),
                    # Open Full View - close modal and navigate
                    rx.link(
                        rx.button(
                            rx.hstack(rx.icon("external-link", size=14), rx.text("Open Full View"), spacing="2"),
                            variant="outline",
                            size="2",
                            on_click=InferenceState.close_preview,  # Cleanup before navigating
                        ),
                        href=f"/inference/result/{InferenceState.preview_result_id}",
                    ),
                    rx.button(
                        "Close",
                        on_click=InferenceState.close_preview,  # Now includes JS cleanup
                        size="2",
                    ),
                    spacing="2",
                    width="100%",
                ),
                
                spacing="4",
                width="100%",
            ),
            style={
                "background": styles.BG_SECONDARY,
                "border": f"1px solid {styles.BORDER}",
                "border_radius": styles.RADIUS_LG,
                "padding": styles.SPACING_6,
                "max_width": "700px",
                "width": "90vw",
            },
        ),
        open=InferenceState.is_preview_open,
        on_open_change=lambda open: InferenceState.set_preview_open(open),
    )


# =============================================================================
# Main Page
# =============================================================================

@rx.page(route="/playground", on_load=InferenceState.load_models)
def playground() -> rx.Component:
    """Inference playground page - compact elegant layout."""
    return rx.box(
        rx.vstack(
            # Header
            rx.hstack(
                rx.hstack(
                    rx.icon("zap", size=24, style={"color": styles.ACCENT}),
                    rx.heading("Inference Playground", size="6", style={"color": styles.TEXT_PRIMARY}),
                    spacing="2",
                    align="center",
                ),
                rx.spacer(),
                rx.link(
                    rx.button(
                        rx.hstack(rx.icon("arrow-left", size=14), rx.text("Dashboard"), spacing="2"),
                        variant="ghost",
                        size="1",
                    ),
                    href="/dashboard",
                ),
                width="100%",
                align="center",
            ),
            
            # Main content - two column on large screens
            rx.box(
                rx.hstack(
                    # Left: Inference card + debug crop
                    rx.box(
                        inference_card(),
                        flex="1",
                        min_width="320px",
                    ),
                    
                    # Right: Results
                    rx.box(
                        results_section(),
                        flex="1",
                        min_width="320px",
                    ),
                    
                    spacing="4",
                    width="100%",
                    align_items="start",
                    flex_wrap="wrap",
                ),
                width="100%",
            ),
            
            spacing="4",
            width="100%",
            max_width="1100px",
            margin="0 auto",
            padding=styles.SPACING_6,
        ),
        
        # Preview modal
        preview_modal(),
        
        width="100%",
        min_height="100vh",
        style={"background": styles.BG_PRIMARY},
    )
