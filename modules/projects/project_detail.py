"""
Project Detail Page — View project with datasets.

Route: /projects/{project_id}
Shows annotation stats, datasets grid, and import tools.
"""

import reflex as rx
import styles
from app_state import require_auth, AuthState
from modules.datasets.state import DatasetsState
from modules.projects.models import DatasetModel
from modules.projects.project_detail_state import ProjectDetailState
from modules.admin.admin_state import AdminState


def project_header() -> rx.Component:
    """Header with project name and actions."""
    return rx.hstack(
        # Left side: Back + Icon + Title
        rx.hstack(
            rx.link(
                rx.icon(
                    "arrow-left",
                    size=20,
                    style={"color": styles.TEXT_SECONDARY}
                ),
                href="/dashboard",
                style={
                    "padding": styles.SPACING_2,
                    "border_radius": styles.RADIUS_MD,
                    "&:hover": {
                        "background": styles.BG_TERTIARY,
                    }
                }
            ),
            rx.icon("database", size=24, color=styles.ACCENT),
            rx.vstack(
                rx.hstack(
                    rx.heading(
                        DatasetsState.project_name,
                        size="7",
                        weight="bold",
                        style={"color": styles.TEXT_PRIMARY}
                    ),
                    rx.icon_button(
                        rx.icon("pen", size=14),
                        size="1",
                        variant="ghost",
                        on_click=DatasetsState.open_edit_project_modal,
                        style={
                            "color": styles.TEXT_SECONDARY,
                            "&:hover": {"color": styles.ACCENT},
                        }
                    ),
                    spacing="2",
                    align="center",
                ),
                rx.cond(
                    DatasetsState.project_description != "",
                    rx.text(
                        DatasetsState.project_description,
                        size="2",
                        style={"color": styles.TEXT_SECONDARY}
                    ),
                    rx.fragment(),
                ),
                spacing="1",
                align="start",
            ),
            spacing="3",
            align="center",
        ),
        rx.spacer(),
        rx.hstack(
            # "Company Project" toggle (visible to owner + admins)
            rx.cond(
                (DatasetsState.project_owner_id == AuthState.user_id) | AuthState.is_admin,
                rx.tooltip(
                    rx.hstack(
                        rx.switch(
                            checked=DatasetsState.is_team_project,
                            on_change=lambda _: DatasetsState.toggle_team_status(),
                            color_scheme="green",
                            size="1",
                            # Disable toggle-off for non-admins
                            disabled=DatasetsState.is_team_project & ~AuthState.is_admin,
                        ),
                        rx.text(
                            "Team",
                            size="2",
                            style={"color": styles.TEXT_SECONDARY},
                        ),
                        spacing="2",
                        align="center",
                        style={
                            "padding": f"{styles.SPACING_1} {styles.SPACING_3}",
                            "border": f"1px solid {styles.BORDER}",
                            "border_radius": styles.RADIUS_MD,
                        },
                    ),
                    content=rx.cond(
                        DatasetsState.is_team_project & ~AuthState.is_admin,
                        "Only admins can remove team status",
                        "Share this project with the team",
                    ),
                ),
                rx.fragment(),
            ),
            # Members button (admin only)
            rx.cond(
                AuthState.is_admin,
                rx.button(
                    rx.icon("users", size=16),
                    "Members",
                    variant="outline",
                    on_click=AdminState.load_project_members(
                        DatasetsState.current_project_id,
                        DatasetsState.is_team_project,
                    ),
                ),
                rx.fragment(),
            ),
            rx.link(
                rx.button(
                    rx.icon("plug", size=16),
                    "API",
                    variant="outline",
                ),
                href=f"/projects/{DatasetsState.current_project_id}/api",
            ),
            rx.link(
                rx.button(
                    rx.icon("brain", size=16),
                    "Train Model",
                    variant="outline",
                ),
                href=f"/projects/{DatasetsState.current_project_id}/train",
            ),
            spacing="2",
        ),
        width="100%",
        align="center",
        style={
            "padding": styles.SPACING_6,
            "border_bottom": f"1px solid {styles.BORDER}",
        }
    )


def member_row(member: dict) -> rx.Component:
    """Single member row in the sharing dialog."""
    return rx.hstack(
        rx.vstack(
            rx.text(
                member["email"],
                size="2",
                weight="medium",
                style={"color": styles.TEXT_PRIMARY},
            ),
            rx.text(
                member.get("display_name", ""),
                size="1",
                style={"color": styles.TEXT_SECONDARY},
            ),
            spacing="0",
        ),
        rx.spacer(),
        rx.badge(member.get("role", "member"), size="1", color_scheme="green"),
        rx.icon_button(
            rx.icon("x", size=12),
            size="1",
            variant="ghost",
            color_scheme="red",
            on_click=AdminState.remove_member(member["user_id"]),
        ),
        width="100%",
        align="center",
        style={
            "padding": "6px 10px",
            "border_radius": styles.RADIUS_SM,
            "border": f"1px solid {styles.BORDER}",
        },
    )


def available_user_row(user: dict) -> rx.Component:
    """User that can be added as member."""
    return rx.hstack(
        rx.text(user["email"], size="2", style={"color": styles.TEXT_PRIMARY}),
        rx.spacer(),
        rx.button(
            rx.icon("plus", size=12),
            "Add",
            size="1",
            variant="outline",
            color_scheme="green",
            on_click=AdminState.add_member(user["id"]),
        ),
        width="100%",
        align="center",
        style={
            "padding": "4px 10px",
            "border_radius": styles.RADIUS_SM,
        },
    )


