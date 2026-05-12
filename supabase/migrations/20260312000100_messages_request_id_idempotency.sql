-- Add request_id and idempotency key for messages writes.
-- Prevent duplicate user/assistant rows for the same request.

ALTER TABLE public.messages
ADD COLUMN IF NOT EXISTS request_id TEXT;

CREATE UNIQUE INDEX IF NOT EXISTS uq_messages_project_request_type
ON public.messages(project_id, request_id, type);
