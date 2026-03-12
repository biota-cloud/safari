"""
Dataset Detail Page — View dataset with image/video upload and thumbnail grid.

Route: /projects/{project_id}/datasets/{dataset_id}
"""

import reflex as rx
import styles
from app_state import require_auth, AuthState
from modules.datasets.dataset_detail_state import DatasetDetailState, ImageModel, VideoModel, VideoLabelsBreakdown
from components.upload_zone import upload_zone, upload_button, upload_preview_grid, video_upload_zone, video_upload_preview_grid


# =============================================================================
# SIDEBAR COMPONENTS (matching project_detail.py style)
# =============================================================================

def stat_card(icon: str, value: rx.Var, label: str, color: str = styles.ACCENT) -> rx.Component:
    """Individual stat metric card."""
    return rx.box(
        rx.vstack(
            rx.icon(icon, size=20, color=color),
            rx.text(
                value,
                size="5",
                weight="bold",
                style={"color": color},
            ),
            rx.text(
                label,
                size="1",
                style={"color": styles.TEXT_SECONDARY},
            ),
            spacing="1",
            align="center",
            width="100%",
        ),
        style={
            "padding": styles.SPACING_3,
            "background": styles.BG_TERTIARY,
            "border_radius": styles.RADIUS_MD,
            "flex": "1",
            "min_width": "0",
        },
    )


def stats_overview_panel() -> rx.Component:
    """Stats overview panel with key metrics."""
    return rx.box(
        rx.vstack(
            rx.hstack(
                rx.icon("bar-chart-3", size=18, color=styles.ACCENT),
                rx.text("Overview", size="3", weight="bold", style={"color": styles.TEXT_PRIMARY}),
                spacing="2",
                align="center",
            ),
            rx.hstack(
                # Use rx.cond to choose between image and video stat card
                rx.cond(
                    DatasetDetailState.dataset_type == "video",
                    stat_card(
                        "video",
                        DatasetDetailState.total_items.to_string(),
                        "Items",
                        styles.ACCENT,
                    ),
                    stat_card(
                        "image",
                        DatasetDetailState.total_items.to_string(),
                        "Items",
                        styles.ACCENT,
                    ),
                ),
                stat_card(
                    "check",
                    DatasetDetailState.labeled_count.to_string(),
                    "Labeled",
                    styles.SUCCESS,
                ),
                stat_card(
                    "percent",
                    DatasetDetailState.labeling_progress.to_string() + "%",
                    "Progress",
                    rx.cond(
                        DatasetDetailState.labeling_progress >= 80,
                        styles.SUCCESS,
                        rx.cond(
                            DatasetDetailState.labeling_progress >= 50,
                            styles.WARNING,
                            styles.ERROR
                        )
                    ),
                ),
                spacing="2",
                width="100%",
            ),
            spacing="3",
            width="100%",
        ),
        style={
            "padding": styles.SPACING_4,
            "background": styles.BG_SECONDARY,
            "border_radius": styles.RADIUS_LG,
            "border": f"1px solid {styles.BORDER}",
            "width": "100%",
        },
    )


def class_distribution_panel() -> rx.Component:
    """Class distribution bar chart panel."""
    return rx.box(
        rx.vstack(
            rx.hstack(
                rx.icon("pie-chart", size=18, color=styles.ACCENT),
                rx.text("Class Distribution", size="3", weight="bold", style={"color": styles.TEXT_PRIMARY}),
                spacing="2",
                align="center",
            ),
            rx.cond(
                DatasetDetailState.class_distribution_data.length() > 0,
                rx.recharts.bar_chart(
                    rx.recharts.bar(
                        data_key="count",
                        fill=styles.ACCENT,
                        radius=[0, 4, 4, 0],
                    ),
                    rx.recharts.x_axis(
                        data_key="class_name",
                        stroke=styles.TEXT_SECONDARY,
                        angle=-45,
                        text_anchor="end",
                        height=60,
                        tick={"fontSize": 10},
                    ),
                    rx.recharts.y_axis(
                        stroke=styles.TEXT_SECONDARY,
                        tick={"fontSize": 10},
                    ),
                    rx.recharts.graphing_tooltip(),
                    data=DatasetDetailState.class_distribution_data,
                    width="100%",
                    height=160,
                ),
                rx.center(
                    rx.vstack(
                        rx.icon("bar-chart-2", size=28, style={"color": styles.TEXT_SECONDARY, "opacity": "0.4"}),
                        rx.text(
                            "No annotations yet",
                            size="2",
                            style={"color": styles.TEXT_SECONDARY, "opacity": "0.7"}
                        ),
                        spacing="2",
                        align="center",
                    ),
                    min_height="100px",
                ),
            ),
            spacing="3",
            width="100%",
        ),
        style={
            "padding": styles.SPACING_4,
            "background": styles.BG_SECONDARY,
            "border_radius": styles.RADIUS_LG,
            "border": f"1px solid {styles.BORDER}",
            "width": "100%",
        },
    )








def label_item(class_name: str, count: int) -> rx.Component:
    """Single label class item for image datasets with delete action."""
    return rx.hstack(
        rx.hstack(
            rx.box(
                width="10px",
                height="10px",
                border_radius="2px",
                background=styles.ACCENT,
            ),
            rx.text(class_name, size="2", style={"color": styles.TEXT_PRIMARY}),
            spacing="2",
            align="center",
        ),
        rx.spacer(),
        rx.badge(
            count,
            color_scheme="green",
            variant="outline",
            size="1",
        ),
        rx.icon_button(
            rx.icon("trash-2", size=12),
            size="1",
            variant="ghost",
            color_scheme="red",
            on_click=lambda: DatasetDetailState.open_delete_class_annotations_modal(class_name),
            title="Delete all annotations for this class",
            style={"opacity": "0.5", "&:hover": {"opacity": "1"}},
        ),
        width="100%",
        padding=styles.SPACING_2,
        border_radius=styles.RADIUS_SM,
        _hover={"background": styles.BG_TERTIARY},
    )



