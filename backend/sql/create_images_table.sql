-- =============================================================================
-- IMAGES TABLE — Phase 1.2: Image Upload System
-- Run this in Supabase SQL Editor
-- =============================================================================

-- Create images table for storing uploaded image metadata
CREATE TABLE images (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    project_id UUID REFERENCES projects(id) ON DELETE CASCADE,
    filename TEXT NOT NULL,
    r2_path TEXT NOT NULL,
    width INTEGER,
    height INTEGER,
    labeled BOOLEAN DEFAULT FALSE,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

-- Enable Row Level Security
ALTER TABLE images ENABLE ROW LEVEL SECURITY;

-- Policy: Users can only access images in their own projects
CREATE POLICY "Users can CRUD own project images" ON images
    FOR ALL USING (
        project_id IN (SELECT id FROM projects WHERE user_id = auth.uid())
    );

-- Create index for faster project-based queries
CREATE INDEX idx_images_project_id ON images(project_id);

-- Optional: Create index for labeled status (useful for filtering)
CREATE INDEX idx_images_labeled ON images(project_id, labeled);
