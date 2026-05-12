# Acceptance — UI — analysis-workspace-report-collapse

## Metadata

- **Slug:** analysis-workspace-report-collapse
- **Links:** [proposal.md](./proposal.md), [design.md](./design.md)

## Scope

Desktop (`md+`) workspace on `Index`: chat/report `PanelGroup`, `CommandCenter` message column width.

## Reference assets

## Mockups deferred

No reference images; layout follows existing SecManus chrome and Cursor-like readability.

## Visual criteria

| ID | Criterion |
|----|-----------|
| U-01 | On a new analysis turn, when the user has not dragged the split, the report panel is collapsed and chat uses the freed horizontal space. |
| U-02 | When `workspaceTabs` first appears for the current stream, the report panel expands if it was collapsed. |
| U-03 | After reload, if no message/result has `workspaceTabs`, the report panel stays collapsed; if any has `workspaceTabs`, the report panel is shown (split). |
| U-04 | Chat transcript and composer share a centered column with a max width on wide viewports (readable line length). |

## Interaction criteria

| ID | Criterion |
|----|-----------|
| I-01 | After the user drags the resize handle, starting another analysis does not force-collapse the report panel. |
| I-02 | For a history turn that has `workspaceTabs`, using “Open workspace panel” restores split view if the report side was collapsed. |
| I-03 | Existing panel cycle control on the resize handle still works. |

## Responsive

- **md+:** Criteria above apply.
- **&lt; md:** Unchanged (stacked / overlay patterns).

## Accessibility

- Resize handle remains keyboard-accessible per `react-resizable-panels` defaults; focus styles unchanged.

## Sign-off

| ID | Pass/Fail | Verifier | Date | Notes |
|----|-----------|----------|------|-------|
| U-01 | | | | |
| U-02 | | | | |
| U-03 | | | | |
| U-04 | | | | |
| I-01 | | | | |
| I-02 | | | | |
| I-03 | | | | |
