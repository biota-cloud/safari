"""
Dashboard Hub V2 — Command center landing page.

Route: /dashboard
Shows project manager, context-aware labeling/training panels, and navigation.
"""

import reflex as rx
import styles
from app_state import AuthState, require_auth
from modules.auth.hub_state import (
    HubState,
    HubProjectModel,
    HubDatasetModel,
    HubTrainingRunModel,
)
from components.nav_header import nav_header
from modules.projects.state import ProjectsState
from modules.projects.new_project_modal import new_project_modal as projects_new_project_modal


# =============================================================================
# QUICK STATS
# =============================================================================

def stat_card(label: str, value: rx.Var, icon: str, color: str = styles.ACCENT) -> rx.Component:
    """Individual stat card."""
    return rx.box(
        rx.hstack(
            rx.icon(icon, size=16, style={"color": color}),
            rx.vstack(
                rx.text(value, size="4", weight="bold", style={"color": styles.TEXT_PRIMARY}),
                rx.text(label, size="1", style={"color": styles.TEXT_SECONDARY}),
                spacing="0",
                align="start",
            ),
            spacing="3",
            align="center",
        ),
        style={
            "background": styles.BG_SECONDARY,
            "border": f"1px solid {styles.BORDER}",
            "border_radius": styles.RADIUS_LG,
            "padding": styles.SPACING_3,
            "flex": "1",
        }
    )


def stats_row() -> rx.Component:
    """Row of quick stats."""
    return rx.hstack(
        stat_card("Projects", HubState.project_count, "folder", styles.ACCENT),
        stat_card("Datasets", HubState.dataset_count, "database", styles.EARTH_TAUPE),
        stat_card("Images", HubState.image_count, "image", styles.EARTH_SAGE),
        stat_card("Labeled", HubState.labeled_count, "check-circle", styles.EARTH_SIENNA),
        spacing="3",
        width="100%",
    )


# =============================================================================
# PROJECT MANAGER
# =============================================================================

