"""
Spike Test: SAM3 Cross-Image Exemplar Detection

Tests whether SAM3's PCS (Promptable Concept Segmentation) can use bounding
box exemplars from one annotated image to detect similar objects in a
different, unannotated image.

Test plan:
1. Fetch 4 annotated images from dataset 2562ed42-89bd-482c-a650-cd62c4f8acb0
2. Use image #1's bbox as an exemplar on image #2 (cross-image, same concept)
3. Use image #1's bbox as an exemplar on image #1 (same-image baseline)
4. Log detection counts, confidence scores, and any errors

Usage:
    modal run scripts/spike_cross_image_exemplar.py
"""

import os
import sys
import json
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor, as_completed

import modal

app = modal.App("sam3-exemplar-spike")

sam3_volume = modal.Volume.from_name("sam3-volume", create_if_missing=False)

image = (
    modal.Image.debian_slim(python_version="3.11")
    .apt_install("libgl1-mesa-glx", "libglib2.0-0", "git")
    .pip_install(
        "ultralytics>=8.3.237",
        "boto3",
        "supabase",
        "requests",
        "pillow",
        "ftfy",
        "regex",
        "timm",
        "huggingface_hub",
    )
    .pip_install("git+https://github.com/ultralytics/CLIP.git")
)

DATASET_ID = "2562ed42-89bd-482c-a650-cd62c4f8acb0"


def download_file(url: str, dest_path: Path) -> bool:
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