def video_label_item(video_id: str, class_name: str, count: int) -> rx.Component:
    """Single label class item for video datasets with batch operations."""
    return rx.hstack(
        rx.hstack(
            rx.box(
                width="10px",
                height="10px",
                border_radius="2px",
                background=styles.ACCENT,
            ),
            rx.text(class_name, size="2", style={"color": styles.TEXT_PRIMARY}),
            spacing="2",
            align="center",
        ),
        rx.spacer(),
        rx.badge(
            count,
            color_scheme="green",
            variant="outline",
            size="1",
        ),
        rx.hstack(
            rx.icon_button(
                rx.icon("pen", size=12),
                size="1",
                variant="ghost",
                on_click=lambda: DatasetDetailState.open_reassign_labels_modal(video_id, class_name),
                title="Reassign all labels of this class",
                style={"opacity": "0.5", "&:hover": {"opacity": "1"}},
            ),
            rx.icon_button(
                rx.icon("trash-2", size=12),
                size="1",
                variant="ghost",
                color_scheme="red",
                on_click=lambda: DatasetDetailState.open_delete_labels_modal(video_id, class_name),
                title="Delete all labels of this class",
                style={"opacity": "0.5", "&:hover": {"opacity": "1"}},
            ),
            spacing="1",
        ),
        width="100%",
        padding=styles.SPACING_2,
        border_radius=styles.RADIUS_SM,
        _hover={"background": styles.BG_TERTIARY},
    )


def video_labels_section(video_breakdown: VideoLabelsBreakdown) -> rx.Component:
    """Collapsible section for labels in a single video."""
    return rx.accordion.item(
        header=rx.hstack(
            rx.icon("video", size=14, color=styles.WARNING),
            rx.text(
                video_breakdown.video_name,
                size="2",
                weight="medium",
                style={
                    "color": styles.TEXT_PRIMARY,
                    "overflow": "hidden",
                    "text_overflow": "ellipsis",
                    "white_space": "nowrap",
                    "max_width": "150px",
                }
            ),
            rx.spacer(),
            rx.badge(
                video_breakdown.label_count.to_string() + " labels",
                color_scheme="gray",
                variant="outline",
                size="1",
            ),
            width="100%",
            align="center",
        ),
        content=rx.vstack(
            rx.foreach(
                video_breakdown.labels.items(),
                lambda item: video_label_item(video_breakdown.video_id, item[0], item[1]),
            ),
            spacing="1",
            width="100%",
        ),
        value=video_breakdown.video_id,
    )


def labels_panel() -> rx.Component:
    """Panel showing all labels with management actions."""
    return rx.box(
        rx.vstack(
            rx.hstack(
                rx.icon("tags", size=18, color=styles.ACCENT),
                rx.text("Labels", size="3", weight="bold", style={"color": styles.TEXT_PRIMARY}),
                rx.spacer(),
                rx.cond(
                    DatasetDetailState.class_counts.length() > 0,
                    rx.badge(
                        DatasetDetailState.class_counts.length().to_string() + " classes",
                        color_scheme="green",
                        variant="outline",
                        size="1",
                    ),
                    rx.fragment(),
                ),
                spacing="2",
                align="center",
                width="100%",
            ),
            rx.cond(
                DatasetDetailState.class_counts.length() > 0,
                rx.cond(
                    # For video datasets, show grouped by video
                    DatasetDetailState.dataset_type == "video",
                    rx.scroll_area(
                        rx.accordion.root(
                            rx.foreach(
                                DatasetDetailState.video_labels_breakdown,
                                video_labels_section,
                            ),
                            type="multiple",
                            variant="ghost",
                        ),
                        max_height="250px",
                    ),
                    # For image datasets, show flat list
                    rx.scroll_area(
                        rx.vstack(
                            rx.foreach(
                                DatasetDetailState.class_counts.items(),
                                lambda item: label_item(item[0], item[1]),
                            ),
                            spacing="1",
                            width="100%",
                        ),
                        max_height="250px",
                    ),
                ),
                rx.center(
                    rx.vstack(
                        rx.icon("tag", size=24, style={"color": styles.TEXT_SECONDARY, "opacity": "0.4"}),
                        rx.text("No labels yet", size="2", style={"color": styles.TEXT_SECONDARY}),
                        spacing="2",
                        align="center",
                    ),
                    min_height="80px",
                ),
            ),
            spacing="3",
            width="100%",
        ),
        style={
            "padding": styles.SPACING_4,
            "background": styles.BG_SECONDARY,
            "border_radius": styles.RADIUS_LG,
            "border": f"1px solid {styles.BORDER}",
            "width": "100%",
        },
    )


