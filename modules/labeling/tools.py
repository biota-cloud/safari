
import reflex as rx
from .state import LabelingState
import styles

class Toolbar(rx.Component):
    """Toolbar component for the labeling editor."""
    
    @classmethod
    def create(cls) -> rx.Component:
        return rx.vstack(
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
                size="3",
                radius="full",
                cursor="pointer",
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
                size="3",
                radius="full",
                cursor="pointer",
            ),
            
            spacing="2",
            padding="4",
            bg=styles.BG_SECONDARY,
            border=f"1px solid {styles.BORDER}",
            border_radius="full",
            position="absolute",
            top="20px",
            right="20px", # Floating on top-right of canvas area? Or let parent position it.
            z_index="10",
        )
