"""
Core Video Hybrid Inference Logic — SAM3 Video Detection + Classifier Species Identification.

This module contains the shared video pipeline logic used by both Modal jobs and remote workers.
Environment-specific concerns (model paths, download functions) are passed as parameters.

The key optimization is the "Classify Once" pattern: each unique tracked object is classified
only on first detection, and the species label is propagated to all subsequent frames.

Functions:
    download_video: Download video and extract metadata
    run_sam3_video_detection: Run SAM3 with temporal tracking
    classify_unique_tracks: Classify each unique tracked object once
    propagate_labels_and_format: Propagate labels to all frames, format output
    run_hybrid_video_inference: Orchestrator function
"""

import base64
import os
import tempfile
from pathlib import Path
from typing import Callable, Optional

import cv2
import numpy as np

from backend.core.image_utils import crop_from_box
from backend.core.classifier_utils import load_classifier, classify_with_convnext


def download_video(video_url: str, work_dir: Path) -> tuple[Path, dict]:
    """
    Download video from URL and extract metadata.
    
    Args:
        video_url: Presigned URL to video file
        work_dir: Working directory for temporary files
    
    Returns:
        Tuple of (video_path, metadata_dict) where metadata contains:
            fps, total_frames, frame_width, frame_height, duration
    """
    import requests
    
    print("[1/5] Downloading video...")
    response = requests.get(video_url, timeout=120)
    response.raise_for_status()
    
    video_path = work_dir / "video.mp4"
    video_path.write_bytes(response.content)
    
    # Extract metadata
    cap = cv2.VideoCapture(str(video_path))
    fps = cap.get(cv2.CAP_PROP_FPS)
    total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
    frame_width = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
    frame_height = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
    duration = total_frames / fps if fps > 0 else 0
    cap.release()
    
    print(f"  Video: {total_frames} frames, {fps:.2f} FPS, {duration:.2f}s duration")
    print(f"  Resolution: {frame_width}x{frame_height}")
    
    return video_path, {
        "fps": fps,
        "total_frames": total_frames,
        "frame_width": frame_width,
        "frame_height": frame_height,
        "duration": duration,
    }


