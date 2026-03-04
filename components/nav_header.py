"""
Nav Header — SAFARI global navigation header.

Brown header bar with [●] SAFARI logo and user controls.
Used across all authenticated pages.
"""

import reflex as rx
import styles
from app_state import AuthState
from modules.admin.admin_state import AdminState

# Use centralized tokens from styles.py
HEADER_BG = styles.HEADER_BG
HEADER_TEXT = styles.HEADER_TEXT
HEADER_TEXT_DIM = styles.HEADER_TEXT_DIM
SAFARI_GREEN = styles.ACCENT        # Logo dot green


def safari_logo() -> rx.Component:
    """
    SAFARI [●] logo mark — CSS recreation.
    
    Renders: [ ● S A F A R I ]
    Using text with wide letter-spacing. The A's render as standard A
    until official font assets arrive (the real logo uses crossbar-free A's).
    """
    return rx.hstack(
        # Left bracket
        rx.text(
            "[",
            style={
                "color": HEADER_TEXT,
                "font_size": "22px",
                "font_weight": "300",
                "line_height": "1",
            }
        ),
        # Green dot
        rx.box(
            style={
                "width": "10px",
                "height": "10px",
                "border_radius": "50%",
                "background": SAFARI_GREEN,
                "flex_shrink": "0",
            }
        ),
        # SAFARI text
        rx.text(
            "S A F A R I",
            style={
                "color": HEADER_TEXT,
                "font_size": "16px",
                "font_weight": "300",
                "letter_spacing": "0.15em",
                "line_height": "1",
            }
        ),
        # Right bracket
        rx.text(
            "]",
            style={
                "color": HEADER_TEXT,
                "font_size": "22px",
                "font_weight": "300",
                "line_height": "1",
            }
        ),
        spacing="2",
        align="center",
    )


def admin_user_row(user: dict) -> rx.Component:
    """Single user row in the admin modal."""
    return rx.hstack(
        rx.vstack(
            rx.text(
                user["email"],
                size="2",
                weight="medium",
                style={"color": styles.TEXT_PRIMARY},
            ),
            rx.text(
                user.get("display_name", ""),
                size="1",
                style={"color": styles.TEXT_SECONDARY},
            ),
            spacing="0",
        ),
        rx.spacer(),
        rx.cond(
            user["id"] == AuthState.user_id,
            # Can't demote yourself
            rx.badge("You", color_scheme="green", size="1"),
            # Toggle button
            rx.button(
                rx.cond(
                    user.get("role", "user") == "admin",
                    "Admin",
                    "User",
                ),
                size="1",
                variant=rx.cond(
                    user.get("role", "user") == "admin",
                    "solid",
                    "outline",
                ),
                color_scheme=rx.cond(
                    user.get("role", "user") == "admin",
                    "green",
                    "gray",
                ),
                on_click=AdminState.toggle_user_role(
                    user["id"], user.get("role", "user")
                ),
            ),
        ),
        width="100%",
        align="center",
        style={
            "padding": "8px 12px",
            "border_radius": styles.RADIUS_SM,
            "border": f"1px solid {styles.BORDER}",
        },
    )


def admin_modal() -> rx.Component:
    """Admin modal dialog for user management."""
    return rx.dialog.root(
        rx.dialog.content(
            rx.dialog.title(
                rx.hstack(
                    rx.icon("shield", size=18, color=styles.ACCENT),
                    rx.text("Admin Panel", weight="bold"),
                    spacing="2",
                    align="center",
                ),
            ),
            rx.dialog.description(
                "Manage user roles. Admins can access company projects and manage memberships.",
                size="2",
                style={"color": styles.TEXT_SECONDARY},
            ),
            rx.separator(style={"margin": "12px 0"}),
            rx.vstack(
                rx.text("Users", size="2", weight="bold", style={"color": styles.TEXT_PRIMARY}),
                rx.foreach(AdminState.admin_users, admin_user_row),
                spacing="2",
                width="100%",
            ),
            rx.separator(style={"margin": "12px 0"}),
            rx.dialog.close(
                rx.button("Close", variant="outline", size="2"),
            ),
            style={"max_width": "480px"},
        ),
        open=AdminState.show_admin_modal,
        on_open_change=lambda open: AdminState.close_admin_modal(),
    )


