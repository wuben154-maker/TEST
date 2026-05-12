-- Local PostgreSQL Database Initialization Script
-- Run this script to set up the local database for development
--
-- Prerequisites:
--   1. PostgreSQL 12+ installed and running
--   2. Create database: createdb -U postgres secmanus
--
-- Usage (from repo root, or adjust path):
--   psql -U postgres -d secmanus -f python-agent-service/scripts/db/init_local_db.sql
--   Or from python-agent-service: psql -U postgres -d secmanus -f scripts/db/init_local_db.sql

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
    -- Realtime context-usage snapshot (see supabase migration 20260419120000_projects_context_usage).
    -- Schema v1: {"v":1,"state":{...},"updatedAt":<epoch-ms>}. NULL = never written.
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
    timeline JSONB NOT NULL DEFAULT '[]'::jsonb,
    stats JSONB DEFAULT NULL,
    workspace_tabs JSONB DEFAULT NULL,
    knowledge_archive JSONB DEFAULT NULL,
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

-- Login audit (successful logins; optional for older DBs — see scripts/db/20260408143000_user_login_events.sql)
CREATE TABLE IF NOT EXISTS user_login_events (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    user_id UUID NOT NULL REFERENCES profiles(user_id) ON DELETE CASCADE,
    logged_in_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    ip_address TEXT,
    user_agent TEXT,
    ip_country TEXT
);
CREATE INDEX IF NOT EXISTS idx_user_login_events_user_logged_in
    ON user_login_events (user_id, logged_in_at DESC);

ALTER TABLE project_analysis_progress
  ADD COLUMN IF NOT EXISTS timeline JSONB NOT NULL DEFAULT '[]'::jsonb;

ALTER TABLE project_analysis_progress
  ADD COLUMN IF NOT EXISTS ui_language TEXT;

-- User ahthentication info
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";

CREATE TABLE IF NOT EXISTS public.user_vendor_connections (
    id uuid NOT NULL DEFAULT uuid_generate_v4(),
    user_id uuid NOT NULL,
    provider_code text NOT NULL,
    display_name text NOT NULL,
    auth_type text NOT NULL,
    auth_status text NOT NULL DEFAULT 'pending'::text,
    scope jsonb NOT NULL DEFAULT '{}'::jsonb,
    expires_at timestamp with time zone,
    last_verified_at timestamp with time zone,
    metadata jsonb NOT NULL DEFAULT '{}'::jsonb,
    created_at timestamp with time zone NOT NULL DEFAULT now(),
    updated_at timestamp with time zone NOT NULL DEFAULT now(),
    

    CONSTRAINT user_vendor_connections_pkey PRIMARY KEY (id),
    
    CONSTRAINT user_vendor_connections_user_id_provider_code_display_name_key 
        UNIQUE (user_id, provider_code, display_name),
    
    CONSTRAINT chk_user_vendor_connections_auth_status 
        CHECK (auth_status = ANY (ARRAY['pending'::text, 'active'::text, 'revoked'::text, 'expired'::text, 'error'::text])),
    
    CONSTRAINT chk_user_vendor_connections_metadata_object 
        CHECK (jsonb_typeof(metadata) = 'object'::text),
    
    CONSTRAINT chk_user_vendor_connections_provider_code_not_blank 
        CHECK (length(TRIM(BOTH FROM provider_code)) > 0),
    
    CONSTRAINT chk_user_vendor_connections_scope_object 
        CHECK (jsonb_typeof(scope) = 'object'::text)
);

CREATE INDEX IF NOT EXISTS idx_user_vendor_connections_user_id 
    ON public.user_vendor_connections(user_id);

CREATE INDEX IF NOT EXISTS idx_user_vendor_connections_provider_code 
    ON public.user_vendor_connections(provider_code);

CREATE INDEX IF NOT EXISTS idx_user_vendor_connections_auth_status 
    ON public.user_vendor_connections(auth_status);

CREATE INDEX IF NOT EXISTS idx_user_vendor_connections_expires_at 
    ON public.user_vendor_connections(expires_at);


