-- Add workspace_title column to messages table for LLM-generated and user-editable tab titles
ALTER TABLE messages ADD COLUMN IF NOT EXISTS workspace_title TEXT;
