# Training

> Train detection, classification, and segmentation models on your labeled datasets.

---

## Training Dashboard Overview

Navigate to your project, then click the <span class="icon-btn"><i data-lucide="brain"></i> Training</span> tab. The training dashboard has two main areas:

![Training dashboard](screenshots/Training_dashboard.png)

| Area | Purpose |
|------|---------|
| **Run Configuration** (left panel) | Select datasets, choose model type and hyperparameters, set compute target, and launch training |
| **Run History** (right panel) | View past and active training runs, metrics, logs, and artifacts |

---

## Selecting Datasets

The <span class="icon-btn"><i data-lucide="database"></i> Datasets</span> section lists all datasets in your project. Toggle the checkbox to include or exclude each dataset.

![Datasets selection](screenshots/Training_datasets_card.png)

- Each dataset shows the **labeled image count** and a **usage tag** (train / val / test)
- Change the usage tag via the dropdown — if you assign explicit validation datasets, the dashboard shows a notice
- The stats row below summarizes: **selected datasets**, **total labeled images**, and **class distribution**

> **Tip**: Select multiple datasets to combine their data for a larger training set. At least one dataset with labeled images must be selected.

---

## Detection Training (YOLO)

Select **Detection** in the mode selector to configure a YOLO object detection model.

![Detection config](screenshots/Training_detection_card.png)

### Hyperparameters

| Parameter | Options | Description |
|-----------|---------|-------------|
| **Epochs** | 1–500 (stepper) | Number of complete passes through the training data |
| **Model Size** | n / s / m / l | YOLOv11 backbone size — **n**ano is fastest, **l**arge is most accurate |
| **Batch Size** | 8 / 16 / 32 | Images per training step — larger batches need more GPU memory |
| **Patience** | 0–100 (stepper) | Early stopping — training stops if no improvement for this many epochs. 0 = disabled |
| **Optimizer** | auto / SGD / Adam / AdamW | Optimization algorithm. **auto** lets YOLO choose |

---

## Classification Training

Select **Classification** in the mode selector. Classification models learn to identify species from cropped bounding box regions.

![Classification config](screenshots/Training_classification_card.png)

### Backbone Selection

| Backbone | Sizes | Best For |
|----------|-------|----------|
| **YOLO-Classify** | n / s / m / l | Fast training, lightweight models |
| **ConvNeXt** | tiny / small / base / large | Higher accuracy, transfer learning from ImageNet |

### Additional Parameters

| Parameter | Options |
|-----------|---------|
| **Image Size** | 224 / 256 / 384 / 512 |
| **Batch Size** | 16 / 32 / 64 / 128 |
| **Epochs** | 1–500 (stepper) |

> Classification training crops each annotated bounding box into its own image and trains a classifier on those crops.

---

## SAM3 Fine-Tuning

Select **SAM3** in the mode selector to fine-tune the SAM3 segmentation model for your specific domain.

![SAM3 config](screenshots/Training_sam3_card.png)

SAM3 fine-tuning is **cloud-only** — it requires an A100 GPU and runs exclusively on Modal infrastructure.

### Parameters

| Parameter | Options | Description |
|-----------|---------|-------------|
| **Max Epochs** | stepper | Maximum training epochs |
| **Patience** | stepper | Early stopping patience (0 = disabled) |
| **Images** | 0 / 10 / 50 / 100 | Images per class for few-shot training. 0 = use all |
| **LR Scale** | 0.01 – 1.0 | Learning rate scale factor. Lower = gentler fine-tuning |
| **Prompt** | text input | Concept noun SAM3 learns to detect (e.g., *"animal"*) |

> Use a general domain-level prompt like *"animal"* rather than individual species names — this avoids running SAM3 once per class at inference time.

---

## Compute Target

Below the model configuration, the **Compute Target** toggle lets you choose where training runs:

- <span class="icon-btn"><i data-lucide="cloud"></i> Cloud</span> — Runs on Modal GPU infrastructure (A10G or L40S). No setup required, pay-per-use.
- <span class="icon-btn"><i data-lucide="monitor"></i> Local GPU</span> — Runs on a connected GPU machine on your network. Select the target from the dropdown.

