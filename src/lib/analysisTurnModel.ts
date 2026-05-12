/**
 * Single view-model + ordered item list for one Command Center analysis turn.
 */
import type {
  AnalysisTimelineEntry,
  InputUnderstanding,
  NextAction,
  ParameterRequest,
  TaskPlan,
} from '@/types/analysis';
import type { Language } from '@/i18n';
import type { UserDecisionRequest } from '@/components/reasoning/UserDecision';
import { isHiddenFromUserTimeline } from '@/lib/timelineDisplay';

export type AnalysisTurnViewModel = {
  isAnalyzing: boolean;
  timeline: AnalysisTimelineEntry[];
  currentReasoning?: string;
  userInput?: string;
  inputTimestamp?: Date;
  thinkingStartTime?: Date;
  savedThinkingDurationSec?: number;
  understanding?: InputUnderstanding | null;
  parameterRequests: ParameterRequest[];
  parameterRequestDetail?: string;
  decisions: UserDecisionRequest[];
  resolvedDecisions: Record<string, string[]>;
  taskSummary?: string;
  conclusionText?: string;
  nextActions: NextAction[];
  taskPlan: TaskPlan | null;
  taskPlansSubagent: Record<string, TaskPlan | null>;
  hitlParametersSubmitted?: boolean;
  /** True after terminal ``done`` with ``awaitingHuman`` (LangGraph interrupt). */
  hitlAwaiting?: boolean;
  /** Restored or in-session submitted HITL field values (read-only form display). */
  submittedParameters?: Record<string, string>;
};

/** Any user-visible ``parameter_request`` row (main or subagent), for HITL UI routing. */
export function timelineHasVisibleParameterRequest(timeline: AnalysisTimelineEntry[]): boolean {
  return timeline.some((e) => !isHiddenFromUserTimeline(e) && e.type === 'parameter_request');
}

/** Timeline row that becomes an inline ``UserDecision`` in ``TimelineUnifiedBody``. */
export function timelineHasVisibleDecisionRequest(timeline: AnalysisTimelineEntry[]): boolean {
  return timeline.some(
    (e) =>
      !isHiddenFromUserTimeline(e) &&
      e.type === 'decision_request' &&
      e.decision != null &&
      typeof e.decision === 'object',
  );
}

export type AnalysisTurnItem =
  | { kind: 'user_message'; key: string; content: string; timestamp?: Date }
  | { kind: 'thinking_chrome'; key: string }
  | {
      kind: 'react_timeline';
      key: string;
      timeline: AnalysisTimelineEntry[];
      isStreaming: boolean;
      thinkingDurationSec?: number;
      language: Language;
    }
  | { kind: 'conclusion'; key: string; text: string }
  | { kind: 'parameters_footer'; key: string }
  | { kind: 'decisions_footer'; key: string }
  | { kind: 'next_actions_footer'; key: string }
  | { kind: 'empty_waiting'; key: string };

function shouldShowThinkingChrome(model: AnalysisTurnViewModel): boolean {
  if (model.isAnalyzing) return true;
  return (model.savedThinkingDurationSec ?? 0) > 0;
}

/**
 * Content that must render through the same timeline stack as live SSE (no legacy linear trace).
 */
function hasReplayBodyContent(model: AnalysisTurnViewModel): boolean {
  if (model.currentReasoning?.trim()) return true;
  const u = model.understanding;
  if (u) {
    const intro = [u.summary, u.reasoningSummary].filter(Boolean).join('\n').trim();
    if (intro) return true;
  }
  if (model.taskSummary?.trim()) return true;
  if ((model.taskPlan?.tasks?.length ?? 0) > 0) return true;
  return Object.values(model.taskPlansSubagent ?? {}).some(
    (p) => p != null && (p.tasks?.length ?? 0) > 0,
  );
}

export type BuildAnalysisTurnItemsContext = {
  language: Language;
  subagentFallbackName: string;
  /** When true, append next-actions footer (requires a click handler in UI). */
  includeNextActionsFooter?: boolean;
};

/**
 * Ordered list of UI blocks for one turn (user → thinking → body → conclusion → footers).
 */
export function buildAnalysisTurnItems(
  model: AnalysisTurnViewModel,
  ctx: BuildAnalysisTurnItemsContext,
): AnalysisTurnItem[] {
  const hasTimeline = model.timeline.length > 0;
  const showReactTimeline =
    hasTimeline || model.isAnalyzing || hasReplayBodyContent(model);
  const items: AnalysisTurnItem[] = [];

  if (model.userInput?.trim()) {
    items.push({
      kind: 'user_message',
      key: 'user',
      content: model.userInput.trim(),
      timestamp: model.inputTimestamp,
    });
  }

  if (showReactTimeline) {
    items.push({
      kind: 'react_timeline',
      key: 'react-timeline',
      timeline: model.timeline,
      isStreaming: model.isAnalyzing,
      thinkingDurationSec: model.savedThinkingDurationSec,
      language: ctx.language,
    });
  } else if (shouldShowThinkingChrome(model)) {
    items.push({ kind: 'thinking_chrome', key: 'thinking' });
  }

  if (model.conclusionText?.trim()) {
    items.push({ kind: 'conclusion', key: 'conclusion', text: model.conclusionText.trim() });
  }

  // Timeline usually renders HITL forms inline via `hitl_slot`.
  // Keep a footer fallback when live parameterRequests exists, so UI still
  // shows input even if inline slot mapping fails in edge cases.
  const inlineHitlParam =
    hasTimeline && timelineHasVisibleParameterRequest(model.timeline);
  const inlineHitlDecision =
    hasTimeline && timelineHasVisibleDecisionRequest(model.timeline);

  if (
    model.parameterRequests.length > 0 &&
    (!inlineHitlParam || Boolean(model.hitlAwaiting))
  ) {
    items.push({ kind: 'parameters_footer', key: 'parameters-footer' });
  }

  if (model.decisions.length > 0 && !inlineHitlDecision) {
    items.push({ kind: 'decisions_footer', key: 'decisions-footer' });
  }

  if (ctx.includeNextActionsFooter && !model.isAnalyzing && model.nextActions.length > 0) {
    items.push({ kind: 'next_actions_footer', key: 'next-actions-footer' });
  }

  const emptyBase =
    !model.isAnalyzing &&
    !model.userInput?.trim() &&
    !model.conclusionText?.trim() &&
    model.parameterRequests.length === 0 &&
    model.decisions.length === 0;

  if (emptyBase && !showReactTimeline && !shouldShowThinkingChrome(model)) {
    items.push({ kind: 'empty_waiting', key: 'empty-waiting' });
  }

  return items;
}