def members_dialog() -> rx.Component:
    """Dialog for managing project members and company status."""
    return rx.dialog.root(
        rx.dialog.content(
            rx.dialog.title(
                rx.hstack(
                    rx.icon("users", size=18, color=styles.ACCENT),
                    rx.text("Project Members", weight="bold"),
                    spacing="2",
                    align="center",
                ),
            ),
            rx.dialog.description(
                "Manage who can access this project.",
                size="2",
                style={"color": styles.TEXT_SECONDARY},
            ),
            # Company project toggle
            rx.hstack(
                rx.text("Team Project", size="2", weight="medium"),
                rx.spacer(),
                rx.switch(
                    checked=AdminState.is_team_project,
                    on_change=lambda _: AdminState.toggle_team_project(),
                    color_scheme="green",
                ),
                width="100%",
                align="center",
                style={
                    "padding": "10px 12px",
                    "background": styles.BG_TERTIARY,
                    "border_radius": styles.RADIUS_MD,
                    "margin": "8px 0",
                },
            ),
            rx.separator(style={"margin": "8px 0"}),
            # Current members
            rx.vstack(
                rx.text("Current Members", size="2", weight="bold", style={"color": styles.TEXT_PRIMARY}),
                rx.cond(
                    AdminState.project_members.length() > 0,
                    rx.foreach(AdminState.project_members, member_row),
                    rx.text("No members yet", size="2", style={"color": styles.TEXT_SECONDARY}),
                ),
                spacing="2",
                width="100%",
            ),
            rx.separator(style={"margin": "8px 0"}),
            # Add members
            rx.vstack(
                rx.text("Add Members", size="2", weight="bold", style={"color": styles.TEXT_PRIMARY}),
                rx.cond(
                    AdminState.available_users.length() > 0,
                    rx.foreach(AdminState.available_users, available_user_row),
                    rx.text("No users available", size="2", style={"color": styles.TEXT_SECONDARY}),
                ),
                spacing="2",
                width="100%",
            ),
            rx.separator(style={"margin": "8px 0"}),
            rx.dialog.close(
                rx.button("Done", variant="outline", size="2"),
            ),
            style={"max_width": "480px"},
        ),
        open=AdminState.show_members_popover,
        on_open_change=lambda open: AdminState.close_members_popover(),
    )


def stat_card(icon: str, label: str, value: rx.Var, color: str = styles.ACCENT) -> rx.Component:
    """Individual stat metric card."""
    return rx.box(
        rx.vstack(
            rx.icon(icon, size=24, color=color),
            rx.text(
                value,
                size="6",
                weight="bold",
                style={"color": color},
            ),
            spacing="2",
            align="center",
            width="100%",
        ),
        style={
            "padding": styles.SPACING_4,
            "background": styles.BG_SECONDARY,
            "border": f"1px solid {styles.BORDER}",
            "border_radius": styles.RADIUS_LG,
            "flex": "1",
            "min_width": "0",
        },
    )


def stats_overview() -> rx.Component:
    """Stats overview cards showing key metrics."""
    return rx.grid(
        stat_card(
            "database",
            "Total Datasets",
            DatasetsState.datasets.length().to_string(),
            styles.ACCENT
        ),
        stat_card(
            "image",
            "Total Items",
            DatasetsState.total_items.to_string(),
            styles.SUCCESS
        ),
        stat_card(
            "check-check",
            "Progress",
            DatasetsState.labeling_progress.to_string() + "%",
            rx.cond(
                DatasetsState.labeling_progress >= 80,
                styles.SUCCESS,
                rx.cond(
                    DatasetsState.labeling_progress >= 50,
                    styles.WARNING,
                    styles.ERROR
                )
            )
        ),
        columns="3",
        spacing="3",
        width="100%",
    )


def class_distribution_bar(class_name: str, count: int, total: int, color: str) -> rx.Component:
    """Single class distribution bar."""
    percentage = (count / total * 100) if total > 0 else 0
    
    return rx.vstack(
        rx.hstack(
            rx.text(class_name, size="2", style={"color": styles.TEXT_PRIMARY}),
            rx.spacer(),
            rx.text(f"{count}", size="2", weight="medium", style={"color": color}),
            width="100%",
            align="center",
        ),
        rx.box(
            rx.box(
                height="8px",
                width=f"{percentage}%",
                background=color,
                border_radius=styles.RADIUS_SM,
                transition=styles.TRANSITION_FAST,
            ),
            height="8px",
            width="100%",
            background=styles.BG_TERTIARY,
            border_radius=styles.RADIUS_SM,
        ),
        spacing="1",
        width="100%",
    )


def dataset_progress_item(dataset: dict) -> rx.Component:
    """Single dataset progress item."""
    return rx.vstack(
        rx.hstack(
            rx.cond(
                dataset["type"] == "video",
                rx.icon("video", size=16, color=styles.WARNING),
                rx.icon("image", size=16, color=styles.SUCCESS),
            ),
            rx.text(
                dataset["dataset_name"],
                size="2",
                weight="medium",
                style={"color": styles.TEXT_PRIMARY}
            ),
            rx.spacer(),
            rx.badge(
                dataset['annotation_count'].to_string() + " labels",
                size="1",
                color_scheme="gray",
                variant="outline",
            ),
            width="100%",
            align="center",
        ),
        rx.hstack(
            rx.box(
                rx.box(
                    height="6px",
                    width=dataset["progress_pct"].to_string() + "%",
                    background=styles.SUCCESS,
                    border_radius=styles.RADIUS_SM,
                ),
                height="6px",
                width="100%",
                background=styles.BG_TERTIARY,
                border_radius=styles.RADIUS_SM,
                flex="1",
            ),
            rx.text(
                dataset["labeled_items"].to_string() + "/" + dataset["total_items"].to_string(),
                size="1",
                style={"color": styles.TEXT_SECONDARY, "min_width": "50px", "text_align": "right"}
            ),
            width="100%",
            align="center",
            spacing="2",
        ),
        spacing="1",
        width="100%",
        padding=styles.SPACING_2,
        _hover={"background": styles.BG_TERTIARY},
        border_radius=styles.RADIUS_SM,
        cursor="pointer",
    )


