import { Fragment, memo, useEffect, useMemo, useRef, useState } from 'react';
import { Lightbulb } from 'lucide-react';
import { useLanguage } from '@/contexts/LanguageContext';
import { logger } from '@/lib/logger';
import { ChatMessage } from './ChatMessage';
import { ParameterInput } from './ParameterInput';
import { UserDecision } from './UserDecision';
import { NextActions } from './NextActions';
import { ReActTimelineView } from './ReActTimelineView';
import { TimelineActivity } from './TimelineActivity';
import { buildReActTimeline, type ReActBlock, type ReActHitlSlotBlock } from '@/lib/buildReActTimeline';
import {
  buildAnalysisTurnItems,
  type AnalysisTurnItem,
  type AnalysisTurnViewModel,
} from '@/lib/analysisTurnModel';
import type { ParameterRequest } from '@/types/analysis';
import type { UserDecisionRequest } from './UserDecision';
import { useLiveElapsedSeconds } from '@/lib/liveElapsedSeconds';
import { formatThinkingElapsed, formatThoughtDuration } from '@/lib/thinkingDurationLabel';

export type AnalysisTurnCallbacks = {
  onParameterSubmit?: (parameters: Record<string, string>) => void;
  isSubmittingParameters?: boolean;
  onDecision?: (requestId: string, selectedOptions: string[]) => void;
  onNextActionClick?: (message: string) => void;
};

export type AnalysisTurnPanelProps = AnalysisTurnViewModel & AnalysisTurnCallbacks;

const ThinkingChrome = memo(function ThinkingChrome({
  isAnalyzing,
  thinkingStartTime,
  savedThinkingDurationSec,
}: {
  isAnalyzing: boolean;
  thinkingStartTime?: Date;
  savedThinkingDurationSec?: number;
}) {
  const [thinkingDuration, setThinkingDuration] = useState(0);
  const lastReasoningTimeRef = useRef<Date | undefined>();
  const calculatedDurationRef = useRef(0);
  const lastThinkingStartTsRef = useRef<number | undefined>();

  useEffect(() => {
    const ts = thinkingStartTime?.getTime();
    if (isAnalyzing && ts && ts !== lastThinkingStartTsRef.current) {
      lastThinkingStartTsRef.current = ts;
      lastReasoningTimeRef.current = undefined;
      calculatedDurationRef.current = 0;
      setThinkingDuration(0);
    }
  }, [isAnalyzing, thinkingStartTime]);

  useEffect(() => {
    const shouldStopTimer = !isAnalyzing && thinkingStartTime;
    if (shouldStopTimer && !lastReasoningTimeRef.current && thinkingStartTime) {
      lastReasoningTimeRef.current = new Date();
      const duration = Math.round(
        (lastReasoningTimeRef.current.getTime() - thinkingStartTime.getTime()) / 1000,
      );
      calculatedDurationRef.current = duration;
      setThinkingDuration(duration);
    }
  }, [isAnalyzing, thinkingStartTime]);

  const displayDuration = savedThinkingDurationSec ?? calculatedDurationRef.current ?? thinkingDuration;
  const shouldShowDuration = displayDuration > 0;

  const thinkingStartMs = thinkingStartTime?.getTime();
  const liveThinkingSec = useLiveElapsedSeconds(thinkingStartMs, isAnalyzing);

  if (!isAnalyzing && !shouldShowDuration) return null;

  return (
    <div className="flex justify-start">
      <div className="max-w-[90%] w-full rounded-md border border-border/40 bg-muted/20 px-3 py-2">
        {isAnalyzing ? (
          <div className="flex items-center gap-2 py-1">
            <Lightbulb className="w-4 h-4 text-muted-foreground/70 animate-pulse shrink-0" />
            {liveThinkingSec != null ? (
              <span
                className="bg-gradient-to-r from-muted-foreground/65 via-foreground/95 to-muted-foreground/65 bg-[length:200%_100%] bg-clip-text text-sm text-transparent animate-shimmer"
                lang="en"
              >
                {formatThinkingElapsed(liveThinkingSec)}
              </span>
            ) : (
              <>
                <span className="bg-gradient-to-r from-muted-foreground/65 via-foreground/95 to-muted-foreground/65 bg-[length:200%_100%] bg-clip-text text-sm text-transparent animate-shimmer">
                  Thinking
                </span>
                <span className="inline-flex gap-0.5">
                  <span
                    className="w-1 h-1 rounded-full bg-muted-foreground/50 animate-bounce"
                    style={{ animationDelay: '0ms' }}
                  />
                  <span
                    className="w-1 h-1 rounded-full bg-muted-foreground/50 animate-bounce"
                    style={{ animationDelay: '150ms' }}
                  />
                  <span
                    className="w-1 h-1 rounded-full bg-muted-foreground/50 animate-bounce"
                    style={{ animationDelay: '300ms' }}
                  />
                </span>
              </>
            )}
          </div>
        ) : (
          <div className="flex items-center gap-2 py-1 animate-fade-in">
            <Lightbulb className="w-4 h-4 text-muted-foreground/70 shrink-0" />
            <span className="text-sm text-muted-foreground" lang="en">
              {formatThoughtDuration(displayDuration)}
            </span>
          </div>
        )}
      </div>
    </div>
  );
});