def run_sam3_video_detection(
    video_path: Path,
    sam3_prompts: list[str],
    confidence_threshold: float,
    start_frame: int,
    end_frame: int,
    sam3_model_path: Optional[str] = None,
    progress_callback: Optional[Callable] = None,
    imgsz: int = 640,
    frame_width: int = 0,
    frame_height: int = 0,
    bbox_padding: float = 0.03,
) -> tuple[list[dict], dict]:
    """
    Run SAM3 video detection with temporal tracking.
    
    Args:
        video_path: Path to video file
        sam3_prompts: Text prompts for SAM3 (e.g., ["mammal", "bird"])
        confidence_threshold: SAM3 detection confidence
        start_frame: First frame to process
        end_frame: Last frame to process (exclusive)
        sam3_model_path: Path to SAM3 model (None for auto-download)
    
    Returns:
        Tuple of (frame_detections, unique_tracks) where:
            frame_detections: List of {frame_number, timestamp, detections}
            unique_tracks: Dict of {track_id: {first_frame, box}}
    """
    from ultralytics.models.sam import SAM3VideoSemanticPredictor
    
    print("\n[3/5] Running SAM3 video detection (full video, all prompts)...")
    
    overrides = dict(
        conf=confidence_threshold,
        task="segment",
        mode="predict",
        imgsz=imgsz,
        half=True,
        save=False,
    )
    
    if sam3_model_path:
        overrides["model"] = sam3_model_path
    
    # Get FPS and total frames for timestamp calculation and progress
    cap = cv2.VideoCapture(str(video_path))
    fps = cap.get(cv2.CAP_PROP_FPS)
    total_video_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
    cap.release()
    
    # Emit initial SAM3 progress so UI transitions from "loading classifier"
    if progress_callback:
        if start_frame > 0:
            progress_callback("sam3", 0, end_frame - start_frame, f"SAM3 warming up (seeking to frame {start_frame})")
        else:
            progress_callback("sam3", 0, end_frame - start_frame, "SAM3 starting detection")
    
    video_predictor = SAM3VideoSemanticPredictor(overrides=overrides)
    
    sam3_results_iter = video_predictor(
        source=str(video_path),
        text=sam3_prompts,
        stream=True,
    )
    
    all_frame_detections = []
    unique_tracks = {}
    
    for frame_idx, result in enumerate(sam3_results_iter):
        if frame_idx < start_frame:
            # Report progress during warmup phase so UI doesn't freeze
            if progress_callback and frame_idx % 30 == 0:
                progress_callback("sam3", 0, end_frame - start_frame, f"SAM3 warming up (frame {frame_idx}/{start_frame})")
            continue
        if frame_idx >= end_frame:
            break
        
        frame_detections = []
        
        if hasattr(result, 'boxes') and result.boxes is not None:
            boxes = result.boxes.xyxy.cpu().numpy()
            
            # Expand SAM3 boxes to compensate for conservative predictions
            if bbox_padding > 0 and len(boxes) > 0 and frame_width > 0 and frame_height > 0:
                from backend.core.autolabel_core import expand_boxes
                expand_boxes(boxes, frame_width, frame_height, bbox_padding)
            
            # Get track IDs if available
            track_ids = None
            if hasattr(result.boxes, 'id') and result.boxes.id is not None:
                track_ids = result.boxes.id.cpu().numpy().astype(int)
            
            # Get masks if available
            masks_data = None
            if hasattr(result, 'masks') and result.masks is not None:
                try:
                    if hasattr(result.masks, 'data'):
                        masks_data = result.masks.data.cpu().numpy()
                except Exception:
                    pass
            
            for idx, box in enumerate(boxes):
                track_id = int(track_ids[idx]) if track_ids is not None else idx + frame_idx * 1000
                
                # Inline mask-to-polygon (avoids storing raw tensors in RAM)
                mask_polygon = None
                if masks_data is not None and idx < len(masks_data):
                    mask_polygon = mask_to_polygon(masks_data[idx], frame_width, frame_height)
                
                frame_detections.append({
                    "box": box[:4],
                    "mask_polygon": mask_polygon,
                    "track_id": track_id,
                })
                
                # Track unique objects - accumulate all candidate frames
                if track_id not in unique_tracks:
                    unique_tracks[track_id] = {"candidate_frames": []}
                unique_tracks[track_id]["candidate_frames"].append({
                    "frame": frame_idx,
                    "box": box[:4].tolist(),
                })
        
        all_frame_detections.append({
            "frame_number": frame_idx,
            "timestamp": frame_idx / fps,
            "detections": frame_detections,
        })
        
        if (frame_idx - start_frame) % 30 == 0:
            print(f"  SAM3 processed frame {frame_idx}/{end_frame}, {len(frame_detections)} detections")
            if progress_callback:
                progress_callback("sam3", frame_idx - start_frame, end_frame - start_frame, f"SAM3 frame {frame_idx - start_frame}/{end_frame - start_frame}")
    
    print(f"  Total frames processed by SAM3: {len(all_frame_detections)}")
    print(f"  Unique tracked objects: {len(unique_tracks)}")
    
    return all_frame_detections, unique_tracks


