"""
Unit tests for backend/core/yolo_infer_core.py

Tests pure YOLO detection functions used by both Modal jobs and remote workers.
"""

import io
import pytest
from PIL import Image
from unittest.mock import MagicMock, patch

from backend.core.yolo_infer_core import (
    parse_yolo_results,
    format_predictions_to_yolo,
    run_yolo_single_inference,
    run_yolo_batch_inference,
)


def create_test_image(width: int = 640, height: int = 480, color: str = "green") -> Image.Image:
    """Create a test PIL Image."""
    return Image.new("RGB", (width, height), color=color)


class MockBoxes:
    """Mock YOLO boxes result."""
    def __init__(self, detections: list[dict]):
        """
        Args:
            detections: List of dicts with keys: xyxy, cls, conf
        """
        self.detections = detections
        
    def __len__(self):
        return len(self.detections)
    
    @property
    def xyxy(self):
        class TensorLike:
            def __init__(self, values):
                self.values = values
            def __getitem__(self, idx):
                class ItemLike:
                    def __init__(self, val):
                        self.val = val
                    def cpu(self):
                        return self
                    def numpy(self):
                        return self
                    def tolist(self):
                        return self.val
                return ItemLike(self.values[idx])
        return TensorLike([d["xyxy"] for d in self.detections])
    
    @property
    def cls(self):
        class TensorLike:
            def __init__(self, values):
                self.values = values
            def __getitem__(self, idx):
                class ItemLike:
                    def __init__(self, val):
                        self.val = val
                    def cpu(self):
                        return self
                    def item(self):
                        return self.val
                return ItemLike(self.values[idx])
        return TensorLike([d["cls"] for d in self.detections])
    
    @property
    def conf(self):
        class TensorLike:
            def __init__(self, values):
                self.values = values
            def __getitem__(self, idx):
                class ItemLike:
                    def __init__(self, val):
                        self.val = val
                    def cpu(self):
                        return self
                    def item(self):
                        return self.val
                return ItemLike(self.values[idx])
        return TensorLike([d["conf"] for d in self.detections])


class MockResult:
    """Mock single YOLO result."""
    def __init__(self, boxes: MockBoxes):
        self.boxes = boxes


class TestParseYoloResults:
    """Tests for parse_yolo_results() function."""
    
    def test_single_detection(self):
        """Test parsing a single detection result."""
        model_names = {0: "person", 1: "car"}
        boxes = MockBoxes([
            {"xyxy": [100, 50, 200, 150], "cls": 0, "conf": 0.95}
        ])
        results = [MockResult(boxes)]
        
        predictions = parse_yolo_results(model_names, results, 640, 480)
        
        assert len(predictions) == 1
        pred = predictions[0]
        assert pred["class_id"] == 0
        assert pred["class_name"] == "person"
        assert pred["confidence"] == 0.95
        # Check normalization: x1=100/640, y1=50/480, x2=200/640, y2=150/480
        assert pred["box"] == pytest.approx([100/640, 50/480, 200/640, 150/480], rel=1e-4)
    
    def test_multiple_detections(self):
        """Test parsing multiple detections."""
        model_names = {0: "person", 1: "car"}
        boxes = MockBoxes([
            {"xyxy": [100, 50, 200, 150], "cls": 0, "conf": 0.95},
            {"xyxy": [300, 200, 500, 400], "cls": 1, "conf": 0.88},
        ])
        results = [MockResult(boxes)]
        
        predictions = parse_yolo_results(model_names, results, 640, 480)
        
        assert len(predictions) == 2
        assert predictions[0]["class_name"] == "person"
        assert predictions[1]["class_name"] == "car"
    
    def test_empty_results(self):
        """Test parsing empty results."""
        model_names = {0: "person"}
        results = []
        
        predictions = parse_yolo_results(model_names, results, 640, 480)
        
        assert predictions == []
    
    def test_no_boxes(self):
        """Test parsing result with no boxes."""
        model_names = {0: "person"}
        mock_result = MagicMock()
        mock_result.boxes = None
        results = [mock_result]
        
        predictions = parse_yolo_results(model_names, results, 640, 480)
        
        assert predictions == []
    
    def test_unknown_class_id(self):
        """Test parsing with unknown class ID uses fallback name."""
        model_names = {0: "person"}
        boxes = MockBoxes([
            {"xyxy": [100, 50, 200, 150], "cls": 99, "conf": 0.90}
        ])
        results = [MockResult(boxes)]
        
        predictions = parse_yolo_results(model_names, results, 640, 480)
        
        assert predictions[0]["class_name"] == "class_99"


