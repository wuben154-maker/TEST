import { Fragment, memo, useCallback, useMemo, type ReactNode } from 'react';
import { AlertCircle } from 'lucide-react';
import type {
  AnalysisTimelineEntry,
  DecisionRequest,
  ParameterRequest,
  TaskPlan,
} from '@/types/analysis';
import { useLanguage } from '@/contexts/LanguageContext';
import { ParameterInput } from './ParameterInput';
import { UserDecision, type UserDecisionRequest } from './UserDecision';
import { TaskListPanel } from './TaskExecutionPanel';
import { ReActTimelineView } from './ReActTimelineView';
import type { UnifiedTimelineItem } from '@/lib/unifiedTimelineItems';
import type { TimelineActivityChunk } from '@/lib/timelineDisplay';
import type { Language } from '@/i18n';
import {
  buildReActTimeline,
  foldResearchTaskListBuckets,
  maxSeqInTimelineSlice,
  mergeResearchTaskListsIntoBlocks,
  researchTaskBucketKey,
  type ReActBlock,
} from '@/lib/buildReActTimeline';

/** Explore-buffer rows → ReAct tool/thinking blocks (replaces legacy grouped tool shell). */
function ExploreReActSection({
  fullTimeline,
  events,
  language,
  isStreaming,
}: {
  fullTimeline: readonly AnalysisTimelineEntry[];
  events: readonly AnalysisTimelineEntry[];
  language: Language;
  isStreaming: boolean;
}) {
  const maxSeq = useMemo(() => maxSeqInTimelineSlice(events), [events]);
  const blocks = useMemo(() => {
    const base = buildReActTimeline(events as AnalysisTimelineEntry[], { language });
    const buckets = foldResearchTaskListBuckets(fullTimeline as AnalysisTimelineEntry[], {
      language,
      maxSeq,
    });
    return mergeResearchTaskListsIntoBlocks(base, buckets);
  }, [events, fullTimeline, language, maxSeq]);
  if (blocks.length === 0 && !isStreaming) return null;
  return <ReActTimelineView blocks={blocks} isStreaming={isStreaming} />;
}

function seqNum(ev: AnalysisTimelineEntry): number {
  const n = Number(ev.seq);
  return Number.isFinite(n) ? n : 0;
}

function timelineDecisionToUserRequest(ev: AnalysisTimelineEntry): UserDecisionRequest | null {
  const d = ev.decision as DecisionRequest | undefined;
  if (!d || typeof d !== 'object' || !Array.isArray(d.options)) return null;
  return {
    id: d.id,
    question: d.question,
    options: d.options.map((o) => ({
      id: o.id,
      label: o.label,
      description: o.description,
      variant: o.variant,
    })),
    allowMultiple: d.allowMultiple,
  };
}

/** Subagent-scoped rows → ReAct (compact tone). */
function SubagentReActSection({
  fullTimeline,
  items,
  language,
  isStreaming,
}: {
  fullTimeline: readonly AnalysisTimelineEntry[];
  items: AnalysisTimelineEntry[];
  language: Language;
  isStreaming: boolean;
}) {
  const errorItems = items.filter((e) => e.type === 'error');
  const rest = items.filter((e) => e.type !== 'error');
  const anchor = useMemo(
    () => rest.find((e) => (e.scope ?? 'main') === 'subagent'),
    [rest],
  );
  const onlyBucketKey = anchor ? researchTaskBucketKey(anchor) : undefined;
  const maxSeq = useMemo(() => maxSeqInTimelineSlice(items), [items]);
  const blocks = useMemo(() => {
    const base = buildReActTimeline(rest, { language });
    const buckets = foldResearchTaskListBuckets(fullTimeline as AnalysisTimelineEntry[], {
      language,
      maxSeq,
      onlyBucketKey,
    });
    return mergeResearchTaskListsIntoBlocks(base, buckets);
  }, [fullTimeline, language, maxSeq, onlyBucketKey, rest]);

  return (
    <div className="space-y-1">
      {errorItems.map((ev, i) => (
        <div
          key={`sub-err-${String(ev.id ?? i)}-${seqNum(ev)}`}
          className="flex items-start gap-2 py-1 text-xs text-destructive"
        >
          <AlertCircle className="w-3 h-3 shrink-0 mt-0.5" aria-hidden />
          <span>{String(ev.detail ?? ev.label ?? '')}</span>
        </div>
      ))}
      {blocks.length > 0 || isStreaming ? (
        <ReActTimelineView
          blocks={blocks}
          isStreaming={isStreaming}
          visualTone="subagentInline"
        />
      ) : null}
    </div>
  );
}

