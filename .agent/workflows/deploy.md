---
description: Deploy Modal jobs and sync remote worker scripts to the GPU machine
---

# Deploy Workflow

Deploy updated Modal apps and/or sync worker scripts + backend/core to the remote GPU machine.

// turbo-all

## Step 1: Deploy Modal Jobs

Deploy the Modal apps that have changed. Common jobs and their app names:

| File | App Name | Purpose |
|------|----------|---------|
| `backend/modal_jobs/autolabel_job.py` | `yolo-autolabel` | SAM3/YOLO autolabeling |
| `backend/modal_jobs/hybrid_infer_job.py` | `hybrid-inference` | Hybrid SAM3+YOLO inference |
| `backend/modal_jobs/infer_job.py` | `yolo-inference` | YOLO-only inference |
| `backend/modal_jobs/train_job.py` | `yolo-training` | Detection training |
| `backend/modal_jobs/train_classify_job.py` | `yolo-classify-training` | Classification training |
| `backend/modal_jobs/api_infer_job.py` | `tyto-api-inference` | API inference endpoint |
| `backend/modal_jobs/model_volume.py` | `yolo-models` | Model volume management |

Deploy only the jobs that were modified:

```bash
modal deploy backend/modal_jobs/<job_file>.py
```

To deploy all jobs at once (use sparingly):

```bash
for f in backend/modal_jobs/*_job.py backend/modal_jobs/model_volume.py; do echo "=== Deploying $f ===" && modal deploy "$f"; done
```

## Step 2: Sync Remote Worker

The remote GPU machine is configured as:

- **Host**: `100.122.63.105`
- **Port**: `22`
- **User**: `ise`
- **Remote dir**: `~/.tyto/`
- **SSH key**: Auto-discovered from `~/.ssh/`

Sync worker scripts (`scripts/remote_workers/`) and shared core modules (`backend/core/`) using the built-in SSH client:

```bash
cd /Users/jorge/PycharmProjects/Tyto && python -c "
from backend.ssh_client import SSHWorkerClient
with SSHWorkerClient(host='100.122.63.105', port=22, user='ise') as client:
    result = client.sync_scripts(force=True)
    print(f'Uploaded: {len(result[\"uploaded\"])} files')
    if result['errors']:
        print(f'Errors: {result[\"errors\"]}')
"
```

### What gets synced

- `scripts/remote_workers/*.py` — All worker scripts (autolabel, inference, training, etc.)
- `scripts/remote_workers/*.sh` — Setup and install scripts
- `scripts/remote_workers/*.txt` — Requirements file
- `backend/core/*.py` — Shared core modules (autolabel_core, hybrid_infer_core, etc.)

### Notes

- The sync uses hash-based diffing — `force=True` skips the check and uploads everything.
- Use `force=False` for incremental syncs (faster, only uploads changed files).
- The `.env` file on the remote machine is NOT overwritten — credentials stay intact.
- If you need to update remote `.env`, use: `scp .env ise@100.122.63.105:~/.tyto/.env`
