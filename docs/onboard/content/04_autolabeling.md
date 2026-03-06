# Autolabeling

> Use AI to pre-label your datasets automatically, then review and correct.

---

## What is Autolabeling?

Autolabeling uses AI models to automatically generate annotations for your dataset. Instead of drawing every bounding box by hand, the AI detects objects in your images and creates initial labels — you then review and correct as needed.

SAFARI offers two autolabeling modes:

- **SAM3** — Zero-shot detection using text prompts. No training required — describe what to find and SAM3 locates it.
- **YOLO** — Use a model you've already trained in SAFARI for fast, project-specific detection.

Autolabeling is available for both **image** and **video** datasets from within the editor.

---

## Opening the Autolabel Modal

From the editor toolbar, click the <span class="icon-btn icon-only outline-green"><i data-lucide="sparkles"></i></span> button to open the autolabel modal. The modal has two tabs at the top: **SAM3** and **YOLO Model**.

---

## SAM3 Mode

SAM3 performs zero-shot detection — it can find objects based on text descriptions without any prior training.

![SAM3 autolabel modal](screenshots/SAM3_autolabel_modal.png)

### Generation Options

Before entering prompts, choose what to generate:

- **Generate bounding boxes** — creates rectangular annotation boxes around detected objects
- **Generate masks** — creates polygon segmentation masks for each detection

You must select at least one option. Both can be enabled simultaneously.

> **Mask Fast Path**: If your images already have bounding box annotations and you only enable "Generate masks", SAM3 will generate masks directly from the existing boxes — no text prompts needed.

### Text Prompts

1. Enter comma-separated terms describing what to detect (e.g., *"lince, veado, javali"*)
2. A mapping section appears below, listing each prompt term with an <span class="icon-btn icon-only"><i data-lucide="arrow-right"></i></span> arrow pointing to a class dropdown
3. For each term, select the project class it should map to
4. All prompts must be mapped before you can start

### Confidence Threshold

Adjust the slider to set the minimum confidence (10%–90%) for detections to be kept. Higher values mean fewer but more confident detections; lower values catch more but may include false positives.

---

## YOLO Mode

Use a detection model you've previously trained in SAFARI.

![YOLO autolabel modal](screenshots/Yolo_autolabel_modal.png)

1. Select a model from the **"Choose a trained model..."** dropdown
2. Adjust the **confidence threshold** (10%–90%)
3. The modal shows how many empty images (without existing annotations) will be processed

> Models are added to the autolabel pool from the Training dashboard. If no models appear, you'll need to train one first.

---

## Compute Target

Below the mode-specific settings, the **Compute Target** toggle lets you choose where autolabeling runs:

- <span class="icon-btn"><i data-lucide="cloud"></i> Cloud</span> — Runs on Modal GPU infrastructure. Best for large datasets or when no local GPU is available.
- <span class="icon-btn"><i data-lucide="monitor"></i> Local GPU</span> — Runs on a connected GPU machine on the network. Select the target machine from the dropdown.

---

## Running Autolabeling

1. Configure your mode (SAM3 or YOLO), generation options, and compute target
2. Click <span class="icon-btn solid-green"><i data-lucide="play"></i> Start Auto-Label</span>
3. A progress area appears with a spinner and a live log console showing processing output
4. When complete, the modal can be dismissed and your annotations appear in the editor

---

## Reviewing Results

After autolabeling completes, review the generated annotations in the editor:

- **Navigate** through images (<span class="icon-btn"><i data-lucide="chevron-left"></i> A</span> / <span class="icon-btn"><i data-lucide="chevron-right"></i> D</span>) or videos (Z/C keys) to inspect detections
- **Correct errors** — use <span class="icon-btn solid-blue"><i data-lucide="mouse-pointer-2"></i></span> Select tool, then resize, move, or change class
- **Delete false positives** — select and press <span class="icon-btn"><i data-lucide="trash-2"></i> Delete</span>
- **Add missed detections** — use <span class="icon-btn solid-blue"><i data-lucide="square"></i></span> Draw tool to add bounding boxes manually
- **Refine masks** — use <span class="icon-btn solid-blue"><i data-lucide="pentagon"></i></span> Mask Edit tool to adjust polygon vertices

> **Tip**: Start with a higher confidence threshold to reduce false positives, then run a second pass at lower confidence to catch missed detections.
