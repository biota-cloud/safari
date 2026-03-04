"""
Unit tests for annotation_service module.

These tests verify annotation read, write, and aggregation operations
using mocked Supabase and R2 dependencies.
"""

import pytest
from unittest.mock import MagicMock, patch

# Import the service module
from backend.annotation_service import (
    get_annotations,
    get_dataset_annotations,
    get_annotations_for_training,
    compute_class_counts,
    compute_class_counts_for_datasets,
    save_annotations,
    _annotations_to_yolo,
    _yolo_to_annotations,
    _filter_and_shift_annotations,
    _rename_in_annotations,
    resolve_class_names,
    strip_class_names,
    validate_annotation_coordinates,
    validate_annotations_batch,
)



# =============================================================================
# Test fixtures
# =============================================================================

@pytest.fixture
def sample_annotations():
    """Sample annotation list for testing."""
    return [
        {"id": "ann-1", "class_id": 0, "class_name": "Lynx", "x": 0.1, "y": 0.2, "width": 0.3, "height": 0.4},
        {"id": "ann-2", "class_id": 1, "class_name": "Deer", "x": 0.5, "y": 0.6, "width": 0.2, "height": 0.2},
    ]


@pytest.fixture
def sample_annotations_map():
    """Sample annotation map for testing."""
    return {
        "img-1": [
            {"id": "a1", "class_id": 0, "class_name": "Lynx", "x": 0.1, "y": 0.1, "width": 0.2, "height": 0.2},
        ],
        "img-2": [
            {"id": "a2", "class_id": 0, "class_name": "Lynx", "x": 0.3, "y": 0.3, "width": 0.1, "height": 0.1},
            {"id": "a3", "class_id": 1, "class_name": "Deer", "x": 0.5, "y": 0.5, "width": 0.2, "height": 0.2},
        ],
    }


# =============================================================================
# YOLO format conversion tests
# =============================================================================

class TestAnnotationsToYolo:
    """Tests for _annotations_to_yolo() function."""
    
    def test_single_annotation(self, sample_annotations):
        """Single annotation converts correctly."""
        ann = [sample_annotations[0]]
        yolo = _annotations_to_yolo(ann)
        
        # class_id x_center y_center width height
        # x_center = 0.1 + 0.3/2 = 0.25
        # y_center = 0.2 + 0.4/2 = 0.4
        assert yolo == "0 0.250000 0.400000 0.300000 0.400000"
    
    def test_multiple_annotations(self, sample_annotations):
        """Multiple annotations produce multiple lines."""
        yolo = _annotations_to_yolo(sample_annotations)
        lines = yolo.strip().split("\n")
        
        assert len(lines) == 2
        assert lines[0].startswith("0 ")  # class_id 0
        assert lines[1].startswith("1 ")  # class_id 1
    
    def test_empty_list(self):
        """Empty list returns empty string."""
        assert _annotations_to_yolo([]) == ""


class TestYoloToAnnotations:
    """Tests for _yolo_to_annotations() function."""
    
    def test_single_line(self):
        """Single YOLO line parses correctly."""
        yolo = "0 0.25 0.4 0.3 0.4"
        classes = ["Lynx", "Deer"]
        
        annotations = _yolo_to_annotations(yolo, classes)
        
        assert len(annotations) == 1
        ann = annotations[0]
        assert ann["class_id"] == 0
        assert ann["class_name"] == "Lynx"
        # x = 0.25 - 0.3/2 = 0.1
        assert abs(ann["x"] - 0.1) < 0.001
        assert abs(ann["y"] - 0.2) < 0.001
        assert abs(ann["width"] - 0.3) < 0.001
        assert abs(ann["height"] - 0.4) < 0.001
    
    def test_multiple_lines(self):
        """Multiple YOLO lines parse correctly."""
        yolo = "0 0.25 0.4 0.3 0.4\n1 0.6 0.7 0.2 0.2"
        classes = ["Lynx", "Deer"]
        
        annotations = _yolo_to_annotations(yolo, classes)
        
        assert len(annotations) == 2
        assert annotations[0]["class_name"] == "Lynx"
        assert annotations[1]["class_name"] == "Deer"
    
    def test_empty_input(self):
        """Empty input returns empty list."""
        assert _yolo_to_annotations("", ["Lynx"]) == []
        assert _yolo_to_annotations("   \n  ", ["Lynx"]) == []
    
    def test_invalid_line_skipped(self):
        """Invalid lines are skipped."""
        yolo = "0 0.25 0.4 0.3 0.4\ninvalid line\n1 0.5 0.5 0.2 0.2"
        classes = ["Lynx", "Deer"]
        
        annotations = _yolo_to_annotations(yolo, classes)
        
        assert len(annotations) == 2
    
    def test_unknown_class_id(self):
        """Unknown class_id gets 'Unknown' class_name."""
        yolo = "5 0.5 0.5 0.2 0.2"
        classes = ["Lynx", "Deer"]
        
        annotations = _yolo_to_annotations(yolo, classes)
        
        assert annotations[0]["class_id"] == 5
        assert annotations[0]["class_name"] == "Unknown"


