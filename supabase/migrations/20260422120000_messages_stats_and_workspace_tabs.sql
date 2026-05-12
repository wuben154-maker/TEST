-- Recover schema drift: messages.stats and messages.workspace_tabs are referenced
-- by frontend API (messages.py) INSERT but never had ADD COLUMN migrations.
-- Idempotent: safe on Dev (column missing) and staging/prod (already exists).
ALTER TABLE messages ADD COLUMN IF NOT EXISTS stats JSONB;
ALTER TABLE messages ADD COLUMN IF NOT EXISTS workspace_tabs JSONB;
