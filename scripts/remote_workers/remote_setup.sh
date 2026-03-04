#!/bin/bash
# ============================================================================
# Tyto Remote GPU Worker Setup Script
# ============================================================================
# Run this on your local GPU machine to prepare it for Tyto workloads.
# 
# Prerequisites:
#   - Ubuntu 22.04 or later
#   - NVIDIA GPU with CUDA 12+ drivers installed
#   - Python 3.11 available (python3.11)
#   - SSH access configured from the Tyto server
#
# Usage:
#   curl -sSL https://raw.githubusercontent.com/.../remote_setup.sh | bash
#   # or
#   bash remote_setup.sh
#
# After running this script, you should:
#   1. Copy your R2/Supabase credentials to ~/.tyto/.env
#   2. Test with: ~/.tyto/venv/bin/python ~/.tyto/scripts/verify_remote.py
# ============================================================================

set -e  # Exit on error

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# Configuration
TYTO_HOME="${HOME}/.tyto"
VENV_PATH="${TYTO_HOME}/venv"
SCRIPTS_PATH="${TYTO_HOME}/scripts"
MODELS_PATH="${TYTO_HOME}/models"
DATA_PATH="${TYTO_HOME}/data"
LOGS_PATH="${TYTO_HOME}/logs"

echo -e "${GREEN}============================================${NC}"
echo -e "${GREEN}   Tyto Remote GPU Worker Setup${NC}"
echo -e "${GREEN}============================================${NC}"
echo ""

# ============================================================================
# Step 1: Check prerequisites
# ============================================================================
echo -e "${YELLOW}[1/6] Checking prerequisites...${NC}"

# Check Python 3.11
if ! command -v python3.11 &> /dev/null; then
    echo -e "${RED}Error: Python 3.11 not found.${NC}"
    echo "Install with: sudo apt install python3.11 python3.11-venv python3.11-dev"
    exit 1
fi
echo "  ✓ Python 3.11 found: $(python3.11 --version)"

# Check NVIDIA GPU
if ! command -v nvidia-smi &> /dev/null; then
    echo -e "${RED}Error: nvidia-smi not found. NVIDIA drivers may not be installed.${NC}"
    exit 1
fi
GPU_NAME=$(nvidia-smi --query-gpu=name --format=csv,noheader,nounits | head -n1)
GPU_VRAM=$(nvidia-smi --query-gpu=memory.total --format=csv,noheader,nounits | head -n1)
echo "  ✓ GPU found: ${GPU_NAME} (${GPU_VRAM}MB VRAM)"

# Check CUDA
CUDA_VERSION=$(nvidia-smi --query-gpu=driver_version --format=csv,noheader | head -n1)
echo "  ✓ NVIDIA Driver: ${CUDA_VERSION}"

# ============================================================================
# Step 2: Create directory structure
# ============================================================================
echo -e "\n${YELLOW}[2/6] Creating directory structure...${NC}"

mkdir -p "${TYTO_HOME}"
mkdir -p "${SCRIPTS_PATH}"
mkdir -p "${MODELS_PATH}"
mkdir -p "${DATA_PATH}"
mkdir -p "${LOGS_PATH}"

echo "  ✓ Created ${TYTO_HOME}"
echo "  ✓ Created ${SCRIPTS_PATH}"
echo "  ✓ Created ${MODELS_PATH}"
echo "  ✓ Created ${DATA_PATH}"
echo "  ✓ Created ${LOGS_PATH}"

# ============================================================================
# Step 3: Create Python virtual environment
# ============================================================================
echo -e "\n${YELLOW}[3/6] Creating Python virtual environment...${NC}"

if [ -d "${VENV_PATH}" ]; then
    echo "  Virtual environment already exists at ${VENV_PATH}"
    read -p "  Recreate it? [y/N] " -n 1 -r
    echo
    if [[ $REPLY =~ ^[Yy]$ ]]; then
        rm -rf "${VENV_PATH}"
        python3.11 -m venv "${VENV_PATH}"
        echo "  ✓ Virtual environment recreated"
    else
        echo "  ✓ Keeping existing virtual environment"
    fi
