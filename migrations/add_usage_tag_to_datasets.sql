-- Migration: Add usage_tag column to datasets table
-- Purpose: Allow datasets to be tagged as 'train' or 'validation' for explicit train/val split
-- Date: 2026-01-04

-- Add usage_tag column with default 'train'
ALTER TABLE datasets
ADD COLUMN usage_tag TEXT DEFAULT 'train';

-- Update existing datasets to 'train' (in case default didn't apply to existing rows)
UPDATE datasets SET usage_tag = 'train' WHERE usage_tag IS NULL;

-- Add constraint to ensure only valid values
ALTER TABLE datasets
ADD CONSTRAINT datasets_usage_tag_check CHECK (usage_tag IN ('train', 'validation'));

-- Make column NOT NULL after setting defaults
ALTER TABLE datasets ALTER COLUMN usage_tag SET NOT NULL;

-- Add index for filtering by usage tag
CREATE INDEX idx_datasets_usage_tag ON datasets(usage_tag);

-- Verify migration
-- SELECT id, name, usage_tag FROM datasets LIMIT 10;