export type TimelineUnifiedBodyProps = {
  items: UnifiedTimelineItem[];
  /** Canonical SSE timeline for cumulative ConductResearch merges across explore chunks. */
  fullTimeline: readonly AnalysisTimelineEntry[];
  isStreaming: boolean;
  taskPlan: TaskPlan | null;
  taskPlansSubagent: Record<string, TaskPlan | null>;
  parameterRequests: ParameterRequest[];
  onParameterSubmit?: (parameters: Record<string, string>) => void;
  isSubmittingParameters?: boolean;
  hitlParametersSubmitted?: boolean;
  submittedParameters?: Record<string, string>;
  decisions: UserDecisionRequest[];
  resolvedDecisions: Record<string, string[]>;
  onDecision?: (requestId: string, selectedOptions: string[]) => void;
};

/** Renders pre-sorted ``UnifiedTimelineItem[]`` (explore, task boards, HITL, subagent, …). */
export const TimelineUnifiedBody = memo(function TimelineUnifiedBody({
  items,
  fullTimeline,
  isStreaming,
  taskPlan,
  taskPlansSubagent,
  parameterRequests,
  onParameterSubmit,
  isSubmittingParameters = false,
  hitlParametersSubmitted = false,
  submittedParameters = {},
  decisions,
  resolvedDecisions,
  onDecision,
}: TimelineUnifiedBodyProps) {
  const { t, language } = useLanguage();

  const renderActivityChunk = useCallback(
    (chunk: TimelineActivityChunk): ReactNode => {
      if (chunk.kind === 'explore') {
        if (!chunk.events.length) return null;
        return (
          <ExploreReActSection
            fullTimeline={fullTimeline}
            events={chunk.events as unknown as AnalysisTimelineEntry[]}
            language={language}
            isStreaming={isStreaming}
          />
        );
      }
      if (chunk.kind === 'reasoning_main') {
        if (!chunk.text.trim()) return null;
        const blocks: ReActBlock[] = [
          {
            kind: 'thinking',
            reasoning: `${t.reasoning.thinkingPrefix}${chunk.text}`,
            answer: '',
            turn: chunk.turn,
            invokeDurationSec: chunk.invokeDurationSec,
            invokeStartMs: chunk.invokeStartMs,
            invokeState: chunk.invokeState,
          },
        ];
        return <ReActTimelineView blocks={blocks} isStreaming={isStreaming} />;
      }
      if (chunk.kind === 'task_summary' && chunk.summary.trim()) {
        const blocks: ReActBlock[] = [{ kind: 'result', summary: chunk.summary.trim() }];
        return <ReActTimelineView blocks={blocks} isStreaming={false} />;
      }
      if (chunk.kind === 'delegation') {
        const line = t.reasoning.delegatingSubagent
          .replace('{subagent}', chunk.subagent)
          .replace('{task}', chunk.task || t.reasoning.delegatedTaskPlaceholder);
        const blocks: ReActBlock[] = [{ kind: 'step', stepVariant: 'generic', label: line }];
        return <ReActTimelineView blocks={blocks} isStreaming={false} />;
      }
      if (chunk.kind === 'task_board') {
        if (!taskPlan && !isStreaming) return null;
        return (
          <div className="animate-fade-in">
            <TaskListPanel plan={taskPlan ?? undefined} isLoading={isStreaming && !taskPlan} />
          </div>
        );
      }
      if (chunk.kind === 'task_board_sub') {
        const subPlan = taskPlansSubagent[chunk.subagentKey] ?? null;
        if (!subPlan && !isStreaming) return null;
        return (
          <div className="animate-fade-in space-y-1">
            <p className="text-xs text-muted-foreground">
              {chunk.subagentKey === '_default' ? t.reasoning.subagentFallbackName : chunk.subagentKey}
            </p>
            <TaskListPanel plan={subPlan ?? undefined} isLoading={isStreaming && !subPlan} />
          </div>
        );
      }
      if (chunk.kind === 'parameter_request') {
        const promptText =
          typeof chunk.entry.detail === 'string' ? chunk.entry.detail.trim() : '';
        const fromEntry = chunk.entry.parameterRequests;
        const reqs: ParameterRequest[] =
          Array.isArray(fromEntry) && fromEntry.length > 0 ? fromEntry : parameterRequests;
        if (reqs.length === 0) {
          return <p className="text-xs text-muted-foreground py-1">{t.reasoning.needMoreInfo}</p>;
        }
        return (
          <div className="space-y-2">
            {promptText && (
              <div className="rounded-md bg-muted/30 px-3 py-2 text-sm text-foreground/90 leading-relaxed whitespace-pre-wrap">
                {promptText}
              </div>
            )}
            <div className="rounded-md border border-border/40 bg-muted/10 px-3 py-2">
              <ParameterInput
                requests={reqs}
                onSubmit={onParameterSubmit ?? (() => {})}
                isSubmitting={isSubmittingParameters}
                isSubmitted={hitlParametersSubmitted}
                initialFieldValues={submittedParameters}
              />
            </div>
          </div>
        );
      }
      if (chunk.kind === 'decision_request') {
        const mapped = timelineDecisionToUserRequest(chunk.entry);
        const req =
          mapped ?? decisions.find((d) => d.id === String(chunk.entry.id ?? chunk.entry.requestId ?? ''));
        if (!req) return null;
        return (
          <div className="rounded-md border border-border/40 px-3 py-2">
            <UserDecision
              request={req}
              onDecision={onDecision ?? (() => {})}
              isResolved={!!resolvedDecisions[req.id]}
              resolvedAnswer={resolvedDecisions[req.id]}
            />
          </div>
        );
      }
      if (chunk.kind !== 'subagent') return null;
      if (!chunk.items.length) return null;
      return (
        <div className="space-y-1">
          <SubagentReActSection
            fullTimeline={fullTimeline}
            items={chunk.items}
            language={language}
            isStreaming={isStreaming}
          />
        </div>
      );
    },
    [
      t,
      language,
      fullTimeline,
      isStreaming,
      taskPlan,
      taskPlansSubagent,
      parameterRequests,
      onParameterSubmit,
      isSubmittingParameters,
      decisions,
      resolvedDecisions,
      onDecision,
    ],
  );

  if (items.length === 0) return null;

  return (
    <div className="space-y-3 animate-fade-in">
      {items.map((item) => {
        if (item.kind === 'understanding_intro') {
          const introBlocks: ReActBlock[] = [
            { kind: 'thinking', reasoning: item.text, answer: '', turn: 0 },
          ];
          return (
            <ReActTimelineView key={`intro-${item.order}`} blocks={introBlocks} isStreaming={false} />
          );
        }
        if (item.kind === 'main_error') {
          const ev = item.entry;
          return (
            <div
              key={`err-${String(ev.id)}-${item.sortKey}-${item.order}`}
              className="rounded-md border border-destructive/30 bg-destructive/5 px-3 py-2 text-sm text-destructive flex items-start gap-2"
            >
              <AlertCircle className="w-4 h-4 shrink-0 mt-0.5" />
              <span>{String(ev.detail ?? ev.label ?? '')}</span>
            </div>
          );
        }
        if (item.kind === 'stream_reasoning') {
          const streamBlocks: ReActBlock[] = [
            {
              kind: 'thinking',
              reasoning: `${t.reasoning.thinkingPrefix}${item.text}`,
              answer: '',
              turn: 0,
            },
          ];
          return (
            <ReActTimelineView
              key={`stream-${item.order}`}
              blocks={streamBlocks}
              isStreaming={isStreaming}
            />
          );
        }
        return <Fragment key={item.chunk.key}>{renderActivityChunk(item.chunk)}</Fragment>;
      })}
    </div>
  );
});