/** Render an inline HITL form at its chronological position within the ReAct timeline.
 *  Uses model state (live streaming) first, falls back to event data stored in the slot block
 *  (conversation history / after resume completion when model state is cleared).
 */
function renderHitlInlineSlot(
  slot: ReActHitlSlotBlock,
  model: AnalysisTurnViewModel,
  callbacks: AnalysisTurnCallbacks,
  t: ReturnType<typeof useLanguage>['t'],
): React.ReactNode {
  if (slot.slotType === 'parameter_request') {
    const liveRequests = model.parameterRequests;
    const fallbackRequests = (slot.eventParameterRequests ?? []) as ParameterRequest[];
    const requests = liveRequests.length > 0 ? liveRequests : fallbackRequests;
    if (requests.length === 0) {
      logger.debug('hitl_inline_slot_requests_empty', {
        live_count: liveRequests.length,
        fallback_count: fallbackRequests.length,
      });
      return null;
    }

    const prompt = (
      liveRequests.length > 0
        ? model.parameterRequestDetail
        : slot.eventPrompt
    )?.trim() || '';

    const isSubmitted = model.hitlParametersSubmitted
      ?? (liveRequests.length === 0 && fallbackRequests.length > 0);

    return (
      <section className="mt-3 mb-1 animate-fade-in">
        <h4 className="text-xs font-medium text-muted-foreground/70 mb-3 flex items-center gap-1.5">
          <span className="w-1.5 h-1.5 rounded-full bg-amber-500/60" />
          {t.reasoning.needMoreInfo}
        </h4>
        {prompt && (
          <div className="rounded-md bg-muted/30 px-3 py-2 mb-2 text-sm text-foreground/90 leading-relaxed whitespace-pre-wrap">
            {prompt}
          </div>
        )}
        <ParameterInput
          requests={requests}
          onSubmit={callbacks.onParameterSubmit || (() => {})}
          isSubmitting={callbacks.isSubmittingParameters ?? false}
          isSubmitted={isSubmitted}
          initialFieldValues={model.submittedParameters}
        />
      </section>
    );
  }
  if (slot.slotType === 'decision_request') {
    const liveDecisions = model.decisions;
    const fallbackDecision = slot.eventDecision as UserDecisionRequest | undefined;
    const decisions = liveDecisions.length > 0
      ? liveDecisions
      : (fallbackDecision ? [fallbackDecision] : []);
    if (decisions.length === 0) return null;

    return (
      <section className="mt-3 mb-1 space-y-3 animate-fade-in">
        <h4 className="text-xs font-medium text-muted-foreground/70 mb-3 flex items-center gap-1.5">
          <span className="w-1.5 h-1.5 rounded-full bg-purple-500/60" />
          {t.reasoning.makeChoice}
        </h4>
        {decisions.map((decision) => (
          <UserDecision
            key={decision.id}
            request={decision}
            onDecision={callbacks.onDecision || (() => {})}
            isResolved={!!model.resolvedDecisions[decision.id]}
            resolvedAnswer={model.resolvedDecisions[decision.id]}
          />
        ))}
      </section>
    );
  }
  return null;
}

