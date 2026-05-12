/**
 * Left chat column: show SSE `conclusion` only for turns where the canonical answer
 * is not the workspace/report body.
 *
 * **Strategy B (taskKind + agentic)**: professional sub-agents
 * (security / research, identified by backend-owned TaskStatsMeta.taskKind)
 * always route to the report area. For legacy or un-classified turns we keep
 * an "agentic artifacts" fallback — real blocks, workspace tabs, or multiple
 * subagent plans — but a bare `task_plan` / `timeline(task_plan)` event is
 * NOT enough to hijack the report area anymore. That change prevents simple
 * agents that merely planned a todo list from stealing the report panel.
 */
import type { AnalysisTimelineEntry, TaskPlan } from '@/types/analysis';

export function streamingConclusionForChat(
  conclusion: string | undefined,
  opts: {
    blocksCount: number;
    taskPlan: TaskPlan | null;
    taskPlansSubagent: Record<string, TaskPlan | null>;
    workspaceTabsCount: number;
    timeline: AnalysisTimelineEntry[];
    /** Backend TaskStatsMeta.taskKind. Optional for legacy turns. */
    taskKind?: 'security' | 'research';
  },
): string | undefined {
  const text = conclusion?.trim();
  if (!text) return undefined;

  const isProfessional =
    opts.taskKind === 'security' || opts.taskKind === 'research';

  // Retained agentic fallback — real outputs still route to the report area
  // even without an explicit taskKind (e.g. legacy conversations, unmigrated
  // subagents).  NOTE: `taskPlan` and `timeline(task_plan)` are intentionally
  // removed; see Strategy B in design.md.
  const hasSubagentPlans = Object.values(opts.taskPlansSubagent ?? {}).some(
    (p) => p != null && (p.tasks?.length ?? 0) > 0,
  );
  const hasAgenticArtifacts =
    opts.blocksCount > 0 || opts.workspaceTabsCount > 0 || hasSubagentPlans;

  if (isProfessional || hasAgenticArtifacts) return undefined;
  return text;
}
