# SAFARI File Map — Developer Navigation Guide

> **Purpose**: Quickly find any file, function, or class in the codebase.
> Unlike the architecture reference (which explains *how* things work), this is a *where to find things* map.

## Quick Jump — "Where Do I Look?"

| I need to…                              | Look in                                                                   |
|-----------------------------------------|---------------------------------------------------------------------------|
| Debug inference (image/batch/video)      | `backend/inference_router.py` → `backend/job_router.py`                  |
| Fix a Modal GPU job                      | `backend/modal_jobs/` (see [modal-and-workers.md](modal-and-workers.md)) |
| Fix a local GPU job                      | `scripts/remote_workers/` (see [modal-and-workers.md](modal-and-workers.md)) |
| Change core inference/training logic     | `backend/core/` — shared between Modal & SSH workers                     |
| Fix a database query                     | `backend/supabase_client.py` (see [backend-services.md](backend-services.md)) |
| Fix annotation save/load                 | `backend/annotation_service.py`                                          |
| Fix R2 file storage                      | `backend/r2_storage.py`                                                  |
| Fix SSH remote execution                 | `backend/ssh_client.py`                                                  |
| Fix the public REST API                  | `backend/api/server.py` + `backend/api/routes/`                          |
| Fix playground UI / inference state      | `modules/inference/state.py` + `playground.py`                           |
| Fix training UI / training state         | `modules/training/state.py` + `dashboard.py`                             |
| Fix labeling editor (images)             | `modules/labeling/state.py` + `editor.py`                                |
| Fix labeling editor (videos)             | `modules/labeling/video_state.py` + `video_editor.py`                    |
| Fix dataset uploads / image management   | `modules/datasets/dataset_detail_state.py`                               |
| Fix project management / dashboard hub   | `modules/auth/hub_state.py` + `dashboard.py`                             |
| Fix authentication / sessions            | `app_state.py` (AuthState)                                               |
| Fix API key management                   | `modules/api/state.py` + `page.py`                                       |
| Fix admin / user management              | `modules/admin/admin_state.py`                                            |
| Change global styles                     | `styles.py`                                                              |
| Add a new page / route                   | `safari/safari.py` (register import) + new module in `modules/`         |
| Write a database migration               | `migrations/` (SQL files)                                                |
| Write or run tests                       | `tests/`                                                                 |

---

## Directory Tree

Legend: 🟢 **Your core code** · ⚪ **Reflex boilerplate / config** · 🔵 **Infrastructure / tooling**

