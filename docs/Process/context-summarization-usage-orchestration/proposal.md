# Proposal — Context summarization × usage orchestration (full stack)

## Problem

Realtime context usage (ring + `projects.context_usage`) and DeepAgents `SummarizationMiddleware` run on **different signals**:

- **UI ring**: last main `llm_invoke_end.usage.inputTokens` ÷ catalog `context_window`.
- **Compression**: approximate token count over `messages` ÷ `model.profile.max_input_tokens` (fraction defaults).

That yields **visible drift** (badge says 60% while middleware would fire at 85% of another denominator), **no authoritative server-side budget** for the same percentile semantics as the product, and **no durable thread of “what filled the window”** after summarization besides a toast timestamp.

## Goals

1. **Single budget contract** — One definition of *context window* and *fill ratio* for “main” agent turns, shared by UI badge, SSE payloads, and summarization policy (with documented fallbacks when provider omits usage).
2. **Provider-first metering** — Prefer **vendor-reported prompt/input tokens** from each completed LLM call; use **message approximation** only as fallback or bound.
3. **Aligned policy engine** — Configurable thresholds (e.g. warn 70% / danger 90% / compress 85–95%) driven from **server config + model catalog**, not hard-coded in three places.
4. **Explicit compression lifecycle** — After compression, emit structured SSE (and optional persisted snapshot fields) so the client can **reset or reconcile** ring state without guessing.
5. **Observability** — Log lines / metrics for `fill_source`, `pre_compress_ratio`, `post_compress_ratio`, `cutoff_index` for support and tuning.
6. **Backward compatibility** — Existing SSE types (`llm_invoke_*`, `context_summarized`) keep working; new fields are additive.

## Non-goals

- **Billing / Stripe** — Out of scope; `llm_usage_events` remains source of truth for cost.
- **Cross-session global token ledger** — Still per analysis thread / project session; no new warehouse table unless Phase 2+ explicitly extends.
- **Client-only pre-send estimation (Opt A)** — Still not required; server may add optional **post-turn estimates** in SSE for debugging only.
- **Perfect numeric parity** every provider — Aim for **same policy inputs**; document known skew (e.g. cached tokens, reasoning blocks).

## Users

- **Security analysts** — Trust the ring vs when compression will hit.
- **Operators** — Tune thresholds and windows from config without redeploying scattered magic numbers.

## Dependencies

- Existing: `LlmInvokeLifecycleCallbackHandler`, `extract_token_usage_from_llm_result`, `deepagents_stream_adapter`, `SummarizationMiddleware`, `config/llm_gateway.yaml`, `GET /models`.
- Optional: LangGraph `checkpointer` / thread id for per-thread meter persistence across turns.

## Success metrics

- Ring **severity bucket** (warn/danger/critical) matches server-emitted **budget tier** for the same turn on main agent (≥ **95%** agreement in integration tests with mocked usage).
- Summarization fires when **merged fill** ≥ configured compress threshold in long-replay fixtures (no silent context overflow in golden paths).
- Post-`context_summarized`, frontend shows **non-stale** main prompt token view within one `llm_invoke_end` (or explicit `context_budget` refresh).

## Scope

| In scope | Out of scope |
|----------|----------------|
| Server budget authority + merged fill | Subagent billing attribution changes |
| Policy config (env/yaml) + tests | New admin UI for policies |
| SSE schema extensions | Mobile clients |
| Frontend reconciliation after compress | Rewriting entire DeepAgents vendor |
