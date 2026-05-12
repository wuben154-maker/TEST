-- One-shot: add messages.stats and messages.workspace_tabs for workspace-task-panel persistence.
-- Safe to run multiple times (IF NOT EXISTS).
ALTER TABLE public.messages
  ADD COLUMN IF NOT EXISTS stats JSONB DEFAULT NULL;

ALTER TABLE public.messages
  ADD COLUMN IF NOT EXISTS workspace_tabs JSONB DEFAULT NULL;
