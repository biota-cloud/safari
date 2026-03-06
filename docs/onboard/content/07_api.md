# API

> Programmatic access for batch processing, desktop integration, and custom workflows.

---

## API Overview

SAFARI provides a REST API for running inference on your trained models programmatically. Use it for:

- **Batch camera trap processing** — Process hundreds of images automatically
- **SAFARIDesktop integration** — Native desktop client for local video processing
- **Custom scripts** — Integrate wildlife detection into your own pipelines

The API is deployed on Modal as a FastAPI application with built-in Swagger documentation at `/docs`.

### Base URL Structure

All endpoints follow this pattern:

```
https://<your-modal-app>.modal.run/api/v1/...
```

Authentication uses Bearer tokens in the `Authorization` header:

```
Authorization: Bearer safari_xxxx...
```

---

## API Dashboard

Navigate to your project, then click the <span class="icon-btn"><i data-lucide="plug"></i> API</span> tab to open the API management dashboard.

![API dashboard](screenshots/API.png)

The dashboard has three sections:

| Section | Purpose |
|---------|---------|
| **Deployed Models** | Models promoted from training — shows slug, type, backbone, SAM3 config, and request counts |
| **API Keys** | Create and manage authentication tokens |
| **Quick Start** | Code examples to get started |

---

## Creating API Keys

Click <span class="icon-btn"><i data-lucide="plus"></i> New Key</span> in the API Keys section.

![Key creation](screenshots/API_key_creation.png){.compact}

1. Enter a **descriptive name** (e.g., *"Production Key"*, *"Mobile App"*)
2. Click **Create Key**

![Key confirmation](screenshots/API_key_confirmation.png){.compact}

> **Important**: Copy the key immediately — you won't be able to see it again. Keys are prefixed with `safari_` for easy identification.

### Key Scopes

- **Project-scoped** keys can only access models within the project they were created in
- **User-wide** keys can access any model you own across all projects

---

## Endpoints Reference

| Endpoint | Method | Purpose |
|----------|--------|---------|
| `/api/v1/infer/{slug}` | POST | Single image inference |
| `/api/v1/infer/{slug}/batch` | POST | Batch image inference (up to 100 images) |
| `/api/v1/infer/{slug}/video` | POST | Async video inference |
| `/api/v1/jobs/{job_id}` | GET | Poll video job status |
| `/health` | GET | Health check (no auth) |

---

## Single Image Inference

Send an image and get predictions back synchronously:

```bash
curl -X POST \
  -H "Authorization: Bearer safari_xxxx..." \
  -F "file=@camera_trap_001.jpg" \
  "https://<your-app>.modal.run/api/v1/infer/lynx-detector-v2?confidence=0.25"
```

### Parameters

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `file` | file | required | Image file (JPEG, PNG, WebP). Max 50MB |
| `confidence` | float | 0.25 | Confidence threshold (0–1) |

### Response

```json
{
  "model": "lynx-detector-v2",
  "model_type": "detection",
  "predictions": [
    {
      "class_name": "Lince ibérico",
      "class_id": 0,
      "confidence": 0.92,
      "box": [0.12, 0.34, 0.56, 0.78],
      "box_format": "xyxy_normalized"
    }
  ],
  "image_width": 1920,
  "image_height": 1080,
  "inference_time_ms": 245,
  "request_id": "a1b2c3d4-..."
}
```

---

## Batch Image Inference

Process multiple images in a single request. Models are loaded once and reused across all images for optimal throughput:

```bash
curl -X POST \
  -H "Authorization: Bearer safari_xxxx..." \
  -F "files=@image1.jpg" \
  -F "files=@image2.jpg" \
  -F "files=@image3.jpg" \
  "https://<your-app>.modal.run/api/v1/infer/lynx-detector-v2/batch?confidence=0.3"
```

### Limits

| Limit | Value |
|-------|-------|
| Maximum images per batch | 100 |
| Maximum file size per image | 10 MB |

### Response

```json
{
  "model": "lynx-detector-v2",
  "model_type": "detection",
  "results": [
    {
      "index": 0,
      "success": true,
      "predictions": [...],
      "image_width": 1920,
      "image_height": 1080
    },
    ...
  ],
  "total_images": 3,
  "total_predictions": 5,
  "inference_time_ms": 680,
  "request_id": "e5f6g7h8-..."
}
```

