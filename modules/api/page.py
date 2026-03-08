"""
API Settings Page — Manage API keys and models for a project.

Route: /projects/{project_id}/api
"""

import reflex as rx
import styles
from app_state import require_auth, AuthState
from modules.api.state import APIState, APIKeyModel, APIModelModel
from components.nav_header import nav_header


def breadcrumb_nav() -> rx.Component:
    """Breadcrumb navigation."""
    return rx.hstack(
        rx.link(
            rx.hstack(
                rx.icon("home", size=14),
                rx.text("Dashboard", size="2"),
                spacing="1",
                align="center",
            ),
            href="/dashboard",
            style={"color": styles.TEXT_SECONDARY, "&:hover": {"color": styles.ACCENT}},
        ),
        rx.icon("chevron-right", size=14, color=styles.TEXT_SECONDARY),
        rx.link(
            rx.text(APIState.project_name, size="2"),
            href=f"/projects/{APIState.current_project_id}",
            style={"color": styles.TEXT_SECONDARY, "&:hover": {"color": styles.ACCENT}},
        ),
        rx.icon("chevron-right", size=14, color=styles.TEXT_SECONDARY),
        rx.text("API", size="2", weight="medium", style={"color": styles.TEXT_PRIMARY}),
        spacing="2",
        align="center",
        style={
            "padding": f"{styles.SPACING_3} {styles.SPACING_6}",
            "border_bottom": f"1px solid {styles.BORDER}",
        }
    )


def page_header() -> rx.Component:
    """Page header with title and stats."""
    return rx.hstack(
        rx.hstack(
            rx.icon("plug", size=24, color=styles.ACCENT),
            rx.vstack(
                rx.heading(
                    "API Settings",
                    size="6",
                    weight="bold",
                    style={"color": styles.TEXT_PRIMARY}
                ),
                rx.text(
                    "Manage API keys and deployed models",
                    size="2",
                    style={"color": styles.TEXT_SECONDARY}
                ),
                spacing="0",
                align="start",
            ),
            spacing="3",
            align="center",
        ),
        rx.spacer(),
        # Quick stats
        rx.hstack(
            rx.vstack(
                rx.text(APIState.active_keys_count.to_string(), size="4", weight="bold", style={"color": styles.ACCENT}),
                rx.text("Active Keys", size="1", style={"color": styles.TEXT_SECONDARY}),
                spacing="0",
                align="center",
            ),
            rx.divider(orientation="vertical", style={"height": "40px", "border_color": styles.BORDER}),
            rx.vstack(
                rx.text(APIState.active_models_count.to_string(), size="4", weight="bold", style={"color": styles.SUCCESS}),
                rx.text("Models", size="1", style={"color": styles.TEXT_SECONDARY}),
                spacing="0",
                align="center",
            ),
            rx.divider(orientation="vertical", style={"height": "40px", "border_color": styles.BORDER}),
            rx.vstack(
                rx.text(APIState.total_requests.to_string(), size="4", weight="bold", style={"color": styles.WARNING}),
                rx.text("Requests", size="1", style={"color": styles.TEXT_SECONDARY}),
                spacing="0",
                align="center",
            ),
            spacing="4",
            align="center",
        ),
        width="100%",
        align="center",
        style={
            "padding": f"{styles.SPACING_4} {styles.SPACING_6}",
        }
    )


# =============================================================================
# API KEYS SECTION
# =============================================================================

