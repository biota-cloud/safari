"""
Evaluation Page — Dedicated model evaluation module.

Route: /evaluation
Layouts: run list, metrics dashboard, comparison view, drill-down gallery.
"""

import reflex as rx

from modules.evaluation.state import EvaluationState, RUN_COLORS
from modules.auth.dashboard import nav_header, brand_footer, require_auth
from modules.training.dashboard import numeric_stepper
from app_state import AuthState
import styles


# =============================================================================
# STAT CARD
# =============================================================================

def stat_card(label: str, value: rx.Var, color: str = styles.ACCENT) -> rx.Component:
    """Single metric stat card."""
    return rx.box(
        rx.vstack(
            rx.text(value, size="5", weight="bold", style={"color": color}),
            rx.text(label, size="1", style={"color": styles.TEXT_SECONDARY}),
            spacing="1",
            align="center",
        ),
        style={
            "background": styles.BG_SECONDARY,
            "border": f"1px solid {styles.BORDER}",
            "border_radius": styles.RADIUS_LG,
            "padding": styles.SPACING_4,
            "flex": "1",
            "text_align": "center",
        }
    )


# =============================================================================
# NEW EVALUATION MODAL
# =============================================================================

def _option_label(opt: rx.Var) -> rx.Component:
    """Render a single select option."""
    return rx.el.option(opt["name"], value=opt["id"])


