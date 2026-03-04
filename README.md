# SAFARI

**Wildlife detection and monitoring platform** — detect, classify, and track species in camera trap imagery using AI.

## Tech Stack

| Layer | Technology |
|-------|-----------|
| Frontend | [Reflex](https://reflex.dev) (Python → React) |
| Backend | Python, FastAPI, Modal (GPU) |
| Database | Supabase (PostgreSQL + Auth) |
| Storage | Cloudflare R2 (S3-compatible) |
| Desktop | [SAFARIDesktop](https://github.com/biota-cloud/safari-desktop) — Tauri + Rust + TypeScript |
| Models | YOLO (detection), ConvNeXt (classification), SAM3 (segmentation) |

## Quick Start

### Prerequisites

- Python 3.11+
- Node.js 18+
- [Reflex](https://reflex.dev/docs/getting-started/installation/) CLI
- [Supabase](https://supabase.com) project — PostgreSQL database + auth
- [Cloudflare R2](https://developers.cloudflare.com/r2/) bucket — image/video/model storage
- [Modal](https://modal.com) account — GPU job execution (inference, training)

### Setup

```bash
# Clone and enter project
git clone https://github.com/biota-cloud/safari.git
cd safari

# Create virtual environment
python -m venv .venv
source .venv/bin/activate

# Install dependencies
pip install -r requirements.txt
```

### Configure Credentials

All credentials go in a single `.env` file at the project root:

```bash
cp .env.production.example .env
```

Edit `.env` with your Supabase URL/keys, R2 endpoint/keys, and bucket name. See [`.env.production.example`](.env.production.example) for all required variables with comments, or [`docs/DEVELOPMENT.md`](docs/DEVELOPMENT.md) for full descriptions.

Modal credentials are stored separately (not in `.env`):

```bash
pip install modal
modal token set --token-id <your-token-id> --token-secret <your-token-secret>
modal app list   # verify connection
```

Get your token from [modal.com/settings](https://modal.com/settings). This writes to `~/.modal.toml` — one-time setup per machine.

### Run

```bash
reflex run
```

The app will be available at `http://localhost:3000`.

### Production Deployment

SAFARI runs on a single VPS behind [Tailscale](https://tailscale.com) using systemd + Caddy:

1. Provision a VPS (Hetzner CX22 recommended — ~€4/mo)
2. Install Tailscale, Python 3.11, Caddy
3. Clone, create venv, configure `.env`
4. Enable the systemd service — app is live on Tailscale

See **[Production Deployment Guide](docs/deployment/production_deployment.md)** for full instructions.

## Documentation

See [`docs/`](docs/README.md) for full documentation:

- **[ONBOARDING.md](docs/ONBOARDING.md)** — User guide: first login, creating projects, labeling, training
- **[DEVELOPMENT.md](docs/DEVELOPMENT.md)** — Developer guide: local setup, env vars, Modal deployment
- **[Architecture Reference](docs/architecture/architecture_reference.md)** — System design, inference flows, schema
- **[API Internals](docs/reference/api_internals.md)** — REST API routing, SAM3 processing
- **[File Map](docs/file-map/README.md)** — Complete codebase map with function signatures

## Project Structure

```
SAFARI/
├── safari/              # Reflex app entry point
├── modules/             # UI pages (projects, datasets, labeling, training, API)
├── backend/             # Core logic, Supabase, R2, Modal jobs
│   ├── core/            # Shared inference/training core (portable across targets)
│   └── modal_jobs/      # GPU job definitions (A10G/L40S)
├── assets/              # Static files (JS, icons)
├── docs/                # All documentation
├── scripts/             # Remote worker scripts, utilities
├── migrations/          # SQL migration files
└── tests/               # Test suite
```

## License

Proprietary — all rights reserved.
