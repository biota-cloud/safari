# 📖 SAFARI Onboarding Documentation Portal

> **Goal**: A static, navigable documentation site at `safari-address/onboard` that takes new users from first login through advanced API usage.
> **Delivery**: Styled HTML pages built from Markdown using the md-to-pdf pipeline. Sidebar navigation, SAFARI branding, inter-page links.
> **Source of truth**: UI code for user-facing docs, `docs/architecture/` for technical docs.

---

> [!IMPORTANT]
> ## 📍 Current Focus
> **Phase**: 1 — Getting Started
> **Active Steps**: 1.1–1.6 — Write page content
> **Last Completed**: Phase 0 — Portal Architecture (all steps)
> **Blocked On**: None

---

## 📷 Screenshot Inventory (`docs/onboard/assets/screenshots/`)

27 screenshots available, mapped to pages:

| Screenshot | Phase | Page |
|------------|:-----:|------|
| `Login.png` | 1 | Getting Started |
| `Main_dash.png` | 1 | Getting Started |
| `Projects_card.png` | 1 | Getting Started |
| `New_project_modal.png` | 1 | Getting Started |
| `Project_detail.png` | 1 | Getting Started |
| `New_dataset_modal.png` | 1 | Getting Started |
| `Dataset_detail.png` | 1 | Getting Started |
| `Main_dash_inference_playground_card.png` | 1 | Getting Started |
| `Image_editor.png` | 2 | Image Labeling |
| `SAM3_autolabel_modal.png` | 2 | Autolabeling |
| `Yolo_autolabel_modal.png` | 2 | Autolabeling |
| `Labeling_studio_card.png` | 2 | Image Labeling |
| `Video_editor.png` | 2 | Video Labeling |
| `Trainning_card.png` | 3 | Training |
| `Training_dashboard.png` | 3 | Training |
| `Training_detection_card.png` | 3 | Training |
| `Training_classification_card.png` | 3 | Training |
| `Training_sam3_card.png` | 3 | Training |
| `Training_datasets_card.png` | 3 | Training |
| `Training_runs.png` | 3 | Training |
| `Training_run_detail.png` | 3 | Training |
| `Training_run_artifacts.png` | 3 | Training |
| `Inference_playground.png` | 4 | Playground |
| `Inference_playground_card.png` | 4 | Playground |
| `Inference_playground_card_settings.png` | 4 | Playground |
| `Inference_playground_preview.png` | 4 | Playground |
| `Inference_playground_results.png` | 4 | Playground |

### Missing Screenshots (capture needed)

| Screenshot Needed | Phase | Reason |
|-------------------|:-----:|--------|
| API settings page | 5 | Show API key management UI |
| Mask editing close-up | 2 | Show vertex dragging on a mask |
| Training live metrics | 3 | Show active loss curve during training |
| Video playback with labels | 4 | Show playground video result |
| Model promotion flow | 4 | Show "Add to API" button/modal |

---

## 📚 Reusable Existing Documentation

| File | Target Phase | Reuse Strategy |
|------|:---:|----------------|
| `docs/ONBOARDING.md` | 1–4 | Prose skeleton — expand with screenshots and detail |
| `docs/DEVELOPMENT.md` | 6 | Near-direct inclusion (dev setup, env vars, project structure) |
| `docs/deployment/production_deployment.md` | 6 | Near-direct inclusion (VPS, systemd, Caddy, cost) |
| `docs/architecture/architecture_reference.md` | 6 | Curate into user-facing architecture overview |
| `docs/architecture/architecture_diagrams.md` | 6 | Render Mermaid diagrams to PNG images, embed |
| `docs/architecture/api_architecture_diagram.md` | 5–6 | API response schema + flow diagrams |
| `docs/design/safari_design_reference.md` | 6 | Design system reference |

---

## 🏗️ Phase 0: Portal Architecture & Build Pipeline

**Goal**: Establish file structure, HTML template, build script, and static serving strategy.

### 0.1 File Structure

