-- =============================================================================
-- Model Evaluation Tables
-- Run in Supabase SQL Editor
-- =============================================================================

-- ─── evaluation_runs ─────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS evaluation_runs (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    project_id UUID NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
    user_id UUID NOT NULL REFERENCES profiles(id) ON DELETE CASCADE,
    model_id UUID REFERENCES models(id) ON DELETE SET NULL,
    model_name TEXT NOT NULL,
    dataset_id UUID REFERENCES datasets(id) ON DELETE SET NULL,
    dataset_name TEXT NOT NULL,
    classes_snapshot TEXT[] DEFAULT '{}',
    confidence_threshold DOUBLE PRECISION DEFAULT 0.25,
    iou_threshold DOUBLE PRECISION DEFAULT 0.5,
    -- Aggregate metrics
    overall_metrics JSONB DEFAULT '{}'::jsonb,
    per_class_metrics JSONB DEFAULT '{}'::jsonb,
    confusion_matrix JSONB DEFAULT '[]'::jsonb,
    -- Job tracking
    status TEXT DEFAULT 'pending',
    error_message TEXT,
    total_images INTEGER DEFAULT 0,
    processed_images INTEGER DEFAULT 0,
    started_at TIMESTAMPTZ,
    completed_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ DEFAULT now()
);
ALTER TABLE evaluation_runs ENABLE ROW LEVEL SECURITY;

-- ─── evaluation_predictions ──────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS evaluation_predictions (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    evaluation_run_id UUID NOT NULL REFERENCES evaluation_runs(id) ON DELETE CASCADE,
    image_id UUID REFERENCES images(id) ON DELETE SET NULL,
    image_filename TEXT NOT NULL,
    image_r2_path TEXT,
    ground_truth JSONB DEFAULT '[]'::jsonb,
    predictions JSONB DEFAULT '[]'::jsonb,
    matches JSONB DEFAULT '[]'::jsonb,
    tp_count INTEGER DEFAULT 0,
    fp_count INTEGER DEFAULT 0,
    fn_count INTEGER DEFAULT 0,
    created_at TIMESTAMPTZ DEFAULT now()
);
ALTER TABLE evaluation_predictions ENABLE ROW LEVEL SECURITY;


-- =============================================================================
-- INDEXES
-- =============================================================================

CREATE INDEX IF NOT EXISTS idx_evaluation_runs_project_id ON evaluation_runs(project_id);
CREATE INDEX IF NOT EXISTS idx_evaluation_runs_user_id ON evaluation_runs(user_id);
CREATE INDEX IF NOT EXISTS idx_evaluation_predictions_run_id ON evaluation_predictions(evaluation_run_id);


-- =============================================================================
-- RLS POLICIES
-- =============================================================================

-- evaluation_runs: project-level access
CREATE POLICY "Evaluation run access" ON evaluation_runs
    FOR ALL USING (user_can_access_project(project_id));

-- evaluation_predictions: access via parent run's project
CREATE POLICY "Evaluation prediction access" ON evaluation_predictions
    FOR ALL USING (
        EXISTS (
            SELECT 1 FROM evaluation_runs er
            WHERE er.id = evaluation_run_id
            AND user_can_access_project(er.project_id)
        )
    );
