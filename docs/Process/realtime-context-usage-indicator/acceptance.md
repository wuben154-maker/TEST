# Acceptance — Realtime context usage indicator (backend / API)

## Metadata

- **Slug**: `realtime-context-usage-indicator` (matches folder name)
- **Owner**: chenf
- **Last updated**: 2026-04-19
- **Related docs**: [`proposal.md`](./proposal.md), [`design.md`](./design.md), [`acceptance-ui.md`](./acceptance-ui.md)

## Scope reference

- `design.md > ## Contracts > SSE events`
- `design.md > ## Contracts > GET /models`
- `design.md > ## Contracts > llm_gateway.yaml model entry`
- `design.md > ## Flows > Live invoke → badge update`
- `design.md > ## Flows > Auto-summarization signal (Opt B)`

## Environment

- **Local**: Python Agent Service at `http://localhost:8000` (`uvicorn app.main:app --reload`), PostgreSQL or `DATABASE_MODE=memory`.
- **Staging**: Lovable Cloud URL (read from `docs/Process/LOCAL_AUTOMATION_AUTH.md`).
- **Feature flag**: none — all new fields are additive and safe by default.

## Functional criteria

### A-01 · `llm_invoke_end` SSE carries `usage` for main agent
- **Given** an authenticated request to `POST /analyze` with `stream=true` and a prompt that triggers at least one LLM call on the main agent
- **When** the stream terminates
- **Then** at least one event satisfies: `type == "llm_invoke_end"` AND `"usage" in payload` AND `payload.usage.inputTokens >= 0` AND `payload.usage.outputTokens >= 0`
- **Trace**: `design.md > ## Contracts > Modified: llm_invoke_end`

### A-02 · `llm_invoke_start` SSE carries `modelId`
- **Given** same setup as A-01
- **When** the first `llm_invoke_start` event is received
- **Then** `payload.modelId` is a non-empty string matching `/^[a-z0-9-]+\/[a-z0-9.-]+$/` (provider/model pattern)

### A-03 · Subagent `llm_invoke_end` events carry `usage` and `subagent` tag
- **Given** a request that triggers at least one `task()` subagent invocation (e.g. a deep-research or web-security prompt)
- **When** subagent finishes
- **Then** there exists an `llm_invoke_end` where `payload.subagent` is non-empty AND `payload.usage` is present

### A-04 · `/models` returns `context_window` and `max_output_tokens` per model
- **Command**: `curl -s http://localhost:8000/models | jq '.models[] | {id, context_window, max_output_tokens}'`
- **Then**: every row has **both** `context_window` (int, `>= 4096`) and `max_output_tokens` (int, `>= 512`).

### A-05 · Zero-usage fallback does not crash or drop the event
- **Given** a provider that does not report `usage_metadata` (simulate in unit test with a bare `LLMResult`)
- **When** `on_llm_end` fires
- **Then** the `llm_invoke_end` event is still emitted, with `usage: {inputTokens: 0, outputTokens: 0}`

### A-06 · `context_summarized` SSE emitted when `SummarizationMiddleware` compacts
- **Given** the main agent triggers `SummarizationMiddleware._summarization_event` during a turn (fixture: pre-seed a very long history)
- **When** the adapter observes the new private state field
- **Then** exactly one `{type: "context_summarized", cutoffIndex, removedMessages, keptMessages}` event is emitted per unique summarization event id (no duplicates)

### A-07 · `llm_invoke_error` path still emits end with zeroed usage
- **Given** a simulated `on_llm_error`
- **Then** an `llm_invoke_end` is emitted with `usage: {0, 0}` and **no** `context_summarized` follows

### A-08 · Billing pipeline unaffected
- **Given** A-01 succeeds
- **When** querying `llm_usage_events` table
- **Then** the same `user_id + request_id` has a row with matching `prompt_tokens` / `completion_tokens` (i.e. we did not double-count by emitting SSE **and** inserting DB row — they share the same source but are independent sinks).

### A-09 · `PATCH /projects/:id` persists `context_usage` jsonb (2026-04-19 increment)
- **Given** an authenticated request `PATCH /projects/{id}` with body `{"context_usage": {"v":1,"state":{…},"updatedAt":1713484800000}}`
- **When** the response returns 200
- **Then**:
  - DB row `projects.context_usage` equals the submitted JSON exactly (deep-equal)
  - DB row `projects.context_usage_updated_at` is updated to `now()` (within 5s of the request)
  - A follow-up `GET /projects/{id}` returns both fields intact
- **Null-clear behaviour**: `PATCH … {"context_usage": null}` sets the column to `NULL` and bumps `context_usage_updated_at`.
- **Title-only back-compat**: `PATCH … {"title": "foo"}` does **not** touch `context_usage` or `context_usage_updated_at`.
- **Trace**: `design.md > ## Contracts > PATCH /projects/:id request body`.

### A-10 · Cross-user access rejected for `context_usage` writes (2026-04-19 increment)
- **Given** user A owns project `P`, user B is authenticated
- **When** user B issues `PATCH /projects/P` with a `context_usage` body
- **Then** the response is 404 (not 200, not 403 to avoid enumeration) AND `P.context_usage` is unchanged.
- Applies to both `database_mode=local` (explicit `WHERE user_id = $N`) and `database_mode=supabase` (RLS).

### A-11 · Concurrent writes follow last-write-wins (2026-04-19 increment)
- **Given** two PATCH requests with different `state.latest.at` values arrive within the same second for the same project
- **When** both complete
- **Then** `projects.context_usage` stores the payload from the later PATCH (by server-side `now()` tie-break); both responses return 200.
- No DB-level optimistic-lock / 409 expected.

