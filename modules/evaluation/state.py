"""
Evaluation State — State management for model evaluation module.

Handles:
- Loading evaluation runs for a project
- Starting new evaluations (model + dataset → inference → comparison)
- Run comparison (up to 3 runs)
- Per-image drill-down with GT vs predictions overlay
"""

import reflex as rx
from typing import TypedDict
from datetime import datetime, timezone

from backend.supabase_client import (
    get_accessible_project_ids,
    get_user_models,
    get_project_datasets,
    get_dataset_images,
    get_evaluation_runs,
    get_evaluation_run,
    create_evaluation_run,
    update_evaluation_run,
    delete_evaluation_run as db_delete_evaluation_run,
    create_evaluation_predictions_batch,
    get_evaluation_predictions,
    get_evaluation_prediction_detail,
    get_supabase,
    get_user_preferences,
    update_user_preferences,
)
from backend.evaluation_engine import (
    match_predictions_to_gt,
    aggregate_metrics,
    compare_runs,
)
from backend.r2_storage import R2Client
from app_state import AuthState


# =============================================================================
# RUN-LEVEL COLORS (Design Decision: each run gets one color)
# =============================================================================

RUN_COLORS = {
    "gt": "#22C55E",        # Green — Ground Truth
    "run_a": "#A855F7",     # Purple — Run A
    "run_b": "##A0785A",    # Sienna — Run B
    "run_c": "#3B82F6",     # Blue — Run C
}


# =============================================================================
# TYPED DICTS — Required for Reflex foreach
# =============================================================================


class SelectOption(TypedDict):
    """Generic select option for dropdowns."""
    id: str
    name: str


class EvalRunRow(TypedDict):
    """Flattened evaluation run for table display."""
    id: str
    model_name: str
    dataset_name: str
    status: str
    f1_display: str       # Pre-formatted: "82%" or "—"
    total_images: int
    created_at: str


class EvalPredRow(TypedDict):
    """Flattened per-image prediction for drill-down."""
    id: str
    image_filename: str
    tp_count: int
    fp_count: int
    fn_count: int
    fn_missed_count: int     # Unmatched GT (no detection)
    fn_misclass_count: int   # Detected but wrong class


class PerClassRow(TypedDict):
    """Flattened per-class metrics row."""
    class_name: str
    precision: str    # Pre-formatted: "92%"
    recall: str
    f1: str
    tp: int
    fp: int
    fn: int
    f1_raw: float     # For sorting


class ComparisonDelta(TypedDict):
    """Class improvement/degradation entry."""
    class_name: str
    delta_display: str    # "+12%" or "-5%"
    is_improved: bool


class MatchBreakdownRow(TypedDict):
    """Per-annotation match result for detail view."""
    match_type: str       # "tp", "fp", "fn"
    class_name: str
    detail: str           # e.g. "IoU 0.87" or "missed" or "spurious 72%"


# =============================================================================
# HELPERS
# =============================================================================


def _run_to_row(run: dict) -> EvalRunRow:
    """Convert raw Supabase evaluation_run dict to typed row."""
    om = run.get("overall_metrics") or {}
    f1_val = om.get("f1", 0)
    f1_display = f"{int(f1_val * 100)}%" if f1_val > 0 else "—"
    return EvalRunRow(
        id=run.get("id", ""),
        model_name=run.get("model_name", ""),
        dataset_name=run.get("dataset_name", ""),
        status=run.get("status", "pending"),
        f1_display=f1_display,
        total_images=run.get("total_images", 0),
        created_at=run.get("created_at", ""),
    )


def _pred_to_row(pred: dict) -> EvalPredRow:
    """Convert raw prediction dict to typed row."""
    return EvalPredRow(
        id=pred.get("id", ""),
        image_filename=pred.get("image_filename", ""),
        tp_count=pred.get("tp_count", 0),
        fp_count=pred.get("fp_count", 0),
        fn_count=pred.get("fn_count", 0),
    )


