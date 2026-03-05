"""
Job Router — Dispatch jobs based on project processing target.

Routes jobs to Modal (cloud) or SSH worker (local) based on project config.

Usage:
    from backend.job_router import dispatch_training_job
    
    # Training
    dispatch_training_job(project_id, run_id, **params)
    dispatch_classification_training_job(project_id, run_id, **params)
    dispatch_sam3_training_job(project_id, run_id, **params)
    
    # Autolabeling  
    dispatch_autolabel_job(dataset_id, job_id, **params)
    
    # Inference
    result = dispatch_hybrid_inference(project_id, **params)
    results = dispatch_hybrid_inference_batch(project_id, **params)
"""

import modal
from typing import Optional

from backend.supabase_client import get_project, get_dataset, get_model
from backend.ssh_client import get_ssh_client_for_machine


# =============================================================================
# TARGET RESOLUTION
# =============================================================================

def get_job_target(project_id: str) -> str:
    """Determine processing target for a project.
    
    Returns:
        'cloud' — project-level target is always cloud now.
        Action-level target selection overrides this.
    """
    return "cloud"


def get_project_id_from_dataset(dataset_id: str) -> Optional[str]:
    """Look up project_id from dataset for autolabel routing."""
    dataset = get_dataset(dataset_id)
    if not dataset:
        return None
    return dataset.get("project_id")


def get_project_id_from_model(model_id: str) -> Optional[str]:
    """Look up project_id from model for inference routing."""
    if not model_id:
        return None
    model = get_model(model_id)
    if not model:
        return None
    return model.get("project_id")


# =============================================================================
# TRAINING DISPATCH
# =============================================================================

def dispatch_training_job(
    project_id: str,
    run_id: str,
    dataset_ids: list[str],
    image_urls: dict[str, str],
    annotations: dict[str, list[dict]],
    classes: list[str],
    config: dict,
    train_split_ratio: float = 0.8,
    val_image_urls: dict[str, str] = None,
    val_annotations: dict[str, list[dict]] = None,
    base_weights_r2_path: str = None,
    parent_run_id: str = None,
    # Action-level target selection
    target: str = None,  # "cloud" or "local", defaults to project lookup
    user_id: str = None,  # Required for local target
    machine_name: str = None,  # Required for local target
):
    """Dispatch detection training to Modal or local GPU.
    
    Cloud: modal.Function.from_name("yolo-training", "train_yolo").spawn()
    Local: SSHWorkerClient.execute_async("remote_train.py", {...})
    
    Args:
        target: Explicit compute target. If None, falls back to project lookup.
        user_id: Required when target="local" (for machine lookup)
        machine_name: Required when target="local"
    """
    # Resolve target: use explicit if provided, otherwise fall back to project
    if target is None:
        target = get_job_target(project_id)
    
    if target == "local":
        if user_id and machine_name:
            client = get_ssh_client_for_machine(user_id, machine_name)
        else:
            client = None
        
        if not client:
            raise RuntimeError(f"No SSH client available for local target")
        
        with client:
            # Execute training job async
            job_ref = client.execute_async("remote_train.py", {
                "run_id": run_id,
                "project_id": project_id,
                "dataset_ids": dataset_ids,
                "image_urls": image_urls,
                "annotations": annotations,
                "classes": classes,
                "config": config,
                "train_split_ratio": train_split_ratio,
                "val_image_urls": val_image_urls,
                "val_annotations": val_annotations,
                "base_weights_r2_path": base_weights_r2_path,
                "parent_run_id": parent_run_id,
            })
            print(f"[JobRouter] Local training started: {job_ref}")
    else:
        # Cloud: Use Modal
        train_yolo = modal.Function.from_name("yolo-training", "train_yolo")
        train_yolo.spawn(
            run_id=run_id,
            project_id=project_id,
            dataset_ids=dataset_ids,
            image_urls=image_urls,
            annotations=annotations,
            classes=classes,
            config=config,
            train_split_ratio=train_split_ratio,
            val_image_urls=val_image_urls,
            val_annotations=val_annotations,
            base_weights_r2_path=base_weights_r2_path,
            parent_run_id=parent_run_id,
        )
        print(f"[JobRouter] Modal training spawned: {run_id}")


