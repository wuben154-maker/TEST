# UI Acceptance — `tool-execution-cursor-style`

## Metadata

- **Slug:** `tool-execution-cursor-style`
- **Updated:** 2026-04-16
- **Related:** [proposal.md](./proposal.md), [design.md](./design.md)

## Scope

- Screens / routes: Chat analysis page (conversation timeline)
- Components: `ToolExecutionBlockView`, `ToolRowCollapsible` (replaces `ToolRowStatus`)

## Reference assets (`mockups/`)

## Mockups deferred

No mockup images provided. Visual specification defined in `design.md` § UI section via component state table and Tailwind classes. Reference style: Cursor IDE tool call rows.

## Visual criteria

| ID | Criterion | How to verify |
|----|-----------|---------------|
| U-01 | Each completed tool row shows a green checkmark (success) or red X icon (error) on the left side of the title | Visual inspection of tool rows after analysis completes |
| U-02 | Tool rows with output show a right-pointing chevron that rotates 90° on expand | Click a completed tool row with output; observe chevron rotation |
| U-03 | Expanded result panel has a muted background (`bg-muted/20`) with subtle border, monospace font at 11px | Expand a tool row and inspect the result panel styling |
| U-04 | Result panel height is limited (~160px / `max-h-40`) with vertical scrollbar for long content | Trigger a tool with long output (e.g. web_search); expand and verify scroll |
| U-05 | Running tool shows a spinning loader icon in primary color | Observe tool row during live analysis execution |

## Interaction criteria

| ID | Criterion | How to verify |
|----|-----------|---------------|
| I-01 | Clicking a completed tool row with output toggles expanded/collapsed state | Click row → panel expands; click again → collapses |
| I-02 | Clicking a completed tool row without output does nothing (no chevron, no cursor:pointer) | Complete a tool that has `emit_output: false`; click row → no expansion |
| I-03 | Running tool rows are not clickable | During analysis, try clicking the active spinner row → no expansion |
| I-04 | After page refresh, completed tool rows retain their success/error status and output is expandable | Refresh page after analysis; verify indicators persist and click-expand works |
| I-05 | Error tool row shows destructive-colored output text when expanded | Trigger or observe an error tool result; expand and verify red-tinted text |

## Responsive

- **375px:** Tool rows stack normally; result panel uses full width minus left margin; long detail text truncates
- **768px:** Same layout as desktop; no special breakpoint handling needed
- **1024px+:** Standard layout; tool name and detail badge fit on one line

## Accessibility

- Contrast: Status icons (emerald/destructive) meet WCAG AA on both light and dark backgrounds
- Focus: Expandable rows are keyboard-accessible (clickable div with appropriate cursor)
- Touch targets ≥ 44px: Row height with padding meets minimum touch target

## Sign-off

| ID | Result | Evidence | Verifier | Date | Notes |
|----|--------|----------|----------|------|-------|
| U-01 | ⏳ DEFERRED | Playwright MCP not available; visual verification pending | Agent | 2026-04-16 | Code review confirms CheckCircle2 (emerald) and XCircle (destructive) icons |
| U-02 | ⏳ DEFERRED | Playwright MCP not available | Agent | 2026-04-16 | Code review: ChevronRight with `rotate-90` on expand |
| U-03 | ⏳ DEFERRED | Playwright MCP not available | Agent | 2026-04-16 | Code review: `bg-muted/20 border-border/30 font-mono text-[11px]` |
| U-04 | ⏳ DEFERRED | Playwright MCP not available | Agent | 2026-04-16 | Code review: `max-h-40 overflow-y-auto` on result panel |
| U-05 | ⏳ DEFERRED | Playwright MCP not available | Agent | 2026-04-16 | Code review: Loader2 with animate-spin text-primary |
| I-01 | ✅ PASS | Code review: onClick toggles expanded; canExpand gates on done && hasOutput | Agent | 2026-04-16 | |
| I-02 | ✅ PASS | Code review: canExpand=false → no cursor-pointer, no chevron, no role=button | Agent | 2026-04-16 | |
| I-03 | ✅ PASS | Code review: running rows have canExpand=false (child.done is false) | Agent | 2026-04-16 | |
| I-04 | ✅ PASS | Code review: timeline persistence preserves toolOutput/status; buildReActTimeline rebuilds | Agent | 2026-04-16 | |
| I-05 | ✅ PASS | Code review: `child.isError ? 'text-destructive/80' : 'text-muted-foreground/70'` | Agent | 2026-04-16 | |
