-- =============================================================================
-- SAFARI Database Schema (Supabase)
-- Run this in the Supabase SQL Editor for a fresh deployment.
-- Order: extensions → trigger functions → tables → helper functions → RLS → triggers
-- =============================================================================

-- ─── Extensions ──────────────────────────────────────────────────────────────
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";

-- ─── Trigger Functions (plpgsql — safe to create before tables) ──────────────

CREATE OR REPLACE FUNCTION update_api_models_updated_at()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = NOW();
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE OR REPLACE FUNCTION handle_new_user()
RETURNS TRIGGER AS $$
BEGIN
  INSERT INTO public.profiles (id, email, role)
  VALUES (NEW.id, NEW.email, 'user')
  ON CONFLICT (id) DO NOTHING;
  RETURN NEW;
END;
$$ LANGUAGE plpgsql SECURITY DEFINER;


-- =============================================================================
-- TABLES (ordered by dependency: no forward references)
-- =============================================================================

-- ─── profiles ────────────────────────────────────────────────────────────────
CREATE TABLE profiles (
    id UUID PRIMARY KEY,  -- matches auth.users.id
    email TEXT NOT NULL,
    display_name TEXT,
    created_at TIMESTAMPTZ DEFAULT now(),
    tier TEXT DEFAULT 'free',
    api_key TEXT,
    preferences JSONB DEFAULT '{}'::jsonb,
    local_gpu_machines JSONB DEFAULT '[]'::jsonb,
    role TEXT DEFAULT 'user'
);
ALTER TABLE profiles ENABLE ROW LEVEL SECURITY;
GRANT INSERT ON profiles TO service_role;  -- Required for handle_new_user trigger

-- ─── projects ────────────────────────────────────────────────────────────────
CREATE TABLE projects (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID REFERENCES profiles(id) ON DELETE CASCADE,
    name TEXT NOT NULL,
    description TEXT,
    created_at TIMESTAMPTZ DEFAULT now(),
    classes TEXT[] DEFAULT '{}',
    processing_target TEXT DEFAULT 'cloud',
    local_gpu_config JSONB,
    last_accessed_at TIMESTAMPTZ,
    thumbnail_r2_path TEXT,
    is_company BOOLEAN DEFAULT false
);
ALTER TABLE projects ENABLE ROW LEVEL SECURITY;

-- ─── project_members ─────────────────────────────────────────────────────────
CREATE TABLE project_members (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    project_id UUID REFERENCES projects(id) ON DELETE CASCADE,
    user_id UUID REFERENCES profiles(id) ON DELETE CASCADE,
    role TEXT DEFAULT 'member',
    added_at TIMESTAMPTZ DEFAULT now(),
    UNIQUE(project_id, user_id)
);
ALTER TABLE project_members ENABLE ROW LEVEL SECURITY;

-- ─── datasets ────────────────────────────────────────────────────────────────
CREATE TABLE datasets (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID REFERENCES profiles(id) ON DELETE CASCADE,
    name TEXT NOT NULL,
    created_at TIMESTAMPTZ DEFAULT now(),
    project_id UUID NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
    type TEXT DEFAULT 'image',
    description TEXT,
    last_trained_at TIMESTAMPTZ,
    active_model_id UUID,  -- FK added after models table
    class_counts JSONB DEFAULT '{}'::jsonb,
    usage_tag TEXT NOT NULL DEFAULT 'train',
    last_accessed_at TIMESTAMPTZ,
    thumbnail_r2_path TEXT
);
ALTER TABLE datasets ENABLE ROW LEVEL SECURITY;

-- ─── images ──────────────────────────────────────────────────────────────────
CREATE TABLE images (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    dataset_id UUID REFERENCES datasets(id) ON DELETE CASCADE,
    filename TEXT NOT NULL,
    r2_path TEXT NOT NULL,
    width INTEGER,
    height INTEGER,
    labeled BOOLEAN DEFAULT false,
    created_at TIMESTAMPTZ DEFAULT now(),
    annotation_count INTEGER DEFAULT 0,
    annotations JSONB
);
ALTER TABLE images ENABLE ROW LEVEL SECURITY;

