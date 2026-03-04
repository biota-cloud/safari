-- Migration: Add annotations JSONB column to keyframes table
-- Purpose: Store annotations in Supabase for fast retrieval (hybrid storage with R2)
-- Date: 2025-12-30

-- Add annotations column (nullable for gradual migration)
ALTER TABLE keyframes 
ADD COLUMN IF NOT EXISTS annotations JSONB DEFAULT NULL;

-- Add index for better query performance
CREATE INDEX IF NOT EXISTS idx_keyframes_annotations 
ON keyframes USING GIN (annotations);

-- Add constraint to ensure valid JSON array
ALTER TABLE keyframes
ADD CONSTRAINT IF NOT EXISTS annotations_is_array CHECK (
  annotations IS NULL OR jsonb_typeof(annotations) = 'array'
);

-- Add comment for documentation
COMMENT ON COLUMN keyframes.annotations IS 
'JSONB array of annotation objects. Primary storage for labeling UI. Synced to R2 as YOLO format for training exports.';