# =============================================================================
# Class count aggregation tests
# =============================================================================

class TestComputeClassCounts:
    """Tests for compute_class_counts() function."""
    
    def test_empty_map(self):
        """Empty map returns empty counts."""
        assert compute_class_counts({}) == {}
    
    def test_single_class(self):
        """Single class counted correctly."""
        annotations_map = {
            "img-1": [{"class_name": "Lynx"}],
            "img-2": [{"class_name": "Lynx"}, {"class_name": "Lynx"}],
        }
        
        counts = compute_class_counts(annotations_map)
        
        assert counts == {"Lynx": 3}
    
    def test_multiple_classes(self, sample_annotations_map):
        """Multiple classes counted correctly."""
        counts = compute_class_counts(sample_annotations_map)
        
        assert counts == {"Lynx": 2, "Deer": 1}
    
    def test_missing_class_name(self):
        """Annotations with empty class_name are counted as 'Unknown' when no project_classes provided."""
        annotations_map = {
            "img-1": [{"class_name": ""}, {"class_name": "Lynx"}],
        }
        
        counts = compute_class_counts(annotations_map)
        
        # Without project_classes, empty class_name resolves to "Unknown"
        assert counts == {"Unknown": 1, "Lynx": 1}


# =============================================================================
# Class rename/delete helper tests
# =============================================================================

class TestRenameInAnnotations:
    """Tests for _rename_in_annotations() helper."""
    
    def test_simple_rename(self):
        """Simple class rename works."""
        annotations = [
            {"class_id": 0, "class_name": "Cat"},
            {"class_id": 1, "class_name": "Dog"},
        ]
        
        modified = _rename_in_annotations(
            annotations, "Cat", "Lynx", 
            old_idx=None, new_idx=None, is_merge=False
        )
        
        assert modified is True
        assert annotations[0]["class_name"] == "Lynx"
        assert annotations[1]["class_name"] == "Dog"  # unchanged
    
    def test_no_match(self):
        """No modifications if class not found."""
        annotations = [
            {"class_id": 0, "class_name": "Cat"},
        ]
        
        modified = _rename_in_annotations(
            annotations, "Dog", "Wolf",
            old_idx=None, new_idx=None, is_merge=False
        )
        
        assert modified is False
        assert annotations[0]["class_name"] == "Cat"
    
    def test_merge_with_id_shift(self):
        """Merge operation shifts class IDs."""
        annotations = [
            {"class_id": 0, "class_name": "Cat"},
            {"class_id": 2, "class_name": "Bird"},  # Should shift down
        ]
        
        modified = _rename_in_annotations(
            annotations, "Cat", "Lynx",
            old_idx=1, new_idx=0, is_merge=True
        )
        
        assert modified is True
        assert annotations[0]["class_name"] == "Lynx"
        assert annotations[1]["class_id"] == 1  # Shifted from 2


