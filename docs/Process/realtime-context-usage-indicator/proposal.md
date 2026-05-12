# Proposal — Realtime context usage indicator

## Problem

When the agent runs a multi-turn ReAct loop (main agent + sub-agents via `task()`), the user has no visibility into how close they are to the model's context window limit. This causes:

- Sudden mid-turn failures on long sessions (context overflow from the model provider).
- No actionable signal to trigger `summarization` middleware before a failure.
- No way to compare cost / token spend across different selected models.
- Users cannot tell which sub-agent is "burning the budget".

Cursor's own IDE surfaces a tiny `Context X% (12.3k / 200k)` next to its send button; we want the same capability inside our SecManus workspace.

## Goals

1. **Realtime visibility** — Show a context-usage indicator next to the send button that updates on every LLM invocation during a live stream.
2. **Per-model accuracy** — Divisor is the selected model's real context window (not a hard-coded 200k).
3. **Actionable thresholds** — Visual warning at ≥ 70%, alert at ≥ 90%, and automatic `summarization` middleware activation before the next round at ≥ 95%.
4. **Subagent attribution** — Let power-users click the badge to see a breakdown of tokens burned by `main` vs each sub-agent in the current turn.
5. **Zero regression** — No measurable degradation to SSE throughput or to existing billing pipelines.

## Non-goals

- **No pre-send local token estimation (Opt A)** — dropped during Phase 1 gating (skipped by user). Indicator reflects post-invoke real values only.
- No cross-session aggregation — scope is the **current analysis turn**. Long-horizon usage lives in `pages/Usage.tsx` / `pages/Billing.tsx` (already shipped).
- No model-switching recommendation ("switch to 1M context") — could be a follow-up.
- No changes to `llm_usage_events` DB schema — that pipeline remains the source of truth for billing; this feature is UI-only on top of the SSE stream.

## Users

- **Security analysts** running multi-round deep-research or Web security skills, who need to know when history is about to overflow.
- **Developers / power users** debugging sub-agent behavior and cost hot-spots.
- **Billing-conscious users** who want to pick a smaller-context model when safe.

## Scope

### In scope

- **Backend**: extend `llm_invoke_start` / `llm_invoke_end` SSE events with `modelId` + `usage` fields; extend `llm_gateway.yaml` model entries with `context_window` / `max_output_tokens`; extend `GET /models` response.
- **Frontend**: new `ContextUsageBadge` component, aggregation state in `useStreamingAnalysis` + `useStreamingAnalysisMulti`, click-to-open sub-agent breakdown popover.
- **i18n**: four locales (`en` / `zh` / `ja` / `ko`).
- **Auto-summarization trigger (Opt B)**: dispatch a marker in agent state when `latestInvokeUsage / contextWindow >= 0.95`, so the existing `SummarizationMiddleware` compresses history before the next turn.

### Out of scope (this delivery)

- Local pre-send estimate via `chars/4` or `tiktoken` (Opt A, deferred).
- Persisting the live indicator value to `messages.blocks` for replay — the indicator is live-only; refresh resets it.
- Mobile-specific redesign (beyond the ≥640px breakpoint treatment).

## Dependencies

- Existing infra (all shipped):
  - `app/parsers/llm_invoke_callbacks.py` — `LlmInvokeLifecycleCallbackHandler`.
  - `app/billing/pricing.py` — `extract_token_usage_from_llm_result`.
  - `app/_vendor/deepagents/middleware/summarization.py` — summarization trigger target.
  - `src/components/AnalysisInputComposer.tsx` — host of the new badge.
  - `src/hooks/useStreamingAnalysis.ts` + `useStreamingAnalysisMulti` — SSE consumers.
- **External**: none (no new npm/pip deps; `tiktoken` explicitly rejected with Opt A).

## Success metrics

| Metric | Target |
|---|---|
| Backend SSE events carry `usage` on ≥ 99% of `llm_invoke_end` where provider returned usage metadata | Instrumented via `pytest` fixtures + live staging log check |
| SSE event body size increase per `llm_invoke_end` | < 100 bytes avg |
| Frontend indicator renders within 200ms of SSE `llm_invoke_end` arrival | Measured in E2E test |
| Auto-summarization trigger fires at ≥95% and `SummarizationMiddleware` compresses history before next LLM call | Integration test with synthetic large history |
| No regression in `test_llm_usage_per_invoke.py` or `test_billing_pricing.py` | `pytest` green |

## Open questions

None blocking — all resolved during Phase 1 gating (see `design.md ## Rationale`).
