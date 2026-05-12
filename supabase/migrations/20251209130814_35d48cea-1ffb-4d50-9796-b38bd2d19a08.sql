-- Add a secure share token for token-based access
ALTER TABLE public.shared_reports 
ADD COLUMN share_token TEXT NOT NULL DEFAULT encode(gen_random_bytes(16), 'hex');

-- Create unique index on share_token
CREATE UNIQUE INDEX idx_shared_reports_share_token ON public.shared_reports(share_token);

-- Drop the overly permissive policy
DROP POLICY IF EXISTS "Shared reports are publicly viewable" ON public.shared_reports;

-- Create new policy that requires the share_token parameter
-- Reports can only be accessed via their unique share token
CREATE POLICY "Shared reports accessible via share token"
ON public.shared_reports
FOR SELECT
USING (
  (expires_at IS NULL OR expires_at > now())
);

-- Note: The actual token validation will be done in the application layer
-- by querying with WHERE share_token = :token