def project_row(project: HubProjectModel) -> rx.Component:
    """Single project row in the manager."""
    
    # 80px Thumbnail (no active border - button handles that)
    thumbnail = rx.cond(
        project.thumbnail_url != "",
        # Has thumbnail - show image
        rx.image(
            src=project.thumbnail_url,
            width="80px",
            height="80px",
            object_fit="cover",
            border_radius=styles.RADIUS_MD,
            style={
                "border": f"1px solid {styles.BORDER}",
                "flex_shrink": "0",
            },
        ),
        # No thumbnail - placeholder with icon
        rx.box(
            rx.icon("folder", size=24, color=styles.TEXT_SECONDARY),
            style={
                "width": "80px",
                "height": "80px",
                "border_radius": styles.RADIUS_MD,
                "background": f"linear-gradient(135deg, {styles.BG_TERTIARY} 0%, {styles.ACCENT}22 100%)",
                "border": f"1px solid {styles.BORDER}",
                "display": "flex",
                "align_items": "center",
                "justify_content": "center",
                "flex_shrink": "0",
            },
        ),
    )
    
    # Load/Active button (fixed width for consistency)
    button_style = {"min_width": "75px", "justify_content": "center"}
    
    activate_button = rx.cond(
        project.is_active,
        # Active state - green accent button
        rx.button(
            rx.icon("check", size=12),
            "Active",
            size="1",
            variant="outline",
            color_scheme="green",
            on_click=rx.stop_propagation,
            style={**button_style, "pointer_events": "none"},
        ),
        # Inactive - Load button with icon
        rx.button(
            rx.icon("folder-open", size=12),
            "Load",
            size="1",
            variant="outline",
            color_scheme="gray",
            on_click=[
                rx.stop_propagation,
                HubState.set_active_project(project.id),
                # Scroll projects list to top gracefully (the element itself IS the viewport)
                rx.call_script(
                    "setTimeout(() => { const el = document.getElementById('projects-scroll-area'); if (el) el.scrollTo({top: 0, behavior: 'smooth'}); }, 100)"
                ),
            ],
            style=button_style,
        ),
    )
    
    return rx.box(
        rx.hstack(
            thumbnail,
            # Middle section: name + edit + badge
            rx.vstack(
                # Project name with inline editing
                rx.cond(
                    HubState.editing_project_id == project.id,
                    # Edit mode: input field
                    rx.input(
                        value=HubState.editing_project_name,
                        on_change=HubState.set_editing_project_name,
                        on_key_down=HubState.handle_project_name_keydown,
                        on_blur=HubState.save_project_name,
                        on_click=rx.stop_propagation,
                        size="1",
                        auto_focus=True,
                        style={"min_width": "80px", "max_width": "150px"},
                    ),
                    # View mode: name + pencil icon
                    rx.hstack(
                        rx.text(
                            project.name,
                            size="2",
                            weight="medium",
                            style={"color": styles.TEXT_PRIMARY},
                            truncate=True,
                        ),
                        rx.icon_button(
                            rx.icon("pencil", size=10),
                            size="1",
                            variant="ghost",
                            color_scheme="gray",
                            on_click=[
                                rx.stop_propagation,
                                HubState.start_edit_project_name(project.id, project.name),
                            ],
                            style={
                                "opacity": "0",
                                "transition": "opacity 0.2s",
                                "padding": "2px",
                                "min_width": "18px",
                                "height": "18px",
                            },
                            class_name="edit-pencil",
                        ),
                        spacing="1",
                        align="center",
                        style={
                            "&:hover .edit-pencil": {"opacity": "0.6"},
                        },
                    ),  # Close rx.hstack for view mode
                ),  # Close rx.cond
                # Dataset count badge + class badges row
                rx.hstack(
                    rx.badge(
                        project.dataset_count.to_string() + " Datasets",
                        variant="outline",
                        size="1",
                        color_scheme="gray",
                        style=styles.BADGE_MINI,
                    ),
                    # Class name badges (show first 3) with varied colors
                    rx.foreach(
                        project.classes[:3],
                        lambda cls: rx.badge(
                            cls,
                            variant="outline",
                            size="1",
                            color_scheme=rx.match(
                                cls.length() % 4,  # color based on name length
                                (0, "green"),
                                (1, "teal"),
                                (2, "brown"),
                                (3, "lime"),
                                "green",
                            ),
                            style=styles.BADGE_MINI,
                        ),
                    ),
                    # "+N more" if more than 3 classes
                    rx.cond(
                        project.classes.length() > 3,
                        rx.badge(
                            "+" + (project.classes.length() - 3).to_string(),
                            variant="outline",
                            size="1",
                            color_scheme="gray",
                            style=styles.BADGE_MINI,
                        ),
                        rx.fragment(),
                    ),
                    spacing="1",
                    align="center",
                    wrap="wrap",
                ),
                spacing="1",
                align="start",
                style={"flex": "1"},
            ),
            # Right section: Load/Active button + Delete
            rx.hstack(
                activate_button,
                # Hide trash for team projects if non-admin
                rx.cond(
                    ~project.is_team | AuthState.is_admin,
                    rx.icon_button(
                        rx.icon("trash-2", size=14),
                        size="1",
                        variant="ghost",
                        color_scheme="gray",
                        on_click=[
                            rx.stop_propagation,
                            HubState.open_delete_modal(project.id, project.name),
                        ],
                        style={
                            "opacity": "0.5",
                            "&:hover": {"opacity": "1", "color": styles.ERROR},
                        },
                    ),
                    # Invisible placeholder to keep alignment
                    rx.box(width="24px"),
                ),
                spacing="2",
                align="center",
            ),
            spacing="3",
            align="center",
            width="100%",
        ),
        on_click=HubState.select_and_navigate_to_project(project.id),
        width="100%",
        style={
            "padding": "10px 12px",
            "border_radius": styles.RADIUS_MD,
            "border": f"1px solid {styles.BORDER}",
            "background": rx.cond(project.is_active, styles.BG_TERTIARY, styles.BG_SECONDARY),
            "cursor": "pointer",
            "transition": styles.TRANSITION_FAST,
            "margin_bottom": "6px",
            "&:hover": {
                "background": styles.BG_TERTIARY,
                "border_color": styles.ACCENT,
            },
        }
    )



