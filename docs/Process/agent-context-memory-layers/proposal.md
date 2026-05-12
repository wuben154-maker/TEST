# Proposal: Agent context & memory layers

## Problem

The product needs **coherent long-lived context** for security analysis across:

- **User scope**: habits, cross-project navigation, and a **light index** of projects (not full chat dumps).
- **Project scope**: multi-turn reasoning (checkpointer), **structured “derived” facts** (IOCs, conclusions, open questions) without duplicating `messages`, and **alignment** with Supabase `messages` after refresh/re-login.
- **Operations**: updates must **scale by active usage**, not by “N users in a nightly cron”.

Today, long-term store for `ContextRetriever` is **disabled** (`store_backend=None`), and **derived / user-level** layers are **not specified or persisted**. Main prompt does not systematically guide **historical reference** or **comparison** behavior when the graph state is summarized or cold.

## Goals

1. **Define and implement** a **three-layer memory model** (user index + project derived + session/checkpointer) with clear **read/write triggers** (event-driven, incremental).
2. **Persist** project-derived and user-level index data in **PostgreSQL** (existing patterns: `agent_store`, Supabase), with **RLS/tenant** rules consistent with the rest of SecManus.
3. **Inject** minimal, bounded context into `/analyze` (e.g. `[Project memory]`, optional `[User context]`) without blowing token budgets.
4. **Document** checkpointer vs `messages` responsibilities; add **hydration or tooling** so “compare last two turns” remains reliable when middleware has summarized or checkpoint is cold.
5. **Configure** a **small / fast model** (via existing LLM gateway) for summarization/merge tasks, with **rule-first** extraction for IOCs where possible.

## Non-goals (initial slice)

- **Vector search** / pgvector for all history (optional later).
- **Full UI** for editing memory in v1 (optional follow-up); this slice is **backend + prompt + contracts** first.
- **Replacing** `messages` as source of truth for the product UI.
- **Global nightly jobs** that recompute memory for every user.

## Users

- **End users**: analysts continuing work across sessions and projects.
- **Operators**: need observability, cost control, and safe defaults.

## Scope (v1)

- Schema + service layer for **project derived memory** and **user-level index** (exact table vs `agent_store` namespace decided in `design.md`).
- **Post-analyze** (or async queue) incremental update path; **user index** updated when project derived layer changes.
- **Injection** on relevant `/analyze` requests; **feature flag** to disable.
- **Prompt** updates in `MASTER_AGENT.md` for historical reference, comparison, and uncertainty after summarization.
- **Gateway env** for summary model id + fallback behavior.
- **Tests**: unit/integration for merge idempotency, injection boundaries, and auth/tenant checks.

## Dependencies

- Existing: FastAPI `/analyze`, LangGraph checkpointer (AsyncPostgres in prod path), `messages` persistence, `app/backends/store.py`, LLM gateway.
- Coordination: message persistence writer (“single writer”) must not conflict with derived updates (ordering defined in design).

## Success metrics

- **Functional**: After two turns in a project, derived layer contains stable entities; user index row updates; injection visible in logs (redacted) in dev.
- **Cost/latency**: Summary path p95 within agreed budget (see `acceptance.md`); no full-table scan per request.
- **Safety**: No cross-user leakage in storage or injection (tests + RLS).

## Open questions (resolved for planning)

| Topic | Direction |
|-------|-----------|
| Cron for 10k users | **Avoid** full scans; **event-driven** + optional **batched** compaction job with LIMIT/cursor. |
| Small model | Separate **gateway model id** for derived/summary; **rules first** for IOC extraction. |
| Refresh / short-term | **Persistent** checkpointer + optional **hydration** from `messages` when thread empty or stale. |

## Related documents

- [design.md](./design.md) — implementation source of truth.
- [acceptance.md](./acceptance.md) — verification criteria.
- [acceptance-ui.md](./acceptance-ui.md) — UI scope for this slice (none in v1).
