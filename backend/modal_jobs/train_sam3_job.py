"""
Modal Training Job — SAM3 fine-tuning on A100 GPU.

Uses facebookresearch/sam3 training stack with Hydra config management.
Produces fine-tuned checkpoints drop-in compatible with Ultralytics inference.

Usage (from Reflex app):
    fn = modal.Function.from_name("sam3-training", "train_sam3")
    fn.spawn(run_id=..., project_id=..., ...)
"""

import csv
import io
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import textwrap
import threading
import time
from pathlib import Path

import modal

# Modal App configuration
app = modal.App("sam3-training")

# SAM3 weights volume (shared with inference)
sam3_volume = modal.Volume.from_name("sam3-volume", create_if_missing=True)

# Build the container image with SAM3 training dependencies
image = (
    modal.Image.debian_slim(python_version="3.11")
    .apt_install("libgl1-mesa-glx", "libglib2.0-0", "git")
    .pip_install(
        "boto3",
        "supabase",
        "requests",
        "psutil",
        # PyTorch (install before SAM3 to avoid conflicts)
        "torch>=2.1.0",
        "torchvision",
    )
    .run_commands(
        "git clone https://github.com/facebookresearch/sam3.git /opt/sam3",
        # Install ALL extras to cover every import in the SAM3 codebase
        "cd /opt/sam3 && pip install -e '.[train,dev,notebooks]'",
    )
    .env({"PYTHONPATH": "/root:/opt/sam3"})
    .add_local_python_source("backend")
)


def download_file(url: str, dest_path: Path) -> bool:
    """Download a file from a presigned URL."""
    import requests
    
    try:
        response = requests.get(url, timeout=120)
        response.raise_for_status()
        dest_path.parent.mkdir(parents=True, exist_ok=True)
        dest_path.write_bytes(response.content)
        return True
    except Exception as e:
        print(f"Failed to download {url}: {e}")
        return False


class LogCapture:
    """Capture stdout and stderr and stream to Supabase."""

    def __init__(self, run_id: str, flush_interval: int = 2):
        self.run_id = run_id
        self.flush_interval = flush_interval
        self.log_buffer = io.StringIO()
        self.lock = threading.Lock()
        self.stop_event = threading.Event()
        self.thread = None
        self.original_stdout = sys.stdout
        self.original_stderr = sys.stderr

    def __enter__(self):
        sys.stdout = self
        sys.stderr = self
        self.thread = threading.Thread(target=self._flush_loop, daemon=True)
        self.thread.start()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.stop_event.set()
        if self.thread:
            self.thread.join(timeout=1)
        sys.stdout = self.original_stdout
        sys.stderr = self.original_stderr
        self._flush_buffer(timeout=3)

    def write(self, message):
        self.original_stdout.write(message)
        with self.lock:
            self.log_buffer.write(message)

    def flush(self):
        self.original_stdout.flush()

    def _flush_loop(self):
        while not self.stop_event.is_set():
            time.sleep(self.flush_interval)
            self._flush_buffer()

    def _flush_buffer(self, timeout: int = 10):
        from supabase import create_client
        
        try:
            with self.lock:
                content = self.log_buffer.getvalue()
                if not content:
                    return
                self.log_buffer.seek(0)
                self.log_buffer.truncate(0)

            url = os.environ.get("SUPABASE_URL")
            key = os.environ.get("SUPABASE_KEY")
            if not url or not key:
                return
            
            supabase = create_client(url, key)
            res = supabase.table("training_runs").select("logs").eq("id", self.run_id).single().execute()
            current = res.data.get("logs", "") or ""
            new_logs = current + content
            supabase.table("training_runs").update({"logs": new_logs}).eq("id", self.run_id).execute()

        except Exception as e:
            try:
                self.original_stderr.write(f"\n[LogCapture Error] {e}\n")
            except:
                pass