def new_eval_modal() -> rx.Component:
    """Modal for configuring a new evaluation run."""
    return rx.dialog.root(
        rx.dialog.content(
            rx.dialog.title("New Evaluation", style={"color": styles.TEXT_PRIMARY}),
            rx.vstack(
                # Model selector
                rx.vstack(
                    rx.text("Model", size="2", weight="medium", style={"color": styles.TEXT_SECONDARY}),
                    rx.el.select(
                        rx.el.option("Select model...", value="", disabled=True),
                        rx.foreach(EvaluationState.model_options, _option_label),
                        value=EvaluationState.selected_model_id,
                        on_change=EvaluationState.select_model,
                        style={"width": "100%", "padding": "8px", "border_radius": styles.RADIUS_SM, "border": f"1px solid {styles.BORDER}", "background": styles.BG_TERTIARY, "color": styles.TEXT_PRIMARY},
                    ),
                    spacing="1",
                    width="100%",
                ),

                # Dataset selector
                rx.vstack(
                    rx.text("Ground Truth Dataset", size="2", weight="medium", style={"color": styles.TEXT_SECONDARY}),
                    rx.el.select(
                        rx.el.option("Select dataset...", value="", disabled=True),
                        rx.foreach(EvaluationState.dataset_options, _option_label),
                        value=EvaluationState.selected_dataset_id,
                        on_change=EvaluationState.select_dataset,
                        style={"width": "100%", "padding": "8px", "border_radius": styles.RADIUS_SM, "border": f"1px solid {styles.BORDER}", "background": styles.BG_TERTIARY, "color": styles.TEXT_PRIMARY},
                    ),
                    spacing="1",
                    width="100%",
                ),

                # Hybrid settings (shown when classifier model detected)
                rx.cond(
                    EvaluationState.eval_is_hybrid,
                    rx.vstack(
                        rx.hstack(
                            rx.icon("settings_2", size=14, color=styles.TEXT_SECONDARY),
                            rx.text("Hybrid Settings", size="2", weight="medium", style={"color": styles.TEXT_SECONDARY}),
                            spacing="1",
                            align="center",
                        ),
                        # Object Types (SAM3 prompts)
                        rx.vstack(
                            rx.text("Object Types", size="2", style={"color": styles.TEXT_SECONDARY}),
                            rx.input(
                                value=EvaluationState.eval_sam3_prompts_input,
                                on_change=EvaluationState.set_eval_sam3_prompts,
                                placeholder="animal, bird",
                                size="2",
                                style={"width": "100%"},
                            ),
                            spacing="1",
                            width="100%",
                        ),
                        # SAM3 Conf + SAM3 imgsz row
                        rx.hstack(
                            rx.vstack(
                                rx.text("SAM3 Conf.", size="2", style={"color": styles.TEXT_SECONDARY}),
                                numeric_stepper(
                                    label="",
                                    value=EvaluationState.eval_sam3_confidence.to(str),
                                    on_blur_handler=EvaluationState.set_eval_sam3_confidence,
                                    on_increment=EvaluationState.increment_eval_sam3_conf,
                                    on_decrement=EvaluationState.decrement_eval_sam3_conf,
                                ),
                                spacing="1",
                            ),
                            rx.vstack(
                                rx.text("SAM3 imgsz", size="2", style={"color": styles.TEXT_SECONDARY}),
                                rx.el.select(
                                    rx.el.option("644", value="644"),
                                    rx.el.option("1036", value="1036"),
                                    rx.el.option("1288", value="1288"),
                                    rx.el.option("1918", value="1918"),
                                    rx.el.option("2688", value="2688"),
                                    rx.el.option("3584", value="3584"),
                                    rx.el.option("4480", value="4480"),
                                    value=EvaluationState.eval_sam3_imgsz,
                                    on_change=EvaluationState.set_eval_sam3_imgsz,
                                    style={"padding": "6px 8px", "border_radius": styles.RADIUS_SM, "border": f"1px solid {styles.BORDER}", "background": styles.BG_TERTIARY, "color": styles.TEXT_PRIMARY},
                                ),
                                spacing="1",
                            ),
                            spacing="4",
                            width="100%",
                        ),
                        rx.text(
                            f"{EvaluationState.eval_classifier_classes.length()} species in classifier",
                            size="1",
                            style={"color": styles.TEXT_SECONDARY, "font_style": "italic"},
                        ),
                        spacing="3",
                        width="100%",
                        padding="12px",
                        border_radius=styles.RADIUS_SM,
                        background=styles.BG_TERTIARY,
                    ),
                ),

                # Confidence + IoU (always shown)
                rx.hstack(
                    rx.vstack(
                        rx.text(
                            rx.cond(EvaluationState.eval_is_hybrid, "Species Conf.", "Confidence"),
                            size="2", style={"color": styles.TEXT_SECONDARY},
                        ),
                        numeric_stepper(
                            label="",
                            value=EvaluationState.eval_classifier_confidence.to(str),
                            on_blur_handler=EvaluationState.set_eval_classifier_confidence,
                            on_increment=EvaluationState.increment_eval_classifier_conf,
                            on_decrement=EvaluationState.decrement_eval_classifier_conf,
                        ),
                        spacing="1",
                    ),
                    rx.vstack(
                        rx.hstack(
                            rx.text("IoU Threshold", size="2", style={"color": styles.TEXT_SECONDARY}),
                            rx.tooltip(
                                rx.icon("info", size=12, color=styles.TEXT_SECONDARY),
                                content="Intersection over Union — how much a predicted box must overlap with a ground truth box to count as a correct detection.",
                            ),
                            spacing="1",
                            align="center",
                        ),
                        rx.input(
                            value=EvaluationState.eval_iou.to(str),
                            on_change=EvaluationState.set_eval_iou,
                            size="2",
                            style={"width": "100px"},
                        ),
                        spacing="1",
                    ),
                    spacing="4",
                    width="100%",
                ),

                # Error
                rx.cond(
                    EvaluationState.eval_error != "",
                    rx.text(EvaluationState.eval_error, size="2", style={"color": styles.ERROR}),
                ),

                # Actions
                rx.hstack(
                    rx.dialog.close(
                        rx.button("Cancel", variant="outline", color_scheme="gray", on_click=EvaluationState.close_new_eval_modal),
                    ),
                    rx.button(
                        "Start Evaluation",
                        disabled=~EvaluationState.can_start_eval,
                        on_click=EvaluationState.start_evaluation,
                        style=styles.BUTTON_PRIMARY,
                    ),
                    spacing="3",
                    justify="end",
                    width="100%",
                ),

                spacing="4",
                width="100%",
            ),
            style={"max_width": "480px"},
        ),
        open=EvaluationState.show_new_eval_modal,
    )


# =============================================================================
# DELETE CONFIRMATION MODAL
# =============================================================================

