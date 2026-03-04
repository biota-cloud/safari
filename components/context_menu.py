"""
Annotation Context Menu — Right-click menu for annotation actions.

Used in both Image and Video editors for:
- Changing annotation class (primary action, shown directly)
- Setting as project/dataset thumbnail (secondary, in submenu)
"""

import reflex as rx
import styles


def annotation_context_menu(
    is_open: rx.Var[bool],
    position_x: rx.Var[int],
    position_y: rx.Var[int],
    classes: rx.Var[list[str]],
    on_class_change: rx.EventHandler,
    on_project_thumbnail: rx.EventHandler,
    on_dataset_thumbnail: rx.EventHandler,
    on_close: rx.EventHandler,
) -> rx.Component:
    """
    Right-click context menu for annotations.
    
    Layout:
    - Classes listed directly (most common action)
    - "More Actions" submenu with thumbnail options
    
    Args:
        is_open: Whether the menu is visible
        position_x: X coordinate (viewport pixels)
        position_y: Y coordinate (viewport pixels)
        classes: List of project classes for reassignment
        on_class_change: Handler for class change (receives class_name)
        on_project_thumbnail: Handler for "Use as Project thumbnail"
        on_dataset_thumbnail: Handler for "Use as Dataset thumbnail"
        on_close: Handler to close the menu
    """
    return rx.cond(
        is_open,
        rx.box(
            # Invisible backdrop to catch clicks outside
            rx.box(
                on_click=on_close,
                style={
                    "position": "fixed",
                    "top": "0",
                    "left": "0",
                    "right": "0",
                    "bottom": "0",
                    "z_index": "999",
                },
            ),
            # The actual menu
            rx.box(
                rx.vstack(
                    # Section header
                    rx.text(
                        "Assign Class",
                        size="1",
                        weight="medium",
                        style={
                            "color": styles.TEXT_SECONDARY,
                            "padding": f"4px {styles.SPACING_3}",
                            "text_transform": "uppercase",
                            "letter_spacing": "0.5px",
                        },
                    ),
                    # Classes listed directly (scrollable if many)
                    rx.scroll_area(
                        rx.vstack(
                            rx.foreach(
                                classes,
                                lambda cls_name, idx: _class_item(cls_name, idx, on_class_change, on_close),
                            ),
                            spacing="0",
                            width="100%",
                        ),
                        type="auto",
                        style={"max_height": "180px"},
                    ),
                    
                    rx.divider(style={"border_color": styles.BORDER, "margin": "4px 0"}),
                    
                    # More Actions submenu (thumbnail options)
                    _more_actions_submenu(on_project_thumbnail, on_dataset_thumbnail, on_close),
                    
                    spacing="0",
                    width="100%",
                ),
                style={
                    "position": "fixed",
                    "left": position_x.to_string() + "px",
                    "top": position_y.to_string() + "px",
                    "z_index": "1000",
                    "background": styles.POPOVER_BG,
                    "border": f"1px solid {styles.BORDER}",
                    "border_radius": styles.RADIUS_MD,
                    "padding": styles.SPACING_1,
                    "min_width": "180px",
                    "box_shadow": styles.SHADOW_LG,
                },
            ),
        ),
        rx.fragment(),
    )


def _class_item(
    cls_name: rx.Var[str],
    idx: rx.Var[int],
    on_class_change: rx.EventHandler,
    on_close: rx.EventHandler,
) -> rx.Component:
    """Single class item in the direct list."""
    return rx.box(
        rx.hstack(
            # Color dot
            rx.box(
                width="10px",
                height="10px",
                border_radius="50%",
                background=rx.color("accent", 9),
                style={"filter": f"hue-rotate({(idx * 137) % 360}deg)"},
            ),
            rx.text(cls_name, size="2", style={"color": styles.TEXT_PRIMARY}),
            spacing="2",
            align="center",
        ),
        on_click=[lambda: on_class_change(cls_name), on_close],
        style={
            "padding": f"{styles.SPACING_2} {styles.SPACING_3}",
            "border_radius": styles.RADIUS_SM,
            "cursor": "pointer",
            "width": "100%",
            "&:hover": {
                "background": styles.POPOVER_ITEM_BG,
            },
        },
    )


def _more_actions_submenu(
    on_project_thumbnail: rx.EventHandler,
    on_dataset_thumbnail: rx.EventHandler,
    on_close: rx.EventHandler,
) -> rx.Component:
    """Expandable submenu for thumbnail actions."""
    return rx.popover.root(
        rx.popover.trigger(
            rx.box(
                rx.hstack(
                    rx.icon("more-horizontal", size=14, style={"color": styles.TEXT_SECONDARY}),
                    rx.text("More Actions", size="2", style={"color": styles.TEXT_PRIMARY}),
                    rx.spacer(),
                    rx.icon("chevron-right", size=12, style={"color": styles.TEXT_SECONDARY}),
                    spacing="2",
                    align="center",
                    width="100%",
                ),
                style={
                    "padding": f"{styles.SPACING_2} {styles.SPACING_3}",
                    "border_radius": styles.RADIUS_SM,
                    "cursor": "pointer",
                    "width": "100%",
                    "&:hover": {
                        "background": styles.POPOVER_ITEM_BG,
                    },
                },
            ),
        ),
        rx.popover.content(
            rx.vstack(
                _menu_item(
                    icon="image",
                    label="Use as Project Thumbnail",
                    on_click=[on_project_thumbnail, on_close],
                ),
                _menu_item(
                    icon="folder",
                    label="Use as Dataset Thumbnail",
                    on_click=[on_dataset_thumbnail, on_close],
                ),
                spacing="0",
                width="100%",
            ),
            side="right",
            align="start",
            style={
                "background": styles.POPOVER_BG,
                "border": f"1px solid {styles.BORDER}",
                "border_radius": styles.RADIUS_MD,
                "padding": styles.SPACING_1,
                "min_width": "200px",
            },
        ),
    )


def _menu_item(
    icon: str,
    label: str,
    on_click: list | rx.EventHandler,
) -> rx.Component:
    """Single menu item with icon and label."""
    return rx.box(
        rx.hstack(
            rx.icon(icon, size=14, style={"color": styles.TEXT_SECONDARY}),
            rx.text(label, size="2", style={"color": styles.TEXT_PRIMARY}),
            spacing="2",
            align="center",
            width="100%",
        ),
        on_click=on_click,
        style={
            "padding": f"{styles.SPACING_2} {styles.SPACING_3}",
            "border_radius": styles.RADIUS_SM,
            "cursor": "pointer",
            "width": "100%",
            "&:hover": {
                "background": styles.POPOVER_ITEM_BG,
            },
        },
    )
