"""
Login Page — SAFARI split-panel authentication UI.

Left panel: Login form with SAFARI branding on cream background.
Right panel: Full-bleed wildlife hero photo.
"""

import reflex as rx
import styles
from app_state import AuthState

# Use centralized tokens from styles.py
LOGIN_BG = styles.BG_PRIMARY               # Warm cream
SAFARI_GREEN = styles.ACCENT               # CTA green
SAFARI_GREEN_HOVER = styles.ACCENT_HOVER   # CTA hover
SAFARI_BROWN = styles.HEADER_BG            # Text headings (brown)
LOGIN_TEXT = styles.TEXT_PRIMARY            # Body text
LOGIN_TEXT_DIM = styles.TEXT_SECONDARY      # Labels, secondary
LOGIN_BORDER = styles.BORDER               # Input borders
LOGIN_ERROR_BG = f"{styles.ERROR}08"                 # Error banner bg (light red)


class LoginFormState(rx.State):
    """Local state for the login form."""
    email: str = ""
    password: str = ""
    remember_me: bool = True

    def set_email(self, value: str):
        self.email = value

    def set_password(self, value: str):
        self.password = value

    def set_remember_me(self, value: bool):
        self.remember_me = value


def safari_login_logo() -> rx.Component:
    """Large SAFARI logo for the login page."""
    return rx.vstack(
        # Logo mark: [ ● SAFARI ]
        rx.hstack(
            rx.text(
                "[",
                style={
                    "color": SAFARI_BROWN,
                    "font_size": "36px",
                    "font_weight": "300",
                    "line_height": "1",
                }
            ),
            rx.box(
                style={
                    "width": "14px",
                    "height": "14px",
                    "border_radius": "50%",
                    "background": SAFARI_GREEN,
                    "flex_shrink": "0",
                }
            ),
            rx.text(
                "S A F A R I",
                style={
                    "color": SAFARI_BROWN,
                    "font_size": "28px",
                    "font_weight": "300",
                    "letter_spacing": "0.2em",
                    "line_height": "1",
                }
            ),
            rx.text(
                "]",
                style={
                    "color": SAFARI_BROWN,
                    "font_size": "36px",
                    "font_weight": "300",
                    "line_height": "1",
                }
            ),
            spacing="2",
            align="center",
        ),
        # Tagline
        rx.text(
            "SISTEMA DE ARMADILHAGEM",
            style={
                "color": LOGIN_TEXT_DIM,
                "font_size": "11px",
                "letter_spacing": "0.15em",
                "font_weight": "400",
            }
        ),
        rx.text(
            "FOTOGRÁFICA E ANÁLISE",
            style={
                "color": LOGIN_TEXT_DIM,
                "font_size": "11px",
                "letter_spacing": "0.15em",
                "font_weight": "400",
            }
        ),
        rx.text(
            "INTELIGENTE",
            style={
                "color": LOGIN_TEXT_DIM,
                "font_size": "11px",
                "letter_spacing": "0.15em",
                "font_weight": "400",
            }
        ),
        spacing="1",
        align="center",
    )


