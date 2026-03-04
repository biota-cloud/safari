# Architecture Improvement Roadmap

> **Goal**: Make the codebase more modular so adding new models/technologies requires minimal changes across files.  
> **Approach**: Incremental refactoring with independent, testable checkpoints.

---

## Phase A: Model Registry (Foundation)

Centralize model metadata and loading logic to eliminate scattered loader code.

### A1: Create Model Registry Module
- [x] Create `backend/model_registry.py` with `ModelInfo` dataclass
- [x] Define registry entries for: `yolo-detect`, `yolo-classify`, `convnext-classify`, `sam3-image`, `sam3-video`
- [x] Implement `get_model_info(model_type: str)` → `ModelInfo`
- [x] Implement `load_model(model_type: str, path: str)` → loaded model
- [x] Add unit tests for registry lookups

### A2: Migrate Modal Jobs to Use Registry
- [x] Update `hybrid_infer_job.py` to use `load_classifier()` for classifier
- [x] Update `hybrid_infer_job.py` to use `load_classifier()` for SAM3
- [x] Update `train_classify_job.py` to use registry for backbone detection (N/A - uses pretrained)
- [x] Verify inference still works (Cloud)

### A3: Migrate Remote Workers to Use Registry  
- [x] Update `remote_hybrid_infer.py` to use shared registry
- [x] Update `remote_train_classify.py` to use shared registry (N/A - uses pretrained)
- [x] Verify inference still works (Local GPU)

**Checkpoint A**: Registry is source of truth for model loading. Adding new backbone = 1 registry entry.

---

## Phase B: Unified Inference Router

Replace fragmented dispatch logic with single entry point.

### B1: Create Inference Router Module
- [x] Create `backend/inference_router.py` with `InferenceConfig` dataclass
- [x] Define registry entries for: `yolo-detect`, `yolo-classify`, `convnext-classify`, `sam3-image`, `sam3-video`
- [x] Implement `dispatch_inference(config, **params)` → routes to Modal or SSH
- [x] Add unit tests for routing logic (13 tests)

### B2: Integrate Router into InferenceState
- [x] Update `_run_image_inference()` to use `dispatch_inference()`
- [x] Update `_run_batch_inference()` to use `dispatch_inference()`
- [x] Verify inference still works (Cloud)

### B3: Add YOLO Local GPU Support (via Router)
- [x] Create `remote_yolo_infer.py` mirroring `infer_job.py`
- [x] Router automatically routes to SSH worker when `compute_target: local`
- [ ] Test: YOLO inference on Local GPU — **DEFERRED** (manual verification later)

**Checkpoint B**: All inference goes through one router. Adding new flow = implement job + register.

---

## Phase C: Annotation Access Service

Standardize annotation retrieval and mutation.

### C1: Create Annotation Service Module
- [x] Create `backend/annotation_service.py`
- [x] Implement `get_annotations_for_dataset(dataset_id)` → unified format
- [x] Implement `get_annotations_for_training(dataset_ids, include_r2=True)`
- [x] Implement `save_annotations(image_id, annotations)` with R2+Supabase sync

### C2: Migrate Annotation Reads
- [x] Update `get_image_class_counts_from_annotations()` to use service
- [x] Update `get_combined_class_counts_for_datasets()` to use service
- [x] Update training jobs to use `get_annotations_for_training()` — N/A: annotations already passed as param

### C3: Migrate Annotation Writes
- [x] Update `LabelingState` save logic to use service
- [x] Update autolabel result persistence to use service (via state classes)
- [x] Consolidate class rename/delete logic into service

**Checkpoint C**: Single interface for all annotation access. Class operations in one place.

---

## Phase D: Shared Core Pattern

Extract shared logic from Modal/Remote pairs to eliminate manual parity.

### D1: Create Core Modules ✅
- [x] Create `backend/core/` directory
- [x] Extract `image_utils.py` with `crop_from_box`, `crop_image_from_annotation`, `download_image`
- [x] Extract `classifier_utils.py` with `load_classifier`, `load_convnext_classifier`, `classify_with_convnext`

### D2: Extract Hybrid Inference Pipeline ✅
- [x] Create `backend/core/hybrid_infer_core.py` (~350 lines of shared logic)
- [x] Refactor Modal `hybrid_infer_job.py` (~260→30 lines)
- [x] Refactor `remote_hybrid_infer.py` (~230→50 lines)
- [x] Fixed legacy bug: mask extraction now works on local GPU

### D3: Extract Training Pipeline (future)
- [ ] Create `backend/core/train_core.py`
- [ ] Refactor training Modal jobs and remote workers

**Checkpoint D**: Hybrid inference logic in single source of truth. ~480 lines deduplicated.

---

## Phase E: Tech Debt Cleanup

Address known issues documented in master plan.

### E1: Remove Redundant class_name from Annotations
- [x] Create migration script to test annotation format change
- [x] Update annotation save logic to store `class_id` only
- [x] Update display logic to resolve `class_name` from `projects.classes`
- [x] Update class rename logic (now only updates project, not annotations)
- [x] Run migration on test dataset

### E2: Standardize Coordinate Format
- [x] Audit all prediction formats for consistency
- [x] Document canonical format in architecture_reference.md
- [x] Add validation in annotation service

**Checkpoint E**: Tech debt resolved. Class operations are O(1) not O(annotations).

---

## Progress Tracking

| Phase | Status | Started | Completed |
|-------|--------|---------|-----------|
| A: Model Registry | ✅ Complete | 2026-01-17 | 2026-01-17 |
| B: Inference Router | ✅ Complete | 2026-01-17 | 2026-01-17 |
| C: Annotation Service | ✅ Complete | 2026-01-17 | 2026-01-17 |
| D: Shared Core | ✅ Complete | 2026-01-17 | 2026-01-17 |
| E: Tech Debt | ✅ Complete | 2026-01-17 | 2026-01-17 |

---

## Notes

- Each phase is independent and can be paused/resumed
- Checkpoints ensure working state before moving on
- Use `/wrap-up` after each sub-task (A1, A2, etc.)
- Use `/commit` after each checkpoint