-- ─── videos ──────────────────────────────────────────────────────────────────
CREATE TABLE videos (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    dataset_id UUID REFERENCES datasets(id) ON DELETE CASCADE,
    filename TEXT NOT NULL,
    r2_path TEXT NOT NULL,
    duration_seconds DOUBLE PRECISION,
    frame_count INTEGER,
    fps DOUBLE PRECISION,
    width INTEGER,
    height INTEGER,
    thumbnail_path TEXT,
    created_at TIMESTAMPTZ DEFAULT now(),
    proxy_r2_path TEXT
);
ALTER TABLE videos ENABLE ROW LEVEL SECURITY;

-- ─── keyframes ───────────────────────────────────────────────────────────────
CREATE TABLE keyframes (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    video_id UUID REFERENCES videos(id) ON DELETE CASCADE,
    frame_number INTEGER NOT NULL,
    "timestamp" DOUBLE PRECISION NOT NULL,
    is_empty BOOLEAN DEFAULT false,
    thumbnail_path TEXT,
    annotation_count INTEGER DEFAULT 0,
    created_at TIMESTAMPTZ DEFAULT now(),
    annotations JSONB,
    full_image_path TEXT
);
ALTER TABLE keyframes ENABLE ROW LEVEL SECURITY;

-- ─── training_runs ───────────────────────────────────────────────────────────
CREATE TABLE training_runs (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    dataset_id UUID REFERENCES datasets(id) ON DELETE CASCADE,
    user_id UUID REFERENCES profiles(id) ON DELETE CASCADE,
    status TEXT DEFAULT 'pending',
    target TEXT DEFAULT 'cloud',
    claimed_by TEXT,
    config JSONB NOT NULL,
    metrics JSONB,
    artifacts_r2_prefix TEXT,
    error_message TEXT,
    started_at TIMESTAMPTZ,
    completed_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ DEFAULT now(),
    project_id UUID REFERENCES projects(id) ON DELETE CASCADE,
    dataset_ids UUID[] DEFAULT '{}',
    logs TEXT,
    alias TEXT,
    notes TEXT,
    tags TEXT[] DEFAULT '{}',
    dataset_names TEXT[] DEFAULT '{}',
    classes_snapshot TEXT[] DEFAULT '{}',
    parent_run_id UUID REFERENCES training_runs(id) ON DELETE SET NULL,
    model_type TEXT DEFAULT 'detection',
    top1_accuracy DOUBLE PRECISION,
    top5_accuracy DOUBLE PRECISION
);
ALTER TABLE training_runs ENABLE ROW LEVEL SECURITY;

-- ─── models ──────────────────────────────────────────────────────────────────
CREATE TABLE models (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    training_run_id UUID REFERENCES training_runs(id) ON DELETE CASCADE,
    dataset_id UUID REFERENCES datasets(id) ON DELETE CASCADE,
    user_id UUID REFERENCES profiles(id) ON DELETE CASCADE,
    project_id UUID REFERENCES projects(id) ON DELETE CASCADE,
    name TEXT NOT NULL,
    weights_path TEXT NOT NULL,
    metrics JSONB,
    is_active BOOLEAN DEFAULT false,
    created_at TIMESTAMPTZ DEFAULT now(),
    volume_path TEXT,
    model_type TEXT DEFAULT 'detection',
    top1_accuracy DOUBLE PRECISION,
    top5_accuracy DOUBLE PRECISION
);
ALTER TABLE models ENABLE ROW LEVEL SECURITY;

-- Add deferred FK from datasets → models
ALTER TABLE datasets
    ADD CONSTRAINT datasets_active_model_id_fkey
    FOREIGN KEY (active_model_id) REFERENCES models(id) ON DELETE SET NULL;

