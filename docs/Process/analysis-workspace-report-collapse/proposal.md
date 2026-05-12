# Proposal — analysis-workspace-report-collapse

## Problem

After submitting analysis from the transition flow, the desktop workspace defaults to a split view (chat + report). Users want the chat column to use full width at the start of a turn when the report side has nothing meaningful yet, and only expand the report area when workspace tabs exist or on reload when persisted data indicates tabs. Wide screens should not stretch chat text edge-to-edge; content should be max-width centered (Cursor-like).

## Goals

- Default report panel to collapsed spatially at the beginning of a new analysis when the user has **not** manually resized the split via drag.
- Auto-expand when `workspaceTabs` first appears in the stream (even if report body is still empty).
- On project load / refresh, expand only if persisted project data includes **any** `workspaceTabs` on assistant messages or analysis results.
- Respect **manual drag** of the resize handle: once the user has dragged the split for the current project (session), do **not** auto-collapse the report when a **new** analysis starts.
- Constrain chat column content to a centered max width when the chat pane is wide.

## Non-goals

- Changing report/workspace internal business logic or tab rendering.
- Mobile layout (existing mobile overlay unchanged).

## Success metrics

- Fewer accidental “empty right pane” distractions on simple Q&A.
- Deep-research sessions still surface the report side when tabs exist.
- No regression in resizable panels or cycling control.
