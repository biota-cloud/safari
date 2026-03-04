#!/bin/bash
# ============================================================================
# Tyto Remote GPU Worker — One-Line Installer
# ============================================================================
# Install with:
#   curl -sSL https://raw.githubusercontent.com/your-org/tyto/main/scripts/remote_workers/install.sh | bash
#
# Or run directly:
#   bash install.sh
#
# This script will:
#   1. Check prerequisites (Python 3.11+, NVIDIA GPU)
#   2. Create ~/.tyto directory structure
#   3. Create Python virtual environment
#   4. Install all dependencies (Ultralytics, SAM3, CLIP, etc.)
#   5. Download SAM3 model
#   6. Prompt for R2/Supabase credentials
#   7. Install worker scripts
#   8. Verify the installation
# ============================================================================

set -e

# Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m'

# Configuration
TYTO_HOME="${HOME}/.tyto"
VENV_PATH="${TYTO_HOME}/venv"
SCRIPTS_PATH="${TYTO_HOME}/scripts"
MODELS_PATH="${TYTO_HOME}/models"
DATA_PATH="${TYTO_HOME}/data"
LOGS_PATH="${TYTO_HOME}/logs"

echo ""
echo -e "${BLUE}╔═══════════════════════════════════════════════════════════╗${NC}"
echo -e "${BLUE}║                                                           ║${NC}"
echo -e "${BLUE}║   ${GREEN}🦉 Tyto Remote GPU Worker Installer${BLUE}                     ║${NC}"
echo -e "${BLUE}║                                                           ║${NC}"
echo -e "${BLUE}╚═══════════════════════════════════════════════════════════╝${NC}"
echo ""

# Detect non-interactive mode (no TTY = running via curl | bash or SSH without -t)
if [ -t 0 ]; then
    INTERACTIVE=true
else
    INTERACTIVE=false
    echo -e "${YELLOW}Running in non-interactive mode. Prompts will be auto-skipped.${NC}"
    echo -e "${YELLOW}To enter credentials interactively, run: ssh -t user@host 'bash install.sh'${NC}"
    echo ""
fi

# ============================================================================
# Step 1: Check prerequisites
# ============================================================================
echo -e "${YELLOW}[1/7] Checking prerequisites...${NC}"

# Check for Python 3.11 or 3.12
PYTHON_CMD=""
if command -v python3.12 &> /dev/null; then
    PYTHON_CMD="python3.12"
elif command -v python3.11 &> /dev/null; then
    PYTHON_CMD="python3.11"
elif command -v python3 &> /dev/null; then
    PY_VERSION=$(python3 -c "import sys; print(f'{sys.version_info.major}.{sys.version_info.minor}')")
    PY_MAJOR=$(echo $PY_VERSION | cut -d. -f1)
    PY_MINOR=$(echo $PY_VERSION | cut -d. -f2)
    if [ "$PY_MAJOR" -eq 3 ] && [ "$PY_MINOR" -ge 11 ]; then
        PYTHON_CMD="python3"
    fi
fi

if [ -z "$PYTHON_CMD" ]; then
    echo -e "${RED}Error: Python 3.11 or later not found.${NC}"
    echo "Install with: sudo apt install python3.11 python3.11-venv python3.11-dev"
    exit 1
fi
echo -e "  ${GREEN}✓${NC} Python: $($PYTHON_CMD --version)"

# Check NVIDIA GPU
if ! command -v nvidia-smi &> /dev/null; then
    echo -e "${RED}Error: nvidia-smi not found. NVIDIA drivers may not be installed.${NC}"
    exit 1
fi
GPU_NAME=$(nvidia-smi --query-gpu=name --format=csv,noheader,nounits | head -n1)
GPU_VRAM=$(nvidia-smi --query-gpu=memory.total --format=csv,noheader,nounits | head -n1)
echo -e "  ${GREEN}✓${NC} GPU: ${GPU_NAME} (${GPU_VRAM}MB VRAM)"

# ============================================================================
# Step 2: Create directory structure
# ============================================================================
echo -e "\n${YELLOW}[2/7] Creating directory structure...${NC}"

mkdir -p "${TYTO_HOME}" "${SCRIPTS_PATH}" "${MODELS_PATH}" "${DATA_PATH}" "${LOGS_PATH}"
echo -e "  ${GREEN}✓${NC} Created ${TYTO_HOME}/"

# ============================================================================
# Step 3: Create Python virtual environment
# ============================================================================
echo -e "\n${YELLOW}[3/7] Setting up Python environment...${NC}"

