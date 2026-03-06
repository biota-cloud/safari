"""
Brand Footer — Reusable branding footer component.

Sober, single-line footer for login and dashboard pages.
Not used on working areas (editors, labeling, training) to preserve screen space.
"""

import reflex as rx
import styles


def brand_footer(variant: str = "dashboard") -> rx.Component:
    """
    Branded footer with company attribution.

    Args:
        variant: "login" for cream bg with Biota logo, "dashboard" for text-only.
    """
    if variant == "login":
        return rx.hstack(
            rx.image(
                src="/branding/biota_logo_32h.png",
                alt="Biota",
                height="20px",
                style={"opacity": "0.7"},
            ),
            rx.box(
                style={
                    "width": "1px",
                    "height": "12px",
                    "background": styles.TEXT_SECONDARY,
                    "opacity": "0.3",
                }
            ),
            rx.text(
                "© 2026 Biota — All rights reserved",
                size="1",
                style={
                    "color": styles.TEXT_SECONDARY,
                    "font_size": "11px",
                },
            ),
            spacing="3",
            align="center",
            justify="center",
            style={
                "padding": f"{styles.SPACING_4} {styles.SPACING_6}",
                "width": "100%",
            },
        )

    # Dashboard variant — Biota logo + text, subtle
    return rx.hstack(
        rx.image(
            src="/branding/biota_logo_32h.png",
            alt="Biota",
            height="18px",
            style={"opacity": "0.6"},
        ),
        rx.box(
            style={
                "width": "1px",
                "height": "12px",
                "background": styles.TEXT_SECONDARY,
                "opacity": "0.3",
            }
        ),
        rx.text(
            "SAFARI · Biota © 2026",
            size="1",
            style={
                "color": styles.TEXT_SECONDARY,
                "font_size": "11px",
                "letter_spacing": "0.05em",
            },
        ),
        spacing="3",
        align="center",
        justify="center",
        style={
            "padding": f"{styles.SPACING_6} {styles.SPACING_6} {styles.SPACING_4}",
            "width": "100%",
        },
    )
