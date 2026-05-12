# Acceptance — context-summarization-usage-orchestration (backend / API / SSE)

## Metadata

- **Slug**: `context-summarization-usage-orchestration`
- **Owner**: TBD
- **Last updated**: 2026-05-06
- **Proposal**: [`proposal.md`](./proposal.md)
- **Design**: [`design.md`](./design.md)

## Scope reference

- `design.md` § Contracts (`context_budget`, enriched `context_summarized`)
- `design.md` § Architecture (ContextBudgetAuthority, ContextMeter, summarization hook)
- `design.md` § Persistence v2 (optional mirror; backend continues to store client JSON verbatim)

## Environment

- Local: `python-agent-service` + Postgres checkpointer as needed; `npm run dev` for frontend consumers of SSE.
- Feature flag (optional): `CONTEXT_BUDGET_SSE_ENABLED` — if used, document in `settings.py`.

## Functional criteria

| ID | Criterion |
|----|-----------|
| A-01 | Given a main-scope LLM call completes with non-empty `usage.inputTokens`, when SSE is emitted, then a `context_budget` event (or documented merged envelope) includes `promptTokens`, `contextWindow`, `fillRatio`, `tier`, `fillSource`, and `scope==="main"`. |
| A-02 | Given provider usage is missing for a main call, when fallback applies, then `fillSource` reflects `approximate` or `merged` per `design.md` pseudocode decision recorded in implementation notes. |
| A-03 | Given `context_window` in catalog and `model.profile.max_input_tokens` disagree, then `ContextWindowResolver` documents precedence and unit tests lock the chosen rule. |
| A-04 | Given merged fill crosses `context_compress_trigger_ratio`, when the next model invocation runs, then summarization path executes before context overflow in controlled replay tests (fixture with long message list). |
| A-05 | Given summarization completes, when SSE emits `context_summarized`, then enriched fields (`cutoffIndex` and/or `historyPath`) match middleware state without leaking raw message content. |
| A-06 | Given subagent LLM calls, when `context_budget` is emitted, then `scope==="subagent"` for those events and main-thread meter is not overwritten incorrectly (integration assertion). |
| A-07 | Given existing clients that ignore `context_budget`, when streaming, then `llm_invoke_end` remains valid and unchanged in required fields. |

## Non-functional criteria

| ID | Criterion |
|----|-----------|
| N-01 | Additional SSE processing adds negligible latency: budget computation p95 \< **5 ms** per turn on dev hardware (document measurement method). |
| N-02 | No secrets in SSE payloads or debug logs (paths only; no message bodies). |
| N-03 | Idempotent handling: duplicate summarization cutoffs do not duplicate critical side effects (regression test). |

## Evidence

- A-01 / A-05: `pytest` logs or captured SSE JSON from `tests/test_*`.
- A-04: dedicated replay test file cited in `design.md` testing strategy.
- N-01: simple timing in test or script note.

## Sign-off

| Criterion | Pass/Fail | Verifier | Date | Notes |
|-----------|-----------|----------|------|-------|
| A-01 | | | | |
| A-02 | | | | |
| A-03 | | | | |
| A-04 | | | | |
| A-05 | | | | |
| A-06 | | | | |
| A-07 | | | | |
| N-01 | | | | |
| N-02 | | | | |
| N-03 | | | | |