class EvaluationState(rx.State):
    """State for the model evaluation module."""

    # ── Data (TYPED for foreach) ──────────────────────────────────────
    evaluation_runs: list[EvalRunRow] = []
    selected_run_ids: list[str] = []  # Up to 3 for comparison
    active_run: dict = {}             # Full metrics of currently viewed run
    active_predictions: list[EvalPredRow] = []
    per_class_data: list[PerClassRow] = []   # Computed from active_run
    comparison_deltas: list[ComparisonDelta] = []  # Flattened comparison

    # ── Model & dataset selectors (TYPED) ─────────────────────────────
    model_options: list[SelectOption] = []
    dataset_options: list[SelectOption] = []
    project_options: list[SelectOption] = []

    selected_project_id: str = ""
    selected_model_id: str = ""
    selected_dataset_id: str = ""
    eval_confidence: float = 0.05   # Low floor: capture all detections
    eval_iou: float = 0.3

    # ── Hybrid inference settings (auto-detected on model select) ──────
    eval_is_hybrid: bool = False
    eval_classifier_r2_path: str = ""
    eval_classifier_classes: list[str] = []
    eval_sam3_prompts_input: str = "animal"
    eval_classifier_confidence: float = 0.5
    eval_sam3_confidence: float = 0.5
    eval_sam3_imgsz: str = "1918"

    # ── Analysis-time confidence (dynamic filter) ─────────────────────
    analysis_confidence: float = 0.25  # Adjustable on results dashboard
    _raw_predictions_cache: list[dict] = []  # Internal: raw DB predictions

    # ── Recomputed overall metrics (set by _recompute_metrics) ────────
    computed_precision: float = 0.0
    computed_recall: float = 0.0
    computed_f1: float = 0.0
    computed_images: int = 0

    # ── UI state ──────────────────────────────────────────────────────
    is_loading: bool = False
    is_running_eval: bool = False
    eval_progress_current: int = 0
    eval_progress_total: int = 0
    eval_status: str = ""
    eval_error: str = ""
    show_new_eval_modal: bool = False
    drill_down_class: str = ""
    drill_down_type: str = ""
    predictions_page: int = 0

    # ── Drill-down image detail ───────────────────────────────────────
    detail_image_filename: str = ""
    detail_tp: int = 0
    detail_fp: int = 0
    detail_fn: int = 0
    detail_image_url: str = ""
    show_detail_modal: bool = False

    # ── Detail bounding boxes (for CSS overlay) ───────────────────────
    detail_gt_boxes: list[dict] = []    # [{x1, y1, x2, y2, class_name}]
    detail_pred_boxes: list[dict] = []  # [{x1, y1, x2, y2, class_name, confidence}]
    detail_match_breakdown: list[MatchBreakdownRow] = []
    detail_gt_count: int = 0
    detail_pred_count: int = 0

    # ── Delete confirmation ───────────────────────────────────────────
    delete_run_id: str = ""
    show_delete_modal: bool = False

    # =================================================================
    # COMPUTED VARS
    # =================================================================

    @rx.var
    def can_start_eval(self) -> bool:
        return bool(self.selected_model_id and self.selected_dataset_id and not self.is_running_eval)

    @rx.var
    def has_active_run(self) -> bool:
        return bool(self.active_run.get("id"))

    @rx.var
    def active_model_name(self) -> str:
        return self.active_run.get("model_name", "")

    @rx.var
    def active_dataset_name(self) -> str:
        return self.active_run.get("dataset_name", "")

    @rx.var
    def active_total_images(self) -> str:
        return str(self.computed_images)

    @rx.var
    def overall_precision(self) -> str:
        return f"{int(self.computed_precision * 100)}%"

    @rx.var
    def overall_recall(self) -> str:
        return f"{int(self.computed_recall * 100)}%"

    @rx.var
    def overall_f1(self) -> str:
        return f"{int(self.computed_f1 * 100)}%"

    @rx.var
    def has_comparison(self) -> bool:
        return len(self.selected_run_ids) >= 2 and len(self.comparison_deltas) > 0

    @rx.var
    def show_compare_button(self) -> bool:
        return len(self.selected_run_ids) >= 2

    # =================================================================
    # LOADING
    # =================================================================

    async def load_evaluation_data(self):
        """Load evaluation runs and available models/datasets on page load."""
        self.is_loading = True
        yield

        try:
            auth = await self.get_state(AuthState)
            if not auth.user_id:
                return

            project_ids = get_accessible_project_ids(auth.user_id)
            if not project_ids:
                self.is_loading = False
                return

            # Load projects for selector
            supabase = get_supabase()
            projects_result = (
                supabase.table("projects")
                .select("id, name")
                .in_("id", project_ids)
                .order("last_accessed_at", desc=True)
                .execute()
            )
            self.project_options = [
                SelectOption(id=p["id"], name=p["name"])
                for p in (projects_result.data or [])
            ]

            # Auto-select first project
            if self.project_options and not self.selected_project_id:
                self.selected_project_id = self.project_options[0]["id"]

            # Load saved preferences
            prefs = get_user_preferences(auth.user_id)
            eval_prefs = prefs.get("evaluation", {})
            if "confidence_threshold" in eval_prefs:
                self.eval_confidence = eval_prefs["confidence_threshold"]
            if "iou_threshold" in eval_prefs:
                self.eval_iou = eval_prefs["iou_threshold"]
            if "analysis_confidence" in eval_prefs:
                self.analysis_confidence = eval_prefs["analysis_confidence"]

            # Load models, datasets, and runs for selected project
            if self.selected_project_id:
                await self._load_project_data()
                raw_runs = get_evaluation_runs(self.selected_project_id)
                self.evaluation_runs = [_run_to_row(r) for r in raw_runs]

        except Exception as e:
            print(f"[Evaluation] Error loading data: {e}")
        finally:
            self.is_loading = False

    async def _load_project_data(self):
        """Load models and datasets for the currently selected project."""
        if not self.selected_project_id:
            return

        supabase = get_supabase()
        # Models in this table are promoted to playground (weights on Modal Volume)
        models_result = (
            supabase.table("models")
            .select("id, name, model_type, created_at, training_runs(alias, model_type, config)")
            .eq("project_id", self.selected_project_id)
            .order("created_at", desc=True)
            .execute()
        )
        raw_models = models_result.data or []

        options = []
        for m in raw_models:
            tr = m.get("training_runs", {}) or {}
            alias = tr.get("alias", "")
            name = m.get("name", "")
            weights_type = ""
            if "best" in name.lower():
                weights_type = "best"
            elif "last" in name.lower():
                weights_type = "last"
            display = alias if alias else name
            if weights_type:
                display = f"{display} ({weights_type})"
            options.append(SelectOption(id=m["id"], name=display))

        self.model_options = options

        # Only show evaluation datasets (uploaded via bulk script), not training ones
        eval_datasets = (
            supabase.table("datasets")
            .select("id, name")
            .eq("project_id", self.selected_project_id)
            .eq("usage_tag", "validation")
            .order("created_at", desc=True)
            .execute()
        )
        self.dataset_options = [
            SelectOption(id=d["id"], name=d["name"])
            for d in (eval_datasets.data or [])
        ]
        # Auto-select first evaluation dataset
        if self.dataset_options and not self.selected_dataset_id:
            self.selected_dataset_id = self.dataset_options[0]["id"]

    async def select_project(self, project_id: str):
        """Switch project context."""
        self.selected_project_id = project_id
        self.selected_model_id = ""
        self.selected_dataset_id = ""
        self.selected_run_ids = []
        self.active_run = {}
        self.per_class_data = []
        self.comparison_deltas = []

        await self._load_project_data()
        raw_runs = get_evaluation_runs(project_id)
        self.evaluation_runs = [_run_to_row(r) for r in raw_runs]

    def select_model(self, model_id: str):
        """Select a model and auto-detect hybrid mode (classifier → SAM3 + classifier)."""
        self.selected_model_id = model_id

        # Reset hybrid state
        self.eval_is_hybrid = False
        self.eval_classifier_r2_path = ""
        self.eval_classifier_classes = []

        # Query training run to detect model type
        try:
            supabase = get_supabase()
            model_result = (
                supabase.table("models")
                .select("training_run_id")
                .eq("id", model_id)
                .single()
                .execute()
            )
            training_run_id = (model_result.data or {}).get("training_run_id")
            if training_run_id:
                run_result = (
                    supabase.table("training_runs")
                    .select("model_type, classes_snapshot, artifacts_r2_prefix, config")
                    .eq("id", training_run_id)
                    .single()
                    .execute()
                )
                if run_result.data:
                    run_model_type = run_result.data.get("model_type", "detection")
                    if run_model_type == "classification":
                        self.eval_is_hybrid = True
                        self.eval_classifier_classes = run_result.data.get("classes_snapshot", []) or []
                        prefix = run_result.data.get("artifacts_r2_prefix", "")
                        if prefix:
                            run_config = run_result.data.get("config", {}) or {}
                            ext = ".pth" if run_config.get("classifier_backbone") == "convnext" else ".pt"
                            self.eval_classifier_r2_path = f"{prefix}/best{ext}"
                        print(f"[Evaluation] Hybrid mode: classifier={self.eval_classifier_classes}")
        except Exception as e:
            print(f"[Evaluation] Warning: Could not detect model type: {e}")

    def set_eval_sam3_prompts(self, value: str):
        self.eval_sam3_prompts_input = value

    def set_eval_classifier_confidence(self, value: str):
        try:
            v = float(value)
            if 0.0 <= v <= 1.0:
                self.eval_classifier_confidence = round(v, 2)
        except ValueError:
            pass

    def set_eval_sam3_imgsz(self, value: str):
        self.eval_sam3_imgsz = value

    def set_eval_sam3_confidence(self, value: str):
        try:
            v = float(value)
            if 0.0 <= v <= 1.0:
                self.eval_sam3_confidence = round(v, 2)
        except ValueError:
            pass

    def increment_eval_sam3_conf(self):
        self.eval_sam3_confidence = min(1.0, round(self.eval_sam3_confidence + 0.05, 2))

    def decrement_eval_sam3_conf(self):
        self.eval_sam3_confidence = max(0.0, round(self.eval_sam3_confidence - 0.05, 2))

    def increment_eval_classifier_conf(self):
        self.eval_classifier_confidence = min(1.0, round(self.eval_classifier_confidence + 0.05, 2))

    def decrement_eval_classifier_conf(self):
        self.eval_classifier_confidence = max(0.0, round(self.eval_classifier_confidence - 0.05, 2))

    def select_dataset(self, dataset_id: str):
        self.selected_dataset_id = dataset_id

    async def set_eval_confidence(self, value: str):
        try:
            v = float(value)
            if 0.05 <= v <= 1.0:
                self.eval_confidence = round(v, 2)
                auth = await self.get_state(AuthState)
                if auth.user_id:
                    update_user_preferences(auth.user_id, "evaluation", {"confidence_threshold": self.eval_confidence})
        except (ValueError, TypeError):
            pass

    async def set_eval_iou(self, value: str):
        try:
            v = float(value)
            if 0.1 <= v <= 1.0:
                self.eval_iou = round(v, 2)
                auth = await self.get_state(AuthState)
                if auth.user_id:
                    update_user_preferences(auth.user_id, "evaluation", {"iou_threshold": self.eval_iou})
        except (ValueError, TypeError):
            pass

    # =================================================================
    # NEW EVALUATION
    # =================================================================

    def open_new_eval_modal(self):
        self.show_new_eval_modal = True
        self.eval_error = ""

    def close_new_eval_modal(self):
        self.show_new_eval_modal = False
        self.eval_error = ""

    async def start_evaluation(self):
        """Run evaluation: inference on dataset images → compare to GT → store results."""
        if not self.selected_model_id or not self.selected_dataset_id:
            self.eval_error = "Please select a model and a dataset."
            return

        self.is_running_eval = True
        self.eval_error = ""
        self.eval_status = "Preparing evaluation..."
        self.show_new_eval_modal = False
        yield

        try:
            auth = await self.get_state(AuthState)
            if not auth.user_id:
                self.eval_error = "Not authenticated."
                return

            supabase = get_supabase()
            model_result = (
                supabase.table("models")
                .select("id, name, weights_path, model_type, project_id, training_runs(alias, classes_snapshot, config)")
                .eq("id", self.selected_model_id)
                .single()
                .execute()
            )
            if not model_result.data:
                self.eval_error = "Model not found."
                return
            model = model_result.data
            tr = model.get("training_runs", {}) or {}
            model_name = tr.get("alias") or model["name"]

            # Use PROJECT classes for resolving GT class_ids (NOT training run classes)
            # GT annotations use class_id indexed by project class order
            project_result = (
                supabase.table("projects")
                .select("classes")
                .eq("id", self.selected_project_id)
                .single()
                .execute()
            )
            classes = (project_result.data or {}).get("classes", []) or []
            print(f"[Evaluation] Project classes for GT resolution: {classes}")

            dataset_result = (
                supabase.table("datasets")
                .select("id, name, project_id")
                .eq("id", self.selected_dataset_id)
                .single()
                .execute()
            )
            if not dataset_result.data:
                self.eval_error = "Dataset not found."
                return
            dataset = dataset_result.data

            self.eval_status = "Loading ground truth images..."
            yield
            images = get_dataset_images(self.selected_dataset_id)
            labeled_images = [img for img in images if img.get("annotations")]

            if not labeled_images:
                self.eval_error = "No labeled images found in this dataset."
                return

            self.eval_progress_total = len(labeled_images)
            self.eval_progress_current = 0

            run = create_evaluation_run(
                project_id=self.selected_project_id,
                user_id=auth.user_id,
                model_id=self.selected_model_id,
                model_name=model_name,
                dataset_id=self.selected_dataset_id,
                dataset_name=dataset["name"],
                classes_snapshot=classes,
                confidence_threshold=self.eval_confidence,
                iou_threshold=self.eval_iou,
                total_images=len(labeled_images),
            )
            if not run:
                self.eval_error = "Failed to create evaluation run."
                return

            run_id = run["id"]
            update_evaluation_run(run_id, status="running", started_at=datetime.now(timezone.utc).isoformat())

            # ── Batch inference (single Modal call) ────────────────────
            self.eval_status = "Generating image URLs..."
            yield

            r2_client = R2Client()
            image_urls = [
                r2_client.generate_presigned_url(img["r2_path"])
                for img in labeled_images
            ]

            self.eval_status = f"Running batch inference on {len(image_urls)} images..."
            yield

            if self.eval_is_hybrid:
                # Hybrid dispatch: SAM3 + classifier (same path as playground)
                from backend.job_router import dispatch_hybrid_inference_batch

                sam3_prompts = [p.strip() for p in self.eval_sam3_prompts_input.split(",") if p.strip()]
                prompt_class_map = {p: self.eval_classifier_classes for p in sam3_prompts}

                batch_results = dispatch_hybrid_inference_batch(
                    project_id=self.selected_project_id,
                    image_urls=image_urls,
                    sam3_prompts=sam3_prompts,
                    classifier_r2_path=self.eval_classifier_r2_path,
                    classifier_classes=self.eval_classifier_classes,
                    prompt_class_map=prompt_class_map,
                    confidence_threshold=self.eval_sam3_confidence,
                    classifier_confidence=self.eval_classifier_confidence,
                    sam3_imgsz=int(self.eval_sam3_imgsz),
                )
            else:
                # YOLO detection dispatch
                from backend.inference_router import dispatch_inference, InferenceConfig
                config = InferenceConfig(
                    model_type="yolo-detect",
                    input_type="batch",
                    model_name_or_id=model["id"],
                )
                batch_results = dispatch_inference(
                    config,
                    image_urls=image_urls,
                    confidence=self.eval_classifier_confidence,
                )

            # ── Match predictions to GT per image ─────────────────────
            self.eval_status = "Matching predictions to ground truth..."
            yield

            all_image_results = []
            prediction_records = []
            db_batch_size = 50

            for idx, image in enumerate(labeled_images):
                try:
                    gt_annotations = image.get("annotations", [])
                    if isinstance(gt_annotations, str):
                        import json
                        gt_annotations = json.loads(gt_annotations)

                    # Get predictions for this image from batch results
                    img_result = batch_results[idx] if idx < len(batch_results) else {}
                    predictions = img_result.get("predictions", [])

                    for pred in predictions:
                        pred["confidence"] = int(pred.get("confidence", 0) * 100)

                    result = match_predictions_to_gt(
                        gt_annotations=gt_annotations,
                        predictions=predictions,
                        iou_threshold=self.eval_iou,
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

                    if len(prediction_records) >= db_batch_size:
                        create_evaluation_predictions_batch(prediction_records)
                        prediction_records = []

                except Exception as img_error:
                    print(f"[Evaluation] Error matching image {image['filename']}: {img_error}")
                    all_image_results.append({"tp": 0, "fp": 0, "fn": 0, "matches": [], "tp_details": [], "fp_details": [], "fn_details": []})

                self.eval_progress_current = idx + 1

                if (idx + 1) % 50 == 0:
                    update_evaluation_run(run_id, processed_images=idx + 1)
                    yield

            update_evaluation_run(run_id, processed_images=len(labeled_images))

            if prediction_records:
                create_evaluation_predictions_batch(prediction_records)

            self.eval_status = "Computing metrics..."
            yield

            metrics = aggregate_metrics(all_image_results, classes)

            update_evaluation_run(
                run_id,
                status="completed",
                overall_metrics=metrics["overall"],
                per_class_metrics=metrics["per_class"],
                confusion_matrix=metrics["confusion_matrix"],
                completed_at=datetime.now(timezone.utc).isoformat(),
            )

            raw_runs = get_evaluation_runs(self.selected_project_id)
            self.evaluation_runs = [_run_to_row(r) for r in raw_runs]
            self.eval_status = "Evaluation complete!"

            await self.view_run(run_id)

        except Exception as e:
            self.eval_error = f"Evaluation failed: {str(e)}"
            print(f"[Evaluation] Error: {e}")
            import traceback
            traceback.print_exc()
        finally:
            self.is_running_eval = False
            yield

    async def _run_single_inference(
        self, model: dict, image_r2_path: str, confidence: float, tr_config: dict
    ) -> list[dict]:
        """Run inference on a single image via the existing yolo-inference app.

        Uses the same Modal dispatch as the playground (promoted models on Volume).
        """
        import modal

        model_id = model.get("id", "")

        # Generate presigned URL (same pattern as playground)
        r2_client = R2Client()
        image_url = r2_client.generate_presigned_url(image_r2_path)

        cls = modal.Cls.from_name("yolo-inference", "YOLOInference")
        result = cls().predict_image.remote(
            model_type="custom",
            model_name_or_id=model_id,
            image_url=image_url,
            confidence=confidence,
        )

        return result.get("predictions", []) if result else []

    # =================================================================
    # RUN VIEWING & COMPARISON
    # =================================================================

    async def view_run(self, run_id: str):
        """Load full details for a single run and recompute metrics at current confidence."""
        run = get_evaluation_run(run_id)
        if run:
            self.active_run = run
            self.predictions_page = 0
            self.drill_down_class = ""
            self.drill_down_type = ""

            # Load ALL raw predictions (not paginated) for dynamic recompute
            supabase = get_supabase()
            all_preds = (
                supabase.table("evaluation_predictions")
                .select("id, image_filename, image_r2_path, ground_truth, predictions, image_id")
                .eq("evaluation_run_id", run_id)
                .execute()
            )
            self._raw_predictions_cache = all_preds.data or []
            self.computed_images = len(self._raw_predictions_cache)

            # Recompute metrics at current analysis confidence
            self._recompute_metrics()

    def _recompute_metrics(self):
        """Re-run matching + aggregation on cached predictions at current analysis_confidence."""
        if not self._raw_predictions_cache:
            return

        classes = self.active_run.get("classes_snapshot", []) or []
        iou = self.active_run.get("iou_threshold", 0.3)
        conf = self.analysis_confidence

        all_image_results = []
        pred_rows = []

        for raw in self._raw_predictions_cache:
            gt = raw.get("ground_truth", []) or []
            preds = raw.get("predictions", []) or []

            # Re-match with confidence filter
            # Note: predictions store confidence as int 0-100 (rounded at eval time)
            result = match_predictions_to_gt(
                gt_annotations=gt,
                predictions=preds,
                iou_threshold=iou,
                classes=classes,
                confidence_threshold=conf * 100,  # Convert 0-1 → 0-100 scale
            )
            all_image_results.append(result)

            # Build typed pred row — filter by drill-down class if active
            if self.drill_down_class:
                cls = self.drill_down_class
                img_tp = sum(1 for m in result.get("tp_details", []) if m.get("gt_class") == cls)
                # FP: spurious predictions of this class + misclassified as this class
                img_fp = sum(
                    1 for m in result.get("fp_details", [])
                    if m.get("pred_class") == cls
                )
                # FN missed: unmatched GT of this class (no detection at all)
                img_fn_missed = sum(1 for m in result.get("fn_details", []) if m.get("gt_class") == cls)
                # FN misclassified: detected but classified as wrong species
                img_fn_misclass = sum(
                    1 for m in result.get("fp_details", [])
                    if m.get("type") != "spurious" and m.get("gt_class") == cls
                )
                img_fn = img_fn_missed + img_fn_misclass
            else:
                img_tp = result["tp"]
                img_fp = result["fp"]
                img_fn = result["fn"]
                # Split FN for unfiltered view too
                img_fn_missed = len(result.get("fn_details", []))
                img_fn_misclass = sum(
                    1 for m in result.get("fp_details", [])
                    if m.get("type") != "spurious"
                )

            pred_rows.append(EvalPredRow(
                id=raw.get("id", ""),
                image_filename=raw.get("image_filename", ""),
                tp_count=img_tp,
                fp_count=img_fp,
                fn_count=img_fn,
                fn_missed_count=img_fn_missed,
                fn_misclass_count=img_fn_misclass,
            ))

        # Aggregate metrics
        if classes and all_image_results:
            metrics = aggregate_metrics(all_image_results, classes)
            overall = metrics.get("overall", {})
            self.computed_precision = overall.get("precision", 0)
            self.computed_recall = overall.get("recall", 0)
            self.computed_f1 = overall.get("f1", 0)

            # Build per-class table
            pcm = metrics.get("per_class", {})
            rows = []
            for cls, m in pcm.items():
                rows.append(PerClassRow(
                    class_name=cls,
                    precision=f"{int(m.get('precision', 0) * 100)}%",
                    recall=f"{int(m.get('recall', 0) * 100)}%",
                    f1=f"{int(m.get('f1', 0) * 100)}%",
                    tp=m.get("tp", 0),
                    fp=m.get("fp", 0),
                    fn=m.get("fn", 0),
                    f1_raw=m.get("f1", 0),
                ))
            rows.sort(key=lambda x: x["f1_raw"], reverse=True)
            self.per_class_data = rows
        else:
            self.computed_precision = 0
            self.computed_recall = 0
            self.computed_f1 = 0
            self.per_class_data = []

        # Apply match-type filter (tp/fp/fn/fn_missed/fn_misclass) to pred_rows
        if self.drill_down_type == "tp":
            pred_rows = [r for r in pred_rows if r["tp_count"] > 0]
        elif self.drill_down_type == "fp":
            pred_rows = [r for r in pred_rows if r["fp_count"] > 0]
        elif self.drill_down_type == "fn":
            pred_rows = [r for r in pred_rows if r["fn_count"] > 0]
        elif self.drill_down_type == "fn_missed":
            pred_rows = [r for r in pred_rows if r["fn_missed_count"] > 0]
        elif self.drill_down_type == "fn_misclass":
            pred_rows = [r for r in pred_rows if r["fn_misclass_count"] > 0]

        # Also filter out images with zero relevance when a class filter is active
        if self.drill_down_class:
            pred_rows = [r for r in pred_rows if r["tp_count"] > 0 or r["fp_count"] > 0 or r["fn_count"] > 0]

        # Update predictions list (paginated view)
        start = self.predictions_page * 50
        self.active_predictions = pred_rows[start:start + 50]

    # =================================================================
    # ANALYSIS CONFIDENCE (DYNAMIC FILTER)
    # =================================================================

    async def set_analysis_confidence_input(self, value: str):
        """Handle text input blur for analysis confidence."""
        try:
            v = float(value)
            if 0.0 <= v <= 1.0:
                self.analysis_confidence = round(v, 2)
                self._recompute_metrics()
                auth = await self.get_state(AuthState)
                if auth.user_id:
                    update_user_preferences(auth.user_id, "evaluation", {"analysis_confidence": self.analysis_confidence})
        except (ValueError, TypeError):
            pass

    def increment_analysis_confidence(self):
        if self.analysis_confidence < 0.95:
            self.analysis_confidence = round(self.analysis_confidence + 0.05, 2)
            self._recompute_metrics()

    def decrement_analysis_confidence(self):
        if self.analysis_confidence > 0.0:
            self.analysis_confidence = round(self.analysis_confidence - 0.05, 2)
            self._recompute_metrics()

    def toggle_run_selection(self, run_id: str):
        if run_id in self.selected_run_ids:
            self.selected_run_ids = [r for r in self.selected_run_ids if r != run_id]
        elif len(self.selected_run_ids) < 3:
            self.selected_run_ids = self.selected_run_ids + [run_id]

    async def compute_comparison(self):
        """Compute comparison between selected runs."""
        if len(self.selected_run_ids) < 2:
            self.comparison_deltas = []
            return

        runs = []
        for rid in self.selected_run_ids:
            run = get_evaluation_run(rid)
            if run:
                runs.append(run)

        if len(runs) >= 2:
            comp = compare_runs(runs)
            # Flatten to typed list
            deltas = []
            for item in comp.get("improved_classes", []):
                deltas.append(ComparisonDelta(
                    class_name=item["class"],
                    delta_display=f"+{int(item['delta'] * 100)}%",
                    is_improved=True,
                ))
            for item in comp.get("degraded_classes", []):
                deltas.append(ComparisonDelta(
                    class_name=item["class"],
                    delta_display=f"{int(item['delta'] * 100)}%",
                    is_improved=False,
                ))
            self.comparison_deltas = deltas

    # =================================================================
    # DRILL-DOWN
    # =================================================================

    async def set_drill_down_class(self, cls: str):
        self.drill_down_class = cls
        self.predictions_page = 0
        self._recompute_metrics()

    async def set_drill_down_type(self, match_type: str):
        self.drill_down_type = match_type
        self.predictions_page = 0
        self._recompute_metrics()

    async def load_predictions_page(self):
        if not self.active_run.get("id"):
            return
        raw = get_evaluation_predictions(
            run_id=self.active_run["id"],
            page=self.predictions_page,
            match_type=self.drill_down_type or None,
        )
        self.active_predictions = [_pred_to_row(p) for p in raw]

    async def next_predictions_page(self):
        self.predictions_page += 1
        if self.drill_down_class or self.drill_down_type:
            self._recompute_metrics()
        else:
            await self.load_predictions_page()

    async def prev_predictions_page(self):
        if self.predictions_page > 0:
            self.predictions_page -= 1
            if self.drill_down_class or self.drill_down_type:
                self._recompute_metrics()
            else:
                await self.load_predictions_page()

    async def view_image_detail(self, prediction_id: str):
        """Load single image detail with bounding boxes, recomputed at analysis_confidence."""
        detail = get_evaluation_prediction_detail(prediction_id)
        if detail:
            self.detail_image_filename = detail.get("image_filename", "")
            r2_path = detail.get("image_r2_path", "")
            if r2_path:
                r2_client = R2Client()
                self.detail_image_url = r2_client.generate_presigned_url(r2_path)

            # Get class list — prefer cached active_run, fallback to DB
            run_classes = self.active_run.get("classes_snapshot", []) or []
            if not run_classes:
                run_id = detail.get("evaluation_run_id", "")
                if run_id:
                    try:
                        supabase = get_supabase()
                        run_data = supabase.table("evaluation_runs").select("classes_snapshot").eq("id", run_id).single().execute()
                        run_classes = (run_data.data or {}).get("classes_snapshot", []) or []
                    except Exception:
                        pass

            gt_raw = detail.get("ground_truth", []) or []
            pred_raw = detail.get("predictions", []) or []
            iou = self.active_run.get("iou_threshold", 0.3)

            # Recompute matching at current analysis_confidence
            # Note: predictions stored as int 0-100 (see line 636)
            conf_threshold = self.analysis_confidence * 100
            result = match_predictions_to_gt(
                gt_annotations=gt_raw,
                predictions=pred_raw,
                iou_threshold=iou,
                classes=run_classes,
                confidence_threshold=conf_threshold,
            )
            self.detail_tp = result["tp"]
            self.detail_fp = result["fp"]
            self.detail_fn = result["fn"]

            # Build GT boxes
            self.detail_gt_boxes = []
            for gt in gt_raw:
                x = gt.get("x", 0)
                y = gt.get("y", 0)
                w = gt.get("width", 0)
                h = gt.get("height", 0)
                cid = gt.get("class_id", 0)
                class_name = run_classes[cid] if cid < len(run_classes) else str(cid)
                self.detail_gt_boxes.append({
                    "x1": x, "y1": y, "x2": x + w, "y2": y + h,
                    "class_name": class_name,
                    "confidence": 0,
                })

            # Build prediction boxes — only those above confidence threshold
            self.detail_pred_boxes = []
            for pred in pred_raw:
                if pred.get("confidence", 0) < conf_threshold:
                    continue
                box = pred.get("box", [])
                if box and len(box) == 4:
                    self.detail_pred_boxes.append({
                        "x1": box[0], "y1": box[1], "x2": box[2], "y2": box[3],
                        "class_name": pred.get("class_name", "?"),
                        "confidence": pred.get("confidence", 0),
                    })

            # Counts for header
            self.detail_gt_count = len(gt_raw)
            self.detail_pred_count = len(self.detail_pred_boxes)

            # Build match breakdown for per-annotation detail
            breakdown = []
            for m in result.get("tp_details", []):
                breakdown.append(MatchBreakdownRow(
                    match_type="tp",
                    class_name=m.get("gt_class", "?"),
                    detail=f"IoU {m.get('iou', 0):.2f}",
                ))
            for m in result.get("fp_details", []):
                if m.get("type") == "spurious":
                    breakdown.append(MatchBreakdownRow(
                        match_type="fp",
                        class_name=m.get("pred_class", "?"),
                        detail="spurious",
                    ))
                else:
                    breakdown.append(MatchBreakdownRow(
                        match_type="fp",
                        class_name=f"{m.get('pred_class', '?')} (GT: {m.get('gt_class', '?')})",
                        detail=f"misclassified, IoU {m.get('iou', 0):.2f}",
                    ))
            for m in result.get("fn_details", []):
                breakdown.append(MatchBreakdownRow(
                    match_type="fn",
                    class_name=m.get("gt_class", "?"),
                    detail="missed",
                ))
            self.detail_match_breakdown = breakdown

            self.show_detail_modal = True

    def close_detail_modal(self):
        self.show_detail_modal = False
        self.detail_image_filename = ""
        self.detail_image_url = ""

    # =================================================================
    # DELETE
    # =================================================================

    def open_delete_modal(self, run_id: str):
        self.delete_run_id = run_id
        self.show_delete_modal = True

    def close_delete_modal(self):
        self.delete_run_id = ""
        self.show_delete_modal = False

    async def confirm_delete_run(self):
        if self.delete_run_id:
            db_delete_evaluation_run(self.delete_run_id)
            if self.active_run.get("id") == self.delete_run_id:
                self.active_run = {}
                self.active_predictions = []
                self.per_class_data = []
            self.selected_run_ids = [r for r in self.selected_run_ids if r != self.delete_run_id]
            raw_runs = get_evaluation_runs(self.selected_project_id)
            self.evaluation_runs = [_run_to_row(r) for r in raw_runs]
            self.close_delete_modal()