-- User authentication values
CREATE TABLE IF NOT EXISTS public.user_vendor_connection_secrets (
    id uuid NOT NULL DEFAULT uuid_generate_v4(),
    connection_id uuid NOT NULL,
    secret_ciphertext text NOT NULL,
    secret_version integer NOT NULL DEFAULT 1,
    encryption_meta jsonb NOT NULL DEFAULT '{}'::jsonb,
    created_at timestamp with time zone NOT NULL DEFAULT now(),
    rotated_at timestamp with time zone,
    CONSTRAINT user_vendor_connection_secrets_pkey PRIMARY KEY (id),
    CONSTRAINT user_vendor_connection_secrets_connection_id_key UNIQUE (connection_id),
    CONSTRAINT chk_user_vendor_connection_secrets_encryption_meta_object 
        CHECK (jsonb_typeof(encryption_meta) = 'object'::text),
    CONSTRAINT chk_user_vendor_connection_secrets_version 
        CHECK (secret_version > 0),
    CONSTRAINT user_vendor_connection_secrets_connection_id_fkey 
        FOREIGN KEY (connection_id) 
        REFERENCES public.user_vendor_connections(id) 
        ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS idx_user_vendor_connection_secrets_connection_id 
    ON public.user_vendor_connection_secrets(connection_id);

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

    -- Canonical SSE replay (align with supabase/migrations/*messages_timeline*.sql)
    IF NOT EXISTS (
        SELECT 1
        FROM information_schema.columns
        WHERE table_schema = 'public' AND table_name = 'messages' AND column_name = 'timeline'
    ) THEN
        ALTER TABLE messages ADD COLUMN timeline JSONB NOT NULL DEFAULT '[]'::jsonb;
    END IF;

    -- Backward-compatible migration for vendor auth provider_code model.
    IF EXISTS (
        SELECT 1
        FROM information_schema.columns
        WHERE table_schema = 'public'
          AND table_name = 'user_vendor_connections'
          AND column_name = 'vendor_provider_id'
    ) THEN
        IF NOT EXISTS (
            SELECT 1
            FROM information_schema.columns
            WHERE table_schema = 'public'
              AND table_name = 'user_vendor_connections'
              AND column_name = 'provider_code'
        ) THEN
            ALTER TABLE user_vendor_connections ADD COLUMN provider_code TEXT;
        END IF;

        IF EXISTS (
            SELECT 1
            FROM information_schema.tables
            WHERE table_schema = 'public'
              AND table_name = 'vendor_providers'
        ) THEN
            UPDATE user_vendor_connections uvc
            SET provider_code = vp.code
            FROM vendor_providers vp
            WHERE uvc.vendor_provider_id = vp.id
              AND (uvc.provider_code IS NULL OR trim(uvc.provider_code) = '');
        END IF;

        UPDATE user_vendor_connections
        SET provider_code = 'unknown'
        WHERE provider_code IS NULL OR trim(provider_code) = '';
    END IF;

    IF NOT EXISTS (
        SELECT 1
        FROM information_schema.columns
        WHERE table_schema = 'public' AND table_name = 'messages' AND column_name = 'knowledge_archive'
    ) THEN
        ALTER TABLE messages ADD COLUMN knowledge_archive JSONB DEFAULT NULL;
    END IF;

    IF EXISTS (
        SELECT 1 FROM information_schema.tables
        WHERE table_schema = 'public' AND table_name = 'user_login_events'
    ) AND NOT EXISTS (
        SELECT 1 FROM information_schema.columns
        WHERE table_schema = 'public' AND table_name = 'user_login_events'
          AND column_name = 'ip_country'
    ) THEN
        ALTER TABLE user_login_events ADD COLUMN ip_country TEXT;
    END IF;

    -- Realtime context-usage persistence (feature: realtime-context-usage-indicator).
    IF NOT EXISTS (
        SELECT 1 FROM information_schema.columns
        WHERE table_schema = 'public' AND table_name = 'projects'
          AND column_name = 'context_usage'
    ) THEN
        ALTER TABLE projects ADD COLUMN context_usage JSONB;
    END IF;

    IF NOT EXISTS (
        SELECT 1 FROM information_schema.columns
        WHERE table_schema = 'public' AND table_name = 'projects'
          AND column_name = 'context_usage_updated_at'
    ) THEN
        ALTER TABLE projects ADD COLUMN context_usage_updated_at TIMESTAMPTZ;
    END IF;

    RAISE NOTICE 'Local database initialized successfully!';
END $$;
