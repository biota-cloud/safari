"""
Run Detail Page — Detailed view of a single training run.

Route: /projects/{project_id}/train/{run_id}
Shows metrics, charts from results.csv, artifacts gallery, and logs.
"""

import reflex as rx
import styles
from app_state import require_auth, AuthState
from modules.training.state import TrainingState


def breadcrumb_nav() -> rx.Component:
    """Breadcrumb navigation with back button."""
    return rx.hstack(
        rx.link(
            rx.hstack(
                rx.icon("arrow-left", size=16),
                rx.text("Back to Training", size="2"),
                spacing="1",
                align="center",
            ),
            href=f"/projects/{TrainingState.current_project_id}/train",
            style={"color": styles.TEXT_SECONDARY, "&:hover": {"color": styles.TEXT_PRIMARY}},
        ),
        rx.spacer(),
        # Action buttons in header (only show for completed runs)
        rx.cond(
            TrainingState.selected_run_is_completed,
            rx.hstack(
                # Add to Playground dropdown
                rx.menu.root(
                    rx.menu.trigger(
                        rx.button(
                            rx.icon("plus", size=14),
                            "Playground",
                            rx.icon("chevron-down", size=12),
                            size="1",
                            variant="outline",
                            color_scheme="green",
                        ),
                    ),
                    rx.menu.content(
                        rx.menu.item(
                            rx.hstack(rx.text("Best"), rx.spacer(), rx.badge("mAP"), spacing="2"),
                            on_click=TrainingState.add_model_to_playground("best"),
                        ),
                        rx.menu.item(
                            "Last",
                            on_click=TrainingState.add_model_to_playground("last"),
                        ),
                    ),
                ),
                # Add to Autolabel dropdown
                rx.menu.root(
                    rx.menu.trigger(
                        rx.button(
                            rx.icon("sparkles", size=14),
                            "Autolabel",
                            rx.icon("chevron-down", size=12),
                            size="1",
                            variant="outline",
                            color_scheme="purple",
                            loading=TrainingState.is_uploading_to_autolabel,
                        ),
                    ),
                    rx.menu.content(
                        rx.menu.item(
                            rx.hstack(rx.text("Best"), rx.spacer(), rx.badge("recommended", color_scheme="green"), spacing="2"),
                            on_click=TrainingState.add_model_to_autolabel("best"),
                        ),
                        rx.menu.item(
                            "Last",
                            on_click=TrainingState.add_model_to_autolabel("last"),
                        ),
                    ),
                ),
                # Download dropdown
                rx.menu.root(
                    rx.menu.trigger(
                        rx.button(
                            rx.icon("download", size=14),
                            "Download",
                            rx.icon("chevron-down", size=12),
                            size="1",
                            variant="outline",
                            color_scheme="green",
                        ),
                    ),
                    rx.menu.content(
                        rx.menu.item(
                            rx.link(
                                rx.hstack(rx.text("best.pt"), rx.spacer(), rx.badge("recommended", color_scheme="green"), spacing="2"),
                                href=TrainingState.best_pt_url,
                                is_external=True,
                                style={"text_decoration": "none", "color": "inherit"},
                            ),
                        ),
                        rx.menu.item(
                            rx.link(
                                "last.pt",
                                href=TrainingState.last_pt_url,
                                is_external=True,
                                style={"text_decoration": "none", "color": "inherit"},
                            ),
                        ),
                    ),
                ),
                spacing="2",
            ),
            rx.fragment(),
        ),
        width="100%",
        align="center",
        style={"padding": f"{styles.SPACING_4} {styles.SPACING_6}"},
    )


# Predefined tags with colors
AVAILABLE_TAGS = [
    ("production", "green"),
    ("experiment", "purple"),
    ("baseline", "blue"),
    ("best", "yellow"),
    ("deprecated", "gray"),
]


def tag_badge_component(tag: str, color: str) -> rx.Component:
    """Single tag badge that can be toggled. Uses rx.cond for reactive styling."""
    is_active = TrainingState.selected_run_tags.contains(tag)
    return rx.cond(
        is_active,
        # Active state - solid badge with color
        rx.badge(
            tag,
            color_scheme=color,
            variant="solid",
            size="1",
            cursor="pointer",
            on_click=TrainingState.toggle_tag(tag),
            style={
                "transition": "all 0.2s ease",
                "&:hover": {"opacity": "0.8"},
            },
        ),
        # Inactive state - outline gray badge
        rx.badge(
            tag,
            color_scheme="gray",
            variant="outline",
            size="1",
            cursor="pointer",
            on_click=TrainingState.toggle_tag(tag),
            style={
                "transition": "all 0.2s ease",
                "&:hover": {"opacity": "0.8"},
            },
        ),
    )