def delete_run_modal() -> rx.Component:
    return rx.dialog.root(
        rx.dialog.content(
            rx.dialog.title("Delete Evaluation Run", style={"color": styles.ERROR}),
            rx.vstack(
                rx.text(
                    "This will permanently delete this evaluation run and all per-image results.",
                    style={"color": styles.TEXT_SECONDARY},
                ),
                rx.hstack(
                    rx.dialog.close(
                        rx.button("Cancel", variant="outline", color_scheme="gray", on_click=EvaluationState.close_delete_modal),
                    ),
                    rx.button("Delete", color_scheme="red", on_click=EvaluationState.confirm_delete_run),
                    spacing="3",
                    justify="end",
                    width="100%",
                ),
                spacing="3",
                width="100%",
            ),
            style={"max_width": "400px"},
        ),
        open=EvaluationState.show_delete_modal,
    )


# =============================================================================
# PROGRESS BAR
# =============================================================================

def eval_progress_bar() -> rx.Component:
    return rx.cond(
        EvaluationState.is_running_eval,
        rx.box(
            rx.vstack(
                rx.hstack(
                    rx.spinner(size="2"),
                    rx.text(EvaluationState.eval_status, size="2", style={"color": styles.TEXT_PRIMARY}),
                    spacing="2",
                    align="center",
                ),
                rx.progress(
                    value=rx.cond(
                        EvaluationState.eval_progress_total > 0,
                        (EvaluationState.eval_progress_current * 100 / EvaluationState.eval_progress_total).to(int),
                        0,
                    ),
                    style={"width": "100%"},
                ),
                rx.text(
                    EvaluationState.eval_progress_current.to(str) + " / " + EvaluationState.eval_progress_total.to(str) + " images",
                    size="1",
                    style={"color": styles.TEXT_SECONDARY},
                ),
                spacing="2",
                width="100%",
            ),
            style={
                "background": styles.BG_SECONDARY,
                "border": f"1px solid {styles.BORDER}",
                "border_radius": styles.RADIUS_LG,
                "padding": styles.SPACING_4,
                "width": "100%",
            },
        ),
    )


# =============================================================================
# RUNS TABLE
# =============================================================================

def run_row(run: rx.Var) -> rx.Component:
    """Single row in the evaluation runs table — uses typed EvalRunRow."""
    return rx.hstack(
        # Checkbox for comparison
        rx.checkbox(
            checked=EvaluationState.selected_run_ids.contains(run["id"]),
            on_change=lambda _: EvaluationState.toggle_run_selection(run["id"]),
        ),
        # Model name
        rx.text(run["model_name"], size="2", weight="medium", style={"color": styles.TEXT_PRIMARY, "flex": "1"}),
        # Dataset
        rx.text(run["dataset_name"], size="2", style={"color": styles.TEXT_SECONDARY, "flex": "1"}),
        # F1 (pre-formatted in _run_to_row)
        rx.text(run["f1_display"], size="2", weight="bold", style={"color": styles.ACCENT, "min_width": "50px"}),
        # Status badge
        rx.cond(
            run["status"] == "completed",
            rx.badge("Done", color_scheme="green", size="1"),
            rx.cond(
                run["status"] == "running",
                rx.badge("Running", color_scheme="orange", size="1"),
                rx.badge("Pending", color_scheme="gray", size="1"),
            ),
        ),
        # View
        rx.button(
            rx.icon("eye", size=14),
            size="1",
            variant="ghost",
            on_click=EvaluationState.view_run(run["id"]),
        ),
        # Delete
        rx.button(
            rx.icon("trash-2", size=14),
            size="1",
            variant="ghost",
            color_scheme="red",
            on_click=EvaluationState.open_delete_modal(run["id"]),
        ),
        spacing="3",
        align="center",
        width="100%",
        style={
            "padding": f"{styles.SPACING_2} {styles.SPACING_3}",
            "border_radius": styles.RADIUS_SM,
            "_hover": {"background": styles.BG_TERTIARY},
        },
    )


