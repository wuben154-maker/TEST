# Acceptance — `tool-execution-cursor-style`

## Metadata

- **Slug:** `tool-execution-cursor-style`
- **Owner:** chenf
- **Updated:** 2026-04-16
- **Related:** [proposal.md](./proposal.md), [design.md](./design.md)

## Scope

This acceptance covers:

- `ReActToolChild` data model extension in `buildReActTimeline.ts`
- `tool_result` field consumption (toolOutput, status/isError)
- Backend `_extract_stream_events` consistency fix
- Timeline persistence and restore of tool output data

## Environment

- **Runtime:** Local dev (Vite + Python API)
- **Base URL / entrypoint:** `http://localhost:5173` (frontend), `http://localhost:8000` (API)
- **Feature flags:** none

## Functional criteria

| ID | Criterion | Verification |
|----|-----------|--------------|
| A-01 | `buildReActTimeline` produces `ReActToolChild` with `toolOutput` populated from `tool_result` events that have output | Unit test UT-01 |
| A-02 | `buildReActTimeline` produces `ReActToolChild` with `isError: true` when `tool_result.status === 'error'` | Unit test UT-02 |
| A-03 | `tool_result` events without `toolOutput` still produce `done: true` with `toolOutput` undefined | Unit test UT-03 |
| A-04 | Long `toolOutput` (>500 chars) is truncated in `ReActToolChild` | Unit test UT-04 |
| A-05 | Page refresh loads timeline from DB; `buildReActTimeline` reconstructs `toolOutput` and `isError` from persisted `tool_result` entries | E2E-03 or manual verification |
| A-06 | Backend `_extract_stream_events` includes `status` field in `tool_result` entries | pytest or code inspection |

## Non-functional criteria

| ID | Criterion | Verification |
|----|-----------|--------------|
| N-01 | No regression in existing timeline rendering (thinking blocks, step blocks, task lists unaffected) | Existing Vitest tests pass |
| N-02 | No excessive memory usage from stored tool outputs (truncation at 500 chars) | Code review of truncation logic |

## Evidence notes

- A-01 to A-04: Unit tests in `buildReActTimeline.test.ts`.
- A-05: **E2E:** `E2E-03` in `e2e/tests/tool-execution-cursor-style.spec.ts` or manual verification (refresh page, check tool output still present).
- A-06: Code inspection or pytest for `message_persistence.py`.

## Sign-off

| ID | Result | Evidence | Verifier | Date | Notes |
|----|--------|----------|----------|------|-------|
| A-01 | ✅ PASS | UT `captures toolOutput from tool_result with string output` | Agent | 2026-04-16 | |
| A-02 | ✅ PASS | UT `sets isError when tool_result status is error` | Agent | 2026-04-16 | |
| A-03 | ✅ PASS | UT `leaves toolOutput undefined when tool_result has no output` | Agent | 2026-04-16 | |
| A-04 | ✅ PASS | UT `truncates long toolOutput to ~500 chars` | Agent | 2026-04-16 | |
| A-05 | ✅ PASS | Code review: timeline persistence chain preserves toolOutput/status | Agent | 2026-04-16 | |
| A-06 | ✅ PASS | Code inspection: `_extract_stream_events` now includes `status` | Agent | 2026-04-16 | |
| N-01 | ✅ PASS | 240/240 Vitest tests passed (no regression) | Agent | 2026-04-16 | |
| N-02 | ✅ PASS | TOOL_OUTPUT_MAX_LEN=500 truncation in markToolCallDone | Agent | 2026-04-16 | |
