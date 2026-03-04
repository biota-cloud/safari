# 🧹 Technical Debt & Cleanup Backlog

> Track deprecation warnings, refactors, and cleanup tasks here.  
> Address these during dedicated cleanup sprints or when touching related code.

---

## High Priority (Address Soon)

- [ ] **Local GPU Batch No Detections**: Batch inference runs successfully on Local GPU but finds no detections — likely SAM3 path or prompt issue. Modal batch works fine. (2026-01-18)

---

## Medium Priority (Next Cleanup Sprint)

- [ ] **Modal Custom __init__ Deprecation**: `YOLOInference.__init__()` uses custom constructor — Modal recommends using `modal.parameter()` dataclass-style declarations instead. Affects `infer_job.py`. (2026-01-18)

---

## Low Priority (Nice to Have)

- [ ] **API Keys UX**: Add filter to hide revoked keys, or "Delete forever" option for cleanup (currently shown for audit purposes)
- [ ] **API Hybrid Config UI**: Add SAM3 prompt and classifier confidence settings to API page for classification models
- [ ] **Classification Models in Autolabel**: Support ConvNeXt `.pth` classifiers for autolabeling (currently only YOLO `.pt` detection models) (2026-01-18)

---

## Resolved ✅

- [x] **Redundant class_name in Annotations**: Annotations now store `class_id` only, resolved at display time (Phase E1, 2026-01-17)
- [x] **Coordinate Format Inconsistency**: Audited and documented — already consistent, added validation (Phase E2, 2026-01-17)
- [x] **Modal Deprecation**: `container_idle_timeout` → `scaledown_window` (fixed 2026-01-13)
- [x] **Modal Deprecation**: `allow_concurrent_inputs` → `@modal.concurrent` (fixed 2026-01-13)
