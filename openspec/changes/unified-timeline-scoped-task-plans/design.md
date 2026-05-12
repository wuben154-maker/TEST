## Context

Today the left panel uses **`ReactLinearTraceView`** (narrative rows + optional `conclusionText` card) and then **`TimelineActivity`** (explore tools, task board, HITL, subagent chunks) as **siblings** in `CommandCenter`. Both read the same `timeline` array but **partition** work into two vertical stacks, so **reading order** can diverge from **`seq`**.  

Task state uses **one** `taskPlan` in `PerProjectStreamingState`. **`handleTaskPlan`** merges by `PlannedTask.id` and appends **`extras`** (tasks absent from the latest incoming plan). **`write_todos`** is synthesized into a `task_plan` with **`id: String(idx)`**. **`handleMultiAnalyzeStreamEvent`** does not route `task_plan` by `ev.scope`, so subagent plans can **collide** with main ids.

## Goals / Non-Goals

**Goals:**

- **Single ordered presentation list** for one analysis turn: every user-visible item has a **sort key** derived from canonical timeline rules (`seq` + defined tie-breakers) so **DOM order matches narrative order**.
- **Scoped task plans**: separate **mutable** task lists for **main** vs **subagent** (minimum), with lifecycle events updating **only** the matching bucket.
- **Preserve** agreed semantics: **`conclusion`** content stays **workspace-first** (not duplicated as a left-stream row); **`task_summary`** may appear as a **terminal summary item** in the left stream (or equivalent).

**Non-Goals:**

- Redesigning **right-hand workspace** blocks or markdown styling for conclusions.
- Changing **LangGraph** graph topology—only **SSE payload contracts** and **client state** unless backend work is explicitly scheduled.
- Full **virtualized** infinite timeline performance work (optional follow-up).

## Decisions

### D1 — Unified item model (frontend)

- **Choice**: Introduce a single builder (e.g. `buildUnifiedTimelineItems`) that outputs a **discriminated union** of item kinds (`reasoning`, `tool_explore`, `task_board_main`, `task_board_sub`, `delegation`, `hitl_param`, `hitl_decision`, `summary_task`, …) each carrying **`sortKey`** and render props.
- **Rationale**: One `map` → one list avoids sibling ordering bugs; matches `timeline-product-view` spec intent.
- **Alternatives**: Keep two components and **interleave** via a parent that only passes slices—higher risk of drift and duplicate filter logic.

### D2 — Sort key

- **Choice**: Primary **`seq`** from `AnalysisTimelineEntry`; tie-breakers for multi-emit same seq: stable rule documented in spec (e.g. type priority, then `id`, then ingest order).
- **Rationale**: Aligns with existing reducer and tests.

### D3 — Streaming reasoning

- **Choice**: Represent in-progress reasoning as **one** synthetic item pinned with sort key **`maxSeenSeq + epsilon`** or attach to **current turn** bucket until a `reasoning` row closes—pick one rule and test it.
- **Rationale**: Avoids jumping above completed rows.

### D4 — Scoped task state shape

- **Choice**: `taskPlanMain: TaskPlan | null` plus `taskPlanSubagent: Record<string, TaskPlan | null>` keyed by **`subagentName`** (fallback key `'_default'` if name missing), **or** nested under `taskPlansByScope: { main, subagent: Map }`—teams pick one; document in types.
- **Rationale**: Clear routing for `handleTaskPlan` / `task_start` / `task_complete` when `scope === 'subagent'`.
- **Alternatives**: Single list with **namespaced ids** only—still requires backend guarantees; can be **phase 2** if server prefixes ids first.

### D5 — `write_todos` ids

- **Choice**: Prefix synthetic ids: e.g. `main:todo:${idx}` or `main:todo:${requestId}:${idx}` to avoid collision with server `task_plan` ids and subagent todos.
- **Rationale**: Client-controlled, minimal backend change for first iteration.

### D6 — Backend alignment (recommended)

- **Choice**: Emit **`scope`** on `task_plan`, `task_start`, `task_complete`, `task_step`, `plan_complete` consistently; subagent streams use **`scope: 'subagent'`** + **`subagentName`** (or registry id).
- **Rationale**: Removes ambiguity when the same graph reuses numeric ids.

## Risks / Trade-offs

- **[Risk] Large refactor of CommandCenter render path** → Mitigation: feature flag or single entry component swap; keep old code path until parity tests pass.
- **[Risk] Persisted conversation replay** expects old shape (`taskPlan` only) → Mitigation: migration when hydrating history turns; default missing scope to `main`.
- **[Risk] Backend not yet emitting scope** → Mitigation: client defaults `main`; subagent plans still wrong until server fixed—document as **dependency**.

## Migration Plan

1. Land **types + reducer** for scoped plans behind defaults (`main` only).
2. Land **unified list** for live streaming; verify against golden `seq` fixtures.
3. Update **persistence** (`ConversationMessage`, `useConversationPersistence`) to store scoped plans or derive from timeline replay.
4. Optional **backend** release with `scope` fields; then enable strict routing.

## Open Questions

- Should **multiple subagent invocations** with the **same** `subagentName` share one task board or split by **invocation id** (correlate with `task` tool_call / stream id)?
- Should **`plan_complete`** replace entire plan for a scope or merge—match current `mergeTaskPlan` semantics per bucket?