def annotation_stats_panel() -> rx.Component:
    """Left panel with annotation statistics."""
    return rx.box(
        rx.vstack(
            # Header
            rx.hstack(
                rx.icon("bar-chart-3", size=20, color=styles.ACCENT),
                rx.heading(
                    "Annotations",
                    size="5",
                    weight="bold",
                    style={"color": styles.TEXT_PRIMARY}
                ),
                spacing="2",
                align="center",
            ),
            
            rx.divider(style={"border_color": styles.BORDER}),
            
            # Stats overview
            stats_overview(),
            
            rx.divider(style={"border_color": styles.BORDER}),
            
            # Dataset breakdown
            rx.cond(
                DatasetsState.has_datasets,
                rx.vstack(
                    rx.text(
                        "Dataset Breakdown",
                        size="3",
                        weight="medium",
                        style={"color": styles.TEXT_PRIMARY}
                    ),
                    rx.vstack(
                        rx.foreach(
                            DatasetsState.dataset_breakdown,
                            dataset_progress_item
                        ),
                        spacing="1",
                        width="100%",
                        max_height="300px",
                        overflow_y="auto",
                    ),
                    spacing="2",
                    width="100%",
                ),
                rx.box(
                    rx.center(
                        rx.vstack(
                            rx.icon("inbox", size=32, style={"color": styles.TEXT_SECONDARY, "opacity": "0.5"}),
                            rx.text(
                                "No datasets yet",
                                size="2",
                                style={"color": styles.TEXT_SECONDARY}
                            ),
                            spacing="2",
                            align="center",
                        ),
                        padding=styles.SPACING_6,
                    ),
                ),
            ),
            
            spacing="4",
            width="100%",
        ),
        style={
            "padding": styles.SPACING_6,
            "background": styles.BG_SECONDARY,
            "border_radius": styles.RADIUS_LG,
            "border": f"1px solid {styles.BORDER}",
            "height": "fit-content",
            "position": "sticky",
            "top": styles.SPACING_4,
        },
    )


def class_distribution_panel() -> rx.Component:
    """Right panel showing class distribution chart."""
    return rx.box(
        rx.vstack(
            # Header
            rx.hstack(
                rx.icon("pie-chart", size=20, color=styles.ACCENT),
                rx.heading(
                    "Class Distribution",
                    size="5",
                    weight="bold",
                    style={"color": styles.TEXT_PRIMARY}
                ),
                spacing="2",
                align="center",
            ),
            
            rx.divider(style={"border_color": styles.BORDER}),
            
            # Chart or empty state
            rx.cond(
                DatasetsState.class_distribution_data.length() > 0,
                rx.recharts.bar_chart(
                    rx.recharts.bar(
                        data_key="count",
                        fill=styles.ACCENT,
                        radius=[0, 4, 4, 0],
                    ),
                    rx.recharts.x_axis(
                        data_key="class_name",
                        stroke=styles.TEXT_SECONDARY,
                        angle=-45,
                        text_anchor="end",
                        height=80,
                        tick={"fontSize": 10},
                    ),
                    rx.recharts.y_axis(
                        stroke=styles.TEXT_SECONDARY,
                        tick={"fontSize": 10},
                    ),
                    rx.recharts.graphing_tooltip(),
                    data=DatasetsState.class_distribution_data,
                    width="100%",
                    height=200,
                ),
                rx.center(
                    rx.vstack(
                        rx.icon("bar-chart-2", size=32, style={"color": styles.TEXT_SECONDARY, "opacity": "0.4"}),
                        rx.text(
                            "No annotations yet",
                            size="2",
                            style={"color": styles.TEXT_SECONDARY, "opacity": "0.7"}
                        ),
                        spacing="2",
                        align="center",
                    ),
                    min_height="120px",
                ),
            ),
            
            spacing="3",
            width="100%",
            style={"overflow": "hidden"},
        ),
        style={
            "padding": styles.SPACING_4,
            "background": styles.BG_SECONDARY,
            "border_radius": styles.RADIUS_LG,
            "border": f"1px solid {styles.BORDER}",
            "overflow": "hidden",
            "width": "100%",
        },
    )


def project_camera_info_panel() -> rx.Component:
    """Secondary panel showing camera/EXIF insights at the project level."""
    return rx.cond(
        DatasetsState.exif_total > 0,
        rx.box(
            rx.vstack(
                rx.hstack(
                    rx.icon("camera", size=16, color=styles.TEXT_SECONDARY),
                    rx.text("Camera Info", size="2", weight="medium", style={"color": styles.TEXT_SECONDARY}),
                    spacing="2",
                    align="center",
                ),
                # Camera models list
                rx.cond(
                    DatasetsState.exif_cameras.length() > 0,
                    rx.vstack(
                        rx.foreach(
                            DatasetsState.exif_cameras,
                            lambda cam: rx.hstack(
                                rx.text(
                                    cam["model"],
                                    size="2",
                                    style={"color": styles.TEXT_PRIMARY},
                                ),
                                rx.spacer(),
                                rx.text(
                                    cam["count"] + " images",
                                    size="1",
                                    style={"color": styles.TEXT_SECONDARY},
                                ),
                                width="100%",
                                align="center",
                                padding_y="2px",
                            ),
                        ),
                        spacing="0",
                        width="100%",
                    ),
                    rx.fragment(),
                ),
                # Date range
                rx.cond(
                    DatasetsState.exif_date_min.length() > 0,
                    rx.hstack(
                        rx.icon("calendar", size=14, color=styles.TEXT_SECONDARY),
                        rx.text(
                            DatasetsState.exif_date_min + " — " + DatasetsState.exif_date_max,
                            size="1",
                            style={"color": styles.TEXT_SECONDARY},
                        ),
                        spacing="2",
                        align="center",
                    ),
                    rx.fragment(),
                ),
                # Day/Night split
                rx.cond(
                    (DatasetsState.exif_day_count + DatasetsState.exif_night_count) > 0,
                    rx.hstack(
                        rx.icon("sun", size=14, color=styles.WARNING),
                        rx.text(
                            DatasetsState.exif_day_count.to(str) + " day",
                            size="1",
                            style={"color": styles.TEXT_SECONDARY},
                        ),
                        rx.text("·", size="1", style={"color": styles.TEXT_SECONDARY}),
                        rx.icon("moon", size=14, color=styles.TEXT_SECONDARY),
                        rx.text(
                            DatasetsState.exif_night_count.to(str) + " night",
                            size="1",
                            style={"color": styles.TEXT_SECONDARY},
                        ),
                        spacing="2",
                        align="center",
                    ),
                    rx.fragment(),
                ),
                spacing="3",
                width="100%",
            ),
            style={
                "padding": styles.SPACING_3,
                "background": styles.BG_SECONDARY,
                "border_radius": styles.RADIUS_LG,
                "border": f"1px solid {styles.BORDER}",
                "width": "100%",
                "opacity": "0.85",
            },
        ),
        rx.fragment(),
    )


