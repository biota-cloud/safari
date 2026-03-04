# Video Annotation Rendering — Efficient Canvas Overlay Pattern

> **Purpose**: Document the zero-lag annotation rendering solution used in the SAFARI Inference Playground for real-time bounding box and mask visualization during video playback.

---

## Design Philosophy

The core insight is **separation of concerns**: video decoding is handled by the browser's native `<video>` element (hardware-accelerated), while annotations are rendered on a transparent `<canvas>` overlay. This avoids the expensive operation of "burning in" labels during video encoding.

### Key Benefits
1. **Zero re-encoding cost** — Labels stored as JSON, not burned into video pixels
2. **Instant updates** — Change confidence thresholds, colors, or visibility without re-processing
3. **GPU-accelerated playback** — Native video element uses hardware decoding
4. **Smooth 60fps overlays** — `requestAnimationFrame` syncs canvas to display refresh

---

## Architecture Overview

```
┌─────────────────────────────────────────────────┐
│              Container (position: relative)      │
│  ┌─────────────────────────────────────────┐    │
│  │   <video id="inference-video">          │    │
│  │   • Native controls                     │    │
│  │   • Hardware-decoded playback           │    │
│  └─────────────────────────────────────────┘    │
│  ┌─────────────────────────────────────────┐    │
│  │   <canvas id="inference-canvas">        │    │
│  │   • position: absolute (overlay)        │    │
│  │   • pointer-events: none (click-through)│    │
│  │   • Synced to video.currentTime         │    │
│  └─────────────────────────────────────────┘    │
└─────────────────────────────────────────────────┘
```

---

## Data Structure

Annotations are pre-indexed by frame number for O(1) lookup:

```javascript
// Frame-indexed label dictionary (from API response)
const labelsByFrame = {
    0: [
        { box: [0.12, 0.34, 0.45, 0.67], class_name: "deer", class_id: 0, confidence: 0.92 },
        { box: [0.55, 0.20, 0.80, 0.60], class_name: "bird", class_id: 1, confidence: 0.87 }
    ],
    15: [...],  // Frame 15 detections
    30: [...]   // Frame 30 detections
};

// Optional mask polygons (same structure)
const masksByFrame = {
    0: [
        { polygon: [[0.1, 0.2], [0.3, 0.4], ...], class_id: 0 }
    ]
};
```

> **Critical**: Box coordinates are **normalized (0-1 range)**, not pixel coordinates. This allows resolution-independent storage and rendering at any display size.

---

## Rendering Pipeline

### 1. Canvas Setup

The canvas must exactly overlay the video's **rendered area** (accounting for letterboxing):

```javascript
function updateCanvasSize() {
    const videoRect = video.getBoundingClientRect();
    
    // Match canvas to video display size (not native resolution)
    canvas.width = Math.floor(videoRect.width);
    canvas.height = Math.floor(videoRect.height);
    
    // Calculate letterbox/pillarbox offsets
    const videoAspect = video.videoWidth / video.videoHeight;
    const canvasAspect = canvas.width / canvas.height;
    
    if (videoAspect > canvasAspect) {
        // Letterboxed (horizontal bars)
        renderWidth = canvas.width;
        renderHeight = canvas.width / videoAspect;
        offsetX = 0;
        offsetY = (canvas.height - renderHeight) / 2;
    } else {
        // Pillarboxed (vertical bars)
        renderWidth = canvas.height * videoAspect;
        renderHeight = canvas.height;
        offsetX = (canvas.width - renderWidth) / 2;
        offsetY = 0;
    }
}
```

### 2. Frame Calculation

Convert video `currentTime` to frame index using stored FPS:

```javascript
const currentFrame = Math.floor(video.currentTime * fps);
const labels = labelsByFrame[currentFrame] || [];
```

### 3. Coordinate Transformation

Transform normalized `[0,1]` coordinates to pixel coordinates with letterbox offset:

```javascript
// label.box = [x1, y1, x2, y2] in normalized coords
const [x1, y1, x2, y2] = label.box;

// Transform to canvas pixels
const x = offsetX + (x1 * renderWidth);
const y = offsetY + (y1 * renderHeight);
const w = (x2 - x1) * renderWidth;
const h = (y2 - y1) * renderHeight;

ctx.strokeRect(x, y, w, h);
```