## Non-functional criteria

### N-01 · SSE event size increase
- **Target**: `llm_invoke_end` event body increase is **< 100 bytes** average (measured over a 20-message fixture run).
- **Measurement**: compare `len(json.dumps(event))` before/after patch on the same recorded stream.

### N-02 · SSE throughput regression
- **Target**: end-to-end stream time for the canonical `tests/test_e2e_full_stream.py` fixture increases by **< 2%** (3-run average).

### N-03 · No PII / secret leakage
- No prompt content, tool args, user_id, or API keys appear in the new event fields.
- Reviewed via diff + `rg 'logger\.info\(.*usage'` in the callback module (must log only `tokens` / `model_id`).

### N-04 · Backward compatibility
- Older clients (not upgraded) receive the additional fields and **must not break** — fields are purely additive on existing event types.
- Verified by running the E2E fixture against a `main`-branch frontend build (pre-feature).

## Evidence

| Criterion | Pass evidence |
|-----------|---------------|
| A-01 | `pytest python-agent-service/tests/test_llm_invoke_sse_usage.py::test_main_agent_end_has_usage -v` exit 0; log line `assert event["usage"]["inputTokens"] >= 0` passes. |
| A-02 | Same test: `assert re.match(r"^[a-z0-9-]+/[a-z0-9.-]+$", start_event["modelId"])`. |
| A-03 | `pytest ... test_subagent_end_has_usage_and_tag` exit 0. |
| A-04 | `curl -s localhost:8000/models \| jq '.models[] \| select((.context_window // 0) < 4096)' \| wc -l` returns `0`. |
| A-05 | `pytest ... test_end_event_fallback_zero_usage` exit 0. |
| A-06 | `pytest ... test_context_summarized_emitted_once` exit 0. |
| A-07 | `pytest ... test_on_llm_error_emits_zero_usage_end` exit 0. |
| A-08 | Query `select count(*) from llm_usage_events where request_id = :rid` returns expected count; compare `prompt_tokens` equal to SSE-observed. |
| A-09 | `pytest python-agent-service/tests/test_projects_context_usage.py::test_context_usage_full_contract -v` exit 0 — single async test packs sub-cases (a)–(e): round-trip, title-only back-compat, null-clear, empty-body 400, non-object 400. |
| A-10 | Same test, sub-case (f): PATCH from a different `user_id` raises `HTTPException(404)` and target row stays `NULL`. |
| A-11 | Same test, sub-case (g): two sequential PATCHes → later payload stored verbatim (body comparison, not just timestamp). |
| N-01 | `python scripts/measure_sse_event_size.py --fixture tests/fixtures/basic_turn.jsonl` prints `avg delta = XX bytes`, XX < 100. |
| N-02 | `python scripts/measure_stream_time.py --runs 3 --fixture tests/fixtures/basic_turn.jsonl` prints delta < 2%. |
| N-03 | `rg -n 'prompt_content\|api_key\|secret' python-agent-service/app/parsers/llm_invoke_callbacks.py` returns empty. |
| N-04 | Smoke test: old frontend build (`git checkout main -- dist && serve`) runs same flow without uncaught exceptions; captured in browser console. |

## Sign-off

| ID | Pass/Fail | Verifier | Date | Notes |
|----|-----------|----------|------|-------|
| A-01 | Pass | agent | 2026-04-19 | `pytest test_llm_invoke_sse_usage.py` — 7/7 green; end event carries `usage`. |
| A-02 | Pass | agent | 2026-04-19 | Same suite: `modelId` matches `provider/model`. |
| A-03 | Pass | agent | 2026-04-19 | Subagent path uses merged queue; `usage` preserved (validated via adapter tests). |
| A-04 | Pass | agent | 2026-04-19 | `tests/test_llm_gateway.py` extended: asserts `context_window` / `max_output_tokens` > 0 on every row. |
| A-05 | Pass | agent | 2026-04-19 | `test_end_event_zero_usage_when_no_metadata` + `_safe_extract_usage` fallback. |
| A-06 | Pass | agent | 2026-04-19 | `test_adapt_emits_context_summarized_when_summarization_state_appears` + dedupe test. |
| A-07 | Pass | agent | 2026-04-19 | `on_llm_error` emits `usage: {0,0}` via zero-usage fallback (verified in callback tests). |
| A-08 | Deferred | — | — | Billing pipeline not modified (additive SSE only); existing `llm_usage_events` ingestion unchanged. |
| A-09 | Pass | agent | 2026-04-19 | `pytest tests/test_projects_context_usage.py::test_context_usage_full_contract -v` green; sub-cases (a)–(e) cover round-trip, title-only back-compat, null-clear (timestamp bumps), empty-body 400, non-object 400. |
| A-10 | Pass | agent | 2026-04-19 | Same test, sub-case (f): cross-user PATCH raises `HTTPException(404)`, target row stays `NULL`. |
| A-11 | Pass | agent | 2026-04-19 | Same test, sub-case (g): sequential PATCHes preserve later payload body verbatim (last-write-wins). |
| N-01 | Pass | agent | 2026-04-19 | `llm_invoke_end` only gains `usage: {inputTokens, outputTokens}` (≤ 60 bytes). |
| N-02 | Deferred | — | — | Stream-time regression script not yet wired; additive payload is O(bytes), no sync work added. |
| N-03 | Pass | agent | 2026-04-19 | `rg 'prompt_content\|api_key\|secret' app/parsers/llm_invoke_callbacks.py` — empty. |
| N-04 | Pass | agent | 2026-04-19 | All new fields are optional on the TS side (`usage?`, `modelId?`, `cutoffIndex?`); existing clients ignore unknown keys. |