def project_manager_card() -> rx.Component:
    """Project manager section with list and actions."""
    return rx.box(
        rx.vstack(
            # Header
            rx.hstack(
                rx.icon("folder", size=18, color=styles.ACCENT),
                rx.text("Projects", size="3", weight="bold", style={"color": styles.TEXT_PRIMARY}),
                rx.spacer(),
                rx.button(
                    rx.icon("plus", size=14),
                    "Add Project",
                    size="1",
                    variant="outline",
                    on_click=ProjectsState.open_modal,
                ),
                width="100%",
                align="center",
            ),
            rx.divider(style={"margin": f"{styles.SPACING_2} 0"}),
            
            # Project list
            rx.cond(
                HubState.has_projects,
                rx.scroll_area(
                    rx.vstack(
                        rx.foreach(HubState.projects, project_row),
                        spacing="1",
                        width="100%",
                    ),
                    type="hover",
                    scrollbars="vertical",
                        style={"max_height": "300px"},
                    id="projects-scroll-area",
                ),
                rx.center(
                    rx.vstack(
                        rx.icon("folder-plus", size=24, style={"color": styles.TEXT_SECONDARY, "opacity": "0.5"}),
                        rx.text("No projects yet", size="2", style={"color": styles.TEXT_SECONDARY}),
                        rx.button(
                            "Create First Project",
                            size="1",
                            on_click=ProjectsState.open_modal,
                        ),
                        spacing="2",
                        align="center",
                    ),
                    style={"padding": styles.SPACING_4},
                ),
            ),
            
            spacing="2",
            width="100%",
        ),
        style={
            "background": styles.BG_SECONDARY,
            "border": f"1px solid {styles.BORDER}",
            "border_radius": styles.RADIUS_LG,
            "padding": styles.SPACING_4,
        }
    )


# =============================================================================
# LABELING STUDIO PANEL
# =============================================================================