```
docs/onboard/
├── assets/
│   ├── screenshots/        ← 27 PNGs (moved from assets/onboard/)
│   └── branding/           ← SAFARI logo copy
├── content/                ← Source markdown for each page
│   ├── 00_index.md         ← Welcome portal + page directory
│   ├── 01_getting-started.md
│   ├── 02_image-labeling.md
│   ├── 03_video-labeling.md
│   ├── 04_autolabeling.md
│   ├── 05_training.md
│   ├── 06_playground.md
│   ├── 07_api.md
│   ├── 08_architecture.md
│   ├── 09_deployment.md
│   └── 10_development.md
├── pages/                  ← Generated HTML output
│   ├── index.html
│   ├── 01_getting-started.html
│   └── ...
└── build.py                ← Build script (extends md_to_pdf.py)
```

- [x] **0.1.1** Create directory structure
- [x] **0.1.2** Move screenshots from `assets/onboard/` → `docs/onboard/assets/screenshots/`
- [x] **0.1.3** Copy SAFARI logo to `docs/onboard/assets/branding/`
- [x] **0.1.4** Create stub `.md` files in `content/`

### 0.2 HTML Template Design

The portal is a multi-page static site. Each page shares a consistent shell:

```
┌─────────────────────────────────────────────────────────────┐
│  [●] SAFARI — Documentation                    [Biota Cloud]│
├────────────┬────────────────────────────────────────────────┤
│            │                                                │
│  SIDEBAR   │  MAIN CONTENT                                  │
│            │                                                │
│  □ Home    │  # Page Title                                  │
│  □ Getting │                                                │
│    Started │  Content with embedded screenshots,            │
│  □ Image   │  tables, code blocks, and callouts.            │
│    Labeling│                                                │
│  □ Video   │  ![Screenshot](screenshot.png)                 │
│    Labeling│                                                │
│  □ Auto    │                                                │
│    Labeling│                                                │
│  □ Training│                                                │
│  □ Playgr. │  ┌──────────────────────────────────────────┐  │
│  □ API     │  │  ← Previous: Getting Started             │  │
│  ─────────── │  │  → Next: Video Labeling                  │  │
│  TECHNICAL │  └──────────────────────────────────────────┘  │
│  □ Arch.   │                                                │
│  □ Deploy  │  ─────────────────────────────────────────── │
│  □ Dev     │  SAFARI — Biota Cloud                         │
│            │                                                │
├────────────┴────────────────────────────────────────────────┤
```

- [x] **0.2.1** Design HTML shell template with:
  - Fixed left sidebar (260px) with page list, active state highlighting
  - SAFARI branded header (logo + "Documentation" title)
  - Main content area (max-width 800px, centered)
  - Previous / Next page navigation at bottom
  - Footer with "SAFARI — Biota Cloud" branding
- [x] **0.2.2** Implement CSS using SAFARI design tokens:
  - Dark sidebar (`#352516` brown), light content area (`#F5F0EB` cream)
  - Poppins font for body, JetBrains Mono for code
  - Styled tables, code blocks, callout boxes (tip/important/warning)
  - Screenshot styling: bordered, rounded, centered with shadow
  - Responsive: sidebar collapses on narrow screens
- [x] **0.2.3** Implement "scroll to section" — sidebar shows H2 sub-items for active page

### 0.3 Build Script (`docs/onboard/build.py`)

Reuses `scripts/md_to_pdf.py` CSS and pandoc pipeline, extended for multi-page navigation:

- [x] **0.3.1** Build script that:
  - Reads all `content/*.md` files sorted by numeric prefix
  - Converts each to HTML via pandoc
  - Wraps in shared HTML template (sidebar + header + nav)
  - Resolves relative image paths → `screenshots/`
  - Writes to `assets/onboard/*.html`
  - Generates `assets/onboard/index.html` (welcome page with card-grid linking to all pages)
- [x] **0.3.2** Page metadata: extract title from `# H1`, generate previous/next links
- [x] **0.3.3** Sidebar generation: build sidebar HTML from page list
- [x] **0.3.4** Test: run `python docs/onboard/build.py` → opens index.html in browser

### 0.4 Static Serving

