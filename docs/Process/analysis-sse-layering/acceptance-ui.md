# UI Acceptance — `analysis-sse-layering`

## Metadata

- **Slug:** `analysis-sse-layering`
- **Updated:** 2026-03-28 (Slice B UI criterion U-04 optional)
- **Related:** [proposal.md](./proposal.md), [design.md](./design.md)

## Criteria ownership (delivery-pipeline)

- **Source of truth:** Product owner / you — criteria below are **structured defaults** for an **internal refactor** (no intentional visual redesign). **Edit** in IDE if your bar differs.
- **Agent role:** Format only (`U-` / `I-` ids). Major changes should match conversation.

## Scope

- **Screens / routes:** Analysis / Command Center flows that consume **SSE** from `POST /analyze` and `POST /analyze/resume` (single- and multi-project).
- **Components:** Indirect — any UI fed by `useStreamingAnalysis`, `useStreamingAnalysisMulti`, timeline / task board / HITL blocks.
- **Out of scope:** New layout, new colors, or new components unless added in a different delivery.

## Reference assets (`mockups/`)

| File (repo-relative) | Description |
| --- | --- |
| *None committed at Phase 2* | See **Mockups deferred** below |

## Mockups deferred

- **Reason:** Delivery is **protocol layering / code structure** (Slice A), not a visual redesign.
- **Resolution:** Either (1) add `*.png|jpg|jpeg|webp|pdf` under [mockups/](./mockups/) and update this table, or (2) **confirm skip** with owner + date in this section.
- **Phase 6:** Rely on **`/qa`** + criteria below; `/design-review` image diff **N/A** until mockups exist or skip is confirmed here.

## Visual criteria

| ID | Criterion | How to verify |
| --- | --- | --- |
| U-01 | **No visible regression:** During a normal analyze run, timeline / reasoning / tool rows appear as before refactor (same rough density and ordering for the same backend). | Before/after screen recording or `/qa` on same prompt |
| U-02 | **Task list:** When backend emits `write_todos`, task panel still updates (titles/statuses visible). | Same as U-01 + task-heavy scenario |
| U-03 | **Conclusion / summary:** Final answer and digest regions behave as before (no duplicate or missing blocks vs pre-refactor). | Spot-check known scenarios |
| U-04 | **(Slice B)** **Linear trace / task board** follow [SSE_EVENT_CATALOG.md](../../SSE_EVENT_CATALOG.md) §6 / §10 using **`toolPresentation` on SSE** (e.g. `task` 不占普通工具行、`state` 隐藏)，与后端注册表一致；无「仅改前端硬编码 toolName」导致的与后端不一致。 | Scenarios covering `write_todos`, a known `action` tool, and an unregistered tool (DEFAULT visible path) |

## Interaction criteria

| ID | Criterion | How to verify |
| --- | --- | --- |
| I-01 | **Abort:** User can cancel in-flight analysis; UI returns to idle without stuck “streaming” state. | Manual + `/qa` if automated |
| I-02 | **HITL resume:** If applicable, resume path still completes after user choice / parameter submit. | Manual or existing E2E |

## Responsive

- **375 / 768 / 1024:** No new breakage vs baseline (same components; layout unchanged for Slice A).

## Accessibility

- No **new** a11y regressions vs baseline (focus order, labels on existing controls).

## Sign-off

| ID | Result | Verifier | Date | Notes |
| --- | --- | --- | --- | --- |
| U-01 | | | | |
| U-02 | | | | |
| U-03 | | | | |
| U-04 | | | | |
| I-01 | | | | |
| I-02 | | | | |
