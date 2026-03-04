"""
Training Dashboard — Configure and launch training runs at project level.

Route: /projects/{project_id}/train
Allows selecting which datasets to include in training.
"""

import reflex as rx
import styles
from app_state import require_auth, AuthState
from modules.training.state import TrainingState, DatasetOption, TrainingRunModel
from components.nav_header import nav_header
from components.compute_target_toggle import compute_target_toggle


def section_header(title: str, icon: str, badge: rx.Component = None) -> rx.Component:
    """Reusable section header with icon and optional badge."""
    return rx.hstack(
        rx.icon(icon, size=14, color=styles.TEXT_SECONDARY),
        rx.text(title, size="1", weight="medium", style={"color": styles.TEXT_SECONDARY}),
        rx.cond(badge is not None, badge, rx.fragment()) if badge else rx.fragment(),
        width="100%",
        align="center",
        style={"margin_bottom": "8px"},
    )


def config_section(
    title: str,
    icon: str,
    content: rx.Component,
    accent_color: str = styles.ACCENT,
    collapsed: bool = False,
) -> rx.Component:
    """
    Bold section container with colored left border accent.
    Creates strong visual separation between configuration areas.
    """
    return rx.box(
        rx.vstack(
            # Section header
            rx.hstack(
                rx.icon(icon, size=16, color=accent_color),
                rx.text(title, size="2", weight="medium", style={"color": styles.TEXT_PRIMARY}),
                width="100%",
                align="center",
            ),
            # Content
            rx.box(
                content,
                style={
                    "padding_top": "12px",
                    "width": "100%",
                },
            ),
            spacing="0",
            width="100%",
        ),
        style={
            "background": styles.BG_TERTIARY,
            "border_left": f"3px solid {accent_color}",
            "border_radius": styles.RADIUS_MD,
            "padding": "12px 14px",
            "width": "100%",
        },
    )


def breadcrumb_nav() -> rx.Component:
    """Breadcrumb navigation."""
    return rx.hstack(
        rx.link(
            rx.text("Dashboard", size="2", style={"color": styles.TEXT_SECONDARY}),
            href="/dashboard",
        ),
        rx.icon("chevron-right", size=14, color=styles.TEXT_SECONDARY),
        rx.link(
            rx.text(TrainingState.project_name, size="2", style={"color": styles.TEXT_SECONDARY}),
            href=f"/projects/{TrainingState.current_project_id}",
        ),
        rx.icon("chevron-right", size=14, color=styles.TEXT_SECONDARY),
        rx.text("Training", size="2", weight="medium", style={"color": styles.TEXT_PRIMARY}),
        spacing="2",
        align="center",
        style={"padding": f"{styles.SPACING_4} {styles.SPACING_6}"},
    )


def page_header() -> rx.Component:
    """Page header with title."""
    return rx.hstack(
        rx.vstack(
            rx.heading(
                "Training Dashboard",
                size="6",
                weight="bold",
                style={"color": styles.TEXT_PRIMARY},
            ),
            rx.text(
                f"Train a YOLO model using datasets from {TrainingState.project_name}",
                size="2",
                style={"color": styles.TEXT_SECONDARY},
            ),
            spacing="1",
            align="start",
        ),
        width="100%",
        style={
            "padding": f"0 {styles.SPACING_6} {styles.SPACING_4}",
        },
    )


def dataset_checkbox(dataset: DatasetOption) -> rx.Component:
    """Single dataset row with checkbox."""
    type_icon = rx.cond(
        dataset.type == "video",
        rx.icon("video", size=14, color=styles.WARNING),
        rx.icon("image", size=14, color=styles.ACCENT),
    )
    
    tag_badge = rx.cond(
        dataset.usage_tag == "validation",
        rx.badge("Val", color_scheme="purple", size="1", variant="outline"),
        rx.badge("Train", color_scheme="green", size="1", variant="outline"),
    )
    
    return rx.hstack(
        rx.checkbox(
            checked=dataset.is_selected,
            on_change=lambda _: TrainingState.toggle_dataset(dataset.id),
            size="1",
        ),
        type_icon,
        rx.text(dataset.name, size="1", style={"color": styles.TEXT_PRIMARY}, truncate=True),
        tag_badge,
        rx.spacer(),
        rx.badge(
            f"{dataset.labeled_count}",
            color_scheme=rx.cond(dataset.labeled_count > 0, "green", "gray"),
            variant="outline",
            size="1",
        ),
        spacing="2",
        align="center",
        width="100%",
        style={
            "padding": "6px",
            "border_radius": styles.RADIUS_SM,
            "&:hover": {"background": styles.BG_TERTIARY},
        },
    )


def datasets_selection_card() -> rx.Component:
    """Card for selecting which datasets to include in training."""
    
    # Flashing border animation style
    pulse_style = {
        "animation": "pulse-border 2s infinite",
        "@keyframes pulse-border": {
            "0%": {"border_color": styles.ACCENT},
            "50%": {"border_color": f"{styles.ACCENT}33"},
            "100%": {"border_color": styles.ACCENT}
        }
    }
    
    return rx.vstack(
        rx.hstack(
            rx.icon("database", size=16, color=styles.ACCENT),
            rx.text("Datasets", size="2", weight="medium", style={"color": styles.TEXT_PRIMARY}),
            rx.cond(
                TrainingState.has_new_datasets,
                rx.badge("New", color_scheme="green", size="1", variant="solid"),
            ),
            rx.spacer(),
            rx.badge(
                f"{TrainingState.selected_count}",
                color_scheme="green",
                size="1",
                variant="outline",
            ),
            rx.icon(
                rx.cond(TrainingState.is_datasets_collapsed, "chevron-right", "chevron-down"),
                size=14,
                color=styles.TEXT_SECONDARY,
            ),
            width="100%",
            align="center",
            cursor="pointer",
            on_click=TrainingState.toggle_datasets_collapsed,
            style={
                "&:hover": {"opacity": "0.8"},
            },
        ),
        rx.cond(
            ~TrainingState.is_datasets_collapsed,
            rx.vstack(
                rx.divider(style={"border_color": styles.BORDER, "margin": "8px 0"}),
                rx.cond(
                    TrainingState.has_datasets,
                    rx.scroll_area(
                        rx.vstack(
                            rx.foreach(TrainingState.datasets, dataset_checkbox),
                            spacing="0",
                            width="100%",
                        ),
                        type="hover",
                        scrollbars="vertical",
                        style={"max_height": "200px"},
                    ),
                    rx.center(
                        rx.text("No datasets available", size="1", style={"color": styles.TEXT_SECONDARY}),
                        style={"padding": styles.SPACING_4},
                    ),
                ),
                # Mini Stats
                rx.box(
                    rx.hstack(
                        rx.text("Total Labeled:", size="1", style={"color": styles.TEXT_SECONDARY}),
                        rx.spacer(),
                        rx.text(f"{TrainingState.total_labeled_count}", size="1", weight="bold", style={"color": styles.SUCCESS}),
                        width="100%",
                        align="center",
                    ),
                    style={
                        "background": styles.BG_TERTIARY,
                        "padding": "8px", 
                        "border_radius": styles.RADIUS_SM,
                        "width": "100%",
                        "margin_top": "4px"
                    }
                ),
                # Class Distribution (inline badges)
                rx.cond(
                    TrainingState.has_class_distribution,
                    rx.box(
                        rx.hstack(
                            rx.text("Classes:", size="1", style={"color": styles.TEXT_SECONDARY}),
                            rx.hstack(
                                rx.foreach(
                                    TrainingState.class_distribution_sorted[:5],
                                    lambda item: rx.badge(
                                        f"{item[0]}: {item[1]}",
                                        color_scheme="green",
                                        size="1",
                                        variant="outline",
                                    ),
                                ),
                                rx.cond(
                                    TrainingState.class_distribution_sorted.length() > 5,
                                    rx.tooltip(
                                        rx.badge(
                                            f"+{TrainingState.class_distribution_sorted.length() - 5} more",
                                            color_scheme="gray",
                                            size="1",
                                            variant="outline",
                                        ),
                                        content="More classes available",
                                    ),
                                ),
                                spacing="1",
                                wrap="wrap",
                            ),
                            spacing="2",
                            align="center",
                            width="100%",
                        ),
                        style={
                            "background": styles.BG_TERTIARY,
                            "padding": "8px", 
                            "border_radius": styles.RADIUS_SM,
                            "width": "100%",
                            "margin_top": "4px"
                        }
                    ),
                ),
                width="100%",
                spacing="2",
            ),
        ),
        spacing="2",
        align="start",
        width="100%",
        style=rx.cond(
            TrainingState.has_new_datasets,
            {
                "padding": styles.SPACING_3,
                "background": styles.BG_SECONDARY,
                "border": f"1px solid {styles.ACCENT}", # Start with accent color for pulse
                "border_radius": styles.RADIUS_LG,
                "box_shadow": f"0 0 10px {styles.ACCENT}33",
                **pulse_style
            },
            {
                "padding": styles.SPACING_3,
                "background": styles.BG_SECONDARY,
                "border": f"1px solid {styles.BORDER}",
                "border_radius": styles.RADIUS_LG,
            }
        ),
    )


def classification_config_panel() -> rx.Component:
    """Classification-specific configuration controls."""
    return rx.vstack(
        # 2x2 grid for dropdowns
        rx.grid(
            # Row 1: Backbone + Size
            rx.vstack(
                rx.text("Backbone", size="1", style={"color": styles.TEXT_SECONDARY}),
                rx.select(
                    ["yolo", "convnext"],
                    value=TrainingState.classifier_backbone,
                    on_change=TrainingState.set_classifier_backbone,
                    size="1",
                ),
                spacing="1",
                align="start",
            ),
            rx.cond(
                TrainingState.classifier_backbone == "convnext",
                rx.vstack(
                    rx.text("ConvNeXt Size", size="1", style={"color": styles.TEXT_SECONDARY}),
                    rx.select(
                        ["tiny", "small", "base", "large"],
                        value=TrainingState.convnext_model_size,
                        on_change=TrainingState.set_convnext_model_size,
                        size="1",
                    ),
                    spacing="1",
                    align="start",
                ),
                rx.vstack(
                    rx.text("YOLO Size", size="1", style={"color": styles.TEXT_SECONDARY}),
                    rx.select(
                        ["n", "s", "m", "l"],
                        value=TrainingState.model_size,
                        on_change=TrainingState.set_model_size,
                        size="1",
                    ),
                    spacing="1",
                    align="start",
                ),
            ),
            # Row 2: Image Size + Batch Size
            rx.vstack(
                rx.text("Image Size", size="1", style={"color": styles.TEXT_SECONDARY}),
                rx.select(
                    ["224", "256", "384", "512"],
                    value=TrainingState.classify_image_size.to_string(),
                    on_change=TrainingState.set_classify_image_size,
                    size="1",
                ),
                spacing="1",
                align="start",
            ),
            rx.vstack(
                rx.text("Batch Size", size="1", style={"color": styles.TEXT_SECONDARY}),
                rx.select(
                    ["16", "32", "64", "128"],
                    value=TrainingState.classify_batch_size.to_string(),
                    on_change=TrainingState.set_classify_batch_size,
                    size="1",
                ),
                spacing="1",
                align="start",
            ),
            columns="2",
            spacing="3",
            width="100%",
        ),
        spacing="3",
        width="100%",
    )


