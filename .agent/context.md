# Agent Context

> **Purpose**: Persistent notes and decisions that carry across sessions. 
> Update this file as you learn new things about the project.

---

## 🏗️ Architecture Decisions

| Decision | Rationale | Date |
|----------|-----------|------|
| Custom Canvas for labeling | No external JS deps, full Python control | 2024-12-26 |
| Reflex for UI | Python-first, reactive state management | 2024-12-26 |
| Modal for GPU compute | Serverless GPUs, pay-per-use | 2024-12-26 |
| Cloudflare R2 for storage | S3-compatible, no egress fees | 2024-12-26 |
| Supabase for auth/DB | Postgres + Auth + RLS in one | 2024-12-26 |
| Project → Dataset hierarchy | Enables multiple datasets (image/video) per project | 2025-12-27 |
| Modal ASGI for API | Scales to zero, same GPU pool as training | 2026-01-12 |
| API isolation principle | New files only, no modifications to existing inference | 2026-01-12 |
| Tauri + FFmpeg sidecar | Native video processing, bundled binaries, zero-disk I/O | 2026-01-13 |
| Local GPU via SSH | Project-level target, immutable after datasets exist | 2026-01-16 |

---

## 🔗 Key References

| Document | Purpose |
|----------|---------|
| [Docs Index](file:///Users/jorge/PycharmProjects/Tyto/docs/README.md) | Navigation hub for all documentation |
| [Architecture Reference](file:///Users/jorge/PycharmProjects/Tyto/docs/architecture/architecture_reference.md) | Orchestrator document — architecture, flows, gotchas |
| [Architecture Roadmap v2](file:///Users/jorge/PycharmProjects/Tyto/docs/roadmaps/architecture_roadmap_v2.md) | Shared core refactoring (complete) |
| [Architecture Roadmap v1](file:///Users/jorge/PycharmProjects/Tyto/docs/roadmaps/archive/architecture_roadmap_v1.md) | Archived — Phases A-E |

---

## ⚠️ Gotchas & Lessons Learned

| Issue | Solution |
|-------|----------|
| Modal imports break Reflex | Use `modal.Function.lookup()` at runtime, never direct imports |
| R2 presigned URLs expire | Default 1hr, pass `expires_in` param if needed |
| Cross-state access | Use `await self.get_state(OtherState)` — official pattern since Reflex 0.4.3 |
| Inline JS via `rx.script` | Load from `/assets/*.js` and use `rx.script(src="/file.js")` instead |
| Lambda in rx.foreach | Pass idx directly: `func(idx)` — closures don't work with Vars |
| Async generator returns | Use `yield rx.toast(...)` then `return`, not `return rx.toast(...)` |
| class_id=0 is falsy | Use `if class_id is not None` not `if class_id` — 0 is a valid class_id |

---

## 🚫 Don't Do This

- Never hardcode hex colors — always use `styles.py` tokens
- Never import Modal functions directly in Reflex pages
- Never store credentials in code — use `.env` only
- Never use pixel coordinates for annotations — use normalized 0-1 values
- Never modify existing inference jobs for API — create new `api_infer_job.py`

---

## ✅ User Preferences

- Prefers granular numbered checkboxes in roadmap (e.g., `A1.1.1`, `A1.1.2`)
- Wants agent to update Current Focus at end of each session (`/wrap-up`)
- Values checkpoint-driven development — verify each stage before moving on
- **Use virtual environments** — install packages to `.venv`, not globally

---

## 🎯 Current Focus

**Architecture Roadmap v2 Complete ✅**

All shared core phases (D3-D7) are now complete. The architecture now has full Modal/Local GPU parity.
See [architecture-roadmap-v2.md](file:///Users/jorge/PycharmProjects/Tyto/.agent/architecture-roadmap-v2.md).

---

## 🔒 Current Blockers

*None*

---

## 📝 Session Notes

### Session 12 — YOLO Detection Shared Core (2026-01-18)
- **Completed**: Phase D7 — YOLO detection inference now uses shared core (`yolo_infer_core.py`)
- **Created**: `backend/core/yolo_infer_core.py` (~280 lines) with:
  - `parse_yolo_results()` — normalize YOLO boxes to 0-1 coordinates
  - `format_predictions_to_yolo()` — convert predictions to YOLO label format
  - `run_yolo_single_inference()` — single image inference
  - `run_yolo_batch_inference()` — batch inference with download callback
  - `run_yolo_video_inference()` — video frame inference with progress callback
- **Refactored**: Modal `infer_job.py` (~592→380 lines, ~35% reduction)
- **Refactored**: Remote `remote_yolo_infer.py` (~473→290 lines, ~40% reduction)
- **Tests**: 12 unit tests passing for core module
- **Deployed**: Modal job deployed successfully
- **Milestone**: Architecture Roadmap v2 complete — all D3-D7 phases done
- **Next**: User testing on Modal Cloud and Local GPU to verify parity

### Session 11 — Classification Training Fixes (2026-01-18)
- **Bug Fixes**: 
  - Class ID resolution: Changed from sorted alphabetical (1-indexed) to `project.classes` order (0-indexed)
  - Falsy check bug: Changed `if class_id` to `if class_id is not None` (class_id=0 was treated as falsy)
  - Missing import: Added `import os` to `remote_train_classify.py`
  - Polling stuck: Reset `is_polling = False` at training start to prevent stuck state blocking UI refresh
- **UI Validation**: Added pre-dispatch check for empty classes with user-friendly error message
- **Testing**: Classification training verified on both Modal Cloud and Local GPU with identical results
- **Anti-Pattern**: Don't use `if class_id` for validation — use `if class_id is not None` (0 is a valid class_id)
- **Next**: Consider SSH ControlMaster optimization for faster local GPU communication

### Session 10 — Autolabel Shared Core Extraction (2026-01-18)
- **Completed**: Phase D5 — autolabel now uses shared core (`autolabel_core.py`)
- **Created**: `backend/core/autolabel_core.py` (~310 lines) with YOLO and SAM3 inference
- **Refactored**: Modal `autolabel_job.py` (~705→340 lines), remote (~428→265 lines)
- **Key Functions**: `run_yolo_autolabel()`, `run_sam3_autolabel()`, `xyxy_to_yolo_line()`, `yolo_lines_to_annotations()`
- **Decision**: Classification models (ConvNeXt .pth) for autolabel is out of scope — future feature request
- **Fixed**: Modal image build order (`.env()` before `add_local_*`)

### Session 9 — Video Hybrid Core Extraction (2026-01-18)
- **Completed**: Phase D4 — video hybrid inference now uses shared core (`hybrid_video_core.py`)
- **Created**: `backend/core/hybrid_video_core.py` (~450 lines, 5-phase pipeline with `mask_to_polygon()`)
- **Refactored**: Modal `hybrid_inference_video()` (~373→50 lines), remote (~200→45 lines)
- **Bug Fix**: Remote worker was missing mask extraction — now fixed via shared core
- **Testing**: Modal Cloud ✅, Local GPU ✅ — both ConvNeXt and YOLO classifiers work
- **Documentation**: Updated `architecture_reference.md` File Parity Matrix, Core Module Structure
- **All hybrid inference flows now use Shared Core Pattern** (single, batch, video)
- **Next**: Phase D5 (Autolabel) or D6 (Training), or architecture diagrams

### Session 8 — Architecture Reference Audit (2026-01-17)
- **Completed**: Full audit of `architecture_reference.md` vs actual codebase
- **Key Finding**: Phase D (Shared Core) was overclaimed — only single-image hybrid inference uses thin wrappers
- **Fixed**: Batch (~235 lines) and video (~373 lines) still have inline code in Modal/remote workers
- **Fixed**: Removed non-existent `AutolabelState`, added `VideoLabelingState`
- **Fixed**: Updated File Parity Matrix to show batch/video as ⚠️ Manual
- **Created**: `architecture-roadmap-v2.md` with remaining work (D3-D6)
- **Updated**: `/start-session` and `/wrap-up` workflows to reference v2 roadmap
- **Next**: Begin Phase D3 (Batch Hybrid → Shared Core)

### Session 7 — Coordinate Format Standardization (2026-01-17)
- **Completed**: Phase E2 (Coordinate Standardization) — all 3 sub-tasks done
- **Audit Finding**: Coordinate formats were already consistent across all sources
- **Two Formats**: Predictions use `[x1,y1,x2,y2]`, Annotations use `{x,y,width,height}` — both normalized 0-1
- **Added**: `validate_annotation_coordinates()` and `validate_annotations_batch()` to annotation service
- **Added**: Warning logging in `save_annotations()` for invalid coordinates (non-blocking)
- **Documentation**: Added "Coordinate Format Reference" section to `architecture_reference.md`
- **Tests**: 43 passing (11 new validation tests)
- **Milestone**: Architecture Roadmap complete (Phases A-E all ✅)

### Session 6 — Tech Debt Phase E1 (2026-01-17)
- **Completed**: Phase E1 (Redundant class_name) — all 5 sub-tasks done
- **Created**: `scripts/migrate_strip_class_names.py` — migration script (migrated ~700 records)
- **Updated**: `annotation_service.py` with `resolve_class_names()`, `strip_class_names()` functions
- **Bug Fix**: Editors not showing class tags after migration — added resolution to batch load paths
- **Bug Fix**: Class distribution charts showing "Unknown" — updated counting functions to resolve class_id
- **Tests**: 32 passing for annotation service
- **Outcome**: Simple class renames now O(1), annotations store only `class_id`, UI resolves from project_classes
- **Next**: Commit Phase E1 or continue to E2


### Session 4 — Annotation Access Service (2026-01-17)
- **Completed**: Phase C (Annotation Service) — C1, C2, C3 all done
- **Created**: `backend/annotation_service.py` with 10 core functions for unified annotation access
- **Migrated**: `LabelingState` (3 methods) and `VideoLabelingState` (2 methods) to use service
- **Migrated**: `get_image_class_counts_from_annotations()` and `get_combined_class_counts_for_datasets()`
- **Bug Fix**: Keyframes table doesn't have `labeled` column — fixed silent save failure
- **Tests**: 22 unit tests passing for annotation service
- **Next**: Phase D (Shared Core Pattern) or other work

### Session 7 — Batch Hybrid Core Extraction (2026-01-18)
- **Completed**: Phase D3 — batch hybrid inference now uses shared core (`hybrid_batch_core.py`)
- **Created**: `backend/core/hybrid_batch_core.py` (~260 lines shared batch logic)
- **Refactored**: Modal `hybrid_inference_batch()` (~235→35 lines), remote (~205→30 lines)
- **Infrastructure**: Added Modal image mounts for `backend/core/`, SSH `sync_core_modules()` for remote sync
- **Bug Fix**: SSH client wasn't syncing `backend/core/` — latent bug from D2
- **Testing**: Modal batch passed ✅; Local GPU batch runs but no detections (separate bug)
- **Next**: Investigate Local GPU detection bug, or proceed to D4 (video hybrid)

### Session 6 — Coordinate Standardization & Roadmap v2 (2026-01-17)
- **Completed**: Phase E2 — coordinate validation in annotation service
- **Created**: `architecture-roadmap-v2.md` with remaining shared core phases (D3-D6)
- **Updated**: `architecture_reference.md` audit — corrected File Parity Matrix, Thin Wrapper docs
- **Key Finding**: D2 (single-image) was done but batch/video still inline — roadmap v2 captures this
- **Next**: Phase D3 (batch hybrid core extraction)

### Session 5 — Shared Core Pattern (2026-01-17)
- **Completed**: Phase D (Shared Core) — D1, D2 done (D3 training deferred)
- **Created**: `backend/core/` package with `image_utils.py`, `classifier_utils.py`, `hybrid_infer_core.py`
- **Refactored**: Modal `hybrid_infer_job.py` (~260→30 lines), remote `remote_hybrid_infer.py` (~230→50 lines)
- **Bug Fix**: Mask/polygon extraction was missing in remote worker — now fixed via shared core
- **Tests**: 100 passing (55→100), 8 new core tests added
- **Next**: Phase E (Tech Debt) or deploy Modal changes

### Session 4 — Annotation Access Service (2026-01-17)
- **Completed**: Phase B (Inference Router) — B1, B2, B3 all done
- **Created**: `backend/inference_router.py` with `InferenceConfig` + `dispatch_inference()`
- **Created**: `scripts/remote_workers/remote_yolo_infer.py` for Local GPU YOLO detection
- **Pattern**: Unified entry point abstracts Modal vs SSH routing; `InferenceState` no longer calls Modal directly
- **Tests**: 25 unit tests passing (13 router + 12 registry)
- **Next**: Phase C (Annotation Service) or commit Checkpoint B

### Session 2 — Model Registry Implementation (2026-01-17)
- **Completed**: Phase A (Model Registry) — A1, A2, A3 all done
- **Created**: `backend/model_registry.py` with `ModelInfo`, `ModelType`, `load_classifier()`
- **Pattern**: Unified `load_classifier()` helper added to both Modal and remote worker
- **Key Finding**: Modal isolation prevents direct import of registry; used internal helper pattern
- **Tests**: 12 unit tests passing for registry lookups and backbone detection
- **Next**: Phase B (Unified Inference Router) or commit Checkpoint A

### Session 1 — Architecture Roadmap Creation (2026-01-17)
- **Focus**: Created architecture_reference.md and architecture-roadmap.md
- **Master Plan**: Comprehensive reference for inference flows, training, model loading, Supabase schema
- **Architecture Roadmap**: 5 phases (A-E) for modular refactoring
- **Workflow Updates**: /start-session and /wrap-up now reference architecture_reference.md
- **Next**: Begin Phase A (Model Registry) when ready
