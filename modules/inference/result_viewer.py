"""
Inference Result Viewer — View a saved inference result (image or video).

Route: /inference/result/{result_id}

Handles both image and video result types with appropriate viewers.
"""

import reflex as rx
import styles
from app_state import require_auth
from modules.inference.state import InferenceState
from modules.inference.video_player import inference_video_player
from modules.inference.playground import mask_overlays, classification_crops_gallery


def batch_result_viewer() -> rx.Component:
    """Batch result viewer with image navigation and overlays."""
    return rx.vstack(
        # Hidden trigger inputs for keyboard navigation (A/D keys)
        rx.input(
            id="batch-fullview-next-trigger",
            on_change=InferenceState.batch_preview_next_trigger,
            type="text",
            style={"position": "absolute", "opacity": "0", "height": "0", "width": "0", "pointer_events": "none", "z_index": "-1"},
        ),
        rx.input(
            id="batch-fullview-prev-trigger",
            on_change=InferenceState.batch_preview_prev_trigger,
            type="text",
            style={"position": "absolute", "opacity": "0", "height": "0", "width": "0", "pointer_events": "none", "z_index": "-1"},
        ),
        # Navigation header
        rx.hstack(
            rx.icon_button(
                rx.icon("chevron-left", size=20),
                size="2",
                variant="ghost",
                on_click=InferenceState.batch_preview_prev,
                disabled=InferenceState.preview_batch_index == 0,
            ),
            rx.text(
                (InferenceState.preview_batch_index + 1).to(str) + " / " + InferenceState.preview_batch_count.to(str),
                size="3",
                weight="medium",
                style={"color": styles.TEXT_SECONDARY, "min_width": "60px", "text_align": "center"},
            ),
            rx.icon_button(
                rx.icon("chevron-right", size=20),
                size="2",
                variant="ghost",
                on_click=InferenceState.batch_preview_next,
                disabled=InferenceState.preview_batch_index >= InferenceState.preview_batch_count - 1,
            ),
            rx.spacer(),
            rx.text(
                InferenceState.preview_batch_current_filename,
                size="2",
                style={"color": styles.TEXT_SECONDARY},
            ),
            width="100%",
            align="center",
            justify="center",
            padding=styles.SPACING_2,
        ),
        # Image display with overlays
        rx.center(
            rx.box(
                rx.image(
                    src=InferenceState.preview_batch_current_url,
                    style={
                        "max_width": "100%",
                        "max_height": "70vh",
                        "width": "auto",
                        "height": "auto",
                        "display": "block",
                    },
                    border_radius=styles.RADIUS_MD,
                ),
                # Segmentation masks
                rx.cond(
                    InferenceState.show_masks_fullview & (InferenceState.preview_batch_current_masks_css.length() > 0),
                    mask_overlays(InferenceState.preview_batch_current_masks_css),
                    rx.fragment(),
                ),
                # Bounding boxes
                rx.foreach(
                    InferenceState.preview_batch_current_predictions,
                    lambda pred: rx.box(
                        rx.text(
                            pred["class_name"].to(str) + " " + (pred["confidence"].to(float) * 100).to(int).to(str) + "%",
                            size="1",
                            style={
                                "color": "#000",
                                "background": "rgba(0, 255, 0, 0.85)",
                                "padding": "2px 6px",
                                "font_size": "12px",
                                "white_space": "nowrap",
                                "position": "absolute",
                                "top": "-20px",
                                "left": "0",
                            },
                        ),
                        style={
                            "position": "absolute",
                            "left": (pred["box"][0].to(float) * 100).to(str) + "%",
                            "top": (pred["box"][1].to(float) * 100).to(str) + "%",
                            "width": ((pred["box"][2].to(float) - pred["box"][0].to(float)) * 100).to(str) + "%",
                            "height": ((pred["box"][3].to(float) - pred["box"][1].to(float)) * 100).to(str) + "%",
                            "border": "3px solid #00ff00",
                            "pointer_events": "none",
                        },
                    ),
                ),
                position="relative",
                display="inline-block",
            ),
            width="100%",
            padding=styles.SPACING_4,
        ),
        # Install keyboard listener on mount
        on_mount=rx.call_script(
            """
            window._batchFullviewKeyHandler = function(e) {
                var triggerId = null;
                if (e.key === 'd' || e.key === 'ArrowRight') triggerId = 'batch-fullview-next-trigger';
                else if (e.key === 'a' || e.key === 'ArrowLeft') triggerId = 'batch-fullview-prev-trigger';
                if (triggerId) {
                    e.preventDefault();
                    var inp = document.getElementById(triggerId);
                    if (inp) {
                        var nativeInputValueSetter = Object.getOwnPropertyDescriptor(window.HTMLInputElement.prototype, 'value').set;
                        nativeInputValueSetter.call(inp, Date.now().toString());
                        inp.dispatchEvent(new Event('input', { bubbles: true }));
                        inp.dispatchEvent(new Event('change', { bubbles: true }));
                    }
                }
            };
            document.addEventListener('keydown', window._batchFullviewKeyHandler);
            """
        ),
        on_unmount=rx.call_script(
            "if (window._batchFullviewKeyHandler) { document.removeEventListener('keydown', window._batchFullviewKeyHandler); window._batchFullviewKeyHandler = null; }"
        ),
        spacing="2",
        width="100%",
    )