def camera_info_panel() -> rx.Component:
    """Secondary panel showing camera/EXIF insights (below class distribution)."""
    return rx.cond(
        DatasetDetailState.exif_total > 0,
        rx.box(
            rx.vstack(
                rx.hstack(
                    rx.icon("camera", size=16, color=styles.TEXT_SECONDARY),
                    rx.text("Camera Info", size="2", weight="medium", style={"color": styles.TEXT_SECONDARY}),
                    spacing="2",
                    align="center",
                ),
                # Camera models list
                rx.cond(
                    DatasetDetailState.exif_cameras.length() > 0,
                    rx.vstack(
                        rx.foreach(
                            DatasetDetailState.exif_cameras,
                            lambda cam: rx.hstack(
                                rx.text(
                                    cam["model"],
                                    size="2",
                                    style={"color": styles.TEXT_PRIMARY},
                                ),
                                rx.spacer(),
                                rx.text(
                                    cam["count"] + " images",
                                    size="1",
                                    style={"color": styles.TEXT_SECONDARY},
                                ),
                                width="100%",
                                align="center",
                                padding_y="2px",
                            ),
                        ),
                        spacing="0",
                        width="100%",
                    ),
                    rx.fragment(),
                ),
                # Date range
                rx.cond(
                    DatasetDetailState.exif_date_min.length() > 0,
                    rx.hstack(
                        rx.icon("calendar", size=14, color=styles.TEXT_SECONDARY),
                        rx.text(
                            DatasetDetailState.exif_date_min + " — " + DatasetDetailState.exif_date_max,
                            size="1",
                            style={"color": styles.TEXT_SECONDARY},
                        ),
                        spacing="2",
                        align="center",
                    ),
                    rx.fragment(),
                ),
                # Day/Night split
                rx.cond(
                    (DatasetDetailState.exif_day_count + DatasetDetailState.exif_night_count) > 0,
                    rx.hstack(
                        rx.icon("sun", size=14, color=styles.WARNING),
                        rx.text(
                            DatasetDetailState.exif_day_count.to(str) + " day",
                            size="1",
                            style={"color": styles.TEXT_SECONDARY},
                        ),
                        rx.text("·", size="1", style={"color": styles.TEXT_SECONDARY}),
                        rx.icon("moon", size=14, color=styles.TEXT_SECONDARY),
                        rx.text(
                            DatasetDetailState.exif_night_count.to(str) + " night",
                            size="1",
                            style={"color": styles.TEXT_SECONDARY},
                        ),
                        spacing="2",
                        align="center",
                    ),
                    rx.fragment(),
                ),
                spacing="3",
                width="100%",
            ),
            style={
                "padding": styles.SPACING_3,
                "background": styles.BG_SECONDARY,
                "border_radius": styles.RADIUS_LG,
                "border": f"1px solid {styles.BORDER}",
                "width": "100%",
                "opacity": "0.85",
            },
        ),
        rx.fragment(),
    )


def batch_actions_bar() -> rx.Component:
    """Unified toolbar row for selection controls and bulk actions."""
    return rx.hstack(
        # Left side: selection state
        rx.cond(
            DatasetDetailState.has_selection,
            # Has selection: show count
            rx.hstack(
                rx.checkbox(
                    checked=DatasetDetailState.has_selection,
                    on_change=lambda _: DatasetDetailState.clear_selection(),
                    size="2",
                ),
                rx.text(
                    DatasetDetailState.selection_count.to_string() + " selected",
                    size="2",
                    weight="medium",
                    style={"color": styles.TEXT_PRIMARY},
                ),
                spacing="2",
                align="center",
            ),
            # No selection: show Select All
            rx.hstack(
                rx.checkbox(
                    checked=False,
                    on_change=lambda _: DatasetDetailState.select_all_items(),
                    size="2",
                ),
                rx.text(
                    "Select All",
                    size="2",
                    style={"color": styles.TEXT_SECONDARY},
                ),
                spacing="2",
                align="center",
            ),
        ),
        rx.spacer(),
        # Right side: actions (only when selected)
        rx.cond(
            DatasetDetailState.has_selection,
            rx.hstack(
                rx.button(
                    rx.icon("x", size=14),
                    "Clear",
                    size="2",
                    variant="outline",
                    on_click=DatasetDetailState.clear_selection,
                ),
                rx.button(
                    rx.icon("trash-2", size=14),
                    "Delete",
                    size="2",
                    color_scheme="red",
                    on_click=DatasetDetailState.bulk_delete_selected,
                ),
                spacing="2",
                align="center",
            ),
            rx.fragment(),
        ),
        width="100%",
        align="center",
        padding_x=styles.SPACING_3,
        padding_y=styles.SPACING_2,
        background=rx.cond(
            DatasetDetailState.has_selection,
            styles.ACCENT_MUTE,
            "transparent",
        ),
        border_radius=styles.RADIUS_MD,
        border=rx.cond(
            DatasetDetailState.has_selection,
            f"1px solid {styles.ACCENT}",
            "none",
        ),
        margin_bottom=styles.SPACING_2,
    )


def right_sidebar() -> rx.Component:
    """Right sidebar with stats, class distribution, classes, labels, and camera info panels."""
    return rx.vstack(
        stats_overview_panel(),
        class_distribution_panel(),
        labels_panel(),
        camera_info_panel(),
        spacing="3",
        width="100%",
        style={
            "position": "sticky",
            "top": styles.SPACING_4,
        },
    )


# =============================================================================
# ORIGINAL COMPONENTS (updated with selection)
# =============================================================================

def breadcrumb_nav() -> rx.Component:
    """Breadcrumb navigation."""
    return rx.hstack(
        rx.link(
            "Dashboard",
            href="/dashboard",
            style={"color": styles.TEXT_SECONDARY, "font_size": "12px"}
        ),
        rx.text("/", style={"color": styles.TEXT_SECONDARY, "font_size": "12px"}),
        rx.link(
            DatasetDetailState.project_name,
            href=f"/projects/{DatasetDetailState.current_project_id}",
            style={"color": styles.TEXT_SECONDARY, "font_size": "12px"}
        ),
        rx.text("/", style={"color": styles.TEXT_SECONDARY, "font_size": "12px"}),
        rx.text(
            DatasetDetailState.dataset_name,
            style={"color": styles.TEXT_PRIMARY, "font_size": "12px", "font_weight": "500"}
        ),
        spacing="2",
        align="center",
    )


def usage_tag_selector() -> rx.Component:
    """Inline radio selector for dataset usage tag."""
    return rx.hstack(
        rx.radio(
            ["train", "validation"],
            value=DatasetDetailState.usage_tag,
            on_change=DatasetDetailState.set_usage_tag,
            size="1",
            direction="row",
            spacing="3",
        ),
        align="center",
    )


