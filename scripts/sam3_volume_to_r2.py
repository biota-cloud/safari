"""
Transfer sam3.pt between Modal workspaces via R2.

Step 1 (personal Modal creds - run from local machine):
    modal run scripts/sam3_volume_to_r2.py::upload_to_r2

Step 2 (Biota Modal creds - run from VPS):
    modal run scripts/sam3_volume_to_r2.py::download_from_r2

This avoids downloading 3.2GB through your laptop.
Delete the R2 copy after transfer: it's only needed for migration.
"""

import modal

app = modal.App("sam3-transfer")

image = modal.Image.debian_slim(python_version="3.11").pip_install("boto3")

R2_KEY = "models/sam3_base.pt"  # Temporary R2 path for transfer


# --- Step 1: Volume → R2 (run with personal Modal creds) ---
@app.function(
    image=image,
    volumes={"/vol": modal.Volume.from_name("sam3-volume")},
    secrets=[modal.Secret.from_name("r2-credentials")],
    timeout=600,
)
def upload_to_r2():
    """Copy sam3.pt from personal Modal volume to R2."""
    import boto3, os
    from botocore.config import Config
    from pathlib import Path

    src = Path("/vol/sam3.pt")
    if not src.exists():
        print("❌ sam3.pt not found in volume root!")
        return

    size_mb = src.stat().st_size / 1024 / 1024
    print(f"📦 Found sam3.pt ({size_mb:.0f} MB)")

    s3 = boto3.client("s3",
        endpoint_url=os.environ["R2_ENDPOINT_URL"],
        aws_access_key_id=os.environ["R2_ACCESS_KEY_ID"],
        aws_secret_access_key=os.environ["R2_SECRET_ACCESS_KEY"],
        config=Config(signature_version="s3v4"),
        region_name="auto",
    )
    bucket = os.environ["R2_BUCKET_NAME"]

    print(f"⬆️  Uploading to R2: {bucket}/{R2_KEY} ...")
    s3.upload_file(str(src), bucket, R2_KEY)
    print("✅ Upload complete!")


# --- Step 2: R2 → Volume (run with Biota Modal creds) ---
@app.function(
    image=image,
    volumes={"/vol": modal.Volume.from_name("sam3-volume", create_if_missing=True)},
    secrets=[modal.Secret.from_name("r2-credentials")],
    timeout=600,
)
def download_from_r2():
    """Copy sam3.pt from R2 to Biota Modal volume."""
    import boto3, os
    from botocore.config import Config
    from pathlib import Path

    s3 = boto3.client("s3",
        endpoint_url=os.environ["R2_ENDPOINT_URL"],
        aws_access_key_id=os.environ["R2_ACCESS_KEY_ID"],
        aws_secret_access_key=os.environ["R2_SECRET_ACCESS_KEY"],
        config=Config(signature_version="s3v4"),
        region_name="auto",
    )
    bucket = os.environ["R2_BUCKET_NAME"]

    dest = Path("/vol/sam3.pt")
    print(f"⬇️  Downloading from R2: {bucket}/{R2_KEY} ...")
    s3.download_file(bucket, R2_KEY, str(dest))

    size_mb = dest.stat().st_size / 1024 / 1024
    print(f"📦 Downloaded {size_mb:.0f} MB to volume")

    # Also put in /models/ path (where inference jobs expect it)
    models_dir = Path("/vol/models")
    models_dir.mkdir(exist_ok=True)
    import shutil
    shutil.copy(dest, models_dir / "sam3.pt")
    print("📁 Copied to /models/sam3.pt")

    modal.Volume.from_name("sam3-volume").commit()
    print("✅ Volume committed!")
