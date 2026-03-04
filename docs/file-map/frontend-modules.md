# Frontend Modules — Pages, States & Components

> Every Reflex UI module, its pages, state classes, and key event handlers.
>
> **Boilerplate guide**: Methods like `set_*()` (simple setters), `toggle_*()` (boolean toggles), and computed vars that just format data are Reflex boilerplate. The **important** methods are marked with ⭐.

---

## Module Structure Pattern

Each module in `modules/` follows this pattern:

```
modules/feature/
├── __init__.py          # Exports
├── state.py             # ⭐ State class — event handlers, business logic
├── page.py              # UI layout — Reflex components
└── (optional extras)    # Sub-pages, detail views, etc.
```

---

## `app_state.py` — Global Auth State

**Class: `AuthState(rx.State)`** — Authentication and session management.

| Method | Type | Description |
|--------|------|-------------|
| ⭐ `login(email, password, remember_me)` | Handler | Authenticate user with Supabase |
| ⭐ `logout()` | Handler | Sign out + clear stored tokens |
| ⭐ `check_auth()` | Handler | Check session on page load (use in `on_load`) |
| ⭐ `restore_session(user_id, email, access, refresh)` | Handler | Restore from localStorage tokens |
| ⭐ `proactive_refresh()` | Handler | Refresh tokens before expiration |
| `try_restore_from_storage()` | Handler | Read tokens from browser storage |
| `handle_storage_tokens(json)` | Handler | Callback with parsed tokens |
| `is_authenticated` | Computed | Check if user is authenticated |
| `user_email` | Computed | Current user's email |
| `user_id` | Computed | Current user's UUID |

**`require_auth(page)`** — Decorator for protected pages. Redirects to `/login` if unauthenticated.

---

## `modules/admin/` — Admin Panel & Project Sharing *(NEW)*

### Files
| File | Lines | Purpose |
|------|-------|---------|
| `admin_state.py` | 116 | Admin modal + project sharing state |

### `AdminState` — Key Methods
| Method | Description |
|--------|-------------|
| ⭐ `open_admin_modal()` | Load all users and open admin modal |
| ⭐ `toggle_user_role(user_id, role)` | Toggle user between admin/user (protects self-demotion) |
| ⭐ `load_project_members(project_id, is_team)` | Load project members + open popover |
| ⭐ `add_member(user_id)` | Add user as project member |
| ⭐ `remove_member(user_id)` | Remove user from project |
| ⭐ `toggle_team_project()` | Toggle is_company flag on project |

---

## `modules/auth/` — Login & Dashboard Hub

### Files
| File | Lines | Purpose |
|------|-------|---------|
| `login.py` | 368 | SAFARI split-panel login page |
| `dashboard.py` | 1,209 | Dashboard hub — "Mission Control" overview |
| `hub_state.py` | 819 | Dashboard hub state |

### `HubState` — Key Methods
| Method | Description |
|--------|-------------|
| ⭐ `load_dashboard()` | Load projects, datasets, stats, training runs |
| ⭐ `create_project(name)` | Create new project |
| ⭐ `delete_project(project_id)` | Delete project with confirmation |
| `navigate_to_project(id)` | Navigate to project detail |

---

## `modules/projects/` — Project Management

### Files
| File | Lines | Purpose |
|------|-------|---------|
| `projects.py` | 301 | Projects list page |
| `project_detail.py` | 1,829 | Project detail page (classes, datasets, team settings) |
| `project_detail_state.py` | 495 | Project detail state (team toggle, members) |
| `state.py` | 248 | Projects list state |
| `new_project_modal.py` | 161 | New project creation modal |
| `models.py` | 31 | Pydantic models |

### `ProjectDetailState` — Key Methods
| Method | Description |
|--------|-------------|
| ⭐ `load_project()` | Load project details, classes, datasets |
| ⭐ `add_class(name)` | Add species class to project |
| ⭐ `rename_class(old, new)` | Rename/merge class across all annotations |
| ⭐ `delete_class(name)` | Delete class from project + all annotations |
| ⭐ `create_dataset(name, type)` | Create new dataset in project |
| ⭐ `delete_dataset(id)` | Delete dataset + R2 files |

---

## `modules/datasets/` — Dataset Management

### Files
| File | Lines | Purpose |
|------|-------|---------|
| `dataset_detail.py` | 1,637 | Dataset detail page (image/video grid) |
| `dataset_detail_state.py` | 1,705 | Dataset detail state (uploads, deletion) |
| `state.py` | 1,269 | Dataset list state (autolabel integration) |

