-- Migration: Add thumbnail_r2_path to projects and datasets
-- Purpose: Support custom thumbnails generated from annotation context menu
-- Run via: Supabase SQL Editor

-- Add thumbnail column to projects table
ALTER TABLE projects 
ADD COLUMN IF NOT EXISTS thumbnail_r2_path TEXT;

COMMENT ON COLUMN projects.thumbnail_r2_path IS 'R2 path to custom project thumbnail (from annotated label)';

-- Add thumbnail column to datasets table
ALTER TABLE datasets 
ADD COLUMN IF NOT EXISTS thumbnail_r2_path TEXT;

COMMENT ON COLUMN datasets.thumbnail_r2_path IS 'R2 path to custom dataset thumbnail (from annotated label)';
