-- ============================================================
-- Tyto API Infrastructure Tables
-- Run this in Supabase SQL Editor
-- ============================================================

-- 1. API Models Table
-- Models explicitly promoted for external API access
CREATE TABLE api_models (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    training_run_id UUID REFERENCES training_runs(id) NOT NULL,
    project_id UUID REFERENCES projects(id) NOT NULL,
    user_id UUID REFERENCES auth.users(id) NOT NULL,
    
    -- Identity
    slug TEXT UNIQUE NOT NULL, -- e.g., "lynx-detector-v2"
    display_name TEXT NOT NULL,
    description TEXT,
    version INTEGER DEFAULT 1,
    
    -- Model Metadata (snapshot from training_run)
    model_type TEXT NOT NULL, -- "detection" | "classification"
    classes_snapshot JSONB NOT NULL, -- ["Lynx", "Fox", "Deer"]
    weights_r2_path TEXT NOT NULL, -- Path to best.pt in R2
    
    -- Status
    is_active BOOLEAN DEFAULT TRUE,
    is_public BOOLEAN DEFAULT FALSE, -- For future marketplace
    
    -- Usage Tracking
    total_requests BIGINT DEFAULT 0,
    last_used_at TIMESTAMPTZ,
    
    -- Timestamps
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX idx_api_models_slug ON api_models(slug);
CREATE INDEX idx_api_models_project ON api_models(project_id);
CREATE INDEX idx_api_models_user ON api_models(user_id);
CREATE INDEX idx_api_models_training_run ON api_models(training_run_id);

-- 2. API Keys Table
-- Manage client authentication tokens
CREATE TABLE api_keys (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID REFERENCES auth.users(id) NOT NULL,
    project_id UUID REFERENCES projects(id), -- NULL = user-wide key
    
    -- Key Data
    key_hash TEXT NOT NULL, -- SHA256 hash of the actual key
    key_prefix TEXT NOT NULL, -- First 8 chars for display (e.g., "safari_xxxx")
    name TEXT NOT NULL, -- User-given name
    
    -- Permissions
    scopes TEXT[] DEFAULT ARRAY['infer'], -- Future: ['infer', 'train', 'admin']
    
    -- Rate Limiting
    rate_limit_rpm INTEGER DEFAULT 60, -- Requests per minute
    monthly_quota INTEGER, -- NULL = unlimited
    requests_this_month INTEGER DEFAULT 0,
    
    -- Status
    is_active BOOLEAN DEFAULT TRUE,
    last_used_at TIMESTAMPTZ,
    expires_at TIMESTAMPTZ, -- NULL = never expires
    
    -- Timestamps
    created_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX idx_api_keys_hash ON api_keys(key_hash);
CREATE INDEX idx_api_keys_user ON api_keys(user_id);
CREATE INDEX idx_api_keys_project ON api_keys(project_id);

-- 3. API Jobs Table
-- Track async video processing jobs
CREATE TABLE api_jobs (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    api_key_id UUID REFERENCES api_keys(id) NOT NULL,
    api_model_id UUID REFERENCES api_models(id) NOT NULL,
    user_id UUID REFERENCES auth.users(id) NOT NULL,
    
    -- Job Details
    job_type TEXT NOT NULL DEFAULT 'video_inference', -- "video_inference" | "batch"
    status TEXT NOT NULL DEFAULT 'pending', -- "pending" | "processing" | "completed" | "failed"
    
    -- Progress Tracking
    progress_current INTEGER DEFAULT 0,
    progress_total INTEGER DEFAULT 0,
    
    -- Input/Output
    input_metadata JSONB, -- {filename, file_size_bytes, confidence, frame_skip, ...}
    result_json JSONB, -- Final predictions
    error_message TEXT,
    
    -- Timing
    started_at TIMESTAMPTZ,
    completed_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX idx_api_jobs_status ON api_jobs(status);
CREATE INDEX idx_api_jobs_key ON api_jobs(api_key_id);
CREATE INDEX idx_api_jobs_model ON api_jobs(api_model_id);
CREATE INDEX idx_api_jobs_user ON api_jobs(user_id);

-- 4. API Usage Logs Table
-- Detailed analytics and billing
CREATE TABLE api_usage_logs (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    api_key_id UUID REFERENCES api_keys(id) NOT NULL,
    api_model_id UUID REFERENCES api_models(id) NOT NULL,
    
    -- Request Details
    request_type TEXT NOT NULL, -- "image" | "video"
    file_size_bytes BIGINT,
    inference_time_ms INTEGER,
    prediction_count INTEGER,
    
    -- Response
    status_code INTEGER NOT NULL,
    error_message TEXT,
    
    -- Metadata
    client_ip TEXT,
    user_agent TEXT,
    
    created_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX idx_api_usage_logs_key ON api_usage_logs(api_key_id);
CREATE INDEX idx_api_usage_logs_model ON api_usage_logs(api_model_id);
CREATE INDEX idx_api_usage_logs_time ON api_usage_logs(created_at);

-- 5. Enable RLS (Row Level Security)
ALTER TABLE api_models ENABLE ROW LEVEL SECURITY;
ALTER TABLE api_keys ENABLE ROW LEVEL SECURITY;
ALTER TABLE api_jobs ENABLE ROW LEVEL SECURITY;
ALTER TABLE api_usage_logs ENABLE ROW LEVEL SECURITY;

-- 6. RLS Policies for api_models
CREATE POLICY "Users can view their own API models"
    ON api_models FOR SELECT
    USING (auth.uid() = user_id);

CREATE POLICY "Users can insert their own API models"
    ON api_models FOR INSERT
    WITH CHECK (auth.uid() = user_id);

CREATE POLICY "Users can update their own API models"
    ON api_models FOR UPDATE
    USING (auth.uid() = user_id);

CREATE POLICY "Users can delete their own API models"
    ON api_models FOR DELETE
    USING (auth.uid() = user_id);

-- 7. RLS Policies for api_keys
CREATE POLICY "Users can view their own API keys"
    ON api_keys FOR SELECT
    USING (auth.uid() = user_id);

CREATE POLICY "Users can insert their own API keys"
    ON api_keys FOR INSERT
    WITH CHECK (auth.uid() = user_id);

CREATE POLICY "Users can update their own API keys"
    ON api_keys FOR UPDATE
    USING (auth.uid() = user_id);

CREATE POLICY "Users can delete their own API keys"
    ON api_keys FOR DELETE
    USING (auth.uid() = user_id);

-- 8. RLS Policies for api_jobs (via direct user_id)
CREATE POLICY "Users can view their own API jobs"
    ON api_jobs FOR SELECT
    USING (auth.uid() = user_id);

CREATE POLICY "Users can insert their own API jobs"
    ON api_jobs FOR INSERT
    WITH CHECK (auth.uid() = user_id);

CREATE POLICY "Users can update their own API jobs"
    ON api_jobs FOR UPDATE
    USING (auth.uid() = user_id);

-- 9. RLS Policies for api_usage_logs (via api_key ownership)
CREATE POLICY "Users can view their own usage logs"
    ON api_usage_logs FOR SELECT
    USING (
        api_key_id IN (
            SELECT id FROM api_keys WHERE user_id = auth.uid()
        )
    );

-- 10. Service role bypass for API server
-- The API server uses service_role key, which bypasses RLS
-- This allows the API to validate keys and log usage for any user

-- 11. Trigger to update api_models.updated_at
CREATE OR REPLACE FUNCTION update_api_models_updated_at()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = NOW();
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER trigger_api_models_updated_at
    BEFORE UPDATE ON api_models
    FOR EACH ROW
    EXECUTE FUNCTION update_api_models_updated_at();

-- ============================================================
-- VERIFICATION: Run these queries to confirm tables exist
-- ============================================================
-- SELECT table_name FROM information_schema.tables 
-- WHERE table_schema = 'public' AND table_name LIKE 'api_%';
