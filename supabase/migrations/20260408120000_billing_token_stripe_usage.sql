-- Billing / usage / Stripe support (billing-token-stripe-usage).
-- Backend uses service_role for writes; RLS limits direct client access where applicable.

-- ---------------------------------------------------------------------------
-- Plans (catalog)
-- ---------------------------------------------------------------------------
CREATE TABLE public.billing_plans (
  slug TEXT PRIMARY KEY,
  display_name TEXT NOT NULL,
  included_tokens_per_period BIGINT NOT NULL DEFAULT 0,
  monthly_price_usd NUMERIC(10, 2) NOT NULL DEFAULT 0,
  stripe_price_id TEXT,
  sort_order INTEGER NOT NULL DEFAULT 0
);

ALTER TABLE public.billing_plans ENABLE ROW LEVEL SECURITY;

CREATE POLICY "billing_plans_select_authenticated"
  ON public.billing_plans FOR SELECT TO authenticated
  USING (true);

COMMENT ON TABLE public.billing_plans IS 'Product plan catalog; Ultra included_tokens = 3x Pro at seed time.';

-- ---------------------------------------------------------------------------
-- Stripe customer id per user
-- ---------------------------------------------------------------------------
CREATE TABLE public.user_billing_profile (
  user_id UUID PRIMARY KEY REFERENCES auth.users (id) ON DELETE CASCADE,
  stripe_customer_id TEXT,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX idx_user_billing_profile_stripe_customer
  ON public.user_billing_profile (stripe_customer_id)
  WHERE stripe_customer_id IS NOT NULL;

ALTER TABLE public.user_billing_profile ENABLE ROW LEVEL SECURITY;

CREATE POLICY "user_billing_profile_select_own"
  ON public.user_billing_profile FOR SELECT TO authenticated
  USING (auth.uid() = user_id);

CREATE POLICY "user_billing_profile_insert_own"
  ON public.user_billing_profile FOR INSERT TO authenticated
  WITH CHECK (auth.uid() = user_id);

CREATE POLICY "user_billing_profile_update_own"
  ON public.user_billing_profile FOR UPDATE TO authenticated
  USING (auth.uid() = user_id);

CREATE TRIGGER update_user_billing_profile_updated_at
  BEFORE UPDATE ON public.user_billing_profile
  FOR EACH ROW
  EXECUTE FUNCTION public.update_updated_at_column();

-- ---------------------------------------------------------------------------
-- Subscription state (Stripe is source of truth; mirrored here)
-- ---------------------------------------------------------------------------
CREATE TABLE public.user_subscriptions (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  user_id UUID NOT NULL REFERENCES auth.users (id) ON DELETE CASCADE,
  plan_slug TEXT NOT NULL REFERENCES public.billing_plans (slug),
  stripe_subscription_id TEXT UNIQUE,
  status TEXT NOT NULL DEFAULT 'inactive',
  current_period_start TIMESTAMPTZ,
  current_period_end TIMESTAMPTZ,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX idx_user_subscriptions_user_id ON public.user_subscriptions (user_id);

ALTER TABLE public.user_subscriptions ENABLE ROW LEVEL SECURITY;

CREATE POLICY "user_subscriptions_select_own"
  ON public.user_subscriptions FOR SELECT TO authenticated
  USING (auth.uid() = user_id);

CREATE TRIGGER update_user_subscriptions_updated_at
  BEFORE UPDATE ON public.user_subscriptions
  FOR EACH ROW
  EXECUTE FUNCTION public.update_updated_at_column();

-- ---------------------------------------------------------------------------
-- Model pricing (USD per 1M tokens)
-- ---------------------------------------------------------------------------
CREATE TABLE public.model_pricing (
  model_id TEXT NOT NULL,
  usd_per_million_input NUMERIC(14, 6) NOT NULL,
  usd_per_million_output NUMERIC(14, 6) NOT NULL,
  effective_from TIMESTAMPTZ NOT NULL DEFAULT now(),
  PRIMARY KEY (model_id, effective_from)
);

ALTER TABLE public.model_pricing ENABLE ROW LEVEL SECURITY;

CREATE POLICY "model_pricing_select_authenticated"
  ON public.model_pricing FOR SELECT TO authenticated
  USING (true);

-- ---------------------------------------------------------------------------
-- Per-LLM usage events (VT/Tavily etc. are not recorded here)
-- ---------------------------------------------------------------------------
CREATE TABLE public.llm_usage_events (
  id BIGSERIAL PRIMARY KEY,
  user_id UUID NOT NULL REFERENCES auth.users (id) ON DELETE CASCADE,
  project_id UUID REFERENCES public.projects (id) ON DELETE SET NULL,
  request_id TEXT NOT NULL DEFAULT '',
  model_id TEXT NOT NULL,
  prompt_tokens INTEGER NOT NULL DEFAULT 0,
  completion_tokens INTEGER NOT NULL DEFAULT 0,
  cost_usd NUMERIC(14, 6) NOT NULL DEFAULT 0,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX idx_llm_usage_events_user_created
  ON public.llm_usage_events (user_id, created_at DESC);

CREATE INDEX idx_llm_usage_events_request
  ON public.llm_usage_events (user_id, request_id);

ALTER TABLE public.llm_usage_events ENABLE ROW LEVEL SECURITY;

CREATE POLICY "llm_usage_events_select_own"
  ON public.llm_usage_events FOR SELECT TO authenticated
  USING (auth.uid() = user_id);

-- ---------------------------------------------------------------------------
-- User spend cap / arrears (USD)
-- ---------------------------------------------------------------------------
CREATE TABLE public.user_billing_settings (
  user_id UUID PRIMARY KEY REFERENCES auth.users (id) ON DELETE CASCADE,
  monthly_spend_cap_usd NUMERIC(12, 2) NOT NULL DEFAULT 100.00,
  arrears_allowance_usd NUMERIC(12, 2) NOT NULL DEFAULT 5.00,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

ALTER TABLE public.user_billing_settings ENABLE ROW LEVEL SECURITY;

CREATE POLICY "user_billing_settings_select_own"
  ON public.user_billing_settings FOR SELECT TO authenticated
  USING (auth.uid() = user_id);

CREATE POLICY "user_billing_settings_insert_own"
  ON public.user_billing_settings FOR INSERT TO authenticated
  WITH CHECK (auth.uid() = user_id);

CREATE POLICY "user_billing_settings_update_own"
  ON public.user_billing_settings FOR UPDATE TO authenticated
  USING (auth.uid() = user_id);

CREATE TRIGGER update_user_billing_settings_updated_at
  BEFORE UPDATE ON public.user_billing_settings
  FOR EACH ROW
  EXECUTE FUNCTION public.update_updated_at_column();

-- ---------------------------------------------------------------------------
-- Stripe webhook idempotency
-- ---------------------------------------------------------------------------
CREATE TABLE public.stripe_webhook_events (
  id TEXT PRIMARY KEY,
  received_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  event_type TEXT,
  livemode BOOLEAN
);

ALTER TABLE public.stripe_webhook_events ENABLE ROW LEVEL SECURITY;
-- No policies: only service_role / postgres should access.

-- ---------------------------------------------------------------------------
-- Seed plans (adjust tokens / stripe_price_id in ops)
-- ---------------------------------------------------------------------------
INSERT INTO public.billing_plans (slug, display_name, included_tokens_per_period, monthly_price_usd, stripe_price_id, sort_order)
VALUES
  ('free', 'Free', 500000, 0, NULL, 0),
  ('pro', 'Pro', 1000000, 40, NULL, 1),
  ('ultra', 'Ultra', 3000000, 100, NULL, 2),
  ('enterprise', 'Enterprise', 0, 0, NULL, 3)
ON CONFLICT (slug) DO NOTHING;
