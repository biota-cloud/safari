#!/usr/bin/env python3
"""
SAFARI Remote GPU Worker Verification Script.

Run this after remote_setup.sh to verify the environment is correctly configured.

Usage:
    ~/.tyto/venv/bin/python ~/.tyto/scripts/verify_remote.py

Checks:
    1. Python version
    2. GPU access (CUDA available)
    3. Required packages installed
    4. SAM3 model loadable
    5. Environment variables set
    6. R2/Supabase connectivity
"""

import os
import sys
from pathlib import Path

# Colors for terminal output
GREEN = "\033[0;32m"
RED = "\033[0;31m"
YELLOW = "\033[1;33m"
NC = "\033[0m"  # No Color


def check_mark(success: bool) -> str:
    return f"{GREEN}✓{NC}" if success else f"{RED}✗{NC}"


def main():
    print(f"\n{YELLOW}{'='*50}{NC}")
    print(f"{YELLOW}  SAFARI Remote GPU Worker Verification{NC}")
    print(f"{YELLOW}{'='*50}{NC}\n")

    all_passed = True
    
    # =========================================================================
    # 1. Python version
    # =========================================================================
    print(f"[1/6] Python version...")
    py_version = sys.version_info
    py_ok = py_version.major == 3 and py_version.minor >= 11
    print(f"  {check_mark(py_ok)} Python {py_version.major}.{py_version.minor}.{py_version.micro}")
    all_passed &= py_ok

    # =========================================================================
    # 2. GPU / CUDA availability
    # =========================================================================
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

    # =========================================================================
    # 3. Required packages
    # =========================================================================
    print(f"\n[3/6] Required packages...")
    packages = [
        ("ultralytics", "8.3.0"),
        ("boto3", None),
        ("supabase", None),
        ("requests", None),
        ("PIL", None),  # pillow
        ("ftfy", None),
        ("timm", None),
        ("dotenv", None),  # python-dotenv
    ]
    
    for pkg_name, min_version in packages:
        try:
            if pkg_name == "PIL":
                import PIL
                version = PIL.__version__
            elif pkg_name == "dotenv":
                import dotenv
                version = getattr(dotenv, "__version__", "installed")
            else:
                mod = __import__(pkg_name)
                version = getattr(mod, "__version__", "installed")
            print(f"  {check_mark(True)} {pkg_name} ({version})")
        except ImportError:
            print(f"  {check_mark(False)} {pkg_name} - NOT INSTALLED")
            all_passed = False

    # =========================================================================
    # 4. SAM3 predictor
    # =========================================================================
    print(f"\n[4/6] SAM3 predictor...")
    try:
        import os as _os
        _os.environ['ULTRALYTICS_AUTOUPDATE'] = 'false'
        
        # Check for local SAM3 model downloaded from Modal volume
        tyto_home = Path.home() / ".tyto"
        sam3_model_path = tyto_home / "models" / "sam3.pt"
        
        if not sam3_model_path.exists():
            print(f"  {check_mark(False)} SAM3 model not found at {sam3_model_path}")
            print(f"  {YELLOW}Run: modal volume get sam3-volume /sam3.pt ~/.tyto/models/sam3.pt{NC}")
            all_passed = False
        else:
            print(f"  {check_mark(True)} SAM3 model found ({sam3_model_path.stat().st_size / (1024**3):.1f} GB)")
            
            from ultralytics.models.sam import SAM3SemanticPredictor
            predictor = SAM3SemanticPredictor(overrides=dict(
                task='segment',
                mode='predict',
                model=str(sam3_model_path),
                save=False,
            ))
            print(f"  {check_mark(True)} SAM3SemanticPredictor loads successfully")
    except Exception as e:
        print(f"  {check_mark(False)} SAM3 failed to load: {e}")
        all_passed = False

    # =========================================================================
    # 5. Environment variables
    # =========================================================================
    print(f"\n[5/6] Environment variables...")
    tyto_home = Path.home() / ".tyto"
    env_file = tyto_home / ".env"
    
    if env_file.exists():
        print(f"  {check_mark(True)} .env file found")
        
        # Load and check
        from dotenv import load_dotenv
        load_dotenv(env_file)
        
        required_vars = [
            "SUPABASE_URL",
            "SUPABASE_KEY",
            "R2_ENDPOINT_URL",
            "R2_ACCESS_KEY_ID",
            "R2_SECRET_ACCESS_KEY",
            "R2_BUCKET_NAME",
        ]
        
        for var in required_vars:
            value = os.environ.get(var)
            if value and not value.startswith("your-"):
                print(f"  {check_mark(True)} {var} is set")
            else:
                print(f"  {check_mark(False)} {var} - NOT SET or placeholder")
                all_passed = False
    else:
        print(f"  {check_mark(False)} .env file not found at {env_file}")
        all_passed = False

    # =========================================================================
    # 6. Connectivity test
    # =========================================================================
    print(f"\n[6/6] Connectivity test...")
    
    # Test Supabase
    supabase_ok = False
    try:
        supabase_url = os.environ.get("SUPABASE_URL")
        if supabase_url and not supabase_url.startswith("https://your-"):
            import requests
            resp = requests.get(f"{supabase_url}/rest/v1/", timeout=5)
            supabase_ok = resp.status_code in [200, 401]  # 401 means auth required, but reachable
            print(f"  {check_mark(supabase_ok)} Supabase reachable")
        else:
            print(f"  {check_mark(False)} Supabase URL not configured")
    except Exception as e:
        print(f"  {check_mark(False)} Supabase connection failed: {e}")
    all_passed &= supabase_ok

    # Test R2
    r2_ok = False
    try:
        r2_endpoint = os.environ.get("R2_ENDPOINT_URL")
        if r2_endpoint and not r2_endpoint.startswith("https://your-"):
            import boto3
            from botocore.config import Config
            s3 = boto3.client(
                "s3",
                endpoint_url=os.environ["R2_ENDPOINT_URL"],
                aws_access_key_id=os.environ["R2_ACCESS_KEY_ID"],
                aws_secret_access_key=os.environ["R2_SECRET_ACCESS_KEY"],
                config=Config(signature_version="s3v4"),
                region_name="auto",
            )
            # Try listing bucket (will fail if creds wrong, but confirms connectivity)
            bucket = os.environ["R2_BUCKET_NAME"]
            s3.list_objects_v2(Bucket=bucket, MaxKeys=1)
            r2_ok = True
            print(f"  {check_mark(True)} R2 storage reachable")
        else:
            print(f"  {check_mark(False)} R2 endpoint not configured")
    except Exception as e:
        print(f"  {check_mark(False)} R2 connection failed: {e}")
    all_passed &= r2_ok

    # =========================================================================
    # Summary
    # =========================================================================
    print(f"\n{YELLOW}{'='*50}{NC}")
    if all_passed:
        print(f"{GREEN}  All checks passed! Worker is ready.{NC}")
    else:
        print(f"{RED}  Some checks failed. Please fix the issues above.{NC}")
    print(f"{YELLOW}{'='*50}{NC}\n")

    return 0 if all_passed else 1


if __name__ == "__main__":
    sys.exit(main())
