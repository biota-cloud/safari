"""
Shared Core — Classification Training (YOLO + ConvNeXt).

Pure training logic without environment-specific code (Modal/SSH).
Used by both train_classify_job.py (Modal) and remote_train_classify.py (Local GPU).

Functions:
- download_images_parallel: Parallel image download
- create_classification_crops: Create crops from annotations
- create_train_val_split_classification: Split files into train/val
- run_yolo_classification_training: YOLO-cls training
- run_convnext_training: ConvNeXt training with timm
- train_classification: Dispatcher for backbone selection
- collect_classification_artifacts: Gather artifacts for upload
"""

import csv
import json
import random
import shutil
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import Callable, Optional


def download_images_parallel(
    image_urls: dict[str, str],
    download_dir: Path,
    download_fn: Callable[[str, Path], bool],
    max_workers: int = 10,
) -> list[str]:
    """
    Download images in parallel.
    
    Args:
        image_urls: {filename: url} for images
        download_dir: Directory to download into
        download_fn: Function(url, dest_path) -> bool
        max_workers: Number of parallel downloads
    
    Returns:
        List of failed filenames
    """
    images_dir = download_dir / "images"
    images_dir.mkdir(parents=True, exist_ok=True)
    
    all_downloads = []
    for filename, url in image_urls.items():
        dest = images_dir / filename
        all_downloads.append((url, dest, filename))
    
    failed_downloads = []
    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        futures = {
            executor.submit(download_fn, url, dest): filename
            for url, dest, filename in all_downloads
        }
        for future in as_completed(futures):
            filename = futures[future]
            if not future.result():
                failed_downloads.append(filename)
    
    return failed_downloads


def create_classification_crops(
    dataset_dir: Path,
    download_dir: Path,
    annotations: dict[str, list[dict]],
    classes: list[str],
    train_filenames: set[str],
    val_filenames: set[str],
    crop_fn: Callable,
) -> tuple[dict[str, int], dict[str, dict[str, int]]]:
    """
    Create classification crops from annotations.
    
    Args:
        dataset_dir: Root dataset directory for output
        download_dir: Directory containing downloaded images
        annotations: {filename: [{class_name, x, y, width, height}, ...]}
        classes: List of class names
        train_filenames: Set of filenames for training
        val_filenames: Set of filenames for validation
        crop_fn: Function(image_bytes, x, y, width, height, padding) -> bytes
    
    Returns:
        (crop_counts, class_counts) dicts
    """
    # Create class folders for train/val
    for split in ["train", "val"]:
        for class_name in classes:
            (dataset_dir / split / class_name).mkdir(parents=True, exist_ok=True)
    
    crop_counts = {"train": 0, "val": 0}
    class_counts = {c: {"train": 0, "val": 0} for c in classes}
    
    for filename, ann_list in annotations.items():
        # Find the image file
        img_path = download_dir / "images" / filename
        if not img_path.exists():
            img_path = download_dir / "val_images" / filename
            if not img_path.exists():
                continue
        
        # Determine split
        if filename in val_filenames:
            split = "val"
        elif filename in train_filenames:
            split = "train"
        else:
            split = "train"  # Default to train
        
        # Read image once
        image_bytes = img_path.read_bytes()
        
        # Create crop for each annotation
        for idx, ann in enumerate(ann_list):
            class_name = ann.get("class_name")
            if class_name not in classes:
                print(f"Warning: Unknown class '{class_name}' in {filename}, skipping")
                continue
            
            try:
                crop_bytes = crop_fn(
                    image_bytes,
                    x=ann.get("x", 0),
                    y=ann.get("y", 0),
                    width=ann.get("width", 0),
                    height=ann.get("height", 0),
                    padding=0.05,
                )
                
                # Save crop to class folder
                stem = Path(filename).stem
                crop_filename = f"{stem}_crop{idx}.jpg"
                crop_path = dataset_dir / split / class_name / crop_filename
                crop_path.write_bytes(crop_bytes)
                
                crop_counts[split] += 1
                class_counts[class_name][split] += 1
                
            except Exception as e:
                print(f"Warning: Failed to crop {filename} annotation {idx}: {e}")
    
    return crop_counts, class_counts