def runs_panel() -> rx.Component:
    return rx.box(
        rx.vstack(
            rx.hstack(
                rx.text("Evaluation Runs", size="3", weight="bold", style={"color": styles.TEXT_PRIMARY}),
                rx.spacer(),
                rx.cond(
                    EvaluationState.show_compare_button,
                    rx.button(
                        rx.icon("git-compare", size=14),
                        "Compare Selected",
                        size="2",
                        variant="outline",
                        on_click=EvaluationState.compute_comparison,
                    ),
                ),
                rx.button(
                    rx.icon("plus", size=14),
                    "New Evaluation",
                    size="2",
                    on_click=EvaluationState.open_new_eval_modal,
                    style=styles.BUTTON_PRIMARY,
                ),
                spacing="2",
                align="center",
                width="100%",
            ),

            # Table header
            rx.hstack(
                rx.box(width="20px"),
                rx.text("Model", size="1", weight="medium", style={"color": styles.TEXT_SECONDARY, "flex": "1"}),
                rx.text("Dataset", size="1", weight="medium", style={"color": styles.TEXT_SECONDARY, "flex": "1"}),
                rx.text("F1", size="1", weight="medium", style={"color": styles.TEXT_SECONDARY, "min_width": "50px"}),
                rx.text("Status", size="1", weight="medium", style={"color": styles.TEXT_SECONDARY, "min_width": "60px"}),
                rx.box(width="60px"),
                spacing="3",
                width="100%",
                style={"padding": f"0 {styles.SPACING_3}", "border_bottom": f"1px solid {styles.BORDER}"},
            ),

            # Runs list
            rx.cond(
                EvaluationState.evaluation_runs.length() > 0,
                rx.vstack(
                    rx.foreach(EvaluationState.evaluation_runs, run_row),
                    spacing="0",
                    width="100%",
                ),
                rx.box(
                    rx.vstack(
                        rx.icon("bar-chart-3", size=32, color=styles.EARTH_TAUPE),
                        rx.text("No evaluations yet", size="2", style={"color": styles.TEXT_SECONDARY}),
                        rx.text("Click 'New Evaluation' to compare a model against ground truth.",
                                size="1", style={"color": styles.TEXT_SECONDARY}),
                        spacing="2",
                        align="center",
                        style={"padding": styles.SPACING_8},
                    ),
                ),
            ),

            spacing="3",
            width="100%",
        ),
        style={
            "background": styles.BG_SECONDARY,
            "border": f"1px solid {styles.BORDER}",
            "border_radius": styles.RADIUS_LG,
            "padding": styles.SPACING_4,
            "width": "100%",
        },
    )


# =============================================================================
# METRICS DASHBOARD (Single Run View)
# =============================================================================

def metrics_dashboard() -> rx.Component:
    return rx.cond(
        EvaluationState.has_active_run,
        rx.vstack(
            # Header
            rx.hstack(
                rx.text("Results: ", size="3", style={"color": styles.TEXT_PRIMARY}),
                rx.text(EvaluationState.active_model_name, size="3", weight="bold", style={"color": styles.TEXT_PRIMARY}),
                rx.text(" vs ", size="2", style={"color": styles.TEXT_SECONDARY}),
                rx.text(EvaluationState.active_dataset_name, size="2", style={"color": styles.TEXT_SECONDARY, "font_style": "italic"}),
                spacing="1",
                align="center",
            ),

            # Analysis confidence stepper
            rx.box(
                numeric_stepper(
                    label="Analysis Confidence",
                    value=EvaluationState.analysis_confidence,
                    on_blur_handler=EvaluationState.set_analysis_confidence_input,
                    on_increment=EvaluationState.increment_analysis_confidence,
                    on_decrement=EvaluationState.decrement_analysis_confidence,
                    tooltip="Filter detections by confidence — metrics update instantly. Higher = fewer detections, better precision.",
                    display_width="64px",
                ),
                style={
                    "background": styles.BG_SECONDARY,
                    "border": f"1px solid {styles.BORDER}",
                    "border_radius": styles.RADIUS_LG,
                    "padding": styles.SPACING_3,
                    "width": "100%",
                },
            ),

            # Stat cards
            rx.grid(
                stat_card("Precision", EvaluationState.overall_precision, styles.ACCENT),
                stat_card("Recall", EvaluationState.overall_recall, styles.PURPLE),
                stat_card("F1 Score", EvaluationState.overall_f1, styles.EARTH_SIENNA),
                stat_card("Images", EvaluationState.active_total_images, styles.TEXT_PRIMARY),
                columns="4",
                spacing="3",
                width="100%",
            ),

            per_class_table(),
            drill_down_gallery(),

            spacing="4",
            width="100%",
        ),
    )


# =============================================================================
# PER-CLASS TABLE
# =============================================================================

