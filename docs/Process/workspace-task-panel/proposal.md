# Proposal: workspace-task-panel

## Metadata

| Field       | Value                          |
|-------------|--------------------------------|
| Slug        | `workspace-task-panel`         |
| Date        | 2026-04-14                     |
| Status      | Draft — awaiting Phase 2 approval |
| Author      | AI Agent (Phase 1 exploration) |

---

## Problem

The current right-side workspace (`LiveWorkspace`) is a flat, vertically stacked list of `WorkspaceBlock` cards. Every analysis result is rendered as a passive, read-only "report document". There is no structural distinction between:
- The task title / metadata
- The execution evidence (which tools ran, what happened)
- The final report content

This means:
- Sandbox execution output is dumped into a `LogBlock` with no status machine or session context
- Binary analysis stages are flattened into N disconnected `AnalysisBlock` cards
- Users cannot tell at a glance what tools were invoked or what kind of analysis was performed
- There is no "live" sense — the workspace looks the same whether the agent is still running or finished

---

## Goals

1. **Structural task view**: Each task result gets a consistent 3-part layout: title row → stats bar → inner tab area.
2. **Dynamic inner tabs driven by config**: `tool_presentation.yaml` declares which tools open workspace tabs (type, label, icon, merge strategy). No hardcoded frontend switch logic per tool.
3. **Report tab always first**: The "Report" tab is always present and is the default; it shows a skeleton/pulse animation while the task is running, then renders the final blocks when done.
4. **Sandbox Shell tab**: `sandbox_run` / `sandbox_pty_run` calls open a Shell tab, merged by `sandbox_id` — same instance = one tab, different instances = separate tabs, no `sandbox_id` (one-shot) = always new tab.
5. **Preserve existing multi-result tab bar**: The outer tab bar (one tab per analysis result / task) is kept as-is.
6. **Zero backend SSE changes**: Tab lifecycle is driven by the existing `tool_call` SSE events + config file — no new event types required.

---

## Non-Goals

- No interactive graph / investigation view in this delivery (deferred to a separate slug)
- No binary analysis static/dynamic tabs in this delivery (framework is built, but specific tab components are placeholder)
- No collaborative / multi-user editing of workspace content
- No redesign of the left-side CommandCenter / reasoning timeline

---

## Users

Security analysts using SecManus to investigate IOC, binary samples, web threats, or log data. They need to understand at a glance: what did the agent do, what tools ran, what was the outcome — without reading through a wall of text blocks.

---

## Scope

**In scope (this delivery):**

| Area | What changes |
|------|--------------|
| `tool_presentation.yaml` | Add `workspace_tab` block to relevant tools (`sandbox_run`, `sandbox_pty_run`, `extract_iocs`) |
| `src/types/project.ts` | Extend `AnalysisResult` with `status`, `taskType`, `stats`, `workspaceTabs` |
| `src/types/analysis.ts` | Add `WorkspaceTabConfig`, `WorkspaceTabInstance` types; new block variants |
| `src/lib/tool-tab-registry.ts` | New: loads tool→tab config; resolves merge decisions |
| `src/components/LiveWorkspace.tsx` | Restructure to 3-layer layout |
| `src/components/workspace/TaskHeader.tsx` | New: title + status badge |
| `src/components/workspace/TaskStatsBar.tsx` | New: execution stats row |
| `src/components/workspace/TaskTabPanel.tsx` | New: dynamic inner tab container |
| `src/components/workspace/tabs/ReportTab.tsx` | New: wraps existing block renderers + skeleton |
| `src/components/workspace/tabs/ShellTab.tsx` | New: terminal-style log viewer for sandbox output |
| `src/hooks/useStreamingAnalysisMulti.ts` | Update to populate new `AnalysisResult` fields as SSE flows in |
| Backend `/tools` endpoint or static JSON | Expose `workspace_tab` config to frontend at startup |

**Out of scope (deferred):**
- `InvestigationGraphTab`, `BinaryPipelineTab` — placeholder stub only
- React Flow dependency — not added in this delivery

---

## Dependencies

- Existing `tool_presentation.yaml` structure (read in Phase 1 — confirmed compatible)
- Existing `AnalysisResult` type in `src/types/project.ts`
- Existing SSE `tool_call` event shape (no changes needed)
- shadcn/ui `Tabs` component (already available)

---

## Success Metrics

1. A task that calls `sandbox_run` produces a visible "Shell" inner tab alongside the "Report" tab
2. Two `sandbox_run` calls with the same `sandbox_id` produce one Shell tab (output appended); calls with different IDs produce separate tabs
3. The "Report" tab shows a pulse animation during task execution and switches to rendered blocks on completion
4. Adding a new workspace tab for a new tool requires **only a YAML change** — no frontend code addition
5. Existing multi-result outer tab bar continues to function without regression

---

## Open Questions (resolved in Phase 1)

| Question | Resolution |
|----------|------------|
| Tab merge strategy for sandbox | `by_arg` on `sandbox_id`: same ID → merge, different ID → new tab, absent → always new tab |
| Who triggers tabs — SSE event or config? | **Config-driven**: `tool_presentation.yaml` `workspace_tab` field; frontend resolves on each `tool_call` SSE event |
| First period tab content | Always "Report"; animated skeleton while `status === 'running'` |
| Outer tab bar | Preserved as-is (per-task tabs) |
| Investigation graph / binary pipeline | Deferred — placeholder tab component stubs only |