def sam3_config_panel() -> rx.Component:
    """SAM3 fine-tuning configuration controls."""
    return rx.vstack(
        # Info badge
        rx.box(
            rx.hstack(
                rx.icon("sparkles", size=14, color=styles.EARTH_SIENNA),
                rx.text(
                    "Cloud-only · A100 GPU · Instance Segmentation",
                    size="1",
                    style={"color": styles.TEXT_SECONDARY},
                ),
                spacing="2",
                align="center",
            ),
            style={
                "background": f"{styles.WARNING}14",
                "padding": "8px 12px",
                "border_radius": styles.RADIUS_MD,
                "border": f"1px solid {styles.WARNING}33",
                "width": "100%",
            },
        ),
        # Max Epochs
        rx.vstack(
            rx.hstack(
                rx.text("Max Epochs", size="1", weight="medium", style={"color": styles.TEXT_PRIMARY}),
                rx.spacer(),
                rx.text(
                    TrainingState.sam3_max_epochs,
                    size="1",
                    weight="bold",
                    style={"color": styles.ACCENT, "font_family": styles.FONT_FAMILY_MONO},
                ),
                width="100%",
            ),
            rx.slider(
                value=[TrainingState.sam3_max_epochs],
                min=1,
                max=20,
                step=1,
                on_change=TrainingState.set_sam3_max_epochs,
                style={"width": "100%"},
                size="1",
            ),
            spacing="1",
        ),
        # Patience (early stopping)
        rx.vstack(
            rx.hstack(
                rx.text("Patience", size="1", weight="medium", style={"color": styles.TEXT_PRIMARY}),
                rx.tooltip(
                    rx.icon("info", size=12, color=styles.TEXT_SECONDARY, cursor="help"),
                    content="Early stopping patience. Training stops if mAP doesn't improve for this many epochs. Set to 0 to disable.",
                ),
                rx.spacer(),
                rx.text(
                    rx.cond(
                        TrainingState.sam3_early_stop_patience == 0,
                        "Off",
                        TrainingState.sam3_early_stop_patience,
                    ),
                    size="1",
                    weight="bold",
                    style={"color": styles.ACCENT, "font_family": styles.FONT_FAMILY_MONO},
                ),
                width="100%",
            ),
            rx.slider(
                value=[TrainingState.sam3_early_stop_patience],
                min=0,
                max=5,
                step=1,
                on_change=TrainingState.set_sam3_early_stop_patience,
                style={"width": "100%"},
                size="1",
            ),
            spacing="1",
        ),
        # 2-column grid
        rx.grid(
            # Few-shot images
            rx.vstack(
                rx.hstack(
                    rx.text("Images", size="1", style={"color": styles.TEXT_SECONDARY}),
                    rx.tooltip(
                        rx.icon("info", size=12, color=styles.TEXT_SECONDARY),
                        content="Number of images per class for few-shot training. 0 = use all available.",
                    ),
                    spacing="1",
                    align="center",
                ),
                rx.select(
                    ["0", "10", "50", "100"],
                    value=TrainingState.sam3_num_images.to_string(),
                    on_change=TrainingState.set_sam3_num_images,
                    size="1",
                ),
                spacing="1",
                align="start",
            ),
            # LR Scale
            rx.vstack(
                rx.hstack(
                    rx.text("LR Scale", size="1", style={"color": styles.TEXT_SECONDARY}),
                    rx.tooltip(
                        rx.icon("info", size=12, color=styles.TEXT_SECONDARY),
                        content="Learning rate scale factor relative to SAM3 defaults. Lower = gentler fine-tuning.",
                    ),
                    spacing="1",
                    align="center",
                ),
                rx.select(
                    ["0.01", "0.05", "0.1", "0.5", "1.0"],
                    value=TrainingState.sam3_lr_scale.to_string(),
                    on_change=TrainingState.set_sam3_lr_scale,
                    size="1",
                ),
                spacing="1",
                align="start",
            ),
            columns="2",
            spacing="3",
            width="100%",
        ),
        # Concept Prompt
        rx.vstack(
            rx.hstack(
                rx.text("Prompt", size="1", weight="medium", style={"color": styles.TEXT_PRIMARY}),
                rx.tooltip(
                    rx.icon("info", size=12, color=styles.TEXT_SECONDARY),
                    content="SAM3 concept prompt — the noun phrase SAM3 learns to detect. Use a domain-level term (e.g. 'animal') to avoid running SAM3 once per class at inference time.",
                ),
                spacing="1",
                align="center",
            ),
            rx.input(
                default_value=TrainingState.sam3_prompt,
                on_blur=TrainingState.set_sam3_prompt,
                placeholder="animal",
                size="1",
                style={"width": "100%"},
            ),
            spacing="1",
        ),
        spacing="3",
        width="100%",
    )