def run_header() -> rx.Component:
    """Header showing run info with editable alias, tags, and notes."""
    return rx.vstack(
        # Title row with editable alias
        rx.hstack(
            rx.vstack(
                # Editable Alias
                rx.cond(
                    TrainingState.editing_alias,
                    # Edit mode
                    rx.hstack(
                        rx.input(
                            value=TrainingState.temp_alias,
                            on_change=TrainingState.set_temp_alias,
                            on_key_down=TrainingState.handle_alias_keydown,
                            placeholder="Enter model alias...",
                            size="2",
                            style={"width": "300px"},
                        ),
                        rx.button(
                            rx.icon("check", size=14),
                            size="1",
                            variant="outline",
                            color_scheme="green",
                            on_click=TrainingState.save_alias,
                        ),
                        rx.button(
                            rx.icon("x", size=14),
                            size="1",
                            variant="ghost",
                            on_click=TrainingState.cancel_editing_alias,
                        ),
                        spacing="2",
                        align="center",
                    ),
                    # Display mode
                    rx.hstack(
                        rx.heading(
                            TrainingState.selected_run_alias,
                            size="5",
                            weight="bold",
                            style={"color": styles.TEXT_PRIMARY},
                        ),
                        rx.icon_button(
                            rx.icon("pencil", size=12),
                            size="1",
                            variant="ghost",
                            on_click=TrainingState.start_editing_alias,
                            style={"opacity": "0.6", "&:hover": {"opacity": "1"}},
                        ),
                        spacing="2",
                        align="center",
                    ),
                ),
                # Status, type, and date
                rx.hstack(
                    rx.badge(
                        TrainingState.selected_run.status,
                        color_scheme=rx.match(
                            TrainingState.selected_run.status,
                            ("completed", "green"),
                            ("running", "yellow"),
                            ("failed", "red"),
                            "gray",
                        ),
                        size="2",
                    ),
                    # Model type badge
                    rx.cond(
                        TrainingState.selected_run.model_type == "classification",
                        rx.badge(
                            rx.hstack(
                                rx.icon("tags", size=10),
                                rx.text("Classification", size="1"),
                                spacing="1",
                                align="center",
                            ),
                            color_scheme="purple",
                            size="2",
                            variant="outline",
                        ),
                        rx.badge(
                            rx.hstack(
                                rx.icon("target", size=10),
                                rx.text("Detection", size="1"),
                                spacing="1",
                                align="center",
                            ),
                            color_scheme="green",
                            size="2",
                            variant="outline",
                        ),
                    ),
                    # Backbone badge (classification only)
                    rx.cond(
                        TrainingState.selected_run.model_type == "classification",
                        rx.cond(
                            TrainingState.selected_run_is_convnext,
                            rx.badge("ConvNeXt", color_scheme="gray", size="2", variant="outline"),
                            rx.badge("YOLO", color_scheme="green", size="2", variant="outline"),
                        ),
                        rx.fragment(),
                    ),
                    rx.text(
                        TrainingState.selected_run.created_at,
                        size="2",
                        style={"color": styles.TEXT_SECONDARY},
                    ),
                    spacing="2",
                    align="center",
                ),
                spacing="1",
                align="start",
            ),
            width="100%",
        ),
        # Tags row - always visible for categorization
        rx.hstack(
            rx.text("Tags:", size="1", style={"color": styles.TEXT_SECONDARY}),
            *[tag_badge_component(tag, color) for tag, color in AVAILABLE_TAGS],
            spacing="2",
            align="center",
            style={"margin_top": "4px"},
        ),
        # Classes row - show model classes
        rx.cond(
            TrainingState.selected_run.classes.length() > 0,
            rx.hstack(
                rx.text("Classes:", size="1", style={"color": styles.TEXT_SECONDARY}),
                rx.hstack(
                    rx.foreach(
                        TrainingState.selected_run.classes,
                        lambda cls: rx.badge(cls, color_scheme="gray", size="1", variant="surface"),
                    ),
                    spacing="1",
                    wrap="wrap",
                ),
                spacing="2",
                align="center",
                style={"margin_top": "4px"},
            ),
            rx.fragment(),
        ),
        # Datasets row - show datasets used in training
        rx.cond(
            TrainingState.selected_run.dataset_names.length() > 0,
            rx.hstack(
                rx.text("Datasets:", size="1", style={"color": styles.TEXT_SECONDARY}),
                rx.hstack(
                    rx.foreach(
                        TrainingState.selected_run.dataset_names,
                        lambda ds: rx.badge(ds, color_scheme="green", size="1", variant="surface"),
                    ),
                    spacing="1",
                    wrap="wrap",
                ),
                spacing="2",
                align="center",
                style={"margin_top": "4px"},
            ),
            rx.fragment(),
        ),
        # Notes section (collapsible)
        rx.cond(
            TrainingState.editing_notes,
            # Edit mode
            rx.vstack(
                rx.text_area(
                    value=TrainingState.temp_notes,
                    on_change=TrainingState.set_temp_notes,
                    on_key_down=TrainingState.handle_notes_keydown,
                    placeholder="Add notes about this training run...",
                    style={"width": "100%", "min_height": "80px"},
                ),
                rx.hstack(
                    rx.button(
                        "Save Notes",
                        size="1",
                        variant="outline",
                        color_scheme="green",
                        on_click=TrainingState.save_notes,
                    ),
                    rx.button(
                        "Cancel",
                        size="1",
                        variant="ghost",
                        on_click=TrainingState.cancel_editing_notes,
                    ),
                    spacing="2",
                ),
                width="100%",
                spacing="2",
            ),
            # Display mode - show notes or "add notes" prompt
            rx.cond(
                TrainingState.selected_run_notes != "",
                rx.box(
                    rx.hstack(
                        rx.icon("sticky-note", size=14, color=styles.TEXT_SECONDARY),
                        rx.text(
                            TrainingState.selected_run_notes,
                            size="1",
                            style={"color": styles.TEXT_SECONDARY},
                        ),
                        rx.icon_button(
                            rx.icon("pencil", size=10),
                            size="1",
                            variant="ghost",
                            on_click=TrainingState.start_editing_notes,
                            style={"opacity": "0.6"},
                        ),
                        spacing="2",
                        align="center",
                    ),
                    style={
                        "padding": "8px 12px",
                        "background": styles.BG_TERTIARY,
                        "border_radius": styles.RADIUS_SM,
                        "margin_top": "8px",
                    },
                ),
                rx.button(
                    rx.icon("plus", size=12),
                    "Add notes",
                    size="1",
                    variant="ghost",
                    on_click=TrainingState.start_editing_notes,
                    style={"margin_top": "4px", "opacity": "0.6"},
                ),
            ),
        ),
        width="100%",
        spacing="2",
        style={"padding": f"0 {styles.SPACING_6} {styles.SPACING_4}"},
    )