### `DatasetDetailState` — Key Methods
| Method | Description |
|--------|-------------|
| ⭐ `load_dataset()` | Load dataset, images/videos with presigned URLs |
| ⭐ `handle_upload(files)` | Upload images/videos to R2 + create DB records |
| ⭐ `handle_zip_upload(files)` | Import YOLO-format ZIP dataset |
| ⭐ `handle_video_upload(files)` | Upload videos with FFmpeg metadata extraction |
| ⭐ `delete_image(id)` | Delete image from R2 + DB |
| ⭐ `delete_video(id)` / `delete_selected_videos()` | Delete videos with keyframe cleanup |
| `set_usage_tag(tag)` | Set train/validation tag |

### `DatasetState` (in `state.py`) — Key Methods
| Method | Description |
|--------|-------------|
| ⭐ `load_datasets()` | Load datasets for autolabel page |
| ⭐ `start_autolabel()` | Launch autolabel job |
| ⭐ `polling_autolabel()` | Poll autolabel job progress |

---

## `modules/inference/` — Inference Playground

### Files
| File | Lines | Purpose |
|------|-------|---------|
| `playground.py` | 1,667 | Playground page UI (upload, config, results) |
| `state.py` | 3,469 | **Largest state file** — all inference flows |
| `result_viewer.py` | 232 | Result viewer sub-page |
| `video_player.py` | 156 | Video player component |

### `InferenceState` — Key Methods

**Model & Config:**
| Method | Description |
|--------|-------------|
| ⭐ `load_models()` | Load built-in + custom models from Supabase |
| ⭐ `select_model_by_name(name)` | Select model + persist preference |
| `set_compute_target(value)` | Cloud/local toggle |

**Upload:**
| Method | Description |
|--------|-------------|
| ⭐ `handle_upload(files)` | Detect image/video, single/batch, route accordingly |
| `_handle_image_upload(file)` | Process single image upload |
| `_handle_batch_image_upload(files)` | Process batch image upload |
| `_handle_video_upload(file)` | Process video upload + extract metadata |

**Inference Execution:**
| Method | Description |
|--------|-------------|
| ⭐ `run_inference()` | Main entry — routes to image or video flow |
| ⭐ `_run_image_inference()` | YOLO image detection |
| ⭐ `_run_hybrid_image_inference()` | Hybrid SAM3+classifier image |
| ⭐ `_run_batch_inference()` | YOLO batch detection |
| ⭐ `_run_hybrid_batch_inference()` | Hybrid batch inference |
| ⭐ `start_video_inference()` | Background YOLO video inference + polling |
| ⭐ `start_hybrid_video_inference()` | Background hybrid video inference + polling |
| ⭐ `_run_native_hybrid_video_inference()` | SAM3 native video tracking pipeline |
| ⭐ `polling_inference()` | Poll video/async job progress |

**Results & Preview:**
| Method | Description |
|--------|-------------|
| ⭐ `load_user_results()` | Load result history |
| ⭐ `preview_result(result_id)` | Load + show preview modal |
| ⭐ `load_inference_result()` | Load result for playback page |
| ⭐ `delete_inference_result(id)` | Delete with R2 cleanup |
| `generate_video_hybrid_thumbnail(id)` | On-demand thumbnail generation |

---

## `modules/labeling/` — Image & Video Annotation Editors

### Files
| File | Lines | Purpose |
|------|-------|---------|
| `editor.py` | 1,889 | Image labeling editor UI (canvas, sidebar) |
| `state.py` | 2,830 | Image labeling state |
| `video_editor.py` | 2,262 | Video labeling editor UI |
| `video_state.py` | 4,029 | **Largest file in project** — video labeling state |
| `tools.py` | 50 | Tool constants (box, select, etc.) |

### `LabelingState` (image) — Key Methods
| Method | Description |
|--------|-------------|
| ⭐ `load_image(image)` | Select image to label |
| ⭐ `handle_new_annotation(data_json)` | New box drawn on canvas (from JS) |
| ⭐ `save_annotations()` | Non-blocking background save to R2 + Supabase |
| ⭐ `load_annotations_from_r2(image_id)` | Load with cache → Supabase → R2 fallback |
| ⭐ `navigate_back()` | Save + navigate with thumbnail generation |
| `to_yolo_format()` / `from_yolo_format(txt)` | YOLO format conversion |
| `toggle_focus_mode()` | Hide panels for pure annotation |

