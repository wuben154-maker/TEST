## Why

Analysis chat currently surfaces the full agent trace as a flat text stream. That is useful for debugging but poor for product UX: tools, tasks, and human-in-the-loop prompts are hard to scan, task state is not clearly live-updated, and subagent flows add visual noise. We need a **single chronological timeline** with **lightweight, text-first** components for tools, tasks, and user input—aligned with canonical SSE (`docs/Process/SSE_EVENT_CATALOG.md`) and prior timeline work (`unify-agent-sse-timeline`).

## What Changes

- Introduce **product presentation rules** for the merged analysis timeline: normalized **tool lines** (read / web / shell / script), **Cursor-style task list** (anchored in time, in-place status updates), and **inline user input** (multiple choice and free-form), while keeping **all other content as plain text**.
- **Read-file tool rows**: merge **only adjacent** duplicate reads of the **same path** into one visible line; a later read after a non-read interruption or a write/edit to that path shows again.
- **Subagent**: **no** dedicated nested timeline chrome; at delegation time insert **one short line** (e.g. named subagent executing); following events use the **same** row types as the main agent.
- **No opaque IDs in UI**: do not show `taskId`/UUID as gray metadata; optional secondary text only when it is **human-meaningful** (e.g. truncated task title), otherwise omit.
- **User input**: no sticky/dock; control sits **in-order** on the timeline (stream pauses until response—no extra chrome required).
- Frontend implementation updates (timeline reducer/renderers, possibly small SSE payload hints); backend changes only if events lack fields needed for mapping (e.g. stable tool classification).

## Capabilities

### New Capabilities

- `timeline-product-view`: Product-facing presentation of the analysis timeline—tool line templates, task block behavior, user-input placement, read dedupe rules, and prohibition of meaningless ID chrome.

### Modified Capabilities

- `reasoning-timeline-ui`: Replace **nested subagent grouping** with **single delegation line + same row components as main** for subsequent subagent events (delta spec under this change; source baseline in `openspec/changes/unify-agent-sse-timeline/specs/reasoning-timeline-ui/spec.md`).

## Impact

- **Frontend**: analysis / reasoning timeline components, tool renderers, task aggregation from `task_*` events, HITL `decision_request` / `parameter_request` rendering.
- **Docs**: may extend `docs/Process/SSE_EVENT_CATALOG.md` only if new optional payload fields are agreed (prefer mapping from existing `toolName` + payload where possible).
- **Backend**: optional—only if tool/task events cannot be classified for UI without new metadata.
