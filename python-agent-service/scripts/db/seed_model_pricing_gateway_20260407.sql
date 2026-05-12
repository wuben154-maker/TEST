-- Seed model_pricing for all gateway model_id values (config/llm_gateway.yaml).
-- Each usd_per_million_* = 1.5 × provider-published list price (USD per 1M tokens).
-- Verify originals at official pages; re-run with a newer effective_from when list prices change.
--
-- References (April 2026):
--   OpenAI: https://platform.openai.com/docs/pricing
--   Anthropic: https://docs.anthropic.com/en/about-claude/pricing
--   Google Gemini: https://ai.google.dev/gemini-api/docs/pricing
--   Volcengine / Seed 2.0 (third-party summary): ~$0.47 in / $2.37 out per 1M
--   Moonshot Kimi K2.5 (aggregators / docs): ~$0.383 in / $1.72 out per 1M
--   MiniMax M2.5: https://platform.minimax.io/docs/guides/pricing-paygo ($0.30 / $1.20 per 1M)
--   Z.AI GLM-5 / FlashX: https://docs.z.ai/guides/overview/pricing
--
-- Free-tier Zen models: list price treated as $0 → cost row is 0 (usage still recorded).

INSERT INTO model_pricing (model_id, usd_per_million_input, usd_per_million_output, effective_from)
VALUES
  -- Google (Gemini dev API, <=200k tier where tiered)
  ('google/gemini-3-flash-preview', 0.750000, 4.500000, timestamptz '2026-04-07 12:00:00+00'),
  ('google/gemini-2.5-flash', 0.450000, 3.750000, timestamptz '2026-04-07 12:00:00+00'),
  ('google/gemini-2.5-pro', 1.875000, 15.000000, timestamptz '2026-04-07 12:00:00+00'),
  -- Anthropic (direct API)
  ('anthropic/claude-sonnet-4', 4.500000, 22.500000, timestamptz '2026-04-07 12:00:00+00'),
  ('anthropic/claude-opus-4', 22.500000, 112.500000, timestamptz '2026-04-07 12:00:00+00'),
  ('anthropic/claude-haiku-4', 1.500000, 7.500000, timestamptz '2026-04-07 12:00:00+00'),
  -- OpenAI (direct API)
  ('openai/gpt-4o', 3.750000, 15.000000, timestamptz '2026-04-07 12:00:00+00'),
  ('openai/gpt-4o-mini', 0.225000, 0.900000, timestamptz '2026-04-07 12:00:00+00'),
  -- Doubao / Volcengine (approx. from public Seed 2.0 Pro figures; lite lower tier)
  ('doubao/doubao-seed-2-pro', 0.705000, 3.555000, timestamptz '2026-04-07 12:00:00+00'),
  ('doubao/doubao-seed-1.6-lite', 0.135000, 0.795000, timestamptz '2026-04-07 12:00:00+00'),
  -- OpenCode Zen — map to underlying flagship list prices
  ('opencode/gpt-5.4', 3.750000, 22.500000, timestamptz '2026-04-07 12:00:00+00'),
  ('opencode/gpt-5.4-pro', 22.500000, 180.000000, timestamptz '2026-04-07 12:00:00+00'),
  ('opencode/gpt-5.3-codex', 5.250000, 42.000000, timestamptz '2026-04-07 12:00:00+00'),
  ('opencode/gpt-5.3-codex-spark', 0.375000, 3.000000, timestamptz '2026-04-07 12:00:00+00'),
  ('opencode/claude-opus-4-6', 7.500000, 37.500000, timestamptz '2026-04-07 12:00:00+00'),
  ('opencode/claude-opus-4-7', 7.500000, 37.500000, timestamptz '2026-04-07 12:00:00+00'),
  ('opencode/claude-sonnet-4-6', 4.500000, 22.500000, timestamptz '2026-04-07 12:00:00+00'),
  ('opencode/gemini-3.1-pro', 3.000000, 18.000000, timestamptz '2026-04-07 12:00:00+00'),
  ('opencode/gemini-3-flash', 0.750000, 4.500000, timestamptz '2026-04-07 12:00:00+00'),
  ('opencode/minimax-m2.5', 0.450000, 1.800000, timestamptz '2026-04-07 12:00:00+00'),
  ('opencode/glm-5', 1.500000, 4.800000, timestamptz '2026-04-07 12:00:00+00'),
  ('opencode/glm-5.1', 1.500000, 6.000000, timestamptz '2026-04-07 12:00:00+00'),
  ('opencode/kimi-k2.5', 0.574500, 2.580000, timestamptz '2026-04-07 12:00:00+00'),
  ('opencode/qwen3.6-plus', 0.300000, 1.500000, timestamptz '2026-04-07 12:00:00+00'),
  ('opencode/qwen3.5-plus', 0.300000, 1.500000, timestamptz '2026-04-07 12:00:00+00'),
  -- OpenRouter — routed gateway ids, list prices × 1.5 where public pricing is known
  ('openrouter/anthropic/claude-opus-4.7', 7.500000, 37.500000, timestamptz '2026-04-25 12:00:00+00'),
  ('openrouter/anthropic/claude-sonnet-4.6', 4.500000, 22.500000, timestamptz '2026-04-25 12:00:00+00'),
  ('openrouter/moonshotai/kimi-k2.6', 1.117200, 6.982500, timestamptz '2026-04-25 12:00:00+00'),
  -- Kimi / MiniMax / GLM (direct)
  ('kimi/k2.5', 0.574500, 2.580000, timestamptz '2026-04-07 12:00:00+00'),
  ('kimi/k2', 0.900000, 3.750000, timestamptz '2026-04-07 12:00:00+00'),
  ('minimax/m2.5', 0.450000, 1.800000, timestamptz '2026-04-07 12:00:00+00'),
  ('glm/glm-4-plus', 0.900000, 3.300000, timestamptz '2026-04-07 12:00:00+00'),
  ('glm/glm-4-flash', 0.105000, 0.600000, timestamptz '2026-04-07 12:00:00+00')
ON CONFLICT (model_id, effective_from) DO NOTHING;
