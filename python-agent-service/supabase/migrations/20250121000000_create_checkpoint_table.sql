-- LangGraph Checkpointing Table
-- This table stores state checkpoints for conversation persistence
-- Created automatically by PostgresSaver.setup() if not exists

-- Note: This migration is optional - PostgresSaver will create the table automatically
-- on first use. This migration ensures the table exists with proper permissions.

CREATE TABLE IF NOT EXISTS langgraph_checkpoints (
    thread_id TEXT NOT NULL,
    checkpoint_ns TEXT NOT NULL DEFAULT '',
    checkpoint_id TEXT NOT NULL,
    checkpoint JSONB NOT NULL,
    parent_checkpoint_id TEXT,
    metadata JSONB DEFAULT '{}',
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    PRIMARY KEY (thread_id, checkpoint_ns, checkpoint_id)
);

-- Indexes for efficient querying
CREATE INDEX IF NOT EXISTS idx_checkpoints_thread_id ON langgraph_checkpoints(thread_id);
CREATE INDEX IF NOT EXISTS idx_checkpoints_parent ON langgraph_checkpoints(parent_checkpoint_id);
CREATE INDEX IF NOT EXISTS idx_checkpoints_created_at ON langgraph_checkpoints(created_at DESC);

-- Index for checkpoint namespace queries
CREATE INDEX IF NOT EXISTS idx_checkpoints_ns ON langgraph_checkpoints(checkpoint_ns);

-- Comments
COMMENT ON TABLE langgraph_checkpoints IS 'Stores LangGraph state checkpoints for conversation persistence';
COMMENT ON COLUMN langgraph_checkpoints.thread_id IS 'Session/thread identifier';
COMMENT ON COLUMN langgraph_checkpoints.checkpoint_ns IS 'Checkpoint namespace (for multi-tenant scenarios)';
COMMENT ON COLUMN langgraph_checkpoints.checkpoint_id IS 'Unique checkpoint identifier';
COMMENT ON COLUMN langgraph_checkpoints.checkpoint IS 'Serialized state checkpoint (JSONB)';
COMMENT ON COLUMN langgraph_checkpoints.parent_checkpoint_id IS 'Reference to parent checkpoint (for state history)';
COMMENT ON COLUMN langgraph_checkpoints.metadata IS 'Additional metadata (timestamps, version, etc.)';
