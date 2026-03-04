"""
R2 Storage Client — Cloudflare R2 wrapper using boto3 S3-compatible API.

Usage:
    from backend.r2_storage import R2Client
    
    r2 = R2Client()
    r2.upload_file(image_bytes, "projects/abc/images/001.jpg")
    url = r2.generate_presigned_url("projects/abc/images/001.jpg")
"""

import os
from typing import Optional

import boto3
from botocore.config import Config
from dotenv import load_dotenv

# Load environment variables from .env
load_dotenv()


class R2Client:
    """S3-compatible client for Cloudflare R2 storage."""
    
    def __init__(self):
        self.s3 = boto3.client(
            's3',
            endpoint_url=os.getenv('R2_ENDPOINT_URL'),
            aws_access_key_id=os.getenv('R2_ACCESS_KEY_ID'),
            aws_secret_access_key=os.getenv('R2_SECRET_ACCESS_KEY'),
            config=Config(signature_version='s3v4'),
            region_name='auto',  # R2 uses 'auto' region
        )
        self.bucket = os.getenv('R2_BUCKET_NAME')
    
    def upload_file(self, file_bytes: bytes, path: str, content_type: Optional[str] = None) -> str:
        """
        Upload a file to R2.
        
        Args:
            file_bytes: The file content as bytes
            path: The destination path in the bucket (e.g., "projects/abc/images/001.jpg")
            content_type: Optional MIME type (e.g., "image/jpeg")
        
        Returns:
            The path where the file was stored
        """
        extra_args = {}
        if content_type:
            extra_args['ContentType'] = content_type
        
        self.s3.put_object(
            Bucket=self.bucket,
            Key=path,
            Body=file_bytes,
            **extra_args
        )
        return path
    
    def download_file(self, path: str) -> bytes:
        """
        Download a file from R2.
        
        Args:
            path: The file path in the bucket
        
        Returns:
            The file content as bytes
        """
        response = self.s3.get_object(Bucket=self.bucket, Key=path)
        return response['Body'].read()
    
    def list_files(self, prefix: str = "") -> list[str]:
        """
        List files in R2 with an optional prefix filter.
        
        Args:
            prefix: Filter results to paths starting with this prefix
                    (e.g., "projects/abc/images/")
        
        Returns:
            List of file paths matching the prefix
        """
        response = self.s3.list_objects_v2(Bucket=self.bucket, Prefix=prefix)
        
        if 'Contents' not in response:
            return []
        
        return [obj['Key'] for obj in response['Contents']]
    
    def generate_presigned_url(self, path: str, expires_in: int = 3600) -> str:
        """
        Generate a presigned URL for temporary access to a file.
        
        Args:
            path: The file path in the bucket
            expires_in: URL expiration time in seconds (default: 1 hour)
        
        Returns:
            A presigned URL that grants temporary access to the file
        """
        return self.s3.generate_presigned_url(
            'get_object',
            Params={'Bucket': self.bucket, 'Key': path},
            ExpiresIn=expires_in
        )
    
    def delete_file(self, path: str) -> None:
        """
        Delete a file from R2.
        
        Args:
            path: The file path to delete
        """
        self.s3.delete_object(Bucket=self.bucket, Key=path)
    
    def file_exists(self, path: str) -> bool:
        """
        Check if a file exists in R2.
        
        Args:
            path: The file path to check
        
        Returns:
            True if the file exists, False otherwise
        """
        try:
            self.s3.head_object(Bucket=self.bucket, Key=path)
            return True
        except self.s3.exceptions.ClientError:
            return False

    def delete_files_with_prefix(self, prefix: str) -> int:
        """
        Delete all files starting with a prefix.
        
        Args:
            prefix: The prefix to search for (e.g., "datasets/123/")
        
        Returns:
            Number of files deleted
        """
        # List all objects with the prefix
        paginator = self.s3.get_paginator('list_objects_v2')
        pages = paginator.paginate(Bucket=self.bucket, Prefix=prefix)
        
        deleted_count = 0
        
        for page in pages:
            if 'Contents' in page:
                objects_to_delete = [{'Key': obj['Key']} for obj in page['Contents']]
                
                # Delete in batches (max 1000 per request)
                for i in range(0, len(objects_to_delete), 1000):
                    batch = objects_to_delete[i:i+1000]
                    self.s3.delete_objects(
                        Bucket=self.bucket,
                        Delete={'Objects': batch}
                    )
                    deleted_count += len(batch)
                    
        return deleted_count

    def copy_files_with_prefix(self, source_prefix: str, dest_prefix: str, progress_callback=None) -> dict:
        """
        Copy all files from one prefix to another within the same bucket.
        Uses S3 copy_object API for server-side copying (no download/upload).
        
        Args:
            source_prefix: Source prefix (e.g., "datasets/123/")
            dest_prefix: Destination prefix (e.g., "datasets/456/")
            progress_callback: Optional callback(copied_count, total_count) for progress
        
        Returns:
            Dict with 'copied_count' and 'path_mapping' (old_path -> new_path)
        """
        # List all objects with the source prefix
        paginator = self.s3.get_paginator('list_objects_v2')
        pages = paginator.paginate(Bucket=self.bucket, Prefix=source_prefix)
        
        # Collect all source keys first
        source_keys = []
        for page in pages:
            if 'Contents' in page:
                source_keys.extend([obj['Key'] for obj in page['Contents']])
        
        total_count = len(source_keys)
        copied_count = 0
        path_mapping = {}  # old_path -> new_path
        
        # Copy each file (S3 copy_object is server-side, no data transfer)
        for source_key in source_keys:
            # Replace source prefix with dest prefix
            relative_path = source_key[len(source_prefix):]
            dest_key = dest_prefix + relative_path
            
            try:
                self.s3.copy_object(
                    Bucket=self.bucket,
                    CopySource={'Bucket': self.bucket, 'Key': source_key},
                    Key=dest_key
                )
                path_mapping[source_key] = dest_key
                copied_count += 1
                
                if progress_callback and copied_count % 10 == 0:
                    progress_callback(copied_count, total_count)
                    
            except Exception as e:
                print(f"[R2] Error copying {source_key} to {dest_key}: {e}")
                continue
        
        return {'copied_count': copied_count, 'path_mapping': path_mapping}

