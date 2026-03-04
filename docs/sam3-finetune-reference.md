# SAM3 Fine-Tuning Reference

> Research findings from Feb 16, 2026. This document captures everything needed to implement SAM3 fine-tuning in SAFARI.

## 1. Feasibility: Confirmed ✅

SAM3 fine-tuning is fully supported via Meta's [`facebookresearch/sam3`](https://github.com/facebookresearch/sam3) repository.

- **Training script**: `sam3/train/train.py` (Hydra config management)
- **Install**: `pip install -e ".[train]"`
- **Training docs**: `README_TRAIN.md` in the repo

### What Gets Fine-Tuned

| Component | Trainable | Notes |
|-----------|-----------|-------|
| Detector (main detection network) | ✅ | Primary target |
| Shared vision backbone (ViT) | ✅ | With layer decay (0.9) |
| Language backbone | ✅ | Lower learning rate |
| Presence head | ✅ | Crucial for concept discrimination |
| Tracker | ❌ | Stays frozen in inference mode |

### Training Modes

| Mode | `enable_segmentation` | Loss Functions | Use Case |
|------|----|------|----------|
| Detection only | `False` | bbox + GIoU + focal CE + presence | Object detection |
| **Full segmentation** | **`True`** | bbox + GIoU + focal CE + presence + **mask + dice** | **Our target** |

## 2. Dataset Format: COCO JSON

SAM3 training expects **COCO instance segmentation format** with an extra `noun_phrase` field.

### Directory Structure

```
dataset_root/
  train/
    _annotations.coco.json
    image001.jpg
    image002.jpg
    ...
  test/
    _annotations.coco.json
    image001.jpg
    ...
```

### Annotation JSON Schema

```json
{
  "images": [
    {
      "id": 1,
      "file_name": "image001.jpg",
      "width": 1920,
      "height": 1080
    }
  ],
  "annotations": [
    {
      "id": 1,
      "image_id": 1,
      "category_id": 0,
      "bbox": [x, y, w, h],
      "segmentation": [[x1, y1, x2, y2, x3, y3, ...]],
      "area": 4000,
      "iscrowd": 0,
      "noun_phrase": "animal"
    }
  ],
  "categories": [
    {"id": 0, "name": "animal"}
  ]
}
```

**Key fields**:
- `bbox`: COCO format `[x, y, width, height]`
- `segmentation`: Polygon format `[[x1, y1, x2, y2, ...]]` or RLE
- `noun_phrase`: Text prompt used during training (e.g., `"animal"`)
- `area`: Area of the segmentation mask
- `iscrowd`: 0 for instance, 1 for crowd

### Source Reference

The training config uses `sam3.train.data.sam3_image_dataset.Sam3ImageDataset` with:
- `img_folder`: Path to images
- `ann_file`: Path to `_annotations.coco.json`
- `load_segmentation`: Must be `True` for mask training
- `max_ann_per_img`: Set to 500000 for training

## 3. Training Configuration

### Key Hyperparameters (from Roboflow config)

```yaml
scratch:
  resolution: 1008                    # Input resolution
  enable_segmentation: True           # MUST be True for mask training
  max_ann_per_img: 200
  max_data_epochs: 20
  target_epoch_size: 1500

  # Learning rates
  lr_scale: 0.1
  lr_transformer: 8e-5               # (8e-4 × 0.1)
  lr_vision_backbone: 2.5e-5         # (2.5e-4 × 0.1)
  lr_language_backbone: 5e-6         # (5e-5 × 0.1)
  lrd_vision_backbone: 0.9           # Layer decay
  wd: 0.1                            # Weight decay

  # Normalization
  train_norm_mean: [0.5, 0.5, 0.5]
  train_norm_std: [0.5, 0.5, 0.5]

trainer:
  max_epochs: 20
  gradient_accumulation_steps: 1
  train_batch_size: 1
  val_batch_size: 1
  seed_value: 123
  val_epoch_freq: 10

optim:
  amp:
    enabled: True
    amp_dtype: bfloat16
  gradient_clip:
    max_norm: 0.1
```

### Segmentation Loss Config (commented in default, enable for our use)

```yaml
loss_fns_find:
  - Boxes:
      loss_bbox: 5.0
      loss_giou: 2.0
  - IABCEMdetr:
      loss_ce: 20.0
      presence_loss: 20.0
      pos_weight: 10.0
      use_presence: True
  - Masks:                            # ← Enable this for segmentation
      loss_mask: 200.0
      loss_dice: 10.0
      focal_alpha: 0.25
      focal_gamma: 2.0
```

### Few-Shot vs Full Training

| | Few-Shot (10-shot) | Full Training |
|---|---|---|
| Data needed | 10 images per concept | All available |
| Training time | Minutes | Hours |
| Config param | `num_images: 10` | `num_images: null` |
| Best for | Quick validation, testing pipeline | Maximum accuracy |
| Recommendation | **Start here** | Scale up after validation |

The `num_images` parameter in the config controls this:
```yaml
roboflow_train:
  num_images: 100  # Set to 10 for few-shot, null for all
```

