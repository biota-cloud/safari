-- Migration: Add autolabel_jobs table for SAM3 auto-labeling feature
-- Created: 2025-12-31
-- Description: Track auto-labeling jobs, their status, logs, and detection results

-- Create autolabel_jobs table
CREATE TABLE IF NOT EXISTS autolabel_jobs (
  id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
  dataset_id UUID NOT NULL REFERENCES datasets(id) ON DELETE CASCADE,
  user_id UUID NOT NULL REFERENCES auth.users(id) ON DELETE CASCADE,
  status TEXT NOT NULL DEFAULT 'pending', -- pending, running, completed, failed
  prompt_type TEXT NOT NULL DEFAULT 'text', -- text, bbox, point (for future extensibility)
  prompt_value TEXT NOT NULL, -- text prompt or JSON for bbox/point
  class_id INT NOT NULL, -- Class ID to assign to all detections
  confidence FLOAT NOT NULL DEFAULT 0.25, -- Confidence threshold (0-1)
  logs TEXT DEFAULT '',
  detections_count INT DEFAULT 0, -- Total detections created
  processed_count INT DEFAULT 0, -- Number of images/keyframes processed
  target_count INT DEFAULT 0, -- Number of images/keyframes to process
  created_at TIMESTAMPTZ DEFAULT NOW(),
  started_at TIMESTAMPTZ,
  completed_at TIMESTAMPTZ,
  error_message TEXT
);

-- Indexes for performance
CREATE INDEX IF NOT EXISTS idx_autolabel_jobs_dataset ON autolabel_jobs(dataset_id);
CREATE INDEX IF NOT EXISTS idx_autolabel_jobs_status ON autolabel_jobs(status);
CREATE INDEX IF NOT EXISTS idx_autolabel_jobs_user ON autolabel_jobs(user_id);

-- Add comment
COMMENT ON TABLE autolabel_jobs IS 'Auto-labeling jobs for SAM3-based annotation generation';
