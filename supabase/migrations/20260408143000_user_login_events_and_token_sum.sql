-- Login history for account settings (last N successful logins).
-- Token sum helper for account overview (service_role / backend only).

CREATE TABLE IF NOT EXISTS public.user_login_events (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  user_id UUID NOT NULL REFERENCES auth.users (id) ON DELETE CASCADE,
  logged_in_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  ip_address TEXT,
  user_agent TEXT
);

CREATE INDEX IF NOT EXISTS idx_user_login_events_user_logged_in
  ON public.user_login_events (user_id, logged_in_at DESC);

ALTER TABLE public.user_login_events ENABLE ROW LEVEL SECURITY;

CREATE POLICY "user_login_events_select_own"
  ON public.user_login_events FOR SELECT TO authenticated
  USING (auth.uid() = user_id);

COMMENT ON TABLE public.user_login_events IS 'Successful login audit rows; inserted by backend with service_role.';

-- Aggregated token total for overview (avoid scanning all rows in the API).
CREATE OR REPLACE FUNCTION public.sum_llm_tokens_for_user(p_user_id uuid)
RETURNS bigint
LANGUAGE sql
STABLE
SECURITY DEFINER
SET search_path = public
AS $$
  SELECT COALESCE(SUM(prompt_tokens + completion_tokens), 0)::bigint
  FROM public.llm_usage_events
  WHERE user_id = p_user_id;
$$;

REVOKE ALL ON FUNCTION public.sum_llm_tokens_for_user(uuid) FROM PUBLIC;
GRANT EXECUTE ON FUNCTION public.sum_llm_tokens_for_user(uuid) TO service_role;