def metric_card_with_tooltip(label: str, value: rx.Var, tooltip: str, color: str = styles.ACCENT) -> rx.Component:
    """Individual metric display card with educational tooltip."""
    return rx.box(
        rx.vstack(
            rx.hstack(
                rx.text(label, size="1", style={"color": styles.TEXT_SECONDARY}),
                rx.tooltip(
                    rx.icon("info", size=12, color=styles.TEXT_SECONDARY, cursor="help"),
                    content=tooltip,
                ),
                spacing="1",
                align="center",
                justify="center",
            ),
            rx.text(
                value,
                size="5",
                weight="bold",
                style={"color": color},
            ),
            spacing="1",
            align="center",
        ),
        style={
            "padding": styles.SPACING_4,
            "background": styles.BG_SECONDARY,
            "border": f"1px solid {styles.BORDER}",
            "border_radius": styles.RADIUS_LG,
            "flex": "1",
            "text_align": "center",
        },
    )


# Legacy function for backwards compatibility
def metric_card(label: str, value: rx.Var, color: str = styles.ACCENT) -> rx.Component:
    """Individual metric display card without tooltip."""
    return metric_card_with_tooltip(label, value, "", color)


def metrics_row() -> rx.Component:
    """Row of Priority 1 essential metric cards with educational tooltips."""
    return rx.box(
        metric_card_with_tooltip(
            "mAP@50-95",
            TrainingState.selected_run_metrics.get("mAP50-95", 0).to(float).to_string()[:5],
            "Mean Average Precision averaged over IoU thresholds 0.50-0.95. This is the gold standard metric for object detection. Values above 0.7 indicate excellent performance. Below 0.3 suggests the model needs more training or better data.",
            styles.ACCENT,
        ),
        metric_card_with_tooltip(
            "mAP@50",
            TrainingState.selected_run_metrics.get("mAP50", 0).to(float).to_string()[:5],
            "Mean Average Precision at IoU=0.50. This is more lenient than mAP@50-95. Good for evaluating if your model can roughly locate objects. Aim for >0.8 for production models.",
            styles.SUCCESS,
        ),
        metric_card_with_tooltip(
            "Precision",
            TrainingState.selected_run_metrics.get("precision", 0).to(float).to_string()[:5],
            "Percentage of correct predictions among all detections. High precision (>0.9) means few false positives. Low precision means the model is detecting objects that aren't there.",
            styles.WARNING,
        ),
        metric_card_with_tooltip(
            "Recall",
            TrainingState.selected_run_metrics.get("recall", 0).to(float).to_string()[:5],
            "Percentage of actual objects that were detected. High recall (>0.9) means few missed objects. Low recall means the model is missing objects it should find.",
            styles.PURPLE,  # Purple
        ),
        metric_card_with_tooltip(
            "F1 Score",
            TrainingState.f1_score.to(float).to_string()[:5],
            "Harmonic mean of precision and recall. This is the best single metric when you need a balance. Values above 0.8 indicate well-balanced performance.",
            styles.SUCCESS,  # Green
        ),
        metric_card_with_tooltip(
            "Best Epoch",
            TrainingState.best_epoch.to(str),
            "The epoch with highest mAP@50-95. If this is much earlier than the last epoch, early stopping would have saved time. We automatically save weights from the best epoch.",
            styles.EARTH_CLAY,  # Warm clay
        ),
        display="grid",
        style={
            "grid_template_columns": "repeat(6, minmax(0, 1fr))",
            "gap": styles.SPACING_3,
            "padding": f"0 {styles.SPACING_6}",
            "width": "100%",
        },
    )


def classification_metrics_row() -> rx.Component:
    """Row of classification-specific metric cards with tooltips."""
    return rx.box(
        metric_card_with_tooltip(
            "Top-1 Accuracy",
            TrainingState.selected_run_metrics.get("top1_accuracy", 0).to(float).to_string()[:5],
            "Percentage of predictions where the top predicted class matches the ground truth. Values above 0.9 indicate excellent performance for species classification.",
            styles.ACCENT,
        ),
        metric_card_with_tooltip(
            "Top-5 Accuracy",
            TrainingState.selected_run_metrics.get("top5_accuracy", 0).to(float).to_string()[:5],
            "Percentage of predictions where the ground truth is within the top 5 predicted classes. Useful for multi-class scenarios where similar species may be confused.",
            styles.SUCCESS,
        ),
        metric_card_with_tooltip(
            "Final Loss",
            TrainingState.selected_run_metrics.get("loss", 0).to(float).to_string()[:5],
            "Final training loss. Lower is better. Values below 0.5 typically indicate good convergence for classification tasks.",
            styles.WARNING,
        ),
        metric_card_with_tooltip(
            "Val Loss",
            TrainingState.selected_run_metrics.get("val_loss", 0).to(float).to_string()[:5],
            "Validation loss. Should be close to training loss. If much higher, the model may be overfitting.",
            styles.PURPLE,  # Purple
        ),
        metric_card_with_tooltip(
            "Best Epoch",
            TrainingState.best_epoch.to(str),
            "The epoch with best validation accuracy. If this is much earlier than the last epoch, early stopping would have saved time.",
            styles.EARTH_CLAY,  # Warm clay
        ),
        display="grid",
        style={
            "grid_template_columns": "repeat(5, minmax(0, 1fr))",
            "gap": styles.SPACING_3,
            "padding": f"0 {styles.SPACING_6}",
            "width": "100%",
        },
    )


def accuracy_chart() -> rx.Component:
    """Chart showing Top-1 and Top-5 accuracy over epochs for classification."""
    return rx.recharts.line_chart(
        rx.recharts.line(
            data_key="metrics/accuracy_top1",
            stroke=styles.ACCENT,
            name="Top-1 Acc",
            dot=False,
        ),
        rx.recharts.line(
            data_key="metrics/accuracy_top5",
            stroke=styles.SUCCESS,
            name="Top-5 Acc",
            dot=False,
        ),
        rx.recharts.x_axis(
            data_key="epoch",
            stroke=styles.TEXT_SECONDARY,
            type="number",
            domain=["dataMin", "dataMax"],
        ),
        rx.recharts.y_axis(stroke=styles.TEXT_SECONDARY, domain=[0, 1]),
        rx.recharts.legend(),
        rx.recharts.graphing_tooltip(),
        data=TrainingState.results_csv_data,
        width="100%",
        height=250,
    )


