-- ============================================================================
-- Phase 3.4.1: Inference Results Table
-- ============================================================================
-- Run this SQL in Supabase Dashboard → SQL Editor
-- This creates the inference_results table for tracking inference runs
--
-- NOTE: models table already exists with schema:
--   - id, training_run_id, dataset_id, user_id, name, weights_path, 
--     metrics, is_active, created_at
-- ============================================================================

CREATE TABLE inference_results (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID REFERENCES profiles(id) ON DELETE CASCADE,
    model_id UUID REFERENCES models(id) ON DELETE SET NULL,  -- NULL if built-in model (yolo11n/s/m)
    model_name TEXT NOT NULL,  -- e.g., "yolo11s.pt" or custom model name
    
    -- Input metadata
    input_type TEXT NOT NULL CHECK (input_type IN ('image', 'video')),
    input_filename TEXT NOT NULL,
    input_r2_path TEXT NOT NULL,
    
    -- Video-specific fields (NULL for images)
    video_start_time FLOAT,  -- Start time in seconds for video clips
    video_end_time FLOAT,    -- End time in seconds for video clips
    video_fps FLOAT,         -- Frames per second
    video_total_frames INTEGER,  -- Total frames processed
    
    -- Inference configuration
    confidence_threshold FLOAT NOT NULL DEFAULT 0.25,
    
    -- Results storage
    predictions_json JSONB NOT NULL,  -- Array of frame predictions for videos, single array for images
    labels_r2_path TEXT,  -- Path to YOLO format labels (for images) or per-frame labels JSON (for videos)
    
    -- Metadata
    inference_duration_ms INTEGER,  -- How long inference took
    detection_count INTEGER,  -- Total detections across all frames
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

-- Indexes for performance
CREATE INDEX idx_inference_results_user_id ON inference_results(user_id);
CREATE INDEX idx_inference_results_model_id ON inference_results(model_id);
CREATE INDEX idx_inference_results_created_at ON inference_results(created_at DESC);
CREATE INDEX idx_inference_results_input_type ON inference_results(input_type);

-- Row Level Security
ALTER TABLE inference_results ENABLE ROW LEVEL SECURITY;

CREATE POLICY "Users can CRUD own inference results" ON inference_results
    FOR ALL USING (auth.uid() = user_id);
