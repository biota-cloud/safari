-- ============================================================================
-- Autolabel Modal Feature Migration
-- Run this in Supabase SQL Editor
-- ============================================================================

-- 1. Add volume_path column to models table
-- This stores the Modal volume path for fast GPU access during autolabeling
ALTER TABLE models ADD COLUMN IF NOT EXISTS volume_path TEXT;

-- 2. Create index for quick lookups on models with volume paths
CREATE INDEX IF NOT EXISTS idx_models_volume_path ON models(volume_path) WHERE volume_path IS NOT NULL;

-- 3. Add index for training_run_id lookups (needed for deletion cleanup)
CREATE INDEX IF NOT EXISTS idx_models_training_run_id ON models(training_run_id);

-- 4. Update autolabel_jobs table to support YOLO model mode
-- Add model_id column for YOLO-based autolabeling (NULL means SAM3 mode)
ALTER TABLE autolabel_jobs ADD COLUMN IF NOT EXISTS model_id UUID REFERENCES models(id) ON DELETE SET NULL;

-- 5. Add selected_video_ids column for dataset-wide video autolabeling
-- Stores array of video IDs to process (NULL means process all videos)
ALTER TABLE autolabel_jobs ADD COLUMN IF NOT EXISTS selected_video_ids UUID[] DEFAULT NULL;

-- ============================================================================
-- Verification queries (run these after migration to confirm success)
-- ============================================================================

-- Check models table has new column:
-- SELECT column_name, data_type FROM information_schema.columns WHERE table_name = 'models' AND column_name = 'volume_path';

-- Check autolabel_jobs has new columns:
-- SELECT column_name, data_type FROM information_schema.columns WHERE table_name = 'autolabel_jobs' AND column_name IN ('model_id', 'selected_video_ids');

-- ============================================================================
-- Success! The database is ready for the autolabel modal feature.
-- ============================================================================
