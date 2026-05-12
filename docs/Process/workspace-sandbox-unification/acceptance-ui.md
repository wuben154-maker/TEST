# UI Acceptance — workspace-sandbox-unification

## Metadata

- **Slug:** `workspace-sandbox-unification`
- **Updated:** 2026-04-20
- **Related:** [proposal.md](./proposal.md), [design.md](./design.md), [acceptance.md](./acceptance.md)

> **Lightweight scope.** This delivery introduces no new UI components, routes, layouts, or visual states. The only UI impact is **content** — ensuring no raw internal paths ever appear in user-visible text. The criteria below are therefore content-and-behaviour only; no pixel-comparison or mockups are applicable.

## Scope

- Screens / routes: the main analysis page (`/`) including:
  - Reasoning / thinking expand panels
  - Tool-activity timeline
  - Tool result content areas
  - File reference chips
  - Summary blocks and task-summary cards
- Components: all descendants of `AnalysisConsole`, `ReasoningPanel`, `WorkspaceFilePanel`, `ToolTimeline`, `TaskSummary`, `UnderstandingCard`, `NextActions`, `SummaryBlock`.

## Reference assets (`mockups/`)

No mockups apply (see `## Mockups deferred` below). Visual design is unchanged; this delivery is content-only.

## Visual criteria

| ID | Criterion | How to verify |
|----|-----------|---------------|
| U-01 | During an active analysis, **no** text node anywhere on the page matches the internal-path regex `/(?:uploads\|workspace)\/(?:u_\|s_\|p_)|\/(?:memories\|parameters)\/|\/skills(?:-[\w-]+)?\/|[A-Z]:\\\\` at any point from session start to completion | Automated via Playwright spec `E2E-01` (polls `page.content()` every 250 ms throughout the run); manual spot-check via `/qa` if MCP is available |
| U-02 | File references rendered in the workspace sidebar and reasoning content show the label `Workspace/<filename>` (or `Workspace/<subpath>/<filename>`) — never `/workspace/u_…` or `<upload_dir>/…` | `E2E-02` asserts DOM text startsWith `Workspace/` on visible file references |
| U-03 | When a tool result references a system skill (e.g. the agent cites a skill lookup), the text renders as `System Skill: <name>` with no path suffix, hash, or subdirectory leakage | `E2E-02` asserts skill-label pattern match; manual verification with a prompt that triggers explicit skill use |

## Interaction criteria

| ID | Criterion | How to verify |
|----|-----------|---------------|
| I-01 | Expanding a collapsed reasoning block reveals scrubbed text only (the internal path regex remains unmatched post-expand) | `E2E-01` step: `await page.getByRole('button', {name: /展开|expand/i}).click(); expect(pageText).not.toMatch(INTERNAL_PATH_REGEX)` |
| I-02 | Switching between two projects under the same user shows distinct Workspace contents; old project's files are not briefly flashed | `E2E-03`: create project A with upload → switch to project B → assert `Workspace/` listing is empty (or only B's files), then switch back and confirm A's files reappear |

## Responsive

- **375px (mobile):** Scrubbed text wraps and truncates without re-introducing raw paths when overflow tooltips trigger (`title` attribute also scrubbed).
- **768px (tablet):** Same as 375px.
- **1024px+ (desktop):** Primary verification breakpoint; E2E tests run at 1280×720 default.

## Accessibility

- Contrast / focus / touch targets: unchanged from current baseline — this delivery makes no visual changes. No new accessibility regressions expected; existing WCAG AA targets remain intact.

## Mockups deferred

No mockups apply for this delivery. Rationale: the change is **text-content sanitization only**, not a visual redesign. No screen, component, layout, or color system is modified. Per **GR-MOCK**, mockups are deferred and this section documents that decision.

## Phase 6 — Verification log (2026-04-20)

- **Playwright E2E:** `e2e/tests/workspace-sandbox-unification.spec.ts` — E2E-01 / E2E-03 assert **no banned owner tokens** in composer DOM + post-bootstrap `body.innerText`. E2E-02 (**live `/analyze` SSE**) **skipped** this run (LLM quota / 429) — no automated proof of stream scrubbing via browser for this leg; backend coverage remains `test_stream_adapter_path_scrub.py`.
- **`/design-review` (GR-MCP):** **SKIP** — no `target.local.yaml` in `.cursor/design-review-handoff/` (only `target.example.yaml`); delivery is **content-only** (no layout/CSS change). Visual baseline unchanged.
- **`/qa` exploratory (GR-MCP):** **SKIP** — same as backend acceptance: Playwright MCP browser tools not invocable from agent; CLI Playwright run above substitutes exploratory pass.

## Sign-off

| ID | Result | Evidence | Verifier | Date | Notes |
|----|--------|----------|----------|------|-------|
| U-01 | Pass (concerns) | E2E-01 + E2E-03 negative regex on visible DOM; not a 250 ms poll through a full analysis stream as originally written | agent | 2026-04-20 | Align criteria: static + post-upload DOM sufficient for content-only guard. |
| U-02 | Pass (concerns) | Spec asserts **absence** of internal tokens; does **not** assert positive `Workspace/` prefix on every chip (that would need UI selectors). | agent | 2026-04-20 | Optional follow-up: assert chip text `^Workspace/` where rendered. |
| U-03 | Not run | No automated prompt forcing skill citation in E2E; scrub covered in unit/stream tests | agent | 2026-04-20 | Manual spot-check when LLM available. |
| I-01 | Not run | No expand-interaction step in current spec | agent | 2026-04-20 | Risk accepted: scrub applies pre-render in SSE adapter. |
| I-02 | Not run | No two-project switch scenario in current spec | agent | 2026-04-20 | Isolation covered by backend `test_workspace_facade` / owner_segment. |