@app.function(
    image=image,
    gpu="L40S",
    timeout=600,
    volumes={"/models": sam3_volume},
    secrets=[
        modal.Secret.from_name("r2-credentials"),
        modal.Secret.from_name("supabase-credentials"),
    ],
)
def run_spike_test() -> dict:
    """Core spike test: cross-image exemplar detection with SAM3."""
    import cv2
    import numpy as np
    import boto3
    import tempfile
    from botocore.config import Config
    from supabase import create_client

    os.environ["ULTRALYTICS_AUTOUPDATE"] = "false"

    # --- 1. Fetch image list + annotations from Supabase ---
    print("=" * 60)
    print("SAM3 Cross-Image Exemplar Spike Test")
    print("=" * 60)

    supabase = create_client(
        os.environ["SUPABASE_URL"],
        os.environ["SUPABASE_KEY"],
    )

    # Get images from the dataset that have annotations
    res = supabase.table("images") \
        .select("id, filename, r2_path, annotation_count, annotations") \
        .eq("dataset_id", DATASET_ID) \
        .gt("annotation_count", 0) \
        .limit(6) \
        .execute()

    images = res.data
    print(f"Found {len(images)} annotated images")

    if len(images) < 2:
        return {"error": "Need at least 2 annotated images"}

    # Pick reference image (most annotations) and target images
    images.sort(key=lambda x: x.get("annotation_count", 0), reverse=True)
    ref_image = images[0]
    target_images = images[1:4]  # Up to 3 targets

    print(f"\nReference image: {ref_image['filename']} ({ref_image['annotation_count']} annotations)")
    for t in target_images:
        print(f"Target image:    {t['filename']} ({t['annotation_count']} annotations)")

    # --- 2. Download images from R2 ---
    print("\n--- Downloading images from R2 ---")

    s3 = boto3.client(
        's3',
        endpoint_url=os.environ['R2_ENDPOINT_URL'],
        aws_access_key_id=os.environ['R2_ACCESS_KEY_ID'],
        aws_secret_access_key=os.environ['R2_SECRET_ACCESS_KEY'],
        config=Config(signature_version='s3v4'),
        region_name='auto',
    )
    bucket = os.environ['R2_BUCKET_NAME']

    work_dir = Path(tempfile.mkdtemp(prefix="spike_"))
    all_images = [ref_image] + target_images
    image_paths = {}

    for img in all_images:
        r2_path = img["r2_path"]
        dest = work_dir / f"{img['id']}.jpg"
        try:
            url = s3.generate_presigned_url(
                'get_object',
                Params={'Bucket': bucket, 'Key': r2_path},
                ExpiresIn=300,
            )
            download_file(url, dest)
            image_paths[img['id']] = dest
            print(f"  Downloaded: {img['filename']}")
        except Exception as e:
            print(f"  FAILED: {img['filename']}: {e}")

    # --- 3. Parse reference annotations -> get exemplar bboxes ---
    print("\n--- Parsing reference annotations ---")

    ref_anns = ref_image.get("annotations")
    if isinstance(ref_anns, str):
        ref_anns = json.loads(ref_anns)
    if not ref_anns:
        return {"error": "Reference image has no annotations"}

    # Read reference image dimensions
    ref_path = image_paths[ref_image['id']]
    ref_img = cv2.imread(str(ref_path))
    ref_h, ref_w = ref_img.shape[:2]

    # Convert normalized annotations to pixel xyxy for SAM3
    exemplar_bboxes = []
    for ann in ref_anns[:3]:  # Use up to 3 bboxes as exemplars
        x1 = ann["x"] * ref_w
        y1 = ann["y"] * ref_h
        x2 = (ann["x"] + ann["width"]) * ref_w
        y2 = (ann["y"] + ann["height"]) * ref_h
        exemplar_bboxes.append([x1, y1, x2, y2])
        class_name = ann.get("class_name", "unknown")
        print(f"  Exemplar bbox: [{x1:.0f}, {y1:.0f}, {x2:.0f}, {y2:.0f}] class={class_name}")

    # --- 4. Initialize SAM3 ---
    print("\n--- Initializing SAM3 SemanticPredictor ---")
    from ultralytics.models.sam import SAM3SemanticPredictor

    overrides = dict(
        conf=0.15,  # Low conf for discovery
        task="segment",
        mode="predict",
        model="/models/sam3.pt",
        half=True,
        save=False,
    )
    predictor = SAM3SemanticPredictor(overrides=overrides)

    results_log = {}

    # --- 5. Test A: Same-image exemplar (baseline) ---
    print("\n" + "=" * 60)
    print("TEST A: Same-image exemplar (baseline)")
    print("=" * 60)

    predictor.set_image(str(ref_path))
    try:
        results = predictor(bboxes=exemplar_bboxes)
        if results and len(results) > 0:
            res_a = results[0]
            n_detections = len(res_a.boxes) if hasattr(res_a, 'boxes') and res_a.boxes is not None else 0
            n_masks = len(res_a.masks.data) if hasattr(res_a, 'masks') and res_a.masks is not None else 0
            confs = res_a.boxes.conf.cpu().numpy().tolist() if n_detections > 0 else []
            print(f"  Detections: {n_detections}")
            print(f"  Masks: {n_masks}")
            print(f"  Confidences: {[f'{c:.3f}' for c in confs[:10]]}")
            results_log["test_a_same_image"] = {
                "detections": n_detections,
                "masks": n_masks,
                "confidences": confs[:10],
            }
        else:
            print("  No results returned")
            results_log["test_a_same_image"] = {"detections": 0, "error": "no results"}
    except Exception as e:
        print(f"  ERROR: {e}")
        import traceback; traceback.print_exc()
        results_log["test_a_same_image"] = {"error": str(e)}

    # --- 6. Test B: Cross-image exemplar (the key test) ---
    print("\n" + "=" * 60)
    print("TEST B: Cross-image exemplar (reference -> target)")
    print("=" * 60)
    print("Using exemplar bboxes from reference image on different images")

    # Method 1: Extract features from ref, query on target via inference_features
    print("\n--- Method 1: inference_features transfer ---")

    predictor_ref = SAM3SemanticPredictor(overrides=overrides)
    predictor_target = SAM3SemanticPredictor(overrides=overrides)
    predictor_target.setup_model()

    predictor_ref.set_image(str(ref_path))
    ref_features = predictor_ref.features
    ref_shape = (ref_h, ref_w)

    for i, target_img in enumerate(target_images):
        target_path = image_paths.get(target_img['id'])
        if not target_path:
            continue

        target_cv = cv2.imread(str(target_path))
        target_h, target_w = target_cv.shape[:2]
        target_shape = (target_h, target_w)

        print(f"\n  Target {i+1}: {target_img['filename']}")
        print(f"  Known annotations: {target_img['annotation_count']}")

        # Try using the reference features + exemplar bboxes on the target image
        try:
            # First set the target image to get its features
            predictor_target.set_image(str(target_path))
            target_features = predictor_target.features

            # Now query target features with the exemplar bboxes
            masks, boxes = predictor_target.inference_features(
                target_features,
                src_shape=target_shape,
                bboxes=exemplar_bboxes,
            )

            n_det = len(boxes) if boxes is not None else 0
            n_mask = len(masks) if masks is not None else 0
            print(f"  inference_features result: {n_det} boxes, {n_mask} masks")

            if boxes is not None and len(boxes) > 0:
                # Try to extract confidence if available
                if hasattr(boxes, 'conf'):
                    confs = boxes.conf.cpu().numpy().tolist()
                    print(f"  Confidences: {[f'{c:.3f}' for c in confs[:10]]}")
                else:
                    confs = []
                    print(f"  Box coords: {boxes[:5]}")

            results_log[f"test_b_method1_target{i+1}"] = {
                "filename": target_img['filename'],
                "detections": n_det,
                "masks": n_mask,
            }

        except Exception as e:
            print(f"  ERROR (method 1): {e}")
            import traceback; traceback.print_exc()
            results_log[f"test_b_method1_target{i+1}"] = {"error": str(e)}

    # Method 2: Direct predictor call on target with ref bboxes
    print("\n--- Method 2: Direct predictor(bboxes=...) on target image ---")

    predictor2 = SAM3SemanticPredictor(overrides=overrides)

    for i, target_img in enumerate(target_images):
        target_path = image_paths.get(target_img['id'])
        if not target_path:
            continue

        print(f"\n  Target {i+1}: {target_img['filename']}")

        try:
            predictor2.set_image(str(target_path))
            results = predictor2(bboxes=exemplar_bboxes)

            if results and len(results) > 0:
                res_b = results[0]
                n_det = len(res_b.boxes) if hasattr(res_b, 'boxes') and res_b.boxes is not None else 0
                n_mask = len(res_b.masks.data) if hasattr(res_b, 'masks') and res_b.masks is not None else 0
                confs = res_b.boxes.conf.cpu().numpy().tolist() if n_det > 0 else []
                print(f"  Detections: {n_det}")
                print(f"  Masks: {n_mask}")
                print(f"  Confidences: {[f'{c:.3f}' for c in confs[:10]]}")

                # Compare with known annotation count
                known = target_img['annotation_count']
                print(f"  Known annotations: {known}, Found: {n_det} (delta: {n_det - known:+d})")

                results_log[f"test_b_method2_target{i+1}"] = {
                    "filename": target_img['filename'],
                    "detections": n_det,
                    "masks": n_mask,
                    "confidences": confs[:10],
                    "known_annotations": known,
                }
            else:
                print("  No results returned")
                results_log[f"test_b_method2_target{i+1}"] = {"detections": 0}

        except Exception as e:
            print(f"  ERROR (method 2): {e}")
            import traceback; traceback.print_exc()
            results_log[f"test_b_method2_target{i+1}"] = {"error": str(e)}

    # --- 7. Test C: Text prompt baseline comparison ---
    print("\n" + "=" * 60)
    print("TEST C: Text prompt baseline (for comparison)")
    print("=" * 60)

    # Get class names from reference annotations
    class_names = list(set(
        ann.get("class_name", "animal")
        for ann in ref_anns
        if ann.get("class_name")
    ))
    if not class_names:
        class_names = ["animal"]
    print(f"  Text prompts: {class_names}")

    predictor3 = SAM3SemanticPredictor(overrides=overrides)

    for i, target_img in enumerate(target_images):
        target_path = image_paths.get(target_img['id'])
        if not target_path:
            continue

        print(f"\n  Target {i+1}: {target_img['filename']}")

        try:
            predictor3.set_image(str(target_path))
            results = predictor3(text=class_names)

            if results and len(results) > 0:
                res_c = results[0]
                n_det = len(res_c.boxes) if hasattr(res_c, 'boxes') and res_c.boxes is not None else 0
                confs = res_c.boxes.conf.cpu().numpy().tolist() if n_det > 0 else []
                known = target_img['annotation_count']
                print(f"  Detections: {n_det}")
                print(f"  Confidences: {[f'{c:.3f}' for c in confs[:10]]}")
                print(f"  Known annotations: {known}, Found: {n_det} (delta: {n_det - known:+d})")

                results_log[f"test_c_text_target{i+1}"] = {
                    "filename": target_img['filename'],
                    "detections": n_det,
                    "confidences": confs[:10],
                    "known_annotations": known,
                }

        except Exception as e:
            print(f"  ERROR: {e}")
            results_log[f"test_c_text_target{i+1}"] = {"error": str(e)}

    # --- Summary ---
    print("\n" + "=" * 60)
    print("SUMMARY")
    print("=" * 60)
    print(json.dumps(results_log, indent=2, default=str))

    return results_log