def create_train_val_split_classification(
    download_dir: Path,
    image_urls: dict[str, str],
    train_split_ratio: float = 0.8,
    val_image_urls: Optional[dict[str, str]] = None,
    download_fn: Optional[Callable[[str, Path], bool]] = None,
) -> tuple[set[str], set[str]]:
    """
    Determine train/val split for classification.
    
    Args:
        download_dir: Directory containing downloaded images
        image_urls: Training image URLs
        train_split_ratio: Ratio for random split
        val_image_urls: Optional explicit validation image URLs
        download_fn: Function to download validation images
    
    Returns:
        (train_filenames, val_filenames) sets
    """
    if val_image_urls and len(val_image_urls) > 0:
        print(f"Using explicit validation datasets ({len(val_image_urls)} validation images)")
        train_filenames = set(image_urls.keys())
        val_filenames = set(val_image_urls.keys())
        
        # Download validation images
        val_images_dir = download_dir / "val_images"
        val_images_dir.mkdir(parents=True, exist_ok=True)
        for filename, url in val_image_urls.items():
            dest = val_images_dir / filename
            download_fn(url, dest)
    else:
        print(f"Using random split with ratio: {train_split_ratio}/{1-train_split_ratio}")
        image_files = list((download_dir / "images").glob("*"))
        random.shuffle(image_files)
        split_idx = int(len(image_files) * train_split_ratio)
        train_files = image_files[:split_idx]
        val_files = image_files[split_idx:]
        train_filenames = {f.name for f in train_files}
        val_filenames = {f.name for f in val_files}
    
    return train_filenames, val_filenames


