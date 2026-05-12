-- Persist "report saved to knowledge base" metadata on assistant rows (survives refresh).
ALTER TABLE messages ADD COLUMN IF NOT EXISTS knowledge_archive JSONB;

COMMENT ON COLUMN messages.knowledge_archive IS
    'JSON blob aligned with KnowledgeArchiveNotice (filename, displayPath, reportLabel, pending); keyed by project_id + request_id upserts.';
