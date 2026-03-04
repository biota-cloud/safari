-- ============================================================================
-- Add progress_status column to inference_results
-- ============================================================================
-- Run this SQL in Supabase Dashboard → SQL Editor
-- Adds a text column for human-readable progress status (e.g., "SAM3 frame 150/915")
-- ============================================================================

ALTER TABLE inference_results 
ADD COLUMN IF NOT EXISTS progress_status TEXT DEFAULT 'queued';

COMMENT ON COLUMN inference_results.progress_status IS 'Human-readable progress status text for video inference (e.g., SAM3 frame 150/915)';