- [x] **0.4.1** Decided serving strategy: **Option B** — build outputs to Reflex `assets/onboard/`
- [x] **0.4.2** Configured: `build.py` outputs directly to `assets/onboard/` with screenshots copied
- [x] **0.4.3** Verified: portal loads at `assets/onboard/index.html` with full navigation

> [!TIP]
> **Test checkpoint**: After 0.4, the portal shell works — all pages load with sidebar nav, but content is stub-only.

---

## 📄 Phase 1: Getting Started

**Goal**: Take a user from zero to "I have a project with uploaded images."
**Page**: `01_getting-started.md`
**Source**: Expand from `docs/ONBOARDING.md` §1–3 with screenshots.

### Content Outline

- [x] **1.1** Section: Getting Access
  - Tailscale installation and invite flow
  - Navigate to SAFARI URL
  - Login screen walkthrough
  - 📷 `Login.png`

- [x] **1.2** Section: The Dashboard
  - Card-based layout overview: Projects, Training, Playground
  - Quick-access navigation
  - 📷 `Main_dash.png`
  - 📷 `Projects_card.png`
  - 📷 `Main_dash_inference_playground_card.png`

- [x] **1.3** Section: Creating Your First Project
  - Click "+ New Project" → name it (descriptive best practice)
  - Project detail view: datasets, classes, training runs
  - 📷 `New_project_modal.png`
  - 📷 `Project_detail.png`

- [x] **1.4** Section: Creating a Dataset
  - Image vs. Video dataset types
  - 📷 `New_dataset_modal.png`

- [x] **1.5** Section: Uploading Data
  - Drag-and-drop / click upload
  - Supported formats: JPG, PNG, WEBP (images); MP4, AVI, MOV, MKV (video)
  - Auto-generated thumbnails
  - 📷 `Dataset_detail.png`

- [x] **1.6** Section: What's Next?
  - Links to: Image Labeling, Video Labeling, Training

### Research Required
- [x] Check `modules/auth/dashboard.py` for current dashboard card layout
- [x] Check `modules/datasets/dataset_detail_state.py` for supported upload formats
- [x] Check `modules/projects/project_detail.py` for project detail page features

> [!TIP]
> **Test checkpoint**: After Phase 1, a user reading only this page should be able to create a project, add a dataset, and upload images.

---

## ✏️ Phase 2: Editors (3 Pages)

**Goal**: Teach the full labeling workflow. Three separate pages for image, video, and autolabeling.

---

### Page 2A: Image Labeling (`02_image-labeling.md`)

**Source**: Check `modules/labeling/editor.py` for tools and layout, `modules/labeling/state.py` for keyboard shortcuts.

- [x] **2A.1** Section: Entering the Editor
  - Navigate: Dataset → click card
  - 📷 `Labeling_studio_card.png`

- [x] **2A.2** Section: Editor Layout
  - Left sidebar: image thumbnails, progress bar ("X of Y labeled")
  - Center: HTML5 Canvas with image + annotations
  - Right sidebar: Tools, Classes, Annotations list
  - Annotated screenshot with callouts
  - 📷 `Image_editor.png`

- [x] **2A.3** Section: Drawing Bounding Boxes
  - Select Draw tool (R key or toolbar button)
  - Click and drag to create box
  - Box auto-assigned to current class

- [x] **2A.4** Section: Selecting & Editing
  - Click annotation to select (V key)
  - Resize via corner handles
  - Move by dragging interior
  - Delete with Delete key or sidebar button
  - Right-click context menu: change class, set as project/dataset thumbnail

- [x] **2A.5** Section: Class Management
  - Add classes: type name in sidebar input
  - Change class of selected annotation
  - Delete class (with confirmation)
  - Color-coded labels on canvas (HSL rotation)

- [x] **2A.6** Section: Editing Masks
  - Pentagon tool in toolbar (mask_edit mode)
  - Drag vertices to reshape polygon mask
  - Click edge to add vertex
  - "Delete Mask" button removes polygon (keeps bounding box)
  - Only available on annotations with SAM3 masks