def crop_quality_score(box: list, frame_width: int, frame_height: int) -> float:
    """
    GPU-free heuristic to score a detection crop's quality.
    
    Combines:
    - Area ratio (larger crops → better detail)
    - Edge proximity penalty (near frame borders → likely clipped)
    - Aspect ratio balance (extreme ratios → partial animal)
    
    Returns score in [0, 1] range.
    """
    x1, y1, x2, y2 = box
    w = x2 - x1
    h = y2 - y1
    
    if w <= 0 or h <= 0:
        return 0.0
    
    # Area: fraction of frame covered by this crop (larger = better)
    area_ratio = (w * h) / (frame_width * frame_height)
    area_score = min(area_ratio * 10, 1.0)  # Saturate at 10% of frame
    
    # Edge proximity: penalise boxes touching frame edges
    margin_x = min(x1, frame_width - x2) / frame_width
    margin_y = min(y1, frame_height - y2) / frame_height
    edge_score = min(margin_x * 10, 1.0) * min(margin_y * 10, 1.0)
    
    # Aspect ratio: penalise very elongated boxes
    aspect = w / h if h > 0 else 1.0
    aspect_score = 1.0 - abs(aspect - 1.0) / max(aspect, 1.0)
    
    return 0.5 * area_score + 0.3 * edge_score + 0.2 * aspect_score


def select_diverse_frames(
    candidates: list[dict],
    K: int,
    frame_width: int,
    frame_height: int,
) -> list[dict]:
    """
    Select K high-quality, temporally diverse frames from candidates.
    
    Algorithm:
    1. Score all candidates by crop quality
    2. Pick highest-quality frame as seed
    3. Greedily add frames respecting min_gap = span/(K+1)
    4. If fewer than K selected, relax gap and fill by quality
    
    Args:
        candidates: List of {"frame": int, "box": [x1,y1,x2,y2]}
        K: Number of frames to select
        frame_width: Video frame width
        frame_height: Video frame height
    
    Returns:
        Selected subset of candidates (up to K)
    """
    if len(candidates) <= K:
        return candidates
    
    # Score all candidates
    scored = []
    for c in candidates:
        score = crop_quality_score(c["box"], frame_width, frame_height)
        scored.append((score, c))
    scored.sort(key=lambda x: x[0], reverse=True)
    
    # Compute dynamic min_gap
    frames = [c["frame"] for c in candidates]
    span = max(frames) - min(frames)
    min_gap = span / (K + 1) if span > 0 else 0
    
    # Greedy selection: seed with best quality
    selected = [scored[0][1]]
    selected_frames = {scored[0][1]["frame"]}
    
    # Add frames respecting min_gap, by descending quality
    for _, candidate in scored[1:]:
        if len(selected) >= K:
            break
        if all(abs(candidate["frame"] - sf) >= min_gap for sf in selected_frames):
            selected.append(candidate)
            selected_frames.add(candidate["frame"])
    
    # If still fewer than K, relax gap and fill by quality
    if len(selected) < K:
        for _, candidate in scored:
            if len(selected) >= K:
                break
            if candidate["frame"] not in selected_frames:
                selected.append(candidate)
                selected_frames.add(candidate["frame"])
    
    return selected


def vote_classifications(
    results: list[tuple[str | None, float]],
    classifier_confidence: float,
) -> tuple[str, int, float, float]:
    """
    Majority vote over K classification results.
    
    Args:
        results: List of (class_name, confidence) from each frame.
                 class_name is None if classification failed.
        classifier_confidence: Minimum confidence to accept a vote.
    
    Returns:
        (winning_class, class_id_placeholder, avg_confidence, agreement_ratio)
        class_id is set to -1 here; caller maps it via class_to_id.
    """
    from collections import Counter
    
    # Filter valid votes above confidence threshold
    valid_votes = [
        (cls, conf) for cls, conf in results
        if cls is not None and conf >= classifier_confidence
    ]
    
    if not valid_votes:
        return ("Unknown", -1, 0.0, 0.0)
    
    # Count votes per class
    class_counts = Counter(cls for cls, _ in valid_votes)
    winner, win_count = class_counts.most_common(1)[0]
    
    # Average confidence of winning class
    winner_confs = [conf for cls, conf in valid_votes if cls == winner]
    avg_conf = sum(winner_confs) / len(winner_confs)
    
    # Agreement: fraction of total votes (not just valid) for winner
    agreement = win_count / len(results) if results else 0.0
    
    return (winner, -1, avg_conf, agreement)


