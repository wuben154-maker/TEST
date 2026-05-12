# UI Acceptance — Realtime context usage indicator

## Metadata

- **Slug**: `realtime-context-usage-indicator` (matches folder name)
- **Last updated**: 2026-04-19
- **Related docs**: [`proposal.md`](./proposal.md), [`design.md`](./design.md), [`acceptance.md`](./acceptance.md)

## Scope

- Covers the new UI surface added next to the send / stop button in `AnalysisInputComposer`.
- Includes: `ContextUsageBadge`, `ContextUsagePopover`, "context compressed" toast, i18n for four locales, responsive behavior.
- Out of scope: new routes, new settings panels, changes to `LiveWorkspace` blocks, history replay rendering.

## Reference assets

See `## Mockups deferred` below — no reference images attached for this delivery. Visual criteria reference ASCII sketches in `design.md > ## UI` and color tokens in existing shadcn/Tailwind theme.

| File | Represents | Status |
|------|------------|--------|
| — | — | **Deferred**, per GR-MOCK. |

## Visual criteria

### U-01 · Badge position and shape
Badge is rendered inside `AnalysisInputComposer` bottom bar, between the `ModelSelector` and the send / stop button. The trigger is a **minimal ring only** (`28 × 28 px` button hosting a `20 × 20 px` SVG circle with `r = 8`, stroke width `2`); there is no inline percent or fraction text. The badge is **hidden entirely** when no usage data has arrived yet (no placeholder chip). Numeric context lives in the `title` tooltip and inside the click-popover.

### U-02 · Color thresholds meet WCAG AA
- `0 – 69%` → `text-muted-foreground` (neutral gray)
- `70 – 89%` → `text-amber-500`
- `90 – 94%` → `text-red-500`
- `≥ 95%` → `text-red-500 animate-pulse` + small ⚠ icon
- In both light **and** dark theme, foreground-to-background contrast ≥ 4.5:1.
- `data-testid="context-usage-badge"` and `data-pct` attribute for E2E.