def dispatch_classification_training_job(
    project_id: str,
    run_id: str,
    dataset_ids: list[str],
    image_urls: dict[str, str],
    annotations: dict[str, list[dict]],
    classes: list[str],
    config: dict,
    train_split_ratio: float = 0.8,
    val_image_urls: dict[str, str] = None,
    val_annotations: dict[str, list[dict]] = None,
    # Action-level target selection
    target: str = None,  # "cloud" or "local", defaults to project lookup
    user_id: str = None,  # Required for local target
    machine_name: str = None,  # Required for local target
):
    """Dispatch classification training to Modal or local GPU.
    
    Cloud: modal.Function.from_name("yolo-classify-training", "train_classifier").spawn()
    Local: SSHWorkerClient.execute_async("remote_train_classify.py", {...})
    """
    # Resolve target: use explicit if provided, otherwise fall back to project
    if target is None:
        target = get_job_target(project_id)
    
    if target == "local":
        # Use explicit machine if provided, otherwise fall back to project config
        if user_id and machine_name:
            client = get_ssh_client_for_machine(user_id, machine_name)
        else:
            client = None
        
        if not client:
            raise RuntimeError(f"No SSH client available for local target")
        
        with client:
            job_ref = client.execute_async("remote_train_classify.py", {
                "run_id": run_id,
                "project_id": project_id,
                "dataset_ids": dataset_ids,
                "image_urls": image_urls,
                "annotations": annotations,
                "classes": classes,
                "config": config,
                "train_split_ratio": train_split_ratio,
                "val_image_urls": val_image_urls,
                "val_annotations": val_annotations,
            })
            print(f"[JobRouter] Local classification training started: {job_ref}")
    else:
        # Cloud: Use Modal
        train_classifier = modal.Function.from_name("yolo-classify-training", "train_classifier")
        train_classifier.spawn(
            run_id=run_id,
            project_id=project_id,
            dataset_ids=dataset_ids,
            image_urls=image_urls,
            annotations=annotations,
            classes=classes,
            config=config,
            train_split_ratio=train_split_ratio,
            val_image_urls=val_image_urls,
            val_annotations=val_annotations,
        )
        print(f"[JobRouter] Modal classification training spawned: {run_id}")


def dispatch_sam3_training_job(
    project_id: str,
    run_id: str,
    image_r2_urls: dict[str, str],  # {filename: presigned_url}
    train_coco_json: str,  # JSON string of train COCO annotations
    test_coco_json: str,  # JSON string of test COCO annotations
    classes: list[str],
    config: dict,  # {resolution, max_epochs, num_images, lr_scale}
):
    """Dispatch SAM3 fine-tuning to Modal (cloud-only, requires A100).
    
    Cloud: modal.Function.from_name("sam3-training", "train_sam3").spawn()
    
    Note: No local GPU support — SAM3 fine-tuning requires A100.
    """
    train_sam3 = modal.Function.from_name("sam3-training", "train_sam3")
    train_sam3.spawn(
        run_id=run_id,
        project_id=project_id,
        dataset_r2_prefix=f"projects/{project_id}/runs/{run_id}",
        image_r2_urls=image_r2_urls,
        train_coco_json=train_coco_json,
        test_coco_json=test_coco_json,
        classes=classes,
        config=config,
    )
    print(f"[JobRouter] Modal SAM3 training spawned: {run_id}")


# =============================================================================
# AUTOLABEL DISPATCH
# =============================================================================