def api_key_row(key: APIKeyModel) -> rx.Component:
    """Single API key row."""
    return rx.table.row(
        rx.table.cell(
            rx.hstack(
                rx.icon(
                    "key",
                    size=14,
                    color=rx.cond(key.is_active, styles.ACCENT, styles.TEXT_SECONDARY),
                ),
                rx.vstack(
                    rx.text(
                        key.name,
                        size="2",
                        weight="medium",
                        style={"color": styles.TEXT_PRIMARY},
                    ),
                    rx.code(
                        key.key_prefix,
                        size="1",
                        style={"color": styles.TEXT_SECONDARY},
                    ),
                    spacing="0",
                    align="start",
                ),
                spacing="2",
                align="center",
            ),
        ),
        rx.table.cell(
            rx.cond(
                key.is_active,
                rx.badge("Active", color_scheme="green", variant="outline", size="1"),
                rx.badge("Revoked", color_scheme="red", variant="outline", size="1"),
            ),
        ),
        rx.table.cell(
            rx.text(key.created_at, size="1", style={"color": styles.TEXT_SECONDARY}),
        ),
        rx.table.cell(
            rx.cond(
                key.last_used_at.is_not_none(),
                rx.text(key.last_used_at, size="1", style={"color": styles.TEXT_SECONDARY}),
                rx.text("Never", size="1", style={"color": styles.TEXT_SECONDARY, "opacity": "0.5"}),
            ),
        ),
        rx.table.cell(
            rx.text(
                f"{key.rate_limit_rpm}/min",
                size="1",
                style={"color": styles.TEXT_SECONDARY},
            ),
        ),
        rx.table.cell(
            rx.cond(
                key.is_active,
                rx.icon_button(
                    rx.icon("x", size=12),
                    size="1",
                    variant="ghost",
                    color_scheme="red",
                    on_click=APIState.open_revoke_modal(key.id, key.name),
                ),
                rx.fragment(),
            ),
        ),
    )


def api_keys_card() -> rx.Component:
    """Card showing API keys with create/revoke actions."""
    return rx.vstack(
        # Header
        rx.hstack(
            rx.icon("key-round", size=18, color=styles.ACCENT),
            rx.text("API Keys", size="3", weight="medium", style={"color": styles.TEXT_PRIMARY}),
            rx.spacer(),
            rx.button(
                rx.icon("plus", size=14),
                "New Key",
                size="1",
                on_click=APIState.open_create_key_modal,
                style={
                    "background": styles.ACCENT,
                    "color": "white",
                    "&:hover": {"background": styles.ACCENT_HOVER},
                },
            ),
            width="100%",
            align="center",
        ),
        rx.divider(style={"border_color": styles.BORDER, "margin": "8px 0"}),
        rx.text(
            "API keys authenticate requests to the Tyto API. Keep them secret!",
            size="1",
            style={"color": styles.TEXT_SECONDARY},
        ),
        
        # Keys table
        rx.cond(
            APIState.has_keys,
            rx.table.root(
                rx.table.header(
                    rx.table.row(
                        rx.table.column_header_cell("Key", style={"font_size": "11px"}),
                        rx.table.column_header_cell("Status", style={"font_size": "11px"}),
                        rx.table.column_header_cell("Created", style={"font_size": "11px"}),
                        rx.table.column_header_cell("Last Used", style={"font_size": "11px"}),
                        rx.table.column_header_cell("Rate Limit", style={"font_size": "11px"}),
                        rx.table.column_header_cell("", style={"font_size": "11px", "width": "40px"}),
                    ),
                ),
                rx.table.body(
                    rx.foreach(APIState.api_keys, api_key_row),
                ),
                variant="surface",
                size="1",
                style={"width": "100%"},
            ),
            # Empty state
            rx.center(
                rx.vstack(
                    rx.icon("key-round", size=32, style={"color": styles.TEXT_SECONDARY, "opacity": "0.4"}),
                    rx.text("No API keys yet", size="2", style={"color": styles.TEXT_SECONDARY}),
                    rx.text(
                        "Create a key to authenticate API requests",
                        size="1",
                        style={"color": styles.TEXT_SECONDARY, "opacity": "0.7"},
                    ),
                    spacing="2",
                    align="center",
                ),
                style={"padding": styles.SPACING_6},
            ),
        ),
        
        spacing="3",
        width="100%",
        style={
            "padding": styles.SPACING_4,
            "background": styles.BG_SECONDARY,
            "border": f"1px solid {styles.BORDER}",
            "border_radius": styles.RADIUS_LG,
        },
    )


