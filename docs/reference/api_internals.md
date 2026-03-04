# SAFARI API Internals

> **Purpose**: Technical reference for agents and developers integrating with the SAFARI API.
> This document explains internal routing logic, model types, and processing pipelines.

---

## Model Types & Routing

The API routes requests based on `model_type` stored in the `api_models` table:

| `model_type` | Detection Engine | Classification | Use Case |
|--------------|------------------|----------------|----------|
| `"detection"` | YOLO | N/A | Standard object detection |
| `"classification"` | SAM3 (Segment Anything) | YOLOv11-Classify | Hybrid: detect-then-classify |

### Detection Flow (`model_type: "detection"`)

```
Image/Video → YOLO Model → Bounding Boxes + Classes
```

- Uses the model's trained YOLO weights directly
- Fast inference, single-stage detection

### Hybrid Flow (`model_type: "classification"`)

```
Image/Video → SAM3 (generic "animal" prompt) → Bounding Boxes
            → Crop each detection → YOLOv11-Classify → Species ID
```

- **SAM3** uses open-vocabulary detection with a generic prompt (e.g., "animal")
- Each detection is cropped and sent to a **classifier** for species identification
- Returns both bounding boxes and species classifications

---

## Endpoint-Specific Behavior

### Image Inference (`POST /api/v1/infer/{model_slug}`)

| Model Type | Predictor | Notes |
|------------|-----------|-------|
| `detection` | Standard YOLO | Single-pass inference |
| `classification` | `SAM3SemanticPredictor` + YOLOv11-Classify | Two-stage hybrid |

### Batch Inference (`POST /api/v1/infer/{model_slug}/batch`)

Same routing as image inference, but:
- Models loaded **once** and reused across all images
- Max 100 images, 10MB each
- Designed for high-throughput frame sequences

### Video Inference (`POST /api/v1/infer/{model_slug}/video`)

| Model Type | Predictor | Tracking |
|------------|-----------|----------|
| `detection` | YOLO with `vid_stride` | No temporal tracking |
| `classification` | `SAM3VideoSemanticPredictor` | **Full temporal tracking** |

---

## Video Upload Flow

When a client uploads a video, here's exactly what happens:

```
┌─────────────────────────────────────────────────────────────────┐
│                      SAFARIDesktop Client                          │
│                POST /api/v1/infer/{slug}/video                   │
│              (multipart/form-data with video file)               │
└─────────────────────────────────────────────────────────────────┘
                               │
                               ▼
┌─────────────────────────────────────────────────────────────────┐
│              1. AUTHENTICATION (FastAPI Middleware)              │
│  • Checks "Authorization: Bearer safari_xxxx..." header            │
│  • SHA256 hashes key, looks up in api_keys table                 │
│  • Returns APIKeyData (user_id, project_id, key_id)              │
│  • ❌ Rejects request if auth fails (401/403)                    │
└─────────────────────────────────────────────────────────────────┘
                               │
                               ▼
┌─────────────────────────────────────────────────────────────────┐
│              2. REQUEST HANDLING (inference.py)                  │
│  • Validates model exists and key has access                     │
│  • Reads video into memory: file_content = await file.read()     │
│  • Creates job record in api_jobs table (status: "pending")      │
└─────────────────────────────────────────────────────────────────┘
                               │
                               ▼
┌─────────────────────────────────────────────────────────────────┐
│          3. SPAWN MODAL JOB (async, returns immediately)         │
│  APIInference().process_video_job_hybrid.spawn(                  │
│      video_bytes=file_content,  ◄── VIDEO SENT DIRECTLY          │
│      ...                                                         │
│  )                                                               │
│  Returns job_id to client immediately                            │
└─────────────────────────────────────────────────────────────────┘
                               │
                               ▼
┌─────────────────────────────────────────────────────────────────┐
│            4. MODAL GPU WORKER (api_infer_job.py)                │
│  • Writes video_bytes to temp file on Modal container            │
│  • Runs SAM3VideoSemanticPredictor (or YOLO for detection)       │
│  • Updates job status in Supabase periodically                   │
│  • Stores final results in api_jobs.result_json                  │
└─────────────────────────────────────────────────────────────────┘
```

### Key Points

| Question | Answer |
|----------|--------|
| **Where does video go?** | Directly to Modal GPU worker (NOT R2) |
| **When is auth done?** | Before anything else (FastAPI dependency) |
| **Max video size?** | 500MB (validated in request handler) |
| **Storage used?** | Temp file on Modal container only |

> **Note:** Video bytes are passed directly via Modal's `.spawn()` function call.
> For very large videos (>500MB), consider uploading to R2 first and passing a URL.

---

## SAM3 Video Processing Details

When `model_type: "classification"`, video uses `SAM3VideoSemanticPredictor`:

### How It Works

1. **SAM3 processes ALL frames** with memory-based temporal tracking
2. Each unique **track_id** is classified using **Quality-Diverse Top-K** — K diverse high-quality frames are selected and classified, then majority-voted for the final species label
3. Classifications are **propagated** to all frames where that track appears
4. `frame_skip` parameter only **filters output** — it does NOT skip SAM3 processing

### Performance Implications

| Parameter | Effect on SAM3 | Effect on Output |
|-----------|----------------|------------------|
| `frame_skip=1` | Process all frames | Return all frames |
| `frame_skip=5` | Process all frames | Return every 5th frame |

> **Why?** SAM3's temporal memory requires sequential frame processing for accurate tracking.
> Skipping input frames would break tracking consistency.

---

## Confidence Thresholds

Two separate thresholds are used in hybrid mode:

| Threshold | Controlled By | Purpose |
|-----------|---------------|---------|
| `sam3_confidence` | Model config in DB | SAM3 detection sensitivity |
| `confidence` | API request param | Classifier output filtering |

Example: A model with `sam3_confidence=0.25` will detect more potential animals,
but only those classified with `confidence >= 0.25` appear in results.

---

## Response Schema Notes

### `model_type` Field

The response includes `model_type` to help clients understand which pipeline was used:

```json
{
  "model": "lynx-detector-v2",
  "model_type": "classification",  // "classification" = hybrid SAM3 + classifier
  "predictions": [...]
}
```

### Video Results Structure

For video endpoints, completed jobs return:

```json
{
  "frame_results": [
    {
      "frame_number": 0,
      "timestamp": 0.0,
      "predictions": [
        {
          "class_name": "Lynx_pardinus",
          "confidence": 0.95,
          "box": [0.1, 0.2, 0.3, 0.4],
          "track_id": 1  // Consistent across frames for same object
        }
      ]
    }
  ],
  "unique_tracks": 5,
  "classified_tracks": 4
}
```

---

## For SAFARIDesktop Integration

### Recommended Client Patterns

1. **Check `model_type` in responses** to understand pipeline used
2. **Use batch endpoint** for frame sequences (reduces cold start overhead)
3. **Poll job status** for video inference — these are async
4. **Trust `track_id`** for temporal consistency in video results

### Frame Extraction Guidance

When extracting frames client-side for batch inference:
- Match the Playground's **native resolution** (no scaling distortion)
- Use **1024px width** with aspect ratio preserved for optimal SAM3 detection
- Send frames in **original order** for result correlation

---

## Related Files

- `backend/api/routes/inference.py` — API endpoint routing logic
- `backend/modal_jobs/api_infer_job.py` — GPU inference implementations
- `docs/openapi.json` — OpenAPI specification
