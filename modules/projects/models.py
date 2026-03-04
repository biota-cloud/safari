"""
Shared Models — Data models for projects and datasets.
"""

from pydantic import BaseModel


class ProjectModel(BaseModel):
    """Model for project container data."""
    id: str = ""
    name: str = ""
    description: str = ""
    dataset_count: int = 0
    created_at: str = ""


class DatasetModel(BaseModel):
    """Model for dataset data.
    
    Note: Classes are stored at the project level (project.classes), not the dataset level.
    """
    id: str = ""
    project_id: str = ""
    name: str = ""
    type: str = "image"  # "image" or "video"
    description: str = ""
    created_at: str = ""
    usage_tag: str = "train"  # "train" or "validation"
    annotation_count: int = 0  # Sum of annotations across all items in dataset
    thumbnail_url: str = ""  # Presigned URL for thumbnail image

