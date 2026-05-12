# Proposal — `tool-execution-cursor-style`

## Problem

The current tool execution display in the chat timeline uses a grouped list style (`ToolExecutionBlockView`): a single collapsible "Tool Execution · X of Y Done" header with all tool rows inside. This approach has three issues:

1. **No per-tool result visibility** — users cannot see what a tool returned without opening DevTools.
2. **No success/failure indicator per tool** — all completed tools show the same green check regardless of outcome.
3. **Data loss on page reload** — `buildReActTimeline` discards `toolOutput` and `status` from `tool_result` events, even though the backend already persists these fields in the timeline.

## Goals

- Redesign tool execution rows to a **Cursor-style collapsible per-tool pattern**: each tool call shows as an independent row with a title header, status indicator (success/error), and optional expandable result panel.
- **Persist and restore** tool output and error status across page refreshes by consuming existing `toolOutput` and `status` fields from the timeline.
- **Limit result panel height** with scrollable overflow for long outputs.

## Non-goals

- Changing backend SSE event format (fields already exist).
- Changing the tool_presentation YAML configuration.
- Modifying TaskListBlockView, ThinkingBlockView, or StepBlockView.
- Adding new API endpoints.

## Users

- SecManus end users who interact with the chat analysis interface.

## Scope

- **Frontend only** (one minor backend consistency fix for `_extract_stream_events`).
- `ReActToolChild` data model extension.
- `buildReActTimeline` consumption of `toolOutput` / `status`.
- `ToolExecutionBlockView` + `ToolRowStatus` UI redesign → `ToolRowCollapsible`.
- Unit tests for data model changes.

## Dependencies

- Existing `toolOutput` and `status` fields in SSE `tool_result` events (confirmed present).
- Existing timeline persistence via `_timeline_from_events` (confirmed preserves all fields).

## Success metrics

- Tool output visible in UI after clicking a completed tool row.
- Error tools show red indicator; success tools show green indicator.
- Page refresh preserves tool output and status display.
- Long tool outputs scroll within a height-limited container.
