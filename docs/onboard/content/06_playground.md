# Model Playground

> Test your trained models on new images and video before deploying.

---

## Playground Overview

From the main dashboard, click the <span class="icon-btn"><i data-lucide="zap"></i> Playground</span> card to open the inference playground.

![Playground card on dashboard](screenshots/Main_dash_inference_playground_card.png){.compact}

The playground lets you upload images or video, run inference with any model, and view results instantly.

![Playground overview](screenshots/Inference_playground.png)

The interface has three areas:

| Area | Purpose |
|------|---------|
| **Model Selector** | Choose which model to run |
| **Upload Zone** | Drag-and-drop images or video |
| **Results Gallery** | View and compare inference results |

---

## Selecting a Model

Click the model selector to open the dropdown. Models are grouped by project and show detailed metadata:

![Model dropdown](screenshots/Inference_playground_model_dropdown.png)

Each model card displays:
- **Alias** — The name you gave the training run
- **Weights badge** — <span class="icon-btn" style="font-size:11px">best</span> or <span class="icon-btn" style="font-size:11px">last</span> checkpoint
- **Type badge** — Detection (🎯 Det) or Classification (🏷 Cls)
- **Backbone badge** — YOLO or CNX (ConvNeXt)
- **Metric** — mAP score for detection, accuracy for classification

Use the search bar to filter models by name or project.

### Built-in Models

A collapsible section at the bottom offers pre-trained YOLO11 models for quick testing:

| Model | Size | Speed |
|-------|------|-------|
| **yolo11n.pt** | Nano | Fastest |
| **yolo11s.pt** | Small | Balanced (default) |
| **yolo11m.pt** | Medium | Most accurate |

---

## Configuring Settings

Below the model selector, the settings panel controls inference behavior:

![Playground settings](screenshots/Inference_playground_card_settings.png)

### Core Settings

| Setting | Default | Description |
|---------|---------|-------------|
| **Confidence Threshold** | 25% | Minimum confidence to display a detection. Raise to reduce false positives |
| **SAM3 Resolution** | 644 | Image resolution for SAM3 inference (490 / 644 / 1036 / 1288 / 1918). Higher = more accurate but slower |
| **SAM3 Model** | Pretrained (Meta) | Choose between pre-trained SAM3 or your fine-tuned checkpoints |

### Video Settings

| Setting | Default | Description |
|---------|---------|-------------|
| **Target Resolution** | 644 | Resize video before upload (490 / 644 / 1036 / 1288 / 1918) |
| **Target FPS** | Original | Downsample video framerate (original / 30 / 15 / 10) |

### Hybrid Mode (SAM3 + Classifier)

When you select a classification model, **hybrid mode** enables automatically. SAM3 detects objects and crops them, then your classifier identifies the species:

| Setting | Description |
|---------|-------------|
| **SAM3 Prompts** | Comma-separated concept nouns SAM3 should detect (e.g., *"mammal, bird"*) |
| **Classifier Confidence** | Minimum classifier confidence to accept a classification |
| **Top-K** | Number of frames per track for classification voting (video only) |

### Compute Target

Choose where inference runs:
- <span class="icon-btn"><i data-lucide="cloud"></i> Cloud</span> — Modal GPU infrastructure
- <span class="icon-btn"><i data-lucide="monitor"></i> Local GPU</span> — Your connected GPU machine

---

## Running Inference

### Single Image

Drag and drop an image (or click to browse). The playground uploads to R2 storage and runs inference immediately. Results appear as bounding box overlays on the image.

### Batch Images

Drop multiple images at once. A progress bar tracks processing across all images. Navigate between results using the batch viewer.

### Video

Upload a video file — the playground extracts metadata (duration, FPS, frame count) and shows a preview. Click <span class="icon-btn solid-green"><i data-lucide="play"></i> Run Inference</span> to start processing. Video inference runs asynchronously with real-time progress updates.

---

## Understanding Results

![Inference results](screenshots/Inference_playground_results.png){.compact}

### Bounding Boxes

Each detection is drawn on the image with:
- A **colored bounding box** around the detected object
- A **class label** (e.g., *"Lince ibérico"*)
- A **confidence percentage** (e.g., *87%*)

### Mask Polygons

When SAM3 models generate segmentation masks, semi-transparent polygon overlays highlight the exact shape of each detection. Toggle mask visibility with the <span class="icon-btn icon-only"><i data-lucide="eye"></i></span> button.

### Results Gallery

All inference results are saved and appear in the collapsible <span class="icon-btn"><i data-lucide="history"></i> Results</span> section. Each card shows:
- Input filename and thumbnail
- Model used
- Detection count
- Input type (image / batch / video)

Click any result card to reopen the preview with full overlays.

---

## Video Results

Video results open in a dedicated player with frame-by-frame navigation:
- **Playback controls** — Play/pause, seek through frames
- **Bounding box overlays** — Detections rendered on each frame in real time
- **Mask overlays** — SAM3 segmentation masks drawn per frame (toggleable)

### Classification Crops Gallery

When using hybrid mode (SAM3 + Classifier) on video, a **crop gallery** appears below the player showing the Top-K classification candidates for each tracked object — the cropped evidence images that the classifier used to identify each species.

---

## Preview Modal

Click any result in the gallery to open the preview modal:

![Preview](screenshots/Inference_playground_preview.png)

- **Single image**: Full-resolution view with bounding boxes and optional mask overlays
- **Batch**: Navigate between images with <span class="icon-btn icon-only"><i data-lucide="chevron-left"></i></span> / <span class="icon-btn icon-only"><i data-lucide="chevron-right"></i></span> arrows
- **Video**: Embedded player with frame-by-frame overlays and playback controls

Delete a result by clicking <span class="icon-btn icon-only"><i data-lucide="trash-2"></i></span> on the result card.