-- ─── inference_results ───────────────────────────────────────────────────────
CREATE TABLE inference_results (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID REFERENCES profiles(id) ON DELETE CASCADE,
    model_id UUID REFERENCES models(id) ON DELETE SET NULL,
    model_name TEXT NOT NULL,
    input_type TEXT NOT NULL,
    input_filename TEXT NOT NULL,
    input_r2_path TEXT NOT NULL,
    video_start_time DOUBLE PRECISION,
    video_end_time DOUBLE PRECISION,
    video_fps DOUBLE PRECISION,
    video_total_frames INTEGER,
    confidence_threshold DOUBLE PRECISION NOT NULL DEFAULT 0.25,
    predictions_json JSONB NOT NULL,
    labels_r2_path TEXT,
    inference_duration_ms INTEGER,
    detection_count INTEGER,
    created_at TIMESTAMPTZ DEFAULT now(),
    progress_current INTEGER DEFAULT 0,
    progress_total INTEGER DEFAULT 0,
    inference_status TEXT DEFAULT 'pending',
    batch_images JSONB,
    thumbnail_r2_path TEXT,
    progress_status TEXT DEFAULT 'queued',
    inference_settings JSONB DEFAULT '{}'::jsonb
);
ALTER TABLE inference_results ENABLE ROW LEVEL SECURITY;

-- ─── autolabel_jobs ──────────────────────────────────────────────────────────
CREATE TABLE autolabel_jobs (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    dataset_id UUID NOT NULL REFERENCES datasets(id) ON DELETE CASCADE,
    user_id UUID NOT NULL,
    status TEXT NOT NULL DEFAULT 'pending',
    prompt_type TEXT NOT NULL DEFAULT 'text',
    prompt_value TEXT NOT NULL,
    class_id INTEGER NOT NULL,
    confidence DOUBLE PRECISION NOT NULL DEFAULT 0.25,
    logs TEXT DEFAULT '',
    detections_count INTEGER DEFAULT 0,
    processed_count INTEGER DEFAULT 0,
    target_count INTEGER DEFAULT 0,
    created_at TIMESTAMPTZ DEFAULT now(),
    started_at TIMESTAMPTZ,
    completed_at TIMESTAMPTZ,
    error_message TEXT,
    model_id UUID REFERENCES models(id) ON DELETE SET NULL,
    selected_video_ids UUID[]
);
ALTER TABLE autolabel_jobs ENABLE ROW LEVEL SECURITY;

-- ─── api_keys ────────────────────────────────────────────────────────────────
CREATE TABLE api_keys (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID NOT NULL,
    project_id UUID REFERENCES projects(id) ON DELETE CASCADE,
    key_hash TEXT NOT NULL,
    key_prefix TEXT NOT NULL,
    name TEXT NOT NULL,
    scopes TEXT[] DEFAULT ARRAY['infer'],
    rate_limit_rpm INTEGER DEFAULT 60,
    monthly_quota INTEGER,
    requests_this_month INTEGER DEFAULT 0,
    is_active BOOLEAN DEFAULT true,
    last_used_at TIMESTAMPTZ,
    expires_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ DEFAULT now()
);
ALTER TABLE api_keys ENABLE ROW LEVEL SECURITY;

-- ─── api_models ──────────────────────────────────────────────────────────────
CREATE TABLE api_models (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    training_run_id UUID NOT NULL REFERENCES training_runs(id),
    project_id UUID NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
    user_id UUID NOT NULL,
    slug TEXT NOT NULL,
    display_name TEXT NOT NULL,
    description TEXT,
    version INTEGER DEFAULT 1,
    model_type TEXT NOT NULL,
    classes_snapshot JSONB NOT NULL,
    weights_r2_path TEXT NOT NULL,
    is_active BOOLEAN DEFAULT true,
    is_public BOOLEAN DEFAULT false,
    total_requests BIGINT DEFAULT 0,
    last_used_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ DEFAULT now(),
    updated_at TIMESTAMPTZ DEFAULT now(),
    sam3_prompt TEXT DEFAULT 'animal',
    sam3_confidence DOUBLE PRECISION DEFAULT 0.5,
    backbone TEXT DEFAULT 'yolo',
    sam3_imgsz INTEGER
);
ALTER TABLE api_models ENABLE ROW LEVEL SECURITY;