def user_menu() -> rx.Component:
    """User dropdown menu with admin panel access and sign out."""
    return rx.menu.root(
        rx.menu.trigger(
            rx.button(
                rx.text(
                    AuthState.user_email,
                    size="2",
                    style={"color": HEADER_TEXT_DIM},
                ),
                rx.icon("chevron-down", size=14, color=HEADER_TEXT_DIM),
                variant="ghost",
                size="1",
                style={
                    "cursor": "pointer",
                    "&:hover": {
                        "background": "rgba(255, 255, 255, 0.1)",
                    },
                },
            ),
        ),
        rx.menu.content(
            # Admin Panel (admin only)
            rx.cond(
                AuthState.is_admin,
                rx.menu.item(
                    rx.hstack(
                        rx.icon("shield", size=14),
                        rx.text("Admin Panel", size="2"),
                        spacing="2",
                        align="center",
                    ),
                    on_click=AdminState.open_admin_modal,
                ),
                rx.fragment(),
            ),
            rx.cond(
                AuthState.is_admin,
                rx.menu.separator(),
                rx.fragment(),
            ),
            # Sign Out
            rx.menu.item(
                rx.hstack(
                    rx.icon("log-out", size=14),
                    rx.text("Sign Out", size="2"),
                    spacing="2",
                    align="center",
                ),
                color="red",
                on_click=AuthState.logout,
            ),
        ),
    )


def nav_header(
    breadcrumb: rx.Component = None,
    show_user_menu: bool = True,
    show_logo: bool = True,
) -> rx.Component:
    """
    Global navigation header with SAFARI logo and optional breadcrumb.

    Args:
        breadcrumb: Optional breadcrumb component to show after logo
        show_user_menu: Whether to show user email and sign out button
        show_logo: Whether to show the SAFARI logo
    """
    return rx.fragment(
        rx.hstack(
            # Logo / Home link
            rx.cond(
                show_logo,
                rx.link(
                    safari_logo(),
                    href="/dashboard",
                    style={
                        "text_decoration": "none",
                        "&:hover": {"opacity": "0.85"},
                    },
                ),
                rx.fragment(),
            ),

            # Breadcrumb slot
            rx.cond(
                breadcrumb is not None,
                rx.hstack(
                    rx.icon("chevron-right", size=16, color=HEADER_TEXT_DIM),
                    breadcrumb,
                    spacing="2",
                    align="center",
                ),
                rx.fragment(),
            ) if breadcrumb else rx.fragment(),

            rx.spacer(),

            # User menu
            rx.cond(
                show_user_menu,
                user_menu(),
                rx.fragment(),
            ),

            width="100%",
            align="center",
            style={
                "padding": f"{styles.SPACING_3} {styles.SPACING_6}",
                "background": HEADER_BG,
                "position": "sticky",
                "top": "0",
                "z_index": "100",
            }
        ),
        # Admin modal (rendered once at top level, controlled by state)
        admin_modal(),
    )


def breadcrumb_link(text: str, href: str = None, is_current: bool = False) -> rx.Component:
    """Single breadcrumb item."""
    if is_current:
        return rx.text(
            text,
            size="2",
            weight="medium",
            style={"color": HEADER_TEXT}
        )

    return rx.link(
        rx.text(text, size="2", style={"color": HEADER_TEXT_DIM}),
        href=href or "#",
    )


def breadcrumb_separator() -> rx.Component:
    """Breadcrumb separator icon."""
    return rx.icon("chevron-right", size=14, color=HEADER_TEXT_DIM)