def dataset_row(dataset: HubDatasetModel) -> rx.Component:
    """Single dataset row - card click navigates to labeling."""
    
    # Type-specific icon for placeholder and badge
    type_icon_placeholder = rx.cond(
        dataset.type == "video",
        rx.icon("video", size=24, color=styles.EARTH_SIENNA),
        rx.icon("image", size=24, color=styles.ACCENT),
    )
    
    # Media type badge (overlay on thumbnail corner)
    media_type_badge = rx.box(
        rx.cond(
            dataset.type == "video",
            rx.icon("video", size=12, color="#FFFFFF"),
            rx.icon("image", size=12, color="#FFFFFF"),
        ),
        style={
            "position": "absolute",
            "bottom": "2px",
            "right": "2px",
            "background": rx.cond(dataset.type == "video", styles.EARTH_SIENNA, styles.EARTH_SAGE),
            "border_radius": "4px",
            "padding": "3px",
            "display": "flex",
            "align_items": "center",
            "justify_content": "center",
        },
    )
    
    # Thumbnail with fallback placeholder (80px to match projects, cyan border)
    thumbnail = rx.cond(
        dataset.thumbnail_url != "",
        # Has thumbnail - show image with media type badge
        rx.box(
            rx.image(
                src=dataset.thumbnail_url,
                width="80px",
                height="80px",
                object_fit="cover",
                border_radius=styles.RADIUS_MD,
                style={
                    "border": f"2px solid {styles.EARTH_SAGE}",  # Sage border for datasets
                },
            ),
            media_type_badge,
            style={
                "position": "relative",
                "flex_shrink": "0",
            },
        ),
        # No thumbnail - placeholder with type icon
        rx.box(
            rx.box(
                type_icon_placeholder,
                style={
                    "width": "80px",
                    "height": "80px",
                    "border_radius": styles.RADIUS_MD,
                    "background": f"linear-gradient(135deg, {styles.BG_TERTIARY} 0%, {styles.EARTH_SAGE}22 100%)",
                    "border": f"2px solid {styles.EARTH_SAGE}",  # Sage border for datasets
                    "display": "flex",
                    "align_items": "center",
                    "justify_content": "center",
                },
            ),
            media_type_badge,
            style={
                "position": "relative",
                "flex_shrink": "0",
            },
        ),
    )
    
    # Choose correct labeling route based on type
    label_route = rx.cond(
        dataset.type == "video",
        f"/projects/{HubState.active_project_id}/datasets/{dataset.id}/video-label",
        f"/projects/{HubState.active_project_id}/datasets/{dataset.id}/label",
    )
    
    # Upload route goes to dataset detail page
    upload_route = f"/projects/{HubState.active_project_id}/datasets/{dataset.id}"
    
    return rx.box(
        rx.hstack(
            thumbnail,
            # Middle section: name + edit + badges (matching project pattern)
            rx.vstack(
                # Dataset name with inline editing
                rx.cond(
                    HubState.editing_dataset_id == dataset.id,
                    # Edit mode: input field
                    rx.input(
                        value=HubState.editing_dataset_name,
                        on_change=HubState.set_editing_dataset_name,
                        on_key_down=HubState.handle_dataset_name_keydown,
                        on_blur=HubState.save_dataset_name,
                        on_click=rx.stop_propagation,
                        size="1",
                        auto_focus=True,
                        style={"min_width": "80px", "max_width": "150px"},
                    ),
                    # View mode: name + pencil icon
                    rx.hstack(
                        rx.text(
                            dataset.name,
                            size="2",
                            weight="medium",
                            style={"color": styles.TEXT_PRIMARY},
                            truncate=True,
                        ),
                        rx.icon_button(
                            rx.icon("pencil", size=10),
                            size="1",
                            variant="ghost",
                            color_scheme="gray",
                            on_click=[
                                rx.stop_propagation,
                                HubState.start_edit_dataset_name(dataset.id, dataset.name),
                            ],
                            style={
                                "opacity": "0",
                                "transition": "opacity 0.2s",
                                "padding": "2px",
                                "min_width": "18px",
                                "height": "18px",
                            },
                            class_name="edit-pencil",
                        ),
                        spacing="1",
                        align="center",
                        style={
                            "&:hover .edit-pencil": {"opacity": "0.6"},
                        },
                    ),
                ),
                # Type badge + progress count row (matching project's dataset count + class badges)
                rx.hstack(
                    # Type badge (Image/Video)
                    rx.cond(
                        dataset.type == "video",
                        rx.badge(
                            "Video",
                            variant="outline",
                            size="1",
                            color_scheme="gray",
                            style=styles.BADGE_MINI,
                        ),
                        rx.badge(
                            "Images",
                            variant="outline",
                            size="1",
                            color_scheme="green",
                            style=styles.BADGE_MINI,
                        ),
                    ),
                    # Progress badge
                    rx.badge(
                        dataset.labeled_count.to_string() + "/" + dataset.image_count.to_string(),
                        color_scheme=rx.cond(dataset.labeled_count > 0, "green", "gray"),
                        variant="outline",
                        size="1",
                        style=styles.BADGE_MINI,
                    ),
                    spacing="1",
                    align="center",
                    wrap="wrap",
                ),
                spacing="1",
                align="start",
                style={"flex": "1"},
            ),
            # Right section: Manage button + Delete (matching project pattern)
            rx.hstack(
                rx.link(
                    rx.button(
                        rx.icon("settings-2", size=12),
                        "Manage",
                        size="1",
                        variant="outline",
                        color_scheme="gray",
                        style={"min_width": "75px", "justify_content": "center"},
                    ),
                    href=upload_route,
                    on_click=rx.stop_propagation,
                ),
                rx.icon_button(
                    rx.icon("trash-2", size=14),
                    size="1",
                    variant="ghost",
                    color_scheme="gray",
                    on_click=[
                        rx.stop_propagation,
                        HubState.open_delete_dataset_modal(dataset.id, dataset.name),
                    ],
                    style={
                        "opacity": "0.5",
                        "&:hover": {"opacity": "1", "color": styles.ERROR},
                    },
                ),
                spacing="2",
                align="center",
            ),
            spacing="3",
            align="center",
            width="100%",
        ),
        on_click=rx.redirect(label_route),
        width="100%",
        style={
            "padding": "10px 12px",
            "border_radius": styles.RADIUS_MD,
            "border": f"1px solid {styles.BORDER}",
            "background": styles.BG_SECONDARY,
            "cursor": "pointer",
            "transition": styles.TRANSITION_FAST,
            "margin_bottom": "6px",
            "&:hover": {
                "background": styles.BG_TERTIARY,
                "border_color": styles.ACCENT,
            },
        }
    )