def configuration_card() -> rx.Component:
    """Card with training configuration controls."""
    return rx.vstack(
        rx.hstack(
            rx.icon("sliders-horizontal", size=16, color=styles.ACCENT),
            rx.text("Configuration", size="2", weight="medium", style={"color": styles.TEXT_PRIMARY}),
            width="100%",
            align="center",
        ),
        
        # Training Mode Selector (Detection / Classification / SAM3)
        rx.box(
            rx.segmented_control.root(
                rx.segmented_control.item(
                    rx.hstack(
                        rx.icon("target", size=12),
                        rx.text("Detection", size="1"),
                        spacing="1",
                        align="center",
                    ),
                    value="detection",
                ),
                rx.segmented_control.item(
                    rx.hstack(
                        rx.icon("tags", size=12),
                        rx.text("Classification", size="1"),
                        spacing="1",
                        align="center",
                    ),
                    value="classification",
                ),
                rx.segmented_control.item(
                    rx.hstack(
                        rx.icon("sparkles", size=12),
                        rx.text("SAM3", size="1"),
                        spacing="1",
                        align="center",
                    ),
                    value="sam3_finetune",
                ),
                value=TrainingState.training_mode,
                on_change=TrainingState.set_training_mode,
                size="1",
                width="100%",
            ),
            style={"margin": "8px 0"},
        ),
        
        rx.divider(style={"border_color": styles.BORDER, "margin": "4px 0"}),
        
        # Explicit validation notice (Visible when relevant)
        rx.cond(
            TrainingState.has_explicit_validation_datasets,
            rx.box(
                rx.hstack(
                    rx.icon("info", size=14, color=styles.ACCENT),
                    rx.text(
                        "Using explicit validation datasets",
                        size="1",
                        weight="medium",
                        style={"color": styles.TEXT_PRIMARY}
                    ),
                    spacing="2",
                    align="center",
                ),
                style={
                    "background": styles.ACCENT_MUTE,
                    "padding": "8px 12px",
                    "border_radius": styles.RADIUS_MD,
                    "border": f"1px solid {styles.ACCENT}44",
                    "margin_bottom": "8px",
                    "width": "100%",
                }
            ),
        ),
        
        # Scrollable content area
        rx.scroll_area(
            rx.vstack(
                # Mode-specific configuration
                rx.match(
                    TrainingState.training_mode,
                    # Detection config
                    ("detection", rx.vstack(
                        # Epochs (shared)
                        rx.vstack(
                            rx.hstack(
                                rx.text("Epochs", size="1", weight="medium", style={"color": styles.TEXT_PRIMARY}),
                                rx.spacer(),
                                rx.text(
                                    TrainingState.epochs,
                                    size="1",
                                    weight="bold",
                                    style={"color": styles.ACCENT, "font_family": styles.FONT_FAMILY_MONO},
                                ),
                                width="100%",
                            ),
                            rx.slider(
                                value=[TrainingState.epochs],
                                min=10,
                                max=500,
                                step=10,
                                on_change=TrainingState.set_epochs,
                                on_value_commit=TrainingState.save_training_prefs,
                                style={"width": "100%"},
                                size="1",
                            ),
                            spacing="1",
                        ),
                        # 2-column grid for dropdowns
                        rx.grid(
                            rx.vstack(
                                rx.text("Batch Size", size="1", style={"color": styles.TEXT_SECONDARY}),
                                rx.select(
                                    ["8", "16", "32"],
                                    value=TrainingState.batch_size.to_string(),
                                    on_change=TrainingState.set_batch_size,
                                    size="1",
                                ),
                                spacing="1",
                                align="start",
                                width="100%",
                            ),
                            rx.vstack(
                                rx.text("Model Size", size="1", style={"color": styles.TEXT_SECONDARY}),
                                rx.select(
                                    ["n", "s", "m", "l"],
                                    value=TrainingState.model_size,
                                    on_change=TrainingState.set_model_size,
                                    size="1",
                                ),
                                spacing="1",
                                align="start",
                                width="100%",
                            ),
                            columns="2",
                            spacing="3",
                            width="100%",
                        ),
                        spacing="3",
                        width="100%",
                    )),
                    # Classification config
                    ("classification", rx.vstack(
                        # Epochs (shared)
                        rx.vstack(
                            rx.hstack(
                                rx.text("Epochs", size="1", weight="medium", style={"color": styles.TEXT_PRIMARY}),
                                rx.spacer(),
                                rx.text(
                                    TrainingState.epochs,
                                    size="1",
                                    weight="bold",
                                    style={"color": styles.ACCENT, "font_family": styles.FONT_FAMILY_MONO},
                                ),
                                width="100%",
                            ),
                            rx.slider(
                                value=[TrainingState.epochs],
                                min=10,
                                max=500,
                                step=10,
                                on_change=TrainingState.set_epochs,
                                on_value_commit=TrainingState.save_training_prefs,
                                style={"width": "100%"},
                                size="1",
                            ),
                            spacing="1",
                        ),
                        classification_config_panel(),
                        spacing="3",
                        width="100%",
                    )),
                    # SAM3 Fine-Tune config
                    ("sam3_finetune", sam3_config_panel()),
                    # Default (fallback to detection)
                    rx.fragment(),
                ),
                
                # Compute Target Section (hidden for SAM3 - cloud-only)
                rx.cond(
                    TrainingState.training_mode != "sam3_finetune",
                    rx.vstack(
                        rx.hstack(
                            rx.icon("cpu", size=14, color=styles.TEXT_SECONDARY),
                            rx.text("Compute Target", size="1", weight="medium", style={"color": styles.TEXT_SECONDARY}),
                            width="100%",
                            align="center",
                        ),
                        rx.box(
                            compute_target_toggle(
                                value=TrainingState.compute_target,
                                on_change=TrainingState.set_compute_target,
                                machines=TrainingState.local_machines,
                                selected_machine=TrainingState.selected_machine,
                                on_machine_change=TrainingState.set_selected_machine,
                            ),
                            style={
                                "background": styles.BG_TERTIARY,
                                "border_radius": styles.RADIUS_MD,
                                "padding": "10px 12px",
                                "width": "100%",
                            },
                        ),
                        spacing="2",
                        width="100%",
                        style={"margin_top": "12px"},
                    ),
                ),
                
                # Continue from existing run checkbox (hidden for SAM3 - no continuation)
                rx.cond(
                    TrainingState.training_mode != "sam3_finetune",
                    rx.hstack(
                        rx.checkbox(
                            "Continue from existing run",
                            checked=TrainingState.continue_from_run,
                            on_change=TrainingState.toggle_continue_from_run,
                            size="1",
                        ),
                        rx.cond(
                            TrainingState.continue_from_run & (TrainingState.selected_parent_run_id != ""),
                            rx.badge(
                                TrainingState.selected_parent_run_alias,
                                color_scheme="purple",
                                size="1",
                                variant="outline",
                            ),
                        ),
                        spacing="2",
                        align="center",
                        width="100%",
                        style={"margin_top": "8px"},
                    ),
                ),
                

                # Advanced Settings (collapsible) - styled accordion
                rx.vstack(
                    # Accordion trigger
                    rx.box(
                        rx.hstack(
                            rx.icon(
                                rx.cond(TrainingState.show_advanced_settings, "chevron-down", "chevron-right"),
                                size=14,
                                color=styles.TEXT_SECONDARY,
                            ),
                            rx.text("Advanced Settings", size="1", weight="medium", style={"color": styles.TEXT_SECONDARY}),
                            rx.spacer(),
                            rx.cond(
                                ~TrainingState.show_advanced_settings,
                                rx.badge("6 options", color_scheme="gray", size="1", variant="surface"),
                            ),
                            width="100%",
                            align="center",
                        ),
                        on_click=TrainingState.toggle_advanced_settings,
                        style={
                            "padding": "8px 12px",
                            "background": styles.BG_TERTIARY,
                            "border_radius": styles.RADIUS_MD,
                            "cursor": "pointer",
                            "&:hover": {"opacity": "0.85"},
                            "width": "100%",
                        },
                    ),
                    # Accordion content
                    rx.cond(
                        TrainingState.show_advanced_settings,
                        rx.vstack(
                            # Patience
                            rx.vstack(
                                rx.hstack(
                                    rx.text("Patience", size="1", style={"color": styles.TEXT_SECONDARY}),
                                    rx.spacer(),
                                    rx.text(f"{TrainingState.patience}", size="1", weight="bold", style={"color": styles.ACCENT}),
                                    width="100%",
                                ),
                                rx.slider(
                                    value=[TrainingState.patience],
                                    min=5,
                                    max=100,
                                    step=5,
                                    on_change=TrainingState.set_patience,
                                    on_value_commit=TrainingState.save_training_prefs,
                                    style={"width": "100%"},
                                    size="1",
                                ),
                                spacing="1",
                            ),
                            # Optimizer
                            rx.vstack(
                                rx.text("Optimizer", size="1", style={"color": styles.TEXT_SECONDARY}),
                                rx.cond(
                                    (TrainingState.training_mode == "classification") & (TrainingState.classifier_backbone == "convnext"),
                                    rx.text("AdamW", size="2", weight="medium", style={"color": styles.TEXT_PRIMARY, "opacity": "0.6", "padding": "4px 0"}),
                                    rx.select(
                                        ["auto", "SGD", "Adam", "AdamW"],
                                        value=TrainingState.optimizer,
                                        on_change=TrainingState.set_optimizer,
                                        size="1",
                                    ),
                                ),
                                spacing="1",
                            ),
                            # Learning Rate (lr0) - conditional based on backbone
                            rx.cond(
                                (TrainingState.training_mode == "classification") & (TrainingState.classifier_backbone == "convnext"),
                                # ConvNeXt: LR + Weight Decay stacked vertically
                                rx.vstack(
                                    # Initial LR
                                    rx.vstack(
                                        rx.hstack(
                                            rx.text("ConvNeXt LR", size="1", style={"color": styles.TEXT_SECONDARY}),
                                            rx.tooltip(
                                                rx.icon("info", size=12, color=styles.TEXT_SECONDARY),
                                                content=(
                                                    "Recommended LR by model size:\n"
                                                    "• Tiny:   1e-4  – 5e-5\n"
                                                    "• Small: 1e-4  – 5e-5\n"
                                                    "• Base:  5e-5  – 1e-5\n"
                                                    "• Large: 2e-5  – 5e-6\n"
                                                    "Lower LR = gentler fine-tuning"
                                                ),
                                            ),
                                            spacing="1",
                                            align="center",
                                        ),
                                        rx.input(
                                            default_value=TrainingState.convnext_lr0.to_string(),
                                            on_blur=TrainingState.set_convnext_lr0_input,
                                            on_key_down=rx.call_script("if (event.key === 'Enter') event.target.blur()"),
                                            size="1",
                                            style={
                                                "width": "100%",
                                                "text_align": "center",
                                                "color": styles.ACCENT,
                                                "font_weight": "bold",
                                                "font_family": styles.FONT_FAMILY_MONO,
                                                "background": "transparent",
                                                "border": f"1px solid {styles.BORDER}",
                                            },
                                        ),
                                        rx.slider(
                                            value=[TrainingState.convnext_lr0_slider_value],
                                            min=0,
                                            max=100,
                                            step=1,
                                            on_change=TrainingState.set_convnext_lr0_slider,
                                            on_value_commit=TrainingState.save_training_prefs,
                                            style={"width": "100%"},
                                            size="1",
                                        ),
                                        spacing="1",
                                        width="100%",
                                    ),
                                    # Weight Decay
                                    rx.vstack(
                                        rx.hstack(
                                            rx.text("Weight Decay", size="1", style={"color": styles.TEXT_SECONDARY}),
                                            rx.tooltip(
                                                rx.icon("info", size=12, color=styles.TEXT_SECONDARY),
                                                content="AdamW weight decay for regularization. Higher values prevent overfitting but may reduce model capacity. Default: 0.05",
                                            ),
                                            spacing="1",
                                            align="center",
                                        ),
                                        rx.input(
                                            default_value=TrainingState.convnext_weight_decay.to_string(),
                                            on_blur=TrainingState.set_convnext_weight_decay_input,
                                            on_key_down=rx.call_script("if (event.key === 'Enter') event.target.blur()"),
                                            size="1",
                                            style={
                                                "width": "100%",
                                                "text_align": "center",
                                                "color": styles.ACCENT,
                                                "font_weight": "bold",
                                                "font_family": styles.FONT_FAMILY_MONO,
                                                "background": "transparent",
                                                "border": f"1px solid {styles.BORDER}",
                                            },
                                        ),
                                        rx.slider(
                                            value=[TrainingState.convnext_weight_decay_slider_value],
                                            min=0,
                                            max=100,
                                            step=1,
                                            on_change=TrainingState.set_convnext_weight_decay_slider,
                                            on_value_commit=TrainingState.save_training_prefs,
                                            style={"width": "100%"},
                                            size="1",
                                        ),
                                        spacing="1",
                                        width="100%",
                                    ),
                                    spacing="2",
                                    width="100%",
                                ),
                                # YOLO/Detection: standard LR range (0.001 to 0.1)
                                rx.vstack(
                                    rx.hstack(
                                        rx.text("Initial LR", size="1", style={"color": styles.TEXT_SECONDARY}),
                                        rx.spacer(),
                                        rx.text(f"{TrainingState.lr0}", size="1", weight="bold", style={"color": styles.ACCENT}),
                                        width="100%",
                                    ),
                                    rx.slider(
                                        value=[TrainingState.lr0_slider_value],
                                        min=0,
                                        max=100,
                                        step=1,
                                        on_change=TrainingState.set_lr0,
                                        on_value_commit=TrainingState.save_training_prefs,
                                        style={"width": "100%"},
                                        size="1",
                                    ),
                                    spacing="1",
                                ),
                            ),
                            # Final LR Factor (lrf) - only for YOLO, not used by ConvNeXt
                            rx.cond(
                                ~((TrainingState.training_mode == "classification") & (TrainingState.classifier_backbone == "convnext")),
                                rx.vstack(
                                    rx.hstack(
                                        rx.text("Final LR Factor", size="1", style={"color": styles.TEXT_SECONDARY}),
                                        rx.spacer(),
                                        rx.text(f"{TrainingState.lrf}", size="1", weight="bold", style={"color": styles.ACCENT}),
                                        width="100%",
                                    ),
                                    rx.slider(
                                        value=[TrainingState.lrf_slider_value],
                                        min=0,
                                        max=100,
                                        step=1,
                                        on_change=TrainingState.set_lrf,
                                        on_value_commit=TrainingState.save_training_prefs,
                                        style={"width": "100%"},
                                        size="1",
                                    ),
                                    spacing="1",
                                ),
                            ),
                            # Train/Val Ratio (conditional)
                            rx.vstack(
                                rx.cond(
                                    ~TrainingState.has_explicit_validation_datasets,
                                    # Configurable slider otherwise
                                    rx.vstack(
                                        rx.hstack(
                                            rx.text("Train/Val Ratio", size="1", style={"color": styles.TEXT_SECONDARY}),
                                            rx.spacer(),
                                            rx.text(
                                                f"{TrainingState.train_split_percentage}% / {100 - TrainingState.train_split_percentage}%",
                                                size="1",
                                                weight="bold",
                                                style={"color": styles.ACCENT}
                                            ),
                                            width="100%",
                                        ),
                                        rx.slider(
                                            value=[TrainingState.train_split_percentage],
                                            min=50,
                                            max=95,
                                            step=5,
                                            on_change=TrainingState.set_train_split,
                                            on_value_commit=TrainingState.save_training_prefs,
                                            style={"width": "100%"},
                                            size="1",
                                        ),
                                        spacing="1",
                                    ),
                                ),
                                spacing="1",
                            ),
                            spacing="2",
                            width="100%",
                            style={"margin_top": "8px", "padding_left": "16px"},
                        ),
                        rx.fragment(),
                    ),
                    spacing="2",
                    width="100%",
                    style={"margin_top": "8px"},
                ),
                spacing="3",
                width="100%",
            ),
            type="hover",
            scrollbars="vertical",
            style={"max_height": "400px"},  # Reduced to make room for button
        ),
        
        # Divider before action button
        rx.divider(style={"border_color": styles.BORDER, "margin": "16px 0 12px"}),
        
        # Start Training Button (integrated footer)
        rx.vstack(
            rx.button(
                rx.icon("play", size=16),
                rx.match(
                    TrainingState.training_mode,
                    ("sam3_finetune", "Start SAM3 Fine-Tuning"),
                    ("classification", "Start Classification Training"),
                    "Start Detection Training",
                ),
                size="3",  # Larger for primary CTA
                disabled=~TrainingState.can_start_training,
                loading=TrainingState.is_starting,
                on_click=TrainingState.dispatch_training,
                style={
                    "width": "100%",
                    "background": styles.ACCENT,
                    "&:hover": {"background": styles.ACCENT_HOVER},
                    "&:disabled": {"opacity": "0.5", "cursor": "not-allowed"},
                },
            ),
            rx.cond(
                TrainingState.start_error != "",
                rx.text(TrainingState.start_error, size="1", style={"color": styles.ERROR}),
            ),
            rx.cond(
                ~TrainingState.can_start_training,
                rx.text("Select labeled datasets", size="1", style={"color": styles.WARNING}),
                rx.text(
                    f"Ready: {TrainingState.total_labeled_count} images",
                    size="1",
                    style={"color": styles.SUCCESS, "font_family": styles.FONT_FAMILY_MONO},
                ),
            ),
            spacing="2",
            align="center",
            width="100%",
        ),

        spacing="2",
        align="start",
        width="100%",
        style={
            "padding": styles.SPACING_3,
            "background": styles.BG_SECONDARY,
            "border": f"1px solid {styles.BORDER}",
            "border_radius": styles.RADIUS_LG,
        },
    )


def start_training_card() -> rx.Component:
    """Card with start training button."""
    return rx.box(
        rx.vstack(
            rx.button(
                rx.icon("play", size=16),
                rx.match(
                    TrainingState.training_mode,
                    ("sam3_finetune", "Start SAM3 Fine-Tuning"),
                    ("classification", "Start Classification Training"),
                    "Start Detection Training",
                ),
                size="2",
                disabled=~TrainingState.can_start_training,
                loading=TrainingState.is_starting,
                on_click=TrainingState.dispatch_training,
                style={
                    "width": "100%",
                    "background": styles.ACCENT,
                    "&:hover": {"background": styles.ACCENT_HOVER},
                    "&:disabled": {"opacity": "0.5", "cursor": "not-allowed"},
                },
            ),
            rx.cond(
                TrainingState.start_error != "",
                rx.text(TrainingState.start_error, size="1", style={"color": styles.ERROR}),
            ),
            rx.cond(
                ~TrainingState.can_start_training,
                rx.text("Select labeled datasets", size="1", style={"color": styles.WARNING}),
                rx.text(
                    f"Ready: {TrainingState.total_labeled_count} images",
                    size="1",
                    style={"color": styles.SUCCESS, "opacity": "0.8"},
                ),
            ),
            spacing="2",
            align="center",
            width="100%",
        ),
        style={
            "padding": styles.SPACING_3,
            "background": styles.BG_SECONDARY,
            "border": f"1px solid {styles.BORDER}",
            "border_radius": styles.RADIUS_LG,
        },
    )


