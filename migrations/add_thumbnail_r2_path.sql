-- ============================================================================
-- Add thumbnail_r2_path column to inference_results table
-- ============================================================================
-- Run this SQL in Supabase Dashboard → SQL Editor
-- This adds support for storing video hybrid thumbnail paths
-- ============================================================================

ALTER TABLE inference_results 
ADD COLUMN IF NOT EXISTS thumbnail_r2_path TEXT;

-- Add a comment to document the column purpose
COMMENT ON COLUMN inference_results.thumbnail_r2_path IS 'R2 path to generated thumbnail image for video hybrid results';