def dataset_header() -> rx.Component:
    """Header with dataset name and back button."""
    return rx.hstack(
        # Left side: Back + Icon + Title
        rx.hstack(
            rx.link(
                rx.icon(
                    "arrow-left",
                    size=20,
                    style={"color": styles.TEXT_SECONDARY}
                ),
                href=f"/projects/{DatasetDetailState.current_project_id}",
                style={
                    "padding": styles.SPACING_2,
                    "border_radius": styles.RADIUS_MD,
                    "&:hover": {
                        "background": styles.BG_TERTIARY,
                    }
                }
            ),
            # Type icon (video/image)
            rx.cond(
                DatasetDetailState.dataset_type == "video",
                rx.icon("video", size=24, color=styles.WARNING),
                rx.icon("image", size=24, color=styles.ACCENT),
            ),
            rx.hstack(
                rx.heading(
                    DatasetDetailState.dataset_name,
                    size="7",
                    weight="bold",
                    style={"color": styles.TEXT_PRIMARY}
                ),
                rx.icon_button(
                    rx.icon("pen", size=14),
                    size="1",
                    variant="ghost",
                    on_click=DatasetDetailState.open_edit_modal,
                    style={
                        "color": styles.TEXT_SECONDARY,
                        "&:hover": {"color": styles.ACCENT},
                    }
                ),
                spacing="2",
                align="center",
            ),
            spacing="3",
            align="center",
        ),
        rx.spacer(),
        # Right side: Usage toggle + badges + Start Labeling
        rx.hstack(
            # Usage tag selector (now inline)
            usage_tag_selector(),
            # Count badges
            rx.cond(
                DatasetDetailState.dataset_type == "video",
                rx.badge(
                    f"{DatasetDetailState.video_count} videos",
                    color_scheme="gray",
                    variant="outline",
                ),
                rx.fragment(
                    rx.badge(
                        f"{DatasetDetailState.image_count} images",
                        color_scheme="green",
                        variant="outline",
                    ),
                    rx.cond(
                        DatasetDetailState.labeled_count > 0,
                        rx.badge(
                            f"{DatasetDetailState.labeled_count} labeled",
                            color_scheme="green",
                            variant="outline",
                        ),
                        rx.fragment(),
                    ),
                ),
            ),
            rx.cond(
                DatasetDetailState.dataset_type == "video",
                rx.cond(
                    DatasetDetailState.has_videos,
                    rx.link(
                        rx.button(
                            rx.icon("pen-tool", size=16),
                            "Start Labeling",
                            size="2",
                        ),
                        href=f"/projects/{DatasetDetailState.current_project_id}/datasets/{DatasetDetailState.current_dataset_id}/video-label",
                    ),
                    rx.fragment(),
                ),
                rx.cond(
                    DatasetDetailState.has_images,
                    rx.link(
                        rx.button(
                            rx.icon("pen-tool", size=16),
                            "Start Labeling",
                            size="2",
                        ),
                        href=f"/projects/{DatasetDetailState.current_project_id}/datasets/{DatasetDetailState.current_dataset_id}/label",
                    ),
                    rx.fragment(),
                ),
            ),
            spacing="2",
            align="center",
        ),
        width="100%",
        align="center",
        style={
            "padding": styles.SPACING_6,
            "border_bottom": f"1px solid {styles.BORDER}",
        }
    )


def upload_section() -> rx.Component:
    """Upload zone section with button and preview."""
    return rx.vstack(
        rx.hstack(
            rx.heading(
                "Upload Images",
                size="4",
                weight="medium",
                style={"color": styles.TEXT_PRIMARY}
            ),
            rx.spacer(),
            upload_button(
                upload_id="dataset_images",
                on_upload=lambda: DatasetDetailState.handle_upload(
                    rx.upload_files(upload_id="dataset_images")
                ),
                is_uploading=DatasetDetailState.is_uploading,
            ),
            width="100%",
            align="center",
        ),
        upload_zone(
            upload_id="dataset_images",
            is_uploading=DatasetDetailState.is_uploading,
        ),
        # Preview of selected files (shows on drop, before upload)
        upload_preview_grid(upload_id="dataset_images"),
        spacing="4",
        width="100%",
        style={
            "padding": styles.SPACING_6,
            "border_bottom": f"1px solid {styles.BORDER}",
        }
    )


def video_upload_section() -> rx.Component:
    """Video upload zone section with button."""
    return rx.vstack(
        rx.hstack(
            rx.heading(
                "Upload Videos",
                size="4",
                weight="medium",
                style={"color": styles.TEXT_PRIMARY}
            ),
            rx.spacer(),
            rx.button(
                rx.cond(
                    DatasetDetailState.is_uploading,
                    rx.hstack(
                        rx.spinner(size="1"),
                        rx.text("Uploading..."),
                        spacing="2",
                    ),
                    rx.hstack(
                        rx.icon("upload", size=16),
                        rx.text("Upload Videos"),
                        spacing="2",
                    ),
                ),
                on_click=lambda: DatasetDetailState.handle_video_upload(
                    rx.upload_files(upload_id="dataset_videos")
                ),
                disabled=DatasetDetailState.is_uploading,
                style={
                    "background": styles.ACCENT,
                    "color": "white",
                    "padding_left": styles.SPACING_4,
                    "padding_right": styles.SPACING_4,
                    "&:hover": {
                        "background": styles.ACCENT_HOVER,
                    },
                    "&:disabled": {
                        "opacity": "0.5",
                        "cursor": "not-allowed",
                    },
                }
            ),
            width="100%",
            align="center",
        ),
        video_upload_zone(
            upload_id="dataset_videos",
            is_uploading=DatasetDetailState.is_uploading,
        ),
        # Video preview grid with thumbnails
        video_upload_preview_grid(upload_id="dataset_videos"),
        spacing="4",
        width="100%",
        style={
            "padding": styles.SPACING_6,
            "border_bottom": f"1px solid {styles.BORDER}",
        }
    )