- [x] **2A.7** Section: Navigation
  - Thumbnails in left sidebar (click to jump)
  - Previous/Next: A/D keys
  - Progress tracking (labeled checkmarks)

- [x] **2A.8** Section: Autosave
  - All changes saved automatically — no save button
  - Dirty indicator in top-corner

- [x] **2A.9** Section: Keyboard Shortcuts
  - Full reference table:

| Key | Action |
|-----|--------|
| V | Select tool |
| R | Draw rectangle |
| C | Edit masks (image only) |
| Delete | Delete selected annotation |
| 1–9 | Select class by number |
| A / D | Previous / Next image |
| Escape | Deselect / Cancel |
| ? | Show shortcuts help |

### Research Required
- [x] Check `modules/labeling/editor.py` → `right_sidebar()` for exact tools list
- [x] Check `assets/canvas.js` → `handleKeyDown()` for all keyboard shortcuts
- [x] Check `modules/labeling/state.py` for class management methods
- [x] Verify mask editing button label and icon

---

### Page 2B: Video Labeling (`03_video-labeling.md`)

**Source**: Check `modules/labeling/video_editor.py` and `modules/labeling/video_state.py`.

- [x] **2B.1** Section: Video Editor Overview
  - Same layout as image editor but with video player controls
  - 📷 `Video_editor.png`

- [x] **2B.2** Section: Video Player Controls
  - Play/Pause: Space
  - Frame step: Z (back), C (forward)
  - 10-frame step: Shift+Z, Shift+C
  - Timeline scrubber (slider)
  - Frame/timestamp display

- [x] **2B.3** Section: The Keyframe System
  - What keyframes are: frames marked for annotation (sparse labeling)
  - Mark keyframe: K key or button
  - Mark empty frame (negative sample)
  - Keyframe thumbnails in left sidebar
  - Navigate between keyframes: Q (prev), E (next)

- [x] **2B.4** Section: Annotating Keyframes
  - Same tools as image editor (draw, select, resize, delete, mask edit)
  - Annotations tied to specific keyframes
  - Auto-saved per keyframe

- [x] **2B.5** Section: Keyboard Shortcuts
  - Video-specific shortcuts table:

| Key | Action |
|-----|--------|
| Space | Play / Pause |
| Z / C | Previous / Next frame |
| Shift+Z / Shift+C | -10 / +10 frames |
| K | Mark keyframe |
| Q / E | Previous / Next keyframe |
| I / O / P | Interval Start / End / Create |

### Research Required
- [x] Check `modules/labeling/video_editor.py` → player controls layout
- [x] Check `assets/canvas.js` → video mode keyboard shortcuts
- [x] Check `modules/labeling/video_state.py` → interval marking feature details

---

### Page 2C: Autolabeling (`04_autolabeling.md`)

**Source**: Check `modules/labeling/editor.py` → `autolabel_modal()` and `video_editor.py` → autolabel modal.

- [ ] **2C.1** Section: What is Autolabeling?
  - AI pre-labels your dataset → you review and correct
  - Two modes: SAM3 (zero-shot) and YOLO (trained model)
  - Available for both image and video datasets

- [ ] **2C.2** Section: SAM3 Mode
  - Text prompt detection (e.g., "Lynx", "animal")
  - Map prompts to project classes
  - Confidence threshold
  - Generate bounding boxes checkbox
  - Generate masks checkbox
  - 📷 `SAM3_autolabel_modal.png`

- [ ] **2C.3** Section: YOLO Mode
  - Select a trained detection model
  - Confidence threshold
  - 📷 `Yolo_autolabel_modal.png`

- [ ] **2C.4** Section: Compute Target
  - Cloud (Modal GPU) vs. Local GPU toggle
  - When to use which

- [ ] **2C.5** Section: Reviewing Results
  - Navigate labeled images, correct errors
  - Delete incorrect annotations
  - Change classes where misclassified

### Research Required
- [ ] Check `modules/labeling/editor.py` → SAM3/YOLO panel contents for exact parameters
- [ ] Check `modules/labeling/video_editor.py` → video autolabel modal (differences from image)