-- ─── api_jobs ────────────────────────────────────────────────────────────────
CREATE TABLE api_jobs (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    api_key_id UUID NOT NULL REFERENCES api_keys(id) ON DELETE CASCADE,
    api_model_id UUID NOT NULL REFERENCES api_models(id) ON DELETE CASCADE,
    job_type TEXT NOT NULL DEFAULT 'video',
    status TEXT NOT NULL DEFAULT 'pending',
    progress INTEGER DEFAULT 0,
    frames_done INTEGER DEFAULT 0,
    frames_total INTEGER,
    input_file_url TEXT,
    input_file_size_bytes BIGINT,
    result_json JSONB,
    error_message TEXT,
    started_at TIMESTAMPTZ,
    completed_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ DEFAULT now(),
    input_metadata JSONB,
    user_id UUID,
    progress_current INTEGER DEFAULT 0,
    progress_total INTEGER DEFAULT 0
);
ALTER TABLE api_jobs ENABLE ROW LEVEL SECURITY;

-- ─── api_usage_logs ──────────────────────────────────────────────────────────
CREATE TABLE api_usage_logs (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    api_key_id UUID NOT NULL REFERENCES api_keys(id) ON DELETE CASCADE,
    api_model_id UUID NOT NULL REFERENCES api_models(id) ON DELETE CASCADE,
    request_type TEXT NOT NULL,
    file_size_bytes BIGINT,
    inference_time_ms INTEGER,
    prediction_count INTEGER,
    status_code INTEGER NOT NULL,
    error_message TEXT,
    client_ip TEXT,
    user_agent TEXT,
    created_at TIMESTAMPTZ DEFAULT now()
);
ALTER TABLE api_usage_logs ENABLE ROW LEVEL SECURITY;


-- =============================================================================
-- INDEXES
-- =============================================================================

CREATE INDEX idx_images_dataset_id ON images(dataset_id);
CREATE INDEX idx_videos_dataset_id ON videos(dataset_id);
CREATE INDEX idx_keyframes_video_id ON keyframes(video_id);
CREATE INDEX idx_datasets_project_id ON datasets(project_id);
CREATE INDEX idx_training_runs_project_id ON training_runs(project_id);
CREATE INDEX idx_training_runs_dataset_id ON training_runs(dataset_id);
CREATE INDEX idx_models_project_id ON models(project_id);
CREATE INDEX idx_inference_results_user_id ON inference_results(user_id);
CREATE INDEX idx_autolabel_jobs_dataset_id ON autolabel_jobs(dataset_id);
CREATE INDEX idx_api_keys_user_id ON api_keys(user_id);
CREATE INDEX idx_api_models_project_id ON api_models(project_id);
CREATE INDEX idx_api_jobs_api_key_id ON api_jobs(api_key_id);
CREATE INDEX idx_api_usage_logs_api_key_id ON api_usage_logs(api_key_id);


-- =============================================================================
-- HELPER FUNCTIONS (created after tables — SQL functions validate references)
-- =============================================================================

CREATE OR REPLACE FUNCTION is_admin()
RETURNS BOOLEAN AS $$
  SELECT EXISTS (
    SELECT 1 FROM profiles WHERE id = auth.uid() AND role = 'admin'
  );
$$ LANGUAGE sql SECURITY DEFINER;

CREATE OR REPLACE FUNCTION user_can_access_project(p_id UUID)
RETURNS BOOLEAN AS $$
  SELECT
    EXISTS (SELECT 1 FROM projects WHERE id = p_id AND user_id = auth.uid())
    OR EXISTS (SELECT 1 FROM project_members WHERE project_id = p_id AND user_id = auth.uid())
    OR (EXISTS (SELECT 1 FROM projects WHERE id = p_id AND is_company = TRUE) AND is_admin());
$$ LANGUAGE sql SECURITY DEFINER;

CREATE OR REPLACE FUNCTION project_id_for_dataset(d_id UUID)
RETURNS UUID AS $$
  SELECT project_id FROM datasets WHERE id = d_id;
$$ LANGUAGE sql SECURITY DEFINER;

CREATE OR REPLACE FUNCTION project_id_for_video(v_id UUID)
RETURNS UUID AS $$
  SELECT d.project_id FROM datasets d JOIN videos v ON d.id = v.dataset_id WHERE v.id = v_id;
$$ LANGUAGE sql SECURITY DEFINER;


-- =============================================================================
-- RLS POLICIES
-- =============================================================================

-- profiles
CREATE POLICY "Users can read profiles" ON profiles FOR SELECT USING ((auth.uid() = id) OR is_admin());
CREATE POLICY "Users can insert own profile" ON profiles FOR INSERT WITH CHECK (auth.uid() = id);
CREATE POLICY "Users can update own profile" ON profiles FOR UPDATE USING (auth.uid() = id);

