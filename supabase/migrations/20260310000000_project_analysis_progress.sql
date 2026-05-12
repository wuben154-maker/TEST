-- Project analysis progress (for refresh recovery - one running task per project)
CREATE TABLE IF NOT EXISTS project_analysis_progress (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    project_id UUID NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
    user_id UUID NOT NULL,
    request_id TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'running',
    user_input TEXT NOT NULL,
    thinking_steps JSONB DEFAULT '[]',
    task_plan JSONB,
    understanding JSONB,
    task_summary TEXT,
    conclusion TEXT,
    blocks JSONB DEFAULT '[]',
    error_detail TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE(project_id)
);
CREATE INDEX IF NOT EXISTS idx_progress_project_id ON project_analysis_progress(project_id);
