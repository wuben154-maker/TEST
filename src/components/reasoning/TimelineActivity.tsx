import { memo, useMemo } from 'react';
import type {
  AnalysisTimelineEntry,
  InputUnderstanding,
  ParameterRequest,
  TaskPlan,
} from '@/types/analysis';
import { useLanguage } from '@/contexts/LanguageContext';
import type { UserDecisionRequest } from './UserDecision';
import { buildUnifiedTimelineItems } from '@/lib/unifiedTimelineItems';
import { TimelineUnifiedBody } from './TimelineUnifiedBody';

export interface TimelineActivityProps {
  timeline: AnalysisTimelineEntry[];
  isStreaming?: boolean;
  taskPlan?: TaskPlan | null;
  taskPlansSubagent?: Record<string, TaskPlan | null>;
  streamReasoning?: string;
  understanding?: InputUnderstanding | null;
  parameterRequests?: ParameterRequest[];
  onParameterSubmit?: (parameters: Record<string, string>) => void;
  isSubmittingParameters?: boolean;
  hitlParametersSubmitted?: boolean;
  submittedParameters?: Record<string, string>;
  decisions?: UserDecisionRequest[];
  resolvedDecisions?: Record<string, string[]>;
  onDecision?: (requestId: string, selectedOptions: string[]) => void;
}

/** Composes unified timeline body; embedded from ``AnalysisTurnPanel`` for Command Center. */
export const TimelineActivity = memo(function TimelineActivity({
  timeline,
  isStreaming = false,
  taskPlan = null,
  taskPlansSubagent = {},
  streamReasoning,
  understanding,
  parameterRequests = [],
  onParameterSubmit,
  isSubmittingParameters = false,
  hitlParametersSubmitted = false,
  submittedParameters = {},
  decisions = [],
  resolvedDecisions = {},
  onDecision,
}: TimelineActivityProps) {
  const { t } = useLanguage();
  const streamReasoningTrim = streamReasoning?.trim();
  const understandingIntro = understanding
    ? [understanding.summary, understanding.reasoningSummary].filter(Boolean).join('\n\n').trim()
    : '';

  const unifiedItems = useMemo(
    () =>
      buildUnifiedTimelineItems({
        timeline,
        subagentFallbackName: t.reasoning.subagentFallbackName,
        understandingIntro: understandingIntro || undefined,
        streamReasoning: streamReasoningTrim || undefined,
        isStreaming,
      }),
    [
      timeline,
      t.reasoning.subagentFallbackName,
      understandingIntro,
      streamReasoningTrim,
      isStreaming,
    ],
  );

  return (
    <TimelineUnifiedBody
      items={unifiedItems}
      fullTimeline={timeline}
      isStreaming={isStreaming}
      taskPlan={taskPlan}
      taskPlansSubagent={taskPlansSubagent}
      parameterRequests={parameterRequests}
      onParameterSubmit={onParameterSubmit}
      isSubmittingParameters={isSubmittingParameters}
      hitlParametersSubmitted={hitlParametersSubmitted}
      submittedParameters={submittedParameters}
      decisions={decisions}
      resolvedDecisions={resolvedDecisions}
      onDecision={onDecision}
    />
  );
});
