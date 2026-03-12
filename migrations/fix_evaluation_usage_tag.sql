-- Migration: Fix 'evaluation' usage_tag → 'validation'
-- Purpose: The bulk upload script incorrectly used 'evaluation' as a usage_tag,
--          which is outside the intended 'train'/'validation' constraint.
-- Date: 2026-03-11

-- Step 1: Convert all 'evaluation' tags to 'validation'
UPDATE datasets SET usage_tag = 'validation' WHERE usage_tag = 'evaluation';

-- Step 2: Verify no invalid values remain
-- SELECT count(*) FROM datasets WHERE usage_tag NOT IN ('train', 'validation');

-- Step 3: Re-apply CHECK constraint (may not have been applied to prod)
ALTER TABLE datasets DROP CONSTRAINT IF EXISTS datasets_usage_tag_check;
ALTER TABLE datasets ADD CONSTRAINT datasets_usage_tag_check CHECK (usage_tag IN ('train', 'validation'));