def classify_unique_tracks(
    video_path: Path,
    unique_tracks: dict,
    classifier_data: dict,
    classifier_classes: list[str],
    classifier_confidence: float,
    work_dir: Path,
    classify_top_k: int = 3,
    frame_width: int = 0,
    frame_height: int = 0,
) -> tuple[dict, list[dict]]:
    """
    Classify each unique tracked object using Quality-Diverse Top-K selection.
    
    For each track, selects K high-quality, temporally diverse frames,
    classifies each independently, and uses majority voting.
    
    Args:
        video_path: Path to video file
        unique_tracks: Dict of {track_id: {candidate_frames: [{frame, box}, ...]}}
        classifier_data: Loaded classifier from load_classifier()
        classifier_classes: Class names for ID mapping
        classifier_confidence: Minimum confidence to accept
        work_dir: Working directory for temp crops
        classify_top_k: Number of frames to classify per track
        frame_width: Video frame width (for quality scoring)
        frame_height: Video frame height (for quality scoring)
    
    Returns:
        Tuple of (classifications, crop_records):
        - classifications: {track_id: (class_name, class_id, confidence)}
        - crop_records: [{"track_id", "crop_bytes", "class_name", "confidence", "frame_num"}, ...]
    """
    print(f"\n[4/5] Classifying unique tracked objects (top-K={classify_top_k})...")
    
    is_convnext = classifier_data["type"] == "convnext"
    class_to_id = {name: idx for idx, name in enumerate(classifier_classes)}
    
    cap = cv2.VideoCapture(str(video_path))
    classifications = {}
    crop_records = []  # All K crops with metadata for UI display
    
    for track_id, track_info in unique_tracks.items():
        candidates = track_info.get("candidate_frames", [])
        if not candidates:
            continue
        
        # Select K diverse, high-quality frames
        selected = select_diverse_frames(
            candidates, classify_top_k, frame_width, frame_height,
        )
        
        # Classify each selected frame
        frame_results = []  # (class_name, confidence)
        track_crops = []    # (crop_bytes, class_name, confidence, frame_num)
        
        for sel in selected:
            frame_num = sel["frame"]
            box = sel["box"]
            
            cap.set(cv2.CAP_PROP_POS_FRAMES, frame_num)
            ret, frame = cap.read()
            if not ret:
                frame_results.append((None, 0.0))
                continue
            
            try:
                _, frame_encoded = cv2.imencode('.jpg', frame)
                frame_bytes = frame_encoded.tobytes()
                x1, y1, x2, y2 = box
                crop_bytes = crop_from_box(frame_bytes, (x1, y1, x2, y2), padding=0.05)
                
                # Classify
                if is_convnext:
                    top1_class, top1_conf = classify_with_convnext(
                        classifier_data["model"],
                        classifier_data["transform"],
                        crop_bytes,
                        classifier_data["idx_to_class"],
                        classifier_data["device"],
                    )
                else:
                    classifier = classifier_data["model"]
                    crop_path = work_dir / f"crop_t{track_id}_f{frame_num}.jpg"
                    crop_path.write_bytes(crop_bytes)
                    results = classifier.predict(str(crop_path), verbose=False)
                    
                    if results and len(results) > 0:
                        probs = results[0].probs
                        if probs is not None:
                            top1_idx = probs.top1
                            top1_conf = probs.top1conf.item()
                            top1_class = classifier.names[top1_idx]
                        else:
                            top1_class, top1_conf = None, 0.0
                    else:
                        top1_class, top1_conf = None, 0.0
                
                frame_results.append((top1_class, top1_conf))
                
                # Determine label for this crop
                crop_label = top1_class if (top1_class and top1_conf >= classifier_confidence) else "Unknown"
                crop_conf = top1_conf if top1_class else 0.0
                track_crops.append((crop_bytes, crop_label, crop_conf, frame_num))
                
            except Exception as e:
                print(f"  Track {track_id} frame {frame_num}: classification failed - {e}")
                frame_results.append((None, 0.0))
        
        # Majority vote
        winner, _, avg_conf, agreement = vote_classifications(
            frame_results, classifier_confidence,
        )
        
        class_id = class_to_id.get(winner, -1)
        classifications[track_id] = (winner, class_id, avg_conf)
        
        # Store crop records for UI
        for crop_bytes, crop_label, crop_conf, frame_num in track_crops:
            crop_records.append({
                "track_id": track_id,
                "crop_bytes": crop_bytes,
                "class_name": crop_label,
                "confidence": crop_conf,
                "frame_num": frame_num,
            })
        
        vote_str = ", ".join(
            f"{cls}({conf:.2f})" if cls else "fail"
            for cls, conf in frame_results
        )
        print(f"  Track {track_id}: {winner} (avg={avg_conf:.2f}, agree={agreement:.0%}) ← [{vote_str}]")
    
    cap.release()
    print(f"  Classified {len(classifications)} tracks, {len(crop_records)} crops saved")
    
    return classifications, crop_records


