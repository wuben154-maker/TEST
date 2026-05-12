-- Add canonical SSE timeline to in-progress analysis rows (refresh recovery).
-- Run once on existing Postgres: psql ... -f add_project_analysis_progress_timeline.sql

ALTER TABLE project_analysis_progress
  ADD COLUMN IF NOT EXISTS timeline JSONB NOT NULL DEFAULT '[]'::jsonb;
