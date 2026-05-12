# Acceptance (UI) — context-summarization-usage-orchestration

## Metadata

- **Slug**: `context-summarization-usage-orchestration`
- **Last updated**: 2026-05-06
- **Design**: [`design.md`](./design.md)

## Scope

- `ContextUsageBadge`, `ContextUsagePopover` (optional debug row), `AnalysisInputComposer` integration.
- Reducers: `applyEventToContextUsage` / streaming hooks consuming `context_budget`.
- Hydration: `context_usage` v2 with `lastServerBudget` mirror (if implemented).

## Reference assets

| File | Purpose |
|------|---------|
| — | **Mockups deferred** (see `design.md` § Mockups) |

## Visual criteria

| ID | Criterion |
|----|-----------|
| U-01 | Context ring reflects **server `tier`** when `context_budget` present (color matches severity mapping shared with `deriveIndicator` or documented mapping table). |
| U-02 | After summarization (`context_summarized`), main-line metric clears: trigger shows **Layers** idle icon (`data-awaiting-measure=true`) until next main `llm_invoke_end`; popover main row shows `mainAfterCompact`. |
| U-03 | Popover / breakdown layout unchanged at 1440px except optional single line for `fillSource` in advanced section. |

## Interaction criteria

| ID | Criterion |
|----|-----------|
| I-01 | Keyboard focus order: popover trigger remains accessible; `aria-label` describes budget state. |
| I-02 | Toast on `context_summarized` still fires; copy updated if needed for i18n (`en`/`zh`/…). |

## Responsive

- **375 / 768 / 1024**: small-screen ring-only mode still works; no overflow of composer bar when optional debug row hidden.

## Accessibility

- Target **WCAG 2.1 AA** for badge + popover: contrast, focus ring, touch target ≥ 44px where interactive.

## Sign-off

| ID | Pass/Fail | Verifier | Date | Notes |
|----|-----------|----------|------|-------|
| U-01 | | | | |
| U-02 | | | | |
| U-03 | | | | |
| I-01 | | | | |
| I-02 | | | | |