def image_result_viewer() -> rx.Component:
    """Image result viewer with bounding box and mask overlays."""
    return rx.center(
        rx.box(
            rx.image(
                src=InferenceState.current_result_image_url,
                style={
                    "max_width": "100%",
                    "max_height": "70vh",  # Scale to fit viewport
                    "width": "auto",
                    "height": "auto",
                    "display": "block",
                },
                border_radius=styles.RADIUS_MD,
            ),
            # Render segmentation masks as CSS clip-path overlays (same approach as boxes)
            rx.cond(
                InferenceState.show_masks_fullview & (InferenceState.fullview_masks_css.length() > 0),
                mask_overlays(InferenceState.fullview_masks_css),
                rx.fragment(),
            ),
            # Render bounding boxes as CSS overlays
            rx.foreach(
                InferenceState.current_result_predictions,
                lambda pred: rx.box(
                    rx.text(
                        pred["class_name"].to(str) + " " + (pred["confidence"].to(float) * 100).to(int).to(str) + "%",
                        size="1",
                        style={
                            "color": "#000",
                            "background": "rgba(0, 255, 0, 0.85)",
                            "padding": "2px 6px",
                            "font_size": "12px",
                            "white_space": "nowrap",
                            "position": "absolute",
                            "top": "-20px",
                            "left": "0",
                        },
                    ),
                    style={
                        "position": "absolute",
                        # box format: [x1, y1, x2, y2] - all normalized 0-1
                        "left": (pred["box"][0].to(float) * 100).to(str) + "%",
                        "top": (pred["box"][1].to(float) * 100).to(str) + "%",
                        "width": ((pred["box"][2].to(float) - pred["box"][0].to(float)) * 100).to(str) + "%",
                        "height": ((pred["box"][3].to(float) - pred["box"][1].to(float)) * 100).to(str) + "%",
                        "border": "3px solid #00ff00",
                        "pointer_events": "none",
                    },
                ),
            ),
            position="relative",
            display="inline-block",  # Shrink to fit image
        ),
        width="100%",
        padding=styles.SPACING_4,
    )


