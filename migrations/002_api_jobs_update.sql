-- ============================================================
-- Tyto API Jobs Table Update
-- Run this ONLY if you already have the api_jobs table from 001_api_tables.sql
-- This adds the new columns for the A3 API implementation
-- ============================================================

-- Add user_id column if it doesn't exist
DO $$ 
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM information_schema.columns 
        WHERE table_name = 'api_jobs' AND column_name = 'user_id'
    ) THEN
        ALTER TABLE api_jobs ADD COLUMN user_id UUID REFERENCES auth.users(id);
    END IF;
END $$;

-- Rename progress columns if they exist with old names
DO $$
BEGIN
    IF EXISTS (
        SELECT 1 FROM information_schema.columns 
        WHERE table_name = 'api_jobs' AND column_name = 'progress'
    ) THEN
        ALTER TABLE api_jobs RENAME COLUMN progress TO progress_current;
    END IF;
    
    IF EXISTS (
        SELECT 1 FROM information_schema.columns 
        WHERE table_name = 'api_jobs' AND column_name = 'frames_done'
    ) THEN
        ALTER TABLE api_jobs DROP COLUMN frames_done;
    END IF;
    
    IF EXISTS (
        SELECT 1 FROM information_schema.columns 
        WHERE table_name = 'api_jobs' AND column_name = 'frames_total'
    ) THEN
        ALTER TABLE api_jobs RENAME COLUMN frames_total TO progress_total;
    END IF;
END $$;

-- Add progress_current if missing
DO $$ 
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM information_schema.columns 
        WHERE table_name = 'api_jobs' AND column_name = 'progress_current'
    ) THEN
        ALTER TABLE api_jobs ADD COLUMN progress_current INTEGER DEFAULT 0;
    END IF;
END $$;

-- Add progress_total if missing
DO $$ 
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM information_schema.columns 
        WHERE table_name = 'api_jobs' AND column_name = 'progress_total'
    ) THEN
        ALTER TABLE api_jobs ADD COLUMN progress_total INTEGER DEFAULT 0;
    END IF;
END $$;

-- Replace old input columns with input_metadata JSONB
DO $$
BEGIN
    IF EXISTS (
        SELECT 1 FROM information_schema.columns 
        WHERE table_name = 'api_jobs' AND column_name = 'input_file_url'
    ) THEN
        ALTER TABLE api_jobs DROP COLUMN input_file_url;
    END IF;
    
    IF EXISTS (
        SELECT 1 FROM information_schema.columns 
        WHERE table_name = 'api_jobs' AND column_name = 'input_file_size_bytes'
    ) THEN
        ALTER TABLE api_jobs DROP COLUMN input_file_size_bytes;
    END IF;
    
    IF NOT EXISTS (
        SELECT 1 FROM information_schema.columns 
        WHERE table_name = 'api_jobs' AND column_name = 'input_metadata'
    ) THEN
        ALTER TABLE api_jobs ADD COLUMN input_metadata JSONB;
    END IF;
END $$;

-- Create index on user_id if not exists
CREATE INDEX IF NOT EXISTS idx_api_jobs_user ON api_jobs(user_id);

-- Update job_type default
ALTER TABLE api_jobs ALTER COLUMN job_type SET DEFAULT 'video_inference';

-- Update RLS policies for direct user_id access
DROP POLICY IF EXISTS "Users can view their own API jobs" ON api_jobs;
DROP POLICY IF EXISTS "Users can insert their own API jobs" ON api_jobs;
DROP POLICY IF EXISTS "Users can update their own API jobs" ON api_jobs;

CREATE POLICY "Users can view their own API jobs"
    ON api_jobs FOR SELECT
    USING (auth.uid() = user_id);

CREATE POLICY "Users can insert their own API jobs"
    ON api_jobs FOR INSERT
    WITH CHECK (auth.uid() = user_id);

CREATE POLICY "Users can update their own API jobs"
    ON api_jobs FOR UPDATE
    USING (auth.uid() = user_id);

-- ============================================================
-- VERIFICATION: Run this to check the updated schema
-- ============================================================
-- SELECT column_name, data_type, column_default 
-- FROM information_schema.columns 
-- WHERE table_name = 'api_jobs'
-- ORDER BY ordinal_position;