def classification_loss_chart() -> rx.Component:
    """Chart showing training and validation loss for classification."""
    return rx.recharts.line_chart(
        rx.recharts.line(
            data_key="train/loss",
            stroke=styles.ACCENT,
            name="Train Loss",
            dot=False,
        ),
        rx.recharts.line(
            data_key="val/loss",
            stroke=styles.SUCCESS,
            name="Val Loss",
            dot=False,
            stroke_dasharray="5 5",
        ),
        rx.recharts.x_axis(
            data_key="epoch",
            stroke=styles.TEXT_SECONDARY,
            type="number",
            domain=["dataMin", "dataMax"],
        ),
        rx.recharts.y_axis(stroke=styles.TEXT_SECONDARY),
        rx.recharts.legend(),
        rx.recharts.graphing_tooltip(),
        data=TrainingState.results_csv_data,
        width="100%",
        height=250,
    )


def classification_charts_section() -> rx.Component:
    """Charts section for classification training runs."""
    return rx.cond(
        TrainingState.results_csv_data.length() > 0,
        rx.vstack(
            rx.hstack(
                rx.icon("bar-chart-3", size=18, color=styles.ACCENT),
                rx.text(
                    "Classification Training Progress",
                    size="3",
                    weight="bold",
                    style={"color": styles.TEXT_PRIMARY},
                ),
                spacing="2",
                align="center",
            ),
            rx.grid(
                chart_with_tooltip(
                    "Accuracy Over Epochs",
                    "Track how classification accuracy improves during training. Top-1 should steadily increase. Top-5 accuracy is usually higher and shows if the model is learning related classes.",
                    accuracy_chart(),
                ),
                chart_with_tooltip(
                    "Train vs Val Loss",
                    "Training and validation loss should both decrease. If validation loss increases while training decreases, you're overfitting. Consider data augmentation or more training data.",
                    classification_loss_chart(),
                ),
                chart_with_tooltip(
                    "Learning Rate Schedule",
                    "Learning rate should decrease over time for fine-tuning. Classification models typically use lower learning rates than detection models.",
                    learning_rate_chart(),
                ),
                style={
                    "display": "grid",
                    "grid_template_columns": "repeat(2, minmax(0, 1fr))",
                    "gap": styles.SPACING_3,
                    "width": "100%",
                },
            ),
            spacing="3",
            width="100%",
            style={"padding": f"{styles.SPACING_4} {styles.SPACING_6}"},
        ),
        rx.fragment(),
    )


def loss_chart() -> rx.Component:
    """Chart showing loss curves over epochs."""
    return rx.box(
        rx.vstack(
            rx.text("Loss Curves", size="2", weight="medium", style={"color": styles.TEXT_PRIMARY}),
            rx.recharts.line_chart(
                rx.recharts.line(
                    data_key="train/box_loss",
                    stroke=styles.ACCENT,
                    name="Box Loss",
                    dot=False,
                ),
                rx.recharts.line(
                    data_key="train/cls_loss",
                    stroke=styles.SUCCESS,
                    name="Class Loss",
                    dot=False,
                ),
                rx.recharts.line(
                    data_key="train/dfl_loss",
                    stroke=styles.WARNING,
                    name="DFL Loss",
                    dot=False,
                ),
                rx.recharts.x_axis(
                    data_key="epoch",
                    stroke=styles.TEXT_SECONDARY,
                    type="number",
                    domain=["dataMin", "dataMax"],
                ),
                rx.recharts.y_axis(stroke=styles.TEXT_SECONDARY),
                rx.recharts.legend(),
                rx.recharts.graphing_tooltip(),
                data=TrainingState.results_csv_data,
                width="100%",
                height=250,
            ),
            spacing="2",
            width="100%",
        ),
        style={
            "padding": styles.SPACING_4,
            "background": styles.BG_SECONDARY,
            "border": f"1px solid {styles.BORDER}",
            "border_radius": styles.RADIUS_LG,
        },
    )


def map_chart() -> rx.Component:
    """Chart showing mAP over epochs."""
    return rx.recharts.line_chart(
        rx.recharts.line(
            data_key="metrics/mAP50(B)",
            stroke=styles.SUCCESS,
            name="mAP@50",
            dot=False,
        ),
        rx.recharts.line(
            data_key="metrics/mAP50-95(B)",
            stroke=styles.ACCENT,
            name="mAP@50-95",
            dot=False,
        ),
        rx.recharts.x_axis(
            data_key="epoch",
            stroke=styles.TEXT_SECONDARY,
            type="number",
            domain=["dataMin", "dataMax"],
        ),
        rx.recharts.y_axis(stroke=styles.TEXT_SECONDARY, domain=[0, 1]),
        rx.recharts.legend(),
        rx.recharts.graphing_tooltip(),
        data=TrainingState.results_csv_data,
        width=500,
        height=250,
    )


def pr_chart() -> rx.Component:
    """Chart showing Precision/Recall over epochs."""
    return rx.recharts.line_chart(
        rx.recharts.line(
            data_key="metrics/precision(B)",
            stroke=styles.WARNING,
            name="Precision",
            dot=False,
        ),
        rx.recharts.line(
            data_key="metrics/recall(B)",
            stroke=styles.PURPLE,
            name="Recall",
            dot=False,
        ),
        rx.recharts.x_axis(
            data_key="epoch",
            stroke=styles.TEXT_SECONDARY,
            type="number",
            domain=["dataMin", "dataMax"],
        ),
        rx.recharts.y_axis(stroke=styles.TEXT_SECONDARY, domain=[0, 1]),
        rx.recharts.legend(),
        rx.recharts.graphing_tooltip(),
        data=TrainingState.results_csv_data,
        width=500,
        height=250,
    )


