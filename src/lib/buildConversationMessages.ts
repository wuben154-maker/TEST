/**
 * Build [userMsg, assistantMsg] from streaming state for appending to conversation history.
 * Shared by useStreamingAnalysisMulti (direct append) and useConversationPersistence (DB save).
 */
import type { WorkspaceBlock, TaskPlan, InputUnderstanding, AnalysisTimelineEntry } from '@/types/analysis';
import type { ConversationMessage, AnalysisResultStats } from '@/types/project';
import type { PerProjectStreamingState } from '@/types/streaming';
import {
  aggregateReasoningFromTimeline,
  getTimelineErrorDetail,
  timelineHasError,
} from '@/lib/timelineDisplay';
import { taskPlanHasStartedExecution } from '@/lib/analysisWorkspaceChrome';

function cloneSnapshot<T>(value: T): T {
  if (value === null || value === undefined) return value;
  try {
    return structuredClone(value);
  } catch {
    return JSON.parse(JSON.stringify(value)) as T;
  }
}

export function buildConversationMessages(
  state: PerProjectStreamingState,
): [ConversationMessage, ConversationMessage] | null {
  const timelineReasoning = aggregateReasoningFromTimeline(state.timeline);
  const hasReasoning = !!timelineReasoning || !!state.currentReasoning;
  const hasBlocks = (state.blocks?.length ?? 0) > 0;
  // A task_plan only counts as "agentic turn" after at least one task has started.
  // A plan whose tasks are all still `pending` (e.g. HITL hit right after planning)
  // means the agent produced nothing analysable — treat this turn as a plain chat reply
  // so `content` keeps the conclusion text instead of being cleared.
  const hasTaskPlan =
    taskPlanHasStartedExecution(state.taskPlanMain) ||
    Object.values(state.taskPlansSubagent ?? {}).some((pl) => taskPlanHasStartedExecution(pl));
  const hasUnderstanding = !!state.understanding;
  const hasTaskSummary = !!state.taskSummary;
  const hasConclusion = !!state.conclusion;
  const hasTimeline = (state.timeline?.length ?? 0) > 0;
  const hasError = timelineHasError(state.timeline);

  if (
    !hasReasoning &&
    !hasBlocks &&
    !hasTaskPlan &&
    !hasUnderstanding &&
    !hasTaskSummary &&
    !hasConclusion &&
    !hasTimeline
  ) {
    return null;
  }

  const snapshot = {
    userInput: state.userInput,
    inputTimestamp: state.inputTimestamp,
    currentReasoning: state.currentReasoning,
    blocks: cloneSnapshot(state.blocks ?? []),
    taskPlan: cloneSnapshot(state.taskPlanMain),
    taskPlansSubagent: cloneSnapshot(state.taskPlansSubagent ?? {}),
    understanding: cloneSnapshot(state.understanding),
    taskSummary: state.taskSummary,
    conclusion: state.conclusion,
    timeline: cloneSnapshot(state.timeline ?? []) as AnalysisTimelineEntry[],
  };

  const thinkingDuration = state.thinkingStartTime
    ? Math.round((Date.now() - state.thinkingStartTime.getTime()) / 1000)
    : undefined;

  const userMsg: ConversationMessage = {
    id: `user-${Date.now()}`,
    type: 'user',
    content: snapshot.userInput || '[Attachment-only request]',
    timestamp: snapshot.inputTimestamp || new Date(),
  };

  let content: string;
  let reasoning: string;

  const aggregatedReasoning =
    timelineReasoning ||
    snapshot.currentReasoning ||
    (snapshot.understanding as { reasoningSummary?: string } | null)?.reasoningSummary ||
    '';

  if (hasTaskPlan) {
    content = '';
    reasoning = aggregatedReasoning;
  } else {
    content = snapshot.conclusion || aggregatedReasoning || '';
    reasoning = aggregatedReasoning;
  }

  // With task_plan, keep assistant chat empty: the canonical answer is workspace blocks
  // (and timeline replay). Do not duplicate SSE `conclusion` into `content`.

  if (reasoning && content) {
    const r = reasoning.trim();
    const c = content.trim();
    const shorter = r.length < c.length ? r : c;
    const longer = r.length >= c.length ? r : c;
    if (longer.startsWith(shorter)) {
      reasoning = (snapshot.understanding as { reasoningSummary?: string } | null)?.reasoningSummary || '';
    }
  }

  const errorDetail = getTimelineErrorDetail(state.timeline);
  if (!content && hasError) {
    content = `分析失败: ${errorDetail || '未知错误（请查看后端日志）'}`;
  } else if (!content && hasUnderstanding) {
    const u = snapshot.understanding as Record<string, unknown> | null;
    const alternatives = Array.isArray(u?.suggestedAlternatives) ? u.suggestedAlternatives : [];
    const isOutOfScope = u?.taskCategory === 'unknown' && alternatives.length > 0;
    if (isOutOfScope) {
      const optionLines = (alternatives as Array<Record<string, unknown>>).map((alt) => {
        const option = alt?.option ?? '-';
        const title = alt?.title ?? '';
        const desc = alt?.description ?? '';
        return `${option}. ${title}\n${desc}`;
      });
      content = `${u?.summary || '此请求超出系统能力范围。'}\n\n你可以尝试以下方向：\n${optionLines.join('\n\n')}`;
    } else if (typeof u?.summary === 'string' && u.summary) {
      content = u.summary;
    }
  } else if (!content && !hasTimeline && !hasBlocks && !hasTaskPlan) {
    content = '分析过程中断，未能获取完整结果。请重试。';
  } else if (!content && hasBlocks && !hasTaskPlan) {
    content = snapshot.blocks
      .map((b: WorkspaceBlock) => {
        if (b.type === 'summary') return (b.description || b.title || '').trim();
        if (b.type === 'text') return (b.content || '').trim();
        if (b.type === 'analysis') return (b.content || '').trim();
        if (b.type === 'log') return (b.content || '').trim();
        return '';
      })
      .filter(Boolean)
      .join('\n\n');
  }

  const now = Date.now();
  const stats: AnalysisResultStats = {};
  if (state.resultStartTime) stats.durationMs = now - state.resultStartTime;
  // Internal layout-routing signals (see AnalysisResultStats doc).
  if (state.toolCallCount) stats.toolCallCount = state.toolCallCount;
  if (state.sandboxRunCount) stats.sandboxRunCount = state.sandboxRunCount;

  // Task-stats profile (security / research) produced by backend conclusion.meta.
  const meta = state.statsMeta;
  if (meta?.taskKind) {
    stats.taskKind = meta.taskKind;
    if (meta.security) stats.security = meta.security;
    if (meta.research) stats.research = meta.research;
  }

  const assistantMsg: ConversationMessage = {
    id: `assistant-${now}`,
    type: 'assistant',
    content: content ?? '',
    reasoning: reasoning || '',
    blocks: snapshot.blocks,
    timestamp: new Date(),
    thinkingDuration,
    taskPlan: snapshot.taskPlan as TaskPlan | null | undefined,
    taskPlansSubagent: snapshot.taskPlansSubagent as Record<string, TaskPlan | null> | undefined,
    understanding: snapshot.understanding as InputUnderstanding | null | undefined,
    taskSummary: snapshot.taskSummary,
    timeline: snapshot.timeline,
    requestId: (state.completedRequestId || state.currentRequestId || '').trim() || undefined,
    stats: Object.keys(stats).length > 0 ? stats : undefined,
    workspaceTabs: cloneSnapshot(state.workspaceTabs ?? []),
  };

  return [userMsg, assistantMsg];
}
