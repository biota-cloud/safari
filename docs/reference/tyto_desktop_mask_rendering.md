# SAFARIDesktop: API Payload Handling & Mask Rendering Guide

> Implementation reference for rendering SAM3 mask polygons from SAFARI API inference responses.

---

## 1. API Payload Structure

All hybrid (classification) models return predictions with **mask polygons by default**. SAFARIDesktop should handle all payload variants with a single, robust parser.

### Image Inference Response (`POST /api/v1/infer/{slug}`)

```json
{
  "predictions": [
    {
      "class_name": "Lynx",
      "class_id": 3,
      "confidence": 0.9245,
      "box": [0.123, 0.456, 0.789, 0.901],
      "mask_polygon": [[0.15, 0.42], [0.18, 0.39], [0.22, 0.41], ...]
    }
  ],
  "image_width": 1920,
  "image_height": 1080,
  "model_type": "classification",
  "sam3_detections": 2
}
```

### Video Inference Response (`GET /api/v1/jobs/{id}`)

```json
{
  "status": "completed",
  "result": {
    "frame_results": [
      {
        "frame_number": 0,
        "timestamp": 0.0,
        "predictions": [
          {
            "class_name": "Fox",
            "class_id": 1,
            "confidence": 0.87,
            "box": [0.2, 0.3, 0.6, 0.8],
            "mask_polygon": [[0.21, 0.31], [0.25, 0.28], ...],
            "track_id": 42
          }
        ]
      }
    ],
    "fps": 29.97,
    "video_width": 1920,
    "video_height": 1080
  }
}
```

### Key Fields

| Field | Type | Present When | Description |
|-------|------|--------------|-------------|
| `box` | `[x1, y1, x2, y2]` | Always | Normalized 0-1 bounding box (xyxy) |
| `mask_polygon` | `[[x,y], ...]` or `null` | Hybrid models | Normalized 0-1 polygon points |
| `track_id` | `integer` | Video only | Object tracking ID across frames |
| `model_type` | `"detection"` or `"classification"` | Always | Pipeline used |

> **Rule**: Always check if `mask_polygon` exists and has ≥3 points before rendering.

---

## 2. Coordinate System

All coordinates are **normalized (0-1)** relative to the source media dimensions. This ensures the data works at any display resolution.

```
Normalized → Pixel Transformation:
  pixel_x = normalized_x * display_width
  pixel_y = normalized_y * display_height
```

### Letterbox Correction

When the video aspect ratio doesn't match the display container, black bars appear. Coordinates must map to the **active video area**, not the full canvas.

```typescript
// Step 1: Calculate aspect ratios
const videoAspect = videoWidth / videoHeight;
const canvasAspect = canvasWidth / canvasHeight;

let renderWidth, renderHeight, offsetX = 0, offsetY = 0;

// Step 2: Determine letterbox/pillarbox
if (videoAspect > canvasAspect) {
    // Video wider than canvas → Letterboxed (bars top/bottom)
    renderWidth = canvasWidth;
    renderHeight = canvasWidth / videoAspect;
    offsetY = (canvasHeight - renderHeight) / 2;
} else {
    // Video taller than canvas → Pillarboxed (bars left/right)
    renderWidth = canvasHeight * videoAspect;
    renderHeight = canvasHeight;
    offsetX = (canvasWidth - renderWidth) / 2;
}

// Step 3: Transform normalized → pixel
function toPixel(normX: number, normY: number): [number, number] {
    return [
        offsetX + normX * renderWidth,
        offsetY + normY * renderHeight
    ];
}
```

---

## 3. Rendering Masks (Canvas 2D)

Direct port from SAFARI's `inference_player.js` (lines 354-383):

```typescript
interface MaskData {
    class_id: number;
    polygon: [number, number][];  // [[x, y], ...]
}

function drawMask(ctx: CanvasRenderingContext2D, mask: MaskData) {
    // Skip invalid polygons
    if (!mask.polygon || mask.polygon.length < 3) return;
    
    // Generate class-based color (deterministic hue)
    const hue = (mask.class_id * 137) % 360;
    
    // Draw filled polygon
    ctx.beginPath();
    const [startX, startY] = toPixel(mask.polygon[0][0], mask.polygon[0][1]);
    ctx.moveTo(startX, startY);
    
    for (let i = 1; i < mask.polygon.length; i++) {
        const [px, py] = toPixel(mask.polygon[i][0], mask.polygon[i][1]);
        ctx.lineTo(px, py);
    }
    
    ctx.closePath();
    
    // Semi-transparent fill
    ctx.fillStyle = `hsla(${hue}, 70%, 50%, 0.35)`;
    ctx.fill();
    
    // Solid outline
    ctx.strokeStyle = `hsl(${hue}, 70%, 50%)`;
    ctx.lineWidth = 1;
    ctx.stroke();
}
```

