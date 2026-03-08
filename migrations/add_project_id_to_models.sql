-- =============================================================================
-- Migration: Add project_id to models table for team model sharing
-- Run this in the Supabase SQL Editor.
-- =============================================================================

-- 1. Add the column
ALTER TABLE models ADD COLUMN project_id UUID REFERENCES projects(id) ON DELETE CASCADE;

-- 2. Backfill from datasets
UPDATE models
SET project_id = d.project_id
FROM datasets d
WHERE models.dataset_id = d.id;

-- 3. Index for fast project-scoped queries
CREATE INDEX idx_models_project_id ON models(project_id);
