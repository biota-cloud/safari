"""
Evaluation Engine — Compare model predictions against ground truth annotations.

Pure Python logic (runs on web server, no GPU needed).
IoU-based matching, per-class metrics, confusion matrix, and multi-run comparison.
"""

from typing import Optional


# =============================================================================
# IoU & BOX UTILITIES
# =============================================================================


def _annotation_to_xyxy(ann: dict) -> tuple[float, float, float, float]:
    """
    Convert annotation format {x, y, width, height} to (x1, y1, x2, y2).
    All values are normalized 0-1.
    """
    x = ann.get("x", 0)
    y = ann.get("y", 0)
    w = ann.get("width", 0)
    h = ann.get("height", 0)
    return (x, y, x + w, y + h)


def _prediction_box_to_xyxy(pred: dict) -> tuple[float, float, float, float]:
    """
    Convert prediction box format [x1, y1, x2, y2] or {x, y, width, height} to tuple.
    Handles both formats for robustness.
    """
    box = pred.get("box")
    if box and isinstance(box, (list, tuple)) and len(box) == 4:
        return tuple(box)
    # Fallback: annotation-style format
    return _annotation_to_xyxy(pred)


def compute_iou(box_a: tuple, box_b: tuple) -> float:
    """Compute Intersection over Union between two (x1, y1, x2, y2) boxes."""
    x1 = max(box_a[0], box_b[0])
    y1 = max(box_a[1], box_b[1])
    x2 = min(box_a[2], box_b[2])
    y2 = min(box_a[3], box_b[3])

    inter_w = max(0, x2 - x1)
    inter_h = max(0, y2 - y1)
    inter_area = inter_w * inter_h

    area_a = (box_a[2] - box_a[0]) * (box_a[3] - box_a[1])
    area_b = (box_b[2] - box_b[0]) * (box_b[3] - box_b[1])
    union_area = area_a + area_b - inter_area

    if union_area <= 0:
        return 0.0
    return inter_area / union_area


# =============================================================================
# PER-IMAGE MATCHING (GT ↔ Predictions)
# =============================================================================


def match_predictions_to_gt(
    gt_annotations: list[dict],
    predictions: list[dict],
    iou_threshold: float = 0.5,
    classes: list[str] | None = None,
    confidence_threshold: float = 0,
) -> dict:
    """
    Match predictions to ground truth annotations for a single image.

    Uses greedy matching by IoU (highest first) with class-aware matching:
    a match requires BOTH IoU >= threshold AND matching class.

    Args:
        gt_annotations: List of GT annotations {class_id, x, y, width, height}
        predictions: List of predictions {class_name, confidence, box/x/y/width/height}
        iou_threshold: IoU threshold for matching (default 0.5)
        classes: Class name list for resolving class_id → class_name
        confidence_threshold: Min confidence to include a prediction (default 0 = all)

    Returns:
        {
            "matches": [{gt_idx, pred_idx, iou, gt_class, pred_class, class_match}],
            "tp": int, "fp": int, "fn": int,
            "tp_details": [...], "fp_details": [...], "fn_details": [...]
        }
    """
    classes = classes or []

    # Filter predictions by confidence threshold
    if confidence_threshold > 0:
        predictions = [p for p in predictions if p.get("confidence", 0) >= confidence_threshold]

    # Convert GT boxes
    gt_boxes = [_annotation_to_xyxy(gt) for gt in gt_annotations]
    gt_class_names = []
    for gt in gt_annotations:
        cid = gt.get("class_id", 0)
        name = classes[cid] if cid < len(classes) else f"class_{cid}"
        gt_class_names.append(name)

    # Convert prediction boxes
    pred_boxes = [_prediction_box_to_xyxy(p) for p in predictions]
    pred_class_names = [p.get("class_name", "unknown") for p in predictions]

    # Compute IoU matrix
    iou_pairs = []
    for gi, gb in enumerate(gt_boxes):
        for pi, pb in enumerate(pred_boxes):
            iou = compute_iou(gb, pb)
            if iou >= iou_threshold:
                iou_pairs.append((iou, gi, pi))

    # Greedy matching: highest IoU first, class-aware
    iou_pairs.sort(key=lambda x: x[0], reverse=True)
    matched_gt = set()
    matched_pred = set()
    matches = []

    for iou_val, gi, pi in iou_pairs:
        if gi in matched_gt or pi in matched_pred:
            continue
        gt_cls = gt_class_names[gi]
        pred_cls = pred_class_names[pi]
        class_match = (gt_cls == pred_cls)
        matches.append({
            "gt_idx": gi,
            "pred_idx": pi,
            "iou": round(iou_val, 4),
            "gt_class": gt_cls,
            "pred_class": pred_cls,
            "class_match": class_match,
        })
        matched_gt.add(gi)
        matched_pred.add(pi)

    # Classify results
    tp_details = [m for m in matches if m["class_match"]]
    fp_mis = [m for m in matches if not m["class_match"]]  # Misclassified

    # Unmatched predictions = false positives (spurious detections)
    unmatched_pred = set(range(len(predictions))) - matched_pred
    fp_spurious = [
        {"pred_idx": pi, "pred_class": pred_class_names[pi], "type": "spurious"}
        for pi in sorted(unmatched_pred)
    ]

    # Unmatched GT = false negatives (missed detections)
    unmatched_gt = set(range(len(gt_annotations))) - matched_gt
    fn_details = [
        {"gt_idx": gi, "gt_class": gt_class_names[gi]}
        for gi in sorted(unmatched_gt)
    ]

    tp = len(tp_details)
    fp = len(fp_mis) + len(fp_spurious)
    fn = len(fn_details)

    return {
        "matches": matches,
        "tp": tp,
        "fp": fp,
        "fn": fn,
        "tp_details": tp_details,
        "fp_details": fp_mis + fp_spurious,
        "fn_details": fn_details,
    }