if [ -d "${VENV_PATH}" ]; then
    echo -e "  Virtual environment already exists."
    if [ "$INTERACTIVE" = true ]; then
        read -p "  Recreate it? [y/N] " -n 1 -r
        echo
        if [[ $REPLY =~ ^[Yy]$ ]]; then
            rm -rf "${VENV_PATH}"
            $PYTHON_CMD -m venv "${VENV_PATH}"
            echo -e "  ${GREEN}✓${NC} Virtual environment recreated"
        else
            echo -e "  ${GREEN}✓${NC} Keeping existing virtual environment"
        fi
    else
        echo -e "  ${GREEN}✓${NC} Keeping existing virtual environment (non-interactive)"
    fi
else
    $PYTHON_CMD -m venv "${VENV_PATH}"
    echo -e "  ${GREEN}✓${NC} Virtual environment created"
fi

source "${VENV_PATH}/bin/activate"

# ============================================================================
# Step 4: Install dependencies
# ============================================================================
echo -e "\n${YELLOW}[4/7] Installing Python dependencies...${NC}"
echo "  This may take 5-10 minutes on first install..."

pip install --upgrade pip --quiet 2>/dev/null

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
    --quiet 2>/dev/null

echo -e "  ${GREEN}✓${NC} Core dependencies installed"

# Install CLIP (required for SAM3)
pip install git+https://github.com/ultralytics/CLIP.git --quiet 2>/dev/null
echo -e "  ${GREEN}✓${NC} CLIP installed"

# ============================================================================
# Step 5: Warmup SAM3 (auto-downloads model on first use)
# ============================================================================
echo -e "\n${YELLOW}[5/7] Warming up SAM3 predictor...${NC}"
echo "  This downloads the SAM3 model on first run (~350MB)..."

python -c "
import os
os.environ['ULTRALYTICS_AUTOUPDATE'] = 'false'

# SAM3SemanticPredictor auto-downloads the model on first use
from ultralytics.models.sam import SAM3SemanticPredictor

print('  Loading SAM3SemanticPredictor...')
predictor = SAM3SemanticPredictor(overrides=dict(
    task='segment',
    mode='predict',
    half=False,
    save=False,
))
print('  SAM3 ready!')
"
echo -e "  ${GREEN}✓${NC} SAM3 warmed up successfully"

# ============================================================================
# Step 6: Configure credentials
# ============================================================================
echo -e "\n${YELLOW}[6/7] Configuring credentials...${NC}"

ENV_FILE="${TYTO_HOME}/.env"
if [ -f "${ENV_FILE}" ]; then
    echo -e "  ${GREEN}✓${NC} .env file already exists — keeping existing credentials"
    SKIP_CREDS=true
else
    if [ "$INTERACTIVE" = true ]; then
        echo ""
        echo -e "  ${BLUE}Enter your Supabase credentials:${NC}"
        read -p "    SUPABASE_URL (e.g., https://xxx.supabase.co): " SUPABASE_URL
        read -p "    SUPABASE_KEY (anon key): " SUPABASE_KEY
        
        echo ""
        echo -e "  ${BLUE}Enter your Cloudflare R2 credentials:${NC}"
        read -p "    R2_ENDPOINT_URL (e.g., https://xxx.r2.cloudflarestorage.com): " R2_ENDPOINT_URL
        read -p "    R2_ACCESS_KEY_ID: " R2_ACCESS_KEY_ID
        read -s -p "    R2_SECRET_ACCESS_KEY: " R2_SECRET_ACCESS_KEY
        echo ""
        read -p "    R2_BUCKET_NAME: " R2_BUCKET_NAME

        cat > "${ENV_FILE}" << EOF
# Tyto Remote GPU Worker Environment
# Generated by install.sh on $(date)

# Supabase
SUPABASE_URL=${SUPABASE_URL}
SUPABASE_KEY=${SUPABASE_KEY}

# Cloudflare R2
R2_ENDPOINT_URL=${R2_ENDPOINT_URL}
R2_ACCESS_KEY_ID=${R2_ACCESS_KEY_ID}
R2_SECRET_ACCESS_KEY=${R2_SECRET_ACCESS_KEY}
R2_BUCKET_NAME=${R2_BUCKET_NAME}
EOF

        chmod 600 "${ENV_FILE}"
        echo -e "  ${GREEN}✓${NC} Credentials saved to ${ENV_FILE}"
    else
        echo -e "  ${YELLOW}⚠️  No .env file found. Skipping credentials (non-interactive mode).${NC}"
        echo -e "  ${YELLOW}   Copy your .env file manually: scp .env user@host:~/.tyto/.env${NC}"
        SKIP_CREDS=true
    fi
fi

# ============================================================================
# Step 7: Install worker scripts (embedded)
# ============================================================================
echo -e "\n${YELLOW}[7/7] Installing worker scripts...${NC}"