/**
 * Split ReAct blocks at `hitl_slot` boundaries for interleaved form rendering.
 * Returns N+1 segments and N slots where segments[i] precedes slots[i].
 */
function splitBlocksAtHitlSlots(blocks: ReActBlock[]): {
  segments: ReActBlock[][];
  slots: ReActHitlSlotBlock[];
} {
  const segments: ReActBlock[][] = [];
  const slots: ReActHitlSlotBlock[] = [];
  let current: ReActBlock[] = [];
  for (const b of blocks) {
    if (b.kind === 'hitl_slot') {
      segments.push(current);
      slots.push(b);
      current = [];
    } else {
      current.push(b);
    }
  }
  segments.push(current);
  return { segments, slots };
}

function renderAnalysisTurnItem(
  item: AnalysisTurnItem,
  model: AnalysisTurnViewModel,
  callbacks: AnalysisTurnCallbacks,
  t: ReturnType<typeof useLanguage>['t'],
): React.ReactNode {
  switch (item.kind) {
    case 'user_message':
      return (
        <ChatMessage key={item.key} type="user" content={item.content} timestamp={item.timestamp} />
      );
    case 'thinking_chrome':
      return (
        <ThinkingChrome
          key={item.key}
          isAnalyzing={model.isAnalyzing}
          thinkingStartTime={model.thinkingStartTime}
          savedThinkingDurationSec={model.savedThinkingDurationSec}
        />
      );
    case 'react_timeline': {
      // Empty timeline: unified shell (understanding, live tokens, intro).
      if (item.timeline.length === 0) {
        return (
          <TimelineActivity
            key={item.key}
            timeline={item.timeline}
            isStreaming={item.isStreaming}
            taskPlan={model.taskPlan}
            taskPlansSubagent={model.taskPlansSubagent}
            streamReasoning={model.currentReasoning?.trim() || undefined}
            understanding={model.understanding ?? undefined}
            parameterRequests={[]}
            onParameterSubmit={callbacks.onParameterSubmit}
            isSubmittingParameters={callbacks.isSubmittingParameters}
            hitlParametersSubmitted={false}
            submittedParameters={undefined}
            decisions={[]}
            resolvedDecisions={{}}
            onDecision={callbacks.onDecision}
          />
        );
      }
      const blocks = buildReActTimeline(item.timeline, { language: item.language });
      const hasHitlSlot = blocks.some((b) => b.kind === 'hitl_slot');

      if (!hasHitlSlot) {
        return (
          <ReActTimelineView
            key={item.key}
            blocks={blocks}
            isStreaming={item.isStreaming}
            hitlAwaiting={model.hitlAwaiting}
            thinkingDurationSec={item.thinkingDurationSec}
          />
        );
      }

      // Split at HITL slots: render forms inline at their chronological position
      // (e.g. between "Clarify research request" and "Define research brief").
      const { segments, slots } = splitBlocksAtHitlSlots(blocks);
      return (
        <div key={item.key}>
          {segments.map((seg, segIdx) => {
            const isLastSeg = segIdx === segments.length - 1;
            const reactView =
              seg.length > 0 ? (
                <ReActTimelineView
                  key={`seg-${segIdx}`}
                  blocks={seg}
                  isStreaming={isLastSeg ? item.isStreaming : false}
                  hitlAwaiting={model.hitlAwaiting}
                  thinkingDurationSec={segIdx === 0 ? item.thinkingDurationSec : undefined}
                />
              ) : null;
            const slot = segIdx < slots.length ? slots[segIdx] : null;
            const hitlForm = slot
              ? renderHitlInlineSlot(slot, model, callbacks, t)
              : null;
            return (
              <Fragment key={`split-${segIdx}`}>
                {reactView}
                {hitlForm}
              </Fragment>
            );
          })}
        </div>
      );
    }
    case 'conclusion':
      return <ChatMessage key={item.key} type="assistant" content={item.text} />;
    case 'parameters_footer': {
      const footerPrompt = model.parameterRequestDetail?.trim() || '';
      return (
        <section key={item.key} className="mt-4 pt-4 border-t border-border/30 animate-fade-in">
          <h4 className="text-xs font-medium text-muted-foreground/70 mb-3 flex items-center gap-1.5">
            <span className="w-1.5 h-1.5 rounded-full bg-amber-500/60" />
            {t.reasoning.needMoreInfo}
          </h4>
          {footerPrompt && (
            <div className="rounded-md bg-muted/30 px-3 py-2 mb-2 text-sm text-foreground/90 leading-relaxed whitespace-pre-wrap">
              {footerPrompt}
            </div>
          )}
          <ParameterInput
            requests={model.parameterRequests}
            onSubmit={callbacks.onParameterSubmit || (() => {})}
            isSubmitting={callbacks.isSubmittingParameters ?? false}
            isSubmitted={model.hitlParametersSubmitted ?? false}
            initialFieldValues={model.submittedParameters}
          />
        </section>
      );
    }
    case 'decisions_footer':
      return (
        <section key={item.key} className="mt-4 pt-4 border-t border-border/30 space-y-3">
          <h4 className="text-xs font-medium text-muted-foreground/70 mb-3 flex items-center gap-1.5">
            <span className="w-1.5 h-1.5 rounded-full bg-purple-500/60" />
            {t.reasoning.makeChoice}
          </h4>
          {model.decisions.map((decision) => (
            <UserDecision
              key={decision.id}
              request={decision}
              onDecision={callbacks.onDecision || (() => {})}
              isResolved={!!model.resolvedDecisions[decision.id]}
              resolvedAnswer={model.resolvedDecisions[decision.id]}
            />
          ))}
        </section>
      );
    case 'next_actions_footer':
      return (
        <section key={item.key} className="mt-4 pt-4 border-t border-border/30">
          <NextActions
            actions={model.nextActions}
            onActionClick={callbacks.onNextActionClick ?? (() => {})}
          />
        </section>
      );
    case 'empty_waiting':
      return (
        <div key={item.key} className="py-8 text-center">
          <p className="text-sm text-muted-foreground/50">{t.reasoning.waitingAnalysis}</p>
        </div>
      );
    default:
      return null;
  }
}