class TestFilterAndShiftAnnotations:
    """Tests for _filter_and_shift_annotations() helper."""
    
    def test_filters_deleted_class(self):
        """Deleted class is filtered out."""
        annotations = [
            {"class_id": 0, "class_name": "Cat"},
            {"class_id": 1, "class_name": "Dog"},
        ]
        new_classes = ["Cat"]  # Dog deleted
        
        result, modified = _filter_and_shift_annotations(
            annotations, "Dog", 1, new_classes
        )
        
        assert modified is True
        assert len(result) == 1
        assert result[0]["class_name"] == "Cat"
    
    def test_shifts_higher_ids(self):
        """Class IDs higher than deleted are shifted down."""
        annotations = [
            {"class_id": 0, "class_name": "Cat"},
            {"class_id": 2, "class_name": "Bird"},
        ]
        new_classes = ["Cat", "Bird"]  # Dog (id=1) deleted
        
        result, modified = _filter_and_shift_annotations(
            annotations, "Dog", 1, new_classes
        )
        
        assert modified is True
        assert len(result) == 2
        assert result[1]["class_id"] == 1  # Shifted from 2
        assert result[1]["class_name"] == "Bird"


# =============================================================================
# Read operation tests (with mocked Supabase)
# =============================================================================

class TestGetAnnotations:
    """Tests for get_annotations() with mocked dependencies."""
    
    @patch("backend.supabase_client.get_supabase")
    def test_returns_annotations_for_image(self, mock_get_supabase):
        """Returns annotations for image type."""
        mock_supabase = MagicMock()
        mock_get_supabase.return_value = mock_supabase
        
        mock_supabase.table.return_value.select.return_value.eq.return_value.single.return_value.execute.return_value.data = {
            "annotations": [{"class_id": 0, "class_name": "Lynx"}]
        }
        
        result = get_annotations("img-123", "image")
        
        assert len(result) == 1
        assert result[0]["class_name"] == "Lynx"
        mock_supabase.table.assert_called_with("images")
    
    @patch("backend.supabase_client.get_supabase")
    def test_returns_annotations_for_keyframe(self, mock_get_supabase):
        """Returns annotations for keyframe type."""
        mock_supabase = MagicMock()
        mock_get_supabase.return_value = mock_supabase
        
        mock_supabase.table.return_value.select.return_value.eq.return_value.single.return_value.execute.return_value.data = {
            "annotations": [{"class_id": 0, "class_name": "Deer"}]
        }
        
        result = get_annotations("kf-456", "keyframe")
        
        assert result[0]["class_name"] == "Deer"
        mock_supabase.table.assert_called_with("keyframes")
    
    @patch("backend.supabase_client.get_supabase")
    def test_returns_empty_list_on_null(self, mock_get_supabase):
        """Returns empty list when annotations is NULL."""
        mock_supabase = MagicMock()
        mock_get_supabase.return_value = mock_supabase
        
        mock_supabase.table.return_value.select.return_value.eq.return_value.single.return_value.execute.return_value.data = {
            "annotations": None
        }
        
        result = get_annotations("img-123", "image")
        
        assert result == []


# =============================================================================
# Write operation tests (with mocked Supabase and R2)
# =============================================================================

class TestSaveAnnotations:
    """Tests for save_annotations() with mocked dependencies."""
    
    @patch("backend.r2_storage.R2Client")
    @patch("backend.supabase_client.get_supabase")
    def test_saves_to_supabase_and_r2(self, mock_get_supabase, mock_r2_class):
        """Saves to both Supabase and R2."""
        mock_supabase = MagicMock()
        mock_get_supabase.return_value = mock_supabase
        mock_r2 = MagicMock()
        mock_r2_class.return_value = mock_r2
        
        annotations = [{"class_id": 0, "class_name": "Lynx", "x": 0.1, "y": 0.2, "width": 0.3, "height": 0.4}]
        
        result = save_annotations(
            item_id="img-123",
            item_type="image",
            annotations=annotations,
            dataset_id="ds-456",
            sync_r2=True
        )
        
        assert result is True
        
        # Verify Supabase update
        mock_supabase.table.assert_called_with("images")
        
        # Verify R2 upload
        mock_r2.upload_file.assert_called_once()
        call_kwargs = mock_r2.upload_file.call_args.kwargs
        assert "datasets/ds-456/labels/img-123.txt" in call_kwargs["path"]
    
    @patch("backend.supabase_client.get_supabase")
    def test_skips_r2_when_disabled(self, mock_get_supabase):
        """Skips R2 sync when sync_r2=False."""
        mock_supabase = MagicMock()
        mock_get_supabase.return_value = mock_supabase
        
        result = save_annotations(
            item_id="img-123",
            item_type="image",
            annotations=[],
            dataset_id="ds-456",
            sync_r2=False
        )
        
        assert result is True
        # R2 not called (no import of R2Client)