def chart_with_tooltip(title: str, tooltip: str, chart_component) -> rx.Component:
    """Wrapper for charts with educational tooltip."""
    return rx.box(
        rx.vstack(
            rx.hstack(
                rx.text(title, size="2", weight="medium", style={"color": styles.TEXT_PRIMARY}),
                rx.tooltip(
                    rx.icon("info", size=14, color=styles.TEXT_SECONDARY, cursor="help"),
                    content=tooltip,
                ),
                spacing="2",
                align="center",
            ),
            rx.box(
                chart_component,
                height="250px",
                style={"min_width": "0", "overflow": "hidden"},
            ),
            spacing="2",
            width="100%",
        ),
        style={
            "padding": styles.SPACING_4,
            "background": styles.BG_SECONDARY,
            "border": f"1px solid {styles.BORDER}",
            "border_radius": styles.RADIUS_LG,
            "overflow": "hidden",
            "min_width": "0",
        },
    )


# =========================================================================
# Priority 2: Training Health Charts
# =========================================================================

def train_val_loss_chart() -> rx.Component:
    """Chart comparing training vs validation losses."""
    return rx.recharts.line_chart(
        rx.recharts.line(
            data_key="train_box_loss",
            stroke=styles.ACCENT,
            name="Train Box Loss",
            dot=False,
        ),
        rx.recharts.line(
            data_key="val_box_loss",
            stroke=styles.SUCCESS,
            name="Val Box Loss",
            dot=False,
            stroke_dasharray="5 5",
        ),
        rx.recharts.line(
            data_key="train_cls_loss",
            stroke=styles.WARNING,
            name="Train Cls Loss",
            dot=False,
        ),
        rx.recharts.line(
            data_key="val_cls_loss",
            stroke=styles.EARTH_CLAY,
            name="Val Cls Loss",
            dot=False,
            stroke_dasharray="5 5",
        ),
        rx.recharts.x_axis(
            data_key="epoch",
            stroke=styles.TEXT_SECONDARY,
            type="number",
            domain=["dataMin", "dataMax"],
        ),
        rx.recharts.y_axis(stroke=styles.TEXT_SECONDARY),
        rx.recharts.legend(),
        rx.recharts.graphing_tooltip(),
        data=TrainingState.train_val_loss_data,
        width=500,
        height=250,
    )


def loss_components_chart() -> rx.Component:
    """Chart showing breakdown of loss components."""
    return rx.recharts.area_chart(
        rx.recharts.area(
            data_key="box_loss",
            stroke=styles.ACCENT,
            fill=styles.ACCENT,
            name="Box Loss",
            stack_id="1",
        ),
        rx.recharts.area(
            data_key="cls_loss",
            stroke=styles.SUCCESS,
            fill=styles.SUCCESS,
            name="Cls Loss",
            stack_id="1",
        ),
        rx.recharts.area(
            data_key="dfl_loss",
            stroke=styles.WARNING,
            fill=styles.WARNING,
            name="DFL Loss",
            stack_id="1",
        ),
        rx.recharts.x_axis(
            data_key="epoch",
            stroke=styles.TEXT_SECONDARY,
            type="number",
            domain=["dataMin", "dataMax"],
        ),
        rx.recharts.y_axis(stroke=styles.TEXT_SECONDARY),
        rx.recharts.legend(),
        rx.recharts.graphing_tooltip(),
        data=TrainingState.loss_components_data,
        width=500,
        height=250,
    )


def learning_rate_chart() -> rx.Component:
    """Chart showing learning rate schedule."""
    return rx.recharts.line_chart(
        rx.recharts.line(
            data_key="learning_rate",
            stroke=styles.ACCENT,
            name="Learning Rate",
            dot=False,
        ),
        rx.recharts.x_axis(
            data_key="epoch",
            stroke=styles.TEXT_SECONDARY,
            type="number",
            domain=["dataMin", "dataMax"],
        ),
        rx.recharts.y_axis(stroke=styles.TEXT_SECONDARY),
        rx.recharts.graphing_tooltip(),
        data=TrainingState.learning_rate_data,
        width=500,
        height=250,
    )


# =========================================================================
# Priority 3: Progress Tracking Charts
# =========================================================================

def f1_score_chart() -> rx.Component:
    """Chart showing F1 score progression."""
    return rx.recharts.line_chart(
        rx.recharts.line(
            data_key="f1_score",
            stroke=styles.SUCCESS,
            name="F1 Score",
            dot=False,
        ),
        rx.recharts.x_axis(
            data_key="epoch",
            stroke=styles.TEXT_SECONDARY,
            type="number",
            domain=["dataMin", "dataMax"],
        ),
        rx.recharts.y_axis(stroke=styles.TEXT_SECONDARY, domain=[0, 1]),
        rx.recharts.graphing_tooltip(),
        data=TrainingState.f1_scores_data,
        width=500,
        height=250,
    )


def epoch_improvements_chart() -> rx.Component:
    """Chart showing epoch-by-epoch metric improvements."""
    return rx.recharts.line_chart(
        rx.recharts.line(
            data_key="delta_mAP50-95",
            stroke=styles.ACCENT,
            name="ΔmAP50-95",
            dot=False,
        ),
        rx.recharts.line(
            data_key="delta_precision",
            stroke=styles.WARNING,
            name="ΔPrecision",
            dot=False,
        ),
        rx.recharts.line(
            data_key="delta_recall",
            stroke=styles.PURPLE,
            name="ΔRecall",
            dot=False,
        ),
        rx.recharts.x_axis(
            data_key="epoch",
            stroke=styles.TEXT_SECONDARY,
            type="number",
            domain=["dataMin", "dataMax"],
        ),
        rx.recharts.y_axis(stroke=styles.TEXT_SECONDARY),
        rx.recharts.legend(),
        rx.recharts.graphing_tooltip(),
        rx.recharts.reference_line(y=0, stroke=styles.TEXT_SECONDARY, stroke_dasharray="3 3"),
        data=TrainingState.epoch_improvements_data,
        width=500,
        height=250,
    )