def dataset_card(dataset: DatasetModel) -> rx.Component:
    """Single dataset card with thumbnail and type icon."""
    type_icon = rx.cond(
        dataset.type == "video",
        rx.icon("video", size=20, color=styles.WARNING),
        rx.icon("image", size=20, color=styles.ACCENT),
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
    
    # Thumbnail with fallback placeholder (80px, cyan border)
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
                    "border": f"2px solid {styles.EARTH_SAGE}",
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
                type_icon,
                style={
                    "width": "80px",
                    "height": "80px",
                    "border_radius": styles.RADIUS_MD,
                    "background": f"linear-gradient(135deg, {styles.BG_TERTIARY} 0%, {styles.EARTH_SAGE}22 100%)",
                    "border": f"2px solid {styles.EARTH_SAGE}",
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
    
    return rx.box(
        rx.link(
            rx.hstack(
                thumbnail,
                rx.vstack(
                    rx.text(
                        dataset.name,
                        size="3",
                        weight="medium",
                        style={"color": styles.TEXT_PRIMARY},
                        truncate=True,
                    ),
                    rx.hstack(
                        rx.badge(
                            dataset.type,
                            color_scheme=rx.cond(dataset.type == "video", "brown", "teal"),
                            variant="outline",
                            size="1",
                        ),
                        rx.badge(
                            dataset.usage_tag,
                            color_scheme=rx.cond(dataset.usage_tag == "validation", "gray", "teal"),
                            variant="outline",
                            size="1",
                        ),
                        rx.badge(
                            dataset.annotation_count.to_string() + " labels",
                            color_scheme="gray",
                            variant="outline",
                            size="1",
                        ),
                        spacing="2",
                    ),
                    rx.text(
                        dataset.created_at[:10],
                        size="1",
                        style={"color": styles.TEXT_SECONDARY, "opacity": "0.7"}
                    ),
                    spacing="1",
                    align="start",
                    flex="1",
                    style={"min_width": "0", "overflow": "hidden"},
                ),
                spacing="3",
                align="center",
                width="100%",
            ),
            href=f"/projects/{DatasetsState.current_project_id}/datasets/{dataset.id}",
            style={"text_decoration": "none", "width": "100%"},
        ),
        # Delete button (appears on hover)
        rx.icon_button(
            rx.icon("trash-2", size=14),
            size="1",
            variant="ghost",
            color_scheme="red",
            on_click=[
                rx.stop_propagation,
                DatasetsState.open_delete_modal(dataset.id, dataset.name, 0),
            ],
            style={
                "opacity": "0",
                "transition": styles.TRANSITION_FAST,
                "position": "absolute",
                "top": styles.SPACING_2,
                "right": styles.SPACING_2,
                "z_index": "10",
            },
            class_name="delete-btn",
        ),
        style={
            "position": "relative",
            "padding": styles.SPACING_3,
            "background": styles.BG_SECONDARY,
            "border": f"1px solid {styles.BORDER}",
            "border_radius": styles.RADIUS_LG,
            "transition": styles.TRANSITION_FAST,
            "&:hover": {
                "border_color": styles.ACCENT,
                "background": styles.BG_TERTIARY,
            },
            "&:hover .delete-btn": {
                "opacity": "1",
            }
        }
    )


def datasets_panel() -> rx.Component:
    """Main datasets panel with grid."""
    return rx.box(
        rx.vstack(
            # Header with actions
            rx.hstack(
                rx.hstack(
                    rx.icon("folder", size=20, color=styles.ACCENT),
                    rx.heading(
                        "Datasets",
                        size="5",
                        weight="bold",
                        style={"color": styles.TEXT_PRIMARY}
                    ),
                    rx.cond(
                        DatasetsState.has_datasets,
                        rx.badge(
                            DatasetsState.datasets.length().to_string(),
                            color_scheme="green",
                            variant="outline",
                        ),
                        rx.fragment(),
                    ),
                    spacing="2",
                    align="center",
                ),
                rx.spacer(),
                rx.hstack(
                    rx.button(
                        rx.icon("download", size=14),
                        "Export",
                        on_click=DatasetsState.open_export_modal,
                        variant="outline",
                        size="2",
                    ),
                    rx.button(
                        rx.icon("upload", size=14),
                        "Import",
                        on_click=DatasetsState.open_import_modal,
                        variant="outline",
                        size="2",
                    ),
                    rx.button(
                        rx.icon("plus", size=14),
                        "New Dataset",
                        on_click=DatasetsState.open_modal,
                        size="2",
                        style={
                            "background": styles.ACCENT,
                            "color": "white",
                            "&:hover": {"background": styles.ACCENT_HOVER},
                        }
                    ),
                    spacing="2",
                ),
                width="100%",
                align="center",
            ),
            
            rx.divider(style={"border_color": styles.BORDER}),
            
            # Dataset cards grid or empty state
            rx.cond(
                DatasetsState.has_datasets,
                rx.grid(
                    rx.foreach(
                        DatasetsState.datasets,
                        dataset_card
                    ),
                    columns="2",
                    spacing="3",
                    width="100%",
                    style={
                        "grid_template_columns": "repeat(auto-fill, minmax(280px, 1fr))",
                    }
                ),
                # Empty state
                rx.center(
                    rx.vstack(
                        rx.icon(
                            "folder-open",
                            size=48,
                            style={"color": styles.TEXT_SECONDARY, "opacity": "0.5"}
                        ),
                        rx.text(
                            "No datasets yet",
                            size="3",
                            weight="medium",
                            style={"color": styles.TEXT_PRIMARY}
                        ),
                        rx.text(
                            "Use the buttons above to create a dataset or import a YOLO ZIP",
                            size="2",
                            style={"color": styles.TEXT_SECONDARY, "text_align": "center"},
                        ),
                        spacing="2",
                        align="center",
                    ),
                    min_height="300px",
                    width="100%",
                ),
            ),
            
            spacing="4",
            width="100%",
        ),
        style={
            "padding": styles.SPACING_6,
            "background": styles.BG_SECONDARY,
            "border_radius": styles.RADIUS_LG,
            "border": f"1px solid {styles.BORDER}",
        },
    )


def import_modal() -> rx.Component:
    """Modal dialog for YOLO ZIP import."""
    return rx.dialog.root(
        rx.dialog.content(
            rx.dialog.title(
                rx.hstack(
                    rx.icon("upload", size=20, color=styles.ACCENT),
                    "Import YOLO Dataset",
                    spacing="2",
                    align="center",
                ),
            ),
            rx.vstack(
                rx.text(
                    "Import a complete YOLO dataset from a ZIP file containing images/ and labels/ folders.",
                    size="2",
                    style={"color": styles.TEXT_SECONDARY}
                ),
                
                # Upload zone
                rx.upload(
                    rx.vstack(
                        rx.icon("file-archive", size=36, style={"color": styles.TEXT_SECONDARY, "opacity": "0.6"}),
                        rx.text(
                            "Drop ZIP file here",
                            size="2",
                            weight="medium",
                            style={"color": styles.TEXT_PRIMARY}
                        ),
                        rx.text(
                            "or click to browse",
                            size="1",
                            style={"color": styles.TEXT_SECONDARY, "opacity": "0.7"}
                        ),
                        spacing="1",
                        align="center",
                    ),
                    id="dataset_zip",
                    accept={".zip": ["application/zip", "application/x-zip-compressed"]},
                    max_files=1,
                    border=f"2px dashed {styles.BORDER}",
                    border_radius=styles.RADIUS_MD,
                    padding=styles.SPACING_6,
                    width="100%",
                    cursor="pointer",
                    _hover={"border_color": styles.ACCENT, "background": styles.BG_TERTIARY},
                    transition=styles.TRANSITION_FAST,
                ),
                
                # Selected file preview
                rx.cond(
                    rx.selected_files("dataset_zip").length() > 0,
                    rx.hstack(
                        rx.icon("file-archive", size=14, color=styles.ACCENT),
                        rx.text(
                            rx.selected_files("dataset_zip")[0],
                            size="2",
                            style={
                                "color": styles.TEXT_PRIMARY,
                                "overflow": "hidden",
                                "text_overflow": "ellipsis",
                                "white_space": "nowrap",
                            }
                        ),
                        spacing="2",
                        align="center",
                        padding=styles.SPACING_3,
                        background=styles.BG_TERTIARY,
                        border_radius=styles.RADIUS_SM,
                        width="100%",
                    ),
                    rx.fragment(),
                ),
                
                # Progress indicator
                rx.cond(
                    DatasetsState.zip_upload_progress != "",
                    rx.hstack(
                        rx.spinner(size="2"),
                        rx.text(
                            DatasetsState.zip_upload_progress,
                            size="2",
                            style={"color": styles.TEXT_SECONDARY}
                        ),
                        spacing="2",
                        align="center",
                        width="100%",
                        padding=styles.SPACING_2,
                    ),
                    rx.fragment(),
                ),
                
                # Action buttons
                rx.hstack(
                    rx.dialog.close(
                        rx.button(
                            "Cancel",
                            variant="outline",
                            color_scheme="gray",
                            on_click=DatasetsState.close_import_modal,
                        ),
                    ),
                    rx.button(
                        rx.cond(
                            DatasetsState.is_uploading_zip,
                            rx.hstack(
                                rx.spinner(size="1"),
                                rx.text("Importing..."),
                                spacing="2",
                            ),
                            rx.hstack(
                                rx.icon("upload", size=14),
                                rx.text("Import Dataset"),
                                spacing="2",
                            ),
                        ),
                        on_click=lambda: DatasetsState.handle_zip_upload(
                            rx.upload_files(upload_id="dataset_zip")
                        ),
                        disabled=DatasetsState.is_uploading_zip,
                        style={
                            "background": styles.ACCENT,
                            "color": "white",
                            "&:hover": {"background": styles.ACCENT_HOVER},
                            "&:disabled": {"opacity": "0.5"},
                        },
                    ),
                    spacing="3",
                    justify="end",
                    width="100%",
                    margin_top=styles.SPACING_4,
                ),
                
                spacing="4",
                width="100%",
            ),
            style={"max_width": "480px"},
        ),
        open=DatasetsState.show_import_modal,
    )


def class_chip(class_name: str, idx: int) -> rx.Component:
    """Single class chip with edit/delete actions."""
    # When renaming is in progress, show locked state
    locked_chip = rx.hstack(
        rx.spinner(size="1"),
        rx.text(
            class_name,
            size="2",
            style={"color": styles.TEXT_SECONDARY}
        ),
        spacing="2",
        align="center",
        padding=styles.SPACING_2,
        padding_left=styles.SPACING_3,
        padding_right=styles.SPACING_3,
        background=styles.BG_TERTIARY,
        border_radius=styles.RADIUS_MD,
        style={"opacity": "0.6"},
    )
    
    # Normal display/edit chip
    normal_chip = rx.cond(
        ProjectDetailState.editing_class_idx == idx,
        # Editing mode
        rx.hstack(
            rx.input(
                value=ProjectDetailState.editing_class_name,
                on_change=ProjectDetailState.set_editing_class_name,
                on_key_down=ProjectDetailState.handle_edit_class_keydown,
                on_blur=ProjectDetailState.save_class_edit,
                size="1",
                style={"width": "120px"},
                auto_focus=True,
            ),
            spacing="1",
            align="center",
        ),
        # Display mode
        rx.hstack(
            rx.text(
                class_name,
                size="2",
                style={"color": styles.TEXT_PRIMARY}
            ),
            rx.hstack(
                rx.icon_button(
                    rx.icon("pen", size=10),
                    size="1",
                    variant="ghost",
                    on_click=lambda: ProjectDetailState.start_edit_class(idx),
                    style={
                        "opacity": "0",
                        "transition": styles.TRANSITION_FAST,
                    },
                    class_name="class-action-btn",
                ),
                rx.icon_button(
                    rx.icon("x", size=10),
                    size="1",
                    variant="ghost",
                    color_scheme="red",
                    on_click=lambda: ProjectDetailState.request_delete_class(idx),
                    style={
                        "opacity": "0",
                        "transition": styles.TRANSITION_FAST,
                    },
                    class_name="class-action-btn",
                ),
                spacing="0",
            ),
            spacing="2",
            align="center",
            padding=styles.SPACING_2,
            padding_left=styles.SPACING_3,
            padding_right=styles.SPACING_2,
            background=styles.BG_TERTIARY,
            border_radius=styles.RADIUS_MD,
            style={
                "&:hover .class-action-btn": {"opacity": "1"},
            },
        ),
    )
    
    return rx.cond(
        ProjectDetailState.is_renaming_class,
        locked_chip,
        normal_chip,
    )


def classes_panel() -> rx.Component:
    """Panel for managing project-wide classes."""
    return rx.box(
        rx.vstack(
            # Header
            rx.hstack(
                rx.icon("tags", size=20, color=styles.ACCENT),
                rx.heading(
                    "Classes",
                    size="5",
                    weight="bold",
                    style={"color": styles.TEXT_PRIMARY}
                ),
                rx.spacer(),
                rx.badge(
                    ProjectDetailState.project_classes.length().to_string(),
                    color_scheme="green",
                    variant="outline",
                ),
                width="100%",
                align="center",
            ),
            
            rx.divider(style={"border_color": styles.BORDER}),
            
            # Add new class input
            rx.hstack(
                rx.input(
                    placeholder="New class name",
                    value=ProjectDetailState.new_class_name,
                    on_change=ProjectDetailState.set_new_class_name,
                    on_key_down=ProjectDetailState.handle_add_class_keydown,
                    size="2",
                    style={"flex": "1"},
                ),
                rx.icon_button(
                    rx.icon("plus", size=16),
                    size="2",
                    on_click=ProjectDetailState.add_class,
                    style={
                        "background": styles.ACCENT,
                        "color": "white",
                    },
                ),
                spacing="2",
                width="100%",
            ),
            
            # Class list
            rx.cond(
                ProjectDetailState.project_classes.length() > 0,
                rx.box(
                    rx.foreach(
                        ProjectDetailState.project_classes,
                        lambda c, i: class_chip(c, i),
                    ),
                    style={
                        "display": "flex",
                        "flex_wrap": "wrap",
                        "gap": styles.SPACING_2,
                        "max_height": "200px",
                        "overflow_y": "auto",
                    },
                ),
                rx.center(
                    rx.text(
                        "No classes defined",
                        size="2",
                        style={"color": styles.TEXT_SECONDARY, "opacity": "0.7"}
                    ),
                    padding=styles.SPACING_4,
                ),
            ),
            
            spacing="3",
            width="100%",
        ),
        style={
            "padding": styles.SPACING_4,
            "background": styles.BG_SECONDARY,
            "border_radius": styles.RADIUS_LG,
            "border": f"1px solid {styles.BORDER}",
            "margin_top": styles.SPACING_4,
        },
    )


def delete_class_modal() -> rx.Component:
    """Delete confirmation modal for classes with type-to-confirm."""
    return rx.dialog.root(
        rx.dialog.content(
            rx.dialog.title(
                "Delete Class",
                style={"color": styles.ERROR}
            ),
            rx.vstack(
                rx.text(
                    "This action cannot be undone. The following will be permanently deleted:",
                    style={"color": styles.TEXT_SECONDARY}
                ),
                rx.box(
                    rx.vstack(
                        rx.hstack(
                            rx.icon("tag", size=16),
                            rx.text(
                                ProjectDetailState.class_to_delete_name,
                                weight="bold",
                                style={"color": styles.TEXT_PRIMARY}
                            ),
                            spacing="2",
                        ),
                        rx.text(
                            "• All annotations using this class",
                            size="2",
                            style={"color": styles.TEXT_SECONDARY, "padding_left": styles.SPACING_4}
                        ),
                        spacing="1",
                        align="start",
                    ),
                    style={
                        "background": styles.BG_TERTIARY,
                        "padding": styles.SPACING_3,
                        "border_radius": styles.RADIUS_SM,
                        "width": "100%",
                    }
                ),
                rx.text(
                    "Type 'delete' to confirm:",
                    size="2",
                    style={"color": styles.TEXT_SECONDARY, "margin_top": styles.SPACING_3}
                ),
                rx.input(
                    placeholder="delete",
                    value=ProjectDetailState.delete_class_confirmation_text,
                    on_change=ProjectDetailState.set_delete_class_confirmation_text,
                    on_key_down=ProjectDetailState.handle_delete_class_keydown,
                    style={"width": "100%"},
                ),
                rx.hstack(
                    rx.dialog.close(
                        rx.button(
                            "Cancel",
                            variant="outline",
                            color_scheme="gray",
                            on_click=ProjectDetailState.cancel_delete_class,
                        ),
                    ),
                    rx.button(
                        "Delete Class",
                        color_scheme="red",
                        disabled=~ProjectDetailState.can_confirm_delete_class,
                        on_click=ProjectDetailState.confirm_delete_class,
                    ),
                    spacing="3",
                    justify="end",
                    width="100%",
                    margin_top=styles.SPACING_4,
                ),
                spacing="3",
                width="100%",
            ),
            style={"max_width": "450px"},
        ),
        open=ProjectDetailState.show_delete_class_modal,
    )


def new_dataset_modal() -> rx.Component:
    """Modal for creating a new dataset."""
    return rx.dialog.root(
        rx.dialog.content(
            rx.dialog.title("New Dataset"),
            rx.vstack(
                rx.input(
                    placeholder="Dataset name",
                    value=DatasetsState.new_dataset_name,
                    on_change=DatasetsState.set_dataset_name,
                    on_key_down=DatasetsState.handle_create_dataset_keydown,
                    style={"width": "100%"},
                ),
                rx.select(
                    ["image", "video"],
                    value=DatasetsState.new_dataset_type,
                    on_change=DatasetsState.set_dataset_type,
                    style={"width": "100%"},
                ),
                rx.cond(
                    DatasetsState.create_error != "",
                    rx.text(
                        DatasetsState.create_error,
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
                            on_click=DatasetsState.close_modal,
                        ),
                    ),
                    rx.button(
                        "Create",
                        on_click=DatasetsState.create_dataset,
                        loading=DatasetsState.is_creating,
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
        open=DatasetsState.show_modal,
    )


def delete_dataset_modal() -> rx.Component:
    """Delete confirmation modal for datasets with type-to-confirm."""
    return rx.dialog.root(
        rx.dialog.content(
            rx.dialog.title(
                "Delete Dataset",
                style={"color": styles.ERROR}
            ),
            rx.vstack(
                rx.text(
                    "This action cannot be undone. The following will be permanently deleted:",
                    style={"color": styles.TEXT_SECONDARY}
                ),
                rx.box(
                    rx.vstack(
                        rx.hstack(
                            rx.icon("database", size=16),
                            rx.text(
                                DatasetsState.delete_dataset_name,
                                weight="bold",
                                style={"color": styles.TEXT_PRIMARY}
                            ),
                            spacing="2",
                        ),
                        rx.text(
                            "• All images in this dataset",
                            size="2",
                            style={"color": styles.TEXT_SECONDARY, "padding_left": styles.SPACING_4}
                        ),
                        rx.text(
                            "• All annotations and labels",
                            size="2",
                            style={"color": styles.TEXT_SECONDARY, "padding_left": styles.SPACING_4}
                        ),
                        spacing="1",
                        align="start",
                    ),
                    style={
                        "background": styles.BG_TERTIARY,
                        "padding": styles.SPACING_3,
                        "border_radius": styles.RADIUS_SM,
                        "width": "100%",
                    }
                ),
                rx.text(
                    "Type 'delete' to confirm:",
                    size="2",
                    style={"color": styles.TEXT_SECONDARY, "margin_top": styles.SPACING_3}
                ),
                rx.input(
                    placeholder="delete",
                    value=DatasetsState.delete_confirmation_text,
                    on_change=DatasetsState.set_delete_confirmation_text,
                    on_key_down=DatasetsState.handle_delete_dataset_keydown,
                    style={"width": "100%"},
                ),
                rx.cond(
                    DatasetsState.delete_error != "",
                    rx.text(
                        DatasetsState.delete_error,
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
                            on_click=DatasetsState.close_delete_modal,
                        ),
                    ),
                    rx.button(
                        "Delete Dataset",
                        color_scheme="red",
                        disabled=~DatasetsState.can_delete,
                        loading=DatasetsState.is_deleting,
                        on_click=DatasetsState.confirm_delete_dataset,
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
                "max_width": "450px",
            }
        ),
        open=DatasetsState.show_delete_modal,
    )


def loading_skeleton() -> rx.Component:
    """Loading skeleton for the page."""
    return rx.vstack(
        rx.skeleton(height="80px", width="100%"),
        rx.hstack(
            rx.skeleton(height="400px", width="320px"),
            rx.skeleton(height="400px", flex="1"),
            rx.skeleton(height="400px", width="320px"),
            spacing="4",
        ),
        spacing="4",
        padding=styles.SPACING_6,
        width="100%",
    )


def project_detail_content() -> rx.Component:
    """Main content for the project detail page."""
    return rx.cond(
        DatasetsState.is_loading,
        loading_skeleton(),
        rx.vstack(
            # Three-column layout: Stats | Datasets | Classes
            rx.grid(
                # Left: Annotation Stats
                annotation_stats_panel(),
                
                # Middle: Datasets Grid (main focus)
                datasets_panel(),
                
                # Right: Class Distribution & Management
                rx.vstack(
                    class_distribution_panel(),
                    classes_panel(),
                    project_camera_info_panel(),
                    spacing="4",
                    width="100%",
                ),
                
                columns="3",
                spacing="4",
                width="100%",
                style={
                    "grid_template_columns": "320px 1fr 320px",
                },
            ),
            
            # Modals
            new_dataset_modal(),
            delete_dataset_modal(),
            edit_project_modal(),

            delete_class_modal(),
            import_modal(),
            export_modal(),
            members_dialog(),
            
            spacing="4",
            width="100%",
        ),
    )



def project_detail_page_content() -> rx.Component:
    """Full page wrapper."""
    return rx.box(
        project_header(),
        rx.box(
            project_detail_content(),
            style={
                "padding": styles.SPACING_6,
                "max_width": "1600px",
                "margin": "0 auto",
            }
        ),
        style={
            "background": styles.BG_PRIMARY,
            "min_height": "100vh",
        }
    )




def edit_project_modal() -> rx.Component:
    """Modal for editing project details."""
    return rx.dialog.root(
        rx.dialog.content(
            rx.dialog.title("Edit Project"),
            rx.vstack(
                rx.input(
                    placeholder="Project name",
                    value=DatasetsState.edit_project_name,
                    on_change=DatasetsState.set_edit_project_name,
                    on_key_down=DatasetsState.handle_edit_project_keydown,
                    style={"width": "100%"},
                ),
                rx.text_area(
                    placeholder="Description (optional)",
                    value=DatasetsState.edit_project_description,
                    on_change=DatasetsState.set_edit_project_description,
                    rows="3",
                    style={"width": "100%"},
                ),
                rx.cond(
                    DatasetsState.edit_project_error != "",
                    rx.text(
                        DatasetsState.edit_project_error,
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
                            on_click=DatasetsState.close_edit_project_modal,
                        ),
                    ),
                    rx.button(
                        "Save",
                        on_click=DatasetsState.save_project_edits,
                        loading=DatasetsState.is_saving_project,
                        style={
                            "background": styles.ACCENT,
                            "color": "white",
                            "&:hover": {
                                "background": styles.ACCENT_HOVER,
                            }
                        }
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
                "max_width": "450px",
            }
        ),
        open=DatasetsState.show_edit_project_modal,
    )



def export_dataset_item(dataset: DatasetModel) -> rx.Component:
    """Single dataset item with checkbox for export selection."""
    return rx.hstack(
        rx.checkbox(
            checked=DatasetsState.export_selected_datasets.contains(dataset.id),
            on_change=lambda _: DatasetsState.toggle_dataset_selection(dataset.id),
        ),
        rx.hstack(
            rx.cond(
                dataset.type == "video",
                rx.icon("video", size=16, color=styles.WARNING),
                rx.icon("image", size=16, color=styles.ACCENT),
            ),
            rx.text(
                dataset.name,
                size="2",
                weight="medium",
                style={"color": styles.TEXT_PRIMARY}
            ),
            spacing="2",
            align="center",
        ),
        rx.spacer(),
        rx.badge(
            dataset.type,
            color_scheme=rx.cond(dataset.type == "video", "brown", "teal"),
            variant="outline",
            size="1",
        ),
        rx.badge(
            dataset.annotation_count.to_string() + " labels",
            color_scheme="gray",
            variant="outline",
            size="1",
        ),
        spacing="3",
        align="center",
        width="100%",
        padding=styles.SPACING_2,
        style={
            "border_radius": styles.RADIUS_SM,
            "&:hover": {"background": styles.BG_TERTIARY},
        }
    )


def export_modal() -> rx.Component:
    """Modal for exporting datasets to ZIP or another project."""
    return rx.dialog.root(
        rx.dialog.content(
            rx.dialog.title(
                rx.hstack(
                    rx.icon("download", size=20, color=styles.ACCENT),
                    "Export Datasets",
                    spacing="2",
                    align="center",
                ),
            ),
            rx.vstack(
                rx.text(
                    "Select datasets to export as a YOLO-formatted ZIP or copy to another project.",
                    size="2",
                    style={"color": styles.TEXT_SECONDARY}
                ),
                
                # Export mode selector
                rx.hstack(
                    rx.text("Export to:", size="2", weight="medium"),
                    rx.radio(
                        ["Download ZIP", "Another Project"],
                        value=rx.cond(
                            DatasetsState.export_mode == "download",
                            "Download ZIP",
                            "Another Project"
                        ),
                        on_change=lambda v: DatasetsState.set_export_mode(
                            rx.cond(v == "Download ZIP", "download", "project")
                        ),
                        direction="row",
                        spacing="4",
                    ),
                    spacing="3",
                    align="center",
                    width="100%",
                ),
                
                # Target project selector (shown when export to project mode)
                rx.cond(
                    DatasetsState.export_mode == "project",
                    rx.vstack(
                        rx.text("Target Project:", size="2", weight="medium"),
                        rx.cond(
                            DatasetsState.user_projects.length() > 0,
                            rx.select(
                                DatasetsState.export_target_project_options,
                                placeholder="Select a project...",
                                on_change=DatasetsState.set_export_target_by_name,
                                width="100%",
                            ),
                            rx.text(
                                "No other projects available",
                                size="2",
                                style={"color": styles.TEXT_SECONDARY, "fontStyle": "italic"}
                            ),
                        ),
                        spacing="2",
                        width="100%",
                        padding=styles.SPACING_2,
                        background=styles.BG_TERTIARY,
                        border_radius=styles.RADIUS_MD,
                    ),
                    rx.fragment(),
                ),

                
                # Dataset selection header
                rx.hstack(
                    rx.text("Select Datasets:", size="2", weight="medium"),
                    rx.spacer(),
                    rx.hstack(
                        rx.button(
                            "Select All",
                            size="1",
                            variant="ghost",
                            on_click=DatasetsState.select_all_datasets,
                        ),
                        rx.button(
                            "Select None",
                            size="1",
                            variant="ghost",
                            on_click=DatasetsState.select_no_datasets,
                        ),
                        spacing="1",
                    ),
                    width="100%",
                    align="center",
                ),
                
                # Dataset list with checkboxes
                rx.scroll_area(
                    rx.vstack(
                        rx.foreach(
                            DatasetsState.datasets,
                            export_dataset_item,
                        ),
                        spacing="1",
                        width="100%",
                    ),
                    type="auto",
                    scrollbars="vertical",
                    style={
                        "max_height": "250px",
                        "border": f"1px solid {styles.BORDER}",
                        "border_radius": styles.RADIUS_MD,
                        "padding": styles.SPACING_2,
                    },
                ),
                
                # Selection count
                rx.text(
                    rx.cond(
                        DatasetsState.export_selected_datasets.length() > 0,
                        DatasetsState.export_selected_datasets.length().to_string() + " dataset(s) selected",
                        "No datasets selected",
                    ),
                    size="1",
                    style={"color": styles.TEXT_SECONDARY}
                ),
                
                # Progress indicator
                rx.cond(
                    DatasetsState.export_progress != "",
                    rx.hstack(
                        rx.spinner(size="2"),
                        rx.text(
                            DatasetsState.export_progress,
                            size="2",
                            style={"color": styles.TEXT_SECONDARY}
                        ),
                        spacing="2",
                        align="center",
                        width="100%",
                    ),
                    rx.fragment(),
                ),
                
                # Action buttons
                rx.hstack(
                    rx.dialog.close(
                        rx.button(
                            "Cancel",
                            variant="outline",
                            color_scheme="gray",
                            on_click=DatasetsState.close_export_modal,
                        ),
                    ),
                    rx.cond(
                        DatasetsState.export_mode == "download",
                        rx.button(
                            rx.cond(
                                DatasetsState.is_exporting,
                                rx.hstack(
                                    rx.spinner(size="1"),
                                    rx.text("Exporting..."),
                                    spacing="2",
                                ),
                                rx.hstack(
                                    rx.icon("download", size=14),
                                    rx.text("Download ZIP"),
                                    spacing="2",
                                ),
                            ),
                            on_click=DatasetsState.download_yolo_zip,
                            disabled=~DatasetsState.can_export | DatasetsState.is_exporting,
                            style={
                                "background": styles.ACCENT,
                                "color": "white",
                                "&:hover": {"background": styles.ACCENT_HOVER},
                                "&:disabled": {"opacity": "0.5"},
                            },
                        ),
                        rx.button(
                            rx.cond(
                                DatasetsState.is_exporting,
                                rx.hstack(
                                    rx.spinner(size="1"),
                                    rx.text("Copying..."),
                                    spacing="2",
                                ),
                                rx.hstack(
                                    rx.icon("copy", size=14),
                                    rx.text("Copy to Project"),
                                    spacing="2",
                                ),
                            ),
                            on_click=DatasetsState.export_to_project,
                            disabled=~DatasetsState.can_export | DatasetsState.is_exporting,
                            style={
                                "background": styles.ACCENT,
                                "color": "white",
                                "&:hover": {"background": styles.ACCENT_HOVER},
                                "&:disabled": {"opacity": "0.5"},
                            },
                        ),
                    ),
                    spacing="3",
                    justify="end",
                    width="100%",
                    margin_top=styles.SPACING_4,
                ),
                
                spacing="4",
                width="100%",
            ),
            style={"max_width": "520px"},
        ),
        open=DatasetsState.show_export_modal,
    )


@rx.page(
    route="/projects/[project_id]",
    title="Project | SAFARI",
    on_load=[AuthState.check_auth, DatasetsState.load_project_and_datasets, ProjectDetailState.load_project]
)
def project_detail_page() -> rx.Component:
    """The project detail page (protected)."""
    return require_auth(project_detail_page_content())