# =============================================================================
# AGGREGATE METRICS
# =============================================================================


def aggregate_metrics(
    all_image_results: list[dict],
    classes: list[str],
) -> dict:
    """
    Aggregate per-image match results into per-class and overall metrics.

    Args:
        all_image_results: List of match_predictions_to_gt() results
        classes: Class name list

    Returns:
        {
            "overall": {precision, recall, f1, total_tp, total_fp, total_fn},
            "per_class": {class_name: {tp, fp, fn, precision, recall, f1}},
            "confusion_matrix": {labels: [...], matrix: [[...]]},
        }
    """
    # Initialize per-class counters
    class_metrics = {}
    for cls in classes:
        class_metrics[cls] = {"tp": 0, "fp": 0, "fn": 0}

    # Also track confusion: confusion[gt_class][pred_class] += 1
    confusion = {}
    for cls in classes:
        confusion[cls] = {c: 0 for c in classes}
        confusion[cls]["__missed__"] = 0  # GT with no matching prediction
    confusion["__background__"] = {c: 0 for c in classes}  # Spurious preds

    for result in all_image_results:
        # True positives
        for m in result.get("tp_details", []):
            cls = m["gt_class"]
            if cls in class_metrics:
                class_metrics[cls]["tp"] += 1
            # Confusion: correct → diagonal
            if cls in confusion:
                confusion[cls][cls] = confusion[cls].get(cls, 0) + 1

        # False positives (misclassified)
        for m in result.get("fp_details", []):
            if m.get("type") == "spurious":
                # Spurious detection — no GT match
                pred_cls = m["pred_class"]
                if pred_cls in class_metrics:
                    class_metrics[pred_cls]["fp"] += 1
                confusion["__background__"][pred_cls] = confusion["__background__"].get(pred_cls, 0) + 1
            else:
                # Misclassified — matched GT but wrong class
                gt_cls = m.get("gt_class", "")
                pred_cls = m.get("pred_class", "")
                if pred_cls in class_metrics:
                    class_metrics[pred_cls]["fp"] += 1
                if gt_cls in class_metrics:
                    class_metrics[gt_cls]["fn"] += 1
                # Confusion: off-diagonal
                if gt_cls in confusion and pred_cls in confusion[gt_cls]:
                    confusion[gt_cls][pred_cls] += 1

        # False negatives (missed)
        for m in result.get("fn_details", []):
            cls = m["gt_class"]
            if cls in class_metrics:
                class_metrics[cls]["fn"] += 1
            if cls in confusion:
                confusion[cls]["__missed__"] += 1

    # Compute P/R/F1 per class
    per_class = {}
    for cls, m in class_metrics.items():
        tp, fp, fn = m["tp"], m["fp"], m["fn"]
        precision = tp / (tp + fp) if (tp + fp) > 0 else 0.0
        recall = tp / (tp + fn) if (tp + fn) > 0 else 0.0
        f1 = 2 * precision * recall / (precision + recall) if (precision + recall) > 0 else 0.0
        per_class[cls] = {
            "tp": tp,
            "fp": fp,
            "fn": fn,
            "precision": round(precision, 4),
            "recall": round(recall, 4),
            "f1": round(f1, 4),
        }

    # Overall (macro average)
    total_tp = sum(m["tp"] for m in per_class.values())
    total_fp = sum(m["fp"] for m in per_class.values())
    total_fn = sum(m["fn"] for m in per_class.values())

    overall_p = total_tp / (total_tp + total_fp) if (total_tp + total_fp) > 0 else 0.0
    overall_r = total_tp / (total_tp + total_fn) if (total_tp + total_fn) > 0 else 0.0
    overall_f1 = 2 * overall_p * overall_r / (overall_p + overall_r) if (overall_p + overall_r) > 0 else 0.0

    # Build confusion matrix as 2D array
    # Labels: classes + "__background__" (rows = GT, cols = Predicted + "__missed__")
    matrix_labels = list(classes) + ["__background__"]
    col_labels = list(classes) + ["__missed__"]
    matrix = []
    for row_cls in matrix_labels:
        row_data = []
        for col_cls in col_labels:
            if row_cls == "__background__" and col_cls == "__missed__":
                row_data.append(0)
            elif row_cls == "__background__":
                row_data.append(confusion.get("__background__", {}).get(col_cls, 0))
            else:
                row_data.append(confusion.get(row_cls, {}).get(col_cls, 0))
        matrix.append(row_data)

    return {
        "overall": {
            "precision": round(overall_p, 4),
            "recall": round(overall_r, 4),
            "f1": round(overall_f1, 4),
            "total_tp": total_tp,
            "total_fp": total_fp,
            "total_fn": total_fn,
        },
        "per_class": per_class,
        "confusion_matrix": {
            "row_labels": matrix_labels,
            "col_labels": col_labels,
            "matrix": matrix,
        },
    }


