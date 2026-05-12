# Acceptance — `analysis-sse-layering`

## Metadata

- **Slug:** `analysis-sse-layering`
- **Owner:** (team)
- **Updated:** 2026-03-28 (backend `app/sse` required + registry criteria)
- **Related:** [proposal.md](./proposal.md), [design.md](./design.md)

## Scope

This acceptance covers:

- Frontend SSE **L1/L2** refactor (Slice A): transport parsing + `ThinkingEvent` narrowing; **no change** to observable SSE JSON contract.
- Shared **`write_todos` → task plan** extraction used by `applyStreamingSwitch` and `multiAnalyzeStreamEvents`.
- **Backend (required):** Python **`python-agent-service/app/sse/`** — **`framing.py`**（`create_sse_message` 唯一实现）、**`envelope.py`**（`schemaVersion`/`seq`/`scope`/`turn` 等信封逻辑集中）；**wire format 与重构前一致**，pytest 证明等价。
- **Slice B** — **Tool presentation registry** (see [design.md](./design.md) **Tool presentation registry**): backend merged table `toolName → toolPresentation[/parameterControl]`; adapter lookup + DEFAULT + observability. **Sign-off A-05+** applies only when Slice B ships in the same or a follow-up PR.

## Environment

- **Runtime:** Local dev — Vite frontend + `python-agent-service` per repo README / `AGENT.md`.
- **Base URL:** e.g. `http://localhost:8000` (API), frontend per Vite config.
- **Feature flags:** none for Slice A.

## Functional criteria

| ID | Criterion | Verification |
| --- | --- | --- |
| A-01 | Given a captured or live `POST /analyze` **stream=true** response, when parsed with the **new L1** helper using the same byte sequence as before refactor, then emitted JSON objects match **per-event** the legacy inline parser (order and `type`/`id` fields for a fixed fixture). | Vitest fixture in `readSseJsonLines.test.ts` + optional manual diff against pre-refactor branch |
| A-02 | `write_todos` **tool_call** still drives task list / task plan UI the same way as before (tasks appear, statuses map pending/in_progress/completed). | `multiAnalyzeStreamEvents.test.ts` / manual `/qa` session; E2E `test_e2e_full_stream.py` when LLM keys present |
| A-03 | `POST /analyze/resume` SSE stream still dispatches HITL-related events without regression (same handlers invoked for `decision_request` / `parameter_request` as applicable). | Existing tests + manual resume flow |
| A-04 | Multi-project stream: events with **mismatched `requestId`** are ignored (no timeline append / no state mutation), same as current behavior. | `multiAnalyzeStreamEvents.test.ts` or new unit covering filter |
| A-04b | **(Backend packaging)** Every HTTP SSE response path in `python-agent-service` that formats `data: …` uses **`create_sse_message`** from **`app.sse.framing`** (no duplicate ad-hoc `data: {json}` builders left in `main.py` except re-export/import). | Grep / code review checklist + pytest on representative routes |
| A-04c | **(Backend packaging)** Envelope application for streamed analysis events uses **`app.sse.envelope`** (or the single module name chosen in `design.md`); **`test_deepagents_stream_adapter`** (and related) still pass. | `pytest` |
| A-05 | **(Slice B)** Every emitted SSE `tool_call` for a **registered** system/framework tool includes `toolPresentation` (and `parameterControl` when `toolPresentation === 'parameter'`) **matching** the merged registry definition in repo. | Parametrized pytest on registry + snapshot of serialized event dict |
| A-06 | **(Slice B)** For a **deliberately unregistered** `toolName`, emitted `tool_call` uses the **documented DEFAULT** `toolPresentation` and emits a **structured** log event keyed e.g. `unknown_tool_name` (with `tool_name` and request context fields as per design). | Pytest with caplog / structured logging mock; document expected fields |
| A-07 | **(Slice B)** Prefix/namespace convention (e.g. `internal_*` / `hitl_*` → default `state` unless overridden) matches `design.md` when implemented. | Unit tests for `get_presentation()` with synthetic names |

## Non-functional criteria

| ID | Criterion | Verification |
| --- | --- | --- |
| N-01 | No **new** npm or PyPI dependencies for Slice A unless recorded in `design.md` ADR. | `package.json` / `requirements*.txt` diff review |
| N-02 | No secrets or tokens committed in test fixtures. | Grep / review |
| N-03 | **(Slice B)** New tools: **who adds tool adds registry row** (or documented config + test); PR template or bot check optional — if adopted, list check name in Evidence. | Process review / CI config reference |

## Evidence notes

- A-01: Store redacted SSE text fixtures under `src/lib/sse/__fixtures__/` or inline strings in tests.
- A-02: Align with `python-agent-service/tests/test_e2e_full_stream.py` expectations for task list visibility when E2E runs.
- A-04b–A-04c: List touched route modules in PR; confirm no second copy of `create_sse_message` body.
- A-05–A-07: Reference exact module path of registry and DEFAULT chosen in `design.md` (product sign-off on DEFAULT if not `action`).

## Sign-off

| ID | Result | Verifier | Date | Notes |
| --- | --- | --- | --- | --- |
| A-01 | | | | |
| A-02 | | | | |
| A-03 | | | | |
| A-04 | | | | |
| A-04b | | | | |
| A-04c | | | | |
| A-05 | | | | |
| A-06 | | | | |
| A-07 | | | | |
| N-01 | | | | |
| N-02 | | | | |
| N-03 | | | | |