def labeling_studio_card() -> rx.Component:
    """Labeling studio panel showing datasets for active project."""
    return rx.box(
        rx.vstack(
            # Header (matching Projects style)
            rx.hstack(
                rx.icon("square-pen", size=18, color=styles.ACCENT),
                rx.text("Labeling Studio", size="3", weight="bold", style={"color": styles.TEXT_PRIMARY}),
                rx.spacer(),
                rx.cond(
                    HubState.has_active_project,
                    rx.button(
                        rx.icon("plus", size=14),
                        "Add Dataset",
                        size="1",
                        variant="outline",
                        on_click=HubState.open_dataset_modal,
                    ),
                    rx.fragment(),
                ),
                width="100%",
                align="center",
            ),
            rx.divider(style={"margin": f"{styles.SPACING_2} 0"}),
            
            # Content
            rx.cond(
                HubState.has_active_project,
                # Dataset list (or empty message)
                rx.cond(
                    HubState.has_datasets,
                    rx.scroll_area(
                        rx.vstack(
                            rx.foreach(HubState.active_project_datasets, dataset_row),
                            spacing="1",
                            width="100%",
                        ),
                        type="hover",
                        scrollbars="vertical",
                            style={"max_height": "300px"},
                    ),
                    rx.center(
                        rx.vstack(
                            rx.icon("database", size=24, style={"color": styles.TEXT_SECONDARY, "opacity": "0.5"}),
                            rx.text("No datasets yet", size="2", style={"color": styles.TEXT_SECONDARY}),
                            rx.button(
                                "Create First Dataset",
                                size="1",
                                on_click=HubState.open_dataset_modal,
                            ),
                            spacing="2",
                            align="center",
                        ),
                        style={"padding": styles.SPACING_4},
                    ),
                ),
                rx.center(
                    rx.text("Select a project to see datasets", size="2", style={"color": styles.TEXT_SECONDARY}),
                    style={"padding": styles.SPACING_6},
                ),
            ),
            
            spacing="2",
            width="100%",
        ),
        style={
            "background": styles.BG_SECONDARY,
            "border": f"1px solid {styles.BORDER}",
            "border_radius": styles.RADIUS_LG,
            "padding": styles.SPACING_4,
        }
    )


# =============================================================================
# TRAINING PIPELINE PANEL
# =============================================================================

def run_status_badge(status: str) -> rx.Component:
    """Status badge for training run."""
    return rx.match(
        status,
        ("pending", rx.badge("Pending", color_scheme="gray", size="1")),
        ("queued", rx.badge("Queued", color_scheme="green", size="1")),
        ("running", rx.badge("Running", color_scheme="yellow", size="1")),
        ("completed", rx.badge("Done", color_scheme="green", size="1")),
        ("failed", rx.badge("Failed", color_scheme="red", size="1")),
        rx.badge(status, color_scheme="gray", size="1"),
    )


def training_run_row(run: HubTrainingRunModel) -> rx.Component:
    """Single training run row with rich metrics display."""
    
    # Type badge (compact)
    type_badge = rx.cond(
        run.model_type == "classification",
        rx.badge("Cls", color_scheme="purple", size="1", variant="outline", style=styles.BADGE_MINI),
        rx.badge("Det", color_scheme="green", size="1", variant="outline", style=styles.BADGE_MINI),
    )
    
    # Display name: alias if set, else run_{id[:8]} (matching Training module pattern)
    display_name = rx.cond(
        run.alias != "",
        run.alias,
        "run_" + run.id[:8],
    )
    
    # Backbone badge (classification only - show CNX for convnext, YOLO for yolo)
    backbone_badge = rx.cond(
        run.model_type == "classification",
        rx.cond(
            run.backbone == "convnext",
            rx.badge("CNX", color_scheme="gray", size="1", variant="outline", style=styles.BADGE_MINI),
            rx.badge("YOLO", color_scheme="gray", size="1", variant="outline", style=styles.BADGE_MINI),
        ),
        rx.fragment(),  # No backbone badge for detection
    )
    
    # Secondary metrics for detection (P/R)
    secondary_metrics = rx.cond(
        (run.model_type == "detection") & (run.precision_str != ""),
        rx.hstack(
            rx.text(run.precision_str, size="1", style={"color": styles.TEXT_SECONDARY}),
            rx.text(run.recall_str, size="1", style={"color": styles.TEXT_SECONDARY}),
            spacing="1",
        ),
        rx.fragment(),
    )
    
    # Primary metric (mAP for detection, Accuracy for classification)
    primary_metric = rx.cond(
        run.model_type == "classification",
        rx.cond(
            run.accuracy_str != "",
            rx.text(run.accuracy_str, size="1", weight="bold", style={"color": styles.SUCCESS}),
            rx.text("-", size="1", style={"color": styles.TEXT_SECONDARY}),
        ),
        rx.cond(
            run.map_str != "",
            rx.text(run.map_str, size="1", weight="bold", style={"color": styles.SUCCESS}),
            rx.text("-", size="1", style={"color": styles.TEXT_SECONDARY}),
        ),
    )
    
    # Usage badges (show when model has been used)
    usage_badges = rx.hstack(
        rx.cond(
            run.used_in_playground,
            rx.tooltip(
                rx.icon("zap", size=12, color=styles.EARTH_TAUPE),
                content="Used in Playground",
            ),
            rx.fragment(),
        ),
        rx.cond(
            run.used_in_autolabel,
            rx.tooltip(
                rx.icon("tags", size=12, color=styles.ACCENT),
                content="Used in Autolabel",
            ),
            rx.fragment(),
        ),
        spacing="1",
    )
    
    return rx.hstack(
        type_badge,
        rx.text(
            display_name,
            size="2",
            weight="medium",
            style={"color": styles.TEXT_PRIMARY},
            truncate=True,
        ),
        backbone_badge,
        usage_badges,
        rx.spacer(),
        secondary_metrics,
        primary_metric,
        spacing="2",
        align="center",
        width="100%",
        on_click=rx.redirect(f"/projects/{HubState.active_project_id}/train/{run.id}"),
        style={
            "padding": "8px 10px",
            "border_radius": styles.RADIUS_SM,
            "cursor": "pointer",
            "&:hover": {"background": styles.BG_TERTIARY},
        }
    )