# =============================================================================
# MULTI-RUN COMPARISON
# =============================================================================


def compare_runs(
    runs: list[dict],
) -> dict:
    """
    Compare 2-3 evaluation runs and compute per-class deltas.

    Args:
        runs: List of evaluation run dicts (with per_class_metrics populated)

    Returns:
        {
            "runs": [{id, model_name, overall_f1, ...}],
            "per_class_deltas": {
                class_name: [
                    {run_id, f1, precision, recall},
                    ...
                ]
            },
            "improved_classes": [classes where last run > first run],
            "degraded_classes": [classes where last run < first run],
        }
    """
    if not runs or len(runs) < 2:
        return {"runs": [], "per_class_deltas": {}, "improved_classes": [], "degraded_classes": []}

    # Collect all class names across runs
    all_classes = set()
    for run in runs:
        pcm = run.get("per_class_metrics") or {}
        all_classes.update(pcm.keys())

    # Build per-class comparison
    per_class_deltas = {}
    for cls in sorted(all_classes):
        per_class_deltas[cls] = []
        for run in runs:
            pcm = run.get("per_class_metrics") or {}
            class_data = pcm.get(cls, {"tp": 0, "fp": 0, "fn": 0, "precision": 0, "recall": 0, "f1": 0})
            per_class_deltas[cls].append({
                "run_id": run["id"],
                "model_name": run.get("model_name", ""),
                "f1": class_data.get("f1", 0),
                "precision": class_data.get("precision", 0),
                "recall": class_data.get("recall", 0),
                "tp": class_data.get("tp", 0),
                "fp": class_data.get("fp", 0),
                "fn": class_data.get("fn", 0),
            })

    # Compute improved/degraded (first run vs last run)
    first_run = runs[0]
    last_run = runs[-1]
    improved = []
    degraded = []

    first_pcm = first_run.get("per_class_metrics") or {}
    last_pcm = last_run.get("per_class_metrics") or {}

    for cls in sorted(all_classes):
        first_f1 = first_pcm.get(cls, {}).get("f1", 0)
        last_f1 = last_pcm.get(cls, {}).get("f1", 0)
        delta = last_f1 - first_f1
        if delta > 0.01:
            improved.append({"class": cls, "delta": round(delta, 4), "from": first_f1, "to": last_f1})
        elif delta < -0.01:
            degraded.append({"class": cls, "delta": round(delta, 4), "from": first_f1, "to": last_f1})

    # Sort by magnitude
    improved.sort(key=lambda x: x["delta"], reverse=True)
    degraded.sort(key=lambda x: x["delta"])

    run_summaries = []
    for run in runs:
        overall = run.get("overall_metrics") or {}
        run_summaries.append({
            "id": run["id"],
            "model_name": run.get("model_name", ""),
            "dataset_name": run.get("dataset_name", ""),
            "overall_f1": overall.get("f1", 0),
            "overall_precision": overall.get("precision", 0),
            "overall_recall": overall.get("recall", 0),
            "total_images": run.get("total_images", 0),
            "created_at": run.get("created_at", ""),
        })

    return {
        "runs": run_summaries,
        "per_class_deltas": per_class_deltas,
        "improved_classes": improved,
        "degraded_classes": degraded,
    }
