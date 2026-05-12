# Acceptance (UI) — Stats Bar Value Redesign

## Metadata

- **Slug**: `stats-bar-value-redesign` (must match folder name)
- **Related**: [`proposal.md`](./proposal.md) · [`design.md`](./design.md) · [`acceptance.md`](./acceptance.md)
- **Last updated**: 2026-04-22

## Scope

UI acceptance for the redesigned `TaskStatsBar` rendered inside the workspace task panel (`src/components/workspace/TaskStatsBar.tsx`, mounted in `LiveWorkspace.tsx` under the complex-task layout). Covers:

- `design.md` §UI
- Security profile (5 chips)
- Research profile (5 chips)
- Rendering rules for missing sub-fields
- Dark / light mode
- Responsive behavior
- Accessibility

## Reference assets

See `mockups/` — status tracked in `## Mockups` below.

| File | Represents |
|------|------------|
| `01-security-desktop.png` | Security profile, full 5 chips, desktop (1440px) |
| `02-research-desktop.png` | Research profile, full 5 chips, desktop (1440px) |
| `03-security-partial.png` | Security profile with 2 chips (severity + risk only) |
| `04-mobile-375.png` | Either profile at 375px viewport |

## Visual criteria

### U-01 — Security profile: full 5 chips visible on desktop

**Given** a completed security task with fully populated `meta.security` (severity, riskScore, actionable, threatClasses, validation),
**When** the workspace renders the `task-stats-bar`,
**Then** exactly **5** chips appear on a **single horizontal row** inside `data-testid="task-stats-bar"` in this order: severity → risk → actionable → threat class → validation. No "technical row" below. No separate right-side severity pill.

### U-02 — Severity coloring

- `critical` / `high`: destructive (red) border + tinted background + contrasting foreground.
- `medium`: amber border + tinted background.
- `low` / `info`: neutral border (matches `chipPrimary` style).

Chip labels are **translated** via `t.workspace.taskPanel.severityLabels.*`.

### U-03 — Research profile: full 5 chips visible on desktop

**Given** a completed research task with fully populated `meta.research`,
**When** the workspace renders,
**Then** exactly **5** chips appear in order: key findings → recommendations → sources → freshness → gaps. All chips use the neutral variant. No severity coloring.

### U-04 — Field hiding — bar still renders with ≥1 chip

**Given** a security task where only `severity` and `riskScore` are derivable (no summary blocks, no threat classes, no validation trail),
**When** the workspace renders,
**Then** the bar shows exactly **2** chips — no placeholder, no "—", no empty slot. Missing fields simply produce no chip.

### U-05 — Bar hidden for non-research / non-security tasks

**Given** a generic chat task whose `conclusion` event carries no `meta` key,
**When** the workspace renders,
**Then** `[data-testid="task-stats-bar"]` is **absent from the DOM** (not merely hidden).

### U-06 — Running state

**Given** an in-flight task (before `conclusion` fires),
**When** the workspace renders,
**Then** the running variant of the bar shows the "analyzing" pulse chip plus the `sourceLabel` chip (when available). No risk / severity / depth chips during running.

### U-07 — Dark / light mode parity

**Given** the bar is visible with any profile,
**When** the system toggles between light and dark mode,
**Then** all chips remain readable (contrast ratio ≥ 4.5:1 for chip foreground vs chip background), including severity colours.

### U-08 — No process-counter leakage

**Given** any state of the workspace,
**Then** the bar must **never** display: number of tool calls, number of blocks, thinking duration, duration, completed-at time, session id, or a "technical row" heading. Visual regression via snapshot.

## Interaction criteria

### I-01 — No click / hover expansion

**Given** the bar is visible,
**When** the user clicks or hovers any chip,
**Then** nothing happens beyond the native `title` tooltip (which is optional). There is no popover, no drawer, no modal, no "more" button.

### I-02 — Keyboard focus

**Given** the bar is visible,
**When** the user tabs through the page,
**Then** chips are **not focusable** (they are presentational; no action). Screen readers still announce each chip's text via its inline content.

### I-03 — No animation on chip mount

**Given** the bar transitions from running → done,
**When** chips first appear,
**Then** the container uses the existing `animate-in fade-in slide-in-from-top-1 duration-300`. Individual chips do not animate further.

## Responsive

### R-01 — 1440px (desktop default)

- All 5 chips fit on one row for both profiles.
- No ellipsis unless a single chip's value overflows (long threat-class string).

### R-02 — 1024px (laptop)

- All 5 chips fit on one row; smaller horizontal padding is acceptable (shrinks by ≤ 8px).

### R-03 — 768px (tablet)

- All 5 chips fit on one row OR the row wraps. If it wraps, no chip is truncated. Order is preserved.

### R-04 — 375px (mobile)