def per_class_row(item: rx.Var) -> rx.Component:
    return rx.hstack(
        rx.text(item["class_name"], size="2", weight="medium", style={"color": styles.TEXT_PRIMARY, "min_width": "120px"}),
        rx.text(item["precision"], size="2", style={"color": styles.ACCENT, "min_width": "70px"}),
        rx.text(item["recall"], size="2", style={"color": styles.PURPLE, "min_width": "70px"}),
        rx.text(item["f1"], size="2", weight="bold", style={"color": styles.EARTH_SIENNA, "min_width": "70px"}),
        rx.text(item["tp"].to(str), size="2", style={"color": styles.SUCCESS, "min_width": "40px"}),
        rx.text(item["fp"].to(str), size="2", style={"color": styles.ERROR, "min_width": "40px"}),
        rx.text(item["fn"].to(str), size="2", style={"color": styles.WARNING, "min_width": "40px"}),
        rx.button(
            rx.icon("search", size=12),
            size="1",
            variant="ghost",
            on_click=EvaluationState.set_drill_down_class(item["class_name"]),
        ),
        spacing="3",
        align="center",
        width="100%",
        style={
            "padding": f"{styles.SPACING_1} {styles.SPACING_3}",
            "border_radius": styles.RADIUS_SM,
            "_hover": {"background": styles.BG_TERTIARY},
        },
    )


def per_class_table() -> rx.Component:
    return rx.box(
        rx.vstack(
            rx.text("Per-Class Performance", size="3", weight="bold", style={"color": styles.TEXT_PRIMARY}),
            # Header
            rx.hstack(
                rx.text("Class", size="1", weight="medium", style={"color": styles.TEXT_SECONDARY, "min_width": "120px"}),
                rx.text("Precision", size="1", weight="medium", style={"color": styles.TEXT_SECONDARY, "min_width": "70px"}),
                rx.text("Recall", size="1", weight="medium", style={"color": styles.TEXT_SECONDARY, "min_width": "70px"}),
                rx.text("F1", size="1", weight="medium", style={"color": styles.TEXT_SECONDARY, "min_width": "70px"}),
                rx.text("TP", size="1", weight="medium", style={"color": styles.TEXT_SECONDARY, "min_width": "40px"}),
                rx.text("FP", size="1", weight="medium", style={"color": styles.TEXT_SECONDARY, "min_width": "40px"}),
                rx.text("FN", size="1", weight="medium", style={"color": styles.TEXT_SECONDARY, "min_width": "40px"}),
                rx.box(width="28px"),
                spacing="3",
                width="100%",
                style={"padding": f"0 {styles.SPACING_3}", "border_bottom": f"1px solid {styles.BORDER}"},
            ),
            rx.foreach(EvaluationState.per_class_data, per_class_row),
            spacing="2",
            width="100%",
        ),
        style={
            "background": styles.BG_SECONDARY,
            "border": f"1px solid {styles.BORDER}",
            "border_radius": styles.RADIUS_LG,
            "padding": styles.SPACING_4,
            "width": "100%",
        },
    )


# =============================================================================
# DRILL-DOWN GALLERY
# =============================================================================

def prediction_card(pred: rx.Var) -> rx.Component:
    return rx.box(
        rx.vstack(
            rx.text(pred["image_filename"], size="2", weight="medium", style={"color": styles.TEXT_PRIMARY}),
            rx.hstack(
                rx.badge("TP: " + pred["tp_count"].to(str), color_scheme="green", size="1"),
                rx.badge("FP: " + pred["fp_count"].to(str), color_scheme="red", size="1"),
                rx.cond(
                    pred["fn_misclass_count"] > 0,
                    rx.hstack(
                        rx.badge("Missed: " + pred["fn_missed_count"].to(str), color_scheme="orange", size="1"),
                        rx.badge("Misclass: " + pred["fn_misclass_count"].to(str), color_scheme="yellow", size="1"),
                        spacing="1",
                    ),
                    rx.badge("FN: " + pred["fn_count"].to(str), color_scheme="orange", size="1"),
                ),
                spacing="2",
            ),
            rx.button(
                rx.icon("eye", size=12),
                "View Detail",
                size="1",
                variant="outline",
                on_click=EvaluationState.view_image_detail(pred["id"]),
            ),
            spacing="2",
            align="start",
        ),
        style={
            "background": styles.BG_TERTIARY,
            "border": f"1px solid {styles.BORDER}",
            "border_radius": styles.RADIUS_SM,
            "padding": styles.SPACING_3,
        },
    )


