# 📋 Tyto Wishlist

> Feature requests, improvements, and ideas for future development.
> Use `/add-wishlist` workflow to add new items.

---

## 🎨 UI/UX

### W004 — Replace hardcoded hex colors with styles.py constants
- **Context**: ~30 hardcoded hex colors found across `/modules/` (e.g., `#A78BFA`, `#0d1117`, `#00ff00`)
- **Goal**: All colors should reference `styles.py` constants for consistency
- **Missing constants to add**: `CODE_BG`, `CODE_TEXT`, `DETECTION_BORDER`
- **Files affected**: `run_detail.py`, `dashboard.py`, `editor.py`, `video_editor.py`, `result_viewer.py`

## 🏷️ Labeling & Editor

*No items yet*

---

## 🧠 Training & Models

### W005 — ConvNeXt Training Artifacts & Metrics (Parity with YOLO)
- **Context**: YOLO classification training outputs rich artifacts (results.csv, loss/accuracy charts, confusion matrices, augmented sample grids). ConvNeXt training currently outputs **only weights** (`best.pth`, `last.pth`) — no metrics CSV, no charts, no confusion matrix, no augmented samples. The training loop already computes `train_loss`, `val_loss`, and `val_accuracy` each epoch but doesn't save them.
- **Goal**: Bring ConvNeXt training output to parity with YOLO, enabling users to understand training quality.
- **Artifacts to generate**:
  1. **`results.csv`** — per-epoch: `epoch, train/loss, val/loss, val/accuracy, learning_rate` (write each row during training)
  2. **`results.png`** — matplotlib charts: train vs val loss curves, val accuracy curve, LR schedule (plot at end of training)
  3. **`confusion_matrix.png`** + **`confusion_matrix_normalized.png`** — run best model on val set after training, use `sklearn.metrics.confusion_matrix`, plot with matplotlib/seaborn heatmap
  4. **`train_batch.jpg`** — grid of augmented training samples: grab one batch from `train_loader`, un-normalize with `torchvision.utils.make_grid()`, save before training starts
  5. **Top-5 accuracy** — during validation, use `outputs.topk(5)` instead of just `argmax(1)` (currently hardcoded to `0.0`)
- **Files to modify**:
  - `backend/core/train_classify_core.py` → `run_convnext_training()` (add instrumentation to training loop + post-training evaluation)
  - `backend/core/train_classify_core.py` → `collect_classification_artifacts()` (add ConvNeXt artifact paths to upload list)
