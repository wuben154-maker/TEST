import { useRef, useCallback } from 'react';
import { logger } from '@/lib/logger';
import { WorkspaceBlock, TaskPlan, InputUnderstanding, AnalysisTimelineEntry, WorkspaceTabInstance } from '@/types/analysis';
import {
  aggregateReasoningFromTimeline,
  getTimelineErrorDetail,
  timelineHasError,
} from '@/lib/timelineDisplay';
import { taskPlanHasStartedExecution } from '@/lib/analysisWorkspaceChrome';
import { ConversationMessage, AnalysisResult } from '@/types/project';

interface PersistenceState {
  userInput: string;
  requestId?: string;
  inputTimestamp: Date | undefined;
  currentReasoning: string;
  blocks: WorkspaceBlock[];
  thinkingStartTime?: Date;
  taskPlanMain?: TaskPlan | null;
  taskPlansSubagent?: Record<string, TaskPlan | null>;
  understanding?: InputUnderstanding | null;
  taskSummary?: string;
  conclusion?: string;
  timeline?: AnalysisTimelineEntry[];
  workspaceTabs?: WorkspaceTabInstance[];
  resultStartTime?: number;
  toolCallCount?: number;
  sandboxRunCount?: number;
}

interface UseConversationPersistenceOptions {
  currentProjectId: string | null;
  updateProjectBlocks: (projectId: string, blocks: WorkspaceBlock[]) => void;
  /**
   * Append messages to local conversation history (UI-only, instant)
   */
  appendToConversation: (projectId: string, messages: ConversationMessage[]) => void;
  /** Kept for API compat; stream completion syncs tabs in appendToConversation. */
  addAnalysisResult: (projectId: string, result: AnalysisResult) => void;
  /** Clear live panel for a project without aborting (per-project for multi-session). */
  resetForProject: (projectId: string) => void;
}

/**
 * Simplified persistence hook: append-only mode.
 * When analysis finishes, immediately append to conversation (no re-render).
 * Then save to DB in background.
 */
