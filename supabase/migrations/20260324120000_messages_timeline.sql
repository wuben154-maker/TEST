-- Canonical analysis timeline (schemaVersion 1 SSE replay).
ALTER TABLE public.messages
  ADD COLUMN IF NOT EXISTS timeline JSONB NOT NULL DEFAULT '[]'::jsonb;

COMMENT ON COLUMN public.messages.timeline IS 'Ordered SSE-style events (seq, type, scope) for unified UI replay; see python-agent-service README SSE section.';
