## 1. Protocol documentation and envelope

- [x] 1.1 Document canonical envelope fields (`schemaVersion`, `seq`, `scope`, optional `taskId` / `parentTaskId` / `subagentName`) in `docs/` or `python-agent-service/README.md` (English for developer-facing sections).
- [x] 1.2 Document in `src/types/analysis.ts` (or adjacent) that **only** `schemaVersion: 1` timeline + SSE envelope is supported; no legacy client compatibility layer.

## 2. Backend: sequencing and scope

- [x] 2.1 Implement per-connection `seq` counter in `adapt_astream_to_sse` (and any merged subagent yields) so every emitted event includes monotonic `seq`.
- [x] 2.2 Add `schemaVersion: 1` and `scope: "main"` to all main-graph user-visible events; set `scope: "subagent"` in `_tag_merged_subagent_sse` (and ensure research bridge events are tagged consistently).
- [x] 2.3 Add pytest cases asserting `seq` ordering across interleaved main graph chunks and queued subagent events.

## 3. Backend: reasoning gate and deduplication

- [x] 3.1 Redesign `saw_first_tool_call` / messages-stream gating so post-tool reasoning deltas can emit per `agent-stream-protocol` without duplicating final `conclusion` text (implement dedup helper + tests).
- [x] 3.2 Add regression tests for: (a) multiple tool rounds, (b) final answer only in `conclusion`, (c) no duplicate full answer in `reasoning`. *(Partially covered by existing adapter tests; add explicit multi-round cases if needed.)*

## 4. Backend: subagent normalization

- [x] 4.1 Centralize mapping of subagent/research events (`skill_reasoning`, `skill_start`, `skill_complete`, etc.) to canonical `type` values aligned with main agent; drop or downgrade non-user-visible payloads to debug channel.
- [x] 4.2 Review `adapt_subagent_astream_to_skill_events` usage and wire or extend so task-tool subruns match the same canonical kinds where applicable.
- [x] 4.3 Add tests for tagged subagent events: correct `scope`, stable ids, and mapped `type`.

## 5. Frontend: timeline reducer

- [x] 5.1 Introduce `TimelineItem` (or equivalent) type and a single reducer in `useStreamingAnalysisMulti.ts` that appends/updates items from SSE without collapsing `skill_*` to undifferentiated `step` unless intentionally mapped.
- [x] 5.2 Wire `timeline` into `CommandCenter` / `ReasoningPanel` / `TimelineActivity`; removed parallel `thinkingSteps` / `streamEvents` live state.
- [x] 5.3 Add unit tests for the reducer (Vitest): interleaved reasoning + tool_call + tool_result + subagent-scoped events preserve order and kinds.

## 6. Frontend: UI rendering

- [x] 6.1 Render timeline in `seq` order (`sortTimelineBySeq`) with nested grouping for `scope === "subagent"` (delegation line uses `task` tool `subagent_type` / `description`).
- [x] 6.2 Remove `isThinkingPhase && !taskPlan` gating; Thinking shows for the full `isAnalyzing` window.
- [x] 6.3 Dev path unchanged: `internal` SSE rows are not appended to `timeline`; `DevModePanel` / `sseEventLogs` remain for raw inspection.
- [x] 6.4 Thinking animation + duration decoupled from `task_plan`; reasoning text from `aggregateReasoningFromTimeline` only; tools/sub-agent via `TimelineActivity` after Thinking.

## 7. Persistence and cleanup

- [x] 7.1 Add **optional** SQL migration: new `timeline` JSONB on `messages` (and align `project_analysis_progress` or equivalent) plus writer/reader paths in Python `messages` API + `message_persistence` + frontend `useProjects` / `buildConversationMessages`; **only** persist/load canonical timeline shape. *(Messages + API + persistence + frontend done; progress table intentionally unchanged.)*
- [x] 7.2 Document in `README` or `docs/`: **development** may `TRUNCATE` (or delete rows from) `messages` and `project_analysis_progress` instead of migrating; list tables team cares about.
- [x] 7.3 Remove `thinking_steps` / `__extended` client round-trip; drop `thinkingSteps` / `streamEvents` from `PerProjectStreamingState` and message mapping; `useStreamingAnalysis.ts` left unused legacy.
- [x] 7.4 Update `project_context.md` and `docs/Process/FRONTEND_AGENT_SYNC_ANALYSIS.md` (or successor) for unified protocol, timeline persistence, and dev truncate policy.
