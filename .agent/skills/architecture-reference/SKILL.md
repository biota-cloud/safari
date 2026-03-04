---
name: architecture-reference
description: Consult this skill before modifying Modal jobs, remote workers, inference flows, training pipelines, or model loading. Triggers on backend/modal_jobs/, scripts/remote_workers/, InferenceState, or TrainingState changes.
---

# Architecture Reference Skill

## Goal
Ensure the agent consults `docs/architecture_reference.md` before making architectural changes, using the correct section for the work at hand.

## When to Use
Before modifying any of these areas:
- `backend/modal_jobs/*.py` — Modal GPU jobs
- `scripts/remote_workers/*.py` — Local GPU workers
- `modules/inference/state.py` — Inference routing
- `modules/training/state.py` — Training orchestration
- `backend/job_router.py` — Compute target dispatch

## Instructions

### Step 1: Read the Relevant Section

| Work Area | Section in `docs/architecture_reference.md` |
|-----------|---------------------------------------------|
| Model loading | **Model Loading Reference** (lines 179-215) |
| Inference changes | **Inference Flows Reference** (lines 35-131) |
| Training changes | **Training Flows Reference** (lines 133-152) |
| Autolabeling | **Autolabeling Flows Reference** (lines 154-176) |
| Modal/Remote parity | **File Parity Matrix** (lines 351-365) |
| API changes | **API Infrastructure Reference** (lines 218-251) |
| Debugging issues | **Debugging Checklist** (lines 418-428) |
| Common gotchas | **Common Gotchas Quick Reference** (lines 333-348) |

### Step 2: Check Parity Requirements

If modifying a Modal job, check the **File Parity Matrix** to see if a corresponding remote worker needs the same change:

| Modal Job | Remote Worker |
|-----------|---------------|
| `train_job.py` | `remote_train.py` |
| `train_classify_job.py` | `remote_train_classify.py` |
| `autolabel_job.py` | `remote_autolabel.py` |
| `hybrid_infer_job.py` | `remote_hybrid_infer.py` |

### Step 3: Verify Model Patterns

For model loading changes, confirm:
- File extension: `.pt` (YOLO) vs `.pth` (ConvNeXt)
- Loader function: `YOLO()` vs `torch.load()` + `timm.create_model()`
- SAM3 path: Always explicit, never auto-download

## Constraints

> [!CAUTION]
> **Never** modify inference jobs without checking the parity matrix.
> **Always** pass explicit SAM3 model path — never rely on auto-download.
> **Check** backbone extension before loading models (`.pt` vs `.pth`).

## Resources
- [Architecture Reference](file:///Users/jorge/PycharmProjects/Tyto/docs/architecture_reference.md)
- [Architecture Roadmap](file:///Users/jorge/PycharmProjects/Tyto/.agent/architecture-roadmap.md)
