#!/usr/bin/env python3
"""
SAFARI Remote Worker Utilities.

Shared utilities for all remote worker scripts, including:
- LogCapture: Stream logs to Supabase
- R2 helpers: Download/upload files
- Environment loading

Usage:
    from remote_utils import LogCapture, get_supabase, get_r2_client, download_file

Environment:
    Loads credentials from ~/.tyto/.env
"""

import io
import os
import sys
import threading
import time
from pathlib import Path

from dotenv import load_dotenv

# Load environment from ~/.tyto/.env
TYTO_HOME = Path.home() / ".tyto"
ENV_FILE = TYTO_HOME / ".env"

if ENV_FILE.exists():
    load_dotenv(ENV_FILE)
else:
    print(f"Warning: Environment file not found at {ENV_FILE}")
    print("Please run remote_setup.sh first or create the .env file manually.")


def get_supabase():
    """Get a configured Supabase client."""
    from supabase import create_client
    
    url = os.environ["SUPABASE_URL"]
    key = os.environ["SUPABASE_KEY"]
    return create_client(url, key)


def get_r2_client():
    """Get a configured R2 (S3-compatible) client."""
    import boto3
    from botocore.config import Config
    
    return boto3.client(
        's3',
        endpoint_url=os.environ['R2_ENDPOINT_URL'],
        aws_access_key_id=os.environ['R2_ACCESS_KEY_ID'],
        aws_secret_access_key=os.environ['R2_SECRET_ACCESS_KEY'],
        config=Config(signature_version='s3v4'),
        region_name='auto',
    )


def get_r2_bucket():
    """Get the R2 bucket name from environment."""
    return os.environ['R2_BUCKET_NAME']


def download_file(url: str, dest_path: Path) -> bool:
    """Download a file from a presigned URL."""
    import requests
    
    try:
        response = requests.get(url, timeout=60)
        response.raise_for_status()
        dest_path.parent.mkdir(parents=True, exist_ok=True)
        dest_path.write_bytes(response.content)
        return True
    except Exception as e:
        print(f"Failed to download {url}: {e}")
        return False


def upload_to_r2(local_path: Path, r2_key: str) -> bool:
    """Upload a file to R2 storage."""
    try:
        s3 = get_r2_client()
        bucket = get_r2_bucket()
        s3.put_object(
            Bucket=bucket,
            Key=r2_key,
            Body=local_path.read_bytes(),
        )
        print(f"  Uploaded: {r2_key}")
        return True
    except Exception as e:
        print(f"Failed to upload {local_path} to {r2_key}: {e}")
        return False


def download_from_r2(r2_key: str, local_path: Path) -> bool:
    """Download a file from R2 storage."""
    try:
        s3 = get_r2_client()
        bucket = get_r2_bucket()
        response = s3.get_object(Bucket=bucket, Key=r2_key)
        local_path.parent.mkdir(parents=True, exist_ok=True)
        local_path.write_bytes(response['Body'].read())
        print(f"  Downloaded: {r2_key}")
        return True
    except Exception as e:
        print(f"Failed to download {r2_key}: {e}")
        return False


def download_from_r2_cached(r2_key: str, local_path: Path) -> bool:
    """Download a file from R2 storage, using local cache if available.
    
    Useful for models that don't change — avoids re-downloading on every run.
    """
    if local_path.exists():
        print(f"  Using cached: {local_path.name}")
        return True
    return download_from_r2(r2_key, local_path)


class LogCapture:
    """
    Capture stdout and stderr and stream to Supabase.
    
    Usage:
        with LogCapture(run_id, table="training_runs"):
            print("This goes to Supabase")
    """

    def __init__(
        self,
        record_id: str,
        table: str = "training_runs",
        log_column: str = "logs",
        flush_interval: int = 2,
    ):
        self.record_id = record_id
        self.table = table
        self.log_column = log_column
        self.flush_interval = flush_interval
        self.log_buffer = io.StringIO()
        self.lock = threading.Lock()
        self.stop_event = threading.Event()
        self.thread = None
        self.original_stdout = sys.stdout
        self.original_stderr = sys.stderr

    def __enter__(self):
        sys.stdout = self
        sys.stderr = self
        self.thread = threading.Thread(target=self._flush_loop, daemon=True)
        self.thread.start()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.stop_event.set()
        if self.thread:
            self.thread.join(timeout=5)
        sys.stdout = self.original_stdout
        sys.stderr = self.original_stderr
        self._flush_buffer()  # Final flush

    def write(self, message):
        self.original_stdout.write(message)  # Keep local logging
        with self.lock:
            self.log_buffer.write(message)

    def flush(self):
        self.original_stdout.flush()

    def _flush_loop(self):
        while not self.stop_event.is_set():
            time.sleep(self.flush_interval)
            self._flush_buffer()

    def _flush_buffer(self):
        import traceback
        
        try:
            with self.lock:
                content = self.log_buffer.getvalue()
                if not content:
                    return
                # Clear buffer
                self.log_buffer.seek(0)
                self.log_buffer.truncate(0)

            # Send to Supabase
            supabase = get_supabase()
            
            # Fetch current logs
            res = supabase.table(self.table).select(self.log_column).eq("id", self.record_id).single().execute()
            current = res.data.get(self.log_column, "") or ""
            
            # Append and update
            new_logs = current + content
            supabase.table(self.table).update({self.log_column: new_logs}).eq("id", self.record_id).execute()

        except Exception as e:
            self.original_stderr.write(f"\n[LogCapture Error] {e}\n")
            traceback.print_exc(file=self.original_stderr)





def get_models_dir() -> Path:
    """Get the models directory in the SAFARI home directory."""
    return TYTO_HOME / "models"


def get_data_dir() -> Path:
    """Get the data directory for temporary processing files."""
    return TYTO_HOME / "data"


def get_logs_dir() -> Path:
    """Get the logs directory."""
    return TYTO_HOME / "logs"
