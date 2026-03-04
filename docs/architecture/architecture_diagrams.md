# SAFARI Architecture Diagrams

> Visual documentation of the SAFARI platform architecture. All diagrams reflect the current implementation.

---

## Table of Contents

1. [Level 1: System Overview](#level-1-system-overview)
2. [Level 2: Core Workflow Pipelines](#level-2-core-workflow-pipelines)
3. [Level 3: Job Routing Architecture](#level-3-job-routing-architecture)
4. [Level 4: Detailed Components](#level-4-detailed-components)

---

## Level 1: System Overview

### SAFARI Ecosystem

```mermaid
graph TB
    subgraph "User Interfaces"
        WEB["SAFARI Server<br/>(Reflex Web App)"]
        DESK["SAFARIDesktop<br/>(Tauri Client)"]
    end

    subgraph "Compute Layer"
        MODAL["Modal Cloud<br/>(L40S / A10G GPU)"]
        LOCAL["Local GPU<br/>(SSH Workers)"]
    end

    subgraph "Storage Layer"
        SUPA["Supabase<br/>(PostgreSQL + Auth)"]
        R2["Cloudflare R2<br/>(Object Storage)"]
    end

    WEB <--> SUPA
    WEB <--> R2
    WEB --> MODAL
    WEB --> LOCAL
    
    DESK <--> WEB
    DESK --> R2
    
    MODAL <--> R2
    LOCAL <--> R2
```

### Component Responsibilities

| Component | Technology | Responsibility |
|-----------|------------|----------------|
| **SAFARI Server** | Reflex (Python) | Web UI, state management, job orchestration |
| **SAFARIDesktop** | Tauri (Rust + TS) | Native client, video processing, scientific analytics |
| **Modal Cloud** | Modal (Python) | GPU jobs: training, inference, autolabeling |
| **Local GPU** | SSH + Python | Same jobs on user hardware (e.g., RTX 4090) |
| **Supabase** | PostgreSQL | Projects, datasets, annotations, training runs |
| **R2** | S3-compatible | Images, labels, model weights, inference results |

---

## Level 2: Core Workflow Pipelines

### 2A. Labeling Pipeline

```mermaid
flowchart LR
    subgraph "User Interface"
        IMG["Image Editor<br/>(LabelingState)"]
        VID["Video Editor<br/>(VideoLabelingState)"]
    end

    subgraph "Backend Services"
        ANN["Annotation Service<br/>(annotation_service.py)"]
    end

    subgraph "Storage"
        DB["Supabase JSONB<br/>(images/keyframes.annotations)"]
        FS["R2 Labels<br/>(.txt YOLO format)"]
    end

    IMG --> ANN
    VID --> ANN
    ANN -->|"Dual Write"| DB
    ANN -->|"Dual Write"| FS
    
    DB -->|"Fast UI Reads"| ANN
    FS -->|"Training Export"| ANN
```

**Key patterns:**
- Annotations store `class_id` only (not `class_name`)
- Class names resolved dynamically from `projects.classes`
- Dual-write ensures YOLO training compatibility

---

### 2B. Training Pipeline

```mermaid
flowchart TB
    subgraph "UI Layer"
        TS["TrainingState<br/>(modules/training/state.py)"]
    end

    subgraph "Routing Layer"
        JR["Job Router<br/>(job_router.py)"]
    end

    subgraph "Modal Cloud"
        TJ["train_job.py<br/>(Detection)"]
        TCJ["train_classify_job.py<br/>(Classification)"]
    end

    subgraph "Local GPU"
        RT["remote_train.py<br/>(Detection)"]
        RTC["remote_train_classify.py<br/>(Classification)"]
    end

    subgraph "Storage"
        R2W["R2<br/>(Weights + Metrics)"]
        SUP["Supabase<br/>(training_runs, models)"]
    end

    TS -->|"dispatch_training_job()"| JR
    JR -->|"cloud"| TJ
    JR -->|"cloud"| TCJ
    JR -->|"local"| RT
    JR -->|"local"| RTC
    
    TJ --> R2W
    TCJ --> R2W
    RT --> R2W
    RTC --> R2W
    
    R2W --> SUP
```

**Training types:**
| Type | Modal Job | Local Worker | Output |
|------|-----------|--------------|--------|
| Detection | `train_job.py` | `remote_train.py` | `best.pt` |
| YOLO Classify | `train_classify_job.py` | `remote_train_classify.py` | `best.pt` |
| ConvNeXt Classify | `train_classify_job.py` | `remote_train_classify.py` | `best.pth` |
| SAM3 Fine-Tune | `train_sam3_job.py` | N/A (cloud only) | Fine-tuned SAM3 weights |

---

### 2C. Inference Pipeline

```mermaid
flowchart TB
    subgraph "UI Layer"
        IS["InferenceState<br/>(modules/inference/state.py)"]
    end

    subgraph "Routing Layer"
        IR["Inference Router<br/>(inference_router.py)"]
        JR["Job Router<br/>(job_router.py)"]
    end

    subgraph "Modal Cloud"
        IJ["infer_job.py<br/>(YOLO)"]
        HIJ["hybrid_infer_job.py<br/>(SAM3 + Classifier)"]
    end

    subgraph "Local GPU"
        RYI["remote_yolo_infer.py"]
        RHI["remote_hybrid_infer.py"]
    end

    subgraph "Storage"
        R2R["R2<br/>(Results JSON)"]
    end

    IS -->|"dispatch_inference()"| IR
    IR -->|"YOLO detect"| IJ
    IR -->|"YOLO detect local"| RYI
    IR -->|"Hybrid"| JR
    JR -->|"cloud"| HIJ
    JR -->|"local"| RHI
    
    IJ --> R2R
    HIJ --> R2R
    RYI --> R2R
    RHI --> R2R
```

**Inference types:**
| Input | YOLO Detection | Hybrid (SAM3 + Classifier) |
|-------|----------------|---------------------------|
| Single Image | ✅ Modal + Local | ✅ Modal + Local |
| Batch Images | ✅ Modal + Local | ✅ Modal + Local |
| Video | ✅ Modal + Local | ✅ Modal + Local |

---

## Level 3: Job Routing Architecture

### 3A. Action-Level Routing

```mermaid
flowchart TB
    REQ["Job Request<br/>(training/inference/autolabel)"]
    
    subgraph "Target Resolution"
        ACT["Action-level target<br/>(user selects cloud/local per dispatch)"]
        DEFAULT["get_job_target()<br/>defaults to 'cloud'"]
    end
    
    REQ --> ACT
    ACT -->|"explicit target"| ROUTE
    ACT -->|"no target"| DEFAULT --> ROUTE
    ROUTE{"target?"}
    
    ROUTE -->|"'cloud'"| MODAL["Modal Functions<br/>(.spawn() / .remote())"]
    ROUTE -->|"'local'"| SSH["SSH Worker Client<br/>(execute_async / execute_job)"]
    
    subgraph "Modal Jobs"
        MJ1["hybrid_infer_job.py"]
        MJ2["train_job.py"]
        MJ3["autolabel_job.py"]
    end
    
    subgraph "Remote Workers"
        RW1["remote_hybrid_infer.py"]
        RW2["remote_train.py"]
        RW3["remote_autolabel.py"]
    end
    
    MODAL --> MJ1
    MODAL --> MJ2
    MODAL --> MJ3
    
    SSH --> RW1
    SSH --> RW2
    SSH --> RW3
```

> Compute target is selected per action, not locked per project.

---

### 3B. Inference Router Flow

```mermaid
flowchart TB
    START["dispatch_inference()<br/>(InferenceConfig)"]
    
    MT{{"model_type?"}}
    
    START --> MT
    
    MT -->|"yolo-detect"| YOLO_CT{{"compute_target?"}}
    MT -->|"hybrid"| HYB_CT{{"compute_target?"}}
    
    YOLO_CT -->|"cloud"| YOLO_MODAL["Modal: YOLOInference<br/>predict_image / predict_batch / predict_video"]
    YOLO_CT -->|"local"| YOLO_LOCAL["SSH: remote_yolo_infer.py"]
    
    HYB_CT -->|"cloud"| HYB_MODAL["Modal: hybrid_inference<br/>single / batch / video"]
    HYB_CT -->|"local"| HYB_LOCAL["SSH: remote_hybrid_infer.py"]
    
    YOLO_MODAL --> RES["Results"]
    YOLO_LOCAL --> RES
    HYB_MODAL --> RES
    HYB_LOCAL --> RES
```

**Key decision points:**
- `model_type` → determines YOLO vs Hybrid pipeline
- `compute_target` → set per action by user (defaults to cloud)
- Input type (image/batch/video) selects method variant

---


### 3C. Shared Core Pattern

All GPU jobs use the **Shared Core Pattern** — pure logic lives in `backend/core/`, ensuring automatic parity between Modal and Local GPU.

#### Inference Cores

```mermaid
flowchart LR
    subgraph Core["backend/core/"]
        HIC[hybrid_infer_core]
        HBC[hybrid_batch_core]
        HVC[hybrid_video_core]
        YIC[yolo_infer_core]
        CU[classifier_utils]
        IU[image_utils]
    end
    
    subgraph Modal
        HIJ[hybrid_infer_job]
        IJ[infer_job]
    end
    
    subgraph Remote
        RHI[remote_hybrid_infer]
        RYI[remote_yolo_infer]
    end
    
    HIJ --> HIC & HBC & HVC
    RHI --> HIC & HBC & HVC
    IJ --> YIC
    RYI --> YIC
    
    HIC & HBC & HVC --> CU & IU
```

#### Training Cores

```mermaid
flowchart LR
    subgraph Core["backend/core/"]
        TDC[train_detect_core]
        TCC[train_classify_core]
        IU[image_utils]
    end
    
    subgraph Modal
        TJ[train_job]
        TCJ[train_classify_job]
    end
    
    subgraph Remote
        RT[remote_train]
        RTC[remote_train_classify]
    end
    
    TJ --> TDC
    RT --> TDC
    TCJ --> TCC
    RTC --> TCC
    TCC --> IU
```

#### Autolabel Core

```mermaid
flowchart LR
    subgraph Core["backend/core/"]
        ALC[autolabel_core]
    end
    
    subgraph Modal
        ALJ[autolabel_job]
    end
    
    subgraph Remote
        RAL[remote_autolabel]
    end
    
    ALJ --> ALC
    RAL --> ALC
```

**Core module functions:**

| Module | Key Functions |
|--------|--------------|
| `hybrid_infer_core.py` | `run_hybrid_inference()`, `run_sam3_detection()`, `run_classification_loop()` |
| `hybrid_batch_core.py` | `run_hybrid_batch_inference()` |
| `hybrid_video_core.py` | `run_hybrid_video_inference()`, `classify_unique_tracks()` |
| `yolo_infer_core.py` | `run_yolo_single_inference()`, `run_yolo_batch_inference()`, `run_yolo_video_inference()` |
| `autolabel_core.py` | `run_yolo_autolabel()`, `run_sam3_autolabel()` |
| `train_detect_core.py` | `prepare_yolo_dataset()`, `run_yolo_training()` |
| `train_classify_core.py` | `create_classification_crops()`, `train_classification()` |
| `sam3_dataset_core.py` | `prepare_sam3_dataset()` |
| `classifier_utils.py` | `load_classifier()`, `classify_with_convnext()` |
| `image_utils.py` | `crop_from_box()`, `download_image()` |
| `thumbnail_generator.py` | `generate_thumbnail()` |

---

## Level 4: Detailed Components

### 4A. Hybrid Inference Pipeline

```mermaid
flowchart TB
    subgraph "Input"
        IMG["Image/Video"]
    end

    subgraph "SAM3 Detection"
        SAM["SAM3SemanticPredictor<br/>(or SAM3VideoSemanticPredictor)"]
        MASK["Binary Masks"]
        POLY["Polygons<br/>(mask_to_polygon)"]
    end

    subgraph "Classification"
        CROP["Crop Regions<br/>(crop_from_box)"]
        CLS["Classifier<br/>(YOLO-cls or ConvNeXt)"]
        FILT["Confidence Filter"]
    end

    subgraph "Output"
        RES["Predictions<br/>{class_name, box, confidence}"]
    end

    IMG --> SAM
    SAM --> MASK
    MASK --> POLY
    
    MASK --> CROP
    CROP --> CLS
    CLS --> FILT
    
    POLY --> RES
    FILT --> RES
```

**Video classification strategy:**
**Quality-Diverse Top-K (Video):**
```mermaid
flowchart LR
    subgraph "Top-K Classification"
        TRACK["Track ID 1<br/>N candidate frames"] -->|"Select K diverse"| K["K=3 best frames"]
        K --> C1["Classify Frame A"]
        K --> C2["Classify Frame B"]
        K --> C3["Classify Frame C"]
        C1 & C2 & C3 --> VOTE["Majority Vote<br/>→ Species label"]
    end
```

> `classify_top_k` (default: 3) selects quality-diverse frames per track for more robust species classification.

---

### 4B. Training Flow Detail

```mermaid
sequenceDiagram
    participant UI as TrainingState
    participant JR as Job Router
    participant TRAIN as Training Job
    participant R2 as R2 Storage
    participant DB as Supabase

    UI->>JR: dispatch_training_job(run_id, datasets, config)
    JR->>TRAIN: Execute (Modal or Local)
    
    loop Each Epoch
        TRAIN->>TRAIN: Forward/Backward Pass
        TRAIN->>R2: Save checkpoint (optional)
    end
    
    TRAIN->>R2: Upload best.pt + results.csv
    TRAIN->>DB: Update training_runs (status, metrics)
    TRAIN->>DB: Create models entry
    
    DB-->>UI: Poll for status updates
```

**Classification training (ConvNeXt):**
- Custom PyTorch training loop (not Ultralytics)
- Backbone auto-detected by file extension (`.pth`)
- Same metrics format for dashboard parity

---

### 4C. Storage Architecture

```mermaid
flowchart TB
    subgraph "Supabase (PostgreSQL)"
        PROF["profiles<br/>{id, email, role}"]
        PROJ["projects<br/>{id, classes, is_company}"]
        PM["project_members<br/>{project_id, user_id, role}"]
        DS["datasets<br/>{id, project_id, type}"]
        IMG["images<br/>{annotations JSONB}"]
        VID["videos<br/>{r2_path, proxy_r2_path}"]
        KF["keyframes<br/>{annotations JSONB}"]
        TR["training_runs<br/>{classes_snapshot, model_type}"]
        MOD["models<br/>{training_run_id, weights_path}"]
        AM["api_models<br/>{slug, sam3_prompt}"]
    end

    subgraph "R2 Object Storage"
        DSI["datasets/{id}/images/"]
        DSL["datasets/{id}/labels/"]
        TRW["projects/{id}/runs/{id}/weights/"]
        INF["inference_results/{id}.json"]
    end

    PROF --> PM
    PROJ --> PM
    PROJ --> DS
    DS --> IMG
    DS --> VID
    VID --> KF
    PROJ --> TR
    TR --> MOD
    TR --> AM

    IMG -.->|"training"| DSL
    KF -.->|"training"| DSL
    TR -.->|"artifacts"| TRW
```

**Dual-write pattern:**
| Storage | Format | Purpose | Speed |
|---------|--------|---------|-------|
| Supabase JSONB | `{class_id, x, y, width, height}` | UI reads | ~10ms |
| R2 Labels | YOLO `.txt` | Training export | ~50ms |

---

### 4D. API Infrastructure

```mermaid
flowchart TB
    subgraph "External Clients"
        TD["SAFARIDesktop"]
        EXT["External Apps"]
    end

    subgraph "API Gateway (Modal)"
        SRV["server.py<br/>(FastAPI ASGI)"]
        AUTH["auth.py<br/>(API Key Validation)"]
    end

    subgraph "API Workers"
        AIJ["api_infer_job.py<br/>(Isolated from Playground)"]
    end

    subgraph "Database"
        AM["api_models<br/>{slug, sam3_prompt, sam3_imgsz, classifier_r2_path}"]
    end

    TD -->|"safari_* API key"| SRV
    EXT -->|"safari_* API key"| SRV

    
    SRV --> AUTH
    AUTH -->|"valid"| AIJ
    AIJ --> AM
    
    AM -->|"Model Config"| AIJ
```

**API Endpoints:**
| Endpoint | Purpose |
|----------|---------|
| `POST /api/v1/infer/{slug}` | Single image inference |
| `POST /api/v1/infer/{slug}/batch` | Batch image inference |
| `POST /api/v1/infer/{slug}/video` | Async video inference |
| `GET /api/v1/jobs/{job_id}` | Job status polling |

---

### 4E. SAFARIDesktop Integration (High-Level)

```mermaid
flowchart TB
    subgraph "SAFARIDesktop (Tauri)"
        RUST["Rust Backend<br/>(Commands)"]
        TS["TypeScript Frontend<br/>(React)"]
        FF["FFmpeg Sidecar<br/>(Video Processing)"]
    end

    subgraph "SAFARI Server"
        API["API Gateway"]
    end

    subgraph "Storage"
        R2["R2 (Results)"]
        LOCAL["Local SQLite<br/>(Results Cache)"]
    end

    TS --> RUST
    RUST --> FF
    FF -->|"Preprocessed Video"| API
    
    API --> R2
    R2 --> RUST
    RUST --> LOCAL
    
    LOCAL --> TS
```

**Key flows:**
- Video preprocessing (FFmpeg resize to 640/1024/HD)
- API communication (OpenAPI contract)
- Results display (60Hz canvas overlays with RAF)
- Local persistence (SQLite results gallery)

---

## File Parity Matrix

| Modal Job | Remote Worker | Shared Core | Parity |
|-----------|---------------|-------------|--------|
| `hybrid_infer_job.py` (single) | `remote_hybrid_infer.py` | `hybrid_infer_core.py` | ✅ Automatic |
| `hybrid_infer_job.py` (batch) | `remote_hybrid_infer.py` | `hybrid_batch_core.py` | ✅ Automatic |
| `hybrid_infer_job.py` (video) | `remote_hybrid_infer.py` | `hybrid_video_core.py` | ✅ Automatic |
| `train_job.py` | `remote_train.py` | `train_detect_core.py` | ✅ Automatic |
| `train_classify_job.py` | `remote_train_classify.py` | `train_classify_core.py` | ✅ Automatic |
| `train_sam3_job.py` | N/A | `sam3_dataset_core.py` | Cloud only |
| `autolabel_job.py` | `remote_autolabel.py` | `autolabel_core.py` | ✅ Automatic |
| `infer_job.py` | `remote_yolo_infer.py` | `yolo_infer_core.py` | ✅ Automatic |
| `api_infer_job.py` | N/A | Can use `hybrid_infer_core.py` | Isolated |

---

*Last updated: 2026-02-26 — SAFARI rebrand, SAM3 training, multi-user schema*