> [!TIP]
> **Test checkpoint**: After Phase 2, a user should be able to label any dataset (image or video) efficiently, including using AI assistance.

---

## 🎯 Phase 3: Training

**Goal**: Guide the user from labeled datasets to a trained model.
**Page**: `05_training.md`
**Source**: Check `modules/training/` for dashboard layout and state.

- [x] **3.1** Section: Training Dashboard Overview
  - Navigate: Project → Training tab
  - Dashboard layout: datasets, model type cards, recent runs
  - 📷 `Trainning_card.png`
  - 📷 `Training_dashboard.png`

- [x] **3.2** Section: Selecting Datasets
  - Multi-dataset selection
  - Usage tags (train, val, test)
  - Train/val split percentage
  - 📷 `Training_datasets_card.png`

- [x] **3.3** Section: Detection Training (YOLO)
  - Backbone selection: YOLOv11 n/s/m/l/x
  - Hyperparameters: epochs, image size, batch size, patience
  - 📷 `Training_detection_card.png`

- [x] **3.4** Section: Classification Training
  - Backbone: YOLO-Classify vs. ConvNeXt
  - How classification training works: crop bounding boxes → classify
  - 📷 `Training_classification_card.png`

- [x] **3.5** Section: SAM3 Fine-Tuning
  - When to use: custom domain adaptation for SAM3
  - 📷 `Training_sam3_card.png`

- [x] **3.6** Section: Compute Target
  - Cloud (Modal A10G/L40S GPU) vs. Local GPU
  - Cloud: pay-per-use, no setup. Local: use your own hardware

- [x] **3.7** Section: Monitoring a Training Run
  - Real-time status updates
  - Loss curves, precision, recall, mAP
  - 📷 `Training_runs.png`
  - 📷 `Training_run_detail.png`

- [x] **3.8** Section: Training Artifacts
  - Model weights (best.pt / best.pth)
  - Metrics CSV, confusion matrix, PR curves
  - 📷 `Training_run_artifacts.png`

- [x] **3.9** Section: What To Do With Your Model
  - Playground: test on new images
  - Autolabel: apply to unlabeled datasets
  - API: promote for external use

### Research Required
- [x] Check `modules/training/state.py` for all training parameters
- [x] Check `modules/training/dashboard.py` for dashboard sections and cards
- [x] Check training modal components for exact field labels

> [!TIP]
> **Test checkpoint**: After Phase 3, a user should be able to train a detection or classification model and understand the results.

---

## 🧪 Phase 4: Model Playground

**Goal**: Show how to test models on new data.
**Page**: `06_playground.md`
**Source**: Check `modules/inference/state.py` and `modules/inference/playground.py`.

- [x] **4.1** Section: Playground Overview
  - Navigate from dashboard sidebar
  - Model selection, upload, results
  - 📷 `Inference_playground.png`

- [x] **4.2** Section: Selecting a Model
  - Dropdown with model name, backbone badge (YOLO/CNX)
  - 📷 `Inference_playground_card.png`

- [x] **4.3** Section: Configuring Settings
  - Confidence threshold slider
  - SAM3 resolution selector (480/1036/1280)
  - Top-K classification (video only)
  - Video preprocessing: target resolution, target FPS
  - 📷 `Inference_playground_card_settings.png`

- [x] **4.4** Section: Running Inference
  - Single image: drag and drop
  - Batch: multiple files
  - Video: upload → async processing
  - 📷 `Inference_playground_preview.png`

- [x] **4.5** Section: Understanding Results
  - Bounding boxes with class labels and confidence %
  - Mask polygons (when enabled)
  - 📷 `Inference_playground_results.png`

- [x] **4.6** Section: Video Results
  - Frame-by-frame playback with overlays
  - Crop gallery for Top-K visual evidence

- [x] **4.7** Section: Promoting to API
  - "Add to API" button on trained model
  - Set slug, SAM3 prompt, confidence
  - Makes model available via REST API

### Research Required
- [x] Check `modules/inference/state.py` for settings (imgsz options, confidence, top_k)
- [x] Check `modules/inference/playground.py` for model selector and upload UI
- [x] Check video result playback component