def image_thumbnail(image: ImageModel) -> rx.Component:
    """Single image thumbnail with hover actions and selection checkbox."""
    is_selected = DatasetDetailState.selected_image_ids.contains(image.id)
    
    return rx.box(
        rx.image(
            src=image.display_url,
            width="100%",
            height="150px",
            object_fit="cover",
            loading="lazy",
        ),
        # Selection checkbox (top-left)
        rx.box(
            rx.checkbox(
                checked=is_selected,
                on_change=lambda _: DatasetDetailState.toggle_image_selection(image.id),
                size="2",
            ),
            position="absolute",
            top=styles.SPACING_2,
            left=styles.SPACING_2,
            z_index="10",
        ),
        # Overlay with filename and actions
        rx.box(
            rx.hstack(
                rx.text(
                    image.filename,
                    size="1",
                    style={
                        "color": "white",
                        "overflow": "hidden",
                        "text_overflow": "ellipsis",
                        "white_space": "nowrap",
                        "max_width": "120px",
                    }
                ),
                rx.spacer(),
                rx.cond(
                    image.labeled,
                    rx.icon("circle-check", size=14, color=styles.SUCCESS),
                    rx.fragment(),
                ),
            ),
            position="absolute",
            bottom="0",
            left="0",
            right="0",
            padding=styles.SPACING_2,
            background="linear-gradient(transparent, rgba(0,0,0,0.7))",
        ),
        # Delete button (appears on hover)
        rx.box(
            rx.icon_button(
                rx.icon("trash-2", size=14),
                size="1",
                variant="ghost",
                color_scheme="red",
                on_click=lambda: DatasetDetailState.request_delete_image(image.id),
                style={
                    "opacity": "0",
                    "transition": styles.TRANSITION_FAST,
                }
            ),
            position="absolute",
            top=styles.SPACING_2,
            right=styles.SPACING_2,
            class_name="delete-btn",
        ),
        position="relative",
        border_radius=styles.RADIUS_MD,
        overflow="hidden",
        border=rx.cond(
            is_selected,
            f"2px solid {styles.ACCENT}",
            f"1px solid {styles.BORDER}",
        ),
        background=styles.BG_TERTIARY,
        cursor="pointer",
        _hover={
            "border_color": styles.ACCENT,
            "& .delete-btn button": {
                "opacity": "1",
            }
        },
        transition=styles.TRANSITION_FAST,
    )


def images_grid() -> rx.Component:
    """Grid of image thumbnails."""
    return rx.cond(
        DatasetDetailState.has_images,
        rx.box(
            rx.heading(
                "Images",
                size="4",
                weight="medium",
                style={
                    "color": styles.TEXT_PRIMARY,
                    "margin_bottom": styles.SPACING_4,
                }
            ),
            rx.grid(
                rx.foreach(
                    DatasetDetailState.images,
                    image_thumbnail
                ),
                columns="6",
                spacing="3",
                width="100%",
                style={
                    "grid_template_columns": "repeat(auto-fill, minmax(150px, 1fr))",
                }
            ),
            style={"padding": styles.SPACING_6},
        ),
        # Empty state
        rx.center(
            rx.vstack(
                rx.icon(
                    "image",
                    size=48,
                    style={"color": styles.TEXT_SECONDARY, "opacity": "0.5"}
                ),
                rx.text(
                    "No images yet",
                    size="3",
                    style={"color": styles.TEXT_SECONDARY}
                ),
                rx.text(
                    "Upload some images to get started with labeling.",
                    size="2",
                    style={"color": styles.TEXT_SECONDARY, "opacity": "0.7"}
                ),
                spacing="2",
                align="center",
            ),
            style={
                "padding": styles.SPACING_12,
                "min_height": "200px",
            }
        ),
    )