> SAM3 fine-tuning is always Cloud (A100 GPU).

---

## Starting Training

Once configured, click <span class="icon-btn solid-green"><i data-lucide="play"></i> Start Detection Training</span> (or the equivalent for classification/SAM3). The button text changes to match the selected mode.

The status line below the button shows:
- **"Ready: X images"** in green when datasets are selected
- **"Select labeled datasets"** in orange when nothing is selected

---

## Monitoring a Training Run

Active runs appear in the <span class="icon-btn"><i data-lucide="history"></i> History</span> table on the right side of the dashboard.

![Training runs](screenshots/Training_runs.png)

### Run History Table

The table displays:
- **Date/Time** — when the run was created
- **Name** — editable alias for easy identification
- **Status** — <span class="icon-btn solid-green">Completed</span>, <span class="icon-btn" style="background:#3e63dd;border-color:#3e63dd;color:#fff">Running</span>, or <span class="icon-btn" style="background:#e5484d;border-color:#e5484d;color:#fff">Failed</span>
- **Type** — Detection / Classification / SAM3
- **Tags** — Organizational labels (Production, Experiment, Baseline, Best)
- **Epochs** — How many epochs were run
- **Key metric** — mAP@50 for detection, Top-1 accuracy for classification

Use the filter dropdowns (Status, Tag, Type, Backbone) to narrow results. Click any row to see details.

### Live Logs

When a run is in progress, the <span class="icon-btn"><i data-lucide="terminal"></i> Logs</span> panel shows real-time training output with auto-scroll.

---

## Training Results

When you select a completed run, the detail panel shows:

![Run detail](screenshots/Training_run_detail.png)

### Metrics

Metrics vary by model type:

| Detection | Classification | SAM3 |
|-----------|---------------|------|
| mAP@50 | Top-1 Accuracy | Mask Loss |
| mAP@50-95 | Top-5 Accuracy | GIoU Loss |
| Precision | Loss | Class Loss |
| Recall | Val Loss | Total Loss |

### Download Weights

Click <span class="icon-btn"><i data-lucide="download"></i> best.pt</span> or <span class="icon-btn"><i data-lucide="download"></i> last.pt</span> to download model weight files.

---

## Training Artifacts

The <span class="icon-btn"><i data-lucide="images"></i> Artifacts</span> gallery shows visual outputs from the training run:

![Artifacts](screenshots/Training_run_artifacts.png)

- **Results** — Training curves (loss, metrics over epochs)
- **Confusion Matrix** — Class-level prediction accuracy
- **F1 Curve** — F1 score vs. confidence threshold
- **PR Curve** — Precision-Recall curve

Click any thumbnail to open the full-resolution image.

---

## What To Do With Your Model

After training completes, the run detail page shows four action buttons at the top:

- <span class="icon-btn outline-green"><i data-lucide="plug"></i> API</span> — Promote the model to a REST API endpoint for external applications and SAFARIDesktop
- <span class="icon-btn outline-green"><i data-lucide="plus"></i> Playground</span> — Add to the [Model Playground](06_playground.html) for interactive testing on new images and video
- <span class="icon-btn outline-purple"><i data-lucide="sparkles"></i> Autolabel</span> — Add to the [Autolabel](04_autolabeling.html) model list for automated annotation of unlabeled datasets
- <span class="icon-btn outline-green"><i data-lucide="download"></i> Download</span> — Download model weight files (best.pt or last.pt)

Each dropdown lets you choose between the **best** checkpoint (recommended) or the **last** epoch weights.

### Promoting to API

Click <span class="icon-btn outline-green"><i data-lucide="plug"></i> API</span> to open the promotion modal:

![API promote modal](screenshots/API_modal.png)

1. Enter an **API Slug** — a URL-safe identifier (e.g., *"lince-detector-v2"*)
2. Set a **Display Name** (e.g., *"Lince Detector v2"*)
3. Add an optional **Description**
4. Click <span class="icon-btn solid-green"><i data-lucide="rocket"></i> Promote to API</span>

The model is then available at your project's API endpoint and in SAFARIDesktop's model selector.