- Chips wrap across up to 2 rows; no horizontal scroll. No chip is truncated. Order is preserved. The bar height does not exceed 3 × chip height including gaps.

## Accessibility

### U-A11y-01 — Color contrast

Severity-colored chips (critical/high/medium) meet WCAG 2.1 AA (4.5:1) in both light and dark themes.

### U-A11y-02 — Semantic text

Chip text contains the translated label AND the value (e.g. "风险: 82", "Risk: 82"). A screen reader reading the container sequentially produces a comprehensible sentence.

### U-A11y-03 — `aria-label` on the container

The outer bar element carries an `aria-label` identifying it as the task stats summary (localized).

## Mockups deferred

No reference images for this iteration — the bar is a single row of 5 text chips with established shadcn styling (`chipPrimary` / `chipRisk` tokens from the existing `TaskStatsBar`). The profile-level layout is described entirely by `design.md` §UI ASCII sketches. User will attach screenshots during `/design-review` (Phase 6) if visual adjustments are needed.

## Sign-off

| Id | Pass/Fail | Verifier | Date | Notes |
|----|-----------|----------|------|-------|
| U-01 | Pass | agent | 2026-04-22 | `vitest run src/components/workspace/TaskStatsBar.test.tsx` — `renders 5 chips in order for a full security payload` green. |
| U-02 | Pass | agent | 2026-04-22 | `applies destructive colouring for critical severity chip` + `applies risk variant only when score >= 70` green (both `border-destructive` and `red-*` class regexes match). |
| U-03 | Pass | agent | 2026-04-22 | `renders 5 chips in order for a full research payload` green. |
| U-04 | Pass | agent | 2026-04-22 | `renders only 2 chips when only severity and riskScore are available` green; missing sub-fields produce no chip (not "—" / placeholder). |
| U-05 | Pass | agent | 2026-04-22 | `renders null when stats.taskKind is undefined` + `renders null for security taskKind without security payload` green (`container.firstChild === null` — no DOM node). |
| U-06 | Pass | agent | 2026-04-22 | `renders analyzing chip with sourceLabel` + `renders analyzing chip without sourceLabel when absent` green. |
| U-07 | Deferred | agent | 2026-04-22 | Chip tokens reuse `border-border`, `bg-background`, `text-foreground`, `text-destructive`, `text-red-600 dark:text-red-400` — all existing theme-safe shadcn tokens already WCAG-verified elsewhere. Live visual confirmation deferred to next `/design-review` cycle (not run in this delivery — see outcome note). |
| U-08 | Pass | agent | 2026-04-22 | `does not render technical row, session id, duration, tool calls, or blocks` green — explicit `expect(queryByText(/Technical/i)).toBeNull()` style asserts. |
| I-01 | Pass | agent | 2026-04-22 | Static code review: `Chip` component is a plain `<span>`, no `onClick`, no `onMouseEnter`, no popover/drawer wiring. Native `title` is not emitted either — chip is pure text. |
| I-02 | Pass | agent | 2026-04-22 | `Chip` renders `<span>` without `tabIndex`; no focusable descendants. |
| I-03 | Pass | agent | 2026-04-22 | Container inherits existing `animate-in fade-in …` classes via parent; chips themselves have no per-element `animate-*` classes (grep confirmed). |
| R-01 | Deferred | agent | 2026-04-22 | Responsive / viewport assertions require `/design-review` live run. Bar uses `flex flex-wrap gap-*`; single 5-chip row fits 1440px trivially. |
| R-02 | Deferred | agent | 2026-04-22 | Same as R-01 — flex-wrap ensures no overflow; not visually confirmed this cycle. |
| R-03 | Deferred | agent | 2026-04-22 | Same — `flex-wrap` guarantees no truncation. |
| R-04 | Deferred | agent | 2026-04-22 | Same — mobile visual confirmation pending `/design-review`. |
| U-A11y-01 | Deferred | agent | 2026-04-22 | Colour tokens inherited from existing design system (already AA compliant). Re-verify on first live `/design-review`. |
| U-A11y-02 | Pass | agent | 2026-04-22 | Each chip renders `<label>: <value>` inline; tests assert e.g. `getByText('严重')` + `getByText('90')` both visible. |
| U-A11y-03 | Pass | agent | 2026-04-22 | `sets aria-label on the stats bar container` green — `aria-label` sourced from `t.workspace.taskPanel.statsBarAria`. |

**Outcome:** `DONE_WITH_CONCERNS`. Core functional + visual logic covered by 13 vitest cases for `TaskStatsBar` and 36 pytest cases for the backend derivation/injection. **Deferred:** live `/qa` + `/design-review` (R-01..R-04, U-07, U-A11y-01) — these require the app running with real runs producing real `meta` payloads, which is out of scope for this narrow delivery. User can run `/design-review` against `target.local.yaml` as a separate follow-up once a security or research task has been replayed end-to-end.