def training_efficiency_chart() -> rx.Component:
    """Chart showing time per epoch."""
    return rx.recharts.bar_chart(
        rx.recharts.bar(
            data_key="epoch_time",
            fill=styles.ACCENT,
            name="Time (seconds)",
        ),
        rx.recharts.x_axis(
            data_key="epoch",
            stroke=styles.TEXT_SECONDARY,
            type="number",
            domain=["dataMin", "dataMax"],
        ),
        rx.recharts.y_axis(stroke=styles.TEXT_SECONDARY),
        rx.recharts.graphing_tooltip(),
        data=TrainingState.training_efficiency_data,
        width=500,
        height=250,
    )


# =========================================================================
# Chart Sections (Priority-Based Organization)
# =========================================================================

def priority_2_charts_section() -> rx.Component:
    """Priority 2: Training Health charts with tooltips."""
    return rx.cond(
        TrainingState.results_csv_data.length() > 0,
        rx.vstack(
            rx.hstack(
                rx.icon("heart-pulse", size=18, color=styles.ACCENT),
                rx.text(
                    "Training Health",
                    size="3",
                    weight="bold",
                    style={"color": styles.TEXT_PRIMARY},
                ),
                spacing="2",
                align="center",
            ),
            rx.box(
                chart_with_tooltip(
                    "Train vs Val Loss",
                    "Training and validation losses should both decrease and converge. If validation loss increases while training decreases, you're overfitting. If both plateau early, try more epochs or lower learning rate.",
                    train_val_loss_chart(),
                ),
                chart_with_tooltip(
                    "Loss Components",
                    "Box loss measures localization accuracy, class loss measures classification accuracy, DFL loss refines box boundaries. If one component is stuck while others decrease, that's where your model struggles.",
                    loss_components_chart(),
                ),
                chart_with_tooltip(
                    "Learning Rate Schedule",
                    "Learning rate should start high and gradually decrease. Sudden jumps indicate optimizer issues. If it stays flat, adaptive optimizers like Adam are managing it automatically.",
                    learning_rate_chart(),
                ),
                chart_with_tooltip(
                    "mAP Over Epochs",
                    "Track how your model improves over time. A healthy curve shows rapid initial improvement that slows down. If it plateaus early, try training longer or adjusting hyperparameters.",
                    map_chart(),
                ),
                display="grid",
                style={
                    "grid_template_columns": "repeat(2, minmax(0, 1fr))",
                    "gap": styles.SPACING_3,
                    "width": "100%",
                },
            ),
            spacing="3",
            width="100%",
            style={"padding": f"{styles.SPACING_4} {styles.SPACING_6}"},
        ),
        rx.fragment(),
    )


def priority_3_charts_section() -> rx.Component:
    """Priority 3: Progress Tracking charts with tooltips."""
    return rx.cond(
        TrainingState.results_csv_data.length() > 0,
        rx.vstack(
            rx.hstack(
                rx.icon("trending-up", size=18, color=styles.ACCENT),
                rx.text(
                    "Progress Tracking",
                    size="3",
                    weight="bold",
                    style={"color": styles.TEXT_PRIMARY},
                ),
                spacing="2",
                align="center",
            ),
            rx.box(
                chart_with_tooltip(
                    "Precision & Recall Curves",
                    "Precision and recall often trade off. Ideally, both increase together. If precision drops while recall rises, lower your confidence threshold.",
                    pr_chart(),
                ),
                chart_with_tooltip(
                    "Epoch-by-Epoch Improvements",
                    "Shows per-epoch gains in key metrics. Early epochs should show large improvements. If improvements turn negative or oscillate wildly, reduce learning rate.",
                    epoch_improvements_chart(),
                ),
                chart_with_tooltip(
                    "F1 Score Over Time",
                    "F1 score balances precision and recall. A steady upward trend indicates healthy, balanced improvement. Plateaus suggest the model has reached its capacity.",
                    f1_score_chart(),
                ),
                chart_with_tooltip(
                    "Training Efficiency",
                    "Monitor training efficiency. Increasing time per epoch might indicate memory issues or data loading bottlenecks. Typical: 1-5 min/epoch for small datasets on GPU.",
                    training_efficiency_chart(),
                ),
                display="grid",
                style={
                    "grid_template_columns": "repeat(2, minmax(0, 1fr))",
                    "gap": styles.SPACING_3,
                    "width": "100%",
                },
            ),
            spacing="3",
            width="100%",
            style={"padding": f"{styles.SPACING_4} {styles.SPACING_6}"},
        ),
        rx.fragment(),
    )


def charts_section() -> rx.Component:
    """Legacy charts section - now deprecated, kept for backwards compatibility."""
    return rx.fragment()


def artifact_thumbnail(url: rx.Var, label: str) -> rx.Component:
    """Single artifact thumbnail in the gallery - clickable to open popup."""
    return rx.cond(
        url != "",
        rx.dialog.root(
            rx.dialog.trigger(
                rx.box(
                    rx.vstack(
                        rx.box(
                            rx.image(
                                src=url,
                                alt=label,
                                style={
                                    "width": "100%",
                                    "height": "180px",
                                    "object_fit": "cover",
                                    "border_radius": styles.RADIUS_MD,
                                    "transition": "transform 0.2s ease",
                                },
                                _hover={"transform": "scale(1.02)"},
                            ),
                            style={
                                "border": f"1px solid {styles.BORDER}",
                                "border_radius": styles.RADIUS_MD,
                                "overflow": "hidden",
                                "cursor": "pointer",
                            },
                        ),
                        rx.text(
                            label,
                            size="1",
                            style={"color": styles.TEXT_SECONDARY, "text_align": "center"},
                        ),
                        spacing="1",
                        align="center",
                        width="100%",
                    ),
                ),
            ),
            rx.dialog.content(
                rx.dialog.title(label, style={"display": "none"}),
                rx.vstack(
                    rx.image(
                        src=url,
                        alt=label,
                        style={
                            "max_width": "100%",
                            "max_height": "75vh",
                            "border_radius": styles.RADIUS_MD,
                        },
                    ),
                    rx.text(
                        label,
                        size="2",
                        weight="medium",
                        style={"color": styles.TEXT_PRIMARY},
                    ),
                    align="center",
                    spacing="2",
                ),
                style={
                    "background": styles.BG_SECONDARY,
                    "border_radius": styles.RADIUS_LG,
                    "padding": "12px",
                    "width": "auto",
                    "max_width": "fit-content",
                },
            ),
        ),
        rx.fragment(),
    )