> [!TIP]
> **Test checkpoint**: After Phase 4, a user should be able to test any model and promote it to the API.

---

## 🔌 Phase 5: API

**Goal**: Document programmatic access for batch processing and desktop integration.
**Page**: `07_api.md`
**Source**: `docs/architecture/api_architecture_diagram.md` for schema, check `modules/api/` for UI.

- [x] **5.1** Section: API Overview
  - REST API for automated inference
  - Use cases: batch camera trap processing, SAFARIDesktop, custom scripts
  - Base URL structure

- [x] **5.2** Section: Creating API Keys
  - Navigate: Project → API settings
  - Create key → copy `safari_xxxx...` token
  - Key scopes: project-level or user-wide
  - 📷 `API.png`, `API_key_creation.png`, `API_key_confirmation.png`

- [x] **5.3** Section: Endpoints Reference

| Endpoint | Method | Purpose |
|----------|--------|---------|
| `/api/v1/infer/{slug}` | POST | Single image inference |
| `/api/v1/infer/{slug}/batch` | POST | Batch image inference |
| `/api/v1/infer/{slug}/video` | POST | Async video inference |
| `/api/v1/jobs/{job_id}` | GET | Poll video job status |

- [x] **5.4** Section: Single Image Example
  - curl example with Authorization header
  - Response JSON structure: `predictions[]`, `image_width`, `image_height`

- [x] **5.5** Section: Video Inference (Async)
  - Submit → get job_id → poll `/jobs/{id}` → get results
  - Show polling loop example

- [x] **5.6** Section: Response Schema

| Field | Type | Description |
|-------|------|-------------|
| `class_name` | string | Species label |
| `class_id` | integer | Class index |
| `confidence` | float | 0–1 confidence |
| `box` | [x1,y1,x2,y2] | Normalized bounding box |
| `mask_polygon` | [[x,y]...] | Polygon points (hybrid only) |
| `track_id` | integer | Track ID (video only) |

- [x] **5.7** Section: SAFARIDesktop
  - Brief: native desktop client for video processing
  - Download, configure API key, process local videos

### Research Required
- [x] Check `modules/api/` for API key management UI
- [x] Check `backend/api/routes/inference.py` for exact endpoint signatures
- [x] Check `backend/api/server.py` for base URL pattern
- [x] Check response format from `api_architecture_diagram.md` (confirmed as ground truth)

---

## 📐 Phase 6: Technical Documentation (3 Pages)

**Goal**: Developer-facing reference docs. Generated primarily from existing architecture files.

---

### Page 6A: Architecture (`08_architecture.md`)

**Source**: `docs/architecture/architecture_reference.md` (879 lines) + `docs/architecture/architecture_diagrams.md` (609 lines)

- [x] **6A.1** Section: System Overview
  - Two codebases: SAFARI Server (Reflex) + SAFARIDesktop (Tauri)
  - Architecture diagram (ASCII topology)

- [x] **6A.2** Section: Compute Architecture
  - Job Router: Cloud (Modal) vs. Local GPU
  - GPU assignment table (L40S for SAM3, A10G for training)
  - Action-Level target selection

- [x] **6A.3** Section: Shared Core Pattern
  - `backend/core/` — pure logic shared between Modal and Local GPU
  - Core module table (function → purpose)
  - File parity matrix

- [x] **6A.4** Section: Storage Architecture
  - Supabase (PostgreSQL): tables, RLS, JSONB annotations
  - R2 (S3-compatible): images, labels, weights, results
  - Dual-write pattern, annotation schema, coordinate formats

- [x] **6A.5** Section: State Management
  - Key state classes table
  - Data flow between modules

- [x] **6A.6** Section: API Infrastructure
  - Modal ASGI gateway, API key auth, isolated workers
  - From `api_architecture_diagram.md`

**Strategy**: Curated architecture_reference.md + architecture_diagrams.md into readable sections. Used ASCII diagrams (no Mermaid CLI dependency).

