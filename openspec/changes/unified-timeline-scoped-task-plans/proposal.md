## Why

The left analysis panel stacks **two siblings** (`ReactLinearTraceView` then `TimelineActivity`), so **DOM order diverges from SSE `seq` order**: late linear content can appear **above** early task-board / tool chunks, which breaks chronological reading. Separately, **one merged `taskPlan.tasks[]`** ingests **main and subagent `task_plan` events** (and `write_todos`-synthesized plans) without **scope routing**, so **duplicate `id` spaces** (`"0"`, `"1"`, …) cause **wrong row updates** and **inconsistent list length** as merge + `extras` rules apply.

## What Changes

- **Unified timeline stream (frontend)**: One **ordered list** of presentation items keyed by **`seq` (+ tie-breaks)** so **visual order matches event order**, while preserving product rules: **`conclusion` remains workspace-only** (not a row in the left stream); **`task_summary`** remains an acceptable **left-stream terminal summary** row (or equivalent item type). Tool blocks, task boards, HITL, subagent segments, and reasoning text are **interleaved** in that single list—not two vertical panels.
- **Scoped task plans**: **Partition** task state by **owner** (at minimum **`main` vs `subagent`**, optionally keyed by `subagentName` / `planId` per backend contract). **Lifecycle events** (`task_start`, `task_complete`, `task_step`, …) **update only** the bucket matching their **scope** (and id). **No** merging subagent tasks into the main board unless explicitly product-desired.
- **`write_todos` / synthetic `task_plan`**: Stop using **raw array index** as the **sole** stable id when it can collide across scopes or with backend ids; align with **namespaced or server-provided ids** (**BREAKING** for clients that assumed `"0"`… semantics globally).
- **Docs / SSE catalog**: Document **required** `scope` (or equivalent) on **`task_plan`** and lifecycle events when multiple agents emit plans; optional **plan revision** semantics to reduce **`extras` orphan** growth.

## Capabilities

### New Capabilities

- `analysis-timeline-unified-stream`: Single-column, **seq-ordered** presentation model for the analysis UI; which event types become which item kinds; **exclusion** of `conclusion` from the left stream; placement of `task_summary` relative to other items.
- `task-plan-scope`: **Owner/scoped** task plan state, merge rules **per scope**, routing of SSE events to buckets, and **id uniqueness** expectations across main vs subagent (and `write_todos`).

### Modified Capabilities

- `reasoning-timeline-ui`: Delta—replace **two-pane** (linear trace + companion timeline) as the **normative** layout with **one unified ordered stream**; clarify how subagent blocks appear **in-order** without a second stacked region.

## Impact

- **Frontend**: `CommandCenter`, `ReactLinearTraceView`, `TimelineActivity`, `buildReactLinearRows`, `buildTimelineActivityChunks`, `useStreamingAnalysisMulti`, `multiAnalyzeStreamEvents`, `PerProjectStreamingState` / persistence of assistant turns.
- **Backend (python-agent-service)**: Recommended—emit **`scope`** consistently on `task_plan` and task lifecycle events; optionally **namespaced `task.id`** or stable ids for `write_todos` mapping.
- **Docs**: `docs/Process/SSE_EVENT_CATALOG.md` (and related ReAct notes) updated for scope + id rules.