# =============================================================================
# API MODELS SECTION
# =============================================================================

def api_model_row(model: APIModelModel) -> rx.Component:
    """Single API model row."""
    return rx.table.row(
        rx.table.cell(
            rx.hstack(
                rx.icon(
                    rx.cond(model.model_type == "classification", "tag", "target"),
                    size=14,
                    color=rx.cond(model.is_active, styles.SUCCESS, styles.TEXT_SECONDARY),
                ),
                rx.vstack(
                    rx.text(
                        model.display_name,
                        size="2",
                        weight="medium",
                        style={"color": styles.TEXT_PRIMARY},
                    ),
                    rx.code(
                        model.slug,
                        size="1",
                        style={"color": styles.ACCENT},
                    ),
                    spacing="0",
                    align="start",
                ),
                spacing="2",
                align="center",
            ),
        ),
        rx.table.cell(
            rx.badge(
                model.model_type,
                color_scheme=rx.cond(model.model_type == "classification", "purple", "blue"),
                variant="outline",
                size="1",
            ),
        ),
        # Backbone badge
        rx.table.cell(
            rx.badge(
                rx.cond(model.backbone == "convnext", "CNX", "YOLO"),
                color_scheme=rx.cond(model.backbone == "convnext", "teal", "brown"),
                variant="outline",
                size="1",
            ),
        ),
        rx.table.cell(
            rx.cond(
                model.is_active,
                rx.badge("Active", color_scheme="green", variant="outline", size="1"),
                rx.badge("Inactive", color_scheme="gray", variant="outline", size="1"),
            ),
        ),
        rx.table.cell(
            rx.text(
                f"{model.classes_snapshot.length()} classes",
                size="1",
                style={"color": styles.TEXT_SECONDARY},
            ),
        ),
        # SAM3 Confidence - only for classification models, edit on hover pencil click
        rx.table.cell(
            rx.cond(
                model.model_type == "classification",
                rx.cond(
                    # If this model is being edited, show input
                    APIState.editing_sam3_model_id == model.id,
                    rx.input(
                        value=APIState.editing_sam3_value,
                        type="number",
                        min="0",
                        max="1",
                        step="0.01",
                        size="1",
                        auto_focus=True,
                        on_change=APIState.set_editing_sam3_value,
                        on_blur=lambda _: APIState.update_model_sam3_confidence(model.id, APIState.editing_sam3_value),
                        on_key_up=lambda key: APIState.save_sam3_on_enter(model.id, key),
                        style={
                            "width": "60px",
                            "text_align": "center",
                            "font_size": "11px",
                        },
                    ),
                    # Display mode: show value with hover pencil
                    rx.hstack(
                        rx.text(
                            model.sam3_confidence.to_string(),
                            size="1",
                            style={"color": styles.TEXT_SECONDARY},
                        ),
                        rx.icon(
                            "pencil",
                            size=10,
                            color=styles.TEXT_SECONDARY,
                            on_click=APIState.start_editing_sam3(model.id, model.sam3_confidence),
                            style={
                                "cursor": "pointer",
                                "opacity": "0",
                                "transition": "opacity 0.15s",
                            },
                        ),
                        spacing="1",
                        align="center",
                        style={
                            "&:hover > svg": {"opacity": "1"},
                        },
                    ),
                ),
                rx.text("-", size="1", style={"color": styles.TEXT_SECONDARY, "opacity": "0.4"}),
            ),
        ),
        # SAM3 Resolution - only for classification models, edit on hover pencil click
        rx.table.cell(
            rx.cond(
                model.model_type == "classification",
                rx.cond(
                    APIState.editing_imgsz_model_id == model.id,
                    rx.input(
                        value=APIState.editing_imgsz_value,
                        type="number",
                        min="32",
                        max="2048",
                        step="1",
                        size="1",
                        auto_focus=True,
                        on_change=APIState.set_editing_imgsz_value,
                        on_blur=lambda _: APIState.update_model_sam3_imgsz(model.id, APIState.editing_imgsz_value),
                        on_key_up=lambda key: APIState.save_imgsz_on_enter(model.id, key),
                        style={
                            "width": "60px",
                            "text_align": "center",
                            "font_size": "11px",
                        },
                    ),
                    rx.hstack(
                        rx.text(
                            model.sam3_imgsz.to_string(),
                            size="1",
                            style={"color": styles.TEXT_SECONDARY},
                        ),
                        rx.icon(
                            "pencil",
                            size=10,
                            color=styles.TEXT_SECONDARY,
                            on_click=APIState.start_editing_imgsz(model.id, model.sam3_imgsz),
                            style={
                                "cursor": "pointer",
                                "opacity": "0",
                                "transition": "opacity 0.15s",
                            },
                        ),
                        spacing="1",
                        align="center",
                        style={
                            "&:hover > svg": {"opacity": "1"},
                        },
                    ),
                ),
                rx.text("-", size="1", style={"color": styles.TEXT_SECONDARY, "opacity": "0.4"}),
            ),
        ),
        rx.table.cell(
            rx.text(
                model.total_requests.to_string(),
                size="1",
                style={"color": styles.TEXT_SECONDARY},
            ),
        ),
        rx.table.cell(
            rx.text(model.created_at, size="1", style={"color": styles.TEXT_SECONDARY}),
        ),
        rx.table.cell(
            rx.cond(
                model.is_active,
                rx.icon_button(
                    rx.icon("power-off", size=12),
                    size="1",
                    variant="ghost",
                    color_scheme="red",
                    on_click=APIState.open_deactivate_modal(model.id, model.display_name),
                ),
                rx.fragment(),
            ),
        ),
    )


