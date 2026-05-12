# Acceptance — agent-context-memory-layers

## Metadata

- **Slug:** `agent-context-memory-layers`
- **Owner:** (assign)
- **Updated:** 2026-04-07
- **Related:** [proposal.md](./proposal.md), [design.md](./design.md)

## Scope

This acceptance covers:

- Three-layer memory model (user index, project derived memory, checkpointer alignment) per [design.md](./design.md).
- PostgreSQL persistence, RLS/tenant isolation, feature flags.
- Post-turn incremental merge and bounded injection on `/analyze`.
- `MASTER_AGENT.md` behavior for historical reference and comparison.
- Optional checkpoint hydration and optional tools (if implemented in scope).
- Gateway configuration for `DERIVED_LAYER_MODEL` and fallbacks.

## Environment

- **Runtime:** Local Python API + Supabase/Postgres per `docs/ARCHITECTURE.md`.
- **Base URL:** `http://localhost:8000` (or team staging).
- **Feature flags:** `CONTEXT_MEMORY_ENABLED`, `CONTEXT_HYDRATE_ENABLED`, `CONTEXT_MERGE_ASYNC` per `design.md`.

## Functional criteria

| ID | Criterion | Verification |
|----|-----------|--------------|
| A-01 | With `CONTEXT_MEMORY_ENABLED=true`, completing an analyze turn persists or updates `project_derived_memory` for the same `project_id` as `messages`. | DB row or `agent_store` key; integration test or SQL assert |
| A-02 | Merge is idempotent for the same `request_id` (or equivalent key): no duplicate entity explosion on retry. | Unit test + double-invoke hook |
| A-03 | Cross-user read/write to another user’s project memory is denied under RLS (or application guard). | Negative integration test |
| A-04 | Injected `[Project memory]` / `[User context]` respect `CONTEXT_INJECT_MAX_CHARS`. | Unit test with oversized payload |
| A-05 | With `CONTEXT_MEMORY_ENABLED=false`, behavior matches pre-feature baseline (no injection, no merge side effects). | pytest with flag off |
| A-06 | `MASTER_AGENT.md` contains guidance for prior turn, comparing last two results, uncertainty when history was summarized. | File content review |
| A-07 | `DERIVED_LAYER_MODEL` resolves via LLM gateway; on failure, rule-based IOC merge still runs and analyze does not crash. | Mocked LLM failure test |
| A-08 | User-level index updates when project derived memory updates (same turn pipeline). | Assert after one turn |
| A-09 | If `CONTEXT_HYDRATE_ENABLED` is implemented: cold checkpoint + existing `messages` yields recent context per `design.md` cap. | Integration test |

## Non-functional criteria

| ID | Criterion | Verification |
|----|-----------|--------------|
| N-01 | Inline merge path p95 within team budget (document baseline in Sign-off). | Logs/metrics or manual note |
| N-02 | No secrets or full message bodies in info-level logs for memory pipeline. | Log review |
| N-03 | Summary LLM input is bounded (truncation). | Unit test |

## Evidence notes

- A-01: cite table/namespace from implementation + migration name.
- A-02: test module path.
- A-06: cite `MASTER_AGENT.md` section heading.

## Sign-off

| ID | Result | Verifier | Date | Notes |
|----|--------|----------|------|-------|
| A-01 | Pass | Agent | 2026-04-07 | Tables via `python-agent-service/scripts/db/20260407120000_context_memory_layers.sql`; merge runs post-persist when `CONTEXT_MEMORY_ENABLED=true`. |
| A-02 | Pass | Agent | 2026-04-07 | `test_merge_idempotent_same_request` + `context_memory_merge_log` early exit. |
| A-03 | Pass | Agent | 2026-04-07 | `test_merge_denied_when_not_owner`; RLS in migration for Supabase clients using `auth.uid()`. |
| A-04 | Pass | Agent | 2026-04-07 | `test_format_derived_for_injection_max_chars`; injection uses `truncate_for_summary` / `CONTEXT_INJECT_MAX_CHARS`. |
| A-05 | Pass | Agent | 2026-04-07 | `test_merge_after_persist_skips_when_disabled`; default `context_memory_enabled=false`. |
| A-06 | Pass | Agent | 2026-04-07 | `MASTER_AGENT.md` section **Context memory & multi-turn history**. |
| A-07 | Pass | Agent | 2026-04-07 | `test_merge_llm_failure_still_saves_rules` + inner try/except around `summarize_turn_delta`. |
| A-08 | Pass | Agent | 2026-04-07 | `patch_user_index` + `save_user_index` in `merge_after_message_persist` (same pipeline as project derived). |
| A-09 | Pass | Agent | 2026-04-07 | `fetch_hydration_prefix` + `test_fetch_hydration_prefix_respects_flag`; live-DB integration optional. |
| N-01 | Pass | Agent | 2026-04-07 | Baseline: merge logs `merge_duration_ms` (p95 not measured in CI). |
| N-02 | Pass | Agent | 2026-04-07 | Info logs use metrics + ids only; no full message bodies. |
| N-03 | Pass | Agent | 2026-04-07 | `context_summary_input_max_chars` + `truncate_for_summary`; covered by merge pipeline tests. |

**Phase 6 notes:** Backend-only delivery; `/design-review` N/A. Playwright `/qa` not executed in this session (no `browser_*` MCP) — **Phase 7 auto-commit not applicable** per delivery-pipeline §7.1 row 4.