def format_duration(seconds: float) -> str:
    """Format duration in seconds to mm:ss string."""
    mins = int(seconds // 60)
    secs = int(seconds % 60)
    return f"{mins}:{secs:02d}"


def video_thumbnail(video: VideoModel) -> rx.Component:
    """Single video thumbnail with hover actions, metadata, and selection checkbox."""
    is_selected = DatasetDetailState.selected_video_ids.contains(video.id)
    
    return rx.box(
        # Thumbnail or placeholder
        rx.cond(
            video.display_url != "",
            rx.image(
                src=video.display_url,
                width="100%",
                height="150px",
                object_fit="cover",
                loading="lazy",
            ),
            # Placeholder if no thumbnail
            rx.center(
                rx.icon(
                    "video",
                    size=48,
                    style={"color": styles.TEXT_SECONDARY, "opacity": "0.5"}
                ),
                width="100%",
                height="150px",
                background=styles.BG_TERTIARY,
            ),
        ),
        # Selection checkbox (top-left)
        rx.box(
            rx.checkbox(
                checked=is_selected,
                on_change=lambda _: DatasetDetailState.toggle_video_selection(video.id),
                size="2",
            ),
            position="absolute",
            top=styles.SPACING_2,
            left=styles.SPACING_2,
            z_index="10",
        ),
        # Play icon overlay
        rx.center(
            rx.icon(
                "play",
                size=32,
                style={
                    "color": "white",
                    "opacity": "0.8",
                    "filter": "drop-shadow(0 2px 4px rgba(0,0,0,0.5))",
                }
            ),
            position="absolute",
            top="0",
            left="0",
            right="0",
            bottom="0",
            pointer_events="none",
        ),
        # Overlay with filename and metadata
        rx.box(
            rx.hstack(
                rx.text(
                    video.filename,
                    size="1",
                    style={
                        "color": "white",
                        "overflow": "hidden",
                        "text_overflow": "ellipsis",
                        "white_space": "nowrap",
                        "max_width": "100px",
                    }
                ),
                rx.spacer(),
                rx.cond(
                    video.duration_display != "",
                    rx.badge(
                        video.duration_display,
                        color_scheme="gray",
                        variant="solid",
                        size="1",
                    ),
                    rx.fragment(),
                ),
            ),
            position="absolute",
            bottom="0",
            left="0",
            right="0",
            padding=styles.SPACING_2,
            background="linear-gradient(transparent, rgba(0,0,0,0.8))",
        ),
        # Delete button (appears on hover)
        rx.box(
            rx.icon_button(
                rx.icon("trash-2", size=14),
                size="1",
                variant="ghost",
                color_scheme="red",
                on_click=lambda: DatasetDetailState.request_delete_video(video.id),
                style={
                    "opacity": "0",
                    "transition": styles.TRANSITION_FAST,
                }
            ),
            position="absolute",
            top=styles.SPACING_2,
            right=styles.SPACING_2,
            class_name="delete-btn",
        ),
        position="relative",
        border_radius=styles.RADIUS_MD,
        overflow="hidden",
        border=rx.cond(
            is_selected,
            f"2px solid {styles.WARNING}",
            f"1px solid {styles.BORDER}",
        ),
        background=styles.BG_TERTIARY,
        cursor="pointer",
        _hover={
            "border_color": styles.WARNING,
            "& .delete-btn button": {
                "opacity": "1",
            }
        },
        transition=styles.TRANSITION_FAST,
    )


def videos_grid() -> rx.Component:
    """Grid of video thumbnails."""
    return rx.cond(
        DatasetDetailState.has_videos,
        rx.box(
            rx.heading(
                "Videos",
                size="4",
                weight="medium",
                style={
                    "color": styles.TEXT_PRIMARY,
                    "margin_bottom": styles.SPACING_4,
                }
            ),
            rx.grid(
                rx.foreach(
                    DatasetDetailState.videos,
                    video_thumbnail
                ),
                columns="6",
                spacing="3",
                width="100%",
                style={
                    "grid_template_columns": "repeat(auto-fill, minmax(180px, 1fr))",
                }
            ),
            style={"padding": styles.SPACING_6},
        ),
        # Empty state
        rx.center(
            rx.vstack(
                rx.icon(
                    "video",
                    size=48,
                    style={"color": styles.TEXT_SECONDARY, "opacity": "0.5"}
                ),
                rx.text(
                    "No videos yet",
                    size="3",
                    style={"color": styles.TEXT_SECONDARY}
                ),
                rx.text(
                    "Upload some videos to get started with labeling.",
                    size="2",
                    style={"color": styles.TEXT_SECONDARY, "opacity": "0.7"}
                ),
                spacing="2",
                align="center",
            ),
            style={
                "padding": styles.SPACING_12,
                "min_height": "200px",
            }
        ),
    )


def loading_skeleton() -> rx.Component:
    """Loading skeleton for the page."""
    return rx.vstack(
        rx.skeleton(height="60px", width="100%"),
        rx.skeleton(height="200px", width="100%"),
        rx.hstack(
            rx.skeleton(height="150px", width="150px"),
            rx.skeleton(height="150px", width="150px"),
            rx.skeleton(height="150px", width="150px"),
            spacing="3",
        ),
        spacing="4",
        padding=styles.SPACING_6,
        width="100%",
    )


def error_state() -> rx.Component:
    """Error state display."""
    return rx.center(
        rx.vstack(
            rx.icon(
                "circle-alert",
                size=48,
                style={"color": styles.ERROR}
            ),
            rx.text(
                DatasetDetailState.error_message,
                style={"color": styles.TEXT_PRIMARY}
            ),
            rx.link(
                rx.button(
                    "Back to Project",
                    variant="outline",
                ),
                href=f"/projects/{DatasetDetailState.current_project_id}",
            ),
            spacing="4",
            align="center",
        ),
        style={
            "padding": styles.SPACING_12,
            "min_height": "400px",
        }
    )


def dataset_detail_content() -> rx.Component:
    """Main content for the dataset detail page with 2-column layout."""
    return rx.cond(
        DatasetDetailState.is_loading,
        loading_skeleton(),
        rx.cond(
            DatasetDetailState.error_message != "",
            error_state(),
            rx.box(
                dataset_header(),
                # 2-column layout: main content + sidebar
                rx.hstack(
                    # Main content (70%)
                    rx.box(
                        rx.cond(
                            DatasetDetailState.dataset_type == "video",
                            rx.fragment(
                                video_upload_section(),
                                batch_actions_bar(),
                                videos_grid(),
                            ),
                            rx.fragment(
                                upload_section(),
                                batch_actions_bar(),
                                images_grid(),
                            ),
                        ),
                        flex="2",
                        min_width="0",
                    ),
                    # Right sidebar (30%)
                    rx.box(
                        right_sidebar(),
                        flex="1",
                        min_width="280px",
                        max_width="350px",
                        padding_left=styles.SPACING_4,
                    ),
                    width="100%",
                    align="start",
                    padding=styles.SPACING_4,
                ),
                width="100%",
            ),
        ),
    )


def dataset_detail_page_content() -> rx.Component:
    """Full page wrapper."""
    return rx.box(
        dataset_detail_content(),
        edit_dataset_modal(),
        duplicate_warning_modal(),
        reassign_labels_modal(),
        delete_labels_modal(),
        delete_image_modal(),
        delete_video_modal(),
        delete_class_annotations_modal(),
        style={
            "background": styles.BG_PRIMARY,
            "min_height": "100vh",
        }
    )




def reassign_labels_modal() -> rx.Component:
    """Modal for reassigning labels of a class in a video to a different class."""
    return rx.dialog.root(
        rx.dialog.content(
            rx.dialog.title(
                rx.hstack(
                    rx.icon("pen", size=18, color=styles.ACCENT),
                    "Reassign Labels",
                    spacing="2",
                    align="center",
                )
            ),
            rx.vstack(
                rx.text(
                    f"Reassign all '{DatasetDetailState.target_class_name}' labels to a different class.",
                    size="2",
                    style={"color": styles.TEXT_SECONDARY},
                ),
                rx.select(
                    DatasetDetailState.available_classes_for_reassign,
                    placeholder="Select target class",
                    value=DatasetDetailState.reassign_to_class,
                    on_change=DatasetDetailState.set_reassign_to_class,
                    size="2",
                ),
                rx.hstack(
                    rx.dialog.close(
                        rx.button(
                            "Cancel",
                            variant="outline",
                            color_scheme="gray",
                            on_click=DatasetDetailState.close_reassign_modal,
                        ),
                    ),
                    rx.button(
                        "Reassign",
                        color_scheme="green",
                        on_click=DatasetDetailState.confirm_reassign_labels,
                        loading=DatasetDetailState.is_processing_class,
                        disabled=DatasetDetailState.reassign_to_class == "",
                    ),
                    spacing="3",
                    justify="end",
                    width="100%",
                    margin_top=styles.SPACING_4,
                ),
                spacing="3",
                width="100%",
            ),
            style={"max_width": "400px"},
        ),
        open=DatasetDetailState.show_reassign_modal,
    )


def delete_labels_modal() -> rx.Component:
    """Modal for confirming deletion of all labels of a class in a video."""
    return rx.dialog.root(
        rx.dialog.content(
            rx.dialog.title(
                rx.hstack(
                    rx.icon("trash-2", size=18, color=styles.ERROR),
                    "Delete Labels",
                    spacing="2",
                    align="center",
                )
            ),
            rx.vstack(
                rx.callout(
                    rx.text(
                        f"This will permanently delete all '{DatasetDetailState.target_class_name}' "
                        "labels in this video.",
                    ),
                    icon="triangle-alert",
                    color="red",
                    size="2",
                ),
                rx.hstack(
                    rx.dialog.close(
                        rx.button(
                            "Cancel",
                            variant="outline",
                            color_scheme="gray",
                            on_click=DatasetDetailState.close_delete_labels_modal,
                        ),
                    ),
                    rx.button(
                        "Delete",
                        color_scheme="red",
                        on_click=DatasetDetailState.confirm_delete_labels,
                        loading=DatasetDetailState.is_processing_class,
                    ),
                    spacing="3",
                    justify="end",
                    width="100%",
                    margin_top=styles.SPACING_4,
                ),
                spacing="3",
                width="100%",
            ),
            style={"max_width": "400px"},
        ),
        open=DatasetDetailState.show_delete_labels_modal,
    )


def delete_class_annotations_modal() -> rx.Component:
    """Modal for confirming deletion of all annotations for a class (high-impact: requires typing 'delete')."""
    return rx.dialog.root(
        rx.dialog.content(
            rx.dialog.title(
                rx.hstack(
                    rx.icon("trash-2", size=18, color=styles.ERROR),
                    "Delete All Class Annotations",
                    spacing="2",
                    align="center",
                )
            ),
            rx.vstack(
                rx.callout(
                    rx.text(
                        f"This will permanently delete all ",
                        rx.text(
                            DatasetDetailState.delete_class_annotations_count.to_string(),
                            weight="bold",
                        ),
                        " '",
                        rx.text(
                            DatasetDetailState.delete_class_annotations_name,
                            weight="bold",
                        ),
                        "' annotations in this dataset.",
                    ),
                    icon="triangle-alert",
                    color="red",
                    size="2",
                ),
                rx.text(
                    "This action cannot be undone. To confirm, type 'delete' below:",
                    size="2",
                    weight="medium",
                    style={"color": styles.TEXT_SECONDARY},
                ),
                rx.input(
                    value=DatasetDetailState.delete_class_confirmation,
                    on_change=DatasetDetailState.set_delete_class_confirmation,
                    placeholder="Type 'delete' to confirm",
                    width="100%",
                ),
                rx.hstack(
                    rx.dialog.close(
                        rx.button(
                            "Cancel",
                            variant="outline",
                            color_scheme="gray",
                            on_click=DatasetDetailState.close_delete_class_annotations_modal,
                        ),
                    ),
                    rx.button(
                        rx.cond(
                            DatasetDetailState.is_deleting_class_annotations,
                            rx.hstack(rx.spinner(size="1"), rx.text("Deleting..."), spacing="2"),
                            rx.hstack(rx.icon("trash-2", size=14), rx.text("Delete"), spacing="2"),
                        ),
                        color_scheme="red",
                        on_click=DatasetDetailState.confirm_delete_class_annotations,
                        disabled=~DatasetDetailState.can_confirm_delete_class_annotations,
                    ),
                    spacing="3",
                    justify="end",
                    width="100%",
                    margin_top=styles.SPACING_4,
                ),
                spacing="3",
                width="100%",
            ),
            style={"max_width": "450px"},
        ),
        open=DatasetDetailState.show_delete_class_annotations_modal,
    )


def delete_image_modal() -> rx.Component:
    """Modal for confirming image deletion."""
    return rx.dialog.root(
        rx.dialog.content(
            rx.vstack(
                rx.hstack(
                    rx.icon("alert-triangle", size=20, color=styles.WARNING),
                    rx.text(
                        "Remove this image?",
                        weight="medium",
                        style={"color": styles.TEXT_PRIMARY}
                    ),
                    spacing="2",
                    align="center",
                ),
                rx.text(
                    DatasetDetailState.image_to_delete_name,
                    size="2",
                    weight="medium",
                    style={
                        "color": styles.TEXT_SECONDARY,
                        "max_width": "100%",
                        "overflow": "hidden",
                        "text_overflow": "ellipsis",
                        "white_space": "nowrap",
                    }
                ),
                rx.text(
                    "This will also delete any annotations.",
                    size="1",
                    style={"color": styles.TEXT_SECONDARY}
                ),
                rx.hstack(
                    rx.dialog.close(
                        rx.button(
                            "Cancel",
                            variant="outline",
                            color_scheme="gray",
                            on_click=DatasetDetailState.close_delete_image_modal,
                        ),
                    ),
                    rx.button(
                        "Confirm",
                        color_scheme="red",
                        on_click=DatasetDetailState.confirm_delete_image,
                    ),
                    spacing="3",
                    justify="end",
                    width="100%",
                ),
                spacing="3",
                width="100%",
            ),
            style={"max_width": "320px"},
        ),
        open=DatasetDetailState.show_delete_image_modal,
    )


def delete_video_modal() -> rx.Component:
    """Modal for confirming video deletion."""
    return rx.dialog.root(
        rx.dialog.content(
            rx.vstack(
                rx.hstack(
                    rx.icon("alert-triangle", size=20, color=styles.WARNING),
                    rx.text(
                        "Remove this video?",
                        weight="medium",
                        style={"color": styles.TEXT_PRIMARY}
                    ),
                    spacing="2",
                    align="center",
                ),
                rx.text(
                    DatasetDetailState.video_to_delete_name,
                    size="2",
                    weight="medium",
                    style={
                        "color": styles.TEXT_SECONDARY,
                        "max_width": "100%",
                        "overflow": "hidden",
                        "text_overflow": "ellipsis",
                        "white_space": "nowrap",
                    }
                ),
                rx.text(
                    "This will also delete all keyframes and annotations.",
                    size="1",
                    style={"color": styles.TEXT_SECONDARY}
                ),
                rx.hstack(
                    rx.dialog.close(
                        rx.button(
                            "Cancel",
                            variant="outline",
                            color_scheme="gray",
                            on_click=DatasetDetailState.close_delete_video_modal,
                        ),
                    ),
                    rx.button(
                        "Confirm",
                        color_scheme="red",
                        on_click=DatasetDetailState.confirm_delete_video,
                    ),
                    spacing="3",
                    justify="end",
                    width="100%",
                ),
                spacing="3",
                width="100%",
            ),
            style={"max_width": "320px"},
        ),
        open=DatasetDetailState.show_delete_video_modal,
    )


def edit_dataset_modal() -> rx.Component:
    """Modal for editing dataset details."""
    return rx.dialog.root(
        rx.dialog.content(
            rx.dialog.title("Edit Dataset"),
            rx.vstack(
                rx.input(
                    placeholder="Dataset name",
                    value=DatasetDetailState.edit_dataset_name,
                    on_change=DatasetDetailState.set_edit_dataset_name,
                    on_key_down=DatasetDetailState.handle_edit_keydown,
                    style={"width": "100%"},
                ),
                rx.cond(
                    DatasetDetailState.edit_dataset_error != "",
                    rx.text(
                        DatasetDetailState.edit_dataset_error,
                        size="2",
                        style={"color": styles.ERROR}
                    ),
                    rx.fragment(),
                ),
                rx.hstack(
                    rx.dialog.close(
                        rx.button(
                            "Cancel",
                            variant="outline",
                            color_scheme="gray",
                            on_click=DatasetDetailState.close_edit_modal,
                        ),
                    ),
                    rx.button(
                        "Save",
                        on_click=DatasetDetailState.save_dataset_edits,
                        loading=DatasetDetailState.is_saving_dataset,
                        style={
                            "background": styles.ACCENT,
                            "color": "white",
                            "&:hover": {
                                "background": styles.ACCENT_HOVER,
                            }
                        }
                    ),
                    spacing="3",
                    justify="end",
                    width="100%",
                    margin_top=styles.SPACING_4,
                ),
                spacing="3",
                width="100%",
            ),
            style={
                "max_width": "450px",
            }
        ),
        open=DatasetDetailState.show_edit_modal,
    )


def duplicate_warning_modal() -> rx.Component:
    """Modal warning about duplicate filenames before upload."""
    return rx.dialog.root(
        rx.dialog.content(
            rx.dialog.title(
                rx.hstack(
                    rx.icon("triangle-alert", size=20, color=styles.WARNING),
                    rx.text("Duplicate Files Detected"),
                    spacing="2",
                    align="center",
                )
            ),
            rx.vstack(
                rx.text(
                    "The following files already exist in this project:",
                    size="2",
                    style={"color": styles.TEXT_SECONDARY}
                ),
                rx.box(
                    rx.hstack(
                        rx.foreach(
                            DatasetDetailState.duplicate_filenames,
                            lambda name: rx.badge(
                                name,
                                color_scheme="gray",
                                variant="outline",
                            )
                        ),
                        wrap="wrap",
                        spacing="2",
                    ),
                    style={
                        "max_height": "150px",
                        "overflow_y": "auto",
                        "padding": styles.SPACING_2,
                        "background": styles.BG_SECONDARY,
                        "border_radius": styles.RADIUS_MD,
                        "width": "100%",
                    }
                ),
                rx.text(
                    "Would you like to upload anyway or skip these files?",
                    size="2",
                    style={"color": styles.TEXT_SECONDARY, "margin_top": styles.SPACING_2}
                ),
                rx.hstack(
                    rx.button(
                        "Cancel",
                        variant="outline",
                        color_scheme="gray",
                        on_click=DatasetDetailState.cancel_upload,
                    ),
                    rx.button(
                        "Skip Duplicates",
                        variant="outline",
                        on_click=DatasetDetailState.confirm_upload_excluding_duplicates,
                        style={
                            "border_color": styles.WARNING,
                            "color": styles.WARNING,
                        }
                    ),
                    rx.button(
                        "Upload All",
                        on_click=DatasetDetailState.confirm_upload_all,
                        style={
                            "background": styles.ACCENT,
                            "color": "white",
                        }
                    ),
                    spacing="3",
                    justify="end",
                    width="100%",
                    margin_top=styles.SPACING_4,
                ),
                spacing="3",
                width="100%",
            ),
            style={
                "max_width": "500px",
            }
        ),
        open=DatasetDetailState.show_duplicate_warning,
    )


@rx.page(
    route="/projects/[project_id]/datasets/[dataset_id]",
    title="Dataset | SAFARI",
    on_load=[AuthState.check_auth, DatasetDetailState.load_dataset]
)
def dataset_detail_page() -> rx.Component:
    """The dataset detail page (protected)."""
    return require_auth(dataset_detail_page_content())
