-- Migration: Remove legacy class_counts column from datasets table
-- 
-- This column is no longer used; class counts are now computed dynamically from:
-- - keyframes.annotations (for video datasets)
-- - images.annotations (for image datasets)
--
-- Run this after verifying the application works without the column.

ALTER TABLE datasets
DROP COLUMN IF EXISTS class_counts;

-- Verify the column was removed
-- SELECT column_name FROM information_schema.columns 
-- WHERE table_name = 'datasets' AND column_name = 'class_counts';
-- Should return 0 rows.