def run_status_badge(status: str) -> rx.Component:
    """Badge showing training run status."""
    return rx.match(
        status,
        ("pending", rx.badge("Pending", color_scheme="gray", size="1", variant="surface")),
        ("queued", rx.badge("Queued", color_scheme="green", size="1", variant="surface")),
        ("running", rx.badge("Running", color_scheme="yellow", size="1", variant="surface", high_contrast=True)),
        ("completed", rx.badge("Done", color_scheme="green", size="1", variant="surface")),
        ("failed", rx.badge("Failed", color_scheme="red", size="1", variant="surface")),
        ("cancelled", rx.badge("Cancelled", color_scheme="gray", size="1", variant="surface")),
        rx.badge(status, color_scheme="gray", size="1"),
    )


def training_run_row(run: TrainingRunModel) -> rx.Component:
    """Single row in training history table with all metadata columns."""
    # Format date/time: "2024-01-04 10:30:45"
    date_time = run.created_at  # Already formatted as "YYYY-MM-DD HH:MM:SS"
    
    # Display alias if set, otherwise show short run ID
    display_name = rx.cond(
        run.alias.is_not_none() & (run.alias != ""),
        run.alias,
        f"run_{run.id[:8]}",
    )
    
    # Check if this row is being edited
    is_editing_alias = (TrainingState.table_editing_run_id == run.id) & (TrainingState.table_editing_field == "alias")
    is_editing_notes = (TrainingState.table_editing_run_id == run.id) & (TrainingState.table_editing_field == "notes")
    
    # Notes display
    notes_display = rx.cond(
        run.notes.is_not_none() & (run.notes != ""),
        run.notes,
        "-"
    )
    
    # Active tags display - small inline badges
    def tag_indicator(tag_name: str, color: str) -> rx.Component:
        return rx.cond(
            run.tags.contains(tag_name),
            rx.badge(tag_name[:3], color_scheme=color, size="1", variant="solid"),
            rx.fragment()
        )
    
    return rx.table.row(
        # Radio button column (only when continue_from_run is enabled)
        rx.cond(
            TrainingState.continue_from_run,
            rx.table.cell(
                rx.cond(
                    # Only completed runs with matching classes are selectable
                    (run.status == "completed") & (run.classes.length() > 0),
                    # Selectable run - clickable icon
                    rx.icon_button(
                        rx.icon(
                            rx.cond(
                                TrainingState.selected_parent_run_id == run.id,
                                "circle-dot",  # Selected
                                "circle",      # Unselected
                            ),
                            size=14,
                        ),
                        size="1",
                        variant="ghost",
                        color_scheme=rx.cond(
                            TrainingState.selected_parent_run_id == run.id,
                            "purple",
                            "gray",
                        ),
                        on_click=[rx.stop_propagation, TrainingState.select_parent_run(run.id)],
                    ),
                    # Disabled indicator for incompatible runs
                    rx.tooltip(
                        rx.icon("circle", size=14, color=styles.TEXT_SECONDARY, style={"opacity": "0.3"}),
                        content=rx.cond(
                            run.status != "completed",
                            "Only completed runs can be continued",
                            "Run has no class data",
                        ),
                    ),
                ),
                style={"width": "32px"},
            ),
        ),
        # Date/Time column
        rx.table.cell(
            rx.text(date_time, size="1", style={"white_space": "nowrap", "color": styles.TEXT_SECONDARY}),
        ),
        # Name/Alias (editable)
        rx.table.cell(
            rx.cond(
                is_editing_alias,
                rx.hstack(
                    rx.input(
                        value=TrainingState.table_temp_value,
                        on_change=TrainingState.set_table_temp_value,
                        on_key_down=TrainingState.handle_table_edit_keydown,
                        placeholder="Model alias...",
                        size="1",
                        style={"width": "100px"},
                        auto_focus=True,
                    ),
                    rx.icon_button(
                        rx.icon("check", size=10),
                        size="1",
                        variant="outline",
                        color_scheme="green",
                        on_click=[rx.stop_propagation, TrainingState.save_table_edit],
                    ),
                    rx.icon_button(
                        rx.icon("x", size=10),
                        size="1",
                        variant="ghost",
                        on_click=[rx.stop_propagation, TrainingState.cancel_table_edit],
                    ),
                    spacing="1",
                    align="center",
                ),
                rx.hstack(
                    rx.text(display_name, size="1", truncate=True, style={"max_width": "100px"}),
                    rx.icon("pencil", size=10, color=styles.TEXT_SECONDARY, style={"opacity": "0.4"}),
                    spacing="1",
                    align="center",
                    on_click=[rx.stop_propagation, TrainingState.start_table_edit(run.id, "alias")],
                    cursor="pointer",
                    style={"&:hover": {"opacity": "0.8"}},
                ),
            ),
        ),
        # Status
        rx.table.cell(run_status_badge(run.status)),
        # Type (Detection / Classification / SAM3) - Unified badge format
        rx.table.cell(
            rx.match(
                run.model_type,
                # SAM3 Fine-Tune
                ("sam3_finetune", rx.badge(
                    rx.hstack(
                        rx.icon("sparkles", size=10),
                        rx.text("SAM3", size="1", weight="bold"),
                        spacing="1",
                        align="center",
                    ),
                    color_scheme="yellow",
                    size="1",
                    variant="outline",
                )),
                # Classification: show backbone in badge
                ("classification", rx.cond(
                    run.config.get("classifier_backbone", "yolo") == "convnext",
                    # ConvNeXt classifier
                    rx.badge(
                        rx.hstack(
                            rx.icon("tags", size=10),
                            rx.text("Cls", size="1"),
                            rx.text("CNX", size="1", weight="bold"),
                            spacing="1",
                            align="center",
                        ),
                        color_scheme="gray",
                        size="1",
                        variant="outline",
                    ),
                    # YOLO classifier
                    rx.badge(
                        rx.hstack(
                            rx.icon("tags", size=10),
                            rx.text("Cls", size="1"),
                            rx.text("YOL", size="1", weight="bold"),
                            spacing="1",
                            align="center",
                        ),
                        color_scheme="purple",
                        size="1",
                        variant="outline",
                    ),
                )),
                # Detection (default)
                rx.badge(
                    rx.hstack(
                        rx.icon("target", size=10),
                        rx.text("Det", size="1"),
                        spacing="1",
                        align="center",
                    ),
                    color_scheme="green",
                    size="1",
                    variant="outline",
                ),
            ),
        ),
        # Tags (inline indicators)
        rx.table.cell(
            rx.hstack(
                tag_indicator("production", "green"),
                tag_indicator("experiment", "purple"),
                tag_indicator("baseline", "blue"),
                tag_indicator("best", "yellow"),
                tag_indicator("deprecated", "gray"),
                spacing="1",
            ),
        ),
        # Epochs
        rx.table.cell(f"{run.config.get('epochs', '-')}", style={"font_size": "12px"}),
        # Metric 1: mAP@50 for detection, Top-1 for classification
        rx.table.cell(
            rx.text(
                rx.cond(
                    run.model_type == "classification",
                    # Classification: Top-1 Accuracy
                    rx.cond(
                        run.metrics.is_not_none() & (run.metrics.get('top1_accuracy', None) != None),
                        run.metrics.get('top1_accuracy', 0).to(float).to_string()[:5],
                        "-"
                    ),
                    # Detection: mAP@50
                    rx.cond(
                        run.metrics.is_not_none() & (run.metrics.get('mAP50', None) != None),
                        run.metrics.get('mAP50', 0).to(float).to_string()[:5],
                        "-"
                    ),
                ),
                weight="bold",
                size="1"
            )
        ),
        # Metric 2: mAP@50-95 for detection, Top-5 for classification
        rx.table.cell(
            rx.text(
                rx.cond(
                    run.model_type == "classification",
                    # Classification: Top-5 Accuracy
                    rx.cond(
                        run.metrics.is_not_none() & (run.metrics.get('top5_accuracy', None) != None),
                        run.metrics.get('top5_accuracy', 0).to(float).to_string()[:5],
                        "-"
                    ),
                    # Detection: mAP@50-95
                    rx.cond(
                        run.metrics.is_not_none() & (run.metrics.get('mAP50-95', None) != None),
                        run.metrics.get('mAP50-95', 0).to(float).to_string()[:5],
                        "-"
                    ),
                ),
                weight="bold",
                size="1"
            )
        ),
        # Notes (editable, wider)
        rx.table.cell(
            rx.cond(
                is_editing_notes,
                rx.hstack(
                    rx.input(
                        value=TrainingState.table_temp_value,
                        on_change=TrainingState.set_table_temp_value,
                        on_key_down=TrainingState.handle_table_edit_keydown,
                        placeholder="Notes...",
                        size="1",
                        style={"width": "180px"},
                        auto_focus=True,
                    ),
                    rx.icon_button(
                        rx.icon("check", size=10),
                        size="1",
                        variant="outline",
                        color_scheme="green",
                        on_click=[rx.stop_propagation, TrainingState.save_table_edit],
                    ),
                    rx.icon_button(
                        rx.icon("x", size=10),
                        size="1",
                        variant="ghost",
                        on_click=[rx.stop_propagation, TrainingState.cancel_table_edit],
                    ),
                    spacing="1",
                    align="center",
                ),
                rx.tooltip(
                    rx.hstack(
                        rx.text(
                            notes_display,
                            size="1",
                            truncate=True,
                            style={"max_width": "150px", "color": styles.TEXT_SECONDARY}
                        ),
                        rx.icon("pencil", size=10, color=styles.TEXT_SECONDARY, style={"opacity": "0.4"}),
                        spacing="1",
                        align="center",
                        on_click=[rx.stop_propagation, TrainingState.start_table_edit(run.id, "notes")],
                        cursor="pointer",
                        style={"&:hover": {"opacity": "0.8"}},
                    ),
                    content=rx.cond(
                        run.notes.is_not_none() & (run.notes != ""),
                        run.notes,
                        "Click to add notes"
                    ),
                ),
        ),
            style={"min_width": "160px"},
        ),
        # Actions (API promote + Delete)
        rx.table.cell(
            rx.hstack(
                # API Promote button - only visible for completed runs
                rx.cond(
                    run.status == "completed",
                    rx.tooltip(
                        rx.icon_button(
                            rx.icon("plug", size=12),
                            size="1",
                            variant="ghost",
                            color_scheme="green",
                            on_click=[rx.stop_propagation, TrainingState.open_api_promote_modal(run.id)],
                        ),
                        content="Promote to API",
                    ),
                ),
                rx.icon_button(
                    rx.icon("trash-2", size=12),
                    size="1",
                    variant="ghost",
                    color_scheme="red",
                    on_click=[rx.stop_propagation, TrainingState.open_delete_modal(run.id)],
                ),
                spacing="1",
            ),
        ),
        on_click=rx.redirect(f"/projects/{TrainingState.current_project_id}/train/{run.id}"),
        style={
            "cursor": "pointer",
            "&:hover": {"background": styles.BG_TERTIARY},
        },
    )


def sortable_header(label: str, column: str, min_width: str = "auto") -> rx.Component:
    """Sortable column header with icon indicator."""
    return rx.table.column_header_cell(
        rx.hstack(
            rx.text(label, size="1", style={"font_size": "11px"}),
            rx.cond(
                TrainingState.sort_column == column,
                rx.icon(
                    rx.cond(TrainingState.sort_ascending, "chevron-up", "chevron-down"),
                    size=10
                ),
                rx.fragment(),
            ),
            spacing="1",
            align="center",
            cursor="pointer",
            on_click=TrainingState.set_sort_column(column),
        ),
        style={"min_width": min_width},
    )