/**
 * One analysis turn in Command Center: single pipeline from ``buildAnalysisTurnItems`` → render.
 */
export const AnalysisTurnPanel = memo(function AnalysisTurnPanel(props: AnalysisTurnPanelProps) {
  const { t, language } = useLanguage();
  const {
    onParameterSubmit,
    isSubmittingParameters,
    onDecision,
    onNextActionClick,
    ...modelRest
  } = props;
  const model = modelRest as AnalysisTurnViewModel;
  const callbacks: AnalysisTurnCallbacks = {
    onParameterSubmit,
    isSubmittingParameters,
    onDecision,
    onNextActionClick,
  };

  const items = useMemo(
    () =>
      buildAnalysisTurnItems(model, {
        language,
        subagentFallbackName: t.reasoning.subagentFallbackName,
        includeNextActionsFooter: !!onNextActionClick,
      }),
    [
      model.isAnalyzing,
      model.timeline,
      model.currentReasoning,
      model.userInput,
      model.inputTimestamp,
      model.thinkingStartTime,
      model.savedThinkingDurationSec,
      model.understanding,
      model.parameterRequests,
      model.decisions,
      model.resolvedDecisions,
      model.taskSummary,
      model.conclusionText,
      model.nextActions,
      model.taskPlan,
      model.taskPlansSubagent,
      model.hitlAwaiting,
      model.parameterRequestDetail,
      model.hitlParametersSubmitted,
      model.submittedParameters,
      language,
      t.reasoning.subagentFallbackName,
      onNextActionClick,
    ],
  );

  if (items.length === 0) return null;

  return (
    <div className="space-y-3">
      {items.map((item) => renderAnalysisTurnItem(item, model, callbacks, t))}
    </div>
  );
});