def dispatch_autolabel_job(
    dataset_id: str,
    job_id: str,
    image_urls: dict[str, str],
    prompt_type: str = "text",
    prompt_value: str = "",
    class_id: int = 0,
    confidence: float = 0.25,
    model_id: str = "",
    prompt_class_map: dict = None,
    # Video keyframe params
    video_mode: bool = False,
    keyframe_meta: dict = None,
    # Action-level target selection
    target: str = None,  # "cloud" or "local", defaults to project lookup
    user_id: str = None,  # Required for local target
    machine_name: str = None,  # Required for local target
    bbox_padding: float = 0.03,  # SAM3 box expansion fraction
    # Mask generation params
    generate_bboxes: bool = True,
    generate_masks: bool = False,
    existing_annotations: dict = None,  # {image_id: [ann_dict]} for bbox-prompt mask shortcut
):
    """Dispatch autolabel job to Modal or local GPU.
    
    Cloud: modal.Function.from_name("yolo-autolabel", "autolabel_images").spawn()
    Local: SSHWorkerClient.execute_async("remote_autolabel.py", {...})
    
    Args:
        target: Explicit compute target. If None, falls back to project lookup.
        user_id: Required when target="local" (for machine lookup)
        machine_name: Required when target="local"
    """
    # Resolve target: use explicit if provided, otherwise fall back to project
    if target is None:
        project_id = get_project_id_from_dataset(dataset_id)
        target = get_job_target(project_id) if project_id else "cloud"
    
    if target == "local":
        if user_id and machine_name:
            client = get_ssh_client_for_machine(user_id, machine_name)
        else:
            client = None
        if not client:
            raise RuntimeError(f"No SSH client available for local target")
        
        # For YOLO mode, need to get model's R2 path from training run
        model_r2_path = ""
        if prompt_type == "yolo" and model_id:
            model = get_model(model_id)
            if model:
                # First check if model has direct r2_path
                model_r2_path = model.get("r2_path", "")
                
                # If not, construct from training run's artifacts_r2_prefix
                if not model_r2_path and model.get("training_run_id"):
                    from backend.supabase_client import get_supabase
                    supabase = get_supabase()
                    run_result = supabase.table("training_runs").select("artifacts_r2_prefix").eq("id", model.get("training_run_id")).single().execute()
                    if run_result.data and run_result.data.get("artifacts_r2_prefix"):
                        prefix = run_result.data["artifacts_r2_prefix"]
                        # Model name indicates best/last weights
                        if "_best" in model.get("name", ""):
                            model_r2_path = f"{prefix}/best.pt"
                        else:
                            model_r2_path = f"{prefix}/last.pt"
                        print(f"[JobRouter] Resolved model R2 path: {model_r2_path}")
        
        with client:
            job_ref = client.execute_async("remote_autolabel.py", {
                "job_id": job_id,
                "dataset_id": dataset_id,
                "image_urls": image_urls,
                "prompt_type": prompt_type,
                "prompt_value": prompt_value,
                "class_id": class_id,
                "confidence": confidence,
                "model_id": model_id,
                "model_r2_path": model_r2_path,  # For local YOLO mode
                "prompt_class_map": prompt_class_map,
                "video_mode": video_mode,
                "keyframe_meta": keyframe_meta,
                "bbox_padding": bbox_padding,
                "generate_bboxes": generate_bboxes,
                "generate_masks": generate_masks,
                "existing_annotations": existing_annotations,
            })
            print(f"[JobRouter] Local autolabel started: {job_ref}")
    else:
        # Cloud: Use Modal
        autolabel_fn = modal.Function.from_name("yolo-autolabel", "autolabel_images")
        
        # Build kwargs based on prompt type
        spawn_kwargs = {
            "job_id": job_id,
            "dataset_id": dataset_id,
            "image_urls": image_urls,
            "prompt_type": prompt_type,
            "confidence": confidence,
        }
        
        if prompt_type == "yolo":
            spawn_kwargs["model_id"] = model_id
        else:
            spawn_kwargs["prompt_value"] = prompt_value
            spawn_kwargs["class_id"] = class_id
            if prompt_class_map:
                spawn_kwargs["prompt_class_map"] = prompt_class_map
            spawn_kwargs["bbox_padding"] = bbox_padding
            spawn_kwargs["generate_bboxes"] = generate_bboxes
            spawn_kwargs["generate_masks"] = generate_masks
            if existing_annotations:
                spawn_kwargs["existing_annotations"] = existing_annotations
        
        # Video keyframe params
        if video_mode:
            spawn_kwargs["video_mode"] = video_mode
            spawn_kwargs["keyframe_meta"] = keyframe_meta
        
        autolabel_fn.spawn(**spawn_kwargs)
        print(f"[JobRouter] Modal autolabel spawned: {job_id}")


# =============================================================================
# INFERENCE DISPATCH
# =============================================================================