@rx.page(route="/inference/result/[result_id]", on_load=InferenceState.load_inference_result)
def result_viewer() -> rx.Component:
    """View an inference result - supports both image and video."""
    
    # Apply auth wrapper to the content
    content = rx.box(
        # Header
        rx.hstack(
            rx.icon_button(
                rx.icon("arrow-left", size=18),
                variant="ghost",
                size="2",
                on_click=rx.redirect("/playground"),
                style={
                    "color": styles.TEXT_SECONDARY,
                    "&:hover": {"background": styles.BG_TERTIARY},
                }
            ),
            rx.heading(
                "Inference Result",
                size="6",
                style={"color": styles.TEXT_PRIMARY}
            ),
            rx.spacer(),
            # Mask toggle (show for images with masks OR videos with masks)
            rx.cond(
                ((InferenceState.current_result_input_type == "image") & (InferenceState.fullview_masks_css.length() > 0)) | 
                ((InferenceState.current_result_input_type == "video") & (InferenceState.masks_by_frame.length() > 0)),
                rx.tooltip(
                    rx.icon_button(
                        rx.icon(
                            rx.cond(InferenceState.show_masks_fullview, "eye", "eye-off"),
                            size=16,
                        ),
                        size="2",
                        variant=rx.cond(InferenceState.show_masks_fullview, "soft", "ghost"),
                        color_scheme="green",
                        on_click=InferenceState.toggle_fullview_mask_visibility,
                    ),
                    content=rx.cond(InferenceState.show_masks_fullview, "Hide Masks", "Show Masks"),
                ),
                rx.fragment(),
            ),
            rx.cond(
                InferenceState.prediction_error != "",
                rx.text(
                    InferenceState.prediction_error,
                    size="2",
                    style={"color": styles.ERROR}
                ),
                rx.fragment(),
            ),
            width="100%",
            align="center",
            padding=styles.SPACING_4,
            border_bottom=f"1px solid {styles.BORDER}",
        ),
        
        # Conditional content based on input type
        rx.center(
            rx.box(
                rx.match(
                    InferenceState.current_result_input_type,
                    ("video", inference_video_player()),
                    ("image", image_result_viewer()),
                    ("batch", batch_result_viewer()),
                    rx.center(
                        rx.text("Loading result...", size="2", style={"color": styles.TEXT_SECONDARY}),
                        padding=styles.SPACING_6,
                    ),
                ),
                width="100%",
                max_width="1280px",
            ),
            width="100%",
            padding=styles.SPACING_4,
        ),
        
        # Classification crops gallery (K candidate crops)
        rx.center(
            rx.box(
                classification_crops_gallery(),
                width="100%",
                max_width="1280px",
            ),
            width="100%",
            padding_x=styles.SPACING_4,
        ),
        
        # Metadata panel
        rx.center(
            rx.box(
                rx.vstack(
                    rx.heading("Result Metadata", size="4", style={"color": styles.TEXT_PRIMARY}),
                    rx.divider(style={"border_color": styles.BORDER}),
                    
                    rx.hstack(
                        rx.text("Type:", size="2", weight="medium", style={"color": styles.TEXT_SECONDARY}),
                        rx.badge(
                            InferenceState.current_result_input_type,
                            color_scheme="green",
                            variant="outline",
                        ),
                        spacing="2",
                    ),
                    
                    rx.hstack(
                        rx.text("Model:", size="2", weight="medium", style={"color": styles.TEXT_SECONDARY}),
                        rx.text(InferenceState.current_result_model_name, size="2", style={"color": styles.TEXT_PRIMARY}),
                        spacing="2",
                    ),
                    
                    rx.hstack(
                        rx.text("Confidence Threshold:", size="2", weight="medium", style={"color": styles.TEXT_SECONDARY}),
                        rx.text(f"{InferenceState.current_result_confidence:.2f}", size="2", style={"color": styles.TEXT_PRIMARY}),
                        spacing="2",
                    ),
                    
                    # Show detection count for images
                    rx.cond(
                        InferenceState.current_result_input_type == "image",
                        rx.hstack(
                            rx.text("Detections:", size="2", weight="medium", style={"color": styles.TEXT_SECONDARY}),
                            rx.text(InferenceState.current_result_predictions.length(), size="2", style={"color": styles.TEXT_PRIMARY}),
                            spacing="2",
                        ),
                        rx.hstack(
                            rx.text("Frames with Labels:", size="2", weight="medium", style={"color": styles.TEXT_SECONDARY}),
                            rx.text(InferenceState.labels_by_frame.length(), size="2", style={"color": styles.TEXT_PRIMARY}),
                            spacing="2",
                        ),
                    ),
                    
                    spacing="3",
                    width="100%",
                ),
                width="100%",
                max_width="1280px",
                padding=styles.SPACING_4,
                background=styles.BG_SECONDARY,
                border_radius=styles.RADIUS_MD,
                border=f"1px solid {styles.BORDER}",
            ),
            width="100%",
            padding=styles.SPACING_4,
        ),
        
        width="100%",
        min_height="100vh",
        background=styles.BG_PRIMARY,
    )
    
    return require_auth(content)


