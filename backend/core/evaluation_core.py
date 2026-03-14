"""
Evaluation Core — Browser-independent evaluation orchestration.

Extracted from EvaluationState.start_evaluation() to run inside a Modal function
(or any serverless context) without depending on Reflex/WebSocket connections.

This module:
1. Loads GT images from Supabase
2. Generates presigned R2 URLs
3. Calls existing inference (YOLO batch or Hybrid batch) via Modal
4. Matches predictions to GT using evaluation_engine.py
5. Writes prediction records + metrics to Supabase

Pure Python — no GPU, no Reflex dependencies.
"""

import os
import json
from datetime import datetime, timezone


def run_evaluation_job(
    run_id: str,
    project_id: str,
    model_id: str,
    dataset_id: str,
    classes: list[str],
    confidence_threshold: float,
    iou_threshold: float,
    # Hybrid-specific params (None = YOLO detection mode)
    is_hybrid: bool = False,
    sam3_prompts: list[str] | None = None,
    classifier_r2_path: str = "",
    classifier_classes: list[str] | None = None,
    classifier_confidence: float = 0.5,
    sam3_confidence: float = 0.5,
    sam3_imgsz: int = 1918,
):
    """
    Run a complete evaluation: inference → match GT → compute metrics → write DB.

    This function is designed to run inside a Modal function (CPU-only) and call
    existing GPU inference jobs via Modal .remote(). It writes all results directly
    to Supabase, so it doesn't depend on a browser connection.

    Args:
        run_id: Pre-created evaluation_runs row ID
        project_id: Project UUID
        model_id: Model UUID (for YOLO detection dispatch)
        dataset_id: Dataset UUID
        classes: Project class list for GT class_id resolution
        confidence_threshold: Inference confidence threshold
        iou_threshold: IoU threshold for GT matching
        is_hybrid: True for SAM3 + classifier, False for YOLO detection
        sam3_prompts: SAM3 text prompts (hybrid only)
        classifier_r2_path: R2 path to classifier weights (hybrid only)
        classifier_classes: Classifier class list (hybrid only)
        classifier_confidence: Classifier confidence (hybrid only)
        sam3_confidence: SAM3 detection confidence (hybrid only)
        sam3_imgsz: SAM3 inference resolution (hybrid only)
    """
    import boto3
    from botocore.config import Config
    from supabase import create_client

    print(f"[EvalCore] Starting evaluation run {run_id}")
    print(f"[EvalCore] Model: {model_id}, Dataset: {dataset_id}, Classes: {classes}")

    # ── Initialize Supabase ────────────────────────────────────────────
    supabase = create_client(
        os.environ["SUPABASE_URL"],
        os.environ["SUPABASE_KEY"],
    )

    try:
        # Mark as running
        supabase.table("evaluation_runs").update({
            "status": "running",
            "started_at": datetime.now(timezone.utc).isoformat(),
        }).eq("id", run_id).execute()

        # ── Load GT images ─────────────────────────────────────────────
        print("[EvalCore] Loading ground truth images...")
        images_result = (
            supabase.table("images")
            .select("id, filename, r2_path, annotations")
            .eq("dataset_id", dataset_id)
            .execute()
        )
        all_images = images_result.data or []

        # Filter to labeled images only
        labeled_images = []
        for img in all_images:
            anns = img.get("annotations")
            if anns:
                if isinstance(anns, str):
                    anns = json.loads(anns)
                if anns:  # Non-empty list
                    img["annotations"] = anns
                    labeled_images.append(img)

        if not labeled_images:
            supabase.table("evaluation_runs").update({
                "status": "failed",
                "error_message": "No labeled images found in this dataset.",
            }).eq("id", run_id).execute()
            print("[EvalCore] No labeled images found, aborting.")
            return

        print(f"[EvalCore] Found {len(labeled_images)} labeled images")

        # ── Generate presigned URLs ────────────────────────────────────
        print("[EvalCore] Generating presigned URLs...")
        s3 = boto3.client(
            "s3",
            endpoint_url=os.environ["R2_ENDPOINT_URL"],
            aws_access_key_id=os.environ["R2_ACCESS_KEY_ID"],
            aws_secret_access_key=os.environ["R2_SECRET_ACCESS_KEY"],
            config=Config(signature_version="s3v4"),
            region_name="auto",
        )
        bucket = os.environ["R2_BUCKET_NAME"]

        image_urls = []
        image_filenames = []  # Track filenames for debug logging
        for img in labeled_images:
            url = s3.generate_presigned_url(
                "get_object",
                Params={"Bucket": bucket, "Key": img["r2_path"]},
                ExpiresIn=3600,
            )
            image_urls.append(url)
            image_filenames.append(img.get("filename", "unknown"))
            print(f"  [{len(image_urls)}] {img.get('filename', '?')} → r2: {img['r2_path']}")

        # ── Run batch inference via existing Modal jobs ─────────────────
        print(f"[EvalCore] Running batch inference on {len(image_urls)} images (hybrid={is_hybrid})...")
        supabase.table("evaluation_runs").update({
            "processed_images": 0,
        }).eq("id", run_id).execute()

        import modal

        if is_hybrid:
            # Hybrid: SAM3 + classifier
            prompt_class_map = {p: (classifier_classes or []) for p in (sam3_prompts or [])}
            fn = modal.Function.from_name("hybrid-inference", "hybrid_inference_batch")
            batch_results = fn.remote(
                image_urls=image_urls,
                sam3_prompts=sam3_prompts or ["animal"],
                classifier_r2_path=classifier_r2_path,
                classifier_classes=classifier_classes or [],
                prompt_class_map=prompt_class_map,
                confidence_threshold=sam3_confidence,
                classifier_confidence=classifier_confidence,
                sam3_imgsz=sam3_imgsz,
                image_filenames=image_filenames,
            )
        else:
            # YOLO detection
            cls = modal.Cls.from_name("yolo-inference", "YOLOInference")
            batch_results = cls().predict_images_batch.remote(
                model_type="custom",
                model_name_or_id=model_id,
                image_urls=image_urls,
                confidence=confidence_threshold,
            )

        print(f"[EvalCore] Inference complete, {len(batch_results)} results received")

        # ── Match predictions to GT ────────────────────────────────────
        print("[EvalCore] Matching predictions to ground truth...")
        from backend.evaluation_engine import (
            match_predictions_to_gt,
            aggregate_metrics,
        )

        all_image_results = []
        prediction_records = []
        db_batch_size = 50

        for idx, image in enumerate(labeled_images):
            try:
                gt_annotations = image.get("annotations", [])
                filename = image.get("filename", "unknown")

                # Get predictions for this image from batch results
                img_result = batch_results[idx] if idx < len(batch_results) else {}
                predictions = img_result.get("predictions", [])
                
                print(f"  [{idx+1}/{len(labeled_images)}] {filename}: {len(gt_annotations)} GT, {len(predictions)} preds")

                # Convert confidence from 0-1 float to 0-100 int (eval storage format)
                for pred in predictions:
                    pred["confidence"] = int(pred.get("confidence", 0) * 100)

                result = match_predictions_to_gt(
                    gt_annotations=gt_annotations,
                    predictions=predictions,
                    iou_threshold=iou_threshold,
                    classes=classes,
                )
                all_image_results.append(result)

                prediction_records.append({
                    "evaluation_run_id": run_id,
                    "image_id": image["id"],
                    "image_filename": image["filename"],
                    "image_r2_path": image.get("r2_path", ""),
                    "ground_truth": gt_annotations,
                    "predictions": predictions,
                    "matches": result["matches"],
                    "tp_count": result["tp"],
                    "fp_count": result["fp"],
                    "fn_count": result["fn"],
                })

                # Batch insert predictions
                if len(prediction_records) >= db_batch_size:
                    supabase.table("evaluation_predictions").insert(prediction_records).execute()
                    prediction_records = []

            except Exception as img_error:
                print(f"[EvalCore] Error matching image {image['filename']}: {img_error}")
                all_image_results.append({
                    "tp": 0, "fp": 0, "fn": 0,
                    "matches": [], "tp_details": [], "fp_details": [], "fn_details": [],
                })

            # Progress update every 50 images
            if (idx + 1) % 50 == 0:
                supabase.table("evaluation_runs").update({
                    "processed_images": idx + 1,
                }).eq("id", run_id).execute()

        # Flush remaining prediction records
        if prediction_records:
            supabase.table("evaluation_predictions").insert(prediction_records).execute()

        supabase.table("evaluation_runs").update({
            "processed_images": len(labeled_images),
        }).eq("id", run_id).execute()

        # ── Compute metrics ────────────────────────────────────────────
        print("[EvalCore] Computing aggregate metrics...")
        metrics = aggregate_metrics(all_image_results, classes)

        # ── Write final results ────────────────────────────────────────
        supabase.table("evaluation_runs").update({
            "status": "completed",
            "overall_metrics": metrics["overall"],
            "per_class_metrics": metrics["per_class"],
            "confusion_matrix": metrics["confusion_matrix"],
            "completed_at": datetime.now(timezone.utc).isoformat(),
        }).eq("id", run_id).execute()

        print(f"[EvalCore] ✅ Evaluation complete! F1={metrics['overall']['f1']:.4f}")

    except Exception as e:
        print(f"[EvalCore] ❌ Evaluation failed: {e}")
        import traceback
        traceback.print_exc()

        # Mark run as failed
        try:
            supabase.table("evaluation_runs").update({
                "status": "failed",
                "error_message": str(e)[:500],
            }).eq("id", run_id).execute()
        except Exception:
            pass
