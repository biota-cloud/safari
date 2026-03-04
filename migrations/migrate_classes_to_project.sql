-- Migration: Move classes from dataset-level to project-level
-- Run this in Supabase SQL Editor

-- Step 1: Ensure projects table has classes column (as text array to match datasets)
ALTER TABLE projects 
ADD COLUMN IF NOT EXISTS classes TEXT[] DEFAULT '{}';

-- Step 2: Aggregate unique classes from all datasets into their parent project
UPDATE projects p
SET classes = (
    SELECT ARRAY(
        SELECT DISTINCT unnest(d.classes) AS class_value
        FROM datasets d
        WHERE d.project_id = p.id
        AND d.classes IS NOT NULL
        AND array_length(d.classes, 1) > 0
        ORDER BY class_value
    )
)
WHERE EXISTS (
    SELECT 1 FROM datasets d 
    WHERE d.project_id = p.id 
    AND d.classes IS NOT NULL 
    AND array_length(d.classes, 1) > 0
);

-- Step 3: Verify the migration (optional)
-- SELECT p.id, p.name, p.classes FROM projects p ORDER BY p.created_at DESC;