# Create remote_utils.py
cat > "${SCRIPTS_PATH}/remote_utils.py" << 'SCRIPT_EOF'
"""
Tyto Remote Worker Utilities.

Shared utilities for all remote worker scripts:
- Environment loading
- Supabase logging (LogCapture)
- R2 file operations
"""

import os
import sys
import json
from pathlib import Path
from datetime import datetime
from typing import Optional
import threading
import time

# Load environment from ~/.tyto/.env
from dotenv import load_dotenv

TYTO_HOME = Path.home() / ".tyto"
load_dotenv(TYTO_HOME / ".env")


class LogCapture:
    """
    Context manager for capturing logs and streaming to Supabase.
    
    Mirrors the Modal LogCapture pattern for consistency.
    """
    
    def __init__(
        self,
        run_id: str,
        table: str = "training_runs",
        log_column: str = "logs",
        flush_interval: float = 2.0
    ):
        self.run_id = run_id
        self.table = table
        self.log_column = log_column
        self.flush_interval = flush_interval
        self.logs: list[str] = []
        self._lock = threading.Lock()
        self._stop_event = threading.Event()
        self._flush_thread: Optional[threading.Thread] = None
        self._supabase = None
    
    def _get_supabase(self):
        if self._supabase is None:
            from supabase import create_client
            self._supabase = create_client(
                os.environ["SUPABASE_URL"],
                os.environ["SUPABASE_KEY"]
            )
        return self._supabase
    
    def _flush_loop(self):
        while not self._stop_event.wait(self.flush_interval):
            self._flush()
    
    def _flush(self):
        with self._lock:
            if not self.logs:
                return
            logs_to_send = self.logs.copy()
        
        try:
            sb = self._get_supabase()
            sb.table(self.table).update({
                self.log_column: "\n".join(logs_to_send)
            }).eq("id", self.run_id).execute()
        except Exception as e:
            print(f"[LogCapture] Failed to flush logs: {e}", file=sys.stderr)
    
    def log(self, message: str):
        timestamp = datetime.now().strftime("%H:%M:%S")
        formatted = f"[{timestamp}] {message}"
        with self._lock:
            self.logs.append(formatted)
        print(formatted)
    
    def __enter__(self):
        self._flush_thread = threading.Thread(target=self._flush_loop, daemon=True)
        self._flush_thread.start()
        return self
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        self._stop_event.set()
        if self._flush_thread:
            self._flush_thread.join(timeout=5)
        self._flush()
        return False


def get_r2_client():
    """Get a configured boto3 S3 client for R2."""
    import boto3
    from botocore.config import Config
    
    return boto3.client(
        "s3",
        endpoint_url=os.environ["R2_ENDPOINT_URL"],
        aws_access_key_id=os.environ["R2_ACCESS_KEY_ID"],
        aws_secret_access_key=os.environ["R2_SECRET_ACCESS_KEY"],
        config=Config(signature_version="s3v4"),
        region_name="auto",
    )


def download_from_r2(key: str, local_path: Path) -> Path:
    """Download a file from R2 to local path."""
    s3 = get_r2_client()
    bucket = os.environ["R2_BUCKET_NAME"]
    local_path.parent.mkdir(parents=True, exist_ok=True)
    s3.download_file(bucket, key, str(local_path))
    return local_path


def upload_to_r2(local_path: Path, key: str) -> str:
    """Upload a file to R2, return the key."""
    s3 = get_r2_client()
    bucket = os.environ["R2_BUCKET_NAME"]
    s3.upload_file(str(local_path), bucket, key)
    return key


def get_supabase():
    """Get a configured Supabase client."""
    from supabase import create_client
    return create_client(
        os.environ["SUPABASE_URL"],
        os.environ["SUPABASE_KEY"]
    )
SCRIPT_EOF

echo -e "  ${GREEN}✓${NC} Installed remote_utils.py"

# Create verify_remote.py
cat > "${SCRIPTS_PATH}/verify_remote.py" << 'SCRIPT_EOF'
#!/usr/bin/env python3
"""Tyto Remote GPU Worker Verification Script."""

import os
import sys
from pathlib import Path

GREEN = "\033[0;32m"
RED = "\033[0;31m"
YELLOW = "\033[1;33m"
NC = "\033[0m"

def check_mark(success: bool) -> str:
    return f"{GREEN}✓{NC}" if success else f"{RED}✗{NC}"