def training_history_card() -> rx.Component:
    """Card showing training run history with sort/filter, editable fields."""
    return rx.vstack(
        # Header with title and filter controls
        rx.hstack(
            rx.icon("history", size=16, color=styles.ACCENT),
            rx.text("History", size="2", weight="medium", style={"color": styles.TEXT_PRIMARY}),
            rx.spacer(),
            # Filter by status
            rx.select.root(
                rx.select.trigger(
                    placeholder="Status",
                    size="1",
                    style={"min_width": "80px"},
                ),
                rx.select.content(
                    rx.select.item("All", value="all"),
                    rx.select.item("Completed", value="completed"),
                    rx.select.item("Running", value="running"),
                    rx.select.item("Failed", value="failed"),
                ),
                value=TrainingState.filter_status,
                on_change=TrainingState.set_filter_status,
            ),
            # Filter by tag
            rx.select.root(
                rx.select.trigger(
                    placeholder="Tag",
                    size="1",
                    style={"min_width": "80px"},
                ),
                rx.select.content(
                    rx.select.item("All Tags", value="all"),
                    rx.select.item("Production", value="production"),
                    rx.select.item("Experiment", value="experiment"),
                    rx.select.item("Baseline", value="baseline"),
                    rx.select.item("Best", value="best"),
                ),
                value=TrainingState.filter_tag,
                on_change=TrainingState.set_filter_tag,
            ),
            # Filter by model type
            rx.select.root(
                rx.select.trigger(
                    placeholder="Type",
                    size="1",
                    style={"min_width": "80px"},
                ),
                rx.select.content(
                    rx.select.item("All Types", value="all"),
                    rx.select.item("🎯 Detection", value="detection"),
                    rx.select.item("🏷️ Classification", value="classification"),
                    rx.select.item("✨ SAM3", value="sam3_finetune"),
                ),
                value=TrainingState.filter_model_type,
                on_change=TrainingState.set_filter_model_type,
            ),
            # Filter by backbone
            rx.select.root(
                rx.select.trigger(
                    placeholder="Backbone",
                    size="1",
                    style={"min_width": "90px"},
                ),
                rx.select.content(
                    rx.select.item("All Backbones", value="all"),
                    rx.select.item("🧠 ConvNeXt", value="convnext"),
                    rx.select.item("⚡ YOLO", value="yolo"),
                ),
                value=TrainingState.filter_backbone,
                on_change=TrainingState.set_filter_backbone,
            ),
            # Clear filters button
            rx.cond(
                (TrainingState.filter_status != "all") | (TrainingState.filter_tag != "all") | (TrainingState.filter_model_type != "all") | (TrainingState.filter_backbone != "all"),
                rx.icon_button(
                    rx.icon("x", size=12),
                    size="1",
                    variant="ghost",
                    on_click=TrainingState.clear_filters,
                ),
                rx.fragment(),
            ),
            width="100%",
            align="center",
            spacing="2",
        ),
        rx.divider(style={"border_color": styles.BORDER, "margin": "8px 0"}),
        rx.cond(
            TrainingState.has_runs,
            # Table with sticky header
            rx.box(
                rx.table.root(
                    rx.table.header(
                        rx.table.row(
                            # Radio button header (only when continue_from_run is enabled)
                            rx.cond(
                                TrainingState.continue_from_run,
                                rx.table.column_header_cell("", style={"font_size": "11px", "width": "32px"}),
                            ),
                            sortable_header("Date/Time", "created_at", "120px"),
                            rx.table.column_header_cell("Name", style={"font_size": "11px"}),
                            rx.table.column_header_cell("Status", style={"font_size": "11px"}),
                            rx.table.column_header_cell("Type", style={"font_size": "11px"}),
                            rx.table.column_header_cell("Tags", style={"font_size": "11px"}),
                            rx.table.column_header_cell("Ep", style={"font_size": "11px"}),
                            rx.table.column_header_cell(
                                rx.tooltip(
                                    rx.text("Score", size="1"),
                                    content="mAP@50 for Detection, Top-1 Accuracy for Classification",
                                ),
                                style={"font_size": "11px"}
                            ),
                            rx.table.column_header_cell(
                                rx.tooltip(
                                    rx.text("Score 2", size="1"),
                                    content="mAP@50-95 for Detection, Top-5 Accuracy for Classification",
                                ),
                                style={"font_size": "11px"}
                            ),
                            rx.table.column_header_cell("Notes", style={"font_size": "11px", "min_width": "160px"}),
                            rx.table.column_header_cell("", style={"font_size": "11px", "width": "32px"}),
                            style={
                                "position": "sticky",
                                "top": "0",
                                "z_index": "1",
                                "background": styles.BG_SECONDARY,
                            },
                        ),
                    ),
                    rx.table.body(
                        rx.foreach(TrainingState.filtered_runs, training_run_row),
                    ),
                    variant="surface",
                    size="1",
                    style={"width": "100%"},
                ),
                style={
                    "flex": "1",
                    "overflow_y": "auto",
                    "overflow_x": "auto",
                    "min_height": "0",
                },
            ),
            rx.center(
                rx.text("No runs yet", size="1", style={"color": styles.TEXT_SECONDARY}),
                style={"padding": styles.SPACING_4, "flex": "1"},
            ),
        ),
        spacing="2",
        align="start",
        width="100%",
        height="100%",
        style={
            "padding": styles.SPACING_3,
            "background": styles.BG_SECONDARY,
            "border": f"1px solid {styles.BORDER}",
            "border_radius": styles.RADIUS_LG,
            "display": "flex",
            "flex_direction": "column",
        },
    )



def logs_terminal_card() -> rx.Component:
    """Card showing logs from the latest training run with autoscroll."""
    return rx.vstack(
        rx.hstack(
            rx.icon("terminal", size=16, color=styles.ACCENT),
            rx.text("Live Logs", size="2", weight="medium", style={"color": styles.TEXT_PRIMARY}),
            rx.spacer(),
            rx.cond(
                TrainingState.latest_run_is_active,
                rx.badge("Running", color_scheme="yellow", variant="surface", size="1"),
                rx.badge("Latest", color_scheme="gray", variant="outline", size="1"),
            ),
            align="center",
            width="100%",
        ),
        rx.divider(style={"border_color": styles.BORDER, "margin": "4px 0"}),
        rx.box(
            rx.scroll_area(
                rx.text(
                    TrainingState.latest_run_logs,
                    font_family="JetBrains Mono, monospace",
                    white_space="pre-wrap",
                    size="1",
                    weight="medium",
                    style={
                        "color": styles.CODE_TEXT,  # Soft blue-ish white for terminal
                        "line_height": "1.4",
                    },
                    id="live-logs-content",
                ),
                type="always",
                scrollbars="vertical",
                style={"height": "100%"},
                id="live-logs-scroll",
            ),
            style={
                "flex": "1",
                "background": styles.CODE_BG,  # Github Dark Dimmed
                "padding": "12px",
                "border_radius": styles.RADIUS_MD,
                "border": f"1px solid {styles.BORDER}",
                "overflow": "hidden",
                "width": "100%",
            }
        ),
        spacing="2",
        width="100%",
        height="100%",
        style={
            "padding": styles.SPACING_3,
            "background": styles.BG_SECONDARY,
            "border": f"1px solid {styles.BORDER}",
            "border_radius": styles.RADIUS_LG,
            "display": "flex",
            "flex_direction": "column"
        },
    )


def metric_box(label: str, value: rx.Var, color: str = styles.ACCENT) -> rx.Component:
    """Single metric display box."""
    return rx.vstack(
        rx.text(label, size="1", style={"color": styles.TEXT_SECONDARY}),
        rx.text(
            value,
            size="4",
            weight="bold",
            style={"color": color},
        ),
        spacing="1",
        align="center",
        style={
            "padding": styles.SPACING_3,
            "background": styles.BG_TERTIARY,
            "border_radius": styles.RADIUS_MD,
            "min_width": "80px",
        },
    )


def results_card() -> rx.Component:
    """Card showing training results and metrics for completed runs."""
    return rx.vstack(
        # Header
        rx.hstack(
            rx.icon("trophy", size=16, color=styles.SUCCESS),
            rx.text("Results", size="2", weight="medium", style={"color": styles.TEXT_PRIMARY}),
            rx.spacer(),
            rx.badge("Completed", color_scheme="green", variant="surface", size="1"),
            align="center",
            width="100%",
        ),
        rx.divider(style={"border_color": styles.BORDER, "margin": "4px 0"}),
        
        # Metrics Grid (mode-specific)
        rx.match(
            TrainingState.selected_run.model_type,
            # SAM3 metrics
            ("sam3_finetune", rx.grid(
                metric_box("Mask Loss", TrainingState.selected_run_metrics.get("mask_loss", 0).to(float).to_string()[:5], styles.SUCCESS),
                metric_box("GIoU Loss", TrainingState.selected_run_metrics.get("giou_loss", 0).to(float).to_string()[:5], styles.ACCENT),
                metric_box("Class Loss", TrainingState.selected_run_metrics.get("class_loss", 0).to(float).to_string()[:5], styles.WARNING),
                metric_box("Total Loss", TrainingState.selected_run_metrics.get("total_loss", 0).to(float).to_string()[:5], styles.PURPLE),
                columns="4",
                spacing="2",
                width="100%",
            )),
            # Classification metrics
            ("classification", rx.grid(
                metric_box("Top-1 Acc", TrainingState.selected_run_metrics.get("top1_accuracy", 0).to(float).to_string()[:5], styles.ACCENT),
                metric_box("Top-5 Acc", TrainingState.selected_run_metrics.get("top5_accuracy", 0).to(float).to_string()[:5], styles.SUCCESS),
                metric_box("Loss", TrainingState.selected_run_metrics.get("loss", 0).to(float).to_string()[:5], styles.WARNING),
                metric_box("Val Loss", TrainingState.selected_run_metrics.get("val_loss", 0).to(float).to_string()[:5], styles.PURPLE),
                columns="4",
                spacing="2",
                width="100%",
            )),
            # Detection metrics (default)
            rx.grid(
                metric_box("mAP@50", TrainingState.selected_run_metrics.get("mAP50", 0).to(float).to_string()[:5], styles.SUCCESS),
                metric_box("mAP@50-95", TrainingState.selected_run_metrics.get("mAP50-95", 0).to(float).to_string()[:5], styles.ACCENT),
                metric_box("Precision", TrainingState.selected_run_metrics.get("precision", 0).to(float).to_string()[:5], styles.WARNING),
                metric_box("Recall", TrainingState.selected_run_metrics.get("recall", 0).to(float).to_string()[:5], styles.PURPLE),
                columns="4",
                spacing="2",
                width="100%",
            ),
        ),
        
        # Download Buttons
        rx.hstack(
            rx.link(
                rx.button(
                    rx.icon("download", size=14),
                    "best.pt",
                    size="1",
                    variant="outline",
                    style={"cursor": "pointer"},
                ),
                href=TrainingState.best_pt_url,
                is_external=True,
            ),
            rx.link(
                rx.button(
                    rx.icon("download", size=14),
                    "last.pt",
                    size="1",
                    variant="outline",
                    style={"cursor": "pointer"},
                ),
                href=TrainingState.last_pt_url,
                is_external=True,
            ),
            spacing="2",
            width="100%",
            justify="center",
            style={"margin_top": styles.SPACING_2},
        ),
        
        spacing="2",
        width="100%",
        style={
            "padding": styles.SPACING_3,
            "background": styles.BG_SECONDARY,
            "border": f"1px solid {styles.BORDER}",
            "border_radius": styles.RADIUS_LG,
        },
    )


def artifact_thumbnail(url: rx.Var, alt: str) -> rx.Component:
    """Single artifact image thumbnail."""
    return rx.cond(
        url != "",
        rx.box(
            rx.image(
                src=url,
                alt=alt,
                style={
                    "width": "100%",
                    "height": "100%",
                    "object_fit": "cover",
                    "border_radius": styles.RADIUS_SM,
                },
            ),
            style={
                "width": "100%",
                "aspect_ratio": "1",
                "overflow": "hidden",
                "cursor": "pointer",
                "border": f"1px solid {styles.BORDER}",
                "border_radius": styles.RADIUS_SM,
                "&:hover": {"opacity": "0.8"},
            },
        ),
        rx.fragment(),
    )


