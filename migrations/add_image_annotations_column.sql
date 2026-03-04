-- Migration: Add annotations JSONB column to images table
-- Purpose: Store annotations in Supabase for fast retrieval (mirrors keyframes table)
-- Date: 2026-01-08

-- Add annotations column (nullable for gradual migration from R2)
ALTER TABLE images 
ADD COLUMN IF NOT EXISTS annotations JSONB DEFAULT NULL;

-- Add GIN index for better query performance on JSONB
CREATE INDEX IF NOT EXISTS idx_images_annotations 
ON images USING GIN (annotations);

-- Add constraint to ensure valid JSON array
ALTER TABLE images
ADD CONSTRAINT annotations_is_array CHECK (
  annotations IS NULL OR jsonb_typeof(annotations) = 'array'
);

-- Add comment for documentation
COMMENT ON COLUMN images.annotations IS 
'JSONB array of annotation objects. Primary storage for labeling UI. Synced to R2 as YOLO format for training exports.';