### Draw Order

1. **Masks first** (background layer)
2. **Bounding boxes second** (mid layer)
3. **Labels third** (foreground layer)

```typescript
function drawFrame(frameNumber: number) {
    ctx.clearRect(0, 0, canvas.width, canvas.height);
    
    const predictions = predictionsByFrame[frameNumber] || [];
    
    // Layer 1: Masks
    predictions.forEach(pred => {
        if (pred.mask_polygon) {
            drawMask(ctx, { class_id: pred.class_id, polygon: pred.mask_polygon });
        }
    });
    
    // Layer 2: Bounding boxes
    predictions.forEach(pred => drawBoundingBox(ctx, pred));
    
    // Layer 3: Labels
    predictions.forEach(pred => drawLabel(ctx, pred));
}
```

---

## 4. Video Playback Sync (60Hz RAF Loop)

For smooth overlay rendering during video playback:

```typescript
let animationFrameId: number | null = null;
let lastRenderedFrame = -1;

function startOverlayLoop() {
    if (animationFrameId !== null) return;
    
    function animate() {
        const currentFrame = Math.floor(video.currentTime * fps);
        
        // Only redraw when frame changes (optimization)
        if (currentFrame !== lastRenderedFrame) {
            lastRenderedFrame = currentFrame;
            drawFrame(currentFrame);
        }
        
        animationFrameId = requestAnimationFrame(animate);
    }
    
    animationFrameId = requestAnimationFrame(animate);
}

function stopOverlayLoop() {
    if (animationFrameId !== null) {
        cancelAnimationFrame(animationFrameId);
        animationFrameId = null;
    }
}

// Bind to video events
video.addEventListener('play', startOverlayLoop);
video.addEventListener('pause', stopOverlayLoop);
video.addEventListener('seeked', () => drawFrame(Math.floor(video.currentTime * fps)));
```

---

## 5. Universal Payload Parser

SAFARIDesktop should use **one parser** for all model types:

```typescript
interface Prediction {
    class_name: string;
    class_id: number;
    confidence: number;
    box: [number, number, number, number];  // Always present
    mask_polygon?: [number, number][];      // Hybrid only
    track_id?: number;                      // Video only
}

function parsePredictions(apiResponse: any): Map<number, Prediction[]> {
    const byFrame = new Map<number, Prediction[]>();
    
    // Handle image response (single frame)
    if (apiResponse.predictions) {
        byFrame.set(0, apiResponse.predictions);
        return byFrame;
    }
    
    // Handle video response (multiple frames)
    if (apiResponse.result?.frame_results) {
        for (const frame of apiResponse.result.frame_results) {
            byFrame.set(frame.frame_number, frame.predictions);
        }
    }
    
    return byFrame;
}
```

---

## 6. Implementation Checklist

SAFARIDesktop agent should:

- [ ] **Parse `mask_polygon`** as optional field from every prediction
- [ ] **Check polygon validity** (`polygon.length >= 3`) before drawing
- [ ] **Implement letterbox correction** using cached render dimensions
- [ ] **Use RAF loop** for video playback (not `timeupdate` events)
- [ ] **Draw masks before boxes** for correct layer order
- [ ] **Use class-based HSL colors** for visual consistency: `hue = (class_id * 137) % 360`
- [ ] **Handle both model types** with one code path (detection doesn't have masks, just skip)

---

## 7. Reference: SAFARI Source Files

| File | Purpose |
|------|---------|
| [inference_player.js](file:///Users/jorge/PycharmProjects/Tyto/assets/inference_player.js) | Complete JS implementation (masks lines 354-383) |
| [thumbnail_generator.py](file:///Users/jorge/PycharmProjects/Tyto/backend/core/thumbnail_generator.py) | Python OpenCV mask overlay patterns |
| [coordinate_transformations.md](file:///Users/jorge/.gemini/antigravity/knowledge/video_annotation_rendering_patterns/artifacts/implementation/coordinate_transformations.md) | Canvas sizing and letterbox math |
| [openapi.json](file:///Users/jorge/PycharmProjects/Tyto/docs/openapi.json) | Full API schema with mask types |