```
SAFARI/                               ← Project root (repo dir retained for git history)
│
├── safari/                          ⚪ Reflex app entry point
│   └── safari.py                   ⚪ Route registration, global scripts, app config, window.__SAFARI_CONFIG injection
│
├── app_state.py                     🟢 AuthState — login/logout/session management
├── styles.py                        🟢 Design tokens, colors, fonts, spacing (SAFARI Naturalist theme)
├── rxconfig.py                      ⚪ Reflex config (websocket, plugins)
│
├── backend/                         🟢 ALL backend logic lives here
│   ├── __init__.py                 🟢 Package init with SAFARI docstring
│   ├── supabase_client.py          🟢 Database operations (3,589 lines)
│   ├── annotation_service.py       🟢 Annotation read/write/validation (977 lines)
│   ├── r2_storage.py               🟢 Cloudflare R2 file storage client
│   ├── model_registry.py           🟢 Model types, metadata, loading logic
│   ├── ssh_client.py               🟢 SSH remote worker management (671 lines)
│   ├── inference_router.py         🟢 Unified inference dispatch entry point
│   ├── job_router.py               🟢 Routes jobs to Modal (cloud) or SSH (local) (595 lines)
│   ├── frame_extractor.py          🟢 FFmpeg frame extraction from videos
│   ├── zip_processor.py            🟢 YOLO zip dataset import/export
│   ├── supabase_auth.py            🟢 Auth retry decorator for expired tokens
│   │
│   ├── core/                       🟢 Shared processing logic (Modal + SSH workers use these)
│   │   ├── hybrid_infer_core.py    🟢 Single-image hybrid inference pipeline
│   │   ├── hybrid_batch_core.py    🟢 Batch hybrid inference pipeline
│   │   ├── hybrid_video_core.py    🟢 Video hybrid inference (SAM3 tracking) (799 lines)
│   │   ├── autolabel_core.py       🟢 Automatic annotation pipeline
│   │   ├── train_detect_core.py    🟢 YOLO detection training pipeline
│   │   ├── train_classify_core.py  🟢 Classification training (YOLO + ConvNeXt)
│   │   ├── yolo_infer_core.py      🟢 Pure YOLO detection inference
│   │   ├── sam3_dataset_core.py    🟢 SAM3 fine-tuning dataset preparation
│   │   ├── image_utils.py          🟢 Image cropping and download utilities
│   │   ├── classifier_utils.py     🟢 Model loading and classification utilities
│   │   └── thumbnail_generator.py  🟢 Thumbnail generation for results
│   │
│   ├── modal_jobs/                 🟢 Modal GPU cloud jobs
│   │   ├── api_infer_job.py        🟢 Public API inference endpoints (1,472 lines — largest)
│   │   ├── train_sam3_job.py       🟢 SAM3 fine-tuning job (1,170 lines)
│   │   ├── hybrid_infer_job.py     🟢 Hybrid SAM3+classifier inference
│   │   ├── infer_job.py            🟢 YOLO detection inference
│   │   ├── autolabel_job.py        🟢 Auto-labeling job
│   │   ├── train_job.py            🟢 YOLO detection training
│   │   ├── train_classify_job.py   🟢 Classification training
│   │   └── model_volume.py         🟢 Modal volume management
│   │
│   ├── api/                        🟢 Public REST API (deployed on Modal)
│   │   ├── server.py               🟢 FastAPI app + Modal ASGI deployment
│   │   ├── auth.py                 🟢 API key authentication middleware
│   │   └── routes/
│   │       ├── inference.py        🟢 /api/v1/infer endpoints
│   │       └── jobs.py             🟢 /api/v1/jobs polling endpoint
│   │
│   └── sql/                        🔵 Reference SQL files
│
├── modules/                         🟢 Feature modules (page + state per feature)
│   ├── admin/                      🟢 Admin user management
│   │   └── admin_state.py          🟢 User roles, admin modal state
│   ├── auth/                       🟢 Login page + dashboard hub
│   │   ├── login.py                🟢 Split-panel SAFARI login page
│   │   ├── dashboard.py            🟢 Dashboard hub (project/dataset/training cards)
│   │   └── hub_state.py            🟢 Hub state (project/dataset CRUD, inline edit)
│   ├── projects/                   🟢 Project management + detail page
│   │   ├── projects.py             🟢 Project list page
│   │   ├── project_detail.py       🟢 Project detail page (1,829 lines)
│   │   ├── project_detail_state.py 🟢 Project detail state (team toggle, members)
│   │   ├── new_project_modal.py    🟢 New project creation modal
│   │   ├── models.py               🟢 Project data models
│   │   └── state.py                🟢 Project list state
│   ├── datasets/                   🟢 Dataset management + uploads
│   │   ├── dataset_detail.py       🟢 Dataset detail page
│   │   ├── dataset_detail_state.py 🟢 Dataset uploads, video management (1,705 lines)
│   │   └── state.py                🟢 Dataset list/management state (1,269 lines)
│   ├── inference/                  🟢 Inference playground + results
│   │   ├── playground.py           🟢 Inference playground page
│   │   ├── state.py                🟢 Inference state — all flows (3,469 lines)
│   │   ├── result_viewer.py        🟢 Inference result detail page
│   │   └── video_player.py         🟢 Video playback component
│   ├── labeling/                   🟢 Image & video annotation editors
│   │   ├── editor.py               🟢 Image labeling editor page
│   │   ├── state.py                🟢 Image labeling state (2,830 lines)
│   │   ├── video_editor.py         🟢 Video labeling editor page
│   │   ├── video_state.py          🟢 Video labeling state (4,029 lines — largest)
│   │   └── tools.py                🟢 Labeling tool definitions
│   ├── training/                   🟢 Training dashboard + run details
│   │   ├── dashboard.py            🟢 Training dashboard page
│   │   ├── run_detail.py           🟢 Individual training run detail page
│   │   └── state.py                🟢 Training state (2,906 lines)
│   └── api/                        🟢 API key management UI
│       ├── page.py                 🟢 API settings page
│       └── state.py                🟢 API key state
│
├── components/                      🟢 Shared reusable UI components
│   ├── card.py                     🟢 Card component
│   ├── compute_target_toggle.py    🟢 Cloud/local GPU toggle
│   ├── context_menu.py             🟢 Right-click context menus
│   ├── nav_header.py               🟢 Top navigation bar (SAFARI brown header)
│   └── upload_zone.py              🟢 Drag-and-drop upload component
│
├── scripts/                         🔵 Maintenance & deployment scripts
│   ├── remote_workers/             🟢 SSH worker scripts (run on local GPU machines)
│   │   ├── remote_infer.py         🟢 YOLO detection inference worker
│   │   ├── remote_hybrid_infer.py  🟢 Hybrid inference worker
│   │   ├── remote_yolo_infer.py    🟢 YOLO-only inference worker
│   │   ├── remote_autolabel.py     🟢 Auto-labeling worker
│   │   ├── remote_train.py         🟢 Detection training worker
│   │   ├── remote_train_classify.py 🟢 Classification training worker
│   │   ├── remote_utils.py         🟢 Shared utilities for workers
│   │   ├── cleanup_cache.py        🟢 Remote cache cleanup utility
│   │   ├── install.sh              🔵 Remote environment setup
│   │   ├── remote_setup.sh         🔵 Remote environment setup
│   │   ├── remote_requirements.txt 🔵 Remote Python dependencies
│   │   └── verify_remote.py        🔵 Remote environment verification
│   └── *.py                        🔵 One-off maintenance scripts
│
├── tests/                           🔵 Test suite
│   ├── conftest.py                 🔵 Shared test fixtures
│   ├── test_annotation_service.py  🔵 Annotation service tests
│   ├── test_api_inference.py       🔵 API inference endpoint tests
│   ├── test_api_keys.py            🔵 API key management tests
│   ├── test_api_models.py          🔵 API model endpoint tests
│   ├── test_core_classifier_utils.py 🔵 Classifier utility tests
│   ├── test_core_image_utils.py    🔵 Image utility tests
│   ├── test_core_yolo_infer.py     🔵 YOLO inference core tests
│   ├── test_hybrid_video_classification.py 🔵 Hybrid video classification tests
│   ├── test_inference_router.py    🔵 Inference router tests
│   └── test_model_registry.py      🔵 Model registry tests
│
├── migrations/                      🔵 SQL migration files (14 files)
├── assets/                          ⚪ Static files loaded globally
│   ├── canvas.js                   🟢 Labeling canvas logic (2,687 lines)
│   ├── inference_player.js         🟢 Video inference playback
│   ├── selection_handler.js        🟢 Long-press and range selection
│   ├── session_manager.js          🟢 Token refresh & session stability
│   ├── global_shortcuts.js         🟢 Global keyboard shortcuts
│   ├── labeling_shortcuts.js       🟢 Labeling keyboard shortcuts
│   ├── autoscroll.js               🟢 Auto-scroll for log areas
│   ├── safari_fonts.css            ⚪ Google Fonts import (DM Sans / Poppins)
│   ├── branding/                   ⚪ SAFARI logo and branding assets
│   └── favicon.ico                 ⚪ SAFARI [●] mark favicon
│
├── docs/                            🔵 Documentation
├── .env                             ⚪ Environment variables (not in git)
├── .env.production.example          ⚪ Production env template
├── .web/                            ⚪ Reflex build output (auto-generated, don't edit)
├── .states/                         ⚪ Reflex state cache (auto-generated)
├── .venv/                           ⚪ Python virtual environment
└── uploaded_files/                  ⚪ Reflex file upload temp directory
```