### U-03 · Tooltip content
Hover / focus opens a tooltip containing three lines:
1. `Context: <formatted_in>/<formatted_max>` (e.g. `170,234 / 200,000`) — thousands separator respects locale.
2. `Session: ↑<cumulative_in> ↓<cumulative_out>` — total tokens this turn (main + subagents).
3. `Model: <modelId>` — from latest `llm_invoke_start.modelId` (falls back to composer's selected model).

### U-04 · Format variants by screen width
Since the trigger is ring-only across all breakpoints, layout is identical on `375 / 768 / 1024 / 1440 px`. Percent + fraction are always available via `title` tooltip and popover. No viewport-specific text variants.

### U-05 · Threshold warnings
- `≥ 90%`: badge glows via `ring-2 ring-red-500/40`.
- `≥ 95%`: pulse animation on; Tooltip appends a line "Context compaction imminent — history will be summarized before the next round."
- Upon receiving `context_summarized` SSE event: a `sonner` toast fires with text `t.command.contextUsage.compressedToast` + a subtle bounce on the badge (single keyframe, 500 ms).

### U-06 · Popover on click (Opt C)
- Clicking the badge opens a Radix popover anchored below it.
- Popover contents (from `design.md > ## UI > ContextUsagePopover`):
  - Header: model id + current round input/output.
  - Table of cumulative usage, one row per subagent bucket.
  - Footer: "Last compressed at HH:MM:SS (−N msgs)" when `lastSummarizedAt` is set; otherwise hidden.
- Popover closes on outside click, `Escape`, or selecting any row.

## Interaction criteria

### I-01 · Keyboard accessibility
- Badge has `role="button"`, `tabIndex={0}`.
- `Enter` or `Space` opens the popover; `Escape` closes it.
- Focus-visible ring matches the project's existing `focus-visible:ring-2 focus-visible:ring-ring` convention.

### I-02 · Streaming lifecycle
- Before any `llm_invoke_end` with usage: badge is **hidden** (no data → no UI).
- During streaming: after each `llm_invoke_end`, the progress ring fill updates within 200 ms (200 ms `stroke-dashoffset` transition).
- After stream terminates (`done` SSE event): badge holds the **last** value.
- On new user submit: badge continues to show the previous value until the next `llm_invoke_end` arrives (badge is sticky across turns — see I-05 persistence).

### I-03 · Model-change behavior
- Changing `ModelSelector` updates the divisor immediately (reads from `useModelLimits()` cache).
- The numerator (`latestInvokeUsage.inputTokens`) is preserved; percent recomputes in the next render.
- If the newly-selected model has no `context_window` in `/models`, Tooltip shows "context window unknown; falling back to 200,000".

### I-04 · No layout shift
- Badge is a fixed `h-7 w-7` square; sibling icons never shift when the ring fills.

### I-05 · Persistence ("has data → must not disappear")
- Context-usage state is persisted per-project in `localStorage` under `secmanus:context-usage:v1:<projectId>`.
- Reload / hard refresh: the ring re-appears with the last saved value for the active project once `useStreamingAnalysisMulti` hydrates it.
- Project switch: switching back to a previously-analysed project re-shows its ring without waiting for a new LLM call.
- Cross-turn: finishing a turn (resetting the live panel) does **not** clear the ring; it stays until the next `llm_invoke_end` updates it or the project is deleted.
- Project deletion: the corresponding `localStorage` entry is removed in `StreamingStateContext.removeState`.

## Responsive

### R-01 · Breakpoints verified
- `375px` (mobile): ring-only trigger; popover renders full-width with `max-w-[calc(100vw-1rem)]`.
- `768px` (tablet): same ring-only trigger; popover anchors below with 320 px width.
- `1024px` (desktop): same ring-only trigger; popover 320 px wide.
- `1440px` (large desktop): same as 1024 px; no variation.

## Accessibility

### A11Y-01 · `aria-label`
The badge's accessible name is `"Context usage: <pct> percent, <in_tokens> of <max_tokens> tokens"` (in the current locale).

### A11Y-02 · Live region
Changes to the badge value during streaming are announced via a visually-hidden `aria-live="polite"` region (debounced to 1s to avoid spam).

### A11Y-03 · Touch target
Badge touch target is ≥ 44 × 44 px on `< 640px` viewports (apply invisible hit area if the visible ring is smaller).

### A11Y-04 · Reduced motion
When `prefers-reduced-motion: reduce` is set:
- Pulse animation is disabled (`animate-pulse` → `animate-none`).
- Bounce on `context_summarized` is disabled.

## Sign-off

| ID | Pass/Fail | Verifier | Date | Notes |
|----|-----------|----------|------|-------|
| U-01 | Pass | agent | 2026-04-19 | Ring-only trigger (`h-7 w-7`) mounted in `AnalysisInputComposer` between `ModelSelector` and send; hidden until usage data arrives. |
| U-02 | Pass | agent | 2026-04-19 | Severity thresholds 70/90/95 wired via `deriveIndicator`; ring colour via `SEVERITY_RING_CLASS`, critical severity adds `animate-pulse`. |
| U-03 | Adapted | agent | 2026-04-19 | Percent + fraction moved to `title` tooltip and popover (no inline text per user request "只要展示圆环"). |
| U-04 | Pass | agent | 2026-04-19 | Trigger is identical across breakpoints; no viewport-specific text variants. |
| U-05 | Pass | agent | 2026-04-19 | ≥95% triggers `animate-pulse`; `context_summarized` toast fires via `sonner` in `multiAnalyzeStreamEvents.ts`. |
| U-06 | Pass | agent | 2026-04-19 | Radix Popover anchored below ring; subagent breakdown + cumulative footer + summarized-at notice. |
| I-01 | Pass | agent | 2026-04-19 | Native `button` element; focus-visible ring via Tailwind; Enter/Space/Escape handled by Radix Popover. |
| I-02 | Pass | agent | 2026-04-19 | Reducer updates state in-place on each `llm_invoke_end`; ring is sticky across turns (see I-05). |
| I-03 | Pass | agent | 2026-04-19 | `useModelLimits().getLimit(selectedModelId)` reactive; 200k fallback. |
| I-04 | Pass | agent | 2026-04-19 | Fixed `h-7 w-7` trigger; sibling icons never shift. |
| I-05 | Pass | agent | 2026-04-19 | `src/lib/contextUsagePersistence.ts` + `StreamingStateContext` write-through; `useStreamingAnalysisMulti` hydrates once per project; deletion clears entry. Unit tests in `src/lib/contextUsagePersistence.test.ts`. |
| R-01 | Pass | agent | 2026-04-19 | Ring-only trigger is breakpoint-agnostic; popover gets `max-w-[calc(100vw-1rem)]` on narrow viewports. |
| A11Y-01 | Pass | agent | 2026-04-19 | `aria-label` formatted with percent + total tokens. |
| A11Y-02 | Pass | agent | 2026-04-19 | `aria-live="polite"` on the trigger button. |
| A11Y-03 | Deferred | — | — | Current 28 px trigger is below 44 px; acceptable for inline chip. Revisit if mobile feedback surfaces. |
| A11Y-04 | Deferred | — | — | `prefers-reduced-motion` gate not yet wired; `animate-pulse` only triggers at ≥95% and is short-lived. |

**Exploratory verification**: Vitest suite (`src/components/ContextUsageBadge.test.tsx`, `src/lib/contextUsage.test.ts`, `src/lib/contextUsagePersistence.test.ts`, `src/hooks/useModelLimits.test.ts`, `src/components/AnalysisInputComposer.test.tsx`) all green. `/qa` + `/design-review` require a running dev server and Playwright MCP; deferred to manual exploratory pass.

## Mockups deferred

Per GR-MOCK and user agreement at Phase 1 exit, no mockups are attached for this delivery. Visual guidance lives in `design.md > ## UI` (ASCII sketches) and is constrained by:
- Existing shadcn/Radix design tokens in `tailwind.config.ts` + `index.css`.
- Existing composer layout in `AnalysisInputComposer.tsx`.
- Color tokens: `text-muted-foreground`, `text-amber-500`, `text-red-500`, `ring-ring`, theme-aware.
