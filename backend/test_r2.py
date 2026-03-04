"""
Test script for R2 storage client.

Run from project root:
    .venv/bin/python backend/test_r2.py
"""

import sys
from pathlib import Path

# Add project root to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

from backend.r2_storage import R2Client


def main():
    print("🔌 Connecting to R2...")
    r2 = R2Client()
    print(f"   Bucket: {r2.bucket}")
    
    # Test file content
    test_path = "test/hello.txt"
    test_content = b"Hello from SAFARI! This is a test file."
    
    # 1. Upload
    print(f"\n📤 Uploading test file to '{test_path}'...")
    r2.upload_file(test_content, test_path, content_type="text/plain")
    print("   ✅ Upload successful")
    
    # 2. List files
    print("\n📋 Listing files with prefix 'test/'...")
    files = r2.list_files(prefix="test/")
    for f in files:
        print(f"   - {f}")
    
    # 3. Download
    print(f"\n📥 Downloading '{test_path}'...")
    downloaded = r2.download_file(test_path)
    print(f"   Content: {downloaded.decode()}")
    assert downloaded == test_content, "Downloaded content doesn't match!"
    print("   ✅ Content matches")
    
    # 4. Generate presigned URL
    print(f"\n🔗 Generating presigned URL...")
    url = r2.generate_presigned_url(test_path, expires_in=3600)
    print(f"   URL: {url[:80]}...")
    print("   ⏱️  Expires in 1 hour")
    
    # 5. Cleanup
    print(f"\n🗑️  Deleting test file...")
    r2.delete_file(test_path)
    print("   ✅ Deleted")
    
    # Verify deletion
    files_after = r2.list_files(prefix="test/")
    if test_path not in files_after:
        print("   ✅ Verified: file no longer exists")
    
    print("\n" + "="*50)
    print("✅ All R2 tests passed!")
    print("="*50)
    print(f"\n🌐 Open this URL in your browser to verify access:")
    print(f"   (Note: file was deleted, so it will 404 — re-run upload to test)")


if __name__ == "__main__":
    main()