### `VideoLabelingState` (in `video_state.py`) — Key Methods
| Method | Description |
|--------|-------------|
| ⭐ `load_video(video)` | Load video + keyframes |
| ⭐ `save_keyframe_annotations()` | Save current keyframe annotations |
| ⭐ `handle_new_annotation(data_json)` | New box on video keyframe |
| ⭐ `extract_keyframes()` | Extract keyframes from video via FFmpeg |
| ⭐ `start_autolabel()` | Auto-label video keyframes |

---

## `modules/training/` — Training Dashboard

### Files
| File | Lines | Purpose |
|------|-------|---------|
| `dashboard.py` | 2,978 | Training dashboard UI (config, runs, metrics) |
| `state.py` | 2,906 | Training state |
| `run_detail.py` | 1,538 | Training run detail page (logs, metrics, models) |

### `TrainingState` — Key Methods
| Method | Description |
|--------|-------------|
| ⭐ `load_dashboard()` | Load project, datasets, training history, preferences |
| ⭐ `start_training()` | Dispatch training job (detection or classification) |
| ⭐ `polling_training()` | Poll training run progress |
| ⭐ `toggle_dataset(dataset_id)` | Toggle dataset selection for training |
| ⭐ `promote_model_to_api(run_id, slug)` | Promote trained model to REST API |
| `save_training_prefs()` | Save config preferences |
| `set_epochs/batch_size/model_size(...)` | Config setters (boilerplate) |

---

## `modules/api/` — API Key Management

### Files
| File | Lines | Purpose |
|------|-------|---------|
| `page.py` | 893 | API settings page UI |
| `state.py` | 479 | API management state |

### `ApiState` — Key Methods
| Method | Description |
|--------|-------------|
| ⭐ `load_api_settings()` | Load API models + keys |
| ⭐ `create_api_key(name)` | Generate new API key |
| ⭐ `revoke_api_key(id)` | Revoke key |
| ⭐ `update_api_model(id, updates)` | Update model slug/description |

---

## `components/` — Shared Reusable Components

| File | Lines | Purpose |
|------|-------|---------|
| `card.py` | 131 | Generic card container |
| `compute_target_toggle.py` | 109 | Cloud/local GPU toggle (used in training + inference) |
| `context_menu.py` | 225 | Right-click context menus |
| `nav_header.py` | 305 | Top navigation bar (SAFARI brown header + admin access) |
| `upload_zone.py` | 593 | Drag-and-drop upload with duplicate detection |

---

## `assets/` — Client-Side JavaScript

These are loaded globally in `safari/safari.py` via `head_components`.

| File | Purpose |
|------|---------|
| `canvas.js` | Labeling canvas — bounding box drawing, zoom, pan (2,687 lines) |
| `inference_player.js` | Video inference playback with frame-level overlay rendering |
| `selection_handler.js` | Long-press and range selection for image grids |
| `session_manager.js` | Token refresh, session stability, keep-alive (reads `window.__SAFARI_CONFIG`) |
| `global_shortcuts.js` | Global keyboard shortcuts (H for dashboard) |
| `labeling_shortcuts.js` | Labeling-specific shortcuts |
| `autoscroll.js` | Auto-scroll for training/autolabel log areas |
| `safari_fonts.css` | Google Fonts import (Poppins) |

---

## `safari/safari.py` — App Entry Point

This file:
1. **Imports all page modules** to register their routes (imports are side-effect based)
2. **Defines the `index()` page** — redirects to `/login` or `/dashboard`
3. **Injects `window.__SAFARI_CONFIG`** — Supabase URL + anon key from `.env`
4. **Configures the Reflex app** — light theme (SAFARI Naturalist), Poppins font, global JS scripts

### Registered Routes (in import order)
| Import | Route |
|--------|-------|
| `modules.auth.login` | `/login` |
| `modules.auth.dashboard` | `/dashboard` |
| `modules.projects.projects` | `/projects` |
| `modules.projects.project_detail` | `/projects/[id]` |
| `modules.labeling.editor` | `/label/[project_id]/[dataset_id]` |
| `modules.labeling.video_editor` | `/label-video/[project_id]/[dataset_id]` |
| `modules.training.dashboard` | `/training/[project_id]` |
| `modules.training.run_detail` | `/training/[project_id]/run/[run_id]` |
| `modules.inference.playground` | `/inference` |
| `modules.inference.result_viewer` | `/inference/result/[result_id]` |
| `modules.api.page` | `/api-settings` |
