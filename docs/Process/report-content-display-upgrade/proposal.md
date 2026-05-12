# Proposal — Report Content & Display Upgrade

## Metadata

- **Slug**: `report-content-display-upgrade`
- **Date**: 2026-04-25
- **Tier**: Standard
- **Owner**: SecManus workspace
- **Related design**: [`design.md`](./design.md)
- **Acceptance**: [`acceptance.md`](./acceptance.md), [`acceptance-ui.md`](./acceptance-ui.md)

## Problem

The current report area renders most substantial results as a linear list of `WorkspaceBlock` items, usually ending in a single `analysis` markdown block. This makes reports feel rigid and less professional: there is no report-level cover, no durable reading hierarchy, limited template behavior, inconsistent shared-report rendering, and export/share output can diverge from what the user sees in the workspace.

Users want a complete report experience for security and research work without adding an independent report-writing agent in this delivery.

## Goals

- Improve report content presentation so finished analyses read like professional deliverables, not raw assistant responses.
- Add a lightweight report template layer with cover/summary/body/appendix concepts for the current workspace report view.
- Introduce a flexible structured report protocol shape as a UI-facing normalization model, without requiring a backend report agent.
- Unify report rendering across workspace, shared report pages, and export paths.
- Preserve markdown fallback so existing persisted messages and old shared reports keep rendering.

## Non-goals

- No standalone report agent in this delivery.
- No multi-step report rewriting pipeline or extra LLM call after analysis completion.
- No user-customizable template editor.
- No database migration for first-class report documents unless implementation discovers it is strictly necessary.
- No full PDF/DOCX redesign beyond making current export/share behavior consistent with the upgraded report renderer.

## Users

- Security analysts who need readable evidence, findings, and recommended actions.
- Researchers who need long-form reports with sources, conclusions, and limitations.
- Operators sharing reports with teammates or stakeholders through the existing share link.

## Scope

In scope:

- Workspace report tab visual and information architecture upgrade.
- Shared report page parity with workspace report rendering.
- Normalized report document/view model derived from existing `WorkspaceBlock[]`.
- Template presets for at least security analysis, research brief, and generic analysis.
- Cover section and report-level metadata display.
- Markdown renderer consolidation using the existing `react-markdown` dependency.
- Component/unit tests for renderer, normalization, shared report parity, and export serialization.

Out of scope:

- Report agent orchestration.
- Template authoring UI.
- Long-term report versioning, comments, approvals, or collaboration.
- Re-running analysis to improve a report.

## Dependencies

- Existing frontend block types in `src/types/analysis.ts`.
- Existing task stats metadata from `TaskStatsBar`.
- Existing `react-markdown` dependency already used by chat rendering.
- Existing sharing API and `shared_reports.blocks` persistence.
- Existing export controls in `LiveWorkspace`.

## Success metrics

- A persisted `analysis` block renders in both workspace and shared report pages.
- Reports have a visible cover/metadata section and clear section hierarchy.
- Markdown reports with headings, lists, links, code blocks, tables, and blockquotes render consistently.
- Share/export content matches the visible report content rather than a separate ad hoc conversion path.
- Existing report tests still pass, and new tests cover legacy markdown fallback.

