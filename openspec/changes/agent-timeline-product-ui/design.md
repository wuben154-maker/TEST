## Context

- Canonical SSE types and merge rules are documented in `docs/Process/SSE_EVENT_CATALOG.md`; ReAct turn grouping in `docs/Process/SSE_REACT_TURN.md`.
- `unify-agent-sse-timeline` introduced a merged timeline model and `reasoning-timeline-ui` spec; it currently describes **nested** subagent grouping, which conflicts with the desired **product** presentation (single delegation line, same rows as main).
- Frontend already has timeline types (`ThinkingEventType`, `AnalysisTimelineEntry`) and display helpers (e.g. `timelineDisplay.ts`, `TimelineActivity.tsx` per catalog references).
- Human-in-the-loop events (`decision_request`, `parameter_request`) exist; graphs may block until the user responds—no extra sticky UI is required if the control is placed in-order.

## Goals / Non-Goals

**Goals:**

- One **strictly chronological** user-visible list after merge/reduction.
- **Three lightweight UI slots** (implementation as components, **visually** text-first):
  1. **Tool line** — normalized templates for read / web / shell / script.
  2. **Task block** — Cursor-like list; **first insertion position fixed**; rows update in place from `task_*` events.
  3. **User input** — choice and free-form **inline** on the timeline.
- **Adjacent read dedupe** for identical paths only; break on any intervening item or path-invalidating action (policy: treat write/edit/delete targeting the same path as breaking adjacency—exact tool list TBD in implementation).
- **Subagent**: one delegation line at start of invocation; subsequent events **not** wrapped in nested chrome.
- **No** user-visible `taskId`/UUID gray chips; meaningful secondary text only when copy is human-readable.

**Non-Goals:**

- Replacing SSE protocol or merging algorithm (unless a field is strictly necessary—prefer client-side mapping).
- Rich dashboards, graph views, or sticky HITL docks.
- Full parity with Cursor internals; **similar** task affordances only.

## Decisions

### D1 — Reducer produces discriminated row kinds

- **Choice**: Extend the timeline reducer (or equivalent) to emit internal row models: `text`, `tool_line`, `task_block`, `user_input`, `delegation_line` (subagent), preserving order.
- **Rationale**: Keeps React render dumb and testable; collapse rules (reads) apply in one place.
- **Alternatives**: Template logic scattered in JSX (harder to test and replay).

### D2 — Tool template selection by `toolName` + payload shape

- **Choice**: Maintain a small registry `toolName` → template kind; fallback to generic `Run <name>` + truncated JSON for unknown tools.
- **Rationale**: Matches “style like text” without backend churn.
- **Alternatives**: New SSE field `ui_kind` on every tool—cleaner long-term but requires backend release coordination.

### D3 — Task block is a stable anchor node

- **Choice**: On first `task_create` / `task_plan` / batch that opens a list, insert a **single** timeline node with id `task-board:<sessionTurnOrSeq>`; merge all later `task_update` into that node’s state.
- **Rationale**: Prevents “runaway” list jumping; satisfies “dynamic update, static position.”
- **Alternatives**: Re-emit full list rows each time—simpler but may duplicate or shift unless keyed carefully.

### D4 — Subagent delegation line source

- **Choice**: Emit delegation line when detecting subagent boundary events (e.g. `step` with subagent start, merged `skill_start` legacy, or explicit `reasoning` with subagent metadata—**use whatever the codebase already marks**). Copy: one line, e.g. `子 Agent：{display_name} 执行中` / English equivalent per i18n.
- **Rationale**: Aligns with “no special handling” for following rows.
- **Alternatives**: Nested `TimelineActivity`—explicitly rejected by product.

### D5 — Read adjacency collapse algorithm

- **Choice**: While reducing `tool_result`/`tool_call` pairs to `tool_line` rows, coalesce consecutive `Read P` into one if `P` normalized equals previous and **no other row** was emitted since last `Read P`.
- **Rationale**: Matches user clarification.
- **Edge case**: Partial reads / line ranges—if product later needs “Read P (lines 1–50)”, extend template; initial scope is path-only.

### D6 — Meaningful secondary labels only

- **Choice**: No `taskId` in UI; if future need to relate a tool to a task, show optional snippet from **task title** only when backend forwards a stable `taskTitle` or client can resolve from open task list—otherwise omit.
- **Rationale**: Cursor-like cleanliness.

## Risks / Trade-offs

- **[Risk] Tool naming drift** — Mapping breaks when agents rename tools → **Mitigation**: fallback row + telemetry for unmapped `toolName`.
- **[Risk] Task block id collisions** — Multiple plans in one user message → **Mitigation**: key anchor by first event `seq` + message id.
- **[Risk] Spec conflict with shipped nested UI** — Existing users expect nesting → **Mitigation**: feature flag or short changelog; nested mode deprecated.
- **[Risk] Write-then-read collapse** — If write tool not classified as “path break,” reads could wrongly merge → **Mitigation**: explicit break list (`write_file`, `edit_file`, `delete_file`, …) in reducer tests.

## Migration Plan

1. Ship UI behind flag if needed; default ON in dev first.
2. Verify replay: stored canonical timeline reproduces same row sequence.
3. Update user-facing docs/screenshots only if marketing references old nested UI.

## Open Questions

- Exact **toolName** inventory for web search vs fetch vs run_terminal_cmd in this product—finalize table in implementation.
- Whether **subagent delegation** should be driven only by backend-sent `step` or also heuristics when `scope=subagent` flips—prefer single explicit signal to avoid duplicate lines.
- i18n strings for delegation and tool prefixes (CN/EN).
