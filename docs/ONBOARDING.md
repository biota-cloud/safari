# SAFARI Onboarding Guide

> Get started using the SAFARI wildlife detection platform.

---

## 1. Get Access

### Network Access (Tailscale)

SAFARI runs on a private network. To connect:

1. Install [Tailscale](https://tailscale.com/download) on your machine
2. Request an invitation from the project administrator
3. Accept the invite and connect — you'll be on the SAFARI network

### Account

1. Navigate to the SAFARI web app URL (provided by your administrator)
2. Log in with the credentials provided to you
3. On first login, you'll see an empty dashboard

---

## 2. Create a Project

Projects are the top-level container for all your work.

1. Click **"+ New Project"** on the dashboard
2. Give it a descriptive name (e.g., "Alentejo Camera Traps 2026")

---

## 3. Upload Data

### Create a Dataset

1. Open your project
2. Click **"+ New Dataset"**
3. Name it descriptively (e.g., "Station A — January")

### Upload Images or Videos

1. Open the dataset
2. Drag and drop files, or click **"Upload"**
3. Supported formats:
   - **Images**: JPG, PNG, WEBP
   - **Videos**: MP4, AVI, MOV, MKV
4. Thumbnails are generated automatically

---

## 4. Label Data

### Image Labeling

1. Open a dataset and click **"Label"**
2. Use the labeling tools:
   - **Bounding box** — draw rectangles around animals
3. Assign species classes to each annotation
4. Navigate between images with arrow keys or the filmstrip

### Video Labeling

1. For video datasets, the labeling interface includes frame navigation
2. Use the timeline scrubber to move through frames
3. Annotations are tied to specific frames

> [!TIP]
> Use **Autolabel** to pre-label datasets with AI. Two modes available:
> - **SAM3** — detect animals using text prompts (e.g., "Lynx") with automatic mask generation
> - **YOLO** — apply an existing trained detection model
>
> Run autolabel, then review and correct the results manually.

---

## 5. Train Models

### Detection Models (YOLO)

1. Go to your project's **Training** dashboard
2. Select one or more labeled datasets
3. Configure training parameters (or use defaults):
   - Epochs, image size, batch size
   - Backbone: YOLOv11n/s/m/l/x
4. Click **"Train"** — the job runs on GPU infrastructure
5. Monitor progress in real-time (loss curves, metrics)

### Classification Models

1. Same workflow, but choose **Classification** model type
2. Supports YOLO-Classify and ConvNeXt backbones
3. Training data is automatically prepared from your labeled bounding boxes

### Using Trained Models

Once training completes:
- **Playground**: Test the model on new images directly in the browser
- **Autolabel**: Apply the model to unlabeled datasets
- **API**: Promote the model to the REST API for external use (SAFARIDesktop, scripts)

---

## 6. Run Inference

### Playground

1. Navigate to the **Playground** from the sidebar
2. Select a trained model
3. Upload or drag images to get instant predictions
4. View bounding boxes, masks, and classification results

### Batch Inference (API)

For high-volume processing, use the REST API:

1. Go to **Project → API** settings
2. Create an API key (starts with `safari_`)
3. Use the key with SAFARIDesktop or curl:

```bash
curl -X POST \
  -H "Authorization: Bearer safari_xxxx..." \
  -F "file=@camera_trap_photo.jpg" \
  https://<api-url>/api/v1/infer/<model-slug>
```

---

## 7. Analyze Results

### Scientific Analytics

The dashboard provides ecological analysis tools:
- **Species summary** — detection counts, confidence distributions
- **Temporal patterns** — activity by time of day (circadian plots)
- **Sampling effort** — camera station coverage over time
- **Occupancy matrix** — species × station presence/absence

### Export

Export detection data in standard formats:
- **JSON** — full prediction data with coordinates
- **CSV** — tabular format for R, Excel, Wildlife Insights

---

## Need Help?

Contact the project administrator for:
- Account issues or access requests
- GPU quota questions
- Bug reports or feature requests
