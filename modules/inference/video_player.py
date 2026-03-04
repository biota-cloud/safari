"""
Inference Video Player — Playback component with synchronized label rendering.

Displays inference results (video + labels) with frame-accurate playback controls.
Labels are rendered dynamically on canvas overlay, not baked into video.
"""

import reflex as rx
import styles
from modules.inference.state import InferenceState


def video_player_with_labels() -> rx.Component:
    """Video player with canvas overlay for rendering bounding box labels."""
    
    return rx.box(
        # Video and canvas wrapper
        rx.box(
            # Video element (visible with native controls for now)
            rx.el.video(
                id="inference-video",
                src=InferenceState.current_result_video_url,
                style={
                    "width": "100%",
                    "height": "auto",
                    "max_height": "600px",
                    "display": "block",
                    "background": "#000",
                },
                controls=True,
                preload="auto",
                muted=True,
                playsinline=True,
            ),
            
            # Canvas overlay for labels (positioned absolutely over video)
            rx.el.canvas(
                id="inference-canvas",
                style={
                    "position": "absolute",
                    "top": "0",
                    "left": "0",
                    "width": "100%",
                    "height": "100%",
                    "pointer_events": "none",  # Allow clicks to pass through to video
                    "z_index": "10",
                }
            ),
            
            # Info overlay (top-right corner)
            rx.box(
                rx.vstack(
                    rx.hstack(
                        rx.text("Model:", size="1", weight="medium"),
                        rx.text(InferenceState.current_result_model_name, size="1"),
                        spacing="1",
                    ),
                    rx.hstack(
                        rx.text("Confidence:", size="1", weight="medium"),
                        rx.text(f"{InferenceState.current_result_confidence:.2f}", size="1"),
                        spacing="1",
                    ),
                    rx.hstack(
                        rx.text("Frame:", size="1", weight="medium"),
                        rx.text(InferenceState.current_frame_number, size="1", style={"font_family": "monospace"}),
                        spacing="1",
                    ),
                    spacing="1",
                ),
                position="absolute",
                top="12px",
                right="12px",
                padding=styles.SPACING_2,
                background="rgba(0, 0, 0, 0.7)",
                border_radius=styles.RADIUS_SM,
                style={
                    "backdrop_filter": "blur(4px)",
                    "color": styles.TEXT_PRIMARY,
                    "z_index": "20",
                },
            ),
            
            position="relative",
            width="100%",
            display="inline-block",
        ),
        
        width="100%",
        background="#000",
        border_radius=styles.RADIUS_MD,
        overflow="hidden",
    )


def playback_controls() -> rx.Component:
    """Playback controls for inference video (below player)."""
    
    return rx.hstack(
        # Play/Pause
        rx.icon_button(
            rx.cond(
                InferenceState.is_playing,
                rx.icon("pause", size=16),
                rx.icon("play", size=16),
            ),
            size="2",
            variant="solid",
            color_scheme="green",
            on_click=InferenceState.toggle_playback,
            title="Play/Pause (Space)",
            id="btn-inference-play-pause",
        ),
        
        # Frame step buttons
        rx.icon_button(
            rx.icon("chevron-left", size=14),
            size="1",
            variant="outline",
            on_click=lambda: InferenceState.step_frame(-1),
            title="Previous frame",
        ),
        rx.icon_button(
            rx.icon("chevron-right", size=14),
            size="1",
            variant="outline",
            on_click=lambda: InferenceState.step_frame(1),
            title="Next frame",
        ),
        
        rx.spacer(),
        
        # Speed control
        rx.text("Speed:", size="1", style={"color": styles.TEXT_SECONDARY}),
        rx.select(
            ["0.25x", "0.5x", "1x", "2x"],
            value=f"{InferenceState.playback_speed}x",
            on_change=InferenceState.set_playback_speed,
            size="1",
        ),
        
        spacing="2",
        align="center",
        width="100%",
        padding=styles.SPACING_2,
    )


def inference_video_player() -> rx.Component:
    """Complete inference video player with labels and controls."""
    
    return rx.vstack(
        video_player_with_labels(),
        playback_controls(),
        spacing="0",
        width="100%",
    )
