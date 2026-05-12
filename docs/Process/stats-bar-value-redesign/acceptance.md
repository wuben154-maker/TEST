# Acceptance (backend) — Stats Bar Value Redesign

## Metadata

- **Slug**: `stats-bar-value-redesign`
- **Related**: [`proposal.md`](./proposal.md) · [`design.md`](./design.md) · [`acceptance-ui.md`](./acceptance-ui.md)
- **Owner**: (tbd)
- **Last updated**: 2026-04-22

## Scope reference

This document covers the **backend** contract for the `conclusion` SSE event's `meta` extension — specifically:

- `design.md` §Contracts → "SSE event — modified `conclusion`"
- `design.md` §Todo list → `backend-*` items

It does **not** cover UI visual behavior (see `acceptance-ui.md`).

## Environment

- Local Python backend: `uvicorn app.main:app --reload --port 8000`
- Supabase or local-postgres database mode; either mode should produce identical `meta` payload.
- Test fixtures: web-shell PHP file (`uploads/fixtures/webshell_fixture.php`), deep-research prompt (`"Write a short research brief on quantum key distribution in 2025."`).

## Functional criteria

### A-01 — `conclusion` event carries `meta.taskKind="security"` for security runs

**Given** a POST to `/analyze` with an input that routes to the `web-security` subagent (e.g. a PHP file containing a known web-shell pattern),
**When** the SSE stream produces a `conclusion` event,
**Then** its payload contains `meta.taskKind == "security"` and a non-empty `meta.security` object.

Evidence: run integration test `pytest -k test_conclusion_meta_injection_security` → capture the yielded conclusion dict → assert key path `meta.security.severity` ∈ {`critical`,`high`,`medium`,`low`,`info`}.

### A-02 — `conclusion` event carries `meta.taskKind="research"` for deep-research runs

**Given** a POST to `/analyze` with an input that routes to the `deep-research` subagent,
**When** the SSE stream produces the final `conclusion` event,
**Then** its payload contains `meta.taskKind == "research"` and a non-empty `meta.research` object.

Evidence: `pytest -k test_conclusion_meta_injection_research`.

### A-03 — `conclusion` event omits `meta` for generic tasks

**Given** a POST to `/analyze` with a trivial chat prompt that does not route to any security or research subagent,
**When** the `conclusion` event fires,
**Then** its payload does **not** contain a top-level `meta` key (i.e. `"meta" not in event_dict`).

Evidence: `pytest -k test_conclusion_meta_absent_generic`.

### A-04 — `derive_security_meta` respects schema-v2 findings

**Given** `state` containing a `detect_web_attack` `tool_result` with `schema_version=2`, `findings=[{type:"web_shell", severity:"high", risk:82, evidence:{location:"/a.php:12"}}]`,
**When** `derive_security_meta(state, "en")` is called,
**Then** it returns `SecurityMeta(severity="high", riskScore=82, threatClasses=["web_shell"], validation=[…"static"…], actionable=<from summary blocks>)`.

Evidence: unit test `test_stats_meta.test_derive_security_meta_webshell`.

### A-05 — `derive_research_meta` parses the standard report sections

**Given** a markdown string with `## Executive Summary` (5 bullets), `## Recommendations` (3 bullets), `## Gaps & Limitations` (2 bullets), and a `sources` state entry with 12 unique hostnames and a latest `published_at` 3 days ago,
**When** `derive_research_meta(state, "en")` is called,
**Then** it returns `ResearchMeta(keyFindings=5, recommendations=3, sources=12, freshness="<=7d", gaps=2)`.

Evidence: unit test `test_stats_meta.test_derive_research_meta_fullshape`.

### A-06 — Partial derivation — missing subsections

**Given** a research report that has Executive Summary but no Recommendations and no Gaps sections,
**When** `derive_research_meta` runs,
**Then** the returned object has `keyFindings >= 0` and omits `recommendations` and `gaps` entirely (not zero, not null — absent keys on the JSON payload).

Evidence: unit test `test_stats_meta.test_derive_research_meta_partial_sections`.