-- projects
CREATE POLICY "Project read" ON projects FOR SELECT USING (user_can_access_project(id));
CREATE POLICY "Project create" ON projects FOR INSERT WITH CHECK (auth.uid() = user_id);
CREATE POLICY "Project modify" ON projects FOR UPDATE USING ((auth.uid() = user_id) OR is_admin());
CREATE POLICY "Project delete" ON projects FOR DELETE USING ((auth.uid() = user_id) OR is_admin());

-- project_members
CREATE POLICY "Admins manage memberships" ON project_members FOR ALL USING (is_admin());
CREATE POLICY "Members see own memberships" ON project_members FOR SELECT USING ((auth.uid() = user_id) OR is_admin());

-- datasets
CREATE POLICY "Dataset access" ON datasets FOR ALL USING (user_can_access_project(project_id));

-- images
CREATE POLICY "Image access" ON images FOR ALL USING (user_can_access_project(project_id_for_dataset(dataset_id)));

-- videos
CREATE POLICY "Video access" ON videos FOR ALL USING (user_can_access_project(project_id_for_dataset(dataset_id)));

-- keyframes
CREATE POLICY "Keyframe access" ON keyframes FOR ALL USING (user_can_access_project(project_id_for_video(video_id)));

-- training_runs
CREATE POLICY "Training run access" ON training_runs FOR ALL USING (user_can_access_project(project_id));

-- models
CREATE POLICY "Model access" ON models FOR ALL USING (
    (user_id = auth.uid()) OR ((dataset_id IS NOT NULL) AND user_can_access_project(project_id_for_dataset(dataset_id)))
);

-- inference_results
CREATE POLICY "Users can CRUD own inference results" ON inference_results FOR ALL USING (auth.uid() = user_id);

-- autolabel_jobs
CREATE POLICY "Autolabel job access" ON autolabel_jobs FOR ALL USING (user_can_access_project(project_id_for_dataset(dataset_id)));

-- api_keys
CREATE POLICY "Users can view their own API keys" ON api_keys FOR SELECT USING (auth.uid() = user_id);
CREATE POLICY "Users can insert their own API keys" ON api_keys FOR INSERT WITH CHECK (auth.uid() = user_id);
CREATE POLICY "Users can update their own API keys" ON api_keys FOR UPDATE USING (auth.uid() = user_id);
CREATE POLICY "Users can delete their own API keys" ON api_keys FOR DELETE USING (auth.uid() = user_id);

-- api_models
CREATE POLICY "Users can view their own API models" ON api_models FOR SELECT USING (auth.uid() = user_id);
CREATE POLICY "Users can insert their own API models" ON api_models FOR INSERT WITH CHECK (auth.uid() = user_id);
CREATE POLICY "Users can update their own API models" ON api_models FOR UPDATE USING (auth.uid() = user_id);
CREATE POLICY "Users can delete their own API models" ON api_models FOR DELETE USING (auth.uid() = user_id);

-- api_jobs
CREATE POLICY "Users can view their own API jobs" ON api_jobs FOR SELECT USING (
    api_key_id IN (SELECT id FROM api_keys WHERE user_id = auth.uid())
);
CREATE POLICY "Users can insert their own API jobs" ON api_jobs FOR INSERT WITH CHECK (
    api_key_id IN (SELECT id FROM api_keys WHERE user_id = auth.uid())
);

-- api_usage_logs
CREATE POLICY "Users can view their own usage logs" ON api_usage_logs FOR SELECT USING (
    api_key_id IN (SELECT id FROM api_keys WHERE user_id = auth.uid())
);


-- =============================================================================
-- TRIGGERS
-- =============================================================================

-- Auto-update updated_at on api_models
CREATE TRIGGER trigger_api_models_updated_at
    BEFORE UPDATE ON api_models
    FOR EACH ROW EXECUTE FUNCTION update_api_models_updated_at();

-- Auto-create profile when a new user signs up via Supabase Auth
CREATE TRIGGER on_auth_user_created
    AFTER INSERT ON auth.users
    FOR EACH ROW EXECUTE FUNCTION public.handle_new_user();
