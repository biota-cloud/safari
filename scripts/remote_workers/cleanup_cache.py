#!/usr/bin/env python3
"""
SAFARI Remote Worker — Model Cache Cleanup.

Cleans up cached model files based on age and total size.

Usage:
    python cleanup_cache.py              # Dry run (show what would be deleted)
    python cleanup_cache.py --apply      # Actually delete files

Options:
    --max-age DAYS      Delete models older than N days (default: 30)
    --max-size GB       Delete oldest models if cache exceeds N GB (default: 10)
    --apply             Actually delete files (otherwise dry run)
"""

import argparse
import os
from datetime import datetime, timedelta
from pathlib import Path


# Models that should never be deleted (permanent infrastructure)
PROTECTED_MODELS = {
    "sam3.pt",      # SAM3 base model (~3.2 GB)
    "sam3_b.pt",    # SAM3 base model (alternate name)
}


def get_models_dir() -> Path:
    """Get the models cache directory."""
    return Path.home() / ".tyto" / "models"


def get_file_age_days(filepath: Path) -> float:
    """Get file age in days."""
    mtime = datetime.fromtimestamp(filepath.stat().st_mtime)
    return (datetime.now() - mtime).days


def get_file_size_gb(filepath: Path) -> float:
    """Get file size in GB."""
    return filepath.stat().st_size / (1024 ** 3)


def cleanup_cache(max_age_days: int = 30, max_size_gb: float = 10.0, apply: bool = False):
    """
    Clean up cached models based on age and total size.
    
    Args:
        max_age_days: Delete models older than this many days
        max_size_gb: If total cache exceeds this, delete oldest until under limit
        apply: If False, just print what would be deleted (dry run)
    """
    models_dir = get_models_dir()
    
    if not models_dir.exists():
        print(f"Models directory does not exist: {models_dir}")
        return
    
    # Get all .pt files with stats (excluding protected models)
    model_files = []
    protected_count = 0
    protected_size = 0.0
    
    for f in models_dir.glob("*.pt"):
        if f.is_file():
            if f.name in PROTECTED_MODELS:
                protected_count += 1
                protected_size += get_file_size_gb(f)
                continue  # Skip protected models
            
            model_files.append({
                "path": f,
                "size_gb": get_file_size_gb(f),
                "age_days": get_file_age_days(f),
                "mtime": f.stat().st_mtime,
            })
    
    if protected_count > 0:
        print(f"Protected models (never deleted): {protected_count} ({protected_size:.2f} GB)")
    
    if not model_files:
        print("No cached models to clean up.")
        return
    
    # Sort by modification time (oldest first)
    model_files.sort(key=lambda x: x["mtime"])
    
    total_size_gb = sum(m["size_gb"] for m in model_files)
    print(f"Found {len(model_files)} cached models ({total_size_gb:.2f} GB total)")
    print()
    
    to_delete = []
    
    # Pass 1: Mark files older than max_age_days
    for model in model_files:
        if model["age_days"] > max_age_days:
            to_delete.append(model)
            print(f"  [AGE] {model['path'].name} — {model['age_days']:.0f} days old, {model['size_gb']:.3f} GB")
    
    # Pass 2: If still over size limit, delete oldest until under
    remaining = [m for m in model_files if m not in to_delete]
    remaining_size = sum(m["size_gb"] for m in remaining)
    
    if remaining_size > max_size_gb:
        print(f"\n  Cache still {remaining_size:.2f} GB (limit: {max_size_gb} GB)")
        remaining.sort(key=lambda x: x["mtime"])  # Oldest first
        
        while remaining_size > max_size_gb and remaining:
            oldest = remaining.pop(0)
            to_delete.append(oldest)
            remaining_size -= oldest["size_gb"]
            print(f"  [SIZE] {oldest['path'].name} — {oldest['age_days']:.0f} days old, {oldest['size_gb']:.3f} GB")
    
    # Summary
    delete_size = sum(m["size_gb"] for m in to_delete)
    print()
    
    if not to_delete:
        print("✓ No models to delete.")
        return
    
    print(f"{'Would delete' if not apply else 'Deleting'}: {len(to_delete)} models ({delete_size:.2f} GB)")
    
    if apply:
        for model in to_delete:
            try:
                model["path"].unlink()
                print(f"  ✓ Deleted: {model['path'].name}")
            except Exception as e:
                print(f"  ✗ Failed: {model['path'].name} — {e}")
        
        new_total = total_size_gb - delete_size
        print(f"\n✓ Cleanup complete. Cache now: {new_total:.2f} GB")
    else:
        print("\n(Dry run — use --apply to actually delete)")


def main():
    parser = argparse.ArgumentParser(description="Clean up cached model files")
    parser.add_argument("--max-age", type=int, default=30, help="Delete models older than N days")
    parser.add_argument("--max-size", type=float, default=10.0, help="Max cache size in GB")
    parser.add_argument("--apply", action="store_true", help="Actually delete files")
    
    args = parser.parse_args()
    
    cleanup_cache(
        max_age_days=args.max_age,
        max_size_gb=args.max_size,
        apply=args.apply,
    )


if __name__ == "__main__":
    main()