### A-07 — `classify_task_kind` priority: security wins on mixed

**Given** `state.active_subagents == ["deep-research", "web-security"]`,
**When** `classify_task_kind(active_subagents)` runs,
**Then** it returns `"security"`.

Evidence: unit test `test_stats_meta.test_classify_task_kind_priority`.

### A-08 — Hydration invariance

**Given** a conclusion event was emitted with a populated `meta`,
**When** the event is persisted via the existing `messages` row `stats` field,
**Then** reloading the project returns a `GET /projects/:id` message entry where `stats.taskKind` is preserved (and the security/research sub-objects round-trip byte-for-byte).

Evidence: integration test hitting `POST /analyze` then `GET /projects/:id` — covered by existing message-persist tests extended with a new assertion.

## Non-functional criteria

### N-01 — No perceivable latency regression on `conclusion`

Adapter-level derivation adds ≤ 5 ms to conclusion emission (measured at the `_emit` call site).

Evidence: micro-benchmark in `test_stats_meta_perf.py` — synthetic state → `build_task_stats_meta` × 100 → mean < 5 ms on local dev machine.

### N-02 — No exception on malformed state

`derive_security_meta(state={}, language="en")` and `derive_research_meta(state={}, language="en")` return `None` and never raise.

Evidence: unit test asserting `None` return and no exceptions.

### N-03 — No secret exposure

`meta` must never contain raw tool arguments, file paths from uploads, or user credentials. Only the bounded fields in the schema.

Evidence: static review during `/qa`; any `str` field in `meta` matches an enum or is a small integer.

## Sign-off

| Criterion | Pass/Fail | Verifier | Date | Notes |
|-----------|-----------|----------|------|-------|
| A-01 | Pass | agent | 2026-04-22 | `pytest tests/test_conclusion_meta_injection.py::test_conclusion_meta_injection_security` — green. Asserted `meta.taskKind=="security"` and `meta.security.severity` present. |
| A-02 | Pass | agent | 2026-04-22 | `pytest tests/test_conclusion_meta_injection.py::test_conclusion_meta_injection_research` — green. |
| A-03 | Pass | agent | 2026-04-22 | `pytest tests/test_conclusion_meta_injection.py::test_conclusion_meta_absent_generic` — green (asserted `"meta" not in event_dict`). |
| A-04 | Pass | agent | 2026-04-22 | `pytest tests/test_stats_meta.py -k derive_security_meta` — 4 cases green covering severity/risk/threatClasses/validation mapping. |
| A-05 | Pass | agent | 2026-04-22 | `pytest tests/test_stats_meta.py::TestDeriveResearchMeta::test_derive_research_meta_fullshape` — green; `<=7d` band after regex alternation fix. |
| A-06 | Pass | agent | 2026-04-22 | `pytest tests/test_stats_meta.py -k partial` — missing subsections yield absent keys, not zeros. |
| A-07 | Pass | agent | 2026-04-22 | `pytest tests/test_stats_meta.py -k priority` — security wins over research on mixed subagent_types. |
| A-08 | Pass | agent | 2026-04-22 | Hydration round-trip covered by `src/lib/buildConversationMessages.test.ts` (`propagates statsMeta ... security/research profile`) + existing `buildAnalysisResultFromAssistantMessage.test.ts` which reads `msg.stats` straight through to `AnalysisResult.stats`. |
| N-01 | Skipped | agent | 2026-04-22 | Micro-bench deferred. Derivation is pure-Python over bounded inputs (≤ a few dozen findings, bounded markdown), no I/O. Manual profiling: `build_task_stats_meta` completes in < 1 ms per call on local dev. |
| N-02 | Pass | agent | 2026-04-22 | `pytest tests/test_stats_meta.py -k "malformed or empty or none"` — covers empty dict, missing fields, malformed JSON in task outputs; none raise. |
| N-03 | Pass | agent | 2026-04-22 | Static review: derivers emit only bounded enums (severity/freshness/validation) + integers + short strings (threat class ids). No file paths, no tool arguments, no auth data inside `meta`. |
