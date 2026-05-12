-- Optional migration: persist POST /analyze ui_language for HITL resume after refresh.
-- Run once on existing Postgres: psql ... -f add_project_analysis_progress_ui_language.sql

ALTER TABLE project_analysis_progress
  ADD COLUMN IF NOT EXISTS ui_language TEXT;
