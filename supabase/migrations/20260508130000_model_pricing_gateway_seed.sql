-- Extend model_pricing so common gateway model_id values get non-zero llm_usage_events.cost_usd.
-- Rates are approximate onboarding defaults; adjust to match your provider list.
-- effective_from matches existing seed epoch for ON CONFLICT compatibility.

INSERT INTO public.model_pricing (model_id, usd_per_million_input, usd_per_million_output, effective_from)
VALUES
  ('google/gemini-3.1-pro-preview', 2.00, 8.00, timestamptz '2026-01-01 00:00:00+00'),
  ('google/gemini-3.1-flash-lite-preview', 0.08, 0.32, timestamptz '2026-01-01 00:00:00+00'),
  ('openrouter/moonshotai/kimi-k2.6', 0.60, 2.40, timestamptz '2026-01-01 00:00:00+00'),
  ('openrouter/anthropic/claude-sonnet-4.6', 3.00, 15.00, timestamptz '2026-01-01 00:00:00+00'),
  ('openrouter/anthropic/claude-opus-4.7', 15.00, 75.00, timestamptz '2026-01-01 00:00:00+00'),
  ('openrouter/google/gemini-3.1-pro-preview', 2.00, 8.00, timestamptz '2026-01-01 00:00:00+00'),
  ('openrouter/google/gemini-3-flash-preview', 0.15, 0.60, timestamptz '2026-01-01 00:00:00+00')
ON CONFLICT (model_id, effective_from) DO NOTHING;
