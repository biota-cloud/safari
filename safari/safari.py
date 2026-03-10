"""SAFARI — Sistema de Armadilhagem Fotográfica e Análise Inteligente."""

import os

import reflex as rx

import styles

# Import pages to register their routes
from modules.auth import login, dashboard  # noqa: F401
from modules.projects import projects, project_detail  # noqa: F401
from modules.labeling import editor as labeling_editor  # noqa: F401
from modules.labeling import video_editor as video_labeling_editor  # noqa: F401
from modules.training import dashboard as training_dashboard  # noqa: F401
from modules.training import run_detail as training_run_detail  # noqa: F401
from modules.inference import playground as inference_playground  # noqa: F401
from modules.inference import result_viewer as inference_result_viewer  # noqa: F401
from modules.api import page as api_settings  # noqa: F401
from modules.evaluation import page as evaluation_page  # noqa: F401



def index() -> rx.Component:
    """Root page — redirects to login or dashboard based on auth status."""
    return rx.box(
        # Check for existing session in storage and redirect accordingly
        rx.script(
            """
            (function() {
                // Check localStorage first, then sessionStorage
                let accessToken = localStorage.getItem('safari_access_token');
                
                if (!accessToken) {
                    accessToken = sessionStorage.getItem('safari_access_token');
                }
                
                if (accessToken) {
                    console.log('[SAFARI] Found stored session, redirecting to dashboard');
                    window.location.href = '/dashboard';
                } else {
                    console.log('[SAFARI] No stored session, redirecting to login');
                    window.location.href = '/login';
                }
            })();
            """
        ),
        style={
            "background": styles.BG_PRIMARY,
            "min_height": "100vh",
        }
    )


# App configuration with SAFARI Naturalist light theme
app = rx.App(
    theme=rx.theme(
        appearance="light",
        has_background=True,
        radius="medium",
        accent_color="green",
    ),
    style={
        "font_family": styles.FONT_FAMILY,
        "background": styles.BG_PRIMARY,
    },
    stylesheets=[
        "/safari_fonts.css",  # DM Sans + DM Serif Display (Google Fonts)
    ],
    # Load scripts globally for labeling editor
    head_components=[
        rx.script(src="/global_shortcuts.js"),  # Global shortcuts (H for dashboard)
        rx.script(src="/labeling_shortcuts.js"),  # Shortcuts config (load first)
        rx.script(src="/canvas.js"),
        rx.script(src="/inference_player.js"),  # Inference video playback
        rx.script(src="/selection_handler.js"),  # Long-press and range selection
        rx.script(src="/autoscroll.js"),  # Auto-scroll for log areas
        # Inject Supabase config from env vars so JS never needs hardcoded credentials
        rx.script(
            f"window.__SAFARI_CONFIG = {{"
            f"  supabaseUrl: '{os.environ.get('SUPABASE_URL', '')}',"
            f"  supabaseAnonKey: '{os.environ.get('SUPABASE_KEY', '')}'"
            f"}};"
        ),
        rx.script(src="/session_manager.js"),  # Token refresh & session stability
    ],
)
app.add_page(index, route="/")