def generate_hydra_config(
    dataset_dir: Path,
    base_weights_path: Path,
    config: dict,
    classes: list[str],
) -> str:
    """
    Generate a Hydra YAML config for SAM3 fine-tuning and place it in SAM3's
    config directory so train.py can discover it by name.
    
    Based on the reference config:
    sam3/train/configs/roboflow_v100/roboflow_v100_full_ft_100_images.yaml
    
    Args:
        dataset_dir: Path to dataset with train/ and test/ splits
        base_weights_path: Path to base SAM3 checkpoint
        config: Training config dict from dashboard
        classes: List of class names
        
    Returns:
        Config name (for -c flag) — NOT a file path
    """
    resolution = config.get("resolution", 1008)
    max_epochs = config.get("max_epochs", 3)
    num_images = config.get("num_images", 10)  # 0 = all
    lr_scale = config.get("lr_scale", 0.1)
    enable_seg = "False"  # Detection-only fine-tuning (seg head still works at inference)
    
    # num_images: 0 means use all, otherwise limit
    num_images_yaml = "null" if num_images == 0 else str(num_images)
    
    log_dir = dataset_dir / "logs"
    train_dir = dataset_dir / "train"
    test_dir = dataset_dir / "test"
    
    # Full Hydra config matching SAM3's expected structure
    config_yaml = textwrap.dedent(f"""\
# @package _global_
# SAM3 Fine-Tuning Config (auto-generated by SAFARI)
defaults:
  - _self_

# ============================================================================
paths:
  roboflow_vl_100_root: {dataset_dir}
  experiment_log_dir: {log_dir}
  bpe_path: /opt/sam3/sam3/assets/bpe_simple_vocab_16e6.txt.gz

# ============================================================================
roboflow_train:
  num_images: {num_images_yaml}
  supercategory: "."

  # Training transforms pipeline
  train_transforms:
    - _target_: sam3.train.transforms.basic_for_api.ComposeAPI
      transforms:
        - _target_: sam3.train.transforms.filter_query_transforms.FlexibleFilterFindGetQueries
          query_filter:
            _target_: sam3.train.transforms.filter_query_transforms.FilterCrowds
        - _target_: sam3.train.transforms.point_sampling.RandomizeInputBbox
          box_noise_std: 0.1
          box_noise_max: 20
        - _target_: sam3.train.transforms.segmentation.DecodeRle
        - _target_: sam3.train.transforms.basic_for_api.RandomResizeAPI
          sizes:
            _target_: sam3.train.transforms.basic.get_random_resize_scales
            size: ${{scratch.resolution}}
            min_size: 480
            rounded: false
          max_size:
            _target_: sam3.train.transforms.basic.get_random_resize_max_size
            size: ${{scratch.resolution}}
          square: true
          consistent_transform: ${{scratch.consistent_transform}}
        - _target_: sam3.train.transforms.basic_for_api.PadToSizeAPI
          size: ${{scratch.resolution}}
          consistent_transform: ${{scratch.consistent_transform}}
        - _target_: sam3.train.transforms.basic_for_api.ToTensorAPI
        - _target_: sam3.train.transforms.filter_query_transforms.FlexibleFilterFindGetQueries
          query_filter:
            _target_: sam3.train.transforms.filter_query_transforms.FilterEmptyTargets
        - _target_: sam3.train.transforms.basic_for_api.NormalizeAPI
          mean: ${{scratch.train_norm_mean}}
          std: ${{scratch.train_norm_std}}
        - _target_: sam3.train.transforms.filter_query_transforms.FlexibleFilterFindGetQueries
          query_filter:
            _target_: sam3.train.transforms.filter_query_transforms.FilterEmptyTargets
    - _target_: sam3.train.transforms.filter_query_transforms.FlexibleFilterFindGetQueries
      query_filter:
        _target_: sam3.train.transforms.filter_query_transforms.FilterFindQueriesWithTooManyOut
        max_num_objects: ${{scratch.max_ann_per_img}}

  # Validation transforms pipeline
  val_transforms:
    - _target_: sam3.train.transforms.basic_for_api.ComposeAPI
      transforms:
        - _target_: sam3.train.transforms.basic_for_api.RandomResizeAPI
          sizes: ${{scratch.resolution}}
          max_size:
            _target_: sam3.train.transforms.basic.get_random_resize_max_size
            size: ${{scratch.resolution}}
          square: true
          consistent_transform: False
        - _target_: sam3.train.transforms.basic_for_api.ToTensorAPI
        - _target_: sam3.train.transforms.basic_for_api.NormalizeAPI
          mean: ${{scratch.train_norm_mean}}
          std: ${{scratch.train_norm_std}}

  # Loss config with segmentation masks
  loss:
    _target_: sam3.train.loss.sam3_loss.Sam3LossWrapper
    matcher: ${{scratch.matcher}}
    o2m_weight: 2.0
    o2m_matcher:
      _target_: sam3.train.matcher.BinaryOneToManyMatcher
      alpha: 0.3
      threshold: 0.4
      topk: 4
    use_o2m_matcher_on_o2m_aux: false
    loss_fns_find:
      - _target_: sam3.train.loss.loss_fns.Boxes
        weight_dict:
          loss_bbox: 5.0
          loss_giou: 2.0
      - _target_: sam3.train.loss.loss_fns.IABCEMdetr
        weak_loss: False
        weight_dict:
          loss_ce: 20.0
          presence_loss: 20.0
        pos_weight: 10.0
        alpha: 0.25
        gamma: 2
        use_presence: True
        pos_focal: false
        pad_n_queries: 200
        pad_scale_pos: 1.0
    loss_fn_semantic_seg: null
    scale_by_find_batch_size: ${{scratch.scale_by_find_batch_size}}

# ============================================================================
scratch:
  enable_segmentation: {enable_seg}
  d_model: 256
  pos_embed:
    _target_: sam3.model.position_encoding.PositionEmbeddingSine
    num_pos_feats: ${{scratch.d_model}}
    normalize: true
    scale: null
    temperature: 10000

  use_presence_eval: True
  original_box_postprocessor:
    _target_: sam3.eval.postprocessors.PostProcessImage
    max_dets_per_img: -1
    use_original_ids: true
    use_original_sizes_box: true
    use_presence: ${{scratch.use_presence_eval}}

  matcher:
    _target_: sam3.train.matcher.BinaryHungarianMatcherV2
    focal: true
    cost_class: 2.0
    cost_bbox: 5.0
    cost_giou: 2.0
    alpha: 0.25
    gamma: 2
    stable: False
  scale_by_find_batch_size: True

  resolution: {resolution}
  consistent_transform: False
  max_ann_per_img: 200

  train_norm_mean: [0.5, 0.5, 0.5]
  train_norm_std: [0.5, 0.5, 0.5]
  val_norm_mean: [0.5, 0.5, 0.5]
  val_norm_std: [0.5, 0.5, 0.5]

  num_train_workers: 0
  num_val_workers: 0
  max_data_epochs: {max_epochs}
  target_epoch_size: 1500
  hybrid_repeats: 1
  context_length: 2
  gather_pred_via_filesys: false

  lr_scale: {lr_scale}
  lr_transformer: ${{times:8e-4,${{scratch.lr_scale}}}}
  lr_vision_backbone: ${{times:2.5e-4,${{scratch.lr_scale}}}}
  lr_language_backbone: ${{times:5e-5,${{scratch.lr_scale}}}}
  lrd_vision_backbone: 0.9
  wd: 0.1
  scheduler_timescale: 20
  scheduler_warmup: 20
  scheduler_cooldown: 20

  val_batch_size: 1
  collate_fn_val:
    _target_: sam3.train.data.collator.collate_fn_api
    _partial_: true
    repeats: ${{scratch.hybrid_repeats}}
    dict_key: roboflow100
    with_seg_masks: ${{scratch.enable_segmentation}}

  gradient_accumulation_steps: 1
  train_batch_size: 1
  collate_fn:
    _target_: sam3.train.data.collator.collate_fn_api
    _partial_: true
    repeats: ${{scratch.hybrid_repeats}}
    dict_key: all
    with_seg_masks: ${{scratch.enable_segmentation}}

# ============================================================================
trainer:
  _target_: sam3.train.trainer.Trainer
  skip_saving_ckpts: false
  empty_gpu_mem_cache_after_eval: True
  skip_first_val: True
  max_epochs: {max_epochs}
  accelerator: cuda
  seed_value: 123
  val_epoch_freq: 1
  mode: train
  gradient_accumulation_steps: ${{scratch.gradient_accumulation_steps}}

  distributed:
    backend: nccl
    find_unused_parameters: True
    gradient_as_bucket_view: True

  loss:
    all: ${{roboflow_train.loss}}
    default:
      _target_: sam3.train.loss.sam3_loss.DummyLoss

  data:
    train:
      _target_: sam3.train.data.torch_dataset.TorchDataset
      dataset:
        _target_: sam3.train.data.sam3_image_dataset.Sam3ImageDataset
        limit_ids: ${{roboflow_train.num_images}}
        transforms: ${{roboflow_train.train_transforms}}
        load_segmentation: ${{scratch.enable_segmentation}}
        max_ann_per_img: 500000
        multiplier: 1
        max_train_queries: 50000
        max_val_queries: 50000
        training: true
        use_caching: False
        img_folder: {train_dir}/
        ann_file: {train_dir}/_annotations.coco.json

      shuffle: True
      batch_size: ${{scratch.train_batch_size}}
      num_workers: ${{scratch.num_train_workers}}
      pin_memory: True
      drop_last: True
      collate_fn: ${{scratch.collate_fn}}

    val:
      _target_: sam3.train.data.torch_dataset.TorchDataset
      dataset:
        _target_: sam3.train.data.sam3_image_dataset.Sam3ImageDataset
        load_segmentation: ${{scratch.enable_segmentation}}
        coco_json_loader:
          _target_: sam3.train.data.coco_json_loaders.COCO_FROM_JSON
          include_negatives: true
          category_chunk_size: 2
          _partial_: true
        img_folder: {test_dir}/
        ann_file: {test_dir}/_annotations.coco.json
        transforms: ${{roboflow_train.val_transforms}}
        max_ann_per_img: 100000
        multiplier: 1
        training: false

      shuffle: False
      batch_size: ${{scratch.val_batch_size}}
      num_workers: ${{scratch.num_val_workers}}
      pin_memory: True
      drop_last: False
      collate_fn: ${{scratch.collate_fn_val}}

  model:
    _target_: sam3.model_builder.build_sam3_image_model
    bpe_path: ${{paths.bpe_path}}
    device: cpus
    eval_mode: false
    enable_segmentation: ${{scratch.enable_segmentation}}
    checkpoint_path: {base_weights_path}
    load_from_HF: false

  meters:
    val:
      roboflow100:
        detection:
          _target_: sam3.eval.coco_writer.PredictionDumper
          iou_type: "bbox"
          dump_dir: ${{launcher.experiment_log_dir}}/dumps
          merge_predictions: True
          postprocessor: ${{scratch.original_box_postprocessor}}
          gather_pred_via_filesys: ${{scratch.gather_pred_via_filesys}}
          maxdets: 100
          pred_file_evaluators:
            - _target_: sam3.eval.coco_eval_offline.CocoEvaluatorOfflineWithPredFileEvaluators
              gt_path: {test_dir}/_annotations.coco.json
              tide: False
              iou_type: "bbox"

  optim:
    amp:
      enabled: True
      amp_dtype: bfloat16

    optimizer:
      _target_: torch.optim.AdamW

    gradient_clip:
      _target_: sam3.train.optim.optimizer.GradientClipper
      max_norm: 0.1
      norm_type: 2

    param_group_modifiers:
      - _target_: sam3.train.optim.optimizer.layer_decay_param_modifier
        _partial_: True
        layer_decay_value: ${{scratch.lrd_vision_backbone}}
        apply_to: 'backbone.vision_backbone.trunk'
        overrides:
          - pattern: '*pos_embed*'
            value: 1.0

    options:
      lr:
        - scheduler:
            _target_: sam3.train.optim.schedulers.InverseSquareRootParamScheduler
            base_lr: ${{scratch.lr_transformer}}
            timescale: ${{scratch.scheduler_timescale}}
            warmup_steps: ${{scratch.scheduler_warmup}}
            cooldown_steps: ${{scratch.scheduler_cooldown}}
        - scheduler:
            _target_: sam3.train.optim.schedulers.InverseSquareRootParamScheduler
            base_lr: ${{scratch.lr_vision_backbone}}
            timescale: ${{scratch.scheduler_timescale}}
            warmup_steps: ${{scratch.scheduler_warmup}}
            cooldown_steps: ${{scratch.scheduler_cooldown}}
          param_names:
            - 'backbone.vision_backbone.*'
        - scheduler:
            _target_: sam3.train.optim.schedulers.InverseSquareRootParamScheduler
            base_lr: ${{scratch.lr_language_backbone}}
            timescale: ${{scratch.scheduler_timescale}}
            warmup_steps: ${{scratch.scheduler_warmup}}
            cooldown_steps: ${{scratch.scheduler_cooldown}}
          param_names:
            - 'backbone.language_backbone.*'

      weight_decay:
        - scheduler:
            _target_: fvcore.common.param_scheduler.ConstantParamScheduler
            value: ${{scratch.wd}}
        - scheduler:
            _target_: fvcore.common.param_scheduler.ConstantParamScheduler
            value: 0.0
          param_names:
            - '*bias*'
          module_cls_names: ['torch.nn.LayerNorm']

  checkpoint:
    save_dir: ${{launcher.experiment_log_dir}}/checkpoints
    save_freq: 0

  logging:
    tensorboard_writer:
      _target_: sam3.train.utils.logger.make_tensorboard_logger
      log_dir: ${{launcher.experiment_log_dir}}/tensorboard
      flush_secs: 120
      should_log: True
    wandb_writer: null
    log_dir: ${{launcher.experiment_log_dir}}/logs
    log_freq: 10

# ============================================================================
launcher:
  num_nodes: 1
  gpus_per_node: 1
  experiment_log_dir: ${{paths.experiment_log_dir}}
  multiprocessing_context: forkserver

submitit:
  account: null
  partition: null
  qos: null
  timeout_hour: 72
  use_cluster: False
  cpus_per_task: 4
  port_range: [10000, 65000]
  constraint: null
""")
    
    # Write config into SAM3's config directory so Hydra can discover it by name
    config_dir = Path("/opt/sam3/sam3/train/configs")
    config_dir.mkdir(parents=True, exist_ok=True)
    config_path = config_dir / "tyto_finetune.yaml"
    config_path.write_text(config_yaml)
    print(f"Generated Hydra config: {config_path}")
    
    # Hydra resolves relative to sam3.train package, so name = configs/tyto_finetune
    return "configs/tyto_finetune"