# =============================================================================
# Resolution layer tests (Phase E: Tech Debt)
# =============================================================================

class TestResolveClassNames:
    """Tests for resolve_class_names() function."""
    
    def test_resolves_from_class_id(self):
        """Resolves class_name from class_id using project_classes."""
        annotations = [
            {"class_id": 0, "x": 0.1, "y": 0.2, "width": 0.3, "height": 0.4},
            {"class_id": 1, "x": 0.5, "y": 0.5, "width": 0.2, "height": 0.2},
        ]
        project_classes = ["Lynx", "Deer"]
        
        result = resolve_class_names(annotations, project_classes)
        
        assert result[0]["class_name"] == "Lynx"
        assert result[1]["class_name"] == "Deer"
    
    def test_overwrites_existing_class_name(self):
        """Resolved name overrides any existing class_name (handles stale names)."""
        annotations = [
            {"class_id": 0, "class_name": "StaleOldName", "x": 0.1, "y": 0.1, "width": 0.1, "height": 0.1},
        ]
        project_classes = ["Lynx"]
        
        result = resolve_class_names(annotations, project_classes)
        
        assert result[0]["class_name"] == "Lynx"  # Not StaleOldName
    
    def test_unknown_for_invalid_class_id(self):
        """Returns 'Unknown' for class_id out of bounds."""
        annotations = [
            {"class_id": 99, "x": 0.1, "y": 0.1, "width": 0.1, "height": 0.1},
        ]
        project_classes = ["Lynx", "Deer"]
        
        result = resolve_class_names(annotations, project_classes)
        
        assert result[0]["class_name"] == "Unknown"
    
    def test_does_not_mutate_original(self):
        """Original annotations are not mutated."""
        annotations = [
            {"class_id": 0, "class_name": "Original", "x": 0.1, "y": 0.1, "width": 0.1, "height": 0.1},
        ]
        project_classes = ["Resolved"]
        
        resolve_class_names(annotations, project_classes)
        
        assert annotations[0]["class_name"] == "Original"  # Unchanged
    
    def test_empty_list(self):
        """Empty annotations list returns empty list."""
        result = resolve_class_names([], ["Lynx"])
        assert result == []


class TestStripClassNames:
    """Tests for strip_class_names() function."""
    
    def test_removes_class_name(self):
        """Removes class_name key from annotations."""
        annotations = [
            {"class_id": 0, "class_name": "Lynx", "x": 0.1, "y": 0.2, "width": 0.3, "height": 0.4},
        ]
        
        result = strip_class_names(annotations)
        
        assert "class_name" not in result[0]
        assert result[0]["class_id"] == 0
        assert result[0]["x"] == 0.1
    
    def test_preserves_other_fields(self):
        """All other fields are preserved."""
        annotations = [
            {"id": "ann-1", "class_id": 0, "class_name": "Lynx", "x": 0.1, "y": 0.2, "width": 0.3, "height": 0.4},
        ]
        
        result = strip_class_names(annotations)
        
        assert result[0]["id"] == "ann-1"
        assert result[0]["class_id"] == 0
        assert result[0]["x"] == 0.1
        assert result[0]["y"] == 0.2
        assert result[0]["width"] == 0.3
        assert result[0]["height"] == 0.4
    
    def test_already_stripped(self):
        """Works on annotations that already lack class_name."""
        annotations = [
            {"class_id": 0, "x": 0.1, "y": 0.1, "width": 0.1, "height": 0.1},
        ]
        
        result = strip_class_names(annotations)
        
        assert "class_name" not in result[0]
        assert result[0]["class_id"] == 0
    
    def test_does_not_mutate_original(self):
        """Original annotations are not mutated."""
        annotations = [
            {"class_id": 0, "class_name": "Lynx", "x": 0.1, "y": 0.1, "width": 0.1, "height": 0.1},
        ]
        
        strip_class_names(annotations)
        
        assert annotations[0]["class_name"] == "Lynx"  # Unchanged
    
    def test_empty_list(self):
        """Empty annotations list returns empty list."""
        result = strip_class_names([])
        assert result == []