### Research Required
- [x] Verify Mermaid CLI availability: used ASCII diagrams instead
- [x] Review architecture_reference.md for any outdated sections (used as ground truth)

---

### Page 6B: Deployment (`09_deployment.md`)

**Source**: `docs/deployment/production_deployment.md` — near-direct inclusion.

- [x] **6B.1** Prerequisites (VPS, Tailscale, credentials)
- [x] **6B.2** Server Setup (Ubuntu, Python, Tailscale)
- [x] **6B.3** Application Setup (clone, venv, env)
- [x] **6B.4** Supabase Database Schema
- [x] **6B.5** Modal Authentication + Secrets
- [x] **6B.6** Deploy Modal Jobs (`deploy_modal.sh`)
- [x] **6B.7** systemd Service (auto-start, restart on crash)
- [x] **6B.8** Caddy Reverse Proxy (optional)
- [x] **6B.9** Operations (logs, updates, restart, firewall)
- [x] **6B.10** Cost Breakdown (~€4/month + usage)

**Strategy**: Minor formatting to match portal template. Content is already production-ready.

---

### Page 6C: Development (`10_development.md`)

**Source**: `docs/DEVELOPMENT.md` — near-direct inclusion.

- [x] **6C.1** Prerequisites table (Python, Node, Reflex, Modal, Git)
- [x] **6C.2** Local Setup (clone, venv, install, run)
- [x] **6C.3** Environment Variables (Supabase, R2, Modal, App settings)
- [x] **6C.4** Modal GPU Deployment (deploy commands, monitor, SAM3 weights)
- [x] **6C.5** Local GPU Workers (remote setup, credentials, run)
- [x] **6C.6** Running Tests
- [x] **6C.7** Project Structure tree
- [x] **6C.8** Common Tasks reference table

**Strategy**: Minor formatting to match portal template. Content is already production-ready.

---

## 🚀 Phase 7: Portal Index & Build

**Goal**: Build the welcome page, finalize navigation, test end-to-end.

### Welcome Page (`00_index.md`)

- [x] **7.1** Welcome message with SAFARI logo
- [x] **7.2** Card grid linking to all pages (grouped by User Guide / Technical)
- [x] **7.3** Quick start: "New here? Start with Getting Started →"

### Build & Polish

- [x] **7.4** Run `build.py` → generate all HTML pages
- [x] **7.5** Test full navigation: index → every page → back → verify all links
- [x] **7.6** Verify all 33 screenshots render correctly
- [x] **7.7** Test on mobile (sidebar collapse)
- [x] **7.8** Deploy to production server

---

## 💡 Future Improvements

| Feature | Priority | Description |
|---------|:--------:|-------------|
| **Full-text search** | High | lunr.js or minisearch — search across all pages |
| **Breadcrumbs** | Medium | Navigation path: Home → Training → Artifacts |
| **Dark/Light toggle** | Medium | Match app theme preference |
| **PDF export per page** | Medium | "Download as PDF" button using existing md-to-pdf |
| **Interactive demos** | Medium | Embedded GIF/video walkthroughs for complex flows |
| **Version badge** | Low | Show SAFARI version in header/footer |
| **Changelog** | Low | "What's New" page for release notes |
| **Auto-screenshot** | Low | Playwright script to capture screenshots on each release |
| **Localization** | Low | i18n support for PT-BR |
| **Analytics** | Low | Page view tracking (which docs are most read) |

---

## ⚠️ Open Decisions

> [!IMPORTANT]
> **Serving strategy**: How to make the portal accessible at `/onboard`:
> - **Option A** (recommended): Caddy serves static files from `docs/onboard/pages/`
> - **Option B**: Copy generated pages to Reflex `assets/onboard/` directory
> - **Option C**: Use `rx.html()` for in-app embedding (most integrated, ties docs to app deploys)

> [!NOTE]
> **Mermaid rendering** (Phase 6): Architecture diagrams use Mermaid syntax. Two options:
> - Pre-render to PNG using `mmdc` CLI (static, fast pages)
> - Include Mermaid JS library for client-side rendering (auto-updates, heavier pages)

---

*Last updated: 2026-03-06*