### 4. Animation Loop (Smooth Playback)

Use `requestAnimationFrame` for buttery-smooth overlay updates:

```javascript
function onPlay() {
    startAnimationLoop();
}

function startAnimationLoop() {
    if (animationFrameId) return; // Already running
    
    function animate() {
        drawLabels();
        animationFrameId = requestAnimationFrame(animate);
    }
    animationFrameId = requestAnimationFrame(animate);
}

function stopAnimationLoop() {
    if (animationFrameId) {
        cancelAnimationFrame(animationFrameId);
        animationFrameId = null;
    }
    drawLabels(); // Final frame for paused state
}
```

> **Why not `timeupdate`?** The `timeupdate` event fires at ~4Hz (250ms intervals), causing visible lag. `requestAnimationFrame` syncs to display refresh (60Hz+).

---

## Visual Rendering

### Bounding Boxes

```javascript
// Color by class (consistent across frames)
const hue = (label.class_id * 137) % 360;  // Golden angle distribution
const color = `hsl(${hue}, 70%, 50%)`;

ctx.strokeStyle = color;
ctx.lineWidth = 3;
ctx.strokeRect(x, y, w, h);

// Label background + text
ctx.fillStyle = 'rgba(0, 0, 0, 0.7)';
ctx.fillRect(x, y - 24, textWidth + 8, 20);
ctx.fillStyle = '#FFFFFF';
ctx.fillText(`${label.class_name} ${(label.confidence * 100).toFixed(0)}%`, x + 4, y - 8);
```

### Segmentation Masks (Optional)

```javascript
if (showMasks && masks.length > 0) {
    masks.forEach((mask) => {
        ctx.beginPath();
        mask.polygon.forEach((point, i) => {
            const px = offsetX + (point[0] * renderWidth);
            const py = offsetY + (point[1] * renderHeight);
            i === 0 ? ctx.moveTo(px, py) : ctx.lineTo(px, py);
        });
        ctx.closePath();
        ctx.fillStyle = `hsla(${hue}, 70%, 50%, 0.35)`;
        ctx.fill();
        ctx.stroke();
    });
}
```

---

## Event Handling

```javascript
video.addEventListener('loadedmetadata', () => {
    updateCanvasSize();
    drawLabels();  // Render first frame
});

video.addEventListener('play', startAnimationLoop);
video.addEventListener('pause', stopAnimationLoop);
video.addEventListener('seeked', drawLabels);  // User scrubbed

window.addEventListener('resize', debounce(() => {
    updateCanvasSize();
    drawLabels();
}, 100));
```

---

## API Surface

Global functions exposed for framework integration:

| Function | Purpose |
|----------|---------|
| `loadInferenceVideo(url)` | Load video source |
| `setInferenceLabels(data)` | Load frame→labels dictionary |
| `setInferenceMasks(data)` | Load frame→masks dictionary |
| `setInferenceFps(fps)` | Set FPS for frame calculation |
| `toggleInferencePlayback(play)` | Play/pause control |
| `stepInferenceFrame(delta)` | Frame-by-frame navigation |
| `setInferencePlaybackSpeed(rate)` | Speed control (0.25x–2x) |
| `setMasksVisible(bool)` | Toggle mask overlay |
| `cleanupInferencePlayer()` | Cleanup on modal close |

---

## Performance Characteristics

| Metric | Value |
|--------|-------|
| Frame lookup | O(1) dictionary access |
| Render overhead | ~0.5ms per frame (typical) |
| Memory footprint | Labels as JSON (~10KB/1000 frames) |
| Canvas operations | Hardware-accelerated (2D context) |

---

## Critical Gotchas

1. **CORS for presigned URLs**: Set `video.crossOrigin = 'anonymous'` **before** setting `src`, or canvas becomes tainted.

2. **Canvas resolution**: Set `canvas.width/height` to **display size**, not video native resolution. Otherwise, annotations appear offset or scaled incorrectly.

3. **Letterboxing math**: Always account for `object-fit: contain` letterboxing when transforming coordinates.

4. **DOM lifecycle**: Re-initialize when modal opens/closes — cached element references become stale after React/Reflex re-renders.