---

## Companion Documents

| Document | Contents |
|----------|----------|
| [backend-services.md](backend-services.md) | Every function in backend service files |
| [modal-and-workers.md](modal-and-workers.md) | Modal jobs, remote workers, core modules + dispatch flow |
| [frontend-modules.md](frontend-modules.md) | All UI modules, state classes, and key event handlers |

---

## File Size Reference

Largest files (where you'll spend the most time):

| File | Lines | Description |
|------|-------|-------------|
| `modules/labeling/video_state.py` | 4,029 | Video labeling state (SAM3 tracking, keyframe annotations) |
| `modules/inference/state.py` | 3,469 | Inference playground state (all inference flows) |
| `backend/supabase_client.py` | 3,589 | All database operations |
| `modules/training/state.py` | 2,906 | Training dashboard state |
| `modules/labeling/state.py` | 2,830 | Image labeling state (canvas, annotations) |
| `assets/canvas.js` | 2,687 | Canvas rendering and interaction (JavaScript) |
| `modules/projects/project_detail.py` | 1,829 | Project detail page UI |
| `modules/datasets/dataset_detail_state.py` | 1,705 | Dataset uploads, video management |
| `backend/modal_jobs/api_infer_job.py` | 1,472 | Public API inference endpoints |
| `modules/datasets/state.py` | 1,269 | Dataset list/management state |
| `backend/modal_jobs/train_sam3_job.py` | 1,170 | SAM3 fine-tuning job |
| `backend/annotation_service.py` | 977 | Annotation CRUD + class management |
| `backend/core/hybrid_video_core.py` | 799 | Video hybrid inference core (SAM3 tracking) |
| `backend/ssh_client.py` | 671 | Remote GPU worker client |
| `backend/job_router.py` | 595 | Job dispatch routing |