else
    python3.11 -m venv "${VENV_PATH}"
    echo "  ✓ Virtual environment created at ${VENV_PATH}"
fi

# Activate venv
source "${VENV_PATH}/bin/activate"

# ============================================================================
# Step 4: Install dependencies
# ============================================================================
echo -e "\n${YELLOW}[4/6] Installing Python dependencies...${NC}"
echo "  This may take a few minutes..."

pip install --upgrade pip --quiet

# Install core dependencies (same as Modal image)
pip install \
    "ultralytics>=8.3.237" \
    boto3 \
    supabase \
    requests \
    pillow \
    ftfy \
    regex \
    timm \
    huggingface_hub \
    python-dotenv \
    fastapi \
    uvicorn \
    --quiet

echo "  ✓ Core dependencies installed"

# Install Ultralytics CLIP fork (required for SAM3)
echo "  Installing CLIP for SAM3..."
pip install git+https://github.com/ultralytics/CLIP.git --quiet
echo "  ✓ CLIP installed"

# ============================================================================
# Step 5: Download SAM3 model
# ============================================================================
echo -e "\n${YELLOW}[5/6] Downloading SAM3 model...${NC}"

SAM3_MODEL="${MODELS_PATH}/sam3_b.pt"
if [ -f "${SAM3_MODEL}" ]; then
    echo "  SAM3 model already exists at ${SAM3_MODEL}"
else
    echo "  Downloading SAM3 base model (this may take a while)..."
    python -c "
from ultralytics import SAM
import shutil
model = SAM('sam3_b.pt')
# Move to models directory
import os
src = os.path.expanduser('~/.config/Ultralytics/sam3_b.pt')
if os.path.exists(src):
    shutil.copy(src, '${SAM3_MODEL}')
print('SAM3 model ready')
"
    echo "  ✓ SAM3 model downloaded to ${SAM3_MODEL}"
fi

# ============================================================================
# Step 6: Create .env template
# ============================================================================
echo -e "\n${YELLOW}[6/6] Creating environment template...${NC}"

ENV_FILE="${TYTO_HOME}/.env"
if [ -f "${ENV_FILE}" ]; then
    echo "  .env file already exists at ${ENV_FILE}"
else
    cat > "${ENV_FILE}" << 'EOF'
# Tyto Remote GPU Worker Environment
# Fill in these values from your Supabase and R2 dashboards

# Supabase
SUPABASE_URL=https://your-project.supabase.co
SUPABASE_KEY=your-anon-key

# Cloudflare R2
R2_ENDPOINT_URL=https://your-account-id.r2.cloudflarestorage.com
R2_ACCESS_KEY_ID=your-access-key
R2_SECRET_ACCESS_KEY=your-secret-key
R2_BUCKET_NAME=tyto-bucket
EOF
    echo "  ✓ Created .env template at ${ENV_FILE}"
    echo -e "  ${RED}⚠️  IMPORTANT: Edit ${ENV_FILE} with your credentials!${NC}"
fi

# ============================================================================
# Summary
# ============================================================================
echo ""
echo -e "${GREEN}============================================${NC}"
echo -e "${GREEN}   Setup Complete!${NC}"
echo -e "${GREEN}============================================${NC}"
echo ""
echo "  TYTO_HOME:    ${TYTO_HOME}"
echo "  Python:       ${VENV_PATH}/bin/python"
echo "  GPU:          ${GPU_NAME} (${GPU_VRAM}MB)"
echo ""
echo "  Next steps:"
echo "    1. Edit ${ENV_FILE} with your credentials"
echo "    2. Worker scripts will be synced to ${SCRIPTS_PATH}"
echo "    3. Test with: ${VENV_PATH}/bin/python ${SCRIPTS_PATH}/verify_remote.py"
echo ""