def confusion_matrix_table() -> rx.Component:
    """Compact interactive confusion matrix with fixed-size cells."""
    CELL = "96px"
    LABEL_W = "100px"

    def cm_cell(row_idx: rx.Var, col_idx: rx.Var, value: rx.Var) -> rx.Component:
        is_diagonal = row_idx == col_idx
        return rx.tooltip(
            rx.box(
                rx.text(
                    rx.cond(value > 0, value.to(str), ""),
                    style={
                        "color": rx.cond(value > 0, "#fff", "transparent"),
                        "font_family": styles.FONT_FAMILY_MONO,
                        "font_size": "10px",
                    },
                ),
                style={
                    "width": CELL,
                    "height": CELL,
                    "display": "flex",
                    "align_items": "center",
                    "justify_content": "center",
                    "background": rx.cond(
                        value > 0,
                        rx.cond(is_diagonal, "rgba(34,197,94,0.7)", "rgba(239,68,68,0.5)"),
                        styles.BG_TERTIARY,
                    ),
                    "border_radius": "2px",
                    "flex_shrink": "0",
                },
            ),
            content=rx.cond(
                TrainingState.confusion_matrix_classes.length() > 0,
                "Actual: " + TrainingState.confusion_matrix_classes[row_idx].to(str)
                + " → Predicted: " + TrainingState.confusion_matrix_classes[col_idx].to(str)
                + " | Count: " + value.to(str),
                value.to(str),
            ),
        )

    def cm_row(row_idx: rx.Var, row: rx.Var) -> rx.Component:
        return rx.hstack(
            rx.tooltip(
                rx.text(
                    rx.cond(
                        TrainingState.confusion_matrix_classes.length() > 0,
                        TrainingState.confusion_matrix_classes[row_idx],
                        row_idx.to(str),
                    ),
                    size="1",
                    style={
                        "color": styles.TEXT_SECONDARY,
                        "width": LABEL_W,
                        "text_align": "right",
                        "overflow": "hidden",
                        "text_overflow": "ellipsis",
                        "white_space": "nowrap",
                        "font_size": "10px",
                        "flex_shrink": "0",
                    },
                ),
                content=rx.cond(
                    TrainingState.confusion_matrix_classes.length() > 0,
                    TrainingState.confusion_matrix_classes[row_idx],
                    row_idx.to(str),
                ),
            ),
            rx.hstack(
                rx.foreach(
                    row,
                    lambda value, col_idx: cm_cell(row_idx, col_idx, value),
                ),
                spacing="1",
            ),
            spacing="1",
            align="center",
        )

    return rx.cond(
        TrainingState.confusion_matrix_data.length() > 0,
        rx.vstack(
            rx.text("Confusion Matrix", size="2", weight="bold", style={"color": styles.TEXT_PRIMARY}),
            rx.text("Rows = Actual · Columns = Predicted", size="1", style={"color": styles.TEXT_SECONDARY, "opacity": "0.7"}),
            # Column headers
            rx.hstack(
                rx.box(style={"width": LABEL_W, "flex_shrink": "0"}),
                rx.hstack(
                    rx.foreach(
                        TrainingState.confusion_matrix_classes,
                        lambda cls_name: rx.tooltip(
                            rx.text(
                                cls_name,
                                size="1",
                                style={
                                    "color": styles.TEXT_SECONDARY,
                                    "font_size": "9px",
                                    "width": CELL,
                                    "text_align": "center",
                                    "overflow": "hidden",
                                    "text_overflow": "ellipsis",
                                    "white_space": "nowrap",
                                    "flex_shrink": "0",
                                },
                            ),
                            content=cls_name,
                        ),
                    ),
                    spacing="1",
                ),
                spacing="1",
                align="end",
            ),
            # Matrix rows
            rx.vstack(
                rx.foreach(
                    TrainingState.confusion_matrix_data,
                    lambda row, row_idx: cm_row(row_idx, row),
                ),
                spacing="1",
            ),
            # Legend
            rx.hstack(
                rx.hstack(
                    rx.box(style={"width": "10px", "height": "10px", "background": "rgba(34,197,94,0.7)", "border_radius": "2px"}),
                    rx.text("Correct", size="1", style={"color": styles.TEXT_SECONDARY}),
                    spacing="1", align="center",
                ),
                rx.hstack(
                    rx.box(style={"width": "10px", "height": "10px", "background": "rgba(239,68,68,0.5)", "border_radius": "2px"}),
                    rx.text("Misclassified", size="1", style={"color": styles.TEXT_SECONDARY}),
                    spacing="1", align="center",
                ),
                spacing="4",
                style={"margin_top": styles.SPACING_2},
            ),
            spacing="2",
            style={
                "background": styles.BG_SECONDARY,
                "padding": styles.SPACING_4,
                "border": f"1px solid {styles.BORDER}",
                "border_radius": styles.RADIUS_MD,
                "overflow_x": "auto",
                "max_width": "fit-content",
                "margin": "0 auto",
            },
        ),
        rx.fragment(),
    )