### GPU Requirements

- **Minimum**: 1 GPU (single GPU mode: `--num-gpus 1`)
- **Recommended**: A100 (for bfloat16 AMP support)
- **A10G**: Should work but slower, may need gradient accumulation
- **Mixed precision**: bfloat16 enabled by default
- **Modal**: Suitable — use `gpu="A100"` in Modal function decorator

## 4. Weight Compatibility with Ultralytics ✅

### Critical Finding: Drop-in replacement

The Ultralytics `_load_checkpoint` function in [`build_sam3.py`](file:///opt/anaconda3/lib/python3.11/site-packages/ultralytics/models/sam/build_sam3.py) expects **exactly the Meta/facebookresearch checkpoint format**:

```python
def _load_checkpoint(model, checkpoint, interactive=False):
    ckpt = torch_load(f)
    if "model" in ckpt and isinstance(ckpt["model"], dict):
        ckpt = ckpt["model"]              # Unwraps Meta's format
    sam3_image_ckpt = {
        k.replace("detector.", ""): v
        for k, v in ckpt.items()
        if "detector" in k                 # Extracts detector weights
    }
    model.load_state_dict(sam3_image_ckpt, strict=False)  # Partial load OK
```

**What this means**:
1. facebookresearch/sam3 training saves checkpoints with `detector.*` keys
2. Ultralytics extracts exactly these keys
3. `strict=False` means the tracker weights (not fine-tuned) still load from the base checkpoint
4. **The fine-tuned `.pt` file replaces `sam3.pt` with zero code changes**

### Usage in SAFARI

Currently, SAM3 is loaded via the model path. To use fine-tuned weights:
- Replace `sam3.pt` with the fine-tuned checkpoint
- Or add a model selection option in the UI to choose between base and fine-tuned weights
- No changes needed to `hybrid_infer_core.py` or any inference code

## 5. Dataset Generation Strategy (for SAFARI)

### Pipeline

```
SAFARI Project (detection/classification)
    ↓  User selects datasets in Export Modal
    ↓  "Generate SAM3 Dataset" mode
    ↓
Run Hybrid Inference (SAM3 + classifier)
    ↓  For each image: get detections with masks
    ↓  For each video: extract keyframe images with masks
    ↓
Convert to COCO JSON format
    ↓  bbox → COCO [x, y, w, h]
    ↓  mask_polygon → COCO segmentation [[x1,y1,...]]
    ↓  species class → noun_phrase: "animal" (generic)
    ↓  Calculate area from mask polygon
    ↓
Package as SAM3 Dataset
    ↓  train/ and test/ split
    ↓  _annotations.coco.json per split
    ↓  Images copied/downloaded from R2
    ↓
New Project: "{ProjectName} SAM3"
```

### Key Decisions

- **Noun phrase**: Use `"animal"` as generic prompt (confirmed by user)
- **Video handling**: Extract keyframe images → treat as image dataset
- **Train/test split**: 80/20 or configurable
- **Confidence threshold**: Only include high-confidence detections
- **Integration point**: Export modal with new "Generate SAM3 Dataset" mode

## 6. Fine-Tuning Pipeline (future implementation)

### On Modal

```python
@app.function(gpu="A100", timeout=3600*6, image=sam3_image)
def finetune_sam3(dataset_path: str, config_overrides: dict):
    # 1. Download dataset from R2
    # 2. Write Hydra config YAML
    # 3. Run sam3/train/train.py
    # 4. Upload fine-tuned checkpoint to R2
    # 5. Return checkpoint path
```

### Config Template

```yaml
paths:
  dataset_root: /tmp/sam3_dataset
  experiment_log_dir: /tmp/sam3_logs
  bpe_path: sam3/assets/bpe_simple_vocab_16e6.txt.gz

scratch:
  enable_segmentation: True
  resolution: 1008
  max_data_epochs: 20

trainer:
  max_epochs: 20
  mode: train

launcher:
  num_nodes: 1
  gpus_per_node: 1
```

### Integration with SAFARI

1. Fine-tuned checkpoint uploaded to R2
2. New model entry in Supabase `models` table with `model_type: "sam3_finetuned"`
3. UI allows selecting between base SAM3 and fine-tuned SAM3
4. Inference pipeline loads selected checkpoint via standard `_load_checkpoint`

## 7. External References

- **SAM3 Paper**: [arXiv:2511.16719](https://arxiv.org/abs/2511.16719)
- **facebookresearch/sam3**: https://github.com/facebookresearch/sam3
- **Training docs**: https://github.com/facebookresearch/sam3/blob/main/README_TRAIN.md
- **SA-Co Dataset**: https://huggingface.co/datasets/facebook/SACo-Gold
- **SAM3 Weights (HuggingFace)**: https://huggingface.co/facebook/sam3
- **Ultralytics SAM3 docs**: https://docs.ultralytics.com/models/sam-3/
- **Roboflow 100-VL**: https://github.com/roboflow/rf100-vl
- **SAM3-Adapter**: https://arxiv.org/abs/... (parameter-efficient alternative)
