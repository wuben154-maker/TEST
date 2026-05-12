# Acceptance — Report Content & Display Upgrade

## Metadata

- **Slug**: `report-content-display-upgrade`
- **Owner**: SecManus workspace
- **Last updated**: 2026-04-25
- **Proposal**: [`proposal.md`](./proposal.md)
- **Design**: [`design.md`](./design.md)

## Scope reference

This document covers non-visual/data-contract verification for:

- Frontend report normalization contract in `design.md` → `## Contracts`.
- Markdown export serialization in `design.md` → `## Flows` / `Export flow`.
- Shared-report backward compatibility in `design.md` → `## Edge cases & errors`.
- No-report-agent scope boundary in `proposal.md` → `## Non-goals`.

## Environment

- Local frontend test environment: `npm run test`.
- Local E2E environment if available: Vite dev server + Python backend + Playwright.
- Backend pytest only required if implementation changes shared-report API or backend persistence code.
- No secrets or auth credentials are stored in this document.

## Functional criteria

| ID | Criterion | Evidence |
|----|-----------|----------|
| A-01 | Given a report with an `analysis` block, when it is normalized, then the analysis markdown is preserved in a report section and is not dropped. | Unit test for `normalizeReportDocument` with `analysis` block. |
| A-02 | Given legacy blocks (`log`, `decoder`, `intel`, `summary`, `text`), when normalized, then each remains renderable through either a report section or legacy block wrapper. | Unit test covering all existing `WorkspaceBlock` variants. |
| A-03 | Given missing or unknown metadata, when a report is normalized, then it falls back to `generic_analysis` and remains renderable. | Unit test with minimal block payload. |
| A-04 | Given security or research stats metadata, when a report is normalized, then the selected template reflects the task kind without requiring a report agent. | Unit test for template selection. |
| A-05 | Given normalized report content, when Markdown export runs, then the exported markdown includes title, sections, and analysis body. | Unit test for `serializeReportMarkdown`; manual export evidence if implemented. |
| A-06 | Given existing shared-report API payloads with `blocks`, when fetched by the UI, then no backend schema migration is required for this delivery. | No backend migration in diff, or backend tests passing if API touched. |
| A-07 | Given this delivery's scope, when implementation completes, then no standalone report agent, new subagent, or extra post-analysis LLM call is introduced. | Code review / grep evidence for absence of new report-agent orchestration. |

## Non-functional criteria

| ID | Criterion | Evidence |
|----|-----------|----------|
| N-01 | Report normalization is pure and deterministic for the same input. | Pure function tests; no network or time dependency except explicitly passed metadata. |
| N-02 | Markdown rendering does not execute arbitrary raw HTML. | Implementation review; renderer tests if raw HTML is encountered. |
| N-03 | Old reports continue rendering without data migration. | Component tests using legacy `WorkspaceBlock[]` fixtures. |
| N-04 | Export/share paths use the same normalized content source where practical. | Test or implementation review showing shared serializer/renderer usage. |

## Sign-off

| Criterion | Pass/Fail | Verifier | Date | Notes |
|-----------|-----------|----------|------|-------|
| A-01 | Pass | Agent | 2026-04-25 | `src/lib/reportDocument.test.ts`; full `npm run test -- --testTimeout 10000` passed 53 files / 398 tests. |
| A-02 | Pass | Agent | 2026-04-25 | `reportDocument.test.ts` covers `log`, `decoder`, `intel`, `summary`, and `text` legacy block wrappers. |
| A-03 | Pass | Agent | 2026-04-25 | `reportDocument.test.ts` verifies missing metadata falls back to `generic_analysis`. |
| A-04 | Pass | Agent | 2026-04-25 | `reportDocument.test.ts` verifies security stats select `security_analysis` without any report agent. |
| A-05 | Pass | Agent | 2026-04-25 | `serializeReportMarkdown` unit test plus `LiveWorkspace` export path now uses normalized serializer. |
| A-06 | Pass | Agent | 2026-04-25 | No backend schema/API code changed; `SharedReport` consumes existing `blocks` payload. |
| A-07 | Pass | Agent | 2026-04-25 | Implementation adds no report agent/subagent/orchestration; report layer is frontend-only. |
| N-01 | Pass | Agent | 2026-04-25 | `normalizeReportDocument` is a pure function; generated time and localized copy are explicit inputs. |
| N-02 | Pass | Agent | 2026-04-25 | `react-markdown` is used without raw HTML plugins; link rendering is constrained to safe target/rel. |
| N-03 | Pass | Agent | 2026-04-25 | Legacy block tests and shared report E2E confirm old `blocks` payload remains renderable. |
| N-04 | Pass | Agent | 2026-04-25 | Workspace export uses `serializeReportMarkdown`; workspace/shared surfaces use `ReportRenderer`. |

