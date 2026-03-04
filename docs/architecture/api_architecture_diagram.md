# SAFARI API Architecture

> Complete flow diagram of the API infrastructure covering authentication, inference, and async video processing.

---

## High-Level Overview

```mermaid
flowchart LR
    subgraph Clients["External Clients"]
        TC[Tauri Desktop]
        CL[curl / HTTP]
    end

    subgraph API["Modal ASGI Gateway"]
        FW[FastAPI Router]
    end

    subgraph GPU["Modal GPU Pool"]
        INF[APIInference Worker]
    end

    subgraph Storage
        SB[(Supabase)]
        R2[(R2 Bucket)]
    end

    Clients --> |HTTPS + safari_ Key| FW

    FW --> |Validate Key| SB
    FW --> |Dispatch Job| INF
    INF --> |Load Weights| R2
    INF --> |Update Progress| SB
```

---

## Detailed Authentication Flow

```mermaid
sequenceDiagram
    autonumber
    participant C as Client
    participant A as FastAPI (server.py)
    participant AU as Auth (auth.py)
    participant DB as Supabase

    C->>A: POST /api/v1/infer/model-slug<br/>Header: Authorization: Bearer safari_xxx

    A->>AU: validate_api_key(header)
    AU->>AU: Extract "Bearer" prefix
    AU->>AU: Check "safari_" prefix
    AU->>AU: SHA256 hash key

    AU->>DB: SELECT FROM api_keys<br/>WHERE key_hash = ?
    DB-->>AU: {id, user_id, project_id, is_active, expires_at...}

    alt Key not found or inactive
        AU-->>A: HTTP 401/403 Error
        A-->>C: {"error": "Invalid or revoked key"}
    else Key valid
        AU->>DB: UPDATE last_used_at
        AU-->>A: APIKeyData object
        A->>A: Continue to inference
    end
```

---

## Image Inference Flow (Synchronous)

```mermaid
flowchart TB
    subgraph Request["Client Request"]
        REQ[POST /api/v1/infer/slug<br/>+ Image File]
    end

    subgraph Router["FastAPI Router (inference.py)"]
        VAL[Validate API Key]
        MOD[Lookup Model by Slug<br/>from api_models table]
        ACC[Check Model Access<br/>project_id or user_id match]
        ROUTE{Model Type?}
    end

    subgraph GPU["Modal GPU Worker (api_infer_job.py)"]
        subgraph Detection["Detection Flow"]
            YOLO[Load YOLO Model from R2]
            PRED[Run YOLO.predict]
        end
        subgraph Hybrid["Hybrid Classification Flow"]
            SAM3[Load SAM3 from Volume]
            DET[Detect Objects with Prompt]
            MASK[Extract Mask Polygons]
            CROP[Crop Each Detection]
            CLS[Load Classifier from R2<br/>YOLO .pt or ConvNeXt .pth]
            CLASS[Classify Each Crop]
        end
    end

    subgraph Response
        RES["{predictions: [...],<br/>mask_polygon: [[x,y]...],<br/>image_width, image_height}"]
    end

    REQ --> VAL --> MOD --> ACC --> ROUTE
    ROUTE -->|detection| YOLO --> PRED --> RES
    ROUTE -->|classification| SAM3 --> DET --> MASK --> CROP --> CLS --> CLASS --> RES
```

---

## Video Inference Flow (Asynchronous)

```mermaid
sequenceDiagram
    autonumber
    participant C as Client
    participant API as FastAPI
    participant DB as Supabase
    participant GPU as Modal GPU Worker

    C->>API: POST /api/v1/infer/slug/video<br/>+ Video File
    API->>API: Validate key & model
    API->>API: Generate job_id (UUID)

    API->>DB: INSERT api_jobs<br/>status: "pending"
    API->>GPU: process_video_job.spawn(job_id, ...)
    Note right of GPU: Fire-and-forget

    API-->>C: {"job_id": "...", "status": "pending"}

    loop Process Video
        GPU->>GPU: Extract frame N
        GPU->>GPU: Run inference
        GPU->>DB: UPDATE progress_current
    end

    GPU->>DB: UPDATE status: "completed"<br/>+ result_json

    loop Polling
        C->>API: GET /api/v1/jobs/{job_id}
        API->>DB: SELECT status, progress
        DB-->>API: {status, progress_current, progress_total}
        API-->>C: {"status": "processing", "progress": 45}
    end

    C->>API: GET /api/v1/jobs/{job_id}
    API->>DB: SELECT status, result_json
    DB-->>API: {status: "completed", result_json: {...}}
    API-->>C: {"status": "completed", "result": {...}}
```

---

## Database Schema Overview

```mermaid
erDiagram
    api_keys {
        uuid id PK
        uuid user_id FK
        uuid project_id FK "nullable"
        text key_hash "SHA256"
        text key_prefix "safari_xxxx"
        text name
        boolean is_active
        timestamptz expires_at
        int rate_limit_rpm
    }

    api_models {
        uuid id PK
        uuid training_run_id FK
        uuid project_id FK
        uuid user_id FK
        text slug UK "lynx-detector-v2"
        text model_type "detection|classification"
        text backbone "yolo|convnext"
        jsonb classes_snapshot
        text weights_r2_path
        text sam3_prompt "for hybrid"
        float classifier_confidence "for hybrid"
        int sam3_imgsz "stride-14 aligned"
        boolean include_masks "default true"
        boolean is_active
        bigint total_requests
    }

    api_jobs {
        uuid id PK
        uuid api_key_id FK
        uuid api_model_id FK
        uuid user_id FK
        text status "pending|processing|completed|failed"
        int progress_current
        int progress_total
        jsonb input_metadata
        jsonb result_json
        text error_message
    }

    api_usage_logs {
        uuid id PK
        uuid api_key_id FK
        uuid api_model_id FK
        text request_type "image|video"
        bigint file_size_bytes
        int inference_time_ms
        int status_code
    }

    api_keys ||--o{ api_jobs : "creates"
    api_models ||--o{ api_jobs : "processes"
    api_keys ||--o{ api_usage_logs : "logs"
    api_models ||--o{ api_usage_logs : "used by"
```

---

## File Structure

```
backend/api/
├── server.py           # Modal ASGI entrypoint, FastAPI setup
├── auth.py             # Bearer token validation, SHA256 hashing
└── routes/
    ├── inference.py    # /api/v1/infer/* endpoints
    └── jobs.py         # /api/v1/jobs/* endpoints

backend/modal_jobs/
└── api_infer_job.py    # GPU inference worker (detection + hybrid)
```

---

## Key Components Summary

| Component | Purpose |
|-----------|---------|
| **FastAPI Router** | Validates requests, routes by model type |
| **auth.py** | SHA256 key hashing, Bearer validation |
| **api_models** | Promoted models with frozen class snapshots |
| **api_keys** | Project-scoped or user-wide access tokens |
| **api_jobs** | Async video job tracking with progress |
| **APIInference** | Modal GPU worker supporting YOLO + SAM3 hybrid with masks |

---

## Response Schema: Predictions

Each prediction in a hybrid (classification) response includes:

| Field | Type | Description |
|-------|------|-------------|
| `class_name` | string | Species/class name from classifier |
| `class_id` | integer | Class index |
| `confidence` | float | Classifier confidence (0-1) |
| `box` | [x1,y1,x2,y2] | Normalized 0-1 bounding box |
| `mask_polygon` | [[x,y]...] | Normalized 0-1 polygon points (hybrid only) |
| `track_id` | integer | Object tracking ID (video only) |
| `top_k_crops` | [string...] | R2 URLs for classification K-crop images (video hybrid only) |
