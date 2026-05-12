-- Drop the current permissive SELECT policy
DROP POLICY IF EXISTS "Shared reports accessible via share token" ON public.shared_reports;

-- Create a SECURITY DEFINER function to fetch reports by token
-- This bypasses RLS and validates the token in the function itself
CREATE OR REPLACE FUNCTION public.get_shared_report_by_token(p_token TEXT)
RETURNS TABLE (
  id UUID,
  title TEXT,
  blocks JSONB,
  created_at TIMESTAMPTZ,
  expires_at TIMESTAMPTZ
)
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = public
AS $$
BEGIN
  RETURN QUERY
  SELECT 
    sr.id,
    sr.title,
    sr.blocks,
    sr.created_at,
    sr.expires_at
  FROM public.shared_reports sr
  WHERE sr.share_token = p_token
    AND (sr.expires_at IS NULL OR sr.expires_at > now());
END;
$$;

-- Create SELECT policy only for report owners to view their own reports
CREATE POLICY "Users can view their own shared reports"
ON public.shared_reports
FOR SELECT
USING (auth.uid() = user_id);

-- Add UPDATE policy so owners can update their reports
CREATE POLICY "Users can update own shared reports"
ON public.shared_reports
FOR UPDATE
USING (auth.uid() = user_id);