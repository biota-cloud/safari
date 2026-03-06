"""Labeling Editor Page — Canvas-based annotation interface.

Route: /projects/[project_id]/datasets/[dataset_id]/label
Layout: 3-panel (thumbnails | canvas | tools)
"""

import reflex as rx
import styles
from app_state import require_auth, AuthState
from modules.labeling.state import LabelingState, ImageModel
from modules.labeling.tools import Toolbar
from components.nav_header import nav_header
from components.context_menu import annotation_context_menu
from components.compute_target_toggle import compute_target_toggle


# Canvas JavaScript is loaded from /assets/canvas.js



# =============================================================================
# LEFT SIDEBAR — Image Thumbnails
# =============================================================================

def image_thumbnail_item(image: ImageModel) -> rx.Component:
    """Single thumbnail in the sidebar list with image stats and multi-selection support."""
    
    # Check if this image is in the selected list
    is_selected = LabelingState.selected_image_ids.contains(image.id)
    is_current = LabelingState.current_image_id == image.id
    
    return rx.hstack(
        # Thumbnail image (fixed size)
        rx.box(
            rx.image(
                src=image.thumbnail_url,
                width="50px",
                height="50px",
                object_fit="cover",
                loading="lazy",
                border_radius=styles.RADIUS_SM,
            ),
            # Selection checkbox indicator
            rx.cond(
                is_selected,
                rx.box(
                    rx.icon("check", size=12, color="white"),
                    style={
                        "position": "absolute",
                        "top": "2px",
                        "left": "2px",
                        "width": "16px",
                        "height": "16px",
                        "background": styles.ACCENT,
                        "border_radius": "50%",
                        "display": "flex",
                        "align_items": "center",
                        "justify_content": "center",
                    }
                ),
                rx.fragment(),
            ),
            position="relative",
            flex_shrink="0",
        ),
        # Image info
        rx.vstack(
            # Filename (truncated from start, tooltip shows full name)
            rx.tooltip(
                rx.text(
                    image.filename,
                    size="1",
                    weight="medium",
                    style={
                        "color": styles.TEXT_PRIMARY,
                        "white_space": "nowrap",
                        "overflow": "hidden",
                        "text_overflow": "ellipsis",
                        "max_width": "120px",
                        "direction": "rtl",  # Truncates from start, shows end
                        "text_align": "left",
                    },
                ),
                content=image.filename,
            ),
            # Annotation count row
            rx.hstack(
                rx.cond(
                    image.labeled,
                    rx.hstack(
                        rx.icon("circle-check", size=10, color=styles.SUCCESS),
                        rx.text(
                            image.annotation_count,
                            size="1",
                            style={"color": styles.SUCCESS},
                        ),
                        rx.text(
                            " labels",
                            size="1",
                            style={"color": styles.TEXT_SECONDARY},
                        ),
                        spacing="1",
                        align="center",
                    ),
                    rx.text(
                        "No labels",
                        size="1",
                        style={"color": styles.TEXT_SECONDARY, "opacity": "0.7"},
                    ),
                ),
                spacing="1",
                align="center",
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
        border_radius=styles.RADIUS_SM,
        border=rx.cond(
            is_selected,
            f"2px solid {styles.SUCCESS}",
            rx.cond(
                is_current,
                f"2px solid {styles.ACCENT}",
                f"1px solid {styles.BORDER}",
            ),
        ),
        background=rx.cond(
            is_selected,
            f"{styles.SUCCESS}15",  # Light green tint for selection
            rx.cond(
                is_current,
                styles.BG_TERTIARY,
                "transparent",
            ),
        ),
        cursor="pointer",
        # Normal click navigates/views the image
        on_click=lambda: LabelingState.select_image(image.id),
        # Long press toggles selection (handled via JS custom event)
        custom_attrs={"data-image-id": image.id},
        id=f"img-thumb-{image.id}",
        _hover={
            "border_color": rx.cond(is_selected, styles.SUCCESS, styles.ACCENT),
            "background": rx.cond(is_selected, f"{styles.SUCCESS}20", styles.BG_TERTIARY),
        },
        transition=styles.TRANSITION_FAST,
    )



def left_sidebar() -> rx.Component:
    """Left sidebar with image thumbnails and progress bar."""
    # Selection handler logic is loaded globally in safari.py
    
    return rx.box(
        rx.vstack(
            # Hidden buttons for JS event bridge
            rx.el.button(
                id="longpress-trigger",
                on_click=rx.call_script(
                    "window._longpressImageId || ''",
                    callback=LabelingState.toggle_image_selection_by_id,
                ),
                style={"display": "none"},
            ),
            rx.el.button(
                id="range-select-trigger",
                on_click=rx.call_script(
                    "window._rangeSelectImageId || ''",
                    callback=LabelingState.range_select_image_by_id,
                ),
                style={"display": "none"},
            ),
            # Header with title and position
            rx.hstack(
                rx.text(
                    "Images",
                    size="2",
                    weight="medium",
                    style={"color": styles.TEXT_PRIMARY}
                ),
                rx.icon_button(
                    rx.icon("bar-chart-2", size=14),
                    size="1",
                    variant="ghost",
                    on_click=LabelingState.open_empty_stats_modal,
                    title="View dataset statistics",
                ),
                rx.spacer(),
                rx.text(
                    f"{LabelingState.current_image_index}/{LabelingState.image_count}",
                    size="1",
                    style={"color": styles.TEXT_SECONDARY}
                ),
                width="100%",
                align="center",
            ),
            # Progress bar showing labeled/total
            rx.vstack(
                rx.hstack(
                    rx.text(
                        f"{LabelingState.labeled_count} of {LabelingState.image_count} labeled",
                        size="1",
                        style={"color": styles.TEXT_SECONDARY}
                    ),
                    rx.spacer(),
                    rx.cond(
                        LabelingState.image_count > 0,
                        rx.text(
                            f"{(LabelingState.labeled_count * 100 / LabelingState.image_count).to(int)}%",
                            size="1",
                            weight="medium",
                            style={"color": styles.ACCENT}
                        ),
                        rx.fragment(),
                    ),
                    width="100%",
                    align="center",
                ),
                rx.progress(
                    value=rx.cond(
                        LabelingState.image_count > 0,
                        (LabelingState.labeled_count * 100 / LabelingState.image_count).to(int),
                        0
                    ),
                    size="1",
                    color_scheme="green",
                    width="100%",
                ),
                spacing="1",
                width="100%",
            ),
            # Selection action bar (shown when images are selected)
            rx.cond(
                LabelingState.has_image_selection,
                rx.hstack(
                    rx.badge(
                        f"{LabelingState.selected_image_count} selected",
                        color_scheme="green",
                        size="1",
                    ),
                    rx.spacer(),
                    rx.icon_button(
                        rx.icon("x", size=12),
                        size="1",
                        variant="ghost",
                        on_click=LabelingState.clear_image_selection,
                        title="Clear selection",
                    ),
                    rx.icon_button(
                        rx.icon("trash-2", size=14),
                        size="1",
                        variant="outline",
                        color_scheme="red",
                        on_click=LabelingState.open_bulk_delete_modal,
                        title="Delete selected",
                    ),
                    width="100%",
                    align="center",
                    padding="6px 8px",
                    background=f"{styles.SUCCESS}10",
                    border_radius=styles.RADIUS_SM,
                ),
                rx.fragment(),
            ),
            rx.divider(style={"border_color": styles.BORDER}),
            # Scrollable thumbnail list
            rx.scroll_area(
                rx.vstack(
                    rx.foreach(
                        LabelingState.images,
                        image_thumbnail_item
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
            padding=styles.SPACING_3,
        ),
        width="230px",
        min_width="230px",
        height="100%",
        background=styles.BG_SECONDARY,
        border_right=f"1px solid {styles.BORDER}",
    )



# =============================================================================
# CENTER — Canvas Container
# =============================================================================

def zoom_controls() -> rx.Component:
    """Floating zoom controls overlay."""
    return rx.hstack(
        rx.icon_button(
            rx.icon("minus", size=14),
            variant="outline",
            size="1",
            on_click=LabelingState.zoom_out,
            style={"cursor": "pointer"},
        ),
        rx.el.span(
            "100%",  # Initial value, updated by JS
            id="zoom-percentage",
            style={
                "font_size": "12px",
                "font_weight": "500",
                "color": styles.TEXT_PRIMARY,
                "min_width": "45px",
                "text_align": "center",
                "display": "inline-block",
            }
        ),
        rx.icon_button(
            rx.icon("plus", size=14),
            variant="outline",
            size="1",
            on_click=LabelingState.zoom_in,
            style={"cursor": "pointer"},
        ),
        rx.icon_button(
            rx.icon("maximize-2", size=14),
            variant="outline",
            size="1",
            on_click=LabelingState.reset_view,
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
    """Center panel with the labeling canvas."""
    return rx.box(
        # Note: canvas.js is loaded globally via head_components in safari.py
        # Header with image info
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
                    on_click=LabelingState.navigate_back,
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
                LabelingState.dataset_name,
                size="3",
                weight="medium",
                style={"color": styles.TEXT_PRIMARY}
            ),
            rx.spacer(),
            # Save status indicator (Phase 1.9)
            rx.cond(
                LabelingState.save_status == "saving",
                rx.hstack(
                    rx.spinner(size="1"),
                    rx.text(
                        "Saving...",
                        size="1",
                        style={"color": styles.TEXT_SECONDARY}
                    ),
                    spacing="1",
                    align="center",
                ),
                rx.cond(
                    LabelingState.save_status == "saved",
                    rx.hstack(
                        rx.icon("check", size=12, color=styles.SUCCESS),
                        rx.text(
                            "Saved",
                            size="1",
                            style={"color": styles.SUCCESS}
                        ),
                        spacing="1",
                        align="center",
                    ),
                    rx.fragment(),
                ),
            ),
            rx.cond(
                LabelingState.has_current_image,
                rx.text(
                    f"{LabelingState.image_width} × {LabelingState.image_height}",
                    size="1",
                    style={"color": styles.TEXT_SECONDARY}
                ),
                rx.fragment(),
            ),
            # Focus mode toggle button
            rx.icon_button(
                rx.cond(
                    LabelingState.focus_mode,
                    rx.icon("eye", size=16),
                    rx.icon("eye-off", size=16),
                ),
                size="1",
                variant="ghost",
                on_click=LabelingState.toggle_focus_mode,
                title=rx.cond(
                    LabelingState.focus_mode,
                    "Exit Focus Mode (M)",
                    "Focus Mode (M)"
                ),
                style={
                    "color": rx.cond(
                        LabelingState.focus_mode,
                        styles.ACCENT,
                        styles.TEXT_SECONDARY
                    ),
                },
            ),
            # Fullscreen toggle button
            rx.icon_button(
                rx.cond(
                    LabelingState.is_fullscreen,
                    rx.icon("minimize", size=16),
                    rx.icon("maximize", size=16),
                ),
                size="1",
                variant="ghost",
                on_click=rx.call_script("window.toggleFullscreen && window.toggleFullscreen()"),
                title=rx.cond(
                    LabelingState.is_fullscreen,
                    "Exit Fullscreen (F)",
                    "Fullscreen (F)"
                ),
                style={
                    "color": rx.cond(
                        LabelingState.is_fullscreen,
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


# ... (existing imports)

# ... inside canvas_container function ...

        # Canvas area - needs ID for JS to find container
        rx.box(
            # The HTML5 canvas element
            rx.el.canvas(
                id="labeling-canvas",
                style={
                    "width": "100%",
                    "height": "100%",
                    "display": "block",
                }
            ),
            # Floating Toolbar (Top-Right)
            # REMOVED as per user request to keep canvas clean
            
            # Zoom controls overlay (Bottom-Right)
            zoom_controls(),
            
            # Hidden input for JS->Python communication (new annotation)
            # Note: We use type="text" with hidden style because type="hidden" doesn't trigger proper ChangeEvents in React
            rx.input(
                id="new-annotation-data",
                on_change=LabelingState.handle_new_annotation,
                type="text",
                style={
                    "position": "absolute",
                    "opacity": "0",
                    "height": "0",
                    "width": "0",
                    "pointer_events": "none",
                    "z_index": "-1"
                }
            ),
            # Hidden input for selection changes
            rx.input(
                id="selected-annotation-id",
                on_change=LabelingState.handle_selection_change,
                type="text",
                style={
                    "position": "absolute",
                    "opacity": "0",
                    "height": "0",
                    "width": "0",
                    "pointer_events": "none",
                    "z_index": "-1"
                }
            ),
            # Hidden input for deletion events
            rx.input(
                id="deleted-annotation-id",
                on_change=LabelingState.handle_annotation_deleted,
                type="text",
                style={
                    "position": "absolute",
                    "opacity": "0",
                    "height": "0",
                    "width": "0",
                    "pointer_events": "none",
                    "z_index": "-1"
                }
            ),
            # Hidden input for annotation updates (resize/move)
            rx.input(
                id="updated-annotation-data",
                on_change=LabelingState.handle_annotation_updated,
                type="text",
                style={
                    "position": "absolute",
                    "opacity": "0",
                    "height": "0",
                    "width": "0",
                    "pointer_events": "none",
                    "z_index": "-1"
                }
            ),
            # Hidden input for keyboard navigation: next image (D key)
            rx.input(
                id="navigate-next-trigger",
                on_change=LabelingState.handle_navigate_next,
                type="text",
                style={
                    "position": "absolute",
                    "opacity": "0",
                    "height": "0",
                    "width": "0",
                    "pointer_events": "none",
                    "z_index": "-1"
                }
            ),
            # Hidden input for keyboard navigation: prev image (A key)
            rx.input(
                id="navigate-prev-trigger",
                on_change=LabelingState.handle_navigate_prev,
                type="text",
                style={
                    "position": "absolute",
                    "opacity": "0",
                    "height": "0",
                    "width": "0",
                    "pointer_events": "none",
                    "z_index": "-1"
                }
            ),
            # Hidden input for tool changes (V/R keys)
            rx.input(
                id="tool-change-trigger",
                on_change=LabelingState.set_tool,
                type="text",
                style={
                    "position": "absolute",
                    "opacity": "0",
                    "height": "0",
                    "width": "0",
                    "pointer_events": "none",
                    "z_index": "-1"
                }
            ),
            # Hidden input for class selection (1-9 keys) - Step 1.11.5
            rx.input(
                id="class-select-trigger",
                on_change=LabelingState.handle_class_select,
                type="text",
                style={
                    "position": "absolute",
                    "opacity": "0",
                    "height": "0",
                    "width": "0",
                    "pointer_events": "none",
                    "z_index": "-1"
                }
            ),
            # Hidden input for help toggle (? key) - Step 1.11.8
            rx.input(
                id="help-toggle-trigger",
                on_change=LabelingState.toggle_shortcuts_help,
                type="text",
                style={
                    "position": "absolute",
                    "opacity": "0",
                    "height": "0",
                    "width": "0",
                    "pointer_events": "none",
                    "z_index": "-1"
                }
            ),
            # Hidden input for save-before-leave trigger (browser back, close tab)
            rx.input(
                id="save-before-leave-trigger",
                on_change=LabelingState.handle_save_before_leave,
                type="text",
                style={
                    "position": "absolute",
                    "opacity": "0",
                    "height": "0",
                    "width": "0",
                    "pointer_events": "none",
                    "z_index": "-1"
                }
            ),
            # Hidden input for focus mode toggle (M key)
            rx.input(
                id="focus-mode-trigger",
                on_change=LabelingState.toggle_focus_mode,
                type="text",
                style={
                    "position": "absolute",
                    "opacity": "0",
                    "height": "0",
                    "width": "0",
                    "pointer_events": "none",
                    "z_index": "-1"
                }
            ),
            # Hidden input for fullscreen toggle (F key)
            rx.input(
                id="fullscreen-trigger",
                on_change=LabelingState.toggle_fullscreen,
                type="text",
                style={
                    "position": "absolute",
                    "opacity": "0",
                    "height": "0",
                    "width": "0",
                    "pointer_events": "none",
                    "z_index": "-1"
                }
            ),
            # Hidden input for fullscreen state sync (browser fullscreenchange event)
            rx.input(
                id="fullscreen-state-sync",
                on_change=LabelingState.set_fullscreen_state,
                type="text",
                style={
                    "position": "absolute",
                    "opacity": "0",
                    "height": "0",
                    "width": "0",
                    "pointer_events": "none",
                    "z_index": "-1"
                }
            ),
            # Hidden input for context menu trigger (right-click on annotation)
            rx.input(
                id="context-menu-trigger",
                on_change=LabelingState.open_context_menu,
                type="text",
                style={
                    "position": "absolute",
                    "opacity": "0",
                    "height": "0",
                    "width": "0",
                    "pointer_events": "none",
                    "z_index": "-1"
                }
            ),
            
            id="canvas-container",  # ID for JS to find
            flex="1",
            width="100%",
            min_height="0",  # Allow shrinking in flex layout
            position="relative",
            overflow="hidden",
        ),
        # Navigation bar below canvas (Step 1.10.3)
        # Navigation bar below canvas (Hidden in focus mode)
        rx.box(
            rx.hstack(
                rx.button(
                    rx.icon("chevron-left", size=16),
                    "Previous",
                    variant="outline",
                    size="2",
                    on_click=LabelingState.navigate_prev,
                    disabled=LabelingState.current_image_index <= 1,
                    style={"cursor": rx.cond(
                        LabelingState.current_image_index > 1,
                        "pointer",
                        "not-allowed"
                    )},
                ),
                rx.spacer(),
                rx.text(
                    f"Image {LabelingState.current_image_index} of {LabelingState.image_count}",
                    size="2",
                    style={"color": styles.TEXT_SECONDARY},
                ),
                rx.spacer(),
                rx.button(
                    "Next",
                    rx.icon("chevron-right", size=16),
                    variant="outline",
                    size="2",
                    on_click=LabelingState.navigate_next,
                    disabled=LabelingState.current_image_index >= LabelingState.image_count,
                    style={"cursor": rx.cond(
                        LabelingState.current_image_index < LabelingState.image_count,
                        "pointer",
                        "not-allowed"
                    )},
                ),
                width="100%",
                padding=styles.SPACING_3,
                border_top=f"1px solid {styles.BORDER}",
                align="center",
            ),
            # Animate max-height for smooth transition
            max_height=rx.cond(LabelingState.focus_mode, "0px", "60px"),
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



# =============================================================================
# RIGHT SIDEBAR — Tools & Class Selector
# =============================================================================

def class_item(cls: str, idx: int) -> rx.Component:
    """Single class item (read-only, class management is in Project Detail)."""
    return rx.hstack(
        # Radio button (click to select)
        rx.box(
            rx.cond(
                LabelingState.current_class_id == idx,
                rx.icon("circle-dot", size=14, color=styles.ACCENT),
                rx.icon("circle", size=14, color=styles.TEXT_SECONDARY),
            ),
            cursor="pointer",
            on_click=LabelingState.set_current_class(idx),
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
            style={
                "color": styles.TEXT_PRIMARY,
                "flex": "1",
            },
        ),
        spacing="2",
        align="center",
        width="100%",
        padding="4px",
        border_radius=styles.RADIUS_SM,
        background=rx.cond(
            LabelingState.current_class_id == idx,
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
                                LabelingState.project_classes,
                                lambda cls_name, idx: rx.button(
                                    cls_name,
                                    on_click=lambda: LabelingState.update_annotation_class(ann["id"], idx),
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
            on_click=[rx.stop_propagation, LabelingState.delete_selected_annotation],
        ),
        width="100%",
        align="center",
        padding="6px",
        border_radius=styles.RADIUS_SM,
        background=rx.cond(
            LabelingState.selected_annotation_id == ann["id"],
            styles.BG_TERTIARY,
            "transparent",
        ),
        border=rx.cond(
            LabelingState.selected_annotation_id == ann["id"],
            f"1px solid {styles.ACCENT}",
            f"1px solid {styles.BORDER}",
        ),
        cursor="pointer",
        on_click=lambda: LabelingState.select_annotation_from_list(ann["id"]),
        _hover={"background": styles.BG_TERTIARY},
    )


def autolabel_modal() -> rx.Component:
    """Auto-labeling modal dialog with SAM3 and YOLO modes."""
    
    def sam3_panel() -> rx.Component:
        """SAM3 text prompt panel with prompt-to-class mapping."""
        
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
                    LabelingState.project_classes,
                    placeholder="Select class...",
                    on_change=lambda val: LabelingState.set_prompt_class_mapping(idx, val),
                    disabled=LabelingState.is_autolabeling,
                    size="1",
                    style={"flex": "1"},
                ),
                spacing="2",
                align="center",
                width="100%",
            )
        
        return rx.vstack(
            rx.text(
                f"Target images: {LabelingState.autolabel_target_count}",
                size="1",
                style={"color": styles.TEXT_SECONDARY}
            ),
            # Generation options checkboxes (always visible — user picks mode first)
            rx.vstack(
                rx.text("Generation Options", size="1", weight="medium", style={"color": styles.TEXT_SECONDARY}),
                rx.hstack(
                    rx.checkbox(
                        "Generate bounding boxes",
                        checked=LabelingState.autolabel_generate_bboxes,
                        on_change=LabelingState.set_autolabel_generate_bboxes,
                        disabled=LabelingState.is_autolabeling,
                        size="1",
                    ),
                    spacing="2",
                    width="100%",
                ),
                rx.hstack(
                    rx.checkbox(
                        "Generate masks",
                        checked=LabelingState.autolabel_generate_masks,
                        on_change=LabelingState.set_autolabel_generate_masks,
                        disabled=LabelingState.is_autolabeling,
                        size="1",
                    ),
                    spacing="2",
                    width="100%",
                ),
                # Contextual info text for mask-only mode
                rx.cond(
                    LabelingState.autolabel_mask_fast_path,
                    rx.text(
                        f"Masks will be generated from {LabelingState.annotated_image_count} existing bounding boxes",
                        size="1",
                        style={"color": styles.SUCCESS, "font_style": "italic"},
                    ),
                    rx.cond(
                        LabelingState.autolabel_generate_masks & ~LabelingState.autolabel_generate_bboxes,
                        rx.text(
                            "Masks will be generated from text prompts on empty images",
                            size="1",
                            style={"color": styles.ACCENT, "font_style": "italic"},
                        ),
                    ),
                ),
                # Validation: at least one must be selected
                rx.cond(
                    ~LabelingState.autolabel_generate_bboxes & ~LabelingState.autolabel_generate_masks,
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
                ~LabelingState.autolabel_mask_fast_path,
                rx.vstack(
                    # Prompt input
                    rx.input(
                        placeholder="e.g., 'elephant, fox, red car'",
                        value=LabelingState.autolabel_prompt,
                        on_change=LabelingState.set_autolabel_prompt,
                        on_key_down=LabelingState.handle_autolabel_keydown,
                        disabled=LabelingState.is_autolabeling,
                        size="2",
                        width="100%",
                    ),
                    # Dynamic mapping section (shown when prompt has terms)
                    rx.cond(
                        LabelingState.autolabel_prompt_terms.length() > 0,
                        rx.vstack(
                            rx.text(
                                "Map prompts to classes:",
                                size="1",
                                weight="medium",
                                style={"color": styles.TEXT_SECONDARY}
                            ),
                            rx.vstack(
                                rx.foreach(
                                    LabelingState.autolabel_prompt_terms,
                                    prompt_mapping_row,
                                ),
                                spacing="2",
                                width="100%",
                            ),
                            rx.cond(
                                ~LabelingState.all_prompts_mapped,
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
                                LabelingState.autolabel_confidence_percentage,
                                size="1",
                                weight="medium",
                                style={"color": styles.TEXT_PRIMARY}
                            ),
                            width="100%",
                        ),
                        rx.slider(
                            value=[LabelingState.autolabel_confidence],
                            on_change=LabelingState.set_autolabel_confidence,
                            min=0.1,
                            max=0.9,
                            step=0.05,
                            disabled=LabelingState.is_autolabeling,
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
            spacing="3",
            width="100%",
        )
    
    def yolo_panel() -> rx.Component:
        """YOLO model selection panel."""
        return rx.vstack(
            rx.cond(
                LabelingState.has_autolabel_models,
                rx.vstack(
                    rx.text("Select Model", size="2", weight="medium"),
                    rx.select(
                        LabelingState.autolabel_model_names,
                        placeholder="Choose a trained model...",
                        value=LabelingState.selected_autolabel_model_name,
                        on_change=LabelingState.select_autolabel_model_by_name,
                        disabled=LabelingState.is_autolabeling,
                        size="2",
                        width="100%",
                    ),
                    rx.text(
                        f"Empty images: {LabelingState.empty_image_count}",
                        size="1",
                        style={"color": styles.TEXT_SECONDARY}
                    ),
                    # Confidence slider
                    rx.vstack(
                        rx.hstack(
                            rx.text("Confidence:", size="1", style={"color": styles.TEXT_SECONDARY}),
                            rx.spacer(),
                            rx.text(
                                LabelingState.autolabel_confidence_percentage,
                                size="1",
                                weight="medium",
                            ),
                            width="100%",
                        ),
                        rx.slider(
                            value=[LabelingState.autolabel_confidence],
                            on_change=LabelingState.set_autolabel_confidence,
                            min=0.1,
                            max=0.9,
                            step=0.05,
                            disabled=LabelingState.is_autolabeling,
                            size="1",
                            width="100%",
                        ),
                        spacing="1",
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
                    rx.text("Auto-Label Dataset"),
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
                    value=LabelingState.autolabel_mode,
                    on_change=LabelingState.set_autolabel_mode,
                    width="100%",
                ),
                # Compute target toggle (Cloud / Local GPU)
                compute_target_toggle(
                    value=LabelingState.compute_target,
                    on_change=LabelingState.set_compute_target,
                    machines=LabelingState.local_machines,
                    selected_machine=LabelingState.selected_machine,
                    on_machine_change=LabelingState.set_selected_machine,
                ),
                rx.divider(),
                # Progress/Log area (when running)
                rx.cond(
                    LabelingState.is_autolabeling,
                    rx.vstack(
                        rx.hstack(
                            rx.spinner(size="2"),
                            rx.text("Processing...", weight="medium"),
                            spacing="2",
                        ),
                        rx.cond(
                            LabelingState.autolabel_logs != "",
                            rx.box(
                                rx.scroll_area(
                                    rx.text(
                                        LabelingState.autolabel_logs,
                                        font_family="JetBrains Mono, monospace",
                                        white_space="pre-wrap",
                                        size="1",
                                        style={"color": styles.CODE_TEXT, "line_height": "1.4"},
                                    ),
                                    type="always",
                                    scrollbars="vertical",
                                    style={"height": "130px"},
                                    id="image-autolabel-logs-scroll",
                                ),
                                style={
                                    "background": styles.CODE_BG,
                                    "padding": "8px",
                                    "border_radius": styles.RADIUS_SM,
                                    "height": "140px",
                                    "width": "100%",
                                    "overflow": "hidden",
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
                        on_click=LabelingState.close_autolabel_modal,
                        disabled=LabelingState.is_autolabeling,
                    ),
                    rx.button(
                        rx.cond(
                            LabelingState.is_autolabeling,
                            rx.hstack(rx.spinner(size="1"), rx.text("Running..."), spacing="2"),
                            rx.hstack(rx.icon("play", size=14), rx.text("Start Auto-Label"), spacing="2"),
                        ),
                        on_click=LabelingState.start_autolabel,
                        disabled=rx.cond(
                            LabelingState.autolabel_mode == "sam3",
                            ~LabelingState.can_autolabel,
                            ~LabelingState.can_autolabel_yolo,
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
        open=LabelingState.show_autolabel_modal,
        on_open_change=LabelingState.set_show_autolabel_modal,
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
                    # Select Tool
                    rx.icon_button(
                        rx.icon("mouse-pointer-2", size=20),
                        on_click=lambda: LabelingState.set_tool("select"),
                        variant="solid",
                        color_scheme=rx.cond(
                            LabelingState.current_tool == "select",
                            "blue",
                            "gray"
                        ),
                        size="2",
                        cursor="pointer",
                        title="Select Tool (V)"
                    ),
                    # Draw Tool
                    rx.icon_button(
                        rx.icon("square", size=20),
                        on_click=lambda: LabelingState.set_tool("draw"),
                        variant="solid",
                        color_scheme=rx.cond(
                            LabelingState.current_tool == "draw",
                            "blue",
                            "gray"
                        ),
                        size="2",
                        cursor="pointer",
                        title="Draw Rectangle (R)"
                    ),
                    # Mask Edit Tool
                    rx.icon_button(
                        rx.icon("pentagon", size=20),
                        on_click=lambda: LabelingState.set_tool("mask_edit"),
                        variant="solid",
                        color_scheme=rx.cond(
                            LabelingState.current_tool == "mask_edit",
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
                        on_click=LabelingState.open_autolabel_modal,
                        variant="outline",
                        color_scheme="green",
                        size="2",
                        cursor="pointer",
                        title="Auto-Label (A)"
                    ),
                    spacing="2",
                ),
                spacing="2",
                width="100%",
                padding_bottom=styles.SPACING_4,
                border_bottom=f"1px solid {styles.BORDER}",
            ),
            # Classes section - Interactive class manager
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
                        LabelingState.project_classes.length(),
                        size="1",
                        style={"color": styles.TEXT_SECONDARY}
                    ),
                    width="100%",
                    align="center",
                ),
                # Class list with radio buttons and inline editing
                rx.cond(
                    LabelingState.project_classes.length() > 0,
                    rx.vstack(
                        rx.foreach(
                            LabelingState.project_classes,
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
                        value=LabelingState.new_class_name,
                        on_change=LabelingState.set_new_class_name,
                        on_key_down=LabelingState.handle_add_class_keydown,
                        size="1",
                        style={"flex": "1"},
                    ),
                    rx.icon_button(
                        rx.icon("plus", size=14),
                        size="1",
                        variant="outline",
                        on_click=LabelingState.add_class,
                        disabled=LabelingState.new_class_name.strip() == "",
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


            # Annotations section with list and re-class
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
                        LabelingState.annotations.length(),
                        size="1",
                        style={"color": styles.TEXT_SECONDARY}
                    ),
                    width="100%",
                    align="center",
                ),
                # Annotation list (scrollable)
                rx.cond(
                    LabelingState.annotations.length() > 0,
                    rx.scroll_area(
                        rx.vstack(
                            rx.foreach(
                                LabelingState.annotations,
                                annotation_item,
                            ),
                            spacing="1",
                            width="100%",
                        ),
                        type="auto",
                        style={"max_height": "200px", "width": "100%"},
                    ),
                    rx.text(
                        "No annotations yet",
                        size="1",
                        style={"color": styles.TEXT_SECONDARY, "font_style": "italic"}
                    ),
                ),
                # Delete button
                rx.button(
                    rx.icon("trash-2", size=14),
                    "Delete Selected",
                    variant="outline",
                    color_scheme="red",
                    size="1",
                    width="100%",
                    disabled=LabelingState.selected_annotation_id == None,
                    on_click=LabelingState.delete_selected_annotation,
                    style={"cursor": rx.cond(
                        LabelingState.selected_annotation_id != None,
                        "pointer",
                        "not-allowed"
                    )},
                ),
                # Delete Mask button (only shown when selected annotation has mask)
                rx.cond(
                    LabelingState.selected_annotation_has_mask,
                    rx.button(
                        rx.icon("eraser", size=14),
                        "Delete Mask",
                        variant="outline",
                        color_scheme="gray",
                        size="1",
                        width="100%",
                        on_click=LabelingState.delete_mask_from_annotation,
                        cursor="pointer",
                    ),
                ),
                rx.text(
                    "Del/Backspace to remove",
                    size="1",
                    style={"color": styles.TEXT_SECONDARY, "opacity": "0.7"}
                ),
                spacing="2",
                width="100%",
                flex="1",
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
    return rx.hstack(
        rx.skeleton(width="200px", height="100%"),
        rx.skeleton(flex="1", height="100%"),
        rx.skeleton(width="220px", height="100%"),
        spacing="0",
        width="100%",
        height="100vh",
    )


def shortcut_row(key: str, description: str) -> rx.Component:
    """Single row in the shortcuts help modal."""
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
        rx.text(
            description,
            size="2",
            style={"color": styles.TEXT_SECONDARY},
        ),
        spacing="3",
        align="center",
        width="100%",
    )


def shortcuts_help_modal() -> rx.Component:
    """Keyboard shortcuts help modal (Step 1.11.8)."""
    return rx.dialog.root(
        rx.dialog.content(
            rx.dialog.title(
                rx.hstack(
                    rx.icon("keyboard", size=20),
                    rx.text("Keyboard Shortcuts"),
                    spacing="2",
                    align="center",
                ),
            ),
            rx.vstack(
                rx.divider(style={"border_color": styles.BORDER}),
                rx.text("Navigation", size="1", weight="medium", style={"color": styles.ACCENT}),
                shortcut_row("A", "Previous image"),
                shortcut_row("D", "Next image"),
                rx.divider(style={"border_color": styles.BORDER}),
                rx.text("Tools", size="1", weight="medium", style={"color": styles.ACCENT}),
                shortcut_row("V", "Select mode"),
                shortcut_row("R", "Draw rectangle"),
                shortcut_row("C", "Edit masks"),
                rx.divider(style={"border_color": styles.BORDER}),
                rx.text("Classes", size="1", weight="medium", style={"color": styles.ACCENT}),
                shortcut_row("1-9", "Select class by number"),
                rx.divider(style={"border_color": styles.BORDER}),
                rx.text("Actions", size="1", weight="medium", style={"color": styles.ACCENT}),
                shortcut_row("Delete", "Delete selected box"),
                shortcut_row("Escape", "Deselect / Cancel"),
                rx.divider(style={"border_color": styles.BORDER}),
                rx.text("Canvas", size="1", weight="medium", style={"color": styles.ACCENT}),
                shortcut_row("Scroll", "Zoom in/out"),
                shortcut_row("Shift+Drag", "Pan canvas"),
                rx.divider(style={"border_color": styles.BORDER}),
                shortcut_row("M", "Toggle Focus Mode"),
                shortcut_row("F", "Toggle Fullscreen"),
                shortcut_row("H", "Go to Dashboard"),
                shortcut_row("?", "Show this help"),
                spacing="2",
                width="100%",
                padding="4px 0",
            ),
            rx.dialog.close(
                rx.button(
                    "Close",
                    variant="outline",
                    width="100%",
                    margin_top="16px",
                ),
            ),
            style={"max_width": "320px"},
        ),
        open=LabelingState.show_shortcuts_help,
        on_open_change=lambda val: LabelingState.set_show_shortcuts_help(val),
    )


def bulk_delete_modal() -> rx.Component:
    """Modal for confirming bulk image deletion."""
    return rx.dialog.root(
        rx.dialog.content(
            rx.dialog.title("Delete Images", style={"color": styles.ERROR}),
            rx.vstack(
                rx.text(
                    f"Are you sure you want to delete {LabelingState.selected_image_count} image(s)?",
                    style={"color": styles.TEXT_PRIMARY}
                ),
                rx.text(
                    "This will permanently delete the selected images and their annotations.",
                    size="2",
                    style={"color": styles.TEXT_SECONDARY}
                ),
                rx.hstack(
                    rx.dialog.close(
                        rx.button(
                            "Cancel",
                            variant="outline",
                            color_scheme="gray",
                            on_click=LabelingState.close_bulk_delete_modal,
                        ),
                    ),
                    rx.button(
                        "Delete",
                        color_scheme="red",
                        loading=LabelingState.is_bulk_deleting,
                        on_click=LabelingState.confirm_bulk_delete,
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
        open=LabelingState.show_bulk_delete_modal,
    )


def empty_stats_modal() -> rx.Component:
    """Modal showing stats about unannotated images with option to delete them."""
    return rx.dialog.root(
        rx.dialog.content(
            rx.dialog.title(
                rx.hstack(
                    rx.icon("bar-chart-2", size=18, color=styles.ACCENT),
                    "Dataset Statistics",
                    spacing="2",
                    align="center",
                )
            ),
            rx.vstack(
                # Stats section
                rx.vstack(
                    rx.hstack(
                        rx.icon("images", size=16, color=styles.TEXT_SECONDARY),
                        rx.text("Total images:", size="2"),
                        rx.spacer(),
                        rx.text(
                            LabelingState.image_count,
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
                            LabelingState.annotated_image_count,
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
                            LabelingState.empty_image_count,
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
                # Delete empty images section
                rx.cond(
                    LabelingState.empty_image_count > 0,
                    rx.vstack(
                        rx.callout(
                            rx.text(
                                f"You can delete all {LabelingState.empty_image_count} unannotated image(s). "
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
                            value=LabelingState.empty_delete_confirmation,
                            on_change=LabelingState.set_empty_delete_confirmation,
                            placeholder="Type 'delete'",
                            width="100%",
                        ),
                        rx.hstack(
                            rx.dialog.close(
                                rx.button(
                                    "Cancel",
                                    variant="outline",
                                    color_scheme="gray",
                                    on_click=LabelingState.close_empty_stats_modal,
                                ),
                            ),
                            rx.button(
                                rx.cond(
                                    LabelingState.is_deleting_empty_images,
                                    rx.hstack(rx.spinner(size="1"), rx.text("Deleting..."), spacing="2"),
                                    rx.hstack(rx.icon("trash-2", size=14), rx.text("Delete Empty Images"), spacing="2"),
                                ),
                                color_scheme="red",
                                on_click=LabelingState.delete_empty_images,
                                disabled=~LabelingState.can_confirm_delete_empty,
                            ),
                            spacing="3",
                            justify="end",
                            width="100%",
                        ),
                        spacing="3",
                        width="100%",
                    ),
                    # No empty images
                    rx.vstack(
                        rx.hstack(
                            rx.icon("check-circle", size=20, color=styles.SUCCESS),
                            rx.text(
                                "All images have annotations!",
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
                                on_click=LabelingState.close_empty_stats_modal,
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
        open=LabelingState.show_empty_stats_modal,
    )


def editor_layout() -> rx.Component:
    """Main 3-panel editor layout with focus mode support."""
    return rx.box(
        rx.hstack(
            # Left sidebar - hidden in focus mode with slide animation
            rx.box(
                left_sidebar(),
                width=rx.cond(LabelingState.focus_mode, "0px", "230px"),
                min_width=rx.cond(LabelingState.focus_mode, "0px", "230px"),
                height="100%",
                overflow="hidden",
                transition="all 0.3s ease-in-out",
            ),
            canvas_container(),
            # Right sidebar - hidden in focus mode with slide animation
            rx.box(
                right_sidebar(),
                width=rx.cond(LabelingState.focus_mode, "0px", "220px"),
                min_width=rx.cond(LabelingState.focus_mode, "0px", "220px"),
                height="100%",
                overflow="hidden",
                transition="all 0.3s ease-in-out",
            ),
            spacing="0",
            width="100%",
            height="100vh",
            overflow="hidden",
        ),
        # Modals
        shortcuts_help_modal(),
        bulk_delete_modal(),
        autolabel_modal(),
        empty_stats_modal(),
        # Right-click context menu for annotations
        annotation_context_menu(
            is_open=LabelingState.context_menu_open,
            position_x=LabelingState.context_menu_x,
            position_y=LabelingState.context_menu_y,
            classes=LabelingState.project_classes,
            on_class_change=LabelingState.context_menu_change_class,
            on_project_thumbnail=LabelingState.set_as_project_thumbnail,
            on_dataset_thumbnail=LabelingState.set_as_dataset_thumbnail,
            on_close=LabelingState.close_context_menu,
        ),
    )



def editor_content() -> rx.Component:
    """Content wrapper with loading state."""
    return rx.cond(
        LabelingState.is_loading,
        loading_skeleton(),
        rx.cond(
            LabelingState.error_message != "",
            rx.center(
                rx.vstack(
                    rx.icon("circle-alert", size=48, style={"color": styles.ERROR}),
                    rx.text(LabelingState.error_message, style={"color": styles.TEXT_PRIMARY}),
                    rx.link(
                        rx.button("Back to Dataset", variant="outline"),
                        href=f"/projects/{LabelingState.current_project_id}/datasets/{LabelingState.current_dataset_id}",
                    ),
                    spacing="4",
                    align="center",
                ),
                height="100vh",
            ),
            editor_layout(),
        ),
    )


@rx.page(
    route="/projects/[project_id]/datasets/[dataset_id]/label",
    on_load=LabelingState.on_load,
)
def labeling_editor() -> rx.Component:
    """The labeling editor page (protected)."""
    return require_auth(editor_content())