class TestFormatPredictionsToYolo:
    """Tests for format_predictions_to_yolo() function."""
    
    def test_single_prediction(self):
        """Test formatting a single prediction."""
        predictions = [{
            "class_id": 0,
            "class_name": "person",
            "confidence": 0.95,
            "box": [0.1, 0.2, 0.3, 0.4],  # xyxy normalized
        }]
        
        labels_txt = format_predictions_to_yolo(predictions, 640, 480)
        
        # Expected: class_id x_center y_center width height
        # x_center = (0.1 + 0.3) / 2 = 0.2
        # y_center = (0.2 + 0.4) / 2 = 0.3
        # width = 0.3 - 0.1 = 0.2
        # height = 0.4 - 0.2 = 0.2
        lines = labels_txt.strip().split("\n")
        assert len(lines) == 1
        parts = lines[0].split()
        assert parts[0] == "0"
        assert float(parts[1]) == pytest.approx(0.2, rel=1e-4)
        assert float(parts[2]) == pytest.approx(0.3, rel=1e-4)
        assert float(parts[3]) == pytest.approx(0.2, rel=1e-4)
        assert float(parts[4]) == pytest.approx(0.2, rel=1e-4)
    
    def test_multiple_predictions(self):
        """Test formatting multiple predictions."""
        predictions = [
            {"class_id": 0, "class_name": "person", "confidence": 0.95, "box": [0.1, 0.1, 0.2, 0.2]},
            {"class_id": 1, "class_name": "car", "confidence": 0.80, "box": [0.5, 0.5, 0.8, 0.8]},
        ]
        
        labels_txt = format_predictions_to_yolo(predictions, 640, 480)
        
        lines = labels_txt.strip().split("\n")
        assert len(lines) == 2
        assert lines[0].startswith("0 ")
        assert lines[1].startswith("1 ")
    
    def test_empty_predictions(self):
        """Test formatting empty predictions."""
        predictions = []
        
        labels_txt = format_predictions_to_yolo(predictions, 640, 480)
        
        assert labels_txt == ""


class TestRunYoloSingleInference:
    """Tests for run_yolo_single_inference() function."""
    
    def test_inference_returns_predictions(self):
        """Test that inference returns predictions and dimensions."""
        mock_model = MagicMock()
        mock_model.names = {0: "test_class"}
        
        # Create mock result with one detection
        boxes = MockBoxes([
            {"xyxy": [100, 50, 200, 150], "cls": 0, "conf": 0.90}
        ])
        mock_model.predict.return_value = [MockResult(boxes)]
        
        image = create_test_image(640, 480)
        
        predictions, width, height = run_yolo_single_inference(mock_model, image, 0.25)
        
        assert width == 640
        assert height == 480
        assert len(predictions) == 1
        assert predictions[0]["class_id"] == 0
        
        mock_model.predict.assert_called_once()
    
    def test_inference_passes_confidence(self):
        """Test that confidence threshold is passed to model."""
        mock_model = MagicMock()
        mock_model.names = {}
        mock_model.predict.return_value = []
        
        image = create_test_image()
        
        run_yolo_single_inference(mock_model, image, 0.75)
        
        mock_model.predict.assert_called_with(image, conf=0.75, verbose=False)


class TestRunYoloBatchInference:
    """Tests for run_yolo_batch_inference() function."""
    
    def test_batch_returns_indexed_results(self):
        """Test that batch returns results with correct indices."""
        mock_model = MagicMock()
        mock_model.names = {0: "test"}
        mock_model.predict.return_value = []
        
        def mock_download(url: str) -> bytes:
            img = create_test_image()
            buf = io.BytesIO()
            img.save(buf, format="JPEG")
            return buf.getvalue()
        
        results = run_yolo_batch_inference(
            mock_model,
            ["url1", "url2", "url3"],
            0.25,
            mock_download,
        )
        
        assert len(results) == 3
        assert results[0]["index"] == 0
        assert results[1]["index"] == 1
        assert results[2]["index"] == 2
    
    def test_batch_handles_errors_gracefully(self):
        """Test that batch continues on individual failures."""
        mock_model = MagicMock()
        mock_model.names = {0: "test"}
        mock_model.predict.return_value = []
        
        call_count = 0
        def mock_download(url: str) -> bytes:
            nonlocal call_count
            call_count += 1
            if call_count == 2:
                raise Exception("Download failed")
            img = create_test_image()
            buf = io.BytesIO()
            img.save(buf, format="JPEG")
            return buf.getvalue()
        
        results = run_yolo_batch_inference(
            mock_model,
            ["url1", "url2", "url3"],
            0.25,
            mock_download,
        )
        
        assert len(results) == 3
        assert "error" not in results[0]
        assert "error" in results[1]
        assert "error" not in results[2]
