## 1. Audit and row model

- [x] 1.1 Inventory current timeline reducer, `ThinkingEventType` handling, and subagent merge paths (`TimelineActivity`, `timelineDisplay`, analysis hook).
- [x] 1.2 Define internal discriminated row types (`text`, `tool_line`, `task_block`, `user_input`, `delegation_line`) and document mapping from canonical SSE types.

## 2. Tool line templates

- [x] 2.1 Implement `toolName` → template registry with fallbacks; cover read file, web search/fetch URL, shell command + output, script path.
- [x] 2.2 Implement adjacent **Read** collapse for identical normalized paths with interruption rules; add unit tests for merge, break on other tools, and break on configured write/edit/delete tools.
- [x] 2.3 Ensure loading → success/error states for tools remain text-first (spinner or subtle prefix acceptable).

## 3. Task block (Cursor-like)

- [x] 3.1 On first task-plan/create batch, insert anchored `task_block` node; merge `task_update` / completion events into in-place state without moving the block.
- [x] 3.2 Style list rows (pending / in progress / done) consistent with product design tokens; no UUID/`taskId` chips.
- [x] 3.3 Verify chronological ordering: items after the block in the stream render below the block.

## 4. User input inline

- [x] 4.1 Render `decision_request` as inline choice control at timeline index; submit resumes stream per existing HITL wiring.
- [x] 4.2 Render `parameter_request` as inline form/fields; optional confirmation text line after submit.
- [x] 4.3 Confirm no sticky/floating HITL-only chrome was introduced.

## 5. Subagent presentation

- [x] 5.1 Detect subagent invocation start signal already present in merged SSE; insert single `delegation_line` row.
- [x] 5.2 Remove or bypass nested subagent container styling; ensure following tool/reasoning rows use main templates.
- [x] 5.3 Guard against duplicate delegation lines per invocation (idempotent reducer logic).

## 6. Plain text and Thinking

- [x] 6.1 Keep `reasoning`, `conclusion`, `understanding`, and generic steps as plain text/markdown body unless covered by specialized templates.
- [x] 6.2 Preserve existing “Thinking” phase behavior from `reasoning-timeline-ui` where it does not conflict with new rows.

## 7. Replay, docs, and QA

- [x] 7.1 Replay stored canonical timelines from DB/fixtures; snapshot tests for row order and task state updates.
- [x] 7.2 Cross-check implementation against `specs/timeline-product-view/spec.md` and delta `specs/reasoning-timeline-ui/spec.md`.
- [x] 7.3 Update `docs/Process/SSE_EVENT_CATALOG.md` only if new optional fields are added (prefer avoiding).
