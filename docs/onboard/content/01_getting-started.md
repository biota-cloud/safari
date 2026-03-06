# Getting Started

> Take your first steps with SAFARI — from network access to your first uploaded dataset.

---

## Getting Access

SAFARI runs on a private network to keep your data secure. Before you can use the platform, you'll need network access and login credentials.

### Network Access (Tailscale)

1. Install [Tailscale](https://tailscale.com/download) on your machine (available for macOS, Windows, Linux, iOS, and Android)
2. Request an invitation from the project administrator
3. Accept the invite and connect — your machine is now on the SAFARI network

### Logging In

1. Navigate to the SAFARI URL provided by your administrator
2. Enter your credentials on the login screen
3. Click <span class="icon-btn solid-green">SIGN IN</span> — you'll be taken to the dashboard

![Login screen](screenshots/Login.png)

---

## The Dashboard

After logging in, you'll see the SAFARI dashboard — the central hub for all your work.

![Main dashboard](screenshots/Main_dash.png)

The dashboard uses a card-based layout with quick access to the main areas of the platform:

- **Projects** — Your wildlife detection projects, each containing datasets, labels, and trained models
- **Training** — Launch and monitor model training runs
- **Inference Playground** — Test trained models on new images and video

![Projects card](screenshots/Projects_card.png)

![Inference Playground card](screenshots/Main_dash_inference_playground_card.png)

> **Tip**: The navigation header at the top provides breadcrumb-style navigation. Click the SAFARI logo at any time to return to this dashboard.

---

## Creating Your First Project

Projects are the top-level container for all your work — datasets, labels, trained models, and API endpoints are all organized under a project.

1. Click <span class="icon-btn outline-green"><i data-lucide="plus"></i> Project</span> next to the Projects heading on the dashboard
2. Give your project a descriptive name (e.g., *"Lince Ibérico"* or *"Alentejo Fauna 2026"*)
3. Click **Create**

![New project modal](screenshots/New_project_modal.png)

Your new project opens automatically, showing an empty workspace ready for data.

![Project detail view](screenshots/Project_detail.png)

The project detail page shows:

- **Datasets** — All image and video datasets in this project
- **Classes** — Species or object categories used for labeling
- **Training** — Model training runs associated with this project

---

## Creating a Dataset

Datasets hold the images or videos you want to label and train on. Each dataset is either an **image dataset** or a **video dataset**.

1. From your project page, click <span class="icon-btn outline-green"><i data-lucide="plus"></i> New Dataset</span>
2. Enter a descriptive name (e.g., *"Lince — Training Set"* or *"Veado — January"*)
3. Select the type:
   - **Image** — For collections of individual photographs
   - **Video** — For video recordings
4. Click **Create**

![New dataset modal](screenshots/New_dataset_modal.png)

> **Tip**: Use descriptive names that help you identify the source and time period. This makes it easier to select the right datasets when training models later.

---

## Uploading Data

Once you've created a dataset, you can upload your files.

1. Open your dataset from the project page
2. **Drag and drop** files onto the upload area, or click to browse
3. Files are uploaded and thumbnails generated automatically

![Dataset detail with uploaded images](screenshots/Dataset_detail.png)

### Supported Formats

| Type | Formats |
|------|---------|
| **Images** | JPG, JPEG, PNG, WEBP |
| **Videos** | MP4, MOV, WEBM |

### What Happens on Upload

- Each image is stored securely in cloud storage (R2)
- A thumbnail is generated automatically for the grid view
- For videos, a thumbnail is extracted from the first frame and metadata (duration, resolution, FPS) is recorded
- Duplicate filenames across the project are detected and flagged

### YOLO Dataset Import

If you already have a labeled dataset in YOLO format, you can import it directly:

1. Prepare a ZIP file containing:
   - An `images/` folder with your image files
   - A `labels/` folder with YOLO-format `.txt` annotation files
   - A `data.yaml` file defining your class names
2. Use the <span class="icon-btn"><i data-lucide="file-archive"></i> Import ZIP</span> option to upload the entire dataset with labels intact

---

## What's Next?

Now that you have a project with uploaded data, you're ready to start labeling:

- **[Image Labeling](02_image-labeling.html)** — Draw bounding boxes and assign species classes to your images
- **[Video Labeling](03_video-labeling.html)** — Navigate video frames and annotate keyframes
- **[Autolabeling](04_autolabeling.html)** — Let AI pre-label your data using SAM3 or a trained YOLO model

Or, if your data is already labeled, jump ahead to:

- **[Training](05_training.html)** — Train detection and classification models on your labeled datasets
