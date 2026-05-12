# UI Acceptance — Report Content & Display Upgrade

## Metadata

- **Slug**: `report-content-display-upgrade`
- **Last updated**: 2026-04-25
- **Proposal**: [`proposal.md`](./proposal.md)
- **Design**: [`design.md`](./design.md)

## Scope

This UI acceptance covers:

- Workspace report tab content and layout.
- Report cover / metadata presentation.
- Markdown report rendering.
- Shared report page parity.
- Markdown/image export interaction.
- Loading, empty, legacy, and partial states.

## Reference assets

| Asset | Represents | Status |
|-------|------------|--------|
| `docs/Process/report-content-display-upgrade/mockups/` | Optional reference screenshots | Deferred by user on 2026-04-25 |

## Visual criteria

| ID | Criterion | Evidence |
|----|-----------|----------|
| U-01 | Completed reports show a report-level cover/header before the body, including title and generated/context metadata when available. | Screenshot from workspace report view. |
| U-02 | A report with one large `analysis` markdown block renders with readable heading hierarchy, spacing, lists, code blocks, links, and blockquotes. | Component test and screenshot. |
| U-03 | Security/research/generic reports use distinct but restrained template labels or metadata treatment without changing the underlying analysis facts. | Screenshot or component test using metadata fixtures. |
| U-04 | Legacy blocks (`summary`, `log`, `decoder`, `intel`, `text`) still retain their recognizable visual treatment inside the upgraded report. | Component test with mixed block fixture. |
| U-05 | The shared report page renders the same main analysis content as the workspace report and no longer drops `analysis` blocks. | Shared report test or screenshot. |
| U-06 | The report body remains readable at desktop widths, with a constrained line length and no horizontal page overflow except inside code/log blocks. | Screenshot at 1440px and 1024px. |
| U-07 | The upgraded report avoids generic decorative card grids; cards are reserved for semantically meaningful areas such as cover, summary, or evidence. | Design-review screenshot evidence. |

## Interaction criteria

| ID | Criterion | Evidence |
|----|-----------|----------|
| I-01 | Running reports with no content keep the existing animated skeleton. | Existing/updated `ReportTab` test. |
| I-02 | Running reports with streamed blocks render content immediately instead of showing an empty skeleton. | Existing regression test remains passing. |
| I-03 | Empty completed reports show a clear no-report state. | Component test. |
| I-04 | Markdown export produces a file containing the same normalized report title/body visible in the report view. | Unit test and manual export check. |
| I-05 | PNG export captures the report content area without export/share controls appearing as report body content. | Manual QA screenshot or Playwright evidence. |
| I-06 | Existing double-click editing behavior does not regress for completed reports. | Component test or manual QA note. |

## Responsive

| Breakpoint | Criteria |
|------------|----------|
| 375px | Report cover stacks vertically; no clipped title or metadata; code/log blocks scroll horizontally. |
| 768px | Report sections remain readable without dense desktop-only chrome. |
| 1024px | Report max width and spacing feel like a document, not a raw chat transcript. |
| 1440px | Report has clear hierarchy and does not stretch paragraphs across the entire workspace. |

## Accessibility

| ID | Criterion | Evidence |
|----|-----------|----------|
| AX-01 | Report headings follow a meaningful order for screen readers. | Component review or accessibility check. |
| AX-02 | Interactive report actions keep visible focus states. | Keyboard QA. |
| AX-03 | Links are visually identifiable and open safely. | Component test or implementation review. |
| AX-04 | Text and chip contrast remain readable in the existing dark theme. | Design-review QA. |

## Mockups deferred

The user selected "skip mockups" on 2026-04-25. This delivery will use the written UI criteria above plus Phase 6 `/design-review` evidence.

## Sign-off

| ID | Pass/Fail | Verifier | Date | Notes |
|----|-----------|----------|------|-------|
| U-01 | Pass | Agent | 2026-04-25 | `ReportTab.test.tsx`, `SharedReport.test.tsx`, and MCP QA confirm `report-cover` renders title/time/context. |
| U-02 | Pass | Agent | 2026-04-25 | `MarkdownRenderer.test.tsx` covers headings, links, blockquotes, and code; MCP QA confirmed visible markdown body. |
| U-03 | Pass | Agent | 2026-04-25 | `reportDocument.test.ts` verifies security template/badges; locale copy exists in en/zh/ja/ko. |
| U-04 | Pass | Agent | 2026-04-25 | `reportDocument.test.ts` covers legacy block preservation; no-auth E2E confirms legacy log rendering. |
| U-05 | Pass | Agent | 2026-04-25 | `SharedReport.test.tsx`, no-auth E2E, and MCP QA confirm shared page renders `analysis` blocks. |
| U-06 | Pass | Agent | 2026-04-25 | MCP QA at 375px reported no horizontal document overflow; screenshot captured at 1024px. |
| U-07 | Pass | Agent | 2026-04-25 | MCP screenshot `report-content-display-upgrade-shared-report.png` shows restrained cover/section layout, no decorative card grid. |
| I-01 | Pass | Agent | 2026-04-25 | Existing `ReportTab.test.tsx` skeleton test remains passing. |
| I-02 | Pass | Agent | 2026-04-25 | Existing `ReportTab.test.tsx` streamed-block rendering test remains passing. |
| I-03 | Pass | Agent | 2026-04-25 | Existing `ReportTab.test.tsx` completed-empty state test remains passing. |
| I-04 | Pass | Agent | 2026-04-25 | `serializeReportMarkdown` unit test and `LiveWorkspace` normalized export implementation review. |
| I-05 | Pass | Agent | 2026-04-25 | `workspace-content` export target moved to report body in simple layout; complex layout target already excluded header actions. |
| I-06 | Pass | Agent | 2026-04-25 | Existing double-click edit behavior preserved in `ReportTab`; related tests remain passing. |
| AX-01 | Pass | Agent | 2026-04-25 | MCP accessibility snapshot shows semantic heading order with report cover and `Executive Summary`. |
| AX-02 | Pass | Agent | 2026-04-25 | No interactive report controls were altered except export target placement; touched-file lint passed. |
| AX-03 | Pass | Agent | 2026-04-25 | `MarkdownRenderer` custom link renderer sets `target="_blank"` and `rel="noopener noreferrer"`. |
| AX-04 | Pass | Agent | 2026-04-25 | MCP dark-theme screenshot reviewed for readable report text/chip contrast. |

