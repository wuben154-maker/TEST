# design.md (Patch tier lite) — deep-research-subagent-usage-attribution

## Metadata

- slug: `deep-research-subagent-usage-attribution`
- tier: **Patch** (single-file bug fix, ≤ 3 files, no new API/schema/UI)
- date: 2026-04-20
- parent delivery: [`realtime-context-usage-indicator`](../realtime-context-usage-indicator/design.md)
- status: in-progress

## Problem

Deep-research subagent turns show "No subagent activity yet" in the
context-usage popover, even though the main ring lights up correctly.
Root cause: `research_llm_emit.close()` inside
`_run_open_deep_research_subagent` drops `AIMessage.usage_metadata`, so
every `llm_invoke_end` emitted by the deep-research subgraph arrives at
the frontend **without a `usage` field**. The frontend reducer
(`applyEventToContextUsage`) short-circuits on missing `usage` and never
creates a subagent bucket, hence the empty popover.

`_extract_stream_events` (the non-streaming fallback in the same file)
already propagates `msg.usage_metadata` through `llm_invoke_triplet` —
this fix closes the parallel gap on the **streaming** path.

Main agent is unaffected: its boundaries are emitted by
`LlmInvokeLifecycleCallbackHandler` + `LlmUsagePerInvokeCallbackHandler`
in `deepagents_stream_adapter.py`, which already attach usage.

## Code touch list

| File | Change |
|------|--------|
| `python-agent-service/app/agents/research/open_deep_research_compiled.py` | Cache the latest `usage_metadata` per `chunk_id` during the `messages` stream; forward it to every `research_llm_emit.close(usage=…)` call (5 sites); clear the cache at the HITL re-run reset and on graph completion. |
| `python-agent-service/tests/test_open_deep_research_usage_attribution.py` | **New** unit test — drive the streaming path with a mocked `astream` that yields AIMessageChunks whose final chunk carries `usage_metadata`; assert the emitted `llm_invoke_end` event contains a non-zero `usage` and `scope == "subagent"`. |

No frontend changes. No schema changes. No config changes.

## Contract (unchanged, just now actually honored)

`llm_invoke_end` already specifies an optional `usage` field, normalized
by `app/parsers/llm_invoke_sse.py::_coerce_usage` into
`{"inputTokens": int, "outputTokens": int}`. We stop dropping it on the
deep-research streaming path.

## Testing strategy

**Unit (pytest)** — new file
`tests/test_open_deep_research_usage_attribution.py`:

1. **`test_research_streaming_close_forwards_usage`** — mock
   `original_research_graph.astream` to yield one
   `("messages", (AIMessageChunk(...), metadata))` event where the chunk
   has a populated `usage_metadata={"input_tokens": 1234,
   "output_tokens": 567}`, followed by an `("updates", …)` event that
   forces a `close()`. Capture SSE events via an injected
   `subagent_stream_writer`. Assert:
   - At least one emitted event has `type == "llm_invoke_end"` with
     `usage == {"inputTokens": 1234, "outputTokens": 567}`.
   - The same event is later tagged `scope == "subagent"` once routed
     through `tag_merged_subagent_sse` (simulated in-test by invoking
     the tagger directly).
2. **`test_research_streaming_close_without_usage_stays_usage_free`** —
   same mocked astream but the chunk has no `usage_metadata`. Assert
   emitted `llm_invoke_end` has **no** `usage` key (back-compat: legacy
   behavior preserved when upstream doesn't report usage).

**Regression (pytest, existing)** — run
`tests/test_*open_deep_research*` and any test that imports
`_run_open_deep_research_subagent` to ensure no shape change breaks
callers. Expected: all green.

No E2E scenarios — Patch tier, backend-only contract fix, frontend path
is already unit-tested in the parent delivery.

## Rollback

Single commit, single file of runtime code (plus a new test file). If
anything surfaces in production, revert that one commit; the deep-
research popover just goes back to "No subagent activity yet" and
nothing else regresses.
