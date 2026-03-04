-- Add proxy_r2_path column to videos table
-- Stores the R2 path of the web-optimized proxy (720p, libx264, CRF 28)
-- Null means no proxy exists (e.g., video ≤ 720p or uploaded before this migration)
ALTER TABLE videos ADD COLUMN IF NOT EXISTS proxy_r2_path TEXT;
