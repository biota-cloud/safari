"""
Compute Target Toggle — Reusable component for Cloud/Local GPU selection.

Usage:
    compute_target_toggle(
        value=State.compute_target,
        on_change=State.set_compute_target,
        machines=State.local_machines,
        selected_machine=State.selected_machine,
        on_machine_change=State.set_selected_machine,
    )
"""

import reflex as rx
import styles


def compute_target_toggle(
    value: rx.Var[str],
    on_change: callable,
    machines: rx.Var[list[dict]],
    selected_machine: rx.Var[str],
    on_machine_change: callable,
) -> rx.Component:
    """Compact compute target selector with machine dropdown.
    
    Args:
        value: Current target ("cloud" or "local")
        on_change: Callback when target changes
        machines: List of available local machines [{name, host}, ...]
        selected_machine: Currently selected machine name
        on_machine_change: Callback when machine changes
    """
    return rx.hstack(
        # Segmented control for Cloud/Local
        rx.segmented_control.root(
            rx.segmented_control.item(
                rx.hstack(
                    rx.icon("cloud", size=12),
                    rx.text("Cloud", size="1"),
                    spacing="1",
                    align="center",
                ),
                value="cloud",
            ),
            rx.segmented_control.item(
                rx.hstack(
                    rx.icon("monitor", size=12),
                    rx.text("Local GPU", size="1"),
                    spacing="1",
                    align="center",
                ),
                value="local",
            ),
            value=value,
            on_change=on_change,
            size="1",
            style={
                "background": styles.BG_TERTIARY,
            },
        ),
        
        # Machine dropdown (only when local selected)
        rx.cond(
            value == "local",
            rx.cond(
                machines.length() > 0,
                rx.select.root(
                    rx.select.trigger(
                        placeholder="Select machine...",
                        style={
                            "min_width": "120px",
                            "background": styles.BG_TERTIARY,
                            "border": f"1px solid {styles.BORDER}",
                            "border_radius": styles.RADIUS_SM,
                        }
                    ),
                    rx.select.content(
                        rx.foreach(
                            machines,
                            lambda m: rx.select.item(
                                rx.text(m["name"], size="2"),
                                value=m["name"],
                            ),
                        ),
                        style={"background": styles.BG_SECONDARY}
                    ),
                    value=selected_machine,
                    on_change=on_machine_change,
                    size="1",
                ),
                # No machines configured
                rx.hstack(
                    rx.icon("alert-triangle", size=12, style={"color": styles.WARNING}),
                    rx.text(
                        "No machines configured",
                        size="1",
                        style={"color": styles.WARNING},
                    ),
                    spacing="1",
                    align="center",
                ),
            ),
            rx.fragment(),
        ),
        
        spacing="2",
        align="center",
    )
