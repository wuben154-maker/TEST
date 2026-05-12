# Stats bar — survive page refresh (Patch tier)

## Metadata

- **Slug**: `stats-bar-refresh-survival`
- **Tier**: Patch (≤3 implementation files)
- **Date**: 2026-04-25
- **Status**: implemented (Phase 5 green)
- **Trigger**: user report "统计 stat 这块内容刷新前还在，刷新后就消失了"

## Problem

After the *stats-bar-value-redesign* delivery, stats persistence is end-to-end
working: `messages.stats` JSONB column carries the backend-derived
`TaskStatsMeta` (`{ taskKind, security|research }`) and the live API path
returns it correctly as a Python `dict`. Verified against the local Postgres
instance + `/messages/project/<id>` endpoint:

```
type=assistant stats_type=dict value={
  'research': {'gaps': 3, 'sources': 79, 'freshness': '<=90d',
               'keyFindings': 12, 'recommendations': 16},
  'taskKind': 'research'
}
```

So the **data round-trip is fine**. What broke is the *frontend chrome
inference* on reload: `LiveWorkspace`'s task-panel chrome (header + stats bar +
inner tabs) only renders when `AnalysisResult.useWorkspaceTaskPanel === true`,
which is computed by `inferUseWorkspaceTaskPanelFromMessage` in
`src/lib/analysisWorkspaceChrome.ts`.

That function was checking `toolCallCount`, `sandboxRunCount`, `workspaceTabs`,
and `taskPlan` — but the new persistence shape stores **only** the
`TaskStatsMeta` payload on `messages.stats`. None of the lighter signals
round-trip on reload, so for a security/research turn whose `taskPlan` and
`workspaceTabs` weren't denormalized, the inference returned `false`, the
panel collapsed, and the stats bar disappeared with it.

## Fix (one-line semantic change)

Treat `taskKind` as the single strongest "this was an agentic security/research
turn" signal: when present, keep chrome alive regardless of the lighter
signals. Backend-confirmed taskKind is more reliable than frontend-derived
`toolCallCount`.

### Touch list

| File | Change |
|------|--------|
| `src/lib/analysisWorkspaceChrome.ts` | Extend `WorkspaceChromeSnapshot` with optional `taskKind`; short-circuit `inferUseWorkspaceTaskPanelFromSnapshot` when set; pass `msg.stats?.taskKind` from `inferUseWorkspaceTaskPanelFromMessage`. |
| `src/lib/analysisWorkspaceChrome.test.ts` | T-01 (snapshot-level) and T-02 (message-level, security + research refresh shape) regression tests. |

No backend, persistence, schema, or live-streaming code changes. The streaming
path was already fine (`liveIsComplex` reads `liveResult.hasTaskPlan` /
`toolCallCount` from in-flight signals); only the post-refresh inference was
broken.

## Testing

`npx vitest run`: 398/398 passed (53 test files), including the new T-01/T-02
regression cases on the touched module.

## Rationale

Why not also persist `toolCallCount` / `sandboxRunCount` to the `stats`
column? Two reasons:
1. Single source of truth — the redesigned stats bar deliberately stopped
   surfacing those counters. Keeping them server-only avoids drift.
2. `taskKind` is *strictly stronger*: the backend already classifies the turn
   (`classify_task_kind`) before emitting `conclusion.meta`, so anywhere we'd
   gate on "did tools run" we can gate on "is this a recognized agentic
   profile" instead, with higher precision and zero new persistence surface.
