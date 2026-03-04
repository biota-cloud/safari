"""
Backend Core Modules — Shared pure-logic utilities.

This package contains utilities shared between Modal jobs and remote workers
to ensure a single source of truth for common operations.

Modules:
    image_utils: Image cropping and download utilities
    classifier_utils: Model loading and classification utilities
    hybrid_infer_core: Single-image hybrid inference pipeline
    hybrid_batch_core: Batch hybrid inference pipeline (multiple images)
    hybrid_video_core: Video hybrid inference pipeline (SAM3 tracking)
    autolabel_core: YOLO and SAM3 automatic annotation pipeline
    train_detect_core: YOLO detection training pipeline
    train_classify_core: Classification training pipeline (YOLO + ConvNeXt)
    yolo_infer_core: Pure YOLO detection inference pipeline
"""