def api_models_card() -> rx.Component:
    """Card showing API models with usage stats."""
    return rx.vstack(
        # Header
        rx.hstack(
            rx.icon("box", size=18, color=styles.SUCCESS),
            rx.text("Deployed Models", size="3", weight="medium", style={"color": styles.TEXT_PRIMARY}),
            rx.spacer(),
            rx.link(
                rx.button(
                    rx.icon("brain", size=14),
                    "Train & Promote",
                    size="1",
                    variant="outline",
                ),
                href=f"/projects/{APIState.current_project_id}/train",
            ),
            width="100%",
            align="center",
        ),
        rx.divider(style={"border_color": styles.BORDER, "margin": "8px 0"}),
        rx.text(
            "Models promoted from training runs. Use the slug to call inference endpoints.",
            size="1",
            style={"color": styles.TEXT_SECONDARY},
        ),
        
        # Models table
        rx.cond(
            APIState.has_models,
            rx.table.root(
                rx.table.header(
                    rx.table.row(
                        rx.table.column_header_cell("Model", style={"font_size": "11px"}),
                        rx.table.column_header_cell("Type", style={"font_size": "11px"}),
                        rx.table.column_header_cell("Backbone", style={"font_size": "11px"}),
                        rx.table.column_header_cell("Status", style={"font_size": "11px"}),
                        rx.table.column_header_cell("Classes", style={"font_size": "11px"}),
                        rx.table.column_header_cell("SAM3 Conf", style={"font_size": "11px", "width": "70px"}),
                        rx.table.column_header_cell("SAM3 Res", style={"font_size": "11px", "width": "70px"}),
                        rx.table.column_header_cell("Requests", style={"font_size": "11px"}),
                        rx.table.column_header_cell("Created", style={"font_size": "11px"}),
                        rx.table.column_header_cell("", style={"font_size": "11px", "width": "40px"}),
                    ),
                ),
                rx.table.body(
                    rx.foreach(APIState.api_models, api_model_row),
                ),
                variant="surface",
                size="1",
                style={"width": "100%"},
            ),
            # Empty state
            rx.center(
                rx.vstack(
                    rx.icon("box", size=32, style={"color": styles.TEXT_SECONDARY, "opacity": "0.4"}),
                    rx.text("No models deployed", size="2", style={"color": styles.TEXT_SECONDARY}),
                    rx.text(
                        "Promote a training run to make it available via API",
                        size="1",
                        style={"color": styles.TEXT_SECONDARY, "opacity": "0.7"},
                    ),
                    rx.link(
                        rx.button(
                            rx.icon("brain", size=14),
                            "Go to Training",
                            size="1",
                            variant="outline",
                            style={"margin_top": styles.SPACING_2},
                        ),
                        href=f"/projects/{APIState.current_project_id}/train",
                    ),
                    spacing="2",
                    align="center",
                ),
                style={"padding": styles.SPACING_6},
            ),
        ),
        
        spacing="3",
        width="100%",
        style={
            "padding": styles.SPACING_4,
            "background": styles.BG_SECONDARY,
            "border": f"1px solid {styles.BORDER}",
            "border_radius": styles.RADIUS_LG,
        },
    )