def parse_training_logs(log_output: str) -> list[dict]:
    """
    Parse SAM3 training stdout to extract per-epoch metrics.
    
    SAM3 logs look like:
    - Training: "Losses/train_all_loss_bbox: 0.012, Losses/train_all_loss_giou: 0.065, ..."
    - Validation: "coco_eval_bbox_AP: 0.921, coco_eval_bbox_AP_50: 1.0, ..."
    - Epoch markers: "Trainer/epoch: 5"
    
    Maps SAM3 metrics to YOLO-compatible column names for dashboard charts.
    """
    epochs: dict[int, dict] = {}
    
    for line in log_output.split("\n"):
        # Skip lines without our meter data
        if "Losses/" not in line and "coco_eval" not in line:
            continue
        
        # Extract epoch number
        epoch_match = re.search(r"'Trainer/epoch':\s*(\d+)", line)
        if not epoch_match:
            continue
        epoch = int(epoch_match.group(1))
        
        if epoch not in epochs:
            epochs[epoch] = {"epoch": epoch}
        
        row = epochs[epoch]
        
        # Extract training losses (map SAM3 → YOLO-compatible names)
        loss_mappings = {
            r"'Losses/train_all_loss_bbox':\s*([\d.eE+-]+)": "train/box_loss",
            r"'Losses/train_all_loss_giou':\s*([\d.eE+-]+)": "train/dfl_loss",  # map giou → dfl slot
            r"'Losses/train_all_loss_ce':\s*([\d.eE+-]+)": "train/cls_loss",
            r"'Losses/train_all_loss':\s*([\d.eE+-]+)": "train/total_loss",
            r"'Losses/train_all_ce_f1':\s*([\d.eE+-]+)": "train/ce_f1",
            r"'Losses/train_all_presence_dec_acc':\s*([\d.eE+-]+)": "train/presence_acc",
        }
        
        for pattern, col_name in loss_mappings.items():
            m = re.search(pattern, line)
            if m:
                row[col_name] = float(m.group(1))
        
        # Extract validation metrics (COCO eval → mAP columns)
        val_mappings = {
            r"coco_eval_bbox_AP':\s*([\d.eE+-]+)": "metrics/mAP50-95(B)",
            r"coco_eval_bbox_AP_50':\s*([\d.eE+-]+)": "metrics/mAP50(B)",
            r"coco_eval_bbox_AP_75':\s*([\d.eE+-]+)": "metrics/mAP75(B)",
            r"coco_eval_bbox_AR_maxDets@100':\s*([\d.eE+-]+)": "metrics/recall(B)",
            r"coco_eval_bbox_AR_maxDets@1':\s*([\d.eE+-]+)": "metrics/precision(B)",
        }
        
        for pattern, col_name in val_mappings.items():
            m = re.search(pattern, line)
            if m:
                val = float(m.group(1))
                if val >= 0:  # Skip -1.0 (not computed)
                    row[col_name] = val
    
    # Sort by epoch and return
    result = [epochs[e] for e in sorted(epochs.keys())]
    print(f"[SAM3] Parsed {len(result)} epochs from training logs")
    if result:
        last = result[-1]
        print(f"[SAM3] Last epoch metrics: {last}")
    return result


