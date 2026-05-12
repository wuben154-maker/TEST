import type { WorkspaceTabInstance } from '@/types/analysis';
import type { ConversationMessage, TaskKind } from '@/types/project';
import { extractLatestTaskPlanFromTimeline } from '@/lib/timelineDisplay';

/** Fields read from streaming / persistence snapshot when building an AnalysisResult. */
export type WorkspaceChromeSnapshot = {
  toolCallCount?: number;
  sandboxRunCount?: number;
  workspaceTabs?: WorkspaceTabInstance[];
  taskPlanMain?: { tasks?: unknown[] } | null;
  taskPlansSubagent?: Record<string, { tasks?: unknown[] } | null | undefined> | null;
  /**
   * Backend-confirmed task profile (`conclusion.meta.taskKind`). When present
   * this turn was an agentic security/research run, so chrome must persist
   * across refresh even when the lighter signals (toolCallCount / workspaceTabs
   * / taskPlan) didn't survive the JSON-column persistence cull. Without this,
   * `messages.stats` ends up holding only `{taskKind, security|research}` and
   * the panel collapses on reload — regression noted in 2026-04-25.
   */
  taskKind?: TaskKind;
};

/**
 * Whether a task plan has actually started executing (any task past `pending`).
 *
 * A plan whose tasks are all still `pending` means the agent built the plan but
 * never ran a single step — e.g. it hit a HITL `parameter_request` right after
 * planning and the user replied conversationally ("I haven't uploaded yet").
 * Such a turn carries no analysis output and must not be treated as an agentic
 * turn: it should stay a plain chat reply, without creating a workspace tab or
 * expanding the report panel.
 */
export function taskPlanHasStartedExecution(
  plan: { tasks?: unknown[] } | null | undefined,
): boolean {
  if (!plan) return false;
  const tasks = plan.tasks as Array<{ status?: string } | null | undefined> | undefined;
  if (!tasks || tasks.length === 0) return false;
  return tasks.some((t) => {
    const status = t?.status;
    return typeof status === 'string' && status !== 'pending';
  });
}

/**
 * Whether this turn should keep the task panel chrome (header, stats bar, inner tabs)
 * after streaming ends. Must stay aligned with `liveIsComplex` in LiveWorkspace.
 *
 * NOTE: mere presence of `taskPlanMain` is NOT enough — a plan can exist without
 * any task having executed (HITL-aborted turn). See {@link taskPlanHasStartedExecution}.
 */
export function inferUseWorkspaceTaskPanelFromSnapshot(s: WorkspaceChromeSnapshot): boolean {
  if (s.taskKind) return true;
  if ((s.toolCallCount ?? 0) > 0) return true;
  if ((s.workspaceTabs?.length ?? 0) > 0) return true;
  if ((s.sandboxRunCount ?? 0) > 0) return true;
  if (taskPlanHasStartedExecution(s.taskPlanMain)) return true;
  if (s.taskPlansSubagent) {
    for (const plan of Object.values(s.taskPlansSubagent)) {
      if (taskPlanHasStartedExecution(plan)) return true;
    }
  }
  return false;
}

export function inferUseWorkspaceTaskPanelFromMessage(msg: ConversationMessage): boolean {
  if (
    inferUseWorkspaceTaskPanelFromSnapshot({
      toolCallCount: msg.stats?.toolCallCount,
      sandboxRunCount: msg.stats?.sandboxRunCount,
      workspaceTabs: msg.workspaceTabs,
      taskPlanMain: msg.taskPlan ?? null,
      taskPlansSubagent: msg.taskPlansSubagent ?? null,
      taskKind: msg.stats?.taskKind,
    })
  ) {
    return true;
  }
  // Timeline may still carry task_plan after reload when `taskPlan` is not denormalized on the row.
  // Same rule applies: only count it when at least one task actually ran.
  const timelinePlan = extractLatestTaskPlanFromTimeline(msg.timeline ?? []);
  if (taskPlanHasStartedExecution(timelinePlan)) return true;
  return false;
}
