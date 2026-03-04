"""
Shared Core — YOLO Detection Training.

Pure training logic without environment-specific code (Modal/SSH).
Used by both train_job.py (Modal) and remote_train.py (Local GPU).

Functions:
- download_dataset: Parallel download of images and labels
- create_train_val_split: Split files into train/val sets
- create_yolo_data_yaml: Generate data.yaml for YOLO
- run_yolo_detection_training: Execute YOLO training
- collect_detection_artifacts: Gather artifacts for upload
"""

import random
import shutil
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import Callable, Optional


def download_dataset(
    image_urls: dict[str, str],
    label_urls: dict[str, str],
    download_dir: Path,
    download_fn: Callable[[str, Path], bool],
    max_workers: int = 10,
) -> list[str]:
    """
    Download images and labels in parallel.
    
    Args:
        image_urls: {filename: url} for images
        label_urls: {filename: url} for labels
        download_dir: Base directory to download into
        download_fn: Function(url, dest_path) -> bool
        max_workers: Number of parallel downloads
    
    Returns:
        List of failed filenames
    """
    (download_dir / "images").mkdir(parents=True, exist_ok=True)
    (download_dir / "labels").mkdir(parents=True, exist_ok=True)
    
    all_downloads = []
    for filename, url in image_urls.items():
        dest = download_dir / "images" / filename
        all_downloads.append((url, dest, filename))
    
    for filename, url in label_urls.items():
        dest = download_dir / "labels" / filename
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


def create_train_val_split(
    download_dir: Path,
    train_split_ratio: float = 0.8,
    val_image_urls: Optional[dict[str, str]] = None,
    val_label_urls: Optional[dict[str, str]] = None,
    download_fn: Optional[Callable[[str, Path], bool]] = None,
) -> tuple[list[Path], list[Path], Optional[Path]]:
    """
    Create train/val split from downloaded files.
    
    Args:
        download_dir: Directory containing images/labels subdirs
        train_split_ratio: Ratio for random split (if no explicit val)
        val_image_urls: Optional explicit validation image URLs
        val_label_urls: Optional explicit validation label URLs
        download_fn: Function to download validation files (required if val_*_urls provided)
    
    Returns:
        (train_images, val_images, val_download_dir or None)
    """
    val_download_dir = None
    
    if val_image_urls and len(val_image_urls) > 0:
        # Use explicit validation datasets
        print(f"Using explicit validation datasets ({len(val_image_urls)} validation images)")
        
        val_download_dir = download_dir.parent / "val_downloads"
        val_download_dir.mkdir()
        (val_download_dir / "images").mkdir()
        (val_download_dir / "labels").mkdir()
        
        for filename, url in val_image_urls.items():
            dest = val_download_dir / "images" / filename
            download_fn(url, dest)
        
        for filename, url in (val_label_urls or {}).items():
            dest = val_download_dir / "labels" / filename
            download_fn(url, dest)
        
        train_images = list((download_dir / "images").glob("*"))
        val_images = list((val_download_dir / "images").glob("*"))
    else:
        # Use random split
        print(f"Using random split with ratio: {train_split_ratio}/{1-train_split_ratio}")
        
        image_files = list((download_dir / "images").glob("*"))
        random.shuffle(image_files)
        
        split_idx = int(len(image_files) * train_split_ratio)
        train_images = image_files[:split_idx]
        val_images = image_files[split_idx:]
    
    print(f"Train: {len(train_images)}, Val: {len(val_images)}")
    return train_images, val_images, val_download_dir


def organize_train_val_structure(
    dataset_dir: Path,
    download_dir: Path,
    train_images: list[Path],
    val_images: list[Path],
    val_download_dir: Optional[Path] = None,
) -> None:
    """
    Move files into YOLO train/val directory structure.
    
    Args:
        dataset_dir: Root dataset directory
        download_dir: Directory containing downloaded files
        train_images: List of training image paths
        val_images: List of validation image paths
        val_download_dir: Optional separate validation download dir
    """
    # Move training files
    for img_path in train_images:
        dest_img = dataset_dir / "train" / "images" / img_path.name
        dest_img.parent.mkdir(parents=True, exist_ok=True)
        shutil.move(str(img_path), str(dest_img))
        
        label_name = img_path.stem + ".txt"
        label_path = download_dir / "labels" / label_name
        if label_path.exists():
            dest_lbl = dataset_dir / "train" / "labels" / label_name
            dest_lbl.parent.mkdir(parents=True, exist_ok=True)
            shutil.move(str(label_path), str(dest_lbl))
    
    # Move validation files
    for img_path in val_images:
        dest_img = dataset_dir / "val" / "images" / img_path.name
        dest_img.parent.mkdir(parents=True, exist_ok=True)
        shutil.move(str(img_path), str(dest_img))
        
        label_name = img_path.stem + ".txt"
        # Labels come from val_download_dir if explicit validation, else download_dir
        if val_download_dir:
            label_path = val_download_dir / "labels" / label_name
        else:
            label_path = download_dir / "labels" / label_name
        
        if label_path.exists():
            dest_lbl = dataset_dir / "val" / "labels" / label_name
            dest_lbl.parent.mkdir(parents=True, exist_ok=True)
            shutil.move(str(label_path), str(dest_lbl))
        else:
            print(f"Warning: Label not found for validation image {img_path.name}")