def drill_down_gallery() -> rx.Component:
    return rx.box(
        rx.vstack(
            rx.hstack(
                rx.text("Image Results", size="3", weight="bold", style={"color": styles.TEXT_PRIMARY}),
                rx.spacer(),
                rx.hstack(
                    rx.button("All", size="1", variant=rx.cond(EvaluationState.drill_down_type == "", "solid", "outline"), on_click=EvaluationState.set_drill_down_type("")),
                    rx.button("TP", size="1", variant=rx.cond(EvaluationState.drill_down_type == "tp", "solid", "outline"), color_scheme="green", on_click=EvaluationState.set_drill_down_type("tp")),
                    rx.button("FP", size="1", variant=rx.cond(EvaluationState.drill_down_type == "fp", "solid", "outline"), color_scheme="red", on_click=EvaluationState.set_drill_down_type("fp")),
                    rx.button("FN", size="1", variant=rx.cond(EvaluationState.drill_down_type == "fn", "solid", "outline"), color_scheme="orange", on_click=EvaluationState.set_drill_down_type("fn")),
                    rx.text("|", size="1", style={"color": styles.BORDER}),
                    rx.button("Missed", size="1", variant=rx.cond(EvaluationState.drill_down_type == "fn_missed", "solid", "outline"), color_scheme="orange", on_click=EvaluationState.set_drill_down_type("fn_missed")),
                    rx.button("Misclass", size="1", variant=rx.cond(EvaluationState.drill_down_type == "fn_misclass", "solid", "outline"), color_scheme="yellow", on_click=EvaluationState.set_drill_down_type("fn_misclass")),
                    spacing="1",
                ),
                rx.cond(
                    EvaluationState.drill_down_class != "",
                    rx.badge(
                        "Class: " + EvaluationState.drill_down_class,
                        size="1",
                    ),
                ),
                spacing="2",
                align="center",
                width="100%",
            ),

            rx.cond(
                EvaluationState.active_predictions.length() > 0,
                rx.grid(
                    rx.foreach(EvaluationState.active_predictions, prediction_card),
                    columns="3",
                    spacing="3",
                    width="100%",
                ),
                rx.text("No results to display.", size="2", style={"color": styles.TEXT_SECONDARY, "padding": styles.SPACING_4}),
            ),

            # Pagination
            rx.hstack(
                rx.button(
                    rx.icon("chevron-left", size=14),
                    "Previous",
                    size="1",
                    variant="outline",
                    disabled=EvaluationState.predictions_page <= 0,
                    on_click=EvaluationState.prev_predictions_page,
                ),
                rx.text(
                    "Page " + (EvaluationState.predictions_page + 1).to(str),
                    size="2",
                    style={"color": styles.TEXT_SECONDARY},
                ),
                rx.button(
                    "Next",
                    rx.icon("chevron-right", size=14),
                    size="1",
                    variant="outline",
                    disabled=EvaluationState.active_predictions.length() < 50,
                    on_click=EvaluationState.next_predictions_page,
                ),
                spacing="3",
                justify="center",
                width="100%",
            ),

            spacing="3",
            width="100%",
        ),
        style={
            "background": styles.BG_SECONDARY,
            "border": f"1px solid {styles.BORDER}",
            "border_radius": styles.RADIUS_LG,
            "padding": styles.SPACING_4,
            "width": "100%",
        },
    )


# =============================================================================
# COMPARISON VIEW
# =============================================================================

def comparison_delta_row(delta: rx.Var) -> rx.Component:
    return rx.hstack(
        rx.text(delta["class_name"], size="2", style={"color": styles.TEXT_PRIMARY}),
        rx.text(
            delta["delta_display"],
            size="2",
            weight="bold",
            style={"color": rx.cond(delta["is_improved"], styles.SUCCESS, styles.ERROR)},
        ),
        spacing="2",
    )


def comparison_view() -> rx.Component:
    return rx.cond(
        EvaluationState.has_comparison,
        rx.box(
            rx.vstack(
                rx.text("Model Comparison", size="3", weight="bold", style={"color": styles.TEXT_PRIMARY}),
                rx.foreach(EvaluationState.comparison_deltas, comparison_delta_row),
                spacing="2",
                width="100%",
            ),
            style={
                "background": styles.BG_SECONDARY,
                "border": f"1px solid {styles.BORDER}",
                "border_radius": styles.RADIUS_LG,
                "padding": styles.SPACING_4,
                "width": "100%",
            },
        ),
    )


