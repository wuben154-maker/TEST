/**
 * Routes task_plan and task lifecycle updates to main vs subagent buckets.
 * Default scope is main when `scope` is omitted (backward compatible).
 */
import type { TaskPlan } from '@/types/analysis';

import { scrubTaskPlanPathsForDisplay } from '@/lib/scrubVirtualPathsForDisplay';

/** Stable key for subagent task plan maps (never empty string). */
export const SUBAGENT_PLAN_DEFAULT_KEY = '_default';

export type TaskPlanOwner = 'main' | 'subagent';

/**
 * Returns true if the event targets the main agent task board.
 */
export function isMainTaskPlanScope(ev: { scope?: string }): boolean {
  return (ev.scope ?? 'main') !== 'subagent';
}

/**
 * Key into `taskPlansSubagent` for scoped plans. Uses `subagentName` when present.
 */
export function subagentTaskPlanMapKey(ev: { subagentName?: string }): string {
  const n = ev.subagentName?.trim();
  return n && n.length > 0 ? n : SUBAGENT_PLAN_DEFAULT_KEY;
}

/**
 * For ThinkingEvent / timeline rows: owner classification for task routing.
 */
export function taskPlanOwnerFromEvent(ev: { scope?: string }): TaskPlanOwner {
  return isMainTaskPlanScope(ev) ? 'main' : 'subagent';
}

/**
 * Merge incoming plan into previous bucket (same semantics as legacy handleTaskPlan).
 */
export function mergeTaskPlanBucket(prev: TaskPlan | null, incoming: TaskPlan): TaskPlan {
  const incomingClean = scrubTaskPlanPathsForDisplay(incoming);
  if (!prev) return incomingClean;
  const prevById = new Map(prev.tasks.map((t) => [t.id, t] as const));
  const incomingIds = new Set(incomingClean.tasks.map((t) => t.id));
  const mergedTasks = incomingClean.tasks.map((t) => {
    const existing = prevById.get(t.id);
    if (!existing) return t;
    const incomingSteps = (t.steps || []).filter(Boolean);
    const prevSteps = (existing.steps || []).filter(Boolean);
    return {
      ...existing,
      ...t,
      result: t.result ?? existing.result,
      error: t.error ?? existing.error,
      durationMs: t.durationMs || existing.durationMs,
      skillName: t.skillName ?? existing.skillName,
      steps: incomingSteps.length > 0 ? incomingSteps : prevSteps,
    };
  });
  const extras = prev.tasks.filter((t) => !incomingIds.has(t.id));
  return {
    ...prev,
    ...incomingClean,
    totalDurationMs: incomingClean.totalDurationMs || prev.totalDurationMs,
    tasks: [...mergedTasks, ...extras],
  };
}

/**
 * Update one task's status in a plan copy (immutable).
 */
export function mapTaskInPlan(
  plan: TaskPlan,
  taskId: string,
  updater: (t: (typeof plan.tasks)[0]) => (typeof plan.tasks)[0],
): TaskPlan {
  return {
    ...plan,
    tasks: plan.tasks.map((t) => (t.id === taskId ? updater(t) : t)),
  };
}