def artifacts_section() -> rx.Component:
    """Section showing training artifact images in a stylish gallery grid."""
    return rx.cond(
        # ConvNeXt runs: show train batch + confusion matrix
        TrainingState.selected_run_is_convnext,
        rx.vstack(
            rx.hstack(
                rx.icon("images", size=18, color=styles.ACCENT),
                rx.text(
                    "Training Artifacts",
                    size="3",
                    weight="bold",
                    style={"color": styles.TEXT_PRIMARY},
                ),
                spacing="2",
                align="center",
            ),
            # Train batch images (3 grids, same naming as YOLO)
            artifact_thumbnail(TrainingState.train_batch0_url, "Train Batch 1"),
            artifact_thumbnail(TrainingState.train_batch1_url, "Train Batch 2"),
            artifact_thumbnail(TrainingState.train_batch2_url, "Train Batch 3"),
            # Confusion matrix (interactive)
            confusion_matrix_table(),
            spacing="3",
            width="100%",
            style={
                "padding": f"{styles.SPACING_4} {styles.SPACING_6}",
            },
        ),
        # YOLO runs produce full artifacts gallery
        rx.vstack(
            rx.hstack(
                rx.icon("images", size=18, color=styles.ACCENT),
                rx.text(
                    "Training Artifacts",
                    size="3",
                    weight="bold",
                    style={"color": styles.TEXT_PRIMARY},
                ),
                spacing="2",
                align="center",
            ),
            # Main gallery grid - 3 columns
            rx.grid(
                # Row 1: Analysis plots
                artifact_thumbnail(TrainingState.confusion_matrix_url, "Confusion Matrix"),
                artifact_thumbnail(TrainingState.labels_jpg_url, "Label Distribution"),
                artifact_thumbnail(TrainingState.train_batch0_url, "Train Batch 1"),
                # Row 2: More training samples
                artifact_thumbnail(TrainingState.train_batch1_url, "Train Batch 2"),
                artifact_thumbnail(TrainingState.train_batch2_url, "Train Batch 3"),
                artifact_thumbnail(TrainingState.val_batch_labels_url, "Val Labels (GT)"),
                # Row 3: Validation predictions
                artifact_thumbnail(TrainingState.val_batch_pred_url, "Val Predictions"),
                columns="3",
                spacing="3",
                width="100%",
            ),
            rx.text(
                "Click on any image to view full size",
                size="1",
                style={"color": styles.TEXT_SECONDARY, "opacity": "0.7"},
            ),
            spacing="3",
            width="100%",
            style={
                "padding": f"{styles.SPACING_4} {styles.SPACING_6}",
            },
        ),
    )


def logs_section() -> rx.Component:
    """Section showing training logs."""
    return rx.vstack(
        rx.hstack(
            rx.icon("scroll-text", size=18, color=styles.ACCENT),
            rx.text(
                "Training Logs",
                size="3",
                weight="bold",
                style={"color": styles.TEXT_PRIMARY},
            ),
            spacing="2",
            align="center",
        ),
        rx.box(
            rx.scroll_area(
                rx.text(
                    TrainingState.selected_run_logs,
                    font_family="JetBrains Mono, monospace",
                    white_space="pre-wrap",
                    size="1",
                    style={
                        "color": styles.CODE_TEXT,
                        "line_height": "1.5",
                    },
                ),
                type="always",
                scrollbars="vertical",
                style={"height": "400px"},
                id="run-detail-logs-scroll",
            ),
            style={
                "background": styles.CODE_BG,
                "padding": styles.SPACING_4,
                "border_radius": styles.RADIUS_LG,
                "border": f"1px solid {styles.BORDER}",
                "width": "100%",
            },
        ),
        spacing="3",
        width="100%",
        style={
            "padding": f"{styles.SPACING_4} {styles.SPACING_6}",
        },
    )


def error_section() -> rx.Component:
    """Section showing error details for failed runs."""
    return rx.cond(
        TrainingState.selected_run_error != "",
        rx.vstack(
            rx.text(
                "❌ Error Details",
                size="3",
                weight="bold",
                style={"color": styles.ERROR},
            ),
            rx.box(
                rx.text(
                    TrainingState.selected_run_error,
                    size="2",
                    style={"color": styles.ERROR, "white_space": "pre-wrap"},
                ),
                style={
                    "background": styles.BG_SECONDARY,
                    "padding": styles.SPACING_4,
                    "border_radius": styles.RADIUS_LG,
                    "border": f"1px solid {styles.ERROR}",
                    "width": "100%",
                },
            ),
            spacing="3",
            width="100%",
            style={
                "padding": f"{styles.SPACING_4} {styles.SPACING_6}",
            },
        ),
        rx.fragment(),
    )


def run_detail_content() -> rx.Component:
    """Main scrollable content for the run detail page (priority-based organization)."""
    return rx.scroll_area(
        rx.vstack(
            # Priority 1: Essential Metrics Row (mode-specific)
            rx.cond(
                TrainingState.selected_run.model_type == "classification",
                classification_metrics_row(),
                metrics_row(),  # Detection metrics
            ),
            
            # Priority 2 & 3: Charts (mode-specific)
            rx.cond(
                TrainingState.selected_run.model_type == "classification",
                classification_charts_section(),
                rx.vstack(
                    # Detection: Priority 2 Training Health
                    priority_2_charts_section(),
                    # Detection: Priority 3 Progress Tracking
                    priority_3_charts_section(),
                    width="100%",
                    spacing="0",
                ),
            ),
            
            # Priority 4: Artifacts (confusion matrix only)
            artifacts_section(),
            
            # Error section (only for failed runs)
            error_section(),
            
            # Logs terminal
            logs_section(),
            
            # Bottom padding
            rx.box(height="48px"),
            
            spacing="4",
            width="100%",
            style={"overflow_x": "hidden", "min_width": "0"},
        ),
        type="always",
        scrollbars="vertical",
        style={"height": "calc(100vh - 140px)", "width": "100%"},
    )


def run_detail_page_content() -> rx.Component:
    """Full page wrapper."""
    return rx.box(
        breadcrumb_nav(),
        run_header(),
        run_detail_content(),
        style={
            "background": styles.BG_PRIMARY,
            "min_height": "100vh",
            "max_width": "1400px",
            "margin": "0 auto",
        },
    )


@rx.page(
    route="/projects/[project_id]/train/[run_id]",
    title="Training Run | SAFARI",
    on_load=[AuthState.check_auth, TrainingState.load_run_detail],
)
def run_detail_page() -> rx.Component:
    """The run detail page (protected)."""
    return require_auth(run_detail_page_content())