# =============================================================================
# IMAGE DETAIL MODAL
# =============================================================================

def image_detail_modal() -> rx.Component:
    return rx.dialog.root(
        rx.dialog.content(
            rx.dialog.title(EvaluationState.detail_image_filename, style={"color": styles.TEXT_PRIMARY}),
            rx.vstack(
                rx.cond(
                    EvaluationState.detail_image_url != "",
                    rx.box(
                        rx.image(
                            src=EvaluationState.detail_image_url,
                            style={"max_width": "100%", "max_height": "500px", "width": "auto", "height": "auto", "display": "block"},
                            border_radius=styles.RADIUS_SM,
                        ),
                        # GT boxes (green)
                        rx.foreach(
                            EvaluationState.detail_gt_boxes,
                            lambda b: rx.box(
                                rx.text(
                                    b["class_name"].to(str),
                                    size="1",
                                    style={"color": "#000", "background": "rgba(72, 199, 142, 0.9)", "padding": "1px 4px", "font_size": "10px", "white_space": "nowrap", "position": "absolute", "top": "-16px", "left": "0"},
                                ),
                                style={
                                    "position": "absolute",
                                    "left": (b["x1"].to(float) * 100).to(str) + "%",
                                    "top": (b["y1"].to(float) * 100).to(str) + "%",
                                    "width": ((b["x2"].to(float) - b["x1"].to(float)) * 100).to(str) + "%",
                                    "height": ((b["y2"].to(float) - b["y1"].to(float)) * 100).to(str) + "%",
                                    "border": "2px solid " + RUN_COLORS["gt"],
                                    "pointer_events": "none",
                                },
                            ),
                        ),
                        # Prediction boxes (purple)
                        rx.foreach(
                            EvaluationState.detail_pred_boxes,
                            lambda b: rx.box(
                                rx.text(
                                    b["class_name"].to(str) + " " + b["confidence"].to(int).to(str) + "%",
                                    size="1",
                                    style={"color": "#fff", "background": "rgba(147, 112, 219, 0.9)", "padding": "1px 4px", "font_size": "10px", "white_space": "nowrap", "position": "absolute", "bottom": "-16px", "left": "0"},
                                ),
                                style={
                                    "position": "absolute",
                                    "left": (b["x1"].to(float) * 100).to(str) + "%",
                                    "top": (b["y1"].to(float) * 100).to(str) + "%",
                                    "width": ((b["x2"].to(float) - b["x1"].to(float)) * 100).to(str) + "%",
                                    "height": ((b["y2"].to(float) - b["y1"].to(float)) * 100).to(str) + "%",
                                    "border": "2px solid " + RUN_COLORS["run_a"],
                                    "pointer_events": "none",
                                },
                            ),
                        ),
                        position="relative",
                        display="inline-block",
                    ),
                ),
                rx.hstack(
                    rx.badge("TP: " + EvaluationState.detail_tp.to(str), color_scheme="green", size="2"),
                    rx.badge("FP: " + EvaluationState.detail_fp.to(str), color_scheme="red", size="2"),
                    rx.badge("FN: " + EvaluationState.detail_fn.to(str), color_scheme="orange", size="2"),
                    rx.spacer(),
                    rx.text(
                        EvaluationState.detail_gt_count.to(str) + " GT · " + EvaluationState.detail_pred_count.to(str) + " predictions",
                        size="1",
                        style={"color": styles.TEXT_SECONDARY},
                    ),
                    spacing="2",
                    align="center",
                    width="100%",
                ),
                # Match breakdown
                rx.cond(
                    EvaluationState.detail_match_breakdown.length() > 0,
                    rx.box(
                        rx.vstack(
                            rx.text("Match Details", size="1", weight="medium", style={"color": styles.TEXT_SECONDARY}),
                            rx.foreach(
                                EvaluationState.detail_match_breakdown,
                                lambda m: rx.hstack(
                                    rx.text(
                                        rx.cond(m["match_type"] == "tp", "✓", "✗"),
                                        size="1",
                                        weight="bold",
                                        style={"color": rx.cond(
                                            m["match_type"] == "tp",
                                            styles.SUCCESS,
                                            rx.cond(m["match_type"] == "fp", styles.ERROR, styles.WARNING),
                                        )},
                                    ),
                                    rx.text(m["class_name"], size="1", weight="medium", style={"color": styles.TEXT_PRIMARY}),
                                    rx.text("—", size="1", style={"color": styles.TEXT_SECONDARY}),
                                    rx.badge(
                                        m["match_type"].upper(),
                                        size="1",
                                        color_scheme=rx.cond(
                                            m["match_type"] == "tp", "green",
                                            rx.cond(m["match_type"] == "fp", "red", "orange"),
                                        ),
                                    ),
                                    rx.text(m["detail"], size="1", style={"color": styles.TEXT_SECONDARY, "font_style": "italic"}),
                                    spacing="1",
                                    align="center",
                                ),
                            ),
                            spacing="1",
                            width="100%",
                        ),
                        style={
                            "background": styles.BG_TERTIARY,
                            "border": f"1px solid {styles.BORDER}",
                            "border_radius": styles.RADIUS_SM,
                            "padding": styles.SPACING_2,
                            "width": "100%",
                        },
                    ),
                ),
                rx.hstack(
                    rx.hstack(
                        rx.box(style={"width": "12px", "height": "12px", "background": RUN_COLORS["gt"], "border_radius": "2px"}),
                        rx.text("Ground Truth", size="1", style={"color": styles.TEXT_SECONDARY}),
                        spacing="1", align="center",
                    ),
                    rx.hstack(
                        rx.box(style={"width": "12px", "height": "12px", "background": RUN_COLORS["run_a"], "border_radius": "2px"}),
                        rx.text("Predictions", size="1", style={"color": styles.TEXT_SECONDARY}),
                        spacing="1", align="center",
                    ),
                    spacing="4",
                ),
                rx.hstack(
                    rx.dialog.close(
                        rx.button("Close", variant="outline", on_click=EvaluationState.close_detail_modal),
                    ),
                    justify="end",
                    width="100%",
                ),
                spacing="3",
                width="100%",
            ),
            style={"max_width": "700px"},
        ),
        open=EvaluationState.show_detail_modal,
    )