def create_yolo_data_yaml(
    dataset_dir: Path,
    classes: list[str],
) -> Path:
    """
    Generate data.yaml for YOLO training.
    
    Args:
        dataset_dir: Root dataset directory (contains train/val subdirs)
        classes: List of class names
    
    Returns:
        Path to created data.yaml
    """
    # Ensure directories exist
    for split in ["train", "val"]:
        for subdir in ["images", "labels"]:
            (dataset_dir / split / subdir).mkdir(parents=True, exist_ok=True)
    
    yaml_path = dataset_dir / "data.yaml"
    yaml_content = f"""# Auto-generated YOLO dataset configuration
path: {dataset_dir}
train: train/images
val: val/images

nc: {len(classes)}
names: {classes}
"""
    yaml_path.write_text(yaml_content)
    return yaml_path


def run_yolo_detection_training(
    dataset_dir: Path,
    yaml_path: Path,
    config: dict,
    base_weights_path: Optional[Path] = None,
) -> tuple[dict, Path]:
    """
    Execute YOLO detection training.
    
    Args:
        dataset_dir: Root dataset directory
        yaml_path: Path to data.yaml
        config: Training config {epochs, model_size, batch_size, patience, optimizer, lr0, lrf}
        base_weights_path: Optional path to base weights for continued training
    
    Returns:
        (metrics_dict, run_dir)
    """
    from ultralytics import YOLO
    
    model_size = config.get("model_size", "n")
    epochs = config.get("epochs", 50)
    batch_size = config.get("batch_size", 16)
    patience = config.get("patience", 50)
    optimizer = config.get("optimizer", "auto")
    lr0 = config.get("lr0", 0.01)
    lrf = config.get("lrf", 0.01)
    
    print(f"Advanced settings: patience={patience}, optimizer={optimizer}, lr0={lr0}, lrf={lrf}")
    
    # Initialize model
    if base_weights_path and base_weights_path.exists():
        print(f"Loaded weights for continued training from: {base_weights_path}")
        model = YOLO(str(base_weights_path))
    else:
        model = YOLO(f"yolo11{model_size}.pt")
    
    results = model.train(
        data=str(yaml_path),
        epochs=epochs,
        batch=batch_size,
        imgsz=640,
        patience=patience,
        optimizer=optimizer,
        lr0=lr0,
        lrf=lrf,
        project=str(dataset_dir),
        name="run",
        exist_ok=True,
        verbose=True,
    )
    
    # Get final metrics
    metrics = {
        "mAP50": float(results.results_dict.get("metrics/mAP50(B)", 0)),
        "mAP50-95": float(results.results_dict.get("metrics/mAP50-95(B)", 0)),
        "precision": float(results.results_dict.get("metrics/precision(B)", 0)),
        "recall": float(results.results_dict.get("metrics/recall(B)", 0)),
    }
    
    print(f"Training complete! Metrics: {metrics}")
    
    run_dir = dataset_dir / "run"
    return metrics, run_dir


def run_validation_curves(
    yaml_path: Path,
    run_dir: Path,
    dataset_dir: Path,
) -> Path:
    """
    Run validation to generate F1/PR curves.
    
    Args:
        yaml_path: Path to data.yaml
        run_dir: Training run directory
        dataset_dir: Root dataset directory
    
    Returns:
        Path to validation output directory
    """
    from ultralytics import YOLO
    
    best_weights = run_dir / "weights" / "best.pt"
    
    if best_weights.exists():
        print("Running validation to generate curves...")
        val_model = YOLO(str(best_weights))
        val_model.val(
            data=str(yaml_path),
            project=str(dataset_dir),
            name="val",
            plots=True,
        )
    
    return dataset_dir / "val"


def collect_detection_artifacts(
    run_dir: Path,
    val_dir: Path,
) -> list[tuple[Path, str]]:
    """
    Collect training artifacts for upload.
    
    Args:
        run_dir: Training run directory
        val_dir: Validation output directory
    
    Returns:
        List of (local_path, relative_name) tuples for existing files
    """
    weights_dir = run_dir / "weights"
    
    artifact_specs = [
        (weights_dir / "best.pt", "best.pt"),
        (weights_dir / "last.pt", "last.pt"),
        (run_dir / "results.csv", "results.csv"),
        (run_dir / "results.png", "results.png"),
        (run_dir / "confusion_matrix.png", "confusion_matrix.png"),
        (val_dir / "F1_curve.png", "F1_curve.png"),
        (val_dir / "PR_curve.png", "PR_curve.png"),
        (val_dir / "P_curve.png", "P_curve.png"),
        (val_dir / "R_curve.png", "R_curve.png"),
        (run_dir / "labels.jpg", "labels.jpg"),
        (run_dir / "train_batch0.jpg", "train_batch0.jpg"),
        (run_dir / "train_batch1.jpg", "train_batch1.jpg"),
        (run_dir / "train_batch2.jpg", "train_batch2.jpg"),
        (run_dir / "val_batch0_labels.jpg", "val_batch0_labels.jpg"),
        (run_dir / "val_batch0_pred.jpg", "val_batch0_pred.jpg"),
    ]
    
    return [(path, name) for path, name in artifact_specs if path.exists()]