def artifacts_gallery() -> rx.Component:
    """Gallery of training artifact images."""
    return rx.vstack(
        rx.hstack(
            rx.icon("images", size=16, color=styles.ACCENT),
            rx.text("Artifacts", size="2", weight="medium", style={"color": styles.TEXT_PRIMARY}),
            width="100%",
            align="center",
        ),
        rx.divider(style={"border_color": styles.BORDER, "margin": "4px 0"}),
        rx.grid(
            artifact_thumbnail(TrainingState.results_png_url, "Results"),
            artifact_thumbnail(TrainingState.confusion_matrix_url, "Confusion Matrix"),
            artifact_thumbnail(TrainingState.f1_curve_url, "F1 Curve"),
            artifact_thumbnail(TrainingState.pr_curve_url, "PR Curve"),
            columns="2",
            spacing="2",
            width="100%",
        ),
        spacing="2",
        width="100%",
        style={
            "padding": styles.SPACING_3,
            "background": styles.BG_SECONDARY,
            "border": f"1px solid {styles.BORDER}",
            "border_radius": styles.RADIUS_LG,
        },
    )


def error_card() -> rx.Component:
    """Card showing error details for failed runs."""
    return rx.vstack(
        rx.hstack(
            rx.icon("alert-circle", size=16, color=styles.ERROR),
            rx.text("Error", size="2", weight="medium", style={"color": styles.TEXT_PRIMARY}),
            rx.spacer(),
            rx.badge("Failed", color_scheme="red", variant="surface", size="1"),
            align="center",
            width="100%",
        ),
        rx.divider(style={"border_color": styles.BORDER, "margin": "4px 0"}),
        rx.box(
            rx.text(
                TrainingState.selected_run_error,
                size="1",
                style={"color": styles.ERROR, "white_space": "pre-wrap"},
            ),
            style={
                "padding": styles.SPACING_2,
                "background": styles.BG_TERTIARY,
                "border_radius": styles.RADIUS_SM,
                "width": "100%",
            },
        ),
        spacing="2",
        width="100%",
        style={
            "padding": styles.SPACING_3,
            "background": styles.BG_SECONDARY,
            "border": f"1px solid {styles.BORDER}",
            "border_radius": styles.RADIUS_LG,
        },
    )


def run_detail_panel() -> rx.Component:
    """Panel showing details for the selected run (conditional on run status)."""
    return rx.cond(
        TrainingState.has_selected_run,
        rx.flex(
            # Show results for completed runs
            rx.cond(
                TrainingState.selected_run_is_completed,
                rx.vstack(
                    results_card(),
                    artifacts_gallery(),
                    spacing="3",
                    width="100%",
                ),
                rx.fragment(),
            ),
            # Show error for failed runs
            rx.cond(
                TrainingState.selected_run_error != "",
                error_card(),
                rx.fragment(),
            ),
            # Show logs for active runs (or any run with logs)
            rx.box(
                logs_terminal_card(),
                style={"flex": "1", "overflow": "hidden", "min_height": "0"}
            ),
            direction="column",
            spacing="3",
            width="100%",
            height="100%",
        ),
        # No run selected - show placeholder
        rx.center(
            rx.vstack(
                rx.icon("mouse-pointer-click", size=32, color=styles.TEXT_SECONDARY),
                rx.text(
                    "Select a training run to view details",
                    size="2",
                    style={"color": styles.TEXT_SECONDARY},
                ),
                spacing="2",
                align="center",
            ),
            width="100%",
            height="100%",
            style={
                "background": styles.BG_SECONDARY,
                "border": f"1px solid {styles.BORDER}",
                "border_radius": styles.RADIUS_LG,
            },
        ),
    )


def loading_skeleton() -> rx.Component:
    """Loading skeleton for the page."""
    return rx.flex(
        rx.vstack(
            rx.skeleton(height="200px", width="100%"),
            rx.skeleton(height="300px", width="100%"),
            width="320px",
            spacing="4"
        ),
        rx.vstack(
            rx.skeleton(height="100%", width="100%"),
            flex="1",
            height="100%"
        ),
        spacing="4",
        padding=styles.SPACING_6,
        width="100%",
        height="calc(100vh - 60px)",
    )