# =============================================================================
# PROJECT SELECTOR
# =============================================================================

def _project_option(opt: rx.Var) -> rx.Component:
    return rx.el.option(opt["name"], value=opt["id"])


def project_selector() -> rx.Component:
    return rx.cond(
        EvaluationState.project_options.length() > 1,
        rx.el.select(
            rx.foreach(EvaluationState.project_options, _project_option),
            value=EvaluationState.selected_project_id,
            on_change=EvaluationState.select_project,
            style={"min_width": "200px", "padding": "8px", "border_radius": styles.RADIUS_SM, "border": f"1px solid {styles.BORDER}", "background": styles.BG_TERTIARY, "color": styles.TEXT_PRIMARY},
        ),
    )


# =============================================================================
# PAGE LAYOUT
# =============================================================================

def evaluation_content() -> rx.Component:
    return rx.box(
        nav_header(),
        rx.box(
            rx.vstack(
                # Page header
                rx.hstack(
                    rx.vstack(
                        rx.text("Model Evaluation", size="5", weight="bold", style={"color": styles.TEXT_PRIMARY}),
                        rx.text("Compare model predictions against ground truth", size="2", style={"color": styles.TEXT_SECONDARY}),
                        spacing="1",
                    ),
                    rx.spacer(),
                    project_selector(),
                    spacing="4",
                    align="center",
                    width="100%",
                ),
                eval_progress_bar(),
                rx.cond(
                    EvaluationState.eval_error != "",
                    rx.callout(EvaluationState.eval_error, icon="triangle-alert", color_scheme="red", style={"width": "100%"}),
                ),
                runs_panel(),
                comparison_view(),
                metrics_dashboard(),
                spacing="4",
                width="100%",
            ),
            style={"padding": styles.SPACING_6, "max_width": "1400px", "margin": "0 auto"},
        ),
        brand_footer(variant="dashboard"),
        new_eval_modal(),
        delete_run_modal(),
        image_detail_modal(),
        style={"background": styles.BG_PRIMARY, "min_height": "100vh"},
    )


@rx.page(
    route="/evaluation",
    title="Model Evaluation | SAFARI",
    on_load=[AuthState.check_auth, EvaluationState.load_evaluation_data],
)
def evaluation_page() -> rx.Component:
    return require_auth(evaluation_content())