# =============================================================================
# Validation layer tests (Phase E2: Coordinate Standardization)
# =============================================================================

class TestValidateAnnotationCoordinates:
    """Tests for validate_annotation_coordinates() function."""
    
    def test_valid_annotation(self):
        """Valid annotation passes validation."""
        ann = {"class_id": 0, "x": 0.1, "y": 0.2, "width": 0.3, "height": 0.4}
        
        is_valid, error = validate_annotation_coordinates(ann)
        
        assert is_valid is True
        assert error == ""
    
    def test_missing_field(self):
        """Missing required field fails validation."""
        ann = {"class_id": 0, "x": 0.1, "y": 0.2, "width": 0.3}  # Missing height
        
        is_valid, error = validate_annotation_coordinates(ann)
        
        assert is_valid is False
        assert "Missing field: height" in error
    
    def test_non_numeric_value(self):
        """Non-numeric value fails validation."""
        ann = {"class_id": 0, "x": "0.1", "y": 0.2, "width": 0.3, "height": 0.4}
        
        is_valid, error = validate_annotation_coordinates(ann)
        
        assert is_valid is False
        assert "must be numeric" in error
    
    def test_negative_value(self):
        """Negative value fails validation."""
        ann = {"class_id": 0, "x": -0.1, "y": 0.2, "width": 0.3, "height": 0.4}
        
        is_valid, error = validate_annotation_coordinates(ann)
        
        assert is_valid is False
        assert "must be 0-1" in error
    
    def test_value_over_one(self):
        """Value over 1.0 fails validation."""
        ann = {"class_id": 0, "x": 0.1, "y": 1.5, "width": 0.3, "height": 0.4}
        
        is_valid, error = validate_annotation_coordinates(ann)
        
        assert is_valid is False
        assert "must be 0-1" in error
    
    def test_box_extends_beyond_right_edge(self):
        """Box extending beyond right edge fails validation."""
        ann = {"class_id": 0, "x": 0.8, "y": 0.2, "width": 0.3, "height": 0.2}  # x + width > 1
        
        is_valid, error = validate_annotation_coordinates(ann)
        
        assert is_valid is False
        assert "beyond right edge" in error
    
    def test_box_extends_beyond_bottom_edge(self):
        """Box extending beyond bottom edge fails validation."""
        ann = {"class_id": 0, "x": 0.2, "y": 0.9, "width": 0.2, "height": 0.2}  # y + height > 1
        
        is_valid, error = validate_annotation_coordinates(ann)
        
        assert is_valid is False
        assert "beyond bottom edge" in error
    
    def test_edge_case_exact_boundary(self):
        """Box exactly at boundary passes validation."""
        ann = {"class_id": 0, "x": 0.5, "y": 0.5, "width": 0.5, "height": 0.5}  # x + width = 1.0
        
        is_valid, error = validate_annotation_coordinates(ann)
        
        assert is_valid is True


class TestValidateAnnotationsBatch:
    """Tests for validate_annotations_batch() function."""
    
    def test_all_valid(self):
        """All valid annotations returns empty error list."""
        annotations = [
            {"class_id": 0, "x": 0.1, "y": 0.2, "width": 0.3, "height": 0.4},
            {"class_id": 1, "x": 0.5, "y": 0.5, "width": 0.2, "height": 0.2},
        ]
        
        errors = validate_annotations_batch(annotations)
        
        assert errors == []
    
    def test_some_invalid(self):
        """Returns errors for invalid annotations with indices."""
        annotations = [
            {"class_id": 0, "x": 0.1, "y": 0.2, "width": 0.3, "height": 0.4},  # Valid
            {"class_id": 1, "x": -0.1, "y": 0.5, "width": 0.2, "height": 0.2},  # Invalid: negative x
            {"class_id": 2, "x": 0.9, "y": 0.9, "width": 0.2, "height": 0.2},  # Invalid: extends beyond
        ]
        
        errors = validate_annotations_batch(annotations)
        
        assert len(errors) == 2
        assert errors[0][0] == 1  # Index 1
        assert errors[1][0] == 2  # Index 2
    
    def test_empty_list(self):
        """Empty list returns empty error list."""
        errors = validate_annotations_batch([])
        assert errors == []