def unified_run_config_card() -> rx.Component:
    """
    Bold, unified training configuration card.
    Combines datasets, model settings, compute target, and action in one panel.
    Uses colored section dividers for strong visual hierarchy.
    """
    return rx.vstack(
        # Card Header
        rx.hstack(
            rx.icon("rocket", size=20, color=styles.ACCENT),
            rx.text("Run Configuration", size="4", weight="bold", style={"color": styles.TEXT_PRIMARY}),
            width="100%",
            align="center",
        ),
        
        rx.divider(style={"border_color": styles.BORDER, "margin": "12px 0"}),
        
        # === SECTION 1: Datasets (collapsible, minimized by default) ===
        rx.box(
            rx.vstack(
                # Header (clickable)
                rx.hstack(
                    rx.icon(
                        rx.cond(TrainingState.is_datasets_collapsed, "chevron-right", "chevron-down"),
                        size=14,
                        color=styles.TEXT_SECONDARY,
                    ),
                    rx.icon("database", size=16, color=styles.SUCCESS),
                    rx.text("Datasets", size="2", weight="medium", style={"color": styles.TEXT_PRIMARY}),
                    rx.spacer(),
                    # Summary info when collapsed
                    rx.hstack(
                        rx.badge(
                            TrainingState.selected_count,
                            color_scheme="green",
                            size="1",
                            variant="outline",
                        ),
                        rx.cond(
                            TrainingState.has_class_distribution,
                            rx.badge(
                                f"{TrainingState.class_distribution_sorted.length()} classes",
                                color_scheme="green",
                                size="1",
                                variant="outline",
                            ),
                        ),
                        spacing="2",
                        align="center",
                    ),
                    width="100%",
                    align="center",
                    cursor="pointer",
                    on_click=TrainingState.toggle_datasets_collapsed,
                    style={"&:hover": {"opacity": "0.85"}},
                ),
                # Expanded content
                rx.cond(
                    ~TrainingState.is_datasets_collapsed,
                    rx.vstack(
                        rx.divider(style={"border_color": styles.BORDER, "margin": "8px 0"}),
                        # Dataset list
                        rx.cond(
                            TrainingState.has_datasets,
                            rx.scroll_area(
                                rx.vstack(
                                    rx.foreach(TrainingState.datasets, dataset_checkbox),
                                    spacing="0",
                                    width="100%",
                                ),
                                type="hover",
                                scrollbars="vertical",
                                style={"max_height": "140px"},
                            ),
                            rx.center(
                                rx.text("No datasets available", size="1", style={"color": styles.TEXT_SECONDARY}),
                                style={"padding": styles.SPACING_3},
                            ),
                        ),
                        # Stats row
                        rx.hstack(
                            rx.text("Selected:", size="1", style={"color": styles.TEXT_SECONDARY}),
                            rx.badge(
                                TrainingState.selected_count,
                                color_scheme="green",
                                size="1",
                                variant="outline",
                            ),
                            rx.spacer(),
                            rx.text("Images:", size="1", style={"color": styles.TEXT_SECONDARY}),
                            rx.text(
                                TrainingState.total_labeled_count,
                                size="1",
                                weight="bold",
                                style={"color": styles.SUCCESS, "font_family": styles.FONT_FAMILY_MONO},
                            ),
                            width="100%",
                            align="center",
                        ),
                        # Class Distribution (contained in scroll area with mini badges)
                        rx.cond(
                            TrainingState.has_class_distribution,
                            rx.vstack(
                                rx.text("Classes:", size="1", style={"color": styles.TEXT_SECONDARY}),
                                rx.scroll_area(
                                    rx.hstack(
                                        rx.foreach(
                                            TrainingState.class_distribution_sorted,
                                            lambda item: rx.badge(
                                                f"{item[0]}: {item[1]}",
                                                color_scheme="green",
                                                size="1",
                                                variant="outline",
                                                style=styles.BADGE_MINI,
                                            ),
                                        ),
                                        spacing="1",
                                        wrap="wrap",
                                        width="100%",
                                    ),
                                    type="hover",
                                    scrollbars="vertical",
                                    style={"max_height": "60px", "width": "100%"},
                                ),
                                spacing="1",
                                width="100%",
                            ),
                        ),
                        spacing="3",
                        width="100%",
                    ),
                ),
                spacing="0",
                width="100%",
            ),
            style={
                "padding": "12px 14px",
                "background": styles.BG_TERTIARY,
                "border_left": f"3px solid {styles.SUCCESS}",  # Green accent
                "border_radius": styles.RADIUS_MD,
                "width": "100%",
            },
        ),
        
        # === SECTION 2: Model Settings (collapsible) ===
        rx.box(
            rx.vstack(
                # Header (clickable)
                rx.hstack(
                    rx.icon(
                        rx.cond(TrainingState.is_model_collapsed, "chevron-right", "chevron-down"),
                        size=14,
                        color=styles.TEXT_SECONDARY,
                    ),
                    rx.icon("brain", size=16, color=styles.ACCENT),
                    rx.text("Model", size="2", weight="medium", style={"color": styles.TEXT_PRIMARY}),
                    rx.spacer(),
                    # Summary badges when collapsed
                    rx.cond(
                        TrainingState.is_model_collapsed,
                        rx.hstack(
                            rx.match(
                                TrainingState.training_mode,
                                ("sam3_finetune", rx.badge("SAM3", color_scheme="yellow", size="1", variant="outline")),
                                ("classification", rx.badge("Classification", color_scheme="green", size="1", variant="outline")),
                                rx.badge("Detection", color_scheme="green", size="1", variant="outline"),
                            ),
                            rx.badge(
                                f"{TrainingState.epochs} epochs",
                                color_scheme="gray",
                                size="1",
                                variant="outline",
                            ),
                            spacing="2",
                            align="center",
                        ),
                    ),
                    width="100%",
                    align="center",
                    cursor="pointer",
                    on_click=TrainingState.toggle_model_collapsed,
                    style={"&:hover": {"opacity": "0.85"}},
                ),
                # Collapsed view: Mode toggle + Epochs slider visible
                rx.cond(
                    TrainingState.is_model_collapsed,
                    rx.vstack(
                        rx.divider(style={"border_color": styles.BORDER, "margin": "8px 0"}),
                        # Mode toggle
                        rx.segmented_control.root(
                            rx.segmented_control.item(
                                rx.hstack(
                                    rx.icon("target", size=12),
                                    rx.text("Detection", size="1"),
                                    spacing="1",
                                    align="center",
                                ),
                                value="detection",
                            ),
                            rx.segmented_control.item(
                                rx.hstack(
                                    rx.icon("tags", size=12),
                                    rx.text("Classification", size="1"),
                                    spacing="1",
                                    align="center",
                                ),
                                value="classification",
                            ),
                            rx.segmented_control.item(
                                rx.hstack(
                                    rx.icon("sparkles", size=12),
                                    rx.text("SAM3", size="1"),
                                    spacing="1",
                                    align="center",
                                ),
                                value="sam3_finetune",
                            ),
                            value=TrainingState.training_mode,
                            on_change=TrainingState.set_training_mode,
                            size="1",
                            width="100%",
                        ),
                        # Epochs slider (hidden for SAM3 which has its own)
                        rx.cond(
                            TrainingState.training_mode != "sam3_finetune",
                            rx.vstack(
                                rx.hstack(
                                    rx.text("Epochs", size="1", weight="medium", style={"color": styles.TEXT_PRIMARY}),
                                    rx.spacer(),
                                    rx.text(
                                        TrainingState.epochs,
                                        size="2",
                                        weight="bold",
                                        style={"color": styles.ACCENT, "font_family": styles.FONT_FAMILY_MONO},
                                    ),
                                    width="100%",
                                ),
                                rx.slider(
                                    value=[TrainingState.epochs],
                                    min=10,
                                    max=500,
                                    step=10,
                                    on_change=TrainingState.set_epochs,
                                    on_value_commit=TrainingState.save_training_prefs,
                                    style={"width": "100%"},
                                    size="1",
                                ),
                                spacing="1",
                                width="100%",
                            ),
                        ),
                        # SAM3 config (shown only for SAM3 mode)
                        rx.cond(
                            TrainingState.training_mode == "sam3_finetune",
                            sam3_config_panel(),
                        ),
                        spacing="3",
                        width="100%",
                    ),
                ),
                # Expanded view: Full model settings + Advanced
                rx.cond(
                    ~TrainingState.is_model_collapsed,
                    rx.vstack(
                        rx.divider(style={"border_color": styles.BORDER, "margin": "8px 0"}),
                        # Mode toggle
                        rx.segmented_control.root(
                            rx.segmented_control.item(
                                rx.hstack(
                                    rx.icon("target", size=12),
                                    rx.text("Detection", size="1"),
                                    spacing="1",
                                    align="center",
                                ),
                                value="detection",
                            ),
                            rx.segmented_control.item(
                                rx.hstack(
                                    rx.icon("tags", size=12),
                                    rx.text("Classification", size="1"),
                                    spacing="1",
                                    align="center",
                                ),
                                value="classification",
                            ),
                            rx.segmented_control.item(
                                rx.hstack(
                                    rx.icon("sparkles", size=12),
                                    rx.text("SAM3", size="1"),
                                    spacing="1",
                                    align="center",
                                ),
                                value="sam3_finetune",
                            ),
                            value=TrainingState.training_mode,
                            on_change=TrainingState.set_training_mode,
                            size="1",
                            width="100%",
                        ),
                        # Epochs slider (hidden for SAM3 which has its own)
                        rx.cond(
                            TrainingState.training_mode != "sam3_finetune",
                            rx.vstack(
                                rx.hstack(
                                    rx.text("Epochs", size="1", weight="medium", style={"color": styles.TEXT_PRIMARY}),
                                    rx.spacer(),
                                    rx.text(
                                        TrainingState.epochs,
                                        size="2",
                                        weight="bold",
                                        style={"color": styles.ACCENT, "font_family": styles.FONT_FAMILY_MONO},
                                    ),
                                    width="100%",
                                ),
                                rx.slider(
                                    value=[TrainingState.epochs],
                                    min=10,
                                    max=500,
                                    step=10,
                                    on_change=TrainingState.set_epochs,
                                    on_value_commit=TrainingState.save_training_prefs,
                                    style={"width": "100%"},
                                    size="1",
                                ),
                                spacing="1",
                                width="100%",
                            ),
                        ),
                        # Mode-specific dropdowns in 2-column grid
                        rx.match(
                            TrainingState.training_mode,
                            # Detection: Batch Size + Model Size
                            ("detection", rx.grid(
                                rx.vstack(
                                    rx.text("Batch Size", size="1", style={"color": styles.TEXT_SECONDARY}),
                                    rx.select(
                                        ["8", "16", "32"],
                                        value=TrainingState.batch_size.to_string(),
                                        on_change=TrainingState.set_batch_size,
                                        size="1",
                                    ),
                                    spacing="1",
                                    width="100%",
                                ),
                                rx.vstack(
                                    rx.text("Model Size", size="1", style={"color": styles.TEXT_SECONDARY}),
                                    rx.select(
                                        ["n", "s", "m", "l"],
                                        value=TrainingState.model_size,
                                        on_change=TrainingState.set_model_size,
                                        size="1",
                                    ),
                                    spacing="1",
                                    width="100%",
                                ),
                                columns="2",
                                spacing="3",
                                width="100%",
                            )),
                            # Classification: 2x2 grid
                            ("classification", rx.grid(
                                rx.vstack(
                                    rx.text("Backbone", size="1", style={"color": styles.TEXT_SECONDARY}),
                                    rx.select(
                                        ["yolo", "convnext"],
                                        value=TrainingState.classifier_backbone,
                                        on_change=TrainingState.set_classifier_backbone,
                                        size="1",
                                    ),
                                    spacing="1",
                                    width="100%",
                                ),
                                rx.cond(
                                    TrainingState.classifier_backbone == "convnext",
                                    rx.vstack(
                                        rx.text("Size", size="1", style={"color": styles.TEXT_SECONDARY}),
                                        rx.select(
                                            ["tiny", "small", "base", "large"],
                                            value=TrainingState.convnext_model_size,
                                            on_change=TrainingState.set_convnext_model_size,
                                            size="1",
                                        ),
                                        spacing="1",
                                        width="100%",
                                    ),
                                    rx.vstack(
                                        rx.text("Size", size="1", style={"color": styles.TEXT_SECONDARY}),
                                        rx.select(
                                            ["n", "s", "m", "l"],
                                            value=TrainingState.model_size,
                                            on_change=TrainingState.set_model_size,
                                            size="1",
                                        ),
                                        spacing="1",
                                        width="100%",
                                    ),
                                ),
                                rx.vstack(
                                    rx.text("Image", size="1", style={"color": styles.TEXT_SECONDARY}),
                                    rx.select(
                                        ["224", "256", "384", "512"],
                                        value=TrainingState.classify_image_size.to_string(),
                                        on_change=TrainingState.set_classify_image_size,
                                        size="1",
                                    ),
                                    spacing="1",
                                    width="100%",
                                ),
                                rx.vstack(
                                    rx.text("Batch", size="1", style={"color": styles.TEXT_SECONDARY}),
                                    rx.select(
                                        ["16", "32", "64", "128"],
                                        value=TrainingState.classify_batch_size.to_string(),
                                        on_change=TrainingState.set_classify_batch_size,
                                        size="1",
                                    ),
                                    spacing="1",
                                    width="100%",
                                ),
                                columns="2",
                                spacing="3",
                                width="100%",
                            )),
                            # SAM3: dedicated config panel
                            ("sam3_finetune", sam3_config_panel()),
                            # Default: empty
                            rx.fragment(),
                        ),
                        # === ADVANCED SETTINGS (visual separator, hidden for SAM3) ===
                        rx.cond(
                            TrainingState.training_mode != "sam3_finetune",
                            rx.vstack(
                                rx.hstack(
                                    rx.divider(style={"flex": "1", "border_color": styles.BORDER}),
                                    rx.text("Advanced", size="1", weight="medium", style={"color": styles.TEXT_SECONDARY, "padding": "0 8px"}),
                                    rx.divider(style={"flex": "1", "border_color": styles.BORDER}),
                                    width="100%",
                                    align="center",
                                    style={"margin": "12px 0 8px"},
                                ),
                                # Row 1: Patience + Optimizer
                                rx.grid(
                                    # Patience
                                    rx.vstack(
                                        rx.hstack(
                                            rx.text("Patience", size="1", style={"color": styles.TEXT_SECONDARY}),
                                            rx.spacer(),
                                            rx.text(TrainingState.patience, size="1", weight="bold", style={"color": styles.ACCENT}),
                                            width="100%",
                                        ),
                                        rx.slider(
                                            value=[TrainingState.patience],
                                            min=5,
                                            max=100,
                                            step=5,
                                            on_change=TrainingState.set_patience,
                                            on_value_commit=TrainingState.save_training_prefs,
                                            size="1",
                                        ),
                                        spacing="1",
                                        width="100%",
                                    ),
                                    # Optimizer
                                    rx.vstack(
                                        rx.text("Optimizer", size="1", style={"color": styles.TEXT_SECONDARY}),
                                        rx.cond(
                                            (TrainingState.training_mode == "classification") & (TrainingState.classifier_backbone == "convnext"),
                                            rx.text("AdamW", size="2", weight="medium", style={"color": styles.TEXT_PRIMARY, "opacity": "0.6", "padding": "4px 0"}),
                                            rx.select(
                                                ["auto", "SGD", "Adam", "AdamW"],
                                                value=TrainingState.optimizer,
                                                on_change=TrainingState.set_optimizer,
                                                size="1",
                                            ),
                                        ),
                                        spacing="1",
                                        width="100%",
                                    ),
                                    columns="2",
                                    spacing="3",
                                    width="100%",
                                ),
                                # Row 2: Initial LR + Final LR Factor
                                rx.grid(
                                    # Initial Learning Rate (backbone-aware)
                                    rx.cond(
                                        (TrainingState.training_mode == "classification") & (TrainingState.classifier_backbone == "convnext"),
                                        # ConvNeXt LR + Weight Decay stacked vertically
                                        rx.vstack(
                                            # Initial LR
                                            rx.vstack(
                                                rx.hstack(
                                                    rx.text("ConvNeXt LR", size="1", style={"color": styles.TEXT_SECONDARY}),
                                                    rx.tooltip(
                                                        rx.icon("info", size=12, color=styles.TEXT_SECONDARY),
                                                        content=(
                                                            "Recommended LR by model size:\n"
                                                            "• Tiny:   1e-4  – 5e-5\n"
                                                            "• Small: 1e-4  – 5e-5\n"
                                                            "• Base:  5e-5  – 1e-5\n"
                                                            "• Large: 2e-5  – 5e-6\n"
                                                            "Lower LR = gentler fine-tuning"
                                                        ),
                                                    ),
                                                    spacing="1",
                                                    align="center",
                                                ),
                                                rx.input(
                                                    default_value=TrainingState.convnext_lr0.to_string(),
                                                    on_blur=TrainingState.set_convnext_lr0_input,
                                                    on_key_down=rx.call_script("if (event.key === 'Enter') event.target.blur()"),
                                                    size="1",
                                                    style={
                                                        "width": "100%",
                                                        "text_align": "center",
                                                        "color": styles.ACCENT,
                                                        "font_weight": "bold",
                                                        "font_family": styles.FONT_FAMILY_MONO,
                                                        "background": "transparent",
                                                        "border": f"1px solid {styles.BORDER}",
                                                    },
                                                ),
                                                rx.slider(
                                                    value=[TrainingState.convnext_lr0_slider_value],
                                                    min=0,
                                                    max=100,
                                                    step=1,
                                                    on_change=TrainingState.set_convnext_lr0_slider,
                                                    on_value_commit=TrainingState.save_training_prefs,
                                                    size="1",
                                                ),
                                                spacing="1",
                                                width="100%",
                                            ),
                                            # Weight Decay
                                            rx.vstack(
                                                rx.hstack(
                                                    rx.text("Weight Decay", size="1", style={"color": styles.TEXT_SECONDARY}),
                                                    rx.tooltip(
                                                        rx.icon("info", size=12, color=styles.TEXT_SECONDARY),
                                                        content="AdamW weight decay for regularization. Higher values prevent overfitting but may reduce model capacity. Default: 0.05",
                                                    ),
                                                    spacing="1",
                                                    align="center",
                                                ),
                                                rx.input(
                                                    default_value=TrainingState.convnext_weight_decay.to_string(),
                                                    on_blur=TrainingState.set_convnext_weight_decay_input,
                                                    on_key_down=rx.call_script("if (event.key === 'Enter') event.target.blur()"),
                                                    size="1",
                                                    style={
                                                        "width": "100%",
                                                        "text_align": "center",
                                                        "color": styles.ACCENT,
                                                        "font_weight": "bold",
                                                        "font_family": styles.FONT_FAMILY_MONO,
                                                        "background": "transparent",
                                                        "border": f"1px solid {styles.BORDER}",
                                                    },
                                                ),
                                                rx.slider(
                                                    value=[TrainingState.convnext_weight_decay_slider_value],
                                                    min=0,
                                                    max=100,
                                                    step=1,
                                                    on_change=TrainingState.set_convnext_weight_decay_slider,
                                                    on_value_commit=TrainingState.save_training_prefs,
                                                    size="1",
                                                ),
                                                spacing="1",
                                                width="100%",
                                            ),
                                            spacing="2",
                                            width="100%",
                                        ),
                                        # YOLO LR (range: 0.001 to 0.1)
                                        rx.vstack(
                                            rx.hstack(
                                                rx.text("Initial LR", size="1", style={"color": styles.TEXT_SECONDARY}),
                                                rx.spacer(),
                                                rx.text(TrainingState.lr0, size="1", weight="bold", style={"color": styles.ACCENT, "font_family": styles.FONT_FAMILY_MONO}),
                                                width="100%",
                                            ),
                                            rx.slider(
                                                value=[TrainingState.lr0_slider_value],
                                                min=0,
                                                max=100,
                                                step=1,
                                                on_change=TrainingState.set_lr0,
                                                on_value_commit=TrainingState.save_training_prefs,
                                                size="1",
                                            ),
                                            spacing="1",
                                            width="100%",
                                        ),
                                    ),
                                    # Final LR Factor - only for YOLO, not used by ConvNeXt
                                    rx.cond(
                                        ~((TrainingState.training_mode == "classification") & (TrainingState.classifier_backbone == "convnext")),
                                        rx.vstack(
                                            rx.hstack(
                                                rx.text("Final LR", size="1", style={"color": styles.TEXT_SECONDARY}),
                                                rx.spacer(),
                                                rx.text(TrainingState.lrf, size="1", weight="bold", style={"color": styles.ACCENT, "font_family": styles.FONT_FAMILY_MONO}),
                                                width="100%",
                                            ),
                                            rx.slider(
                                                value=[TrainingState.lrf * 100],  # Scale for slider
                                                min=1,
                                                max=100,
                                                step=1,
                                                on_change=lambda v: TrainingState.set_lrf(v[0] / 100),
                                                on_value_commit=TrainingState.save_training_prefs,
                                                size="1",
                                            ),
                                            spacing="1",
                                            width="100%",
                                        ),
                                    ),
                                    columns="2",
                                    spacing="3",
                                    width="100%",
                                ),
                                # Row 3: Train/Val Ratio (only when no explicit validation datasets)
                                rx.cond(
                                    ~TrainingState.has_explicit_validation_datasets,
                                    rx.vstack(
                                        rx.hstack(
                                            rx.text("Train/Val Ratio", size="1", style={"color": styles.TEXT_SECONDARY}),
                                            rx.spacer(),
                                            rx.text(
                                                f"{TrainingState.train_split_percentage}% / {100 - TrainingState.train_split_percentage}%",
                                                size="1",
                                                weight="bold",
                                                style={"color": styles.ACCENT}
                                            ),
                                            width="100%",
                                        ),
                                        rx.slider(
                                            value=[TrainingState.train_split_percentage],
                                            min=50,
                                            max=95,
                                            step=5,
                                            on_change=TrainingState.set_train_split,
                                            on_value_commit=TrainingState.save_training_prefs,
                                            style={"width": "100%"},
                                            size="1",
                                        ),
                                        spacing="1",
                                        width="100%",
                                    ),
                                ),
                                spacing="4",
                                width="100%",
                            ),
                        ),
                        spacing="4",
                        width="100%",
                    ),
                ),
                spacing="0",
                width="100%",
            ),
            style={
                "padding": "12px 14px",
                "background": styles.BG_TERTIARY,
                "border_left": f"3px solid {styles.ACCENT}",
                "border_radius": styles.RADIUS_MD,
                "width": "100%",
            },
        ),
        
        # === SECTION 3: Compute Target (hidden for SAM3) ===
        rx.cond(
            TrainingState.training_mode != "sam3_finetune",
            config_section(
                title="Compute",
                icon="cpu",
                accent_color=styles.PURPLE,
                content=rx.vstack(
                    compute_target_toggle(
                        value=TrainingState.compute_target,
                        on_change=TrainingState.set_compute_target,
                        machines=TrainingState.local_machines,
                        selected_machine=TrainingState.selected_machine,
                        on_machine_change=TrainingState.set_selected_machine,
                    ),
                    # Continue from existing run
                    rx.hstack(
                        rx.checkbox(
                            "Continue from existing run",
                            checked=TrainingState.continue_from_run,
                            on_change=TrainingState.toggle_continue_from_run,
                            size="1",
                        ),
                        rx.cond(
                            TrainingState.continue_from_run & (TrainingState.selected_parent_run_id != ""),
                            rx.badge(
                                TrainingState.selected_parent_run_alias,
                                color_scheme="purple",
                                size="1",
                                variant="outline",
                            ),
                        ),
                        spacing="2",
                        align="center",
                        width="100%",
                    ),
                    spacing="3",
                    width="100%",
                ),
            ),
        ),
        
        # === START BUTTON ===
        rx.divider(style={"border_color": styles.BORDER, "margin": "16px 0 12px"}),
        
        rx.vstack(
            rx.button(
                rx.icon("play", size=18),
                rx.match(
                    TrainingState.training_mode,
                    ("sam3_finetune", "Start SAM3 Fine-Tuning"),
                    ("classification", "Start Classification Training"),
                    "Start Detection Training",
                ),
                size="3",
                disabled=~TrainingState.can_start_training,
                loading=TrainingState.is_starting,
                on_click=TrainingState.dispatch_training,
                style={
                    "width": "100%",
                    "background": styles.ACCENT,
                    "&:hover": {"background": styles.ACCENT_HOVER},
                    "&:disabled": {"opacity": "0.5", "cursor": "not-allowed"},
                },
            ),
            rx.cond(
                TrainingState.start_error != "",
                rx.text(TrainingState.start_error, size="1", style={"color": styles.ERROR}),
            ),
            rx.cond(
                ~TrainingState.can_start_training,
                rx.text("Select labeled datasets", size="1", style={"color": styles.WARNING}),
                rx.text(
                    f"Ready: {TrainingState.total_labeled_count} images",
                    size="1",
                    style={"color": styles.SUCCESS, "font_family": styles.FONT_FAMILY_MONO},
                ),
            ),
            spacing="2",
            align="center",
            width="100%",
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

def dashboard_content() -> rx.Component:
    """Main dashboard content."""
    return rx.cond(
        TrainingState.is_loading,
        loading_skeleton(),
        rx.box(
            breadcrumb_nav(),
            page_header(),
            
            # Application Shell Layout
            rx.flex(
                # Left Sidebar: Controls (scrollable)
                rx.scroll_area(
                    rx.vstack(
                        unified_run_config_card(),
                        spacing="3",
                        width="100%",
                        style={"padding_right": "12px"},  # Prevent content touching edge
                    ),
                    type="hover",
                    scrollbars="vertical",
                    style={
                        "width": "400px",
                        "min_width": "400px",
                        "height": "100%",
                        "overflow_x": "visible",  # Allow dropdowns to extend
                    },
                ),
                
                # Right Content: Monitoring
                rx.flex(
                    # Top: Live logs (only visible during active training)
                    rx.cond(
                        TrainingState.latest_run_is_active,
                        rx.box(
                            logs_terminal_card(),
                            style={"flex": "2", "overflow": "hidden", "min_height": "0"}
                        ),
                        rx.fragment(),
                    ),
                    # Bottom: History (click to view run details)
                    rx.box(
                        training_history_card(),
                        style={"flex": "1", "overflow": "hidden", "min_height": "0"} 
                    ),
                    direction="column",
                    spacing="3",
                    width="100%",
                    height="100%",
                ),
                
                spacing="3",
                width="100%",
                height="calc(100vh - 120px)", # Adjust for header/breadcrumb
                style={
                    "padding": f"0 {styles.SPACING_6} {styles.SPACING_6}",
                }
            ),
            
            width="100%",
            height="100vh", # Ensure full viewport height
            style={"overflow": "hidden"} # Prevent page scrolling, use internal scroll areas
        ),
    )


def delete_run_modal() -> rx.Component:
    """Modal for confirming training run deletion."""
    return rx.dialog.root(
        rx.dialog.content(
            rx.dialog.title("Delete Training Run", style={"color": styles.ERROR}),
            rx.vstack(
                rx.text(
                    "This will permanently delete this training run and all associated model weights and artifacts.",
                    style={"color": styles.TEXT_SECONDARY}
                ),
                rx.text("Type 'delete' to confirm:", size="2", style={"color": styles.TEXT_SECONDARY}),
                rx.input(
                    placeholder="delete",
                    value=TrainingState.delete_confirmation,
                    on_change=TrainingState.set_delete_confirmation,
                    on_key_down=TrainingState.handle_delete_run_keydown,
                    style={"width": "100%"},
                ),
                rx.hstack(
                    rx.dialog.close(
                        rx.button("Cancel", variant="outline", color_scheme="gray", on_click=TrainingState.close_delete_modal),
                    ),
                    rx.button(
                        "Delete Run",
                        color_scheme="red",
                        disabled=~TrainingState.can_delete_run,
                        loading=TrainingState.is_deleting,
                        on_click=TrainingState.confirm_delete_run,
                    ),
                    spacing="3",
                    justify="end",
                    width="100%",
                ),
                spacing="3",
                width="100%",
            ),
            style={"max_width": "400px"},
        ),
        open=TrainingState.show_delete_modal,
    )


def api_promote_modal() -> rx.Component:
    """Modal for promoting a training run to the API registry."""
    return rx.dialog.root(
        rx.dialog.content(
            rx.dialog.title(
                rx.hstack(
                    rx.icon("plug", size=18, color=styles.ACCENT),
                    rx.text("Promote to API"),
                    spacing="2",
                    align="center",
                ),
            ),
            rx.vstack(
                rx.text(
                    "Make this model available via the Tyto API for external applications.",
                    size="2",
                    style={"color": styles.TEXT_SECONDARY},
                ),
                # Slug input
                rx.vstack(
                    rx.text("API Slug", size="1", weight="medium"),
                    rx.input(
                        placeholder="my-model-v1",
                        value=TrainingState.api_slug,
                        on_change=TrainingState.set_api_slug,
                        style={"width": "100%"},
                    ),
                    rx.text(
                        "URL-safe identifier (lowercase, numbers, hyphens only)",
                        size="1",
                        style={"color": styles.TEXT_SECONDARY},
                    ),
                    spacing="1",
                    width="100%",
                ),
                # Display name input
                rx.vstack(
                    rx.text("Display Name", size="1", weight="medium"),
                    rx.input(
                        placeholder="My Detector v1",
                        value=TrainingState.api_display_name,
                        on_change=TrainingState.set_api_display_name,
                        style={"width": "100%"},
                    ),
                    spacing="1",
                    width="100%",
                ),
                # Description input
                rx.vstack(
                    rx.text("Description (optional)", size="1", weight="medium"),
                    rx.text_area(
                        placeholder="Describe what this model detects...",
                        value=TrainingState.api_description,
                        on_change=TrainingState.set_api_description,
                        style={"width": "100%", "min_height": "80px"},
                    ),
                    spacing="1",
                    width="100%",
                ),
                # Action buttons
                rx.hstack(
                    rx.dialog.close(
                        rx.button(
                            "Cancel",
                            variant="outline",
                            color_scheme="gray",
                            on_click=TrainingState.close_api_promote_modal,
                        ),
                    ),
                    rx.button(
                        rx.cond(
                            TrainingState.api_promoting,
                            rx.spinner(size="1"),
                            rx.icon("rocket", size=14),
                        ),
                        "Promote to API",
                        color_scheme="green",
                        disabled=~TrainingState.can_promote_to_api,
                        loading=TrainingState.api_promoting,
                        on_click=TrainingState.promote_run_to_api,
                    ),
                    spacing="3",
                    justify="end",
                    width="100%",
                ),
                spacing="4",
                width="100%",
            ),
            style={"max_width": "420px"},
        ),
        open=TrainingState.show_api_promote_modal,
    )

def dashboard_page_content() -> rx.Component:
    """Full page wrapper."""
    return rx.box(
        nav_header(),
        dashboard_content(),
        delete_run_modal(),
        api_promote_modal(),
        style={
            "background": styles.BG_PRIMARY,
            "min_height": "100vh",
            "overflow": "hidden"
        },
    )


@rx.page(
    route="/projects/[project_id]/train",
    title="Training | SAFARI",
    on_load=[AuthState.check_auth, TrainingState.load_dashboard],
)
def training_dashboard_page() -> rx.Component:
    """The training dashboard page (protected)."""
    return require_auth(dashboard_page_content())
