import type { Project } from '@/types/project';
import { assistantMessageYieldsAnalysisTab } from '@/lib/buildAnalysisResultFromAssistantMessage';

/** sessionStorage key: user adjusted the chat/report layout (drag, cycle, or open workspace) for this session. */
export function panelUserDraggedStorageKey(projectId: string): string {
  return `secmanus:workspacePanelUserDragged:${projectId}`;
}

/**
 * Persisted so refresh does not force-collapse when the user had chosen a split or expanded report.
 */
export function markWorkspacePanelLayoutUserCustomized(projectId: string): void {
  try {
    if (typeof sessionStorage === 'undefined') return;
    sessionStorage.setItem(panelUserDraggedStorageKey(projectId), '1');
  } catch {
    // ignore quota / private mode
  }
}

export function readWorkspacePanelLayoutUserCustomized(projectId: string): boolean {
  try {
    return (
      typeof sessionStorage !== 'undefined' &&
      sessionStorage.getItem(panelUserDraggedStorageKey(projectId)) === '1'
    );
  } catch {
    return false;
  }
}

/**
 * Hints derived from *live* streaming state (pre-persistence). Pass these in so
 * the panel expands immediately when a conclusion meta / first block arrives,
 * instead of waiting for the backend to persist and the frontend to reload.
 */
export interface LiveReportPanelHint {
  /** Backend TaskStatsMeta.taskKind; security/research must always expand. */
  taskKind?: 'security' | 'research';
  /** Live workspace blocks already produced during streaming. */
  blocksCount?: number;
  /** Live workspace tabs already produced during streaming. */
  workspaceTabsCount?: number;
}

/**
 * Whether the report/workspace side should be shown (split) after load/refresh
 * **or** during a live streaming turn.
 *
 * Persisted checks (aligned with {@link assistantMessageYieldsAnalysisTab}):
 * a turn that did not qualify for a report tab must not force the panel open.
 * In particular a HITL-aborted turn with a `running`-only taskPlan and no tool
 * calls / blocks / workspace tabs stays a plain chat reply.
 *
 * Live hints cover the streaming window where nothing is persisted yet: if
 * backend has already classified the turn (taskKind = security/research) or
 * emitted real artifacts, open the panel *now*.
 */
export function projectShouldExpandReportPanel(
  project: Project,
  live?: LiveReportPanelHint,
): boolean {
  if (live) {
    if (live.taskKind === 'security' || live.taskKind === 'research') {
      return true;
    }
    if ((live.blocksCount ?? 0) > 0) return true;
    if ((live.workspaceTabsCount ?? 0) > 0) return true;
  }
  if ((project.blocks?.length ?? 0) > 0) return true;
  for (const r of project.analysisResults) {
    if ((r.workspaceTabs?.length ?? 0) > 0) return true;
    if ((r.blocks?.length ?? 0) > 0) return true;
    if (r.useWorkspaceTaskPanel === true) return true;
  }
  for (const m of project.messages) {
    if (m.type !== 'assistant') continue;
    if (assistantMessageYieldsAnalysisTab(m)) return true;
  }
  return false;
}
