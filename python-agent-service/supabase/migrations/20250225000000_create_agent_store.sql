-- Agent Store Table
-- Persistent key-value storage for memories and parameters.
-- Used by DatabaseBackend when DATABASE_MODE=supabase.
-- Schema matches PostgresStore.CREATE_TABLE_SQL for compatibility.

CREATE TABLE IF NOT EXISTS agent_store (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    namespace VARCHAR(255) NOT NULL,
    key VARCHAR(1024) NOT NULL,
    value JSONB NOT NULL,
    metadata JSONB DEFAULT '{}',
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    expires_at TIMESTAMP WITH TIME ZONE,
    UNIQUE(namespace, key)
);

CREATE INDEX IF NOT EXISTS idx_agent_store_namespace ON agent_store(namespace);
CREATE INDEX IF NOT EXISTS idx_agent_store_expires ON agent_store(expires_at) WHERE expires_at IS NOT NULL;

COMMENT ON TABLE agent_store IS 'Persistent storage for agent memories and parameters';
COMMENT ON COLUMN agent_store.namespace IS 'Logical namespace (e.g. memories, parameters)';
COMMENT ON COLUMN agent_store.key IS 'Path-style key (e.g. /session_id/param_name)';
