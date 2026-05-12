/**
 * Detect whether an analysis turn failed in a way that should block
 * side-effects such as knowledge-base archival.
 */
import type { TaskPlan } from '@/types/analysis';
import type { PerProjectStreamingState } from '@/types/streaming';
import { timelineHasError } from '@/lib/timelineDisplay';

function planHasTaskError(plan: TaskPlan | null | undefined): boolean {
  return Boolean(plan?.tasks?.some((t) => t.status === 'error'));
}

export function analysisTurnHasBlockingError(state: PerProjectStreamingState): boolean {
  if (timelineHasError(state.timeline)) return true;
  if (planHasTaskError(state.taskPlanMain)) return true;
  return Object.values(state.taskPlansSubagent ?? {}).some(planHasTaskError);
}
