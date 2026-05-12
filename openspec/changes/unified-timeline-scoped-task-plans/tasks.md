## 1. Types and SSE contract

- [x] 1.1 Extend `ThinkingEvent` / timeline types with documented optional `scope` and `subagentName` routing rules (default `main`).
- [x] 1.2 Update `docs/Process/SSE_EVENT_CATALOG.md` for scoped `task_plan` and lifecycle events (and optional `planId` / invocation id if adopted).

## 2. Scoped task plan state

- [x] 2.1 Replace single `taskPlan` with `taskPlanMain` + subagent map (or agreed shape from design D4) in `PerProjectStreamingState`.
- [x] 2.2 Route `handleTaskPlan`, `handlePlanComplete`, `task_start` / `task_complete` / `task_step` / `task_error` to the correct bucket by `scope`.
- [x] 2.3 Namespace `write_todos`-synthesized `PlannedTask.id` values (design D5); add unit tests for collision cases.
- [x] 2.4 Update conversation persistence and `ConversationMessage` hydration to store/replay scoped plans or derive from timeline.

## 3. Unified timeline builder

- [x] 3.1 Implement `buildUnifiedTimelineItems` (or equivalent) producing a discriminated union with stable `sortKey` from `seq` + tie-breakers.
- [x] 3.2 Merge responsibilities of `buildReactLinearRows` and `buildTimelineActivityChunks` into one ordered item list; **exclude** `conclusion` body from items; include `task_summary` per spec.
- [x] 3.3 Define streaming reasoning item behavior (design D3) and test against partial timeline.
- [x] 3.4 Render unified list in `CommandCenter` (remove sibling `ReactLinearTraceView` + `TimelineActivity` split for the live/history path, or wrap both behind one component).

## 4. UI and regression tests

- [x] 4.1 Vitest: ordering fixtures for interleaved `reasoning` / `task_plan` / tools / `task_summary`.
- [x] 4.2 Vitest/React: scoped task state—main `"0"` vs subagent `"0"` independence.
- [x] 4.3 Manual QA checklist: multi-subagent turn, `write_todos` + server `task_plan`, history replay after refresh.

## 5. Backend (optional but recommended)

- [x] 5.1 Emit `scope: subagent` (and `subagentName`) on subagent `task_plan` and matching lifecycle events in `python-agent-service` stream adapter.
- [x] 5.2 E2E or stream parser test: subagent plan does not inherit main task ids.
