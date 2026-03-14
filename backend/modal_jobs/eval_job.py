"""
Modal Evaluation Job — CPU-only orchestrator for model evaluation.

This Modal function:
1. Receives evaluation parameters (run_id, model, dataset, etc.)
2. Calls existing GPU inference jobs (YOLO or Hybrid) via Modal .remote()
3. Matches predictions to GT using evaluation_engine.py
4. Writes results directly to Supabase (no browser dependency)

Usage (from Reflex app):
    fn = modal.Function.from_name("safari-evaluation", "run_evaluation")
    fn.spawn(run_id=..., project_id=..., ...)
"""

import modal
from pathlib import Path

app = modal.App("safari-evaluation")

# Paths for mounting backend modules
_BACKEND_DIR = Path(__file__).resolve().parent.parent
_CORE_DIR = _BACKEND_DIR / "core"
_BACKEND_INIT = _BACKEND_DIR / "__init__.py"
_EVAL_ENGINE = _BACKEND_DIR / "evaluation_engine.py"

# CPU-only image — no GPU dependencies needed
image = (
    modal.Image.debian_slim(python_version="3.11")
    .pip_install(
        "supabase",
        "boto3",
    )
    .env({"PYTHONPATH": "/root"})
    .add_local_dir(local_path=str(_CORE_DIR), remote_path="/root/backend/core")
    .add_local_file(local_path=str(_BACKEND_INIT), remote_path="/root/backend/__init__.py")
    .add_local_file(local_path=str(_EVAL_ENGINE), remote_path="/root/backend/evaluation_engine.py")
)


@app.function(
    image=image,
    timeout=1800,  # 30 min for large datasets
    secrets=[
        modal.Secret.from_name("r2-credentials"),
        modal.Secret.from_name("supabase-credentials"),
    ],
)
def run_evaluation(
    run_id: str,
    project_id: str,
    model_id: str,
    dataset_id: str,
    classes: list[str],
    confidence_threshold: float,
    iou_threshold: float,
    is_hybrid: bool = False,
    sam3_prompts: list[str] | None = None,
    classifier_r2_path: str = "",
    classifier_classes: list[str] | None = None,
    classifier_confidence: float = 0.5,
    sam3_confidence: float = 0.5,
    sam3_imgsz: int = 1918,
):
    """Thin wrapper that calls evaluation_core.run_evaluation_job()."""
    from backend.core.evaluation_core import run_evaluation_job

    print(f"[EvalJob] === User Settings ===")
    print(f"[EvalJob]   run_id: {run_id}")
    print(f"[EvalJob]   model_id: {model_id}")
    print(f"[EvalJob]   dataset_id: {dataset_id}")
    print(f"[EvalJob]   classes: {classes}")
    print(f"[EvalJob]   is_hybrid: {is_hybrid}")
    print(f"[EvalJob]   confidence_threshold: {confidence_threshold}")
    print(f"[EvalJob]   iou_threshold: {iou_threshold}")
    if is_hybrid:
        print(f"[EvalJob]   sam3_prompts: {sam3_prompts}")
        print(f"[EvalJob]   sam3_imgsz: {sam3_imgsz}")
        print(f"[EvalJob]   sam3_confidence: {sam3_confidence}")
        print(f"[EvalJob]   classifier_confidence: {classifier_confidence}")
        print(f"[EvalJob]   classifier_r2_path: {classifier_r2_path}")
        print(f"[EvalJob]   classifier_classes: {classifier_classes}")

    run_evaluation_job(
        run_id=run_id,
        project_id=project_id,
        model_id=model_id,
        dataset_id=dataset_id,
        classes=classes,
        confidence_threshold=confidence_threshold,
        iou_threshold=iou_threshold,
        is_hybrid=is_hybrid,
        sam3_prompts=sam3_prompts,
        classifier_r2_path=classifier_r2_path,
        classifier_classes=classifier_classes,
        classifier_confidence=classifier_confidence,
        sam3_confidence=sam3_confidence,
        sam3_imgsz=sam3_imgsz,
    )