def main():
    print(f"\n{YELLOW}{'='*50}{NC}")
    print(f"{YELLOW}  Tyto Remote GPU Worker Verification{NC}")
    print(f"{YELLOW}{'='*50}{NC}\n")

    all_passed = True
    
    # 1. Python version
    print(f"[1/6] Python version...")
    py_version = sys.version_info
    py_ok = py_version.major == 3 and py_version.minor >= 11
    print(f"  {check_mark(py_ok)} Python {py_version.major}.{py_version.minor}.{py_version.micro}")
    all_passed &= py_ok

    # 2. GPU / CUDA
    print(f"\n[2/6] GPU / CUDA availability...")
    try:
        import torch
        cuda_available = torch.cuda.is_available()
        if cuda_available:
            gpu_name = torch.cuda.get_device_name(0)
            gpu_mem = torch.cuda.get_device_properties(0).total_memory / (1024**3)
            print(f"  {check_mark(True)} CUDA available")
            print(f"  {check_mark(True)} GPU: {gpu_name} ({gpu_mem:.1f} GB)")
        else:
            print(f"  {check_mark(False)} CUDA not available")
            all_passed = False
    except ImportError:
        print(f"  {check_mark(False)} PyTorch not installed")
        all_passed = False

    # 3. Required packages
    print(f"\n[3/6] Required packages...")
    packages = ["ultralytics", "boto3", "supabase", "PIL", "ftfy", "timm", "dotenv"]
    for pkg in packages:
        try:
            if pkg == "PIL":
                import PIL
            elif pkg == "dotenv":
                import dotenv
            else:
                __import__(pkg)
            print(f"  {check_mark(True)} {pkg}")
        except ImportError:
            print(f"  {check_mark(False)} {pkg} - NOT INSTALLED")
            all_passed = False

    # 4. SAM3 predictor
    print(f"\n[4/6] SAM3 predictor...")
    try:
        import os
        os.environ['ULTRALYTICS_AUTOUPDATE'] = 'false'
        from ultralytics.models.sam import SAM3SemanticPredictor
        predictor = SAM3SemanticPredictor(overrides=dict(task='segment', mode='predict', save=False))
        print(f"  {check_mark(True)} SAM3SemanticPredictor loads successfully")
    except Exception as e:
        print(f"  {check_mark(False)} SAM3 failed: {e}")
        all_passed = False

    # 5. Environment variables
    print(f"\n[5/6] Environment variables...")
    from dotenv import load_dotenv
    load_dotenv(Path.home() / ".tyto" / ".env")
    
    required_vars = ["SUPABASE_URL", "SUPABASE_KEY", "R2_ENDPOINT_URL", "R2_ACCESS_KEY_ID", "R2_SECRET_ACCESS_KEY", "R2_BUCKET_NAME"]
    for var in required_vars:
        value = os.environ.get(var)
        if value and not value.startswith("your-"):
            print(f"  {check_mark(True)} {var}")
        else:
            print(f"  {check_mark(False)} {var} - NOT SET")
            all_passed = False

    # 6. Connectivity
    print(f"\n[6/6] Connectivity test...")
    try:
        import requests
        supabase_url = os.environ.get("SUPABASE_URL")
        if supabase_url:
            resp = requests.get(f"{supabase_url}/rest/v1/", timeout=5)
            print(f"  {check_mark(resp.status_code in [200, 401])} Supabase reachable")
    except Exception as e:
        print(f"  {check_mark(False)} Supabase: {e}")
        all_passed = False

    print(f"\n{YELLOW}{'='*50}{NC}")
    if all_passed:
        print(f"{GREEN}  All checks passed! Worker is ready.{NC}")
    else:
        print(f"{RED}  Some checks failed. Review issues above.{NC}")
    print(f"{YELLOW}{'='*50}{NC}\n")

    return 0 if all_passed else 1

if __name__ == "__main__":
    sys.exit(main())
SCRIPT_EOF

chmod +x "${SCRIPTS_PATH}/verify_remote.py"
echo -e "  ${GREEN}✓${NC} Installed verify_remote.py"

# ============================================================================
# Complete!
# ============================================================================
echo ""
echo -e "${BLUE}╔═══════════════════════════════════════════════════════════╗${NC}"
echo -e "${BLUE}║                                                           ║${NC}"
echo -e "${BLUE}║   ${GREEN}✅ Installation Complete!${BLUE}                              ║${NC}"
echo -e "${BLUE}║                                                           ║${NC}"
echo -e "${BLUE}╚═══════════════════════════════════════════════════════════╝${NC}"
echo ""
echo -e "  ${GREEN}TYTO_HOME:${NC}    ${TYTO_HOME}"
echo -e "  ${GREEN}Python:${NC}       ${VENV_PATH}/bin/python"
echo -e "  ${GREEN}GPU:${NC}          ${GPU_NAME}"
echo ""
echo -e "  ${YELLOW}Next step:${NC} Run verification:"
echo -e "    ${TYTO_HOME}/venv/bin/python ${TYTO_HOME}/scripts/verify_remote.py"
echo ""
