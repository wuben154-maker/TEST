## Metadata

- **slug:** llm-timeout-sse-status-fix
- **date:** 2026-04-16
- **tier:** Patch

## Problem

1. LLM factory (`get_model`) creates chat models **without** a per-request `timeout` — a single model inference can run indefinitely (observed: 872 s "Thinking").
   - Sub-problem A: HTTP read timeout missing entirely
   - Sub-problem B: HTTP read timeout is per-chunk, NOT total duration — extended thinking streams tokens slowly, so read timeout never triggers
   - Sub-problem C: SDK default `max_retries=2` → 3× timeout multiplier
2. Subagent SSE bridge hardcodes `"status": "success"` for every `tool_result`, even when the tool returned an error JSON — frontend cannot distinguish failures.

## Todo list

- [x] **add-llm-timeout-setting** — Add `llm_request_timeout_seconds` + `subagent_timeout_seconds` to `Settings`
- [x] **factory-pass-timeout** — Pass `timeout` + `max_retries=0` to every ChatXxx constructor in `get_model`
- [x] **subagent-total-timeout** — Wrap subagent `astream` loop with `asyncio.timeout(subagent_timeout_seconds)`
- [x] **sse-tool-result-status** — Derive `tool_result` status from output content (both subagent bridge and main stream adapter)
- [x] **env-example** — Document new settings in `.env.example`
- [x] **tests** — Unit tests for timeout propagation and status derivation

## Code touch list

| File | Change |
|------|--------|
| `python-agent-service/app/config/settings.py` | Add `llm_request_timeout_seconds: int = 120` + `subagent_timeout_seconds: int = 300` |
| `python-agent-service/app/llm_gateway/factory.py` | Read setting, pass `timeout` + `max_retries=0` to all providers |
| `python-agent-service/app/_vendor/deepagents/middleware/subagents.py` | Replace hardcoded `"success"` with `_derive_tool_status()` |
| `python-agent-service/app/parsers/deepagents_stream_adapter.py` | Same status derivation for main-agent tool_result |
| `python-agent-service/.env.example` | Add `LLM_REQUEST_TIMEOUT_SECONDS=120` |
| `python-agent-service/tests/test_llm_gateway.py` | Assert timeout propagated |
| `python-agent-service/tests/test_sse_tool_status.py` (new) | Test status derivation logic |

## Testing strategy

- **Unit:** Verify `get_model()` passes `timeout` for each provider; verify `_derive_tool_status` returns `"error"` when JSON contains `"error"` key with truthy value.
- **Integration:** Existing `test_llm_gateway.py` tests must remain green.

## Rationale

- **Three-layer timeout strategy:**
  1. `llm_request_timeout_seconds=120` — HTTP read timeout (per-chunk idle). Catches dead connections.
  2. `subagent_timeout_seconds=300` — `asyncio.timeout()` wrapping `astream` loop. **This is the one that caps total wall-clock** for extended thinking.
  3. `timeout_seconds=300` — Session-level outer timeout (existing, unchanged).
- `max_retries=0` — Prevents SDK retry multiplication (default 2 = 3× multiplier).
- Status derivation uses a lightweight JSON-parse check (try parse → look for `"error"` key) rather than string matching to avoid false positives.
