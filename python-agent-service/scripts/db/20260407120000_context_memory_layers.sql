-- Context memory layers (agent-context-memory-layers)
-- Moved from supabase/migrations for local PostgreSQL apply.
--
-- Local: no RLS policies (no auth.uid()). Python service uses owner/superuser
-- connection and enforces tenant in application code.
-- For Supabase + PostgREST with JWT, add RLS policies separately if needed.
--
-- Apply using LOCAL_DB_* from python-agent-service/.env:
--   python scripts/db/apply_sql_file.py scripts/db/20260407120000_context_memory_layers.sql
-- Or: psql with the same host/port/user/db/password as in .env

CREATE TABLE IF NOT EXISTS public.project_derived_memory (
  project_id UUID NOT NULL PRIMARY KEY REFERENCES public.projects(id) ON DELETE CASCADE,
  user_id UUID NOT NULL,
  payload JSONB NOT NULL DEFAULT '{}'::jsonb,
  updated_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_project_derived_memory_user_id
  ON public.project_derived_memory(user_id);

CREATE TABLE IF NOT EXISTS public.user_memory_index (
  user_id UUID NOT NULL PRIMARY KEY,
  payload JSONB NOT NULL DEFAULT '{}'::jsonb,
  updated_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS public.context_memory_merge_log (
  project_id UUID NOT NULL REFERENCES public.projects(id) ON DELETE CASCADE,
  request_id TEXT NOT NULL,
  merged_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT now(),
  PRIMARY KEY (project_id, request_id)
);

CREATE INDEX IF NOT EXISTS idx_context_memory_merge_log_merged_at
  ON public.context_memory_merge_log(merged_at DESC);

DROP TRIGGER IF EXISTS update_project_derived_memory_updated_at ON public.project_derived_memory;
CREATE TRIGGER update_project_derived_memory_updated_at
  BEFORE UPDATE ON public.project_derived_memory
  FOR EACH ROW
  EXECUTE FUNCTION public.update_updated_at_column();

DROP TRIGGER IF EXISTS update_user_memory_index_updated_at ON public.user_memory_index;
CREATE TRIGGER update_user_memory_index_updated_at
  BEFORE UPDATE ON public.user_memory_index
  FOR EACH ROW
  EXECUTE FUNCTION public.update_updated_at_column();