def dispatch_hybrid_inference(
    project_id: str,
    image_url: str,
    sam3_prompts: list[str],
    classifier_r2_path: str,
    classifier_classes: list[str],
    prompt_class_map: dict[str, list[str]],
    confidence_threshold: float = 0.25,
    classifier_confidence: float = 0.5,
    # Action-level target selection
    target: str = None,  # "cloud" or "local", defaults to project lookup
    user_id: str = None,  # Required for local target
    machine_name: str = None,  # Required for local target
    sam3_model_path: str = None,  # Volume path for fine-tuned SAM3 model (cloud only)
) -> dict:
    """Dispatch single image hybrid inference to Modal or local GPU.
    
    Returns the inference result dict.
    
    Cloud: modal.Function.from_name("hybrid-inference", "hybrid_inference").remote()
    Local: SSHWorkerClient.execute_job("remote_hybrid_infer.py", {...})
    """
    # Resolve target: use explicit if provided, otherwise fall back to project
    if target is None:
        target = get_job_target(project_id)
    
    if target == "local":
        # Use explicit machine if provided, otherwise fall back to project config
        if user_id and machine_name:
            client = get_ssh_client_for_machine(user_id, machine_name)
        else:
            client = None
        
        if not client:
            raise RuntimeError(f"No SSH client available for local target")
        
        with client:
            result = client.execute_job("remote_hybrid_infer.py", {
                "mode": "single",
                "image_url": image_url,
                "sam3_prompts": sam3_prompts,
                "classifier_r2_path": classifier_r2_path,
                "classifier_classes": classifier_classes,
                "prompt_class_map": prompt_class_map,
                "confidence_threshold": confidence_threshold,
                "classifier_confidence": classifier_confidence,
            })
            return result
    else:
        # Cloud: Use Modal (synchronous call)
        fn = modal.Function.from_name("hybrid-inference", "hybrid_inference")
        kwargs = dict(
            image_url=image_url,
            sam3_prompts=sam3_prompts,
            classifier_r2_path=classifier_r2_path,
            classifier_classes=classifier_classes,
            prompt_class_map=prompt_class_map,
            confidence_threshold=confidence_threshold,
            classifier_confidence=classifier_confidence,
        )
        if sam3_model_path:
            kwargs["sam3_model_path"] = sam3_model_path
        return fn.remote(**kwargs)


def dispatch_hybrid_inference_batch(
    project_id: str,
    image_urls: list[str],
    sam3_prompts: list[str],
    classifier_r2_path: str,
    classifier_classes: list[str],
    prompt_class_map: dict[str, list[str]],
    confidence_threshold: float = 0.25,
    classifier_confidence: float = 0.5,
    # Action-level target selection
    target: str = None,  # "cloud" or "local", defaults to project lookup
    user_id: str = None,  # Required for local target
    machine_name: str = None,  # Required for local target
    sam3_model_path: str = None,  # Volume path for fine-tuned SAM3 model (cloud only)
) -> list[dict]:
    """Dispatch batch hybrid inference to Modal or local GPU.
    
    Returns list of inference results.
    
    Cloud: modal.Function.from_name("hybrid-inference", "hybrid_inference_batch").remote()
    Local: SSHWorkerClient.execute_job("remote_hybrid_infer.py", {...})
    """
    # Resolve target: use explicit if provided, otherwise fall back to project
    if target is None:
        target = get_job_target(project_id)
    
    if target == "local":
        # Use explicit machine if provided, otherwise fall back to project config
        if user_id and machine_name:
            client = get_ssh_client_for_machine(user_id, machine_name)
        else:
            client = None
        
        if not client:
            raise RuntimeError(f"No SSH client available for local target")
        
        with client:
            result = client.execute_job("remote_hybrid_infer.py", {
                "mode": "batch",
                "image_urls": image_urls,
                "sam3_prompts": sam3_prompts,
                "classifier_r2_path": classifier_r2_path,
                "classifier_classes": classifier_classes,
                "prompt_class_map": prompt_class_map,
                "confidence_threshold": confidence_threshold,
                "classifier_confidence": classifier_confidence,
            })
            return result.get("results", [])
    else:
        # Cloud: Use Modal (synchronous call)
        fn = modal.Function.from_name("hybrid-inference", "hybrid_inference_batch")
        kwargs = dict(
            image_urls=image_urls,
            sam3_prompts=sam3_prompts,
            classifier_r2_path=classifier_r2_path,
            classifier_classes=classifier_classes,
            prompt_class_map=prompt_class_map,
            confidence_threshold=confidence_threshold,
            classifier_confidence=classifier_confidence,
        )
        if sam3_model_path:
            kwargs["sam3_model_path"] = sam3_model_path
        return fn.remote(**kwargs)


