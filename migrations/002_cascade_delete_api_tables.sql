-- ============================================================
-- Migration: Add ON DELETE CASCADE to API table foreign keys
-- This allows project deletion to automatically clean up
-- all dependent api_models, api_keys, api_jobs, api_usage_logs.
-- Run this in Supabase SQL Editor.
-- ============================================================

-- 1. api_models.project_id → projects(id) CASCADE
ALTER TABLE api_models
  DROP CONSTRAINT IF EXISTS api_models_project_id_fkey,
  ADD CONSTRAINT api_models_project_id_fkey
    FOREIGN KEY (project_id) REFERENCES projects(id) ON DELETE CASCADE;

-- 2. api_keys.project_id → projects(id) CASCADE
ALTER TABLE api_keys
  DROP CONSTRAINT IF EXISTS api_keys_project_id_fkey,
  ADD CONSTRAINT api_keys_project_id_fkey
    FOREIGN KEY (project_id) REFERENCES projects(id) ON DELETE CASCADE;

-- 3. api_jobs.api_model_id → api_models(id) CASCADE
ALTER TABLE api_jobs
  DROP CONSTRAINT IF EXISTS api_jobs_api_model_id_fkey,
  ADD CONSTRAINT api_jobs_api_model_id_fkey
    FOREIGN KEY (api_model_id) REFERENCES api_models(id) ON DELETE CASCADE;

-- 4. api_jobs.api_key_id → api_keys(id) CASCADE
ALTER TABLE api_jobs
  DROP CONSTRAINT IF EXISTS api_jobs_api_key_id_fkey,
  ADD CONSTRAINT api_jobs_api_key_id_fkey
    FOREIGN KEY (api_key_id) REFERENCES api_keys(id) ON DELETE CASCADE;

-- 5. api_usage_logs.api_model_id → api_models(id) CASCADE
ALTER TABLE api_usage_logs
  DROP CONSTRAINT IF EXISTS api_usage_logs_api_model_id_fkey,
  ADD CONSTRAINT api_usage_logs_api_model_id_fkey
    FOREIGN KEY (api_model_id) REFERENCES api_models(id) ON DELETE CASCADE;

-- 6. api_usage_logs.api_key_id → api_keys(id) CASCADE
ALTER TABLE api_usage_logs
  DROP CONSTRAINT IF EXISTS api_usage_logs_api_key_id_fkey,
  ADD CONSTRAINT api_usage_logs_api_key_id_fkey
    FOREIGN KEY (api_key_id) REFERENCES api_keys(id) ON DELETE CASCADE;

-- ============================================================
-- After running this, deleting a project will automatically
-- cascade to: api_models, api_keys, api_jobs, api_usage_logs
-- ============================================================