def training_pipeline_card() -> rx.Component:
    """Training pipeline panel with recent runs and action button."""
    return rx.box(
        rx.vstack(
            # Header (matching Projects style)
            rx.hstack(
                rx.icon("brain", size=18, color=styles.EARTH_SIENNA),
                rx.text("Training Pipeline", size="3", weight="bold", style={"color": styles.TEXT_PRIMARY}),
                rx.spacer(),
                rx.cond(
                    HubState.has_active_project,
                    rx.link(
                        rx.button(
                            rx.icon("play", size=14),
                            "Go to Training",
                            size="1",
                            variant="outline",
                        ),
                        href=f"/projects/{HubState.active_project_id}/train",
                    ),
                    rx.fragment(),
                ),
                width="100%",
                align="center",
            ),
            rx.divider(style={"margin": f"{styles.SPACING_2} 0"}),
            
            # Content
            rx.cond(
                HubState.has_active_project,
                # Recent runs section
                rx.cond(
                    HubState.has_runs,
                    rx.scroll_area(
                        rx.vstack(
                            rx.foreach(HubState.active_project_runs, training_run_row),
                            spacing="1",
                            width="100%",
                        ),
                        type="hover",
                        scrollbars="vertical",
                            style={"max_height": "300px"},
                    ),
                    rx.center(
                        rx.vstack(
                            rx.icon("brain", size=24, style={"color": styles.TEXT_SECONDARY, "opacity": "0.5"}),
                            rx.text("No training runs yet", size="2", style={"color": styles.TEXT_SECONDARY}),
                            spacing="2",
                            align="center",
                        ),
                        style={"padding": styles.SPACING_4},
                    ),
                ),
                rx.center(
                    rx.text("Select a project", size="2", style={"color": styles.TEXT_SECONDARY}),
                    style={"padding": styles.SPACING_6},
                ),
            ),
            
            spacing="2",
            width="100%",
        ),
        style={
            "background": styles.BG_SECONDARY,
            "border": f"1px solid {styles.BORDER}",
            "border_radius": styles.RADIUS_LG,
            "padding": styles.SPACING_4,
        }
    )


# =============================================================================
# INFERENCE API PANEL (Placeholder)
# =============================================================================

def inference_api_card() -> rx.Component:
    """Inference API panel with playground link."""
    return rx.box(
        rx.vstack(
            # Header with gradient
            rx.box(
                rx.hstack(
                    rx.icon("zap", size=24, color=styles.PURPLE),
                    rx.vstack(
                        rx.text("Inference Playground", size="3", weight="bold", style={"color": styles.TEXT_PRIMARY}),
                        rx.text("Test your trained models", size="1", style={"color": styles.TEXT_SECONDARY}),
                        spacing="0",
                        align="start",
                    ),
                    spacing="3",
                    align="center",
                    width="100%",
                ),
                style={
                    "background": f"linear-gradient(135deg, {styles.BG_SECONDARY} 0%, {styles.EARTH_TAUPE}15 100%)",
                    "padding": styles.SPACING_4,
                    "border_radius": f"{styles.RADIUS_LG} {styles.RADIUS_LG} 0 0",
                    "width": "100%",
                }
            ),
            
            # Content
            rx.box(
                rx.vstack(
                    rx.link(
                        rx.button(
                            rx.icon("play", size=14),
                            "Open Playground",
                            size="2",
                            style={"width": "100%"},
                        ),
                        href="/playground",
                        style={"width": "100%"},
                    ),
                    rx.text(
                        "Upload images and run real-time predictions",
                        size="1",
                        style={"color": styles.TEXT_SECONDARY, "text_align": "center"}
                    ),
                    spacing="2",
                    width="100%",
                ),
                style={"padding": styles.SPACING_3},
            ),
            
            spacing="0",
            width="100%",
        ),
        style={
            "background": styles.BG_SECONDARY,
            "border": f"1px solid {styles.BORDER}",
            "border_radius": styles.RADIUS_LG,
            "overflow": "hidden",
            "width": "360px",  # Match Projects column width
        }
    )


