-- One-shot: add messages.timeline for local DBs created before schemaVersion 1 timeline.
-- Safe to run multiple times (IF NOT EXISTS).
ALTER TABLE public.messages
  ADD COLUMN IF NOT EXISTS timeline JSONB NOT NULL DEFAULT '[]'::jsonb;
