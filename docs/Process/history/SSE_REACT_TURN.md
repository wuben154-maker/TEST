# SSE `turn` field (ReAct cycle)

## Purpose

The `turn` integer groups one **Think** phase (one or more streaming `reasoning` events) with the **Act** phase (`tool_call` / `tool_result`) that follows, until the next Think. It removes ambiguity when multiple tools run in one user request: the backend owns cycle boundaries; the UI segments reasoning by `turn` instead of inferring from `tool_result` count alone.

## Semantics

| Value | Meaning |
|-------|---------|
| `1` | First think stream and its subsequent tool calls/results (until next think). |
| `n+1` | After at least one `tool_result` in cycle `n`, the next `reasoning` chunk(s) belong to turn `n+1`. |

Rules implemented in `ReactTurnTracker` (`python-agent-service/app/parsers/react_turn.py`):

- Multiple `reasoning` events with the same `turn` are one think stream (token chunks).
- `tool_call` and `tool_result` use the **same** `turn` as the think that preceded them in that cycle.
- Each `tool_result` sets `pending_next = current_turn + 1`; multiple parallel `tool_result` events overwrite the same pending value so the next think only advances **once**.
- `conclusion` / `task_summary` use `turn_for_terminal_output()` (pending cycle if tools finished without trailing reasoning).

## Where `turn` is set

| Path | Tracker |
|------|---------|
| Main graph SSE | `adapt_astream_to_sse` → `main_turn` |
| Subagent merged into main SSE | `adapt_subagent_astream_to_skill_events` → `sub_turn` (per invocation; `attach_turn` before `_tag_merged_subagent_sse` when `sse_seq_counter` is set) |
| Standalone skill stream (`sse_seq_counter is None`) | `attach_turn` only; **no** id prefix from `_tag_merged_subagent_sse` (legacy behavior) |
| Open deep research queue | `research_turn` in `open_deep_research_compiled.py` per subagent run |
| Vendor subagent values stream | `sub_turn` in `_ainvoke_subagent_with_sse_queue` |
| Task planner subagent streaming | `_react_turn` in `_execute_subagent_task` |

Events that already include `turn` (e.g. replayed timeline) are left unchanged (`attach_turn_to_event` is idempotent).

## Frontend

- `AnalysisTimelineEntry.turn` and `ThinkingEvent.turn` (`src/types/analysis.ts`).
- `aggregateReasoningSegmentsFromTimeline(entries, { scope?: 'main' | 'subagent' })` defaults to **`main`** so main-agent reasoning text does not collide with subagent turns in the same array.
- Segmentation is **only** by `turn` on `reasoning` rows; a missing `turn` is treated as **`0`** (same bucket for that scope).
- Subagent rows: `mergeSubagentReasoningByTurn` in `TimelineActivity.tsx` merges consecutive `reasoning` events with the same effective `turn`.

## References

- Event catalog (all `ThinkingEventType` + envelope + subagent merge map): [SSE_EVENT_CATALOG.md](./SSE_EVENT_CATALOG.md).
- LangGraph / Deep Agents streaming: [Deep Agents streaming](https://docs.langchain.com/oss/python/deepagents/streaming) (namespaces for main vs subgraph; custom `get_stream_writer` for extra signals).
- Design notes: `openspec/changes/unify-agent-sse-timeline/design.md`.