# =============================================================================
# QUICK START GUIDE
# =============================================================================

def quick_start_card() -> rx.Component:
    """Card with API quick start instructions."""
    return rx.vstack(
        rx.hstack(
            rx.icon("book-open", size=18, color=styles.WARNING),
            rx.text("Quick Start", size="3", weight="medium", style={"color": styles.TEXT_PRIMARY}),
            width="100%",
            align="center",
        ),
        rx.divider(style={"border_color": styles.BORDER, "margin": "8px 0"}),
        
        # Code example
        rx.vstack(
            rx.text("1. Create an API key above", size="2", style={"color": styles.TEXT_SECONDARY}),
            rx.text("2. Promote a trained model from the Training page", size="2", style={"color": styles.TEXT_SECONDARY}),
            rx.text("3. Use the following request format:", size="2", style={"color": styles.TEXT_SECONDARY}),
            spacing="1",
            width="100%",
            align="start",
        ),
        
        rx.box(
            rx.code_block(
                """curl -X POST \\
  -H "Authorization: Bearer safari_xxxx..." \\
  -F "file=@image.jpg" \\
  https://api.tyto.app/v1/infer/{model_slug}""",
                language="bash",
                show_line_numbers=False,
                style={
                    "background": styles.BG_TERTIARY,
                    "border_radius": styles.RADIUS_SM,
                    "font_size": "12px",
                },
            ),
            width="100%",
        ),
        
        rx.text(
            "Replace {model_slug} with your model's slug (e.g., lynx-detector-v1)",
            size="1",
            style={"color": styles.TEXT_SECONDARY, "font_style": "italic"},
        ),
        
        spacing="3",
        width="100%",
        style={
            "padding": styles.SPACING_4,
            "background": styles.BG_SECONDARY,
            "border": f"1px solid {styles.BORDER}",
            "border_radius": styles.RADIUS_LG,
        },
    )


# =============================================================================
# MODALS
# =============================================================================

