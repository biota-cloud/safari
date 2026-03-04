"""
New Project Modal — Dialog for creating a new project.
"""

import reflex as rx
import styles
from modules.projects.state import ProjectsState


def new_project_modal() -> rx.Component:
    """Modal dialog for creating a new project."""
    return rx.dialog.root(
        rx.dialog.content(
            rx.dialog.title(
                "New Project",
                style={"color": styles.TEXT_PRIMARY}
            ),
            rx.dialog.description(
                "Create a new detection project.",
                size="2",
                style={"color": styles.TEXT_SECONDARY, "margin_bottom": styles.SPACING_4}
            ),
            
            rx.vstack(
                # Project name input
                rx.box(
                    rx.text(
                        "Project Name",
                        size="2",
                        weight="medium",
                        style={"color": styles.TEXT_SECONDARY, "margin_bottom": styles.SPACING_1}
                    ),
                    rx.input(
                        placeholder="My Detection Project",
                        value=ProjectsState.new_project_name,
                        on_change=ProjectsState.set_project_name,
                        on_key_down=ProjectsState.handle_create_keydown,
                        size="3",
                        style={
                            "width": "100%",
                            "background": styles.BG_TERTIARY,
                            "border": f"1px solid {styles.BORDER}",
                            "border_radius": styles.RADIUS_SM,
                            "color": styles.TEXT_PRIMARY,
                            "&:focus": {
                                "border_color": styles.ACCENT,
                                "outline": "none",
                            }
                        }
                    ),
                    width="100%",
                ),
                
                # Description input
                rx.box(
                    rx.text(
                        "Description (optional)",
                        size="2",
                        weight="medium",
                        style={"color": styles.TEXT_SECONDARY, "margin_bottom": styles.SPACING_1}
                    ),
                    rx.text_area(
                        placeholder="A brief description of the project...",
                        value=ProjectsState.new_project_description,
                        on_change=ProjectsState.set_project_description,
                        rows="3",
                        style={
                            "width": "100%",
                            "background": styles.BG_TERTIARY,
                            "border": f"1px solid {styles.BORDER}",
                            "border_radius": styles.RADIUS_SM,
                            "color": styles.TEXT_PRIMARY,
                            "resize": "none",
                            "&:focus": {
                                "border_color": styles.ACCENT,
                                "outline": "none",
                            }
                        }
                    ),
                    width="100%",
                ),
                
                
                # Error message
                rx.cond(
                    ProjectsState.create_error != "",
                    rx.box(
                        rx.text(
                            ProjectsState.create_error,
                            size="2",
                            style={"color": styles.ERROR}
                        ),
                        style={
                            "background": f"{styles.ERROR}15",
                            "border": f"1px solid {styles.ERROR}30",
                            "border_radius": styles.RADIUS_SM,
                            "padding": styles.SPACING_3,
                            "width": "100%",
                        }
                    ),
                ),
                
                # Action buttons
                rx.hstack(
                    rx.dialog.close(
                        rx.button(
                            "Cancel",
                            variant="outline",
                            on_click=ProjectsState.close_modal,
                            style={
                                "border_color": styles.BORDER,
                                "color": styles.TEXT_SECONDARY,
                                "&:hover": {
                                    "background": styles.BG_TERTIARY,
                                }
                            }
                        ),
                    ),
                    rx.button(
                        rx.cond(
                            ProjectsState.is_creating,
                            rx.hstack(
                                rx.spinner(size="1"),
                                rx.text("Creating..."),
                                spacing="2",
                            ),
                            rx.text("Create Project"),
                        ),
                        on_click=ProjectsState.create_project,
                        disabled=~ProjectsState.can_create_project | ProjectsState.is_creating,
                        style={
                            "background": styles.ACCENT,
                            "color": "white",
                            "&:hover": {
                                "background": styles.ACCENT_HOVER,
                            },
                            "&:disabled": {
                                "opacity": "0.6",
                                "cursor": "not-allowed",
                            }
                        }
                    ),
                    spacing="3",
                    justify="end",
                    width="100%",
                    style={"margin_top": styles.SPACING_4}
                ),
                
                spacing="4",
                width="100%",
            ),
            
            style={
                "background": styles.BG_SECONDARY,
                "border": f"1px solid {styles.BORDER}",
                "border_radius": styles.RADIUS_LG,
                "max_width": "450px",
            }
        ),
        open=ProjectsState.show_modal,
    )
