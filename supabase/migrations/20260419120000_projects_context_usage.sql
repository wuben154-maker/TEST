-- Add per-project realtime context-usage snapshot persistence.
--
-- The frontend displays a Cursor-style context-usage ring next to the input
-- composer; once any LLM invocation produces usage metadata, the ring must
-- survive page reloads and cross-device access. Persisting the reducer state
-- directly on `projects` keeps scoping simple (one row per project) and
-- avoids an extra table + join.
--
-- `context_usage` stores the full `StoredPayload` authored by the client:
--   { v: 1, state: { latest, cumulative, bySubagent, lastSummarizedAt },
--     updatedAt: <epoch-ms> }
-- so that hydration can diff against `localStorage` on the same schema.
--
-- `context_usage_updated_at` is server-authored on every PATCH that touches
-- `context_usage` (including explicit NULL clears); it lets the frontend
-- compare against the locally mirrored entry and pick the newer source.
--
-- Both columns are NULLable on purpose: most projects start with no ring
-- data, and `NULL` is the natural "not yet written" signal.

ALTER TABLE public.projects
  ADD COLUMN IF NOT EXISTS context_usage jsonb NULL,
  ADD COLUMN IF NOT EXISTS context_usage_updated_at timestamptz NULL;

COMMENT ON COLUMN public.projects.context_usage IS
  'Per-project context-usage reducer snapshot (realtime-context-usage-indicator). Schema v1: { v, state, updatedAt }.';

COMMENT ON COLUMN public.projects.context_usage_updated_at IS
  'Server-authored timestamp bumped on every PATCH that touches context_usage. Used by the client to pick the newer of localStorage vs backend on hydrate.';