def create_key_modal() -> rx.Component:
    """Modal for creating a new API key."""
    return rx.dialog.root(
        rx.dialog.content(
            rx.dialog.title(
                rx.hstack(
                    rx.icon("key-round", size=18, color=styles.ACCENT),
                    rx.text("Create API Key"),
                    spacing="2",
                    align="center",
                ),
            ),
            rx.cond(
                APIState.new_key_created,
                # Success state - show the raw key prominently
                rx.vstack(
                    rx.hstack(
                        rx.icon("alert-triangle", size=18, color="#b45309"),
                        rx.text(
                            "Your API key has been created. Copy it now — you won't be able to see it again!",
                            size="2",
                            weight="medium",
                            style={"color": "#92400e"},
                        ),
                        spacing="2",
                        align="start",
                        style={
                            "width": "100%",
                            "padding": styles.SPACING_3,
                            "background": "#fef3c7",
                            "border": "1px solid #f59e0b",
                            "border_radius": styles.RADIUS_SM,
                        },
                    ),
                    # Key display - stacked vertically for full visibility
                    rx.vstack(
                        rx.text("Your API Key:", size="2", weight="medium", style={"color": styles.TEXT_PRIMARY}),
                        rx.box(
                            rx.text(
                                APIState.new_key_raw,
                                size="2",
                                style={
                                    "word_break": "break_all",
                                    "color": styles.SUCCESS,
                                    "font_family": styles.FONT_FAMILY_MONO,
                                    "line_height": "1.5",
                                },
                            ),
                            style={
                                "padding": styles.SPACING_4,
                                "background": styles.BG_TERTIARY,
                                "border_radius": styles.RADIUS_SM,
                                "border": f"1px solid {styles.BORDER}",
                                "width": "100%",
                            },
                        ),
                        # Copy button - full width and prominent
                        rx.button(
                            rx.icon("copy", size=14),
                            "Copy to Clipboard",
                            size="2",
                            variant="outline",
                            color_scheme="green",
                            on_click=rx.set_clipboard(APIState.new_key_raw),
                            style={"width": "100%"},
                        ),
                        spacing="2",
                        width="100%",
                    ),
                    rx.hstack(
                        rx.dialog.close(
                            rx.button(
                                "Done",
                                on_click=APIState.close_create_key_modal,
                                style={
                                    "background": styles.ACCENT,
                                    "color": "white",
                                    "&:hover": {"background": styles.ACCENT_HOVER},
                                },
                            ),
                        ),
                        justify="end",
                        width="100%",
                    ),
                    spacing="4",
                    width="100%",
                ),
                # Input state
                rx.vstack(
                    rx.text(
                        "Give your API key a descriptive name to identify it later.",
                        size="2",
                        style={"color": styles.TEXT_SECONDARY},
                    ),
                    rx.vstack(
                        rx.text("Key Name", size="1", weight="medium"),
                        rx.input(
                            placeholder="e.g., Production Key, Mobile App",
                            value=APIState.new_key_name,
                            on_change=APIState.set_new_key_name,
                            style={"width": "100%"},
                        ),
                        spacing="1",
                        width="100%",
                    ),
                    rx.hstack(
                        rx.dialog.close(
                            rx.button(
                                "Cancel",
                                variant="outline",
                                color_scheme="gray",
                                on_click=APIState.close_create_key_modal,
                            ),
                        ),
                        rx.button(
                            rx.cond(
                                APIState.is_creating_key,
                                rx.spinner(size="1"),
                                rx.icon("plus", size=14),
                            ),
                            "Create Key",
                            disabled=~APIState.can_create_key,
                            loading=APIState.is_creating_key,
                            on_click=APIState.create_new_key,
                            style={
                                "background": styles.ACCENT,
                                "color": "white",
                                "&:hover": {"background": styles.ACCENT_HOVER},
                            },
                        ),
                        spacing="3",
                        justify="end",
                        width="100%",
                    ),
                    spacing="4",
                    width="100%",
                ),
            ),
            style={"max_width": "560px", "width": "90vw"},
        ),
        open=APIState.show_create_key_modal,
    )


