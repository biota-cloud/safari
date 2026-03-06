# Video Labeling

> Annotate video footage using the keyframe-based labeling workflow.

---

## Video Editor Overview

The video editor shares the same three-panel layout as the image editor, with additional video-specific controls.

![Video editor layout](screenshots/Video_editor.png)

| Panel | Contents |
|-------|----------|
| **Left Sidebar** | Video list with thumbnails, frame counts, and label counts |
| **Center** | Video canvas with annotation overlay, playback controls, timeline, and keyframe panel |
| **Right Sidebar** | Tool buttons, class list, annotations for the current keyframe |

The left sidebar shows all videos in the dataset. Click a video to load it. The current video is highlighted with a green border.

---

## Video Player Controls

Below the canvas, the playback controls let you navigate through the video frame by frame.

### Transport Buttons

| Button | Shortcut | Action |
|--------|----------|--------|
| <span class="icon-btn icon-only"><i data-lucide="chevrons-left"></i></span> | **Shift+Z** | Back 10 frames |
| <span class="icon-btn icon-only"><i data-lucide="chevron-left"></i></span> | **Z** | Previous frame |
| <span class="icon-btn icon-only"><i data-lucide="play"></i></span> / <span class="icon-btn icon-only"><i data-lucide="pause"></i></span> | **Space** | Play / Pause |
| <span class="icon-btn icon-only"><i data-lucide="chevron-right"></i></span> | **C** | Next frame |
| <span class="icon-btn icon-only"><i data-lucide="chevrons-right"></i></span> | **Shift+C** | Forward 10 frames |

### Timeline

The timeline slider shows your position in the video. Drag it to scrub to any frame. Above the slider:

- **Green markers** — keyframes that have annotations
- **Gray markers** — keyframes marked but still empty (negative samples or pending annotation)
- **Green overlay** — shows the interval selection range (when using interval keyframe creation)

A frame counter is displayed between the transport buttons (e.g., "Frame 342 / 1200").

---

## The Keyframe System

Videos are labeled using **keyframes** — specific frames you mark for annotation. This is more efficient than labeling every frame, since consecutive frames often contain the same subjects.

### Marking Keyframes

- Navigate to the frame you want to annotate
- Press **K** or click <span class="icon-btn"><i data-lucide="bookmark"></i> Mark Keyframe</span> in the controls bar
- The frame is registered as a keyframe and appears in the keyframe panel below the timeline

### Keyframe Panel

The keyframe panel sits below the video controls and shows all keyframes for the current video:

- Each row shows the frame number, label count (or "empty" badge), and a jump-to button
- Click a row to navigate to that keyframe and start annotating
- Use checkboxes to select multiple keyframes for bulk deletion

### Interval Keyframe Creation

For systematic labeling, you can automatically create keyframes at regular intervals:

1. Set the **step size** (e.g., every 30 frames) in the interval input field
2. Navigate to the start position and press **I** (or click <span class="icon-btn icon-only solid-blue"><i data-lucide="skip-back"></i></span>)
3. Navigate to the end position and press **O** (or click <span class="icon-btn icon-only solid-blue"><i data-lucide="skip-forward"></i></span>)
4. A green overlay appears on the timeline showing the selected range
5. The badge shows how many keyframes will be created (e.g., "+12")
6. Press **P** (or click <span class="icon-btn icon-only solid-green"><i data-lucide="zap"></i></span>) to create all interval keyframes at once

### Navigating Between Keyframes

| Key | Action |
|-----|--------|
| **Q** | Jump to previous keyframe |
| **E** | Jump to next keyframe |

---

## Annotating Keyframes

When you navigate to a keyframe, the header shows an **"Editing Keyframe"** badge and the annotation tools become active. On non-keyframe frames, the badge shows **"Live Preview"** — you can see existing annotations but not edit.

The annotation tools are identical to the image editor:

- <span class="icon-btn solid-blue"><i data-lucide="mouse-pointer-2"></i> Select</span> (V) — click to select, drag to move, resize via corner handles
- <span class="icon-btn solid-blue"><i data-lucide="square"></i> Draw</span> (R) — click and drag to create a bounding box
- <span class="icon-btn solid-blue"><i data-lucide="pentagon"></i> Mask Edit</span> — refine SAM3 polygon masks (button only, no keyboard shortcut in video mode)
- **Right-click** an annotation for the context menu: reassign class, set as project/dataset thumbnail
- **Delete** — press Delete or use the <span class="icon-btn icon-only"><i data-lucide="trash-2"></i></span> icon

All annotations are **auto-saved** per keyframe — there is no save button. A save status indicator ("Saving..." / "Saved ✓") appears in the header bar.

---

## Keyboard Shortcuts

Press **?** at any time to show the shortcuts help modal.

### Video Navigation

| Key | Action |
|-----|--------|
| **Space** | Play / Pause video |
| **Z** | Previous frame |
| **C** | Next frame |
| **Shift+Z** | Back 10 frames |
| **Shift+C** | Forward 10 frames |

### Keyframes

| Key | Action |
|-----|--------|
| **K** | Mark current frame as keyframe |
| **Q** | Previous keyframe |
| **E** | Next keyframe |
| **I** | Set interval start |
| **O** | Set interval end |
| **P** | Create interval keyframes |

### Annotation

| Key | Action |
|-----|--------|
| **V** | Select tool |
| **R** | Draw rectangle |
| **Delete** | Delete selected annotation |
| **1–9** | Select class by number |

### General

| Key | Action |
|-----|--------|
| **M** | Toggle Focus Mode (hides sidebars) |
| **F** | Toggle Fullscreen |
| **H** | Go to Dashboard |
| **?** | Toggle shortcuts help |
| **Esc** | Deselect / Cancel |
