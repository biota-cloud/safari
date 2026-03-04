#!/bin/bash
# Deploy all Modal infrastructure (GPU jobs + API server)
# Run from the project root: ./scripts/deploy_modal.sh
#
# Prerequisites:
#   - Modal CLI authenticated: modal token set --token-id ... --token-secret ...
#   - Modal secrets created: r2-credentials, supabase-credentials
#   - SAM3 model weights uploaded to sam3-volume (see below)

set -e

echo "🚀 Deploying Modal infrastructure..."
echo ""

# --- Step 1: Jobs that CREATE volumes (must deploy first) ---
echo "── Volume-creating jobs (deploy first) ──"

echo "[1/8] SAM3 training (creates sam3-volume)..."
modal deploy backend/modal_jobs/train_sam3_job.py

echo "[2/8] YOLO models volume..."
modal deploy backend/modal_jobs/model_volume.py

# --- Step 2: Jobs that USE volumes (deploy after) ---
echo ""
echo "── GPU Jobs ──"

echo "[3/8] Hybrid inference..."
modal deploy backend/modal_jobs/hybrid_infer_job.py

echo "[4/8] Inference..."
modal deploy backend/modal_jobs/infer_job.py

echo "[5/8] Detection training..."
modal deploy backend/modal_jobs/train_job.py

echo "[6/8] Classification training..."
modal deploy backend/modal_jobs/train_classify_job.py

echo "[7/8] Autolabel..."
modal deploy backend/modal_jobs/autolabel_job.py

# --- Step 3: API ---
echo ""
echo "── API Server ──"
echo "[8/8] API server..."
modal deploy backend/api/server.py

echo ""
echo "✅ All Modal apps deployed successfully!"
echo ""
echo "Verify with: modal app list"
echo ""
echo "NOTE: If this is a fresh deployment, upload SAM3 model weights:"
echo "  modal volume put sam3-volume /path/to/sam3.pt /models/sam3.pt"
