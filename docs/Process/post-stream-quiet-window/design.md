# Post-stream quiet window — design.md (Patch tier)

## Metadata
- slug: `post-stream-quiet-window`
- date: 2026-04-25
- tier: Patch (≤ 3 files, no schema, no API change)
- related-bug: "任务结束后报告出现，过几秒界面会自动刷一下"
- follow-up: 2026-04-25 round 2 — first pass missed `poll()` exit B (direct `updateState` write when `is_analyzing` still true). Symptom persisted; closed by extending the quiet-window guard into `poll()` itself + new `U-04` test.

## Problem

After a local SSE stream finishes (`done` event delivered, reportarea
populated, stats bar rendered), the chat list visibly "refreshes once" 3–10
seconds later. Symptom matches an entire turn re-mount: tab id flicker, scroll
reset, statsbar/title flash.

Existing comment in `useAnalysisProgressRestore.ts:249-256` already documents
the cause: `useAnalysisProgressRestore` polls the backend
`is_analyzing` row every 3 s; the backend write debounce keeps that row
`true` for up to ~20 s after the local stream finishes. When the row finally
flips to `false`, `finishProgressForProject` calls `reloadProjectMessages` →
full chat re-mount.

The current mitigation (`stopProgressRestorePolling(projectId)` in
`onProjectAnalysisComplete`) cancels **the next setInterval tick** but has
**three** escape paths:

1. **In-flight fetch resolving with `is_analyzing=false`** (or terminal
   timeline): walks into `finishProgressForProject` →
   `reloadProjectMessages`, re-mounting the chat list.
2. **Effect re-subscription**: the polling effect's deps include caller
   callbacks (`loadProjects`, `reloadProjectMessages`); a parent re-render
   right after `appendToConversation` re-runs the effect, which reads the
   stale-true `is_analyzing` row and starts a new interval.
3. **In-flight fetch resolving with `is_analyzing=true`** (backend debounce
   not yet drained): `poll()` skips `finishProgressForProject` and runs the
   `updateState(projectId, applyProgressUpdater(...))` write instead,
   *overwriting* the freshly-finalized local state with stale polled state.
   This is exactly the visible "content flashes once" 3–10 s after a
   deep-research / security task settles. Round-1 fix only blocked paths
   (1) and (2), so the user still observed the flash.

## Fix (option A — quiet window)

Introduce a per-project "recently stopped" timestamp inside
`useAnalysisProgressRestore`. While the timestamp is within
`POST_STREAM_QUIET_WINDOW_MS` (30 s, > the worst-case 20 s backend debounce):

1. `finishProgressForProject` is a no-op (no `clearProjectLiveState`, no
   `reloadProjectMessages`, no `loadProjects`).
2. The polling effect's bootstrap step does **not** start a new interval
   for that project.
3. `poll()` checks the window **after the fetch resolves**, before either
   the `is_analyzing=false` branch (calls `finishProgressForProject`) or
   the `is_analyzing=true` branch (calls `updateState(...)` and would
   overwrite the freshly-finalized local state). This closes the third
   escape path identified in round 2.

`cancelRestore` (the user-pressed Stop button path) intentionally still
works, because the quiet window only suppresses *finalize/reload*, not the
fact that polling is stopped. cancelRestore additionally calls
`clearProjectLiveState` directly, which is unaffected.

Rationale for choosing 30 s: the comment at line 251 cites "up to ~20 s"
debounce. 30 s gives a 50% safety margin without meaningfully delaying the
restore path for legitimate later sessions (the user would have to sit on
the same project ≥30 s after a turn settled, then trigger something that
restarted the effect, which is an extreme corner).

## Code touch list

| File | Change |
|---|---|
| `src/hooks/useAnalysisProgressRestore.ts` | Add `recentlyStoppedRef: Map<string, number>` + `POST_STREAM_QUIET_WINDOW_MS` const; gate `finishProgressForProject`, the bootstrap inside the effect, and the post-fetch branch in `poll()` on the window. `stopPolling` records the timestamp. |
| `src/hooks/useAnalysisProgressRestore.test.tsx` | Two new tests: (a) in-flight `getAnalysisProgress` resolving after `stopPolling` does not call `reloadProjectMessages`; (b) effect re-subscription within 30 s does not restart polling. |

No DB / API / backend / UI component changes.

## Testing strategy

### Unit (Vitest, vi.useFakeTimers)

| ID | Scenario | Assertion |
|---|---|---|
| U-01 | stopPolling, then in-flight fetch resolves with `is_analyzing=false` | `reloadProjectMessages` not called; `clearProjectLiveState` not called |
| U-02 | stopPolling, then effect re-subscribes within 30 s | no new setInterval started; no `reloadProjectMessages` |
| U-03 | stopPolling, advance 31 s, effect re-subscribes | polling resumes normally (window expired) |
| U-04 | stopPolling, then in-flight fetch resolves with **stale `is_analyzing=true`** | `updateState` not called for that project after stopPolling — closes the round-2 hidden path |

E2E: not needed for Patch tier (timing-based bug, pure unit verifiable).

## Edge cases

- **Multiple projects**: `recentlyStoppedRef` is a Map keyed by `projectId`;
  stopping project A does not silence project B.
- **User clicks Stop very late**: `cancelRestore` still calls
  `stopPolling` first, which seeds the timestamp; subsequent in-flight
  resolves are correctly suppressed (and `cancelRestore` itself already
  cleared live state synchronously, so user UX is unaffected).
- **Real legitimate restore path** (page refresh while task is *actually*
  still running): no `stopPolling` was ever called for that project, so
  `recentlyStoppedRef` is empty → polling runs as before.

## Implementation order

1. Write red tests U-01 + U-02 + U-03.
2. Implement `recentlyStoppedRef` + 3 guard sites.
3. Run full test file → green.
4. Auto-continue Phase 5 (regression on hooks + Index).
