-- Local PostgreSQL Database Initialization Script
-- Run this script to set up the local database for development
--
-- Prerequisites:
--   1. PostgreSQL 12+ installed and running
--   2. Create database: createdb -U postgres secmanus
--
-- Usage:
--   psql -U postgres -d secmanus -f scripts/db/init_local_db.sql
--   Or: psql -U postgres -h localhost -d secmanus -f scripts/db/init_local_db.sql

-- Enable extensions
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";
CREATE EXTENSION IF NOT EXISTS "pgcrypto";

-- ============================================
-- TABLES (order matters: profiles -> projects -> messages)
-- ============================================

-- Profiles table (local auth: email + password_hash)
CREATE TABLE IF NOT EXISTS profiles (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    user_id UUID NOT NULL UNIQUE,
    email TEXT UNIQUE,
    password_hash TEXT,
    username TEXT,
    avatar_url TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- Projects table
CREATE TABLE IF NOT EXISTS projects (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    user_id UUID NOT NULL,
    title TEXT NOT NULL DEFAULT 'New Conversation',
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    -- Realtime context-usage snapshot (feature: realtime-context-usage-indicator).
    context_usage JSONB,
    context_usage_updated_at TIMESTAMPTZ
);

-- Messages table
CREATE TABLE IF NOT EXISTS messages (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    project_id UUID NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
    user_id UUID NOT NULL,
    request_id TEXT,
    content TEXT NOT NULL DEFAULT '',
    type TEXT NOT NULL,
    reasoning TEXT,
    thinking_steps JSONB,
    blocks JSONB,
    workspace_title TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- Shared reports table
CREATE TABLE IF NOT EXISTS shared_reports (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    user_id UUID,
    title TEXT NOT NULL DEFAULT 'Security Analysis Report',
    blocks JSONB NOT NULL,
    share_token TEXT NOT NULL DEFAULT encode(gen_random_bytes(16), 'hex'),
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    expires_at TIMESTAMPTZ DEFAULT (now() + interval '7 days')
);

-- LangGraph checkpoints (for conversation persistence)
CREATE TABLE IF NOT EXISTS langgraph_checkpoints (
    thread_id TEXT NOT NULL,
    checkpoint_ns TEXT NOT NULL DEFAULT '',
    checkpoint_id TEXT NOT NULL,
    checkpoint JSONB NOT NULL,
    parent_checkpoint_id TEXT,
    metadata JSONB DEFAULT '{}',
    created_at TIMESTAMPTZ DEFAULT now(),
    PRIMARY KEY (thread_id, checkpoint_ns, checkpoint_id)
);

-- Session parameters (long-term memory, encrypted param storage)
CREATE TABLE IF NOT EXISTS session_parameters (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    session_id TEXT NOT NULL,
    user_id UUID,
    param_name TEXT NOT NULL,
    param_value TEXT NOT NULL,
    param_type TEXT NOT NULL DEFAULT 'text',
    encrypted BOOLEAN NOT NULL DEFAULT true,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    expires_at TIMESTAMPTZ,
    metadata JSONB DEFAULT '{}',
    UNIQUE(session_id, param_name)
);

-- Parameter callbacks (async parameter collection queue)
CREATE TABLE IF NOT EXISTS parameter_callbacks (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    session_id TEXT NOT NULL,
    request_id TEXT NOT NULL UNIQUE,
    status TEXT NOT NULL DEFAULT 'pending',
    parameters JSONB,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    completed_at TIMESTAMPTZ,
    expires_at TIMESTAMPTZ DEFAULT (now() + interval '30 minutes')
);

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
    timeline JSONB NOT NULL DEFAULT '[]'::jsonb,
    error_detail TEXT,
    ui_language TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE(project_id)
);
CREATE INDEX IF NOT EXISTS idx_progress_project_id ON project_analysis_progress(project_id);

ALTER TABLE project_analysis_progress
  ADD COLUMN IF NOT EXISTS timeline JSONB NOT NULL DEFAULT '[]'::jsonb;

ALTER TABLE project_analysis_progress
  ADD COLUMN IF NOT EXISTS ui_language TEXT;

DO $$
BEGIN
    -- Backward-compatible schema patch for existing local databases.
    IF NOT EXISTS (
        SELECT 1
        FROM information_schema.columns
        WHERE table_name = 'messages' AND column_name = 'request_id'
    ) THEN
        ALTER TABLE messages ADD COLUMN request_id TEXT;
    END IF;

    IF NOT EXISTS (
        SELECT 1
        FROM information_schema.columns
        WHERE table_name = 'messages' AND column_name = 'workspace_title'
    ) THEN
        ALTER TABLE messages ADD COLUMN workspace_title TEXT;
    END IF;

    RAISE NOTICE 'Backward-compatible columns checked/added successfully.';
END 
$$;

-- ============================================
-- INDEXES
-- ============================================

CREATE INDEX IF NOT EXISTS idx_profiles_email ON profiles(email);
CREATE INDEX IF NOT EXISTS idx_projects_user_id ON projects(user_id);
CREATE INDEX IF NOT EXISTS idx_projects_updated_at ON projects(updated_at DESC);
CREATE INDEX IF NOT EXISTS idx_messages_project_id ON messages(project_id);
CREATE INDEX IF NOT EXISTS idx_messages_created_at ON messages(created_at);
CREATE UNIQUE INDEX IF NOT EXISTS uq_messages_project_request_type
    ON messages(project_id, request_id, type);
CREATE INDEX IF NOT EXISTS idx_shared_reports_token ON shared_reports(share_token);
CREATE INDEX IF NOT EXISTS idx_checkpoints_thread_id ON langgraph_checkpoints(thread_id);
CREATE INDEX IF NOT EXISTS idx_checkpoints_parent ON langgraph_checkpoints(parent_checkpoint_id);
CREATE INDEX IF NOT EXISTS idx_session_parameters_session ON session_parameters(session_id);
CREATE INDEX IF NOT EXISTS idx_session_parameters_user ON session_parameters(user_id);
CREATE INDEX IF NOT EXISTS idx_parameter_callbacks_session ON parameter_callbacks(session_id);
CREATE INDEX IF NOT EXISTS idx_parameter_callbacks_request ON parameter_callbacks(request_id);

-- ============================================
-- FUNCTIONS
-- ============================================

CREATE OR REPLACE FUNCTION update_updated_at_column()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = now();
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE OR REPLACE FUNCTION get_shared_report_by_token(p_token TEXT)
RETURNS TABLE (
    id UUID,
    title TEXT,
    blocks JSONB,
    created_at TIMESTAMPTZ,
    expires_at TIMESTAMPTZ
) AS $$
BEGIN
    RETURN QUERY
    SELECT sr.id, sr.title, sr.blocks, sr.created_at, sr.expires_at
    FROM shared_reports sr
    WHERE sr.share_token = p_token
      AND (sr.expires_at IS NULL OR sr.expires_at > now());
END;
$$ LANGUAGE plpgsql;

-- ============================================
-- TRIGGERS
-- ============================================

DROP TRIGGER IF EXISTS update_projects_updated_at ON projects;
CREATE TRIGGER update_projects_updated_at
    BEFORE UPDATE ON projects
    FOR EACH ROW
    EXECUTE FUNCTION update_updated_at_column();

DROP TRIGGER IF EXISTS update_profiles_updated_at ON profiles;
CREATE TRIGGER update_profiles_updated_at
    BEFORE UPDATE ON profiles
    FOR EACH ROW
    EXECUTE FUNCTION update_updated_at_column();

-- session_parameters updated_at trigger (requires update_updated_at_column)
DROP TRIGGER IF EXISTS update_session_parameters_updated_at ON session_parameters;
CREATE TRIGGER update_session_parameters_updated_at
    BEFORE UPDATE ON session_parameters
    FOR EACH ROW
    EXECUTE FUNCTION update_updated_at_column();

-- ============================================
-- DONE
-- ============================================

DO $$
BEGIN
    RAISE NOTICE 'Local database initialized successfully!';
END 
$$;