export function useConversationPersistence({
  currentProjectId,
  updateProjectBlocks,
  appendToConversation,
  addAnalysisResult,
  resetForProject,
}: UseConversationPersistenceOptions) {
  const lastSavedByProjectRef = useRef<Map<string, string>>(new Map());
  const isSavingRef = useRef(false);
  const prevAnalyzingRef = useRef(false);

  // Deep-clone streaming state before resetting the live panel.
  // This prevents “history turns” from losing their content if any nested objects were shared.
  const cloneSnapshot = useCallback(<T,>(value: T): T => {
    if (value === null || value === undefined) return value;
    try {
      // Modern browsers
      return structuredClone(value);
    } catch {
      // Fallback for environments without structuredClone
      return JSON.parse(JSON.stringify(value)) as T;
    }
  }, []);

  /** Persist analysis result for a project. When skipAppendAndReset, only DB save (append+reset done by caller). */
  const persistProjectAnalysis = useCallback((projectId: string, state: PersistenceState, options?: { skipAppendAndReset?: boolean }): boolean => {
    const skipAppendAndReset = options?.skipAppendAndReset === true;
    const fallbackKey = [
      state.inputTimestamp?.getTime() ?? 0,
      state.timeline?.length ?? 0,
      state.conclusion ?? '',
      state.taskSummary ?? '',
    ].join(':');
    const persistenceKey = (state.requestId && state.requestId.trim())
      || (state.userInput && state.userInput.trim())
      || fallbackKey;

    const lastSaved = lastSavedByProjectRef.current.get(projectId);
    if (persistenceKey === lastSaved) return false;

    // Do NOT block on isSavingRef - allow concurrent appends so each request gets persisted.
    // lastSavedByProjectRef handles deduplication; async addMessage can run in parallel.
    isSavingRef.current = true;
    lastSavedByProjectRef.current.set(projectId, persistenceKey);

    // Calculate thinking duration from start time
    const thinkingDuration = state.thinkingStartTime 
      ? Math.round((Date.now() - state.thinkingStartTime.getTime()) / 1000)
      : undefined;

    // Capture snapshot including task execution state (deep-cloned)
    const snapshot = {
      userInput: state.userInput,
      inputTimestamp: state.inputTimestamp,
      currentReasoning: state.currentReasoning,
      blocks: cloneSnapshot(state.blocks),
      thinkingDuration,
      taskPlanMain: cloneSnapshot(state.taskPlanMain),
      taskPlansSubagent: cloneSnapshot(state.taskPlansSubagent ?? {}),
      understanding: cloneSnapshot(state.understanding),
      taskSummary: state.taskSummary,
      conclusion: state.conclusion,
      timeline: cloneSnapshot(state.timeline ?? []),
      // workspace-task-panel live state — must be captured for stats bar + dynamic tabs
      workspaceTabs: cloneSnapshot(state.workspaceTabs ?? []),
      resultStartTime: state.resultStartTime,
      toolCallCount: state.toolCallCount ?? 0,
      sandboxRunCount: state.sandboxRunCount ?? 0,
    };

    const timelineReasoning = aggregateReasoningFromTimeline(snapshot.timeline);
    const hasReasoning = !!timelineReasoning || !!snapshot.currentReasoning;
    const hasBlocks = snapshot.blocks.length > 0;
    // Mirror buildConversationMessages: only count as "agentic turn" when at least one
    // task has started. A plan whose tasks are all still `pending` (HITL hit right
    // after planning, user replied conversationally) carries no analysis output.
    const hasTaskPlan =
      taskPlanHasStartedExecution(snapshot.taskPlanMain) ||
      Object.values(snapshot.taskPlansSubagent ?? {}).some((pl) => taskPlanHasStartedExecution(pl));
    const hasUnderstanding = !!snapshot.understanding;
    const hasTaskSummary = !!snapshot.taskSummary;
    const hasConclusion = !!snapshot.conclusion;
    const hasTimeline = (snapshot.timeline?.length ?? 0) > 0;
    const hasError = timelineHasError(snapshot.timeline);
    const errorDetail = getTimelineErrorDetail(snapshot.timeline);

    if (
      !hasReasoning &&
      !hasBlocks &&
      !hasTaskPlan &&
      !hasUnderstanding &&
      !hasTaskSummary &&
      !hasConclusion &&
      !hasTimeline
    ) {
      isSavingRef.current = false;
      return false;
    }

    // After finishing, we append a snapshot turn to the conversation history.
    // Then we reset the live streaming panel so the UI becomes purely append-only
    // (i.e. "append to the end" instead of replacing the existing execution trace).

    // === Append to local conversation for seamless UI ===
    const userMsg: ConversationMessage = {
      id: `user-${Date.now()}`,
      type: 'user',
      content: snapshot.userInput || '[Attachment-only request]',
      timestamp: snapshot.inputTimestamp || new Date(),
    };

    // content = chat reply (conclusion/summary); reasoning = actual thinking process (never conclusion)
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

    // Match buildConversationMessages: no duplicate SSE conclusion into chat for task_plan turns.

    if (!content && hasError) {
      content = `分析失败: ${errorDetail || '未知错误（请查看后端日志）'}`;
    } else if (!content && hasUnderstanding) {
      const u = snapshot.understanding as any;
      const alternatives = Array.isArray(u?.suggestedAlternatives)
        ? u.suggestedAlternatives
        : [];
      const isOutOfScope = u?.taskCategory === 'unknown' && alternatives.length > 0;

      if (isOutOfScope) {
        const optionLines = alternatives.map((alt: any) => {
          const option = alt?.option ?? '-';
          const title = alt?.title ?? '';
          const desc = alt?.description ?? '';
          return `${option}. ${title}\n${desc}`;
        });
        content = `${u.summary || '此请求超出系统能力范围。'}\n\n你可以尝试以下方向：\n${optionLines.join('\n\n')}`;
      } else if (u?.summary) {
        content = u.summary;
      }
    } else if (!content && !hasTimeline && !hasBlocks && !hasTaskPlan) {
      logger.warn('persistence_fallback_interrupted', {
        request_id: state.requestId || '',
        user_input_length: snapshot.userInput.length,
        has_reasoning: hasReasoning,
        has_blocks: hasBlocks,
        hasTaskPlan,
        hasUnderstanding,
        hasTaskSummary,
        hasConclusion,
        hasError,
        timelineLen: snapshot.timeline?.length ?? 0,
      });
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

    const assistantMsg: ConversationMessage = {
      id: `assistant-${Date.now()}`,
      type: 'assistant',
      content: content?.slice(0, 500) || '',
      reasoning: reasoning || '',
      blocks: snapshot.blocks,
      timestamp: new Date(),
      thinkingDuration: snapshot.thinkingDuration,
      taskPlan: snapshot.taskPlanMain,
      taskPlansSubagent: snapshot.taskPlansSubagent,
      understanding: snapshot.understanding,
      taskSummary: snapshot.taskSummary,
      timeline: snapshot.timeline ?? [],
      requestId: (state.requestId || '').trim() || undefined,
    };

    if (!skipAppendAndReset) {
      appendToConversation(projectId, [userMsg, assistantMsg]);
      resetForProject(projectId);
    }

    // Workspace result tabs: streaming already called `appendToConversation` with the
    // canonical assistant message (same id as chat). That path merges `analysisResults`.
    // Avoid `addAnalysisResult` here (duplicate id / wrong id vs chat, and skipped when persist dedupes).

    // Save blocks if we have them
    if (hasBlocks) {
      updateProjectBlocks(projectId, snapshot.blocks);
    }

    // DB persistence is handled by backend message_persistence (single writer).
    // Keep frontend append-only for instant UI updates and avoid duplicate writes.
    isSavingRef.current = false;

    return true;
  }, [updateProjectBlocks, appendToConversation, resetForProject]);

  /** For single-session: trigger when isAnalyzing transitions true->false. */
  const onAnalysisStateChange = useCallback((isAnalyzing: boolean, state: PersistenceState): boolean => {
    const wasAnalyzing = prevAnalyzingRef.current;
    prevAnalyzingRef.current = isAnalyzing;
    if (!wasAnalyzing || isAnalyzing) return false;
    if (!currentProjectId) return false;
    return persistProjectAnalysis(currentProjectId, state);
  }, [currentProjectId, persistProjectAnalysis]);

  const resetPersistence = useCallback(() => {
    lastSavedByProjectRef.current.clear();
    prevAnalyzingRef.current = false;
    isSavingRef.current = false;
  }, []);

  return {
    onAnalysisStateChange,
    persistProjectAnalysis,
    resetPersistence,
  };
}
