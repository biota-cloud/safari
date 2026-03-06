# Development

> Local setup, environment configuration, and deployment instructions for SAFARI development.

---

## Prerequisites

| Tool | Version | Purpose |
|------|---------|---------|
| Python | 3.11+ | Backend, Reflex |
| Node.js | 18+ | Reflex frontend build |
| [Reflex CLI](https://reflex.dev/docs/getting-started/installation/) | Latest | App framework |
| [Modal CLI](https://modal.com/docs/guide) | Latest | GPU job deployment |
| Git | 2.x+ | Version control |

---

## Local Setup

### 1. Clone and Install

```bash
git clone https://github.com/biota-cloud/safari.git
cd safari

# Create virtual environment
python -m venv .venv
source .venv/bin/activate   # macOS/Linux
# .venv\Scripts\activate    # Windows

# Install Python dependencies
pip install -r requirements.txt

# Install Reflex
pip install reflex
```

### 2. Configure Environment

```bash
# Copy the example env file
cp .env.production.example .env
```

Edit `.env` with your credentials. See [Environment Variables](#environment-variables) below.

### 3. Run Development Server

```bash
reflex run
```

The app starts at `http://localhost:3000` with hot reload enabled.

> For **production deployment** (VPS, systemd, Caddy), see the [Deployment](09_deployment.html) page.

---

## Environment Variables

All environment variables are loaded from `.env` at the project root.

### Supabase (Required)

| Variable | Description | Example |
|----------|-------------|---------|
| `SUPABASE_URL` | Supabase project URL | `https://xxx.supabase.co` |
| `SUPABASE_KEY` | Supabase anon/public key | `eyJhbG...` |
| `SUPABASE_SERVICE_ROLE` | Service role key (admin operations) | `eyJhbG...` |

### Cloudflare R2 Storage (Required)

| Variable | Description | Example |
|----------|-------------|---------|
| `R2_ENDPOINT_URL` | R2 S3-compatible endpoint | `https://<account-id>.r2.cloudflarestorage.com` |
| `R2_ACCESS_KEY_ID` | R2 access key | `xxxxx` |
| `R2_SECRET_ACCESS_KEY` | R2 secret key | `xxxxx` |
| `R2_BUCKET_NAME` | R2 bucket name | `safari-bucket` |

### Modal Authentication

Modal authentication is stored in `~/.modal.toml` (not in `.env`). Configure via:

```bash
modal token set --token-id <id> --token-secret <secret>
```

Get your token from [modal.com/settings](https://modal.com/settings). One-time setup per machine.

### App Settings (Optional)

| Variable | Description | Default |
|----------|-------------|---------|
| `SAFARI_ROOT` | Root directory for local GPU workers | `~/.safari` |

---

## Modal GPU Deployment

### Setup

```bash
# Authenticate with Modal
modal token set --token-id <id> --token-secret <secret>

# Verify connection
modal app list
```

### Deploy Jobs

```bash
# Deploy all Modal jobs
modal deploy backend/modal_jobs/hybrid_infer_job.py
modal deploy backend/modal_jobs/infer_job.py
modal deploy backend/modal_jobs/train_job.py
modal deploy backend/modal_jobs/train_classify_job.py
modal deploy backend/modal_jobs/train_sam3_job.py
modal deploy backend/modal_jobs/autolabel_job.py

# Deploy API server
modal deploy backend/api/server.py
```

> Or deploy all at once: `./scripts/deploy_modal.sh`

### Monitor

```bash
# View logs
modal app logs hybrid-inference
modal app logs safari-api-inference

# Check running functions
modal app list
```

### Sync SAM3 Weights

```bash
# Upload SAM3 model to Modal volume
python backend/modal_jobs/model_volume.py
```

---

## Local GPU Workers

For running inference and training on your own GPU hardware (e.g., RTX 4090):

### Setup Remote Machine

```bash
# On the remote GPU machine
mkdir -p ~/.safari/{scripts,models,data}

# Create Python environment
python3.11 -m venv ~/.safari/venv
source ~/.safari/venv/bin/activate
pip install ultralytics supabase python-dotenv boto3
```

### Configure Credentials

Create `~/.safari/.env` on the remote machine:

```bash
SUPABASE_URL=https://xxx.supabase.co
SUPABASE_KEY=eyJhbG...
R2_ENDPOINT_URL=https://xxx.r2.cloudflarestorage.com
R2_ACCESS_KEY_ID=xxxxx
R2_SECRET_ACCESS_KEY=xxxxx
R2_BUCKET_NAME=safari-bucket
```

### Run Workers

```bash
export SAFARI_ROOT=$HOME/.safari && python scripts/remote_hybrid_infer.py
```

> Workers are dispatched from the SAFARI Server via SSH. The `SAFARI_ROOT` env var enables portable path discovery.

---

## Running Tests

```bash
# Run all tests
python -m pytest tests/

# Run specific test file
python -m pytest tests/test_api_keys.py -v

# Run with coverage
python -m pytest tests/ --cov=backend
```

> Tests require valid Supabase credentials in `.env`.

---

## Project Structure

```
SAFARI/
├── safari/                 # Reflex app entry (route registration)
├── modules/                # UI pages
│   ├── projects/           # Project management
│   ├── datasets/           # Dataset views
│   ├── labeling/           # Image/video annotation editors
│   ├── training/           # Training dashboard
│   ├── inference/          # Model playground
│   └── api/                # API key management
├── backend/
│   ├── core/               # Shared core modules (inference, training)
│   ├── modal_jobs/         # Modal GPU job definitions
│   ├── api/                # FastAPI REST API (server, auth, routes)
│   ├── supabase_client.py  # Database operations
│   ├── r2_storage.py       # R2 file storage
│   ├── job_router.py       # Cloud/Local GPU dispatch
│   ├── inference_router.py # Inference flow routing
│   └── annotation_service.py  # Dual-write annotation layer
├── scripts/
│   ├── remote_workers/     # Local GPU worker scripts
│   └── deploy_modal.sh     # Deploy all Modal apps
├── assets/                 # Static JS, CSS, icons, branding
├── docs/                   # Documentation
├── migrations/             # SQL schema migrations
├── tests/                  # Test suite
├── .env                    # Environment variables (not committed)
└── requirements.txt        # Python dependencies
```

---

## Common Tasks

| Task | Command |
|------|---------|
| Start dev server | `reflex run` |
| Deploy all Modal jobs | `./scripts/deploy_modal.sh` |
| Deploy single Modal job | `modal deploy backend/modal_jobs/<job>.py` |
| Deploy API server | `modal deploy backend/api/server.py` |
| View Modal logs | `modal app logs <app-name>` |
| Run tests | `python -m pytest tests/` |
| Sync SAM3 model | `python backend/modal_jobs/model_volume.py` |
| Sync remote workers | Uses `SSHWorkerClient.sync_scripts()` |
| Build docs portal | `python docs/onboard/build.py` |