---

## Video Inference (Async)

Video processing is asynchronous — submit the video, get a `job_id`, then poll for results:

### 1. Submit Video

```bash
curl -X POST \
  -H "Authorization: Bearer safari_xxxx..." \
  -F "file=@camera_trap.mp4" \
  "https://<your-app>.modal.run/api/v1/infer/lynx-detector-v2/video?confidence=0.25&frame_skip=5"
```

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `file` | file | required | Video file (MP4, MOV, AVI, WebM). Max 500MB |
| `confidence` | float | 0.25 | Confidence threshold |
| `frame_skip` | int | 1 | Process every Nth frame (1 = every frame) |
| `start_time` | float | 0.0 | Start processing from this second |
| `end_time` | float | — | Stop processing at this second |

Response:

```json
{
  "job_id": "d4e5f6a7-...",
  "status": "pending",
  "message": "Video job submitted. Poll /api/v1/jobs/{job_id} for progress."
}
```

### 2. Poll for Progress

```bash
curl -H "Authorization: Bearer safari_xxxx..." \
  "https://<your-app>.modal.run/api/v1/jobs/d4e5f6a7-..."
```

Response while processing:

```json
{
  "job_id": "d4e5f6a7-...",
  "status": "processing",
  "progress": 45,
  "frames_processed": 180,
  "total_frames": 400
}
```

### 3. Get Completed Results

When `status` is `"completed"`, the `result` field contains per-frame predictions:

```json
{
  "job_id": "d4e5f6a7-...",
  "status": "completed",
  "progress": 100,
  "frames_processed": 400,
  "total_frames": 400,
  "result": {
    "predictions_by_frame": {
      "0": [...],
      "5": [...],
      "10": [...]
    }
  }
}
```

---

## Response Schema

### Prediction Object

| Field | Type | Description |
|-------|------|-------------|
| `class_name` | string | Species label (e.g., *"Lince ibérico"*) |
| `class_id` | integer | Class index from training |
| `confidence` | float | Detection confidence (0–1) |
| `box` | [x1, y1, x2, y2] | Normalized bounding box coordinates (0–1) |
| `box_format` | string | Always `"xyxy_normalized"` |

### Classification Models (Hybrid)

When using a classification model, the API automatically runs a **two-stage hybrid pipeline**: SAM3 detects objects first, then your classifier identifies each species. The SAM3 configuration is critical — incorrect settings will produce poor or no results.

These parameters are configured per-model on the API dashboard using the inline <span class="icon-btn icon-only"><i data-lucide="pencil"></i></span> edit controls:

| Setting | Impact | Guidance |
|---------|--------|----------|
| **SAM3 Confidence** | Controls how many objects SAM3 detects. Too high = misses animals. Too low = false positives | Start at 0.25 and tune up if you get too many false boxes |
| **SAM3 Resolution** | Image size for SAM3 inference (490 / 644 / 1036 / 1288 / 1918). Higher = more accurate but slower | Use 644 for speed, 1036+ for dense scenes or small targets |
| **SAM3 Prompt** | Comma-separated object types SAM3 should look for (e.g., *"animal, bird, mammal"*) | Keep prompts broad to avoid missing detections |

> **Tip**: If your classification model returns no results, lower the SAM3 confidence first — the classifier can only classify what SAM3 detects.

---

## Promoting Models to API

From the training page, click <span class="icon-btn outline-green"><i data-lucide="plug"></i> API</span> on a completed run to open the promotion modal:

![API promote modal](screenshots/API_modal.png){.compact}

Configure:
- **API Slug** — URL-safe identifier (e.g., *"lynx-detector-v2"*)
- **Display Name** — Human-readable label
- **Description** — Optional notes

Once promoted, the model appears in the API dashboard and responds to inference requests at its slug endpoint.

---

## SAFARIDesktop

SAFARIDesktop is a native desktop application (built with Tauri) for processing local videos using your SAFARI API models.

1. **Download** SAFARIDesktop for your platform
2. **Configure** your API key in settings
3. **Process** local camera trap videos without uploading to the cloud

Detection results are displayed as interactive overlays on the video with a local results gallery and analytics dashboard.