def revoke_key_modal() -> rx.Component:
    """Modal for confirming key revocation."""
    return rx.dialog.root(
        rx.dialog.content(
            rx.dialog.title("Revoke API Key", style={"color": styles.ERROR}),
            rx.vstack(
                rx.text(
                    f"Are you sure you want to revoke '{APIState.revoke_key_name}'?",
                    size="2",
                    style={"color": styles.TEXT_SECONDARY},
                ),
                rx.callout(
                    rx.text("This action cannot be undone. Any applications using this key will stop working."),
                    icon="alert-triangle",
                    color="red",
                    style={"width": "100%"},
                ),
                rx.hstack(
                    rx.dialog.close(
                        rx.button(
                            "Cancel",
                            variant="outline",
                            color_scheme="gray",
                            on_click=APIState.close_revoke_modal,
                        ),
                    ),
                    rx.button(
                        "Revoke Key",
                        color_scheme="red",
                        loading=APIState.is_revoking_key,
                        on_click=APIState.confirm_revoke_key,
                    ),
                    spacing="3",
                    justify="end",
                    width="100%",
                ),
                spacing="4",
                width="100%",
            ),
            style={"max_width": "400px"},
        ),
        open=APIState.show_revoke_modal,
    )


def deactivate_model_modal() -> rx.Component:
    """Modal for confirming model deactivation."""
    return rx.dialog.root(
        rx.dialog.content(
            rx.dialog.title("Deactivate Model", style={"color": styles.WARNING}),
            rx.vstack(
                rx.text(
                    f"Are you sure you want to deactivate '{APIState.deactivate_model_name}'?",
                    size="2",
                    style={"color": styles.TEXT_SECONDARY},
                ),
                rx.text(
                    "The model will no longer accept inference requests via the API.",
                    size="2",
                    style={"color": styles.TEXT_SECONDARY},
                ),
                rx.hstack(
                    rx.dialog.close(
                        rx.button(
                            "Cancel",
                            variant="outline",
                            color_scheme="gray",
                            on_click=APIState.close_deactivate_modal,
                        ),
                    ),
                    rx.button(
                        "Deactivate",
                        color_scheme="gray",
                        loading=APIState.is_deactivating_model,
                        on_click=APIState.confirm_deactivate_model,
                    ),
                    spacing="3",
                    justify="end",
                    width="100%",
                ),
                spacing="4",
                width="100%",
            ),
            style={"max_width": "400px"},
        ),
        open=APIState.show_deactivate_modal,
    )


# =============================================================================
# PAGE LAYOUT
# =============================================================================

def loading_skeleton() -> rx.Component:
    """Loading skeleton for the page."""
    return rx.vstack(
        rx.skeleton(height="100px", width="100%"),
        rx.grid(
            rx.skeleton(height="300px", width="100%"),
            rx.skeleton(height="300px", width="100%"),
            columns="2",
            spacing="4",
            width="100%",
        ),
        spacing="4",
        width="100%",
        padding=styles.SPACING_6,
    )


def api_page_content() -> rx.Component:
    """Main page content."""
    return rx.cond(
        APIState.is_loading,
        loading_skeleton(),
        rx.vstack(
            # Two-column layout - Models first (wider), Keys second
            rx.grid(
                api_models_card(),
                api_keys_card(),
                columns="2",
                spacing="4",
                width="100%",
                style={
                    "grid_template_columns": "3fr 2fr",
                },
            ),
            # Quick start below
            quick_start_card(),
            spacing="4",
            width="100%",
            style={
                "padding": f"0 {styles.SPACING_6} {styles.SPACING_6}",
            },
        ),
    )


def page_wrapper() -> rx.Component:
    """Full page wrapper."""
    return rx.box(
        nav_header(),
        breadcrumb_nav(),
        page_header(),
        api_page_content(),
        create_key_modal(),
        revoke_key_modal(),
        deactivate_model_modal(),
        style={
            "background": styles.BG_PRIMARY,
            "min_height": "100vh",
        },
    )


@rx.page(
    route="/projects/[project_id]/api",
    title="API Settings | SAFARI",
    on_load=[AuthState.check_auth, APIState.load_api_data],
)
def api_settings_page() -> rx.Component:
    """The API settings page (protected)."""
    return require_auth(page_wrapper())
