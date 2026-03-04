"""
Frame Extractor — Extract full-resolution frames from videos in R2.

Usage:
    from backend.frame_extractor import extract_and_store_full_frame
    
    full_path = extract_and_store_full_frame(
        video_r2_path="datasets/{id}/videos/{uuid}.mp4",
        frame_number=150,
        fps=30.0,
        dataset_id="...",
        video_id="..."
    )
"""

import os
import subprocess
import tempfile
from pathlib import Path

from backend.r2_storage import R2Client


def extract_and_store_full_frame(
    video_r2_path: str,
    frame_number: int,
    fps: float,
    dataset_id: str,
    video_id: str,
) -> str | None:
    """
    Extract a single full-resolution frame from a video in R2.
    
    Downloads video, extracts frame with ffmpeg at source resolution,
    uploads result to R2.
    
    Args:
        video_r2_path: R2 path to the video file
        frame_number: Frame number to extract
        fps: Video FPS for timestamp calculation
        dataset_id: Dataset UUID for output path
        video_id: Video UUID for output filename
        
    Returns:
        R2 path to the extracted frame, or None on failure
    """
    r2 = R2Client()
    output_r2_path = f"datasets/{dataset_id}/keyframe_images/{video_id}_f{frame_number}.jpg"
    
    try:
        # 1. Download video to temp file
        print(f"[FrameExtractor] Downloading video {video_r2_path}...")
        video_bytes = r2.download_file(video_r2_path)
        if not video_bytes:
            print(f"[FrameExtractor] Failed to download video")
            return None
        
        # 2. Save to temp file
        with tempfile.NamedTemporaryFile(suffix=".mp4", delete=False) as tmp_video:
            tmp_video.write(video_bytes)
            tmp_video_path = tmp_video.name
        
        # 3. Calculate timestamp
        timestamp = frame_number / fps if fps > 0 else 0
        
        # 4. Extract frame with ffmpeg at full resolution
        with tempfile.NamedTemporaryFile(suffix=".jpg", delete=False) as tmp_frame:
            tmp_frame_path = tmp_frame.name
        
        ffmpeg_cmd = [
            "ffmpeg", "-y",
            "-ss", str(timestamp),
            "-i", tmp_video_path,
            "-vframes", "1",
            "-q:v", "2",  # High quality JPEG
            tmp_frame_path
        ]
        
        print(f"[FrameExtractor] Extracting frame {frame_number} at t={timestamp:.3f}s...")
        result = subprocess.run(ffmpeg_cmd, capture_output=True, timeout=60)
        
        if result.returncode != 0:
            print(f"[FrameExtractor] ffmpeg failed: {result.stderr.decode()}")
            return None
        
        # 5. Upload frame to R2
        if os.path.exists(tmp_frame_path):
            with open(tmp_frame_path, "rb") as f:
                frame_bytes = f.read()
            
            print(f"[FrameExtractor] Uploading {len(frame_bytes)} bytes to {output_r2_path}")
            r2.upload_file(frame_bytes, output_r2_path, content_type="image/jpeg")
            
            # Cleanup
            os.unlink(tmp_frame_path)
            os.unlink(tmp_video_path)
            
            print(f"[FrameExtractor] Successfully extracted frame to {output_r2_path}")
            return output_r2_path
        
        return None
        
    except subprocess.TimeoutExpired:
        print(f"[FrameExtractor] ffmpeg timeout extracting frame {frame_number}")
        return None
    except Exception as e:
        print(f"[FrameExtractor] Error extracting frame: {e}")
        import traceback
        traceback.print_exc()
        return None
    finally:
        # Cleanup temp files in case of error
        for path in [tmp_video_path, tmp_frame_path]:
            try:
                if 'path' in dir() and os.path.exists(path):
                    os.unlink(path)
            except:
                pass