def mask_to_polygon(mask: np.ndarray, frame_width: int, frame_height: int) -> list[list[float]] | None:
    """
    Convert binary mask to normalized polygon coordinates.
    
    Args:
        mask: Binary mask array
        frame_width: Video frame width
        frame_height: Video frame height
    
    Returns:
        List of [x, y] normalized coordinates, or None if conversion fails
    """
    try:
        if mask.max() <= 1.0:
            mask_uint8 = ((mask > 0.5) * 255).astype(np.uint8)
        else:
            mask_uint8 = (mask > 127).astype(np.uint8) * 255
        
        contours, _ = cv2.findContours(mask_uint8, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
        
        if contours:
            largest = max(contours, key=cv2.contourArea)
            epsilon = 0.001 * cv2.arcLength(largest, True)
            approx = cv2.approxPolyDP(largest, epsilon, True)
            
            return [
                [float(p[0][0]) / frame_width, float(p[0][1]) / frame_height]
                for p in approx
            ]
    except Exception:
        pass
    
    return None


def propagate_labels_and_format(
    frame_detections: list[dict],
    classifications: dict,
    frame_width: int,
    frame_height: int,
    start_frame: int,
    frame_skip: int,
) -> list[dict]:
    """
    Propagate classification labels to all frames and format output.
    
    Args:
        frame_detections: List of {frame_number, timestamp, detections}
        classifications: Dict of {track_id: (class_name, class_id, confidence)}
        frame_width: Video frame width
        frame_height: Video frame height
        start_frame: First frame number
        frame_skip: Return every Nth frame
    
    Returns:
        List of {frame_number, timestamp, predictions, masks}
    """
    print("\n[5/5] Propagating labels to all frames...")
    
    frame_results = []
    
    for frame_data in frame_detections:
        frame_number = frame_data["frame_number"]
        
        # Apply frame_skip filter for output
        if (frame_number - start_frame) % frame_skip != 0:
            continue
        
        frame_predictions = []
        frame_masks = []
        
        for detection in frame_data["detections"]:
            track_id = detection["track_id"]
            box = detection["box"]
            mask_polygon = detection.get("mask_polygon")
            
            # Look up classification for this track
            if track_id in classifications:
                class_name, class_id, confidence = classifications[track_id]
            else:
                # SAM3 detected but no classification attempt was made
                class_name = "Unknown"
                class_id = -1
                confidence = 0.0
            
            # Normalize box to 0-1 range
            x1, y1, x2, y2 = box
            normalized_box = [
                float(x1) / frame_width,
                float(y1) / frame_height,
                float(x2) / frame_width,
                float(y2) / frame_height,
            ]
            
            prediction = {
                "class_name": class_name,
                "class_id": class_id,
                "confidence": confidence,
                "box": normalized_box,
                "track_id": track_id,
            }
            frame_predictions.append(prediction)
            
            # Use pre-computed polygon from inline conversion
            if mask_polygon is not None:
                frame_masks.append({
                    "class_name": class_name,
                    "class_id": class_id,
                    "polygon": mask_polygon,
                    "track_id": track_id,
                })
        
        frame_results.append({
            "frame_number": frame_number,
            "timestamp": frame_data["timestamp"],
            "predictions": frame_predictions,
            "masks": frame_masks,
        })
    
    return frame_results


def run_hybrid_video_inference(
    video_url: str,
    sam3_prompts: list[str],
    classifier_r2_path: str,
    classifier_classes: list[str],
    confidence_threshold: float = 0.25,
    classifier_confidence: float = 0.5,
    start_time: float = 0.0,
    end_time: float | None = None,
    frame_skip: int = 1,
    classify_top_k: int = 3,
    # Environment-specific parameters:
    sam3_model_path: Optional[str] = None,
    download_classifier_fn: Callable[[str, Path], bool] = None,
    upload_crop_fn: Optional[Callable[[bytes, str], str]] = None,
    progress_callback: Optional[Callable] = None,
    imgsz: int = 640,
) -> dict:
    """
    Run hybrid SAM3 + Classifier inference on video.
    
    Uses a two-phase pipeline:
    1. SAM3VideoSemanticPredictor processes the full video with temporal tracking
    2. Unique tracked objects are classified once (not per-frame)
    3. Classifications are propagated to all frames via track IDs
    
    Args:
        video_url: Presigned URL to video
        sam3_prompts: Generic prompts for SAM3 (e.g., ["mammal", "bird"])
        classifier_r2_path: R2 path to classifier model weights
        classifier_classes: Class names the classifier can predict
        confidence_threshold: SAM3 detection confidence threshold
        classifier_confidence: Minimum classifier confidence to accept
        start_time: Start time in seconds
        end_time: End time in seconds (None = until end)
        frame_skip: Return every Nth frame in results (SAM3 still tracks all)
        sam3_model_path: Path to SAM3 model (None for auto-download)
        download_classifier_fn: Function to download classifier from R2
    
    Returns:
        Dict with success, frame_results, and summary statistics
    """
    os.environ["ULTRALYTICS_AUTOUPDATE"] = "false"
    
    work_dir = Path(tempfile.mkdtemp(prefix="hybrid_video_"))
    
    try:
        print(f"=== Hybrid Video Inference ==")
        print(f"SAM3 prompts: {sam3_prompts}")
        print(f"Frame skip (for output): {frame_skip}")
        
        # Phase 0: Download video and get metadata
        if progress_callback:
            progress_callback("downloading", 0, 0, "downloading video")
        video_path, metadata = download_video(video_url, work_dir)
        fps = metadata["fps"]
        frame_width = metadata["frame_width"]
        frame_height = metadata["frame_height"]
        total_frames = metadata["total_frames"]
        
        # Calculate frame range
        start_frame = int(start_time * fps)
        end_frame = int(end_time * fps) if end_time else total_frames
        
        # Phase 1: Load classifier — flush GPU memory first
        import gc
        import torch
        gc.collect()
        if torch.cuda.is_available():
            torch.cuda.empty_cache()
        if progress_callback:
            progress_callback("loading", 0, 0, "loading classifier")
        print("\n[2/5] Loading classifier model...")
        
        ext = ".pth" if classifier_r2_path.endswith(".pth") else ".pt"
        classifier_path = work_dir / f"classifier{ext}"
        
        if download_classifier_fn:
            if not download_classifier_fn(classifier_r2_path, classifier_path):
                raise RuntimeError(f"Failed to download classifier from {classifier_r2_path}")
        else:
            raise ValueError("download_classifier_fn is required")
        
        classifier_data = load_classifier(classifier_r2_path, classifier_path)
        
        if classifier_data["type"] == "convnext":
            print(f"  ConvNeXt classifier loaded: {len(classifier_data['idx_to_class'])} classes")
        else:
            print(f"  YOLO classifier loaded: {len(classifier_data['model'].names)} classes")
        
        # Phase 2: Run SAM3 video detection
        frame_detections, unique_tracks = run_sam3_video_detection(
            video_path=video_path,
            sam3_prompts=sam3_prompts,
            confidence_threshold=confidence_threshold,
            start_frame=start_frame,
            end_frame=end_frame,
            sam3_model_path=sam3_model_path,
            progress_callback=progress_callback,
            imgsz=imgsz,
            frame_width=frame_width,
            frame_height=frame_height,
        )
        
        # Phase 3: Classify unique tracks
        if progress_callback:
            progress_callback("classifying", 0, len(unique_tracks), f"classifying {len(unique_tracks)} tracks")
        classifications, crop_records = classify_unique_tracks(
            video_path=video_path,
            unique_tracks=unique_tracks,
            classifier_data=classifier_data,
            classifier_classes=classifier_classes,
            classifier_confidence=classifier_confidence,
            work_dir=work_dir,
            classify_top_k=classify_top_k,
            frame_width=frame_width,
            frame_height=frame_height,
        )
        
        # Phase 4: Propagate labels and format output
        if progress_callback:
            progress_callback("formatting", 0, 0, "formatting results")
        frame_results = propagate_labels_and_format(
            frame_detections=frame_detections,
            classifications=classifications,
            frame_width=frame_width,
            frame_height=frame_height,
            start_frame=start_frame,
            frame_skip=frame_skip,
        )
        
        total_predictions = sum(len(f["predictions"]) for f in frame_results)
        
        print(f"\n=== Results ===")
        print(f"Output frames: {len(frame_results)}")
        print(f"Total predictions: {total_predictions}")
        print(f"Unique tracks classified: {len(classifications)}")
        
        # Upload classification crops directly to R2 if callback provided
        classification_crops = []
        for i, cr in enumerate(crop_records):
            crop_entry = {
                "class_name": cr["class_name"],
                "confidence": round(cr["confidence"], 2),
                "track_id": cr["track_id"],
                "frame_num": cr["frame_num"],
            }
            if upload_crop_fn:
                try:
                    r2_path = f"inference_temp/crops/crop_{cr['track_id']}_{cr['frame_num']}_{i}.jpg"
                    url = upload_crop_fn(cr["crop_bytes"], r2_path)
                    crop_entry["url"] = url
                    crop_entry["r2_path"] = r2_path
                except Exception as e:
                    print(f"  Warning: failed to upload crop {i}: {e}")
                    crop_entry["crop_b64"] = base64.b64encode(cr["crop_bytes"]).decode("ascii")
            else:
                # Fallback: base64 encode if no upload function
                crop_entry["crop_b64"] = base64.b64encode(cr["crop_bytes"]).decode("ascii")
            classification_crops.append(crop_entry)
        
        return {
            "success": True,
            "frame_results": frame_results,
            "processed_frames": len(frame_results),
            "total_predictions": total_predictions,
            "unique_tracks": len(unique_tracks),
            "classified_tracks": len(classifications),
            "fps": fps,
            "classification_crops": classification_crops,
        }
        
    except Exception as e:
        import traceback
        error_msg = str(e)
        print(f"\nVideo inference failed: {error_msg}")
        traceback.print_exc()
        
        return {
            "success": False,
            "error": error_msg,
            "frame_results": [],
        }
        
    finally:
        import shutil
        shutil.rmtree(work_dir, ignore_errors=True)