- **Key point**: No changes to the training algorithm — this is pure instrumentation (recording what's already happening + visualizing at end). Artifacts upload to R2 via the existing artifact collection pattern.

### W007 — Hybrid Autolabel Pipeline (Detection + Classification)
- **Context**: Autolabel currently supports SAM3 (text/bbox/point) and YOLO detection, but not hybrid (detect → crop → classify). Hybrid inference only exists in the Playground module.
- **Goal**: Enable autolabel to use a detection model + classification backbone (ConvNeXt/YOLO-cls) to produce labeled annotations with class names from the classifier.
- **Architecture**:
  1. YOLO detection pass → bounding boxes
  2. Crop each detection from the image
  3. ConvNeXt/YOLO-cls classification on each crop → class assignment
  4. Save combined annotations (bbox + class) to Supabase/R2
- **Files to modify**:
  - `backend/modal_jobs/autolabel_job.py` — add hybrid mode, handle `.pth` model loading
  - `backend/core/autolabel_core.py` — add `run_hybrid_autolabel()` core function
  - `modules/labeling/state.py` — expose hybrid model selection in autolabel UI
- **Dependencies**: Shared Core Pattern must be followed for Modal/Local GPU parity
- **Priority**: Medium
- **Added**: 2026-03-05


---

## 🔧 Infrastructure

### W002 — App-Driven Machine Provisioning (Zero-Terminal Setup)
- **Context**: Current local GPU setup requires SSH key exchange and terminal commands
- **Goal**: Non-technical users can add a local GPU machine from the Tyto web app with just IP/username/password
- **Flow**:
  1. User enters IP, username, one-time password in "Add Machine" modal
  2. Tyto SSHes in, copies its own key, runs `install.sh`
  3. Credentials (R2/Supabase) auto-configured from user's account
  4. Machine appears in project dropdown, ready to use
- **Benefit**: Zero terminal work for end users — fully in-app experience
- **See also**: Roadmap Phase L8 (future)

### W003 — Fully Local Storage for Local GPU Mode
- **Context**: Current remote worker scripts still use Supabase/R2 for logging and file storage
- **Goal**: When "Local GPU" is selected, ALL storage should be local — only GPU compute is remote
- **Architecture**:
  - **Storage**: SQLite database + local filesystem (instead of Supabase + R2)
  - **Logging**: Local log files (not Supabase)
  - **Models/Data**: Tyto's local storage directory (not R2)
  - **GPU Machine**: Only used for processing, files transferred via SSH/rsync
- **Benefit**: True offline capability, no cloud dependencies, faster I/O
- **Implication**: Worker scripts need two modes — cloud-backed vs fully-local

---

## 📱 Desktop Client

*No items yet*

---

## ❓ Questions

*No items yet*

---

## ✅ Completed

### W006 — Enhanced ConvNeXt Data Augmentation ✓
- **Completed**: 2026-02-08
- Added `ColorJitter`, `RandomRotation(15)`, `GaussianBlur(p=0.1)`, `RandomErasing(p=0.1)` to ConvNeXt training pipeline
- Raised `RandomResizedCrop` lower bound from 0.08 → 0.5 for tight SAM3 crops

### W001 — Replace emoji icons with Lucide icons in processing target badges ✓
- **Completed**: 2026-01-18
- Replaced `☁️`/`🖥️` emojis with `rx.icon("cloud")`/`rx.icon("monitor")` across all 4 locations

---

## 📦 Legacy Wishes
-Data augmentation using segmentation masks. Divide rect in 4 and choose biggest are from segmentation
-
- Keep track of sam3 animal detections vs classifier detections, we need to keep unclassified detections in the dataset.
- We could use sam3 masks to split the label in 4 squares, and use the square with the most pixels from the mask to classify it. Because cameras can film only parts of the animal, this would make the model more robust. Can be done with code at trainning time, or we create at trainning time. Data augmentation technique.
- Hybrid video: Make video tracking more robust, if we mess first detection, its all wrong. Maybe track, get biggest box and classify it.
- Class tag should always be visible in playground players, sometimes it is hidden at the top. Must detect if it is hidden and show it.
- Possibility to use sam3 tracking with fish videos
- Test dataset run
- How to handle explicit validation dataset in multiple classes training?
- Autolabels job when no class is created yet, create class in project.
- Combine dataset to decluter UI;
- Improve feedback during upload in dataset detail. Can be text informing what is currently being uploaded.
- Add notes to dataset name, like in project detail.
- Remove class management from dataset detail.
- Improve label management, should be easy to delete all labels in a dataset in case of autolabel undesired results.
- How should we handle multiple training runs?
- Change labels from txt to json only in supabase, we create on the fly with trainning modal jobs using the conversion code we already have.
- We need to manage when autolabel jobs have errors. I canceled the job directly in modal, but because in the autolable table it is still running, when I try to open the autolabel modal in the editor, it shows a running job, making it impossible to trigger a new one.
- In video editor, have keyframe count on the side of label count
- For trainning, add check if there are empty images or classes
- Timeline zoom, check if some code exists to handle this.
- Right click on label to change class (open small modal, same style as change class)
- Improve Autoscroll live log areas: Logs should scroll down as we pull more logs. We have one livelog area in the autolabel and another in the training dashboard.
- Location: Both editors and class manager in project detail. Step and total should both be inputs, and could update each other as we slide. If we change one, the other should update to match. We should only be able to change the total if we have a valid interval with start and end.
- Auto-resize videos and images at dataset detail upload async
- Project/dataset backup and import
- Label creation failed for yolo zip upload (must be images dataset)
- In supabase there is a toast saying "Unrestricted" in red
- Upload progress in dataset detail?
- Compare training runs
- Yolo dataset upload fix
- Regular cleanup for interrupted runs or sessions, delete from R2 and supabase. General sanity check script?
- Concurrent uploads in yolo dataset upload to r2?
