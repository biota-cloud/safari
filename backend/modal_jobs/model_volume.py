"""
Modal Volume for YOLO Model Storage.

Models are uploaded here after training completion for fast inference access.
This avoids downloading from R2 on every autolabel job.

Folder structure in volume: /models/{model_id}.pt

Usage:
    # Deploy this module first
    modal deploy backend/modal_jobs/model_volume.py
    
    # Then from Python:
    import modal
    upload_fn = modal.Function.from_name("yolo-models", "upload_model_to_volume")
    volume_path = upload_fn.remote(r2_weights_path="training_runs/.../best.pt", model_id="...")
"""

import os
from pathlib import Path

import modal

# Create the Modal app
app = modal.App("yolo-models")

# Create or get the volume for model storage
models_volume = modal.Volume.from_name("yolo-models-volume", create_if_missing=True)

# Minimal image for file operations
image = (
    modal.Image.debian_slim(python_version="3.11")
    .pip_install("boto3")
)


@app.function(
    image=image,
    volumes={"/models": models_volume},
    secrets=[modal.Secret.from_name("r2-credentials")],
    timeout=300,
)
def upload_model_to_volume(r2_weights_path: str, model_id: str) -> str:
    """
    Download model from R2 and upload to Modal volume.
    
    Args:
        r2_weights_path: R2 path like "training_runs/{run_id}/best.pt"
        model_id: UUID for organizing in volume
        
    Returns:
        Volume path like "/models/{model_id}.pt"
    """
    import boto3
    from botocore.config import Config
    
    print(f"Uploading model {model_id} from R2 path: {r2_weights_path}")
    
    # Initialize S3 client for R2
    s3 = boto3.client(
        's3',
        endpoint_url=os.environ['R2_ENDPOINT_URL'],
        aws_access_key_id=os.environ['R2_ACCESS_KEY_ID'],
        aws_secret_access_key=os.environ['R2_SECRET_ACCESS_KEY'],
        config=Config(signature_version='s3v4'),
        region_name='auto',
    )
    bucket = os.environ['R2_BUCKET_NAME']
    
    # Download from R2 to temp location
    local_temp = Path(f"/tmp/{model_id}.pt")
    print(f"Downloading from R2 bucket '{bucket}' key '{r2_weights_path}'...")
    s3.download_file(bucket, r2_weights_path, str(local_temp))
    print(f"Downloaded {local_temp.stat().st_size / 1024 / 1024:.1f} MB")
    
    # Copy to volume
    volume_path = Path(f"/models/{model_id}.pt")
    volume_path.parent.mkdir(parents=True, exist_ok=True)
    
    import shutil
    shutil.copy(local_temp, volume_path)
    print(f"Copied to volume path: {volume_path}")
    
    # Clean up temp file
    local_temp.unlink()
    
    # Commit volume changes to persist
    models_volume.commit()
    print("Volume committed successfully")
    
    return str(volume_path)


@app.function(
    image=image,
    volumes={"/models": models_volume},
    timeout=60,
)
def delete_model_from_volume(model_id: str) -> bool:
    """
    Delete a model from the volume when training run is deleted.
    
    Args:
        model_id: UUID of the model
        
    Returns:
        True if deleted, False if not found
    """
    volume_path = Path(f"/models/{model_id}.pt")
    
    if volume_path.exists():
        volume_path.unlink()
        models_volume.commit()
        print(f"Deleted model from volume: {volume_path}")
        return True
    else:
        print(f"Model not found in volume: {volume_path}")
        return False


@app.function(
    image=image,
    volumes={"/models": models_volume},
    timeout=60,
)
def list_volume_models() -> list[str]:
    """
    List all models in the volume (for debugging).
    
    Returns:
        List of model file paths
    """
    models_dir = Path("/models")
    if not models_dir.exists():
        return []
    
    models = [str(p) for p in models_dir.glob("*.pt")]
    print(f"Found {len(models)} models in volume")
    return models


@app.function(
    image=image,
    volumes={"/models": models_volume},
    timeout=60,
)
def model_exists_in_volume(model_id: str) -> bool:
    """
    Check if a model exists in the volume.
    
    Args:
        model_id: UUID of the model
        
    Returns:
        True if exists
    """
    volume_path = Path(f"/models/{model_id}.pt")
    return volume_path.exists()


# For local testing / CLI
if __name__ == "__main__":
    print("Deploy this module with: modal deploy backend/modal_jobs/model_volume.py")
    print("Then use the functions remotely from your Reflex app.")
