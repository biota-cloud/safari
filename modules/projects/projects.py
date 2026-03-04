"""
Projects Page — Grid view of all user projects.
"""

import reflex as rx
import styles
from app_state import require_auth, AuthState
from modules.projects.state import ProjectsState
from modules.projects.new_project_modal import new_project_modal
from components.card import project_card, skeleton_card
from components.nav_header import nav_header


def format_date(iso_string: str) -> str:
    """Format ISO date string to readable format."""
    if not iso_string:
        return ""
    # Simple format: just return the date part
    return iso_string[:10] if len(iso_string) >= 10 else iso_string


def projects_header() -> rx.Component:
    """Header with breadcrumb and title."""
    return rx.vstack(
        # Breadcrumb: Dashboard / Projects
        rx.hstack(
            rx.link(
                rx.hstack(
                    rx.icon("arrow-left", size=14),
                    rx.text("Dashboard", size="2"),
                    spacing="1",
                    align="center",
                ),
                href="/dashboard",
                style={"color": styles.TEXT_SECONDARY, "&:hover": {"color": styles.TEXT_PRIMARY}},
            ),
            rx.icon("chevron-right", size=14, color=styles.TEXT_SECONDARY),
            rx.text("Projects", size="2", weight="medium", style={"color": styles.TEXT_PRIMARY}),
            spacing="2",
            align="center",
        ),
        # Title row
        rx.hstack(
            rx.hstack(
                rx.icon("folder", size=24, color=styles.ACCENT),
                rx.heading(
                    "Projects",
                    size="7",
                    weight="bold",
                    style={"color": styles.TEXT_PRIMARY}
                ),
                spacing="3",
                align="center",
            ),
            rx.spacer(),
            rx.button(
                rx.icon("plus", size=16),
                rx.text("New Project"),
                on_click=ProjectsState.open_modal,
                style={
                    "background": styles.ACCENT,
                    "color": "white",
                    "padding_left": styles.SPACING_4,
                    "padding_right": styles.SPACING_4,
                    "&:hover": {
                        "background": styles.ACCENT_HOVER,
                    }
                }
            ),
            width="100%",
            align="center",
        ),
        spacing="3",
        width="100%",
        style={
            "padding": styles.SPACING_6,
            "border_bottom": f"1px solid {styles.BORDER}",
        }
    )


def loading_grid() -> rx.Component:
    """Grid of skeleton cards for loading state."""
    return rx.box(
        rx.grid(
            skeleton_card(),
            skeleton_card(),
            skeleton_card(),
            columns="3",
            spacing="4",
            width="100%",
            style={
                "grid_template_columns": "repeat(auto-fill, minmax(300px, 1fr))",
            }
        ),
        style={
            "padding": styles.SPACING_6,
        }
    )


def empty_state() -> rx.Component:
    """Empty state when user has no projects."""
    return rx.center(
        rx.vstack(
            rx.icon(
                "folder-open",
                size=64,
                style={"color": styles.TEXT_SECONDARY, "opacity": "0.5"}
            ),
            rx.heading(
                "No projects yet",
                size="5",
                style={"color": styles.TEXT_PRIMARY}
            ),
            rx.text(
                "Create your first project to start labeling images.",
                style={"color": styles.TEXT_SECONDARY}
            ),
            rx.button(
                rx.icon("plus", size=16),
                rx.text("Create Project"),
                on_click=ProjectsState.open_modal,
                style={
                    "background": styles.ACCENT,
                    "color": "white",
                    "margin_top": styles.SPACING_4,
                    "&:hover": {
                        "background": styles.ACCENT_HOVER,
                    }
                }
            ),
            spacing="3",
            align="center",
        ),
        style={
            "padding": styles.SPACING_12,
            "min_height": "400px",
        }
    )


def projects_grid() -> rx.Component:
    """Grid of project cards."""
    return rx.box(
        rx.grid(
            rx.foreach(
                ProjectsState.projects,
                lambda project: project_card(
                    project_id=project.id,
                    name=project.name,
                    dataset_count=project.dataset_count,
                    created_at=project.created_at[:10],
                    on_delete=ProjectsState.open_delete_modal,
                )
            ),
            columns="3",
            spacing="4",
            width="100%",
            style={
                "grid_template_columns": "repeat(auto-fill, minmax(300px, 1fr))",
            }
        ),
        style={
            "padding": styles.SPACING_6,
        }
    )


def delete_project_modal() -> rx.Component:
    """Delete confirmation modal with type-to-confirm."""
    return rx.dialog.root(
        rx.dialog.content(
            rx.dialog.title(
                "Delete Project",
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
                            rx.icon("folder", size=16),
                            rx.text(
                                ProjectsState.delete_project_name,
                                weight="bold",
                                style={"color": styles.TEXT_PRIMARY}
                            ),
                            spacing="2",
                        ),
                        rx.text(
                            f"• {ProjectsState.delete_project_dataset_count} dataset(s) and all their images",
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
                    value=ProjectsState.delete_confirmation_text,
                    on_change=ProjectsState.set_delete_confirmation_text,
                    on_key_down=ProjectsState.handle_delete_keydown,
                    style={"width": "100%"},
                ),
                rx.cond(
                    ProjectsState.delete_error != "",
                    rx.text(
                        ProjectsState.delete_error,
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
                            on_click=ProjectsState.close_delete_modal,
                        ),
                    ),
                    rx.button(
                        "Delete Project",
                        color_scheme="red",
                        disabled=~ProjectsState.can_delete,
                        loading=ProjectsState.is_deleting,
                        on_click=ProjectsState.confirm_delete_project,
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
        open=ProjectsState.show_delete_modal,
    )


def projects_content() -> rx.Component:
    """Main content area with conditional rendering."""
    return rx.cond(
        ProjectsState.is_loading,
        loading_grid(),
        rx.cond(
            ProjectsState.projects.length() == 0,
            empty_state(),
            projects_grid(),
        )
    )


def projects_page_content() -> rx.Component:
    """The full projects page content."""
    return rx.box(
        projects_header(),
        projects_content(),
        new_project_modal(),
        delete_project_modal(),
        style={
            "background": styles.BG_PRIMARY,
            "min_height": "100vh",
        }
    )


@rx.page(
    route="/projects",
    title="Projects | SAFARI",
    on_load=[AuthState.check_auth, ProjectsState.load_projects]
)
def projects_page() -> rx.Component:
    """The projects page (protected)."""
    return require_auth(projects_page_content())
