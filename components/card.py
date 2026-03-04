"""
Card Component — Reusable project card for grid displays.
"""

import reflex as rx
import styles
from typing import Callable


def project_card(
    project_id: rx.Var[str],
    name: rx.Var[str],
    dataset_count: rx.Var[int],
    created_at: rx.Var[str],
    on_delete: Callable = None,
) -> rx.Component:
    """
    A clickable project card for the projects grid.
    
    Args:
        project_id: UUID of the project (for navigation)
        name: Project display name
        dataset_count: Number of datasets in the project
        created_at: Date string (already truncated)
        on_delete: Optional callback for delete action
    """
    # Build the delete button - only if on_delete callback provided
    if on_delete:
        delete_button = rx.icon_button(
            rx.icon("trash-2", size=14),
            size="1",
            variant="ghost",
            color_scheme="red",
            on_click=[
                rx.stop_propagation,
                on_delete(project_id, name, dataset_count),
            ],
            style={
                "opacity": "0",
                "transition": styles.TRANSITION_FAST,
                "position": "absolute",
                "top": styles.SPACING_2,
                "right": styles.SPACING_2,
            },
            class_name="delete-btn",
        )
    else:
        delete_button = rx.fragment()
    
    return rx.box(
        delete_button,
        rx.vstack(
            # Project name
            rx.heading(
                name,
                size="4",
                weight="bold",
                style={"color": styles.TEXT_PRIMARY}
            ),
            
            # Metadata row
            rx.hstack(
                # Datasets badge
                rx.badge(
                    dataset_count.to_string() + " datasets",
                    variant="outline",
                    size="1",
                ),
                rx.spacer(),
                # Created date
                rx.text(
                    created_at,
                    size="1",
                    style={"color": styles.TEXT_SECONDARY}
                ),
                width="100%",
                align="center",
            ),
            
            spacing="3",
            align="start",
            width="100%",
        ),
        
        on_click=rx.redirect("/projects/" + project_id),
        
        style={
            "position": "relative",
            "background": styles.BG_SECONDARY,
            "border": f"1px solid {styles.BORDER}",
            "border_radius": styles.RADIUS_LG,
            "padding": styles.SPACING_6,
            "cursor": "pointer",
            "transition": styles.TRANSITION_FAST,
            "&:hover": {
                "background": styles.BG_TERTIARY,
                "transform": "scale(1.01)",
                "border_color": styles.ACCENT,
            },
            "&:hover .delete-btn": {
                "opacity": "1",
            },
        }
    )


def skeleton_card() -> rx.Component:
    """Loading skeleton placeholder for project cards."""
    return rx.box(
        rx.vstack(
            # Skeleton title
            rx.skeleton(
                rx.box(height="24px", width="60%"),
                loading=True,
            ),
            # Skeleton metadata
            rx.skeleton(
                rx.box(height="16px", width="40%"),
                loading=True,
            ),
            spacing="3",
            align="start",
            width="100%",
        ),
        style={
            "background": styles.BG_SECONDARY,
            "border": f"1px solid {styles.BORDER}",
            "border_radius": styles.RADIUS_LG,
            "padding": styles.SPACING_6,
        }
    )