def dispatch_hybrid_inference_video(
    project_id: str,
    video_url: str,
    sam3_prompts: list[str],
    classifier_r2_path: str,
    classifier_classes: list[str],
    prompt_class_map: dict[str, list[str]],
    confidence_threshold: float = 0.25,
    classifier_confidence: float = 0.5,
    start_time: float = 0.0,
    end_time: float = None,
    frame_skip: int = 1,
    classify_top_k: int = 3,
    sam3_imgsz: int = 640,
    # Action-level target selection
    target: str = None,  # "cloud" or "local", defaults to project lookup
    user_id: str = None,  # Required for local target
    machine_name: str = None,  # Required for local target
    result_id: str = None,  # For progress tracking (Modal writes to Supabase)
    sam3_model_path: str = None,  # Volume path for fine-tuned SAM3 model (cloud only)
) -> dict:
    """Dispatch video hybrid inference to Modal or local GPU.
    
    Returns inference result with frame data.
    
    Cloud: modal.Function.from_name("hybrid-inference", "hybrid_inference_video").spawn()
    Local: SSHWorkerClient.execute_async("remote_hybrid_infer.py", {...})
    
    Both paths return {"async": True, ...} for the state to poll progress.
    """
    # Resolve target: use explicit if provided, otherwise fall back to project
    if target is None:
        target = get_job_target(project_id)
    
    if target == "local":
        # Use explicit machine if provided, otherwise fall back to project config
        if user_id and machine_name:
            client = get_ssh_client_for_machine(user_id, machine_name)
        else:
            client = None
        
        if not client:
            raise RuntimeError(f"No SSH client available for local target")
        
        # Store SSH config BEFORE opening the connection so the state can
        # create a new client for polling later
        ssh_config = {
            "host": client.host,
            "port": client.port,
            "user": client.user,
        }
        
        with client:
            # Use async execution (not blocking execute_job) to avoid
            # pipe deadlocks and enable progress streaming
            job_ref = client.execute_async("remote_hybrid_infer.py", {
                "mode": "video",
                "video_url": video_url,
                "sam3_prompts": sam3_prompts,
                "classifier_r2_path": classifier_r2_path,
                "classifier_classes": classifier_classes,
                "prompt_class_map": prompt_class_map,
                "confidence_threshold": confidence_threshold,
                "classifier_confidence": classifier_confidence,
                "start_time": start_time,
                "end_time": end_time,
                "frame_skip": frame_skip,
                "classify_top_k": classify_top_k,
                "sam3_imgsz": sam3_imgsz,
            })
            
            print(f"[JobRouter] Local video inference started: {job_ref}")
            return {"async": True, "job_ref": job_ref, "ssh_config": ssh_config}
    else:
        # Cloud: Use Modal (async spawn for progress streaming)
        fn = modal.Function.from_name("hybrid-inference", "hybrid_inference_video")
        spawn_kwargs = dict(
            video_url=video_url,
            sam3_prompts=sam3_prompts,
            classifier_r2_path=classifier_r2_path,
            classifier_classes=classifier_classes,
            prompt_class_map=prompt_class_map,
            confidence_threshold=confidence_threshold,
            classifier_confidence=classifier_confidence,
            start_time=start_time,
            end_time=end_time,
            frame_skip=frame_skip,
            classify_top_k=classify_top_k,
            sam3_imgsz=sam3_imgsz,
            result_id=result_id,
        )
        if sam3_model_path:
            spawn_kwargs["sam3_model_path"] = sam3_model_path
        fn.spawn(**spawn_kwargs)
        print(f"[JobRouter] Modal video inference spawned: {result_id}")
        return {"async": True, "modal": True}