# =============================================================================
# MODALS
# =============================================================================

def new_project_modal() -> rx.Component:
    """Modal for creating a new project."""
    return rx.dialog.root(
        rx.dialog.content(
            rx.dialog.title("New Project"),
            rx.vstack(
                rx.input(
                    placeholder="Project name",
                    value=HubState.new_project_name,
                    on_change=HubState.set_new_project_name,
                    on_key_down=HubState.handle_new_project_keydown,
                    style={"width": "100%"},
                ),
                rx.text_area(
                    placeholder="Description (optional)",
                    value=HubState.new_project_description,
                    on_change=HubState.set_new_project_description,
                    rows="3",
                    style={"width": "100%"},
                ),
                rx.hstack(
                    rx.dialog.close(
                        rx.button("Cancel", variant="outline", color_scheme="gray"),
                    ),
                    rx.button(
                        "Create Project",
                        loading=HubState.is_creating_project,
                        on_click=HubState.create_project,
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
        open=HubState.show_new_project_modal,
        on_open_change=lambda open: HubState.set_show_new_project_modal(open),
    )


def delete_project_modal() -> rx.Component:
    """Modal for confirming project deletion."""
    return rx.dialog.root(
        rx.dialog.content(
            rx.dialog.title("Delete Project", style={"color": styles.ERROR}),
            rx.vstack(
                rx.text(
                    "This will permanently delete the project and all its datasets, images, and annotations.",
                    style={"color": styles.TEXT_SECONDARY}
                ),
                rx.box(
                    rx.text(HubState.delete_project_name, weight="bold", style={"color": styles.TEXT_PRIMARY}),
                    style={
                        "background": styles.BG_TERTIARY,
                        "padding": styles.SPACING_3,
                        "border_radius": styles.RADIUS_SM,
                        "width": "100%",
                    }
                ),
                rx.text("Type 'delete' to confirm:", size="2", style={"color": styles.TEXT_SECONDARY}),
                rx.input(
                    placeholder="delete",
                    value=HubState.delete_confirmation,
                    on_change=HubState.set_delete_confirmation,
                    on_key_down=HubState.handle_delete_project_keydown,
                    style={"width": "100%"},
                ),
                rx.hstack(
                    rx.dialog.close(
                        rx.button("Cancel", variant="outline", color_scheme="gray", on_click=HubState.close_delete_modal),
                    ),
                    rx.button(
                        "Delete Project",
                        color_scheme="red",
                        disabled=~HubState.can_delete,
                        loading=HubState.is_deleting,
                        on_click=HubState.confirm_delete_project,
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
        open=HubState.show_delete_modal,
    )


def new_dataset_modal() -> rx.Component:
    """Modal for creating a new dataset."""
    return rx.dialog.root(
        rx.dialog.content(
            rx.dialog.title("New Dataset"),
            rx.vstack(
                rx.input(
                    placeholder="Dataset name",
                    value=HubState.new_dataset_name,
                    on_change=HubState.set_dataset_name,
                    on_key_down=HubState.handle_new_dataset_keydown,
                    style={"width": "100%"},
                ),
                rx.select(
                    ["image", "video"],
                    value=HubState.new_dataset_type,
                    on_change=HubState.set_dataset_type,
                    style={"width": "100%"},
                ),
                rx.cond(
                    HubState.create_dataset_error != "",
                    rx.text(
                        HubState.create_dataset_error,
                        size="2",
                        style={"color": styles.ERROR}
                    ),
                    rx.fragment(),
                ),
                rx.hstack(
                    rx.dialog.close(
                        rx.button(
                            "Cancel",
                            variant="outline",
                            color_scheme="gray",
                            on_click=HubState.close_dataset_modal,
                        ),
                    ),
                    rx.button(
                        "Create",
                        on_click=HubState.create_dataset,
                        loading=HubState.is_creating_dataset,
                    ),
                    spacing="3",
                    justify="end",
                    width="100%",
                    margin_top=styles.SPACING_4,
                ),
                spacing="3",
                width="100%",
            ),
            style={
                "max_width": "400px",
            }
        ),
        open=HubState.show_dataset_modal,
    )


# =============================================================================
# LOADING STATE
# =============================================================================

def loading_skeleton() -> rx.Component:
    """Loading skeleton."""
    return rx.vstack(
        rx.hstack(
            rx.skeleton(rx.box(height="80px", width="100%"), loading=True),
            rx.skeleton(rx.box(height="80px", width="100%"), loading=True),
            rx.skeleton(rx.box(height="80px", width="100%"), loading=True),
            rx.skeleton(rx.box(height="80px", width="100%"), loading=True),
            spacing="3",
            width="100%",
        ),
        rx.hstack(
            rx.skeleton(rx.box(height="250px", width="100%"), loading=True),
            rx.skeleton(rx.box(height="250px", width="100%"), loading=True),
            rx.skeleton(rx.box(height="250px", width="100%"), loading=True),
            spacing="3",
            width="100%",
        ),
        spacing="4",
        width="100%",
        style={"padding": styles.SPACING_6},
    )


# =============================================================================
# MAIN LAYOUT
# =============================================================================

def hub_content() -> rx.Component:
    """Main hub content."""
    return rx.vstack(
        # Quick stats
        stats_row(),
        
        # Main grid: Project Manager + Module Panels
        rx.grid(
            # Left: Project Manager
            project_manager_card(),
            
            # Middle: Labeling Studio
            labeling_studio_card(),
            
            # Right: Training Pipeline
            training_pipeline_card(),
            
            columns="3",
            spacing="4",
            width="100%",
            style={
                "grid_template_columns": "1fr 1fr 1fr",  # Equal widths
            }
        ),
        
        # Bottom: Inference API (full width)
        inference_api_card(),
        
        spacing="4",
        width="100%",
        style={
            "padding": styles.SPACING_6,
            "max_width": "1400px",
            "margin": "0 auto",
        }
    )


def delete_dataset_modal() -> rx.Component:
    """Modal for confirming dataset deletion."""
    return rx.dialog.root(
        rx.dialog.content(
            rx.dialog.title("Delete Dataset", style={"color": styles.ERROR}),
            rx.vstack(
                rx.text(
                    "This will permanently delete the dataset and all its images/videos and annotations.",
                    style={"color": styles.TEXT_SECONDARY}
                ),
                rx.box(
                    rx.text(HubState.delete_dataset_name, weight="bold", style={"color": styles.TEXT_PRIMARY}),
                    style={
                        "background": styles.BG_TERTIARY,
                        "padding": styles.SPACING_3,
                        "border_radius": styles.RADIUS_SM,
                        "width": "100%",
                    }
                ),
                rx.text("Type 'delete' to confirm:", size="2", style={"color": styles.TEXT_SECONDARY}),
                rx.input(
                    placeholder="delete",
                    value=HubState.delete_dataset_confirmation,
                    on_change=HubState.set_delete_dataset_confirmation,
                    on_key_down=HubState.handle_delete_dataset_keydown,
                    style={"width": "100%"},
                ),
                rx.hstack(
                    rx.dialog.close(
                        rx.button("Cancel", variant="outline", color_scheme="gray", on_click=HubState.close_delete_dataset_modal),
                    ),
                    rx.button(
                        "Delete Dataset",
                        color_scheme="red",
                        disabled=~HubState.can_delete_dataset,
                        loading=HubState.is_deleting_dataset,
                        on_click=HubState.confirm_delete_dataset,
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
        open=HubState.show_delete_dataset_modal,
    )


def dashboard_content() -> rx.Component:
    """Full dashboard content with header."""
    return rx.box(
        nav_header(),
        rx.cond(
            HubState.is_loading,
            loading_skeleton(),
            hub_content(),
        ),
        projects_new_project_modal(),
        delete_project_modal(),
        new_dataset_modal(),
        delete_dataset_modal(),
        style={
            "background": styles.BG_PRIMARY,
            "min_height": "100vh",
        }
    )


@rx.page(route="/dashboard", title="Dashboard | SAFARI", on_load=[AuthState.check_auth, HubState.load_hub_data])
def dashboard_page() -> rx.Component:
    """The dashboard hub page (protected)."""
    return require_auth(dashboard_content())
