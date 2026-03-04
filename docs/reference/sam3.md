

```markdown
# SAM 3: Segment Anything with Concepts (Ultralytics Implementation)

**Version:** Ultralytics v8.3.237+
**Model Weights:** `sam3.pt` (Requires manual download via Hugging Face access request)

## 1. System Overview
SAM 3 (Segment Anything Model 3) extends the capabilities of SAM 2 by introducing **Promptable Concept Segmentation (PCS)**. Unlike previous versions that segment single objects based on geometric prompts, SAM 3 detects, segments, and tracks **all instances** of a visual concept specified by text or image exemplars.

### Key Capabilities
* **Open-Vocabulary Segmentation:** Segment objects using simple noun phrases (e.g., "yellow school bus") without specific training.
* **Global Instance Detection:** Finds *every* occurrence of a concept in an image or video, not just a single instance.
* **Exemplar-Based Refinement:** Accepts bounding boxes as "examples" to find all visually similar objects in the scene.
* **Video Tracking:** Tracks concepts across frames using memory-based segmentation (inherited from SAM 2).

### Architecture & Logic
* **Decoupled Recognition/Localization:** Uses a "Presence Head" to predict global concept presence ("what") and a separate decoder for localization ("where").
* **Unified Interface:** Supports both **PCS** (Concept prompts) and **PVS** (Visual prompts like clicks/boxes for single objects).
* **Data Engine:** Trained on the SA-Co dataset (5.2M images, 52.5K videos, 4M+ unique noun phrases).

---

## 2. Installation & Model Weights
**Crucial Step:** Unlike standard YOLO models, SAM 3 weights are **not** auto-downloaded.

1.  **Install Package:**
    ```bash
    pip install -U ultralytics
    ```
2.  **Get Weights:**
    * Model is available in modal volume named sam3-volume

---

## 3. Code Reference: Image Segmentation

### A. Text-based Concept Segmentation
Use `SAM3SemanticPredictor` to find all instances matching a text description.

```python
from ultralytics.models.sam import SAM3SemanticPredictor

# Configuration
overrides = dict(
    conf=0.25,
    task="segment",
    mode="predict",
    model="sam3.pt", # Path to downloaded weights
    half=True,       # FP16 for speed
    save=True,
)

predictor = SAM3SemanticPredictor(overrides=overrides)

# 1. Set Image
predictor.set_image("path/to/image.jpg")

# 2. Query with Text Prompts
# Find multiple concepts simultaneously
results = predictor(text=["person", "bus", "glasses"])

# Find concepts with descriptive attributes
results_desc = predictor(text=["person with red cloth", "person with blue cloth"])

# Find single concept
results_single = predictor(text=["a person"])

```

### B. Image Exemplar-based Segmentation

Use a bounding box as a "prototype" to find all similar objects in the image.

```python
from ultralytics.models.sam import SAM3SemanticPredictor

overrides = dict(conf=0.25, task="segment", mode="predict", model="sam3.pt", half=True, save=True)
predictor = SAM3SemanticPredictor(overrides=overrides)

predictor.set_image("path/to/image.jpg")

# Provide a bounding box [x1, y1, x2, y2] as an example.
# The model will segment ALL objects that look like the object in this box.
results = predictor(bboxes=[[480.0, 290.0, 590.0, 650.0]])

# Using multiple exemplar boxes for different concepts
results = predictor(bboxes=[[539, 599, 589, 639], [343, 267, 499, 662]])

```

### C. Efficiency: Feature Caching

Extract image features once and reuse them for multiple queries (text or exemplar).

```python
import cv2
from ultralytics.models.sam import SAM3SemanticPredictor

# Initialize
overrides = dict(conf=0.50, task="segment", mode="predict", model="sam3.pt")
predictor = SAM3SemanticPredictor(overrides=overrides)
predictor2 = SAM3SemanticPredictor(overrides=overrides)

# Load image and set on first predictor
source = "path/to/image.jpg"
predictor.set_image(source)
src_shape = cv2.imread(source).shape[:2]

# Setup second predictor
predictor2.setup_model()

# Reuse features from predictor 1 for a text query on predictor 2
masks_text, boxes_text = predictor2.inference_features(
    predictor.features, 
    src_shape=src_shape, 
    text=["person"]
)

# Reuse features for a box exemplar query
masks_box, boxes_box = predictor2.inference_features(
    predictor.features, 
    src_shape=src_shape, 
    bboxes=[[439, 437, 524, 709]]
)

```

---

## 4. Code Reference: Video Tracking

### A. Track via Text Prompts (Semantic)

Use `SAM3VideoSemanticPredictor` to detect and track specific concepts across frames.

```python
from ultralytics.models.sam import SAM3VideoSemanticPredictor

overrides = dict(conf=0.25, task="segment", mode="predict", imgsz=640, model="sam3.pt", half=True)
predictor = SAM3VideoSemanticPredictor(overrides=overrides)

# Track all instances of 'person' and 'bicycle'
results = predictor(source="path/to/video.mp4", text=["person", "bicycle"], stream=True)

for r in results:
    r.show() 

```

### B. Track via Visual Prompts (Bounding Box)

Use `SAM3VideoPredictor` to track specific objects defined by initial bounding boxes.

```python
from ultralytics.models.sam import SAM3VideoPredictor

overrides = dict(conf=0.25, task="segment", mode="predict", model="sam3.pt", half=True)
predictor = SAM3VideoPredictor(overrides=overrides)

# Track objects initialized by these boxes
results = predictor(
    source="path/to/video.mp4", 
    bboxes=[[706.5, 442.5, 905.25, 555], [598, 635, 725, 750]], 
    stream=True
)

for r in results:
    r.show()

```

---

## 5. Backward Compatibility (SAM 2 Style)

SAM 3 can function exactly like SAM 2 for **Promptable Visual Segmentation (PVS)** (segmenting a *single* specific object based on a click or box).

**Note:** Use the standard `SAM` class for this, not the `SemanticPredictor`.

```python
from ultralytics import SAM

model = SAM("sam3.pt")

# Point prompt: Segment specific object at x=900, y=370
results = model.predict(source="path/to/image.jpg", points=[900, 370], labels=[1])

# Box prompt: Segment specific object within box
results = model.predict(source="path/to/image.jpg", bboxes=[100, 150, 300, 400])

```

---

## 6. Model Selection Guide

| Requirement | Recommended Model | Why? |
| --- | --- | --- |
| **Open-Vocabulary / Unknown Categories** | **SAM 3** | Can find "yellow bus" or "striped cat" via text without training. |
| **Find ALL instances** | **SAM 3** | Designed to find every occurrence of a concept globally. |
| **Interactive Single Object** | **SAM 2** | Better optimized for "click-to-segment" workflows (PVS). |
| **Real-Time / Production Edge** | **YOLO11** | Significantly faster (2ms vs 30ms) and smaller (5MB vs 3.4GB). |
| **Complex Reasoning** | **SAM 3 + MLLM** | Use an LLM to parse complex logic ("person not holding box") into simple noun phrases for SAM 3. |

```

```