def login_form_panel() -> rx.Component:
    """Left panel — SAFARI branding + login form on cream background."""
    return rx.center(
        rx.vstack(
            # Logo
            safari_login_logo(),

            # Divider
            rx.box(
                style={
                    "width": "24px",
                    "height": "1px",
                    "background": LOGIN_TEXT_DIM,
                    "margin_top": styles.SPACING_6,
                    "margin_bottom": styles.SPACING_4,
                }
            ),

            # Sign In heading
            rx.heading(
                "Sign In into your Account",
                size="4",
                weight="medium",
                style={
                    "color": LOGIN_TEXT,
                    "margin_bottom": styles.SPACING_6,
                }
            ),

            # Login form
            rx.form(
                rx.vstack(
                    # Email input — outlined style
                    rx.box(
                        rx.el.input(
                            placeholder="Email",
                            type="email",
                            name="email",
                            value=LoginFormState.email,
                            on_change=LoginFormState.set_email,
                            style={
                                "width": "100%",
                                "padding": "14px 16px",
                                "background": "transparent",
                                "border": f"1px solid {LOGIN_BORDER}",
                                "border_radius": "4px",
                                "color": LOGIN_TEXT,
                                "font_size": "15px",
                                "outline": "none",
                                "box_sizing": "border-box",
                                "transition": "border-color 0.2s",
                                "&:focus": {
                                    "border_color": SAFARI_GREEN,
                                    "border_width": "2px",
                                    "padding": "13px 15px",
                                },
                                "&::placeholder": {
                                    "color": LOGIN_TEXT_DIM,
                                },
                            }
                        ),
                        width="100%",
                    ),

                    # Password input — outlined style
                    rx.box(
                        rx.el.input(
                            placeholder="Password",
                            type="password",
                            name="password",
                            value=LoginFormState.password,
                            on_change=LoginFormState.set_password,
                            style={
                                "width": "100%",
                                "padding": "14px 16px",
                                "background": "transparent",
                                "border": f"1px solid {LOGIN_BORDER}",
                                "border_radius": "4px",
                                "color": LOGIN_TEXT,
                                "font_size": "15px",
                                "outline": "none",
                                "box_sizing": "border-box",
                                "transition": "border-color 0.2s",
                                "&:focus": {
                                    "border_color": SAFARI_GREEN,
                                    "border_width": "2px",
                                    "padding": "13px 15px",
                                },
                                "&::placeholder": {
                                    "color": LOGIN_TEXT_DIM,
                                },
                            }
                        ),
                        width="100%",
                    ),

                    # Forgot password link
                    rx.box(
                        rx.text(
                            "Forgot your password?",
                            size="2",
                            style={
                                "color": SAFARI_GREEN,
                                "cursor": "pointer",
                                "&:hover": {"text_decoration": "underline"},
                            }
                        ),
                        width="100%",
                        text_align="left",
                    ),

                    # Error message
                    rx.cond(
                        AuthState.error_message != "",
                        rx.box(
                            rx.text(
                                AuthState.error_message,
                                size="2",
                                style={"color": styles.ERROR}
                            ),
                            style={
                                "background": LOGIN_ERROR_BG,
                                "border": f"1px solid {styles.ERROR}30",
                                "border_radius": "4px",
                                "padding": styles.SPACING_3,
                                "width": "100%",
                            }
                        ),
                    ),

                    # Sign In button — green CTA, ALL-CAPS
                    rx.button(
                        rx.cond(
                            AuthState.is_loading,
                            rx.hstack(
                                rx.spinner(size="1"),
                                rx.text("SIGNING IN..."),
                                spacing="2",
                            ),
                            rx.text("SIGN IN"),
                        ),
                        type="submit",
                        disabled=AuthState.is_loading,
                        style={
                            "width": "100%",
                            "background": SAFARI_GREEN,
                            "color": "white",
                            "padding": "14px",
                            "border_radius": "4px",
                            "font_weight": "500",
                            "font_size": "14px",
                            "letter_spacing": "0.08em",
                            "cursor": "pointer",
                            "transition": "background 0.2s",
                            "&:hover": {
                                "background": SAFARI_GREEN_HOVER,
                            },
                            "&:disabled": {
                                "opacity": "0.6",
                                "cursor": "not-allowed",
                            }
                        }
                    ),

                    spacing="4",
                    width="100%",
                ),
                on_submit=lambda form_data: AuthState.login(
                    LoginFormState.email,
                    LoginFormState.password,
                    LoginFormState.remember_me
                ),
                width="100%",
            ),

            spacing="1",
            width="100%",
            max_width="400px",
            align="center",
        ),
        style={
            "width": "50%",
            "min_height": "100vh",
            "background": LOGIN_BG,
            "padding": styles.SPACING_8,
        }
    )


def hero_photo_panel() -> rx.Component:
    """Right panel — full-bleed wildlife hero photo."""
    return rx.box(
        style={
            "width": "50%",
            "min_height": "100vh",
            "background_image": "url('/branding/lobo.jpg')",
            "background_size": "cover",
            "background_position": "center",
            "background_color": styles.ACCENT_HOVER,  # Fallback forest green if image not found
        }
    )


@rx.page(route="/login", title="Login | SAFARI", on_load=AuthState.check_auth)
def login_page() -> rx.Component:
    """The login page — split-panel layout."""
    return rx.box(
        # If already authenticated, redirect to dashboard
        rx.cond(
            AuthState.is_authenticated,
            rx.fragment(
                rx.script("window.location.href = '/dashboard';")
            ),
            rx.fragment(),
        ),
        rx.hstack(
            login_form_panel(),
            hero_photo_panel(),
            spacing="0",
            width="100%",
        ),
        # Script to restore session from storage if server state is lost
        # NOTE: localStorage keys still use safari_* — will be updated in Step 0.3
        rx.script(
            """
            (function() {
                // Check localStorage first, then sessionStorage
                let userId = localStorage.getItem('safari_user_id');
                let userEmail = localStorage.getItem('safari_user_email');
                let accessToken = localStorage.getItem('safari_access_token');
                
                if (!userId || !userEmail || !accessToken) {
                    userId = sessionStorage.getItem('safari_user_id');
                    userEmail = sessionStorage.getItem('safari_user_email');
                    accessToken = sessionStorage.getItem('safari_access_token');
                }
                
                if (userId && userEmail && accessToken) {
                    console.log('[SAFARI] Found stored session for:', userEmail);
                    // Redirect to dashboard since we have saved credentials
                    // The session will be restored on protected pages
                    window.location.href = '/dashboard';
                }
            })();
            """
        ),
        style={
            "min_height": "100vh",
            "overflow": "hidden",
        }
    )