def ensure_validation_data(
    dataset_dir: Path,
    classes: list[str],
    crop_counts: dict[str, int],
) -> dict[str, int]:
    """
    Ensure validation set has data (move from train if needed).
    
    Args:
        dataset_dir: Root dataset directory
        classes: List of class names
        crop_counts: Current crop counts
    
    Returns:
        Updated crop_counts
    """
    if crop_counts['val'] == 0:
        print("Warning: No validation crops! Using training split for validation.")
        for class_name in classes:
            train_dir = dataset_dir / "train" / class_name
            val_dir = dataset_dir / "val" / class_name
            train_crops = list(train_dir.glob("*.jpg"))
            if train_crops:
                val_count = max(1, len(train_crops) // 5)
                for crop in train_crops[:val_count]:
                    shutil.move(str(crop), str(val_dir / crop.name))
                crop_counts['val'] += val_count
                crop_counts['train'] -= val_count
    
    return crop_counts


def remove_empty_class_folders(
    dataset_dir: Path,
    classes: list[str],
    class_counts: dict[str, dict[str, int]],
) -> list[str]:
    """
    Remove empty class folders and return filtered classes list.
    
    PyTorch ImageFolder fails if any class folder is empty.
    This function removes empty folders and returns only classes with data.
    
    Args:
        dataset_dir: Root dataset directory
        classes: Original list of class names
        class_counts: Dict of {class_name: {train: N, val: M}}
    
    Returns:
        Filtered list of classes with at least one training sample
    """
    valid_classes = []
    removed_classes = []
    
    for class_name in classes:
        train_count = class_counts.get(class_name, {}).get("train", 0)
        val_count = class_counts.get(class_name, {}).get("val", 0)
        
        if train_count > 0 or val_count > 0:
            valid_classes.append(class_name)
        else:
            removed_classes.append(class_name)
            # Remove empty folders to avoid ImageFolder errors
            for split in ["train", "val"]:
                empty_dir = dataset_dir / split / class_name
                if empty_dir.exists() and not any(empty_dir.iterdir()):
                    empty_dir.rmdir()
    
    if removed_classes:
        print(f"Removed {len(removed_classes)} empty class folders: {removed_classes}")
        print(f"Training with {len(valid_classes)} classes: {valid_classes}")
    
    return valid_classes


def run_yolo_classification_training(
    dataset_dir: Path,
    config: dict,
) -> tuple[dict, Path]:
    """
    Execute YOLO classification training.
    
    Args:
        dataset_dir: Root dataset directory (contains train/val subdirs)
        config: Training config {epochs, model_size, batch_size, image_size, patience, optimizer, lr0, lrf}
    
    Returns:
        (metrics_dict, weights_dir)
    """
    from ultralytics import YOLO
    
    model_size = config.get("model_size", "n")
    epochs = config.get("epochs", 100)
    batch_size = config.get("batch_size", 32)
    image_size = config.get("image_size", 224)
    patience = config.get("patience", 50)
    optimizer = config.get("optimizer", "auto")
    lr0 = config.get("lr0", 0.01)
    lrf = config.get("lrf", 0.01)
    
    print(f"Model: yolo11{model_size}-cls, Epochs: {epochs}, Batch: {batch_size}, ImgSize: {image_size}")
    print(f"Advanced settings: patience={patience}, optimizer={optimizer}, lr0={lr0}, lrf={lrf}")
    
    model = YOLO(f"yolo11{model_size}-cls.pt")
    
    results = model.train(
        data=str(dataset_dir),
        epochs=epochs,
        batch=batch_size,
        imgsz=image_size,
        patience=patience,
        optimizer=optimizer,
        lr0=lr0,
        lrf=lrf,
        project=str(dataset_dir),
        name="run",
        exist_ok=True,
        verbose=True,
    )
    
    # Parse results.csv for final loss values
    results_csv_path = dataset_dir / "run" / "results.csv"
    final_train_loss = 0.0
    final_val_loss = 0.0
    if results_csv_path.exists():
        with open(results_csv_path, 'r') as f:
            reader = csv.DictReader(f)
            rows = list(reader)
            if rows:
                last_row = rows[-1]
                final_train_loss = float(last_row.get("train/loss", 0))
                final_val_loss = float(last_row.get("val/loss", 0))
    
    metrics = {
        "top1_accuracy": float(results.results_dict.get("metrics/accuracy_top1", 0)),
        "top5_accuracy": float(results.results_dict.get("metrics/accuracy_top5", 0)),
        "loss": final_train_loss,
        "val_loss": final_val_loss,
    }
    
    run_dir = dataset_dir / "run"
    weights_dir = run_dir / "weights"
    
    return metrics, weights_dir


def run_convnext_training(
    dataset_dir: Path,
    classes: list[str],
    config: dict,
) -> tuple[dict, Path]:
    """
    Train ConvNeXt classifier using timm + PyTorch.
    
    Generates artifacts during and after training:
    - results.csv: per-epoch metrics (columns match YOLO classification format for UI charts)
    - train_batch0/1/2.jpg: grids of augmented training samples (saved before training)
    - confusion_matrix.json: post-training evaluation on val set
    - best.pth / last.pth: model weights
    
    Args:
        dataset_dir: Root dataset directory (contains train/val subdirs)
        classes: List of class names
        config: Training config {convnext_model_size, epochs, batch_size, image_size, patience, convnext_lr0}
    
    Returns:
        (metrics_dict, weights_dir)
    """
    import torch
    import torch.nn as nn
    from torch.utils.data import DataLoader
    from torchvision import datasets, transforms
    import torchvision.utils as vutils
    from PIL import Image
    import numpy as np
    import timm
    
    model_size = config.get("convnext_model_size", "tiny")
    # Determine V1 vs V2 from backbone config
    backbone = config.get("classifier_backbone", "convnext")
    model_version = "v2" if backbone == "convnextv2" else "v1"
    epochs = config.get("epochs", 100)
    batch_size = config.get("batch_size", 32)
    image_size = config.get("image_size", 224)
    patience = config.get("patience", 50)
    lr0 = config.get("convnext_lr0", 0.0001)  # Lower for fine-tuning
    weight_decay = config.get("convnext_weight_decay", 0.05)  # AdamW regularization
    
    version_label = "V2" if model_version == "v2" else ""
    print(f"Starting ConvNeXt{version_label}-{model_size} classification training...")
    print(f"Epochs: {epochs}, Batch: {batch_size}, ImgSize: {image_size}")
    print(f"Advanced settings: patience={patience}, lr0={lr0}, weight_decay={weight_decay}")
    
    device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
    print(f"Using device: {device}")
    
    # CLAHE preprocessing — enhances local contrast, critical for IR/night images
    class ApplyCLAHE:
        """Apply CLAHE (Contrast Limited Adaptive Histogram Equalization) to PIL images."""
        def __init__(self, clip_limit=2.0, tile_grid_size=(8, 8)):
            self.clip_limit = clip_limit
            self.tile_grid_size = tile_grid_size
        def __call__(self, img):
            import cv2
            import numpy as np
            arr = np.array(img)
            # Convert to LAB, apply CLAHE to L channel only
            lab = cv2.cvtColor(arr, cv2.COLOR_RGB2LAB)
            clahe = cv2.createCLAHE(clipLimit=self.clip_limit, tileGridSize=self.tile_grid_size)
            lab[:, :, 0] = clahe.apply(lab[:, :, 0])
            result = cv2.cvtColor(lab, cv2.COLOR_LAB2RGB)
            return Image.fromarray(result)
    
    # Transforms
    mean = [0.485, 0.456, 0.406]
    std = [0.229, 0.224, 0.225]
    train_transform = transforms.Compose([
        ApplyCLAHE(),  # Enhance contrast before augmentation
        transforms.RandomRotation(10),
        transforms.RandomResizedCrop(image_size, scale=(0.35, 1.0)),
        transforms.RandomHorizontalFlip(),
        transforms.ColorJitter(brightness=0.25, contrast=0.25, saturation=0.2, hue=0.05),
        transforms.RandomApply([transforms.GaussianBlur(kernel_size=3)], p=0.1),
        transforms.ToTensor(),
        transforms.Normalize(mean, std),
    ])
    val_transform = transforms.Compose([
        ApplyCLAHE(),  # Same preprocessing as training
        transforms.Resize(int(image_size * 1.14)),
        transforms.CenterCrop(image_size),
        transforms.ToTensor(),
        transforms.Normalize(mean, std),
    ])
    
    train_dataset = datasets.ImageFolder(dataset_dir / "train", transform=train_transform)
    val_dataset = datasets.ImageFolder(dataset_dir / "val", transform=val_transform)
    train_loader = DataLoader(train_dataset, batch_size=batch_size, shuffle=True, num_workers=4)
    val_loader = DataLoader(val_dataset, batch_size=batch_size, shuffle=False, num_workers=4)
    
    print(f"Train samples: {len(train_dataset)}, Val samples: {len(val_dataset)}")
    
    # Setup run directory for artifacts
    run_dir = dataset_dir / "run"
    run_dir.mkdir(parents=True, exist_ok=True)
    weights_dir = run_dir / "weights"
    weights_dir.mkdir(parents=True, exist_ok=True)
    
    # ─── Artifact: train_batch0/1/2.jpg (augmented sample grids) ───
    try:
        mean_t = torch.tensor(mean).view(3, 1, 1)
        std_t = torch.tensor(std).view(3, 1, 1)
        batch_iter = iter(train_loader)
        for batch_idx in range(3):
            try:
                batch_images, batch_labels = next(batch_iter)
            except StopIteration:
                break  # Fewer than 3 batches available
            vis_images = (batch_images * std_t + mean_t).clamp(0, 1)
            grid = vutils.make_grid(vis_images, nrow=8, padding=2)
            grid_np = (grid.permute(1, 2, 0).numpy() * 255).astype(np.uint8)
            Image.fromarray(grid_np).save(run_dir / f"train_batch{batch_idx}.jpg", quality=90)
        print(f"Saved train_batch grids (up to 3)")
    except Exception as e:
        print(f"Warning: Failed to save train_batch grids: {e}")
    
    # Model — resolve timm name from version
    if model_version == "v2":
        model_name = f"convnextv2_{model_size}"
    else:
        model_name = f"convnext_{model_size}"
    print(f"Loading {model_name} pretrained model...")
    model = timm.create_model(model_name, pretrained=True, num_classes=len(classes)).to(device)
    
    criterion = nn.CrossEntropyLoss(label_smoothing=0.1)
    
    # Freeze backbone for first epochs — only train classifier head initially
    freeze_epochs = 5
    for param in model.parameters():
        param.requires_grad = False
    # Unfreeze classifier head (last linear layer)
    if hasattr(model, 'head'):
        head = model.head
    elif hasattr(model, 'classifier'):
        head = model.classifier
    else:
        head = list(model.children())[-1]
    for param in head.parameters():
        param.requires_grad = True
    print(f"Backbone frozen for first {freeze_epochs} epochs (training head only)")
    
    optimizer = torch.optim.AdamW(filter(lambda p: p.requires_grad, model.parameters()), lr=lr0, weight_decay=weight_decay)
    scheduler = torch.optim.lr_scheduler.CosineAnnealingLR(optimizer, T_max=epochs)
    
    best_acc, best_top5_acc, epochs_no_improve = 0.0, 0.0, 0
    
    class_to_idx = train_dataset.class_to_idx
    idx_to_class = {v: k for k, v in class_to_idx.items()}
    
    final_train_loss, final_val_loss, final_top5_acc = 0.0, 0.0, 0.0
    
    # ─── Artifact: results.csv (per-epoch metrics) ───
    csv_path = run_dir / "results.csv"
    csv_file = open(csv_path, "w", newline="")
    csv_writer = csv.writer(csv_file)
    csv_writer.writerow(["epoch", "train/loss", "val/loss", "metrics/accuracy_top1", "metrics/accuracy_top5", "lr"])
    
    try:
        for epoch in range(epochs):
            # Unfreeze backbone after warmup period
            if epoch == freeze_epochs:
                print(f"  → Unfreezing backbone at epoch {epoch + 1}")
                for param in model.parameters():
                    param.requires_grad = True
                # Recreate optimizer with all parameters
                optimizer = torch.optim.AdamW(model.parameters(), lr=lr0 * 0.3, weight_decay=weight_decay)
                scheduler = torch.optim.lr_scheduler.CosineAnnealingLR(optimizer, T_max=epochs - freeze_epochs)
            
            # Train
            model.train()
            train_loss = 0.0
            for images, labels in train_loader:
                images, labels = images.to(device), labels.to(device)
                optimizer.zero_grad()
                loss = criterion(model(images), labels)
                loss.backward()
                optimizer.step()
                train_loss += loss.item()
            
            # Validate with top-1 and top-5 accuracy
            model.eval()
            correct_top1, correct_top5, total, val_loss = 0, 0, 0, 0.0
            with torch.no_grad():
                for images, labels in val_loader:
                    images, labels = images.to(device), labels.to(device)
                    outputs = model(images)
                    val_loss += criterion(outputs, labels).item()
                    # Top-1
                    correct_top1 += outputs.argmax(1).eq(labels).sum().item()
                    # Top-5 (clamp k to number of classes)
                    k = min(5, outputs.size(1))
                    _, pred_topk = outputs.topk(k, dim=1)
                    correct_top5 += pred_topk.eq(labels.unsqueeze(1)).any(dim=1).sum().item()
                    total += labels.size(0)
            
            top1_acc = correct_top1 / total if total > 0 else 0
            top5_acc = correct_top5 / total if total > 0 else 0
            current_lr = optimizer.param_groups[0]['lr']
            scheduler.step()
            
            final_train_loss = train_loss / len(train_loader) if len(train_loader) > 0 else 0
            final_val_loss = val_loss / len(val_loader) if len(val_loader) > 0 else 0
            final_top5_acc = top5_acc
            
            # Write CSV row
            csv_writer.writerow([
                epoch + 1, f"{final_train_loss:.6f}", f"{final_val_loss:.6f}",
                f"{top1_acc:.6f}", f"{top5_acc:.6f}", f"{current_lr:.8f}",
            ])
            csv_file.flush()
            
            print(f"Epoch {epoch+1}/{epochs}: train_loss={final_train_loss:.4f}, val_acc={top1_acc:.4f}, top5_acc={top5_acc:.4f}")
            
            if top1_acc > best_acc:
                best_acc = top1_acc
                best_top5_acc = top5_acc
                epochs_no_improve = 0
                torch.save({
                    "model_state_dict": model.state_dict(),
                    "classes": classes,
                    "class_to_idx": class_to_idx,
                    "idx_to_class": idx_to_class,
                    "image_size": image_size,
                    "model_size": model_size,
                    "model_version": model_version,
                }, weights_dir / "best.pth")
                print(f"  → Saved best model (acc={top1_acc:.4f})")
            else:
                epochs_no_improve += 1
                if epochs_no_improve >= patience:
                    print(f"  → Early stopping at epoch {epoch+1}")
                    break
    finally:
        csv_file.close()
    
    print(f"Saved results.csv ({epoch + 1} epochs)")
    
    # Save last checkpoint
    torch.save({
        "model_state_dict": model.state_dict(),
        "classes": classes,
        "class_to_idx": class_to_idx,
        "idx_to_class": idx_to_class,
        "image_size": image_size,
        "model_size": model_size,
        "model_version": model_version,
    }, weights_dir / "last.pth")
    
    # ─── Artifact: confusion_matrix.json (post-training evaluation) ───
    try:
        # Load best model for evaluation
        best_ckpt = torch.load(weights_dir / "best.pth", map_location=device)
        model.load_state_dict(best_ckpt["model_state_dict"])
        model.eval()
        
        all_preds, all_labels = [], []
        with torch.no_grad():
            for images, labels in val_loader:
                images = images.to(device)
                outputs = model(images)
                all_preds.extend(outputs.argmax(1).cpu().tolist())
                all_labels.extend(labels.cpu().tolist())
        
        # Build confusion matrix (rows=actual, cols=predicted)
        num_classes = len(classes)
        matrix = [[0] * num_classes for _ in range(num_classes)]
        for pred, label in zip(all_preds, all_labels):
            matrix[label][pred] += 1
        
        # Use class names in the order ImageFolder discovered them
        ordered_classes = [idx_to_class[i] for i in range(num_classes)]
        
        cm_data = {
            "classes": ordered_classes,
            "matrix": matrix,
        }
        (run_dir / "confusion_matrix.json").write_text(json.dumps(cm_data))
        print(f"Saved confusion_matrix.json ({num_classes} classes, {len(all_labels)} samples)")
    except Exception as e:
        print(f"Warning: Failed to generate confusion matrix: {e}")
    
    metrics = {
        "top1_accuracy": best_acc,
        "top5_accuracy": best_top5_acc,
        "loss": final_train_loss,
        "val_loss": final_val_loss,
    }
    
    return metrics, weights_dir


def train_classification(
    dataset_dir: Path,
    classes: list[str],
    config: dict,
) -> tuple[dict, Path, str]:
    """
    Dispatcher for classification training (YOLO or ConvNeXt).
    
    Args:
        dataset_dir: Root dataset directory
        classes: List of class names
        config: Training config including 'classifier_backbone'
    
    Returns:
        (metrics_dict, weights_dir, backbone)
    """
    backbone = config.get("classifier_backbone", "yolo")
    
    if backbone in ("convnext", "convnextv2"):
        metrics, weights_dir = run_convnext_training(dataset_dir, classes, config)
    else:
        metrics, weights_dir = run_yolo_classification_training(dataset_dir, config)
    
    return metrics, weights_dir, backbone


def collect_classification_artifacts(
    dataset_dir: Path,
    backbone: str,
) -> list[tuple[Path, str]]:
    """
    Collect training artifacts for upload.
    
    Args:
        dataset_dir: Root dataset directory
        backbone: 'yolo' or 'convnext'
    
    Returns:
        List of (local_path, relative_name) tuples for existing files
    """
    run_dir = dataset_dir / "run"
    weights_dir = run_dir / "weights"
    
    if backbone in ("convnext", "convnextv2"):
        artifact_specs = [
            (weights_dir / "best.pth", "best.pth"),
            (weights_dir / "last.pth", "last.pth"),
            (run_dir / "results.csv", "results.csv"),
            (run_dir / "confusion_matrix.json", "confusion_matrix.json"),
            (run_dir / "train_batch0.jpg", "train_batch0.jpg"),
            (run_dir / "train_batch1.jpg", "train_batch1.jpg"),
            (run_dir / "train_batch2.jpg", "train_batch2.jpg"),
        ]
    else:
        artifact_specs = [
            (weights_dir / "best.pt", "best.pt"),
            (weights_dir / "last.pt", "last.pt"),
            (run_dir / "results.csv", "results.csv"),
            (run_dir / "results.png", "results.png"),
            (run_dir / "confusion_matrix.png", "confusion_matrix.png"),
            (run_dir / "confusion_matrix_normalized.png", "confusion_matrix_normalized.png"),
            (run_dir / "train_batch0.jpg", "train_batch0.jpg"),
            (run_dir / "train_batch1.jpg", "train_batch1.jpg"),
            (run_dir / "train_batch2.jpg", "train_batch2.jpg"),
        ]
    
    return [(path, name) for path, name in artifact_specs if path.exists()]