def write_results_csv(epochs: list[dict], output_path: Path) -> None:
    """Write parsed epoch metrics to results.csv."""
    if not epochs:
        print("[SAM3] No epoch data to write to results.csv")
        return
    
    # Collect all column names
    all_keys = set()
    for ep in epochs:
        all_keys.update(ep.keys())
    
    # Ensure epoch is first
    columns = ["epoch"] + sorted(k for k in all_keys if k != "epoch")
    
    with open(output_path, "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=columns)
        writer.writeheader()
        for ep in epochs:
            writer.writerow({k: ep.get(k, "") for k in columns})
    
    print(f"[SAM3] Wrote results.csv with {len(epochs)} epochs, columns: {columns}")


@app.function(
    image=image,
    gpu="A100",
    timeout=3600 * 6,  # 6 hours max
    secrets=[
        modal.Secret.from_name("r2-credentials"),
        modal.Secret.from_name("supabase-credentials"),
    ],
    volumes={"/sam3_weights": sam3_volume},
)
def train_sam3(
    run_id: str,
    project_id: str,
    dataset_r2_prefix: str,
    image_r2_urls: dict[str, str],  # {filename: presigned_url} for images
    train_coco_json: str,  # JSON string of train COCO annotations
    test_coco_json: str,  # JSON string of test COCO annotations
    classes: list[str],
    config: dict,  # {resolution, max_epochs, num_images, lr_scale}
) -> dict:
    """
    Main SAM3 fine-tuning function executed on Modal A100 GPU.
    
    Steps:
    1. Download images from presigned URLs
    2. Write COCO JSON annotations
    3. Generate Hydra training config
    4. Run facebookresearch/sam3 training
    5. Upload checkpoint + results to R2
    6. Update Supabase run status
    """
    import boto3
    from botocore.config import Config
    from supabase import create_client
    
    # Initialize clients
    supabase = create_client(
        os.environ["SUPABASE_URL"],
        os.environ["SUPABASE_KEY"],
    )
    
    s3 = boto3.client(
        's3',
        endpoint_url=os.environ['R2_ENDPOINT_URL'],
        aws_access_key_id=os.environ['R2_ACCESS_KEY_ID'],
        aws_secret_access_key=os.environ['R2_SECRET_ACCESS_KEY'],
        config=Config(signature_version='s3v4'),
        region_name='auto',
    )
    bucket = os.environ['R2_BUCKET_NAME']
    
    # Create temp directory for dataset
    dataset_dir = Path(tempfile.mkdtemp(prefix="sam3_training_"))
    train_dir = dataset_dir / "train"
    test_dir = dataset_dir / "test"
    train_dir.mkdir()
    test_dir.mkdir()
    
    with LogCapture(run_id):
        try:
            # Update status to 'running'
            supabase.table("training_runs").update({
                "status": "running",
                "started_at": "now()",
            }).eq("id", run_id).execute()
            
            print(f"Starting SAM3 fine-tuning run {run_id}")
            print(f"Config: {config}")
            print(f"Classes: {classes}")
            print(f"Images to download: {len(image_r2_urls)}")
            
            # === Step 1: Parse COCO JSONs to find which images go where ===
            train_coco = json.loads(train_coco_json)
            test_coco = json.loads(test_coco_json)
            
            train_filenames = {img["file_name"] for img in train_coco["images"]}
            test_filenames = {img["file_name"] for img in test_coco["images"]}
            
            # === Step 2: Download images ===
            print("Downloading images...")
            downloaded = 0
            failed = 0
            for filename, url in image_r2_urls.items():
                if filename in train_filenames:
                    dest = train_dir / filename
                elif filename in test_filenames:
                    dest = test_dir / filename
                else:
                    continue
                
                if download_file(url, dest):
                    downloaded += 1
                else:
                    failed += 1
            
            print(f"Downloaded {downloaded} images ({failed} failed)")
            
            # === Step 3: Write COCO annotations ===
            train_ann_path = train_dir / "_annotations.coco.json"
            test_ann_path = test_dir / "_annotations.coco.json"
            
            with open(train_ann_path, "w") as f:
                json.dump(train_coco, f, indent=2)
            with open(test_ann_path, "w") as f:
                json.dump(test_coco, f, indent=2)
            
            print(f"Train annotations: {len(train_coco['annotations'])} in {len(train_coco['images'])} images")
            print(f"Test annotations: {len(test_coco['annotations'])} in {len(test_coco['images'])} images")
            
            # === Step 4: Locate base SAM3 weights ===
            base_weights = Path("/sam3_weights/sam3.pt")
            if not base_weights.exists():
                raise FileNotFoundError(
                    f"SAM3 base weights not found at {base_weights}. "
                    "Ensure sam3.pt is in the sam3-volume."
                )
            print(f"Base weights: {base_weights} ({base_weights.stat().st_size / 1e9:.1f} GB)")
            
            # === Step 5: Generate training config ===
            config_name = generate_hydra_config(
                dataset_dir=dataset_dir,
                base_weights_path=base_weights,
                config=config,
                classes=classes,
            )
            
            # === Step 6: Run SAM3 training ===
            print("=" * 60)
            print("Starting SAM3 training...")
            print("=" * 60)
            
            train_cmd = [
                "python", "/opt/sam3/sam3/train/train.py",
                "-c", config_name,
                "--use-cluster", "0",  # Run locally, not on SLURM
                "--num-gpus", "1",
            ]
            
            # Capture output for log parsing with real-time early stopping
            training_output = []
            early_stopped = False
            patience = config.get("early_stop_patience", 2)
            min_delta = 0.001  # Minimum improvement to count as progress
            best_map = -1.0
            epochs_without_improvement = 0
            current_epoch = -1
            
            process = subprocess.Popen(
                train_cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                bufsize=1,
            )
            
            for line in process.stdout:
                print(line, end="")  # Stream to LogCapture → Supabase
                training_output.append(line)
                
                # Track epoch transitions
                epoch_match = re.search(r"'Trainer/epoch':\s*(\d+)", line)
                if epoch_match:
                    new_epoch = int(epoch_match.group(1))
                    if new_epoch != current_epoch:
                        current_epoch = new_epoch
                
                # Monitor mAP for early stopping
                map_match = re.search(r"coco_eval_bbox_AP':\s*([\d.eE+-]+)", line)
                if map_match and current_epoch >= 1 and patience > 0:
                    current_map = float(map_match.group(1))
                    if current_map > best_map + min_delta:
                        best_map = current_map
                        epochs_without_improvement = 0
                    else:
                        epochs_without_improvement += 1
                    
                    if epochs_without_improvement >= patience:
                        print(f"\n{'=' * 60}")
                        print(f"[SAM3] Early stopping at epoch {current_epoch}: "
                              f"mAP {current_map:.4f} hasn't improved beyond "
                              f"{best_map:.4f} for {patience} epochs")
                        print(f"{'=' * 60}")
                        early_stopped = True
                        process.terminate()
                        try:
                            process.wait(timeout=30)
                        except subprocess.TimeoutExpired:
                            process.kill()
                            process.wait()
                        break
            
            return_code = process.wait()
            full_output = "".join(training_output)
            
            # Early-stopped processes return -SIGTERM, which is expected
            if return_code != 0 and not early_stopped:
                raise RuntimeError(f"SAM3 training process exited with code {return_code}")
            
            if early_stopped:
                print(f"SAM3 training early-stopped at epoch {current_epoch} (best mAP: {best_map:.4f})")
            else:
                print("SAM3 training completed all epochs successfully!")
            
            # === Step 7: Parse training logs → results.csv ===
            epoch_data = parse_training_logs(full_output)
            results_csv_path = dataset_dir / "results.csv"
            write_results_csv(epoch_data, results_csv_path)
            
            # === Step 8: Find checkpoint ===
            log_dir = dataset_dir / "logs"
            checkpoint_path = None
            
            # Search for checkpoint files in log directory
            for checkpoint_name in ["checkpoint.pt", "model_final.pt", "best_model.pt"]:
                candidates = list(log_dir.rglob(checkpoint_name))
                if candidates:
                    checkpoint_path = candidates[0]
                    break
            
            # Fallback: find any .pt file in logs
            if not checkpoint_path:
                pt_files = list(log_dir.rglob("*.pt"))
                if pt_files:
                    # Pick the largest (most likely the full checkpoint)
                    checkpoint_path = max(pt_files, key=lambda p: p.stat().st_size)
            
            if not checkpoint_path:
                raise FileNotFoundError(
                    f"No checkpoint found in {log_dir}. "
                    "Training may have failed silently."
                )
            
            print(f"Checkpoint found: {checkpoint_path} "
                  f"({checkpoint_path.stat().st_size / 1e6:.1f} MB)")
            
            # === Step 8b: Copy fine-tuned checkpoint to Modal volume (per-run naming) ===
            import shutil
            short_id = run_id[:8]  # First 8 chars of UUID for readability
            volume_run_path = Path(f"/sam3_weights/sam3_finetuned_{short_id}.pt")
            volume_latest_path = Path("/sam3_weights/sam3_finetuned.pt")
            shutil.copy2(checkpoint_path, volume_run_path)
            shutil.copy2(checkpoint_path, volume_latest_path)  # Latest always available
            sam3_volume.commit()
            print(f"Fine-tuned checkpoint saved to Modal volume: {volume_run_path} (also as {volume_latest_path})")
            
            # === Step 8c: Convert to Ultralytics format (merge onto pretrained base) ===
            # Meta training saves {model: state_dict, optimizer: ..., epoch: ...}
            # Ultralytics expects flat dict with detector.* keys (including mask decoder)
            # We merge fine-tuned weights onto pretrained base to preserve mask/prompt encoder
            import torch as _torch
            pretrained_path = Path("/sam3_weights/sam3.pt")
            print(f"Loading pretrained base for merge...")
            base_state = _torch.load(pretrained_path, map_location="cpu", weights_only=False)
            
            for vol_path in [volume_run_path, volume_latest_path]:
                print(f"Converting {vol_path.name} to Ultralytics format (merge onto pretrained)...")
                raw_ckpt = _torch.load(vol_path, map_location="cpu", weights_only=False)
                if isinstance(raw_ckpt, dict) and "model" in raw_ckpt:
                    model_state = raw_ckpt["model"]
                    finetuned = {f"detector.{k}": v for k, v in model_state.items()}
                    merged = dict(base_state)
                    merged.update(finetuned)
                    _torch.save(merged, vol_path)
                    new_size = vol_path.stat().st_size / (1024**3)
                    print(f"  Merged: {len(finetuned)} fine-tuned keys onto {len(base_state)} pretrained keys → {len(merged)} total, {new_size:.1f} GiB")
                else:
                    print(f"  Skipped: already converted or unexpected structure")
            sam3_volume.commit()
            
            # === Step 9: Upload small artifacts to R2 (skip checkpoint — already on Modal volume) ===
            print("Uploading results to R2 (skipping checkpoint — saved to Modal volume)...")
            r2_prefix = f"projects/{project_id}/runs/{run_id}"
            
            artifacts_to_upload = []
            
            if results_csv_path.exists():
                artifacts_to_upload.append((results_csv_path, "results.csv"))
            
            uploaded = []
            for local_path, name in artifacts_to_upload:
                r2_path = f"{r2_prefix}/{name}"
                s3.put_object(
                    Bucket=bucket,
                    Key=r2_path,
                    Body=local_path.read_bytes(),
                )
                uploaded.append(r2_path)
                print(f"  Uploaded: {r2_path}")
            
            # === Step 10: Build metrics summary ===
            modal_checkpoint_path = str(volume_run_path)
            metrics = {
                "num_epochs": len(epoch_data),
                "num_train_images": len(train_coco["images"]),
                "num_test_images": len(test_coco["images"]),
                "num_annotations": len(train_coco["annotations"]) + len(test_coco["annotations"]),
                "checkpoint_size_mb": checkpoint_path.stat().st_size / 1e6,
                "modal_checkpoint_path": modal_checkpoint_path,
                "early_stopped": early_stopped,
            }
            if early_stopped:
                metrics["early_stop_epoch"] = current_epoch
            
            # Add final epoch losses and detection metrics if available
            if epoch_data:
                final = epoch_data[-1]
                for key in ["total_loss", "loss", "bbox_loss", "giou_loss",
                            "mask_loss", "dice_loss", "presence_loss"]:
                    if key in final:
                        metrics[f"final_{key}"] = final[key]

                # Map parsed CSV column names → dashboard metric card keys
                metric_card_mappings = {
                    "metrics/mAP50-95(B)": "mAP50-95",
                    "metrics/mAP50(B)": "mAP50",
                    "metrics/precision(B)": "precision",
                    "metrics/recall(B)": "recall",
                }
                for csv_key, card_key in metric_card_mappings.items():
                    if csv_key in final:
                        metrics[card_key] = final[csv_key]
            
            # === Step 11: Update training run status ===
            print("Updating training run status...")
            supabase.table("training_runs").update({
                "status": "completed",
                "completed_at": "now()",
                "metrics": metrics,
                "artifacts_r2_prefix": r2_prefix,
            }).eq("id", run_id).execute()
            
            print(f"SAM3 training run {run_id} completed successfully!")
            
            return {
                "success": True,
                "run_id": run_id,
                "metrics": metrics,
                "artifacts": uploaded,
            }
            
        except Exception as e:
            error_msg = str(e)
            print(f"SAM3 training failed: {error_msg}")
            
            supabase.table("training_runs").update({
                "status": "failed",
                "completed_at": "now()",
                "error_message": error_msg,
            }).eq("id", run_id).execute()
            
            return {
                "success": False,
                "run_id": run_id,
                "error": error_msg,
            }
            
        finally:
            shutil.rmtree(dataset_dir, ignore_errors=True)

# Minimal image for lightweight operations (no SAM3 deps needed)
lightweight_image = modal.Image.debian_slim(python_version="3.11")


@app.function(
    image=lightweight_image,
    volumes={"/sam3_weights": sam3_volume},
    timeout=60,
)
def delete_sam3_checkpoint(volume_path: str) -> bool:
    """
    Delete a SAM3 checkpoint from the Modal volume.
    
    Args:
        volume_path: Full path like "/sam3_weights/sam3_finetuned_72e923fe.pt"
        
    Returns:
        True if deleted, False if not found
    """
    from pathlib import Path
    
    checkpoint = Path(volume_path)
    
    if checkpoint.exists():
        size_gb = checkpoint.stat().st_size / (1024 ** 3)
        checkpoint.unlink()
        sam3_volume.commit()
        print(f"[SAM3] Deleted checkpoint: {volume_path} ({size_gb:.1f} GiB freed)")
        return True
    else:
        print(f"[SAM3] Checkpoint not found: {volume_path}")
        return False


@app.function(
    image=lightweight_image.pip_install("torch"),
    volumes={"/sam3_weights": sam3_volume},
    timeout=600,
    memory=32768,
)
def convert_sam3_checkpoint_to_ultralytics(filename: str) -> dict:
    """
    Convert a Meta-format SAM3 fine-tuned checkpoint to Ultralytics-compatible format.
    
    Merges fine-tuned weights onto the pretrained sam3.pt base to preserve
    all mask decoder and prompt encoder weights that weren't part of training.
    
    Meta format: {model: {backbone.*, ...}, optimizer: ..., epoch: ..., ...}
    Ultralytics format: {detector.backbone.*, detector.text_model.*, ...}
    
    The conversion:
    1. Loads pretrained sam3.pt as the base (1156 detector keys + 309 tracker keys)
    2. Extracts fine-tuned ckpt["model"] and prefixes with "detector."
    3. Overwrites only the fine-tuned keys in the base, preserving mask decoder etc.
    4. Saves as flat state dict (~3.5 GB instead of ~10 GB)
    
    Args:
        filename: Name of checkpoint in /sam3_weights/ (e.g. "sam3_finetuned_9d6b696c.pt")
    
    Returns:
        Dict with status, sizes, key counts
    """
    import torch
    from pathlib import Path
    
    src = Path(f"/sam3_weights/{filename}")
    pretrained = Path("/sam3_weights/sam3.pt")
    
    if not src.exists():
        return {"success": False, "error": f"File not found: {filename}"}
    if not pretrained.exists():
        return {"success": False, "error": "Pretrained sam3.pt not found on volume"}
    
    original_size = src.stat().st_size / (1024**3)
    print(f"[Convert] Loading {filename} ({original_size:.1f} GiB)...")
    
    ckpt = torch.load(src, map_location="cpu", weights_only=False)
    
    # Determine if this is a Meta-format or already-converted checkpoint
    if isinstance(ckpt, dict) and "model" in ckpt:
        # Meta format: extract model state_dict
        model_state = ckpt["model"]
        finetuned_keys = {f"detector.{k}": v for k, v in model_state.items()}
        print(f"[Convert] Meta format: extracted {len(finetuned_keys)} keys from ckpt['model']")
    elif isinstance(ckpt, dict):
        det_keys = {k: v for k, v in ckpt.items() if k.startswith("detector.")}
        if det_keys:
            # Already has detector. prefix (previous incomplete conversion)
            finetuned_keys = det_keys
            print(f"[Convert] Previously converted: {len(finetuned_keys)} detector keys (re-merging onto pretrained)")
        else:
            return {"success": False, "error": f"Unexpected format: keys={list(ckpt.keys())[:5]}"}
    else:
        return {"success": False, "error": f"Unexpected type: {type(ckpt)}"}
    
    # Load pretrained as base (has all 1465 keys including mask decoder)
    print(f"[Convert] Loading pretrained base sam3.pt...")
    base = torch.load(pretrained, map_location="cpu", weights_only=False)
    base_det_count = len([k for k in base.keys() if k.startswith("detector.")])
    print(f"[Convert] Pretrained base: {len(base)} total keys, {base_det_count} detector keys")
    
    # Merge: pretrained base + fine-tuned overrides
    merged = dict(base)  # Start with full pretrained (includes tracker keys too)
    overwritten = 0
    new_keys = 0
    for k, v in finetuned_keys.items():
        if k in merged:
            overwritten += 1
        else:
            new_keys += 1
        merged[k] = v
    
    print(f"[Convert] Merged: {overwritten} keys overwritten, {new_keys} new keys added, {len(merged)} total")
    
    # Save backup and merged version
    backup = Path(f"/sam3_weights/{filename}.backup")
    if not backup.exists():
        src.rename(backup)
        print(f"[Convert] Backup saved as: {backup.name}")
    
    torch.save(merged, src)
    sam3_volume.commit()
    
    converted_size = src.stat().st_size / (1024**3)
    print(f"[Convert] Done: {original_size:.1f} GiB → {converted_size:.1f} GiB")
    
    return {
        "success": True,
        "original_size_gb": round(original_size, 1),
        "converted_size_gb": round(converted_size, 1),
        "keys_overwritten": overwritten,
        "keys_total": len(merged),
    }


@app.function(
    image=lightweight_image,
    volumes={"/sam3_weights": sam3_volume},
    timeout=30,
)
def list_sam3_volume_models() -> list[dict]:
    """
    List SAM3 model files in the Modal volume.
    
    Returns list of dicts with filename, size_gb, and volume_path
    (path as mounted in inference containers at /models/).
    """
    from pathlib import Path
    
    # Reload to see any newly committed files
    sam3_volume.reload()
    
    models = []
    for f in sorted(Path("/sam3_weights").glob("*.pt")):
        models.append({
            "filename": f.name,
            "size_gb": round(f.stat().st_size / (1024 ** 3), 1),
            "volume_path": f"/models/{f.name}",  # Inference containers mount at /models
        })
    return models


# For local testing
if __name__ == "__main__":
    print("This module should be deployed to Modal, not run directly.")
    print("Deploy with: modal deploy backend/modal_jobs/train_sam3_job.py")
