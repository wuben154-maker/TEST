/**
 * Multi-session streaming analysis hook.
 * Each project maintains independent streaming state; switching projects does not abort or reset.
 */
import { useCallback, useEffect, useRef } from 'react';
import type {
  ThinkingEvent,
  WorkspaceBlock,
  StreamingAnalysisResult,
  AgentTask,
  DecisionRequest,
  InputUnderstanding,
  ParameterRequest,
  TaskPlan,
  PlannedTask,
  TaskStep,
  NextAction,
  SSEEventLog,
  AnalysisMode,
  AnalyzeAttachment,
} from '@/types/analysis';
import type { PerProjectStreamingState } from '@/types/streaming';
import { createEmptyStreamingState } from '@/types/streaming';
import { createEmptyContextUsageState, getMainUsageSnapshot } from '@/lib/contextUsage';
import { loadContextUsagePayload } from '@/lib/contextUsagePersistence';
import { flushNow } from '@/lib/contextUsageSync';
import { pickNewerContextUsage } from '@/lib/contextUsage';
import { projectsApi } from '@/lib/api-client';
import type { ContextUsageState } from '@/types/analysis';
import { buildConversationMessages } from '@/lib/buildConversationMessages';
import { appendToAnalysisTimeline } from '@/lib/timelineReducer';
import type { ConversationMessage } from '@/types/project';
import { analysisEndpoints } from '@/lib/config';
import { getLastSelectedModelIdForApi } from '@/lib/lastSelectedModel';
import { getAuthToken, analysisApi, getClientTimezoneHeaders } from '@/lib/api-client';
import { parseAnalyzeHttpError } from '@/lib/parseAnalyzeHttpError';
import { logger } from '@/lib/logger';
import { toast } from 'sonner';
import { getTranslations, type Language } from '@/i18n';
import { useStreamingStateContext } from '@/contexts/StreamingStateContext';
import { formatUserMessageForChat } from '@/lib/formatUserMessageDisplay';
import { unwrapStructuredUserPrompt } from '@/lib/unwrapStructuredUserPrompt';
import { readSseJsonLines } from '@/lib/sse/readSseJsonLines';
import { parseAnalysisEvent } from '@/lib/sse/parseAnalysisEvent';
import {
  handleMultiAnalyzeStreamEvent,
  type MultiStreamEventCtx,
  type MultiStreamProgressFlags,
} from '@/hooks/multiAnalyzeStreamEvents';
import {
  isMainTaskPlanScope,
  mergeTaskPlanBucket,
  mapTaskInPlan,
  subagentTaskPlanMapKey,
} from '@/lib/taskPlanScope';
import {
  scrubTaskPlanPathsForDisplay,
  scrubVirtualPathsForDisplay,
} from '@/lib/scrubVirtualPathsForDisplay';
import { buildHitlResumeFromDecision } from '@/lib/hitlResumePayload';
import { clearHitlSubmittedParams, saveHitlSubmittedParams } from '@/lib/hitlSubmittedParamsStorage';
import { stripLeadingPrefaceBeforeCjkReportBody } from '@/lib/stripCjkReportPreface';
import {
  loadToolTabConfig,
  resolveTabAction,
} from '@/lib/tool-tab-registry';
import type { WorkspaceTabConfig } from '@/types/analysis';

const STREAM_URL = analysisEndpoints.stream;
type SupportedLanguage = Language;

/** POST /analyze/resume: persisted to ``timeline`` as ``decision_response``; not sent to LangGraph as ``resume``. */
export type HitlResumeTimelineContext =
  | { decisionUiId: string; selectedOptions: string[] }
  | undefined;

const createRequestId = (): string => {
  if (typeof crypto !== 'undefined' && typeof crypto.randomUUID === 'function') {
    return crypto.randomUUID();
  }
  return `req-${Date.now()}-${Math.random().toString(36).slice(2, 10)}`;
};

/**
 * Defer only conversation append + persist. Live streaming state must be
 * cleared synchronously (with `isAnalyzing: false`) in the same React batch as
 * `updateState`; deferring `resetForProject` created a window where
 * `reloadProjectMessages` could already show the turn in history while the live
 * column still rendered the same Q&A (duplicate), or progress-restore could clear
 * the panel before history updated (flash empty). Heavy work in
 * `persistProjectAnalysis` still runs here so the submit control is not blocked.
 */
function deferPostStreamFinalize(run: () => void): void {
  setTimeout(run, 0);
}

export type { AnalyzeAttachment } from '@/types/analysis';

function serializeAttachmentsForAnalyze(attachments: AnalyzeAttachment[]) {
  return attachments.map((a) => {
    const row: Record<string, unknown> = {
      filename: a.filename,
      content_type: a.content_type,
      size: a.size,
    };
    if (a.hash_sha256) {
      row.hash_sha256 = a.hash_sha256;
    }
    if (a.file_path) {
      row.file_path = a.file_path;
      if (a.sha256) {
        row.sha256 = a.sha256;
      } else if (a.hash_sha256) {
        row.sha256 = a.hash_sha256;
      }
    } else {
      row.content = a.content ?? '';
    }
    return row;
  });
}

export interface UseStreamingAnalysisMultiOptions {
  currentProjectId: string | null;
  /** Append completed turn to conversation history (called directly, no callback chain). */
  appendToConversation: (projectId: string, messages: ConversationMessage[]) => void;
  /** Clear live panel for project after append. */
  resetForProject: (projectId: string) => void;
  /** Optional: persist to DB (addMessage, etc.). */
  onProjectAnalysisComplete?: (projectId: string, state: PerProjectStreamingState) => void;
  /**
   * Open the post-stream quiet window and tear down analysis-progress polling
   * **before** clearing the abort handle. If this only ran inside deferred
   * `onProjectAnalysisComplete`, `isLocallyStreaming` would flip false first,
   * restore bootstrap could run and call `reloadProjectMessages` — the chat /
   * report "second refresh" a few seconds after the turn.
   */
  stopProgressRestorePolling?: (projectId: string) => void;
  /**
   * App UI locale (i18n). Used for SSE/step labels on /analyze/resume only.
   * Model reply language is derived from user message text on the server.
   */
  uiLanguage?: SupportedLanguage;
}

export function useStreamingAnalysisMulti(options: UseStreamingAnalysisMultiOptions) {
  const {
    currentProjectId,
    appendToConversation,
    resetForProject,
    onProjectAnalysisComplete,
    stopProgressRestorePolling,
    uiLanguage = 'zh',
  } = options;
  const onProjectAnalysisCompleteRef = useRef(onProjectAnalysisComplete);
  onProjectAnalysisCompleteRef.current = onProjectAnalysisComplete;
  const stopProgressRestorePollingRef = useRef(stopProgressRestorePolling);
  stopProgressRestorePollingRef.current = stopProgressRestorePolling;
  const {
    updateState,
    getLatestState,
    clearState,
    removeState,
    getAbortController,
    setAbortController,
  } = useStreamingStateContext();

  const isMountedRef = useRef(true);
  /** Cached workspace_tab config from backend (loaded once per session). */
  const toolTabConfigRef = useRef<Record<string, WorkspaceTabConfig>>({});
  const toolTabConfigLoadedRef = useRef(false);
  /** Captures taskSummary/conclusion/blocks before React state flushes; merged in finally. */
  const pendingStateRef = useRef<Map<string, { taskSummary?: string; conclusion?: string; blocks?: WorkspaceBlock[] }>>(new Map());
  const projectRefsRef = useRef<Map<string, {
    hasTaskPlan: boolean;
    hasResearchRoute: boolean;
    activeRequestId: string;
    /** Original POST /analyze request_id for this leg (HITL storage + progress_request_id). */
    progressCorrelationRequestId: string;
    pendingRequestId: string;
    pendingInput: string;
    pendingLanguage: SupportedLanguage;
    timelineLocalSeq: number;
  }>>(new Map());

  const getProjectRefs = useCallback((projectId: string) => {
    let refs = projectRefsRef.current.get(projectId);
    if (!refs) {
      refs = {
        hasTaskPlan: false,
        hasResearchRoute: false,
        activeRequestId: '',
        progressCorrelationRequestId: '',
        pendingRequestId: '',
        pendingInput: '',
        pendingLanguage: 'zh',
        timelineLocalSeq: 0,
      };
      projectRefsRef.current.set(projectId, refs);
    }
    return refs;
  }, []);

  /** Resolves POST /analyze/resume ``ui_language`` (SSE labels), not model output language. */
  const resolveHitlResumeUiLanguage = useCallback(
    (projectId: string, override?: SupportedLanguage): SupportedLanguage => {
      if (override) return override;
      const refs = getProjectRefs(projectId);
      return refs.pendingLanguage ?? uiLanguage;
    },
    [getProjectRefs, uiLanguage],
  );

  useEffect(() => {
    // React 18 Strict Mode (dev) runs mount → unmount → remount once; ref updates survive.
    // Cleanup-only `false` without resetting `true` here leaves `isMountedRef` stuck false after
    // the simulated unmount, so `shouldAbort` short-circuits every SSE read (dead stream).
    isMountedRef.current = true;
    return () => {
      isMountedRef.current = false;
    };
  }, []);

  /**
   * Rehydrate persisted context-usage when the active project changes.
   *
   * Two-source "newer wins" strategy (2026-04-19 backend-persistence
   * increment):
   *
   *   1. Read localStorage synchronously — this is the hot-cache that
   *      survives hard reloads with zero latency.
   *   2. Fire off a `GET /projects/:id` and read `context_usage` +
   *      `context_usage_updated_at` from the response — this is the
   *      authoritative source and survives cross-device access.
   *   3. Pick the branch with the newer timestamp. If only one side
   *      has data, that one wins. If neither has data, leave the ring
   *      hidden (no change).
   *
   * Runs once per project (tracked via a ref set) so we don't clobber a
   * fresher in-memory value with a stale snapshot after a streaming
   * update has already landed.
   */
  const hydratedProjectsRef = useRef<Set<string>>(new Set());
  useEffect(() => {
    if (!currentProjectId) return;
    if (hydratedProjectsRef.current.has(currentProjectId)) return;
    hydratedProjectsRef.current.add(currentProjectId);
    const targetProjectId = currentProjectId;

    const localPayload = loadContextUsagePayload(targetProjectId);

    const applyState = (state: ContextUsageState) => {
      const hasAny =
        getMainUsageSnapshot(state) ||
        (state.latestSubagentByName && Object.keys(state.latestSubagentByName).length > 0) ||
        (state.cumulative?.invocations ?? 0) > 0;
      if (!hasAny) return;
      updateState(targetProjectId, (prev) => {
        // Protect against a race with a freshly arrived `llm_invoke_end`
        // that already populated in-memory state. If the in-memory value
        // has a newer main-snapshot `endedAt` than the hydrate candidate, keep
        // it.
        const prevSnap = prev.contextUsage
          ? getMainUsageSnapshot(prev.contextUsage)
          : undefined;
        const candSnap = getMainUsageSnapshot(state);
        const prevEndedAt = prevSnap?.endedAt;
        const candEndedAt = candSnap?.endedAt;
        if (
          typeof prevEndedAt === 'number' &&
          typeof candEndedAt === 'number' &&
          prevEndedAt >= candEndedAt
        ) {
          return prev;
        }
        if (prev.contextUsage && getMainUsageSnapshot(prev.contextUsage) && !candEndedAt) {
          return prev;
        }
        return { ...prev, contextUsage: state };
      });
    };

    // Eagerly apply localStorage if present so the ring shows up with
    // zero network latency; the backend fetch below will overwrite only
    // when it's strictly newer (via ``pickNewerContextUsage``).
    if (
      localPayload?.state &&
      (getMainUsageSnapshot(localPayload.state) ||
        (localPayload.state.latestSubagentByName &&
          Object.keys(localPayload.state.latestSubagentByName).length > 0))
    ) {
      applyState(localPayload.state);
    }

    // Kick off backend fetch in parallel; we'll pick the winner once
    // both sources are in hand.
    let cancelled = false;
    (async () => {
      let backendArg:
        | { state: ContextUsageState; updatedAt: number }
        | null = null;
      try {
        const { data } = await projectsApi.get(targetProjectId);
        const raw = data as {
          context_usage?: {
            v?: number;
            state?: ContextUsageState;
            updatedAt?: number;
          } | null;
          context_usage_updated_at?: string | null;
        } | null;
        const payload = raw?.context_usage ?? null;
        if (payload && payload.state) {
          // Prefer the payload-embedded ``updatedAt`` (epoch ms, client-
          // stamped, full precision). Fall back to the server-stamped
          // ``context_usage_updated_at`` (ISO, second precision).
          let updatedAt = 0;
          if (typeof payload.updatedAt === 'number') {
            updatedAt = payload.updatedAt;
          } else if (raw?.context_usage_updated_at) {
            const t = Date.parse(raw.context_usage_updated_at);
            updatedAt = Number.isFinite(t) ? t : 0;
          }
          backendArg = { state: payload.state, updatedAt };
        }
      } catch {
        // Backend unreachable — localStorage (if any) already applied.
      }
      if (cancelled) return;

      const localArg = localPayload ? {
        state: localPayload.state,
        updatedAt: localPayload.updatedAt,
      } : null;
      const winner = pickNewerContextUsage(localArg, backendArg);
      if (winner) applyState(winner.state);
    })();

    return () => {
      cancelled = true;
    };
  }, [currentProjectId, updateState]);

  const effectiveSessionId = currentProjectId ?? `session-${Date.now()}-${Math.random().toString(36).slice(2)}`;

  const logSSEEvent = useCallback((projectId: string, event: ThinkingEvent) => {
    const toPreviewString = (v: unknown): string => {
      if (typeof v === 'string') return v;
      if (v === null || v === undefined) return '';
      try {
        return JSON.stringify(v);
      } catch {
        return String(v);
      }
    };
    let previewSource = '';
    if (event.type === 'debug') {
      const errorMsg = (event as unknown as { error_message?: string }).error_message;
      const errorType = (event as unknown as { error_type?: string }).error_type;
      previewSource = errorMsg
        ? `[${errorType || 'Error'}] ${errorMsg}`
        : toPreviewString(event.label) || toPreviewString(event.detail) || '';
    } else {
      previewSource =
        toPreviewString(event.label) ||
        toPreviewString(event.content) ||
        toPreviewString(event.detail) ||
        '';
    }
    const preview = previewSource.length > 80 ? previewSource.slice(0, 80) + '...' : previewSource;
    const newLog: SSEEventLog = {
      type: event.type,
      id: event.id || 'no-id',
      timestamp: typeof event.timestamp === 'number' ? event.timestamp : Date.now(),
      preview,
      rawData: event as unknown as Record<string, unknown>,
    };
    updateState(projectId, (prev) => ({
      ...prev,
      analysisMode: (event.type === 'task_plan' || event.type === 'task_start' || event.type === 'understanding' || event.type === 'step')
        ? 'deepagent'
        : prev.analysisMode,
      sseEventLogs: [newLog, ...prev.sseEventLogs].slice(0, 30),
    }));
  }, [updateState]);

  const clearSSELogs = useCallback((projectId: string) => {
    updateState(projectId, (prev) => ({ ...prev, sseEventLogs: [] }));
  }, [updateState]);

  const extractFinalResultForDisplay = useCallback((rawContent: string): string => {
    const content = (rawContent || '').trim();
    if (!content) return '';
    const markers = ['## 最终结果', '## Final Result'];
    for (const marker of markers) {
      const idx = content.lastIndexOf(marker);
      if (idx !== -1) {
        const extracted = content.slice(idx + marker.length).trim();
        if (extracted) return stripLeadingPrefaceBeforeCjkReportBody(extracted);
      }
    }
    return stripLeadingPrefaceBeforeCjkReportBody(content);
  }, []);

  const handleTaskCreate = useCallback((projectId: string, event: ThinkingEvent) => {
    if (event.task && 'title' in event.task && !('taskType' in event.task)) {
      updateState(projectId, (prev) => ({
        ...prev,
        tasks: [...prev.tasks, event.task as AgentTask],
      }));
    }
  }, [updateState]);

  const handleTaskUpdate = useCallback((projectId: string, event: ThinkingEvent) => {
    if (event.id && event.taskStatus) {
      updateState(projectId, (prev) => ({
        ...prev,
        tasks: prev.tasks.map((task) =>
          task.id === event.id ? { ...task, status: event.taskStatus! } : task
        ),
      }));
    }
  }, [updateState]);

  const handleDecisionRequest = useCallback((projectId: string, event: ThinkingEvent) => {
    if (event.decision) {
      updateState(projectId, (prev) => ({
        ...prev,
        decisions: [...prev.decisions, event.decision!],
      }));
    }
  }, [updateState]);

  const handleUnderstanding = useCallback((projectId: string, event: ThinkingEvent) => {
    if (event.understanding) {
      const u = event.understanding;
      updateState(projectId, (prev) => ({
        ...prev,
        understanding: u,
        parameterRequests: u.parameterRequests?.length ? u.parameterRequests : prev.parameterRequests,
      }));
    }
  }, [updateState]);

  const handleTaskPlan = useCallback((projectId: string, event: ThinkingEvent) => {
    if (!event.plan) return;
    getProjectRefs(projectId).hasTaskPlan = true;
    const incoming = event.plan as TaskPlan;
    updateState(projectId, (prev) => {
      if (isMainTaskPlanScope(event)) {
        const nextMain = mergeTaskPlanBucket(prev.taskPlanMain, incoming);
        return { ...prev, taskPlanMain: nextMain };
      }
      const key = subagentTaskPlanMapKey(event);
      const prevSub = prev.taskPlansSubagent[key] ?? null;
      const nextSub = mergeTaskPlanBucket(prevSub, incoming);
      return {
        ...prev,
        taskPlansSubagent: { ...prev.taskPlansSubagent, [key]: nextSub },
      };
    });
  }, [updateState, getProjectRefs]);

  const handleTaskStart = useCallback((projectId: string, event: ThinkingEvent) => {
    const taskId = event.id;
    if (!taskId) return;
    updateState(projectId, (prev) => {
      if (isMainTaskPlanScope(event)) {
        if (!prev.taskPlanMain) return { ...prev, currentTaskId: taskId };
        return {
          ...prev,
          currentTaskId: taskId,
          taskPlanMain: mapTaskInPlan(prev.taskPlanMain, taskId, (t) => ({
            ...t,
            status: 'running' as const,
          })),
        };
      }
      const key = subagentTaskPlanMapKey(event);
      const plan = prev.taskPlansSubagent[key];
      if (!plan) return { ...prev, currentTaskId: taskId };
      return {
        ...prev,
        currentTaskId: taskId,
        taskPlansSubagent: {
          ...prev.taskPlansSubagent,
          [key]: mapTaskInPlan(plan, taskId, (t) => ({ ...t, status: 'running' as const })),
        },
      };
    });
  }, [updateState]);

  const handleTaskStep = useCallback((projectId: string, event: ThinkingEvent) => {
    const taskId = event.taskId;
    const step = event.step;
    if (!taskId || !step) return;
    updateState(projectId, (prev) => {
      const applyToPlan = (plan: TaskPlan | null): TaskPlan | null => {
        if (!plan) return null;
        return {
          ...plan,
          tasks: plan.tasks.map((t) => {
            if (t.id !== taskId) return t;
            const existingStepIndex = t.steps.findIndex((s) => s.id === step.id);
            if (existingStepIndex >= 0) {
              return {
                ...t,
                steps: t.steps.map((s, i) => (i === existingStepIndex ? step : s)),
              };
            }
            return { ...t, steps: [...t.steps, step] };
          }),
        };
      };
      if (isMainTaskPlanScope(event)) {
        const next = applyToPlan(prev.taskPlanMain);
        if (!next) return prev;
        return { ...prev, taskPlanMain: next };
      }
      const key = subagentTaskPlanMapKey(event);
      const plan = prev.taskPlansSubagent[key];
      const next = applyToPlan(plan);
      if (!next) return prev;
      return {
        ...prev,
        taskPlansSubagent: { ...prev.taskPlansSubagent, [key]: next },
      };
    });
  }, [updateState]);

  const mergePlannedTask = useCallback((prevTask: PlannedTask, incomingTask: PlannedTask): PlannedTask => {
    const scrub = scrubVirtualPathsForDisplay;
    const incomingSteps = (incomingTask.steps || []).filter(Boolean);
    const prevSteps = (prevTask.steps || []).filter(Boolean);
    const merged: PlannedTask = {
      ...prevTask,
      ...incomingTask,
      result: incomingTask.result ?? prevTask.result,
      error: incomingTask.error ?? prevTask.error,
      durationMs: incomingTask.durationMs || prevTask.durationMs,
      skillName: incomingTask.skillName ?? prevTask.skillName,
      steps: incomingSteps.length > 0 ? incomingSteps : prevSteps,
    };
    return {
      ...merged,
      title: scrub(merged.title),
      description:
        merged.description !== undefined && merged.description !== null
          ? scrub(String(merged.description))
          : merged.description,
      result: merged.result !== undefined && merged.result !== null ? scrub(String(merged.result)) : merged.result,
      error: merged.error !== undefined && merged.error !== null ? scrub(String(merged.error)) : merged.error,
    };
  }, []);

  const handleTaskComplete = useCallback((projectId: string, event: ThinkingEvent) => {
    const taskId = event.id;
    if (!taskId) return;
    updateState(projectId, (prev) => {
      const completeOne = (plan: TaskPlan | null): TaskPlan | null => {
        if (!plan) return null;
        return {
          ...plan,
          tasks: plan.tasks.map((t) => {
            if (t.id !== taskId) return t;
            if (event.task && 'taskType' in event.task) {
              return mergePlannedTask(t, { ...(event.task as PlannedTask), status: 'success' as const });
            }
            return { ...t, status: 'success' as const };
          }),
        };
      };
      if (isMainTaskPlanScope(event)) {
        const next = completeOne(prev.taskPlanMain);
        if (!next) return { ...prev, currentTaskId: undefined };
        return { ...prev, currentTaskId: undefined, taskPlanMain: next };
      }
      const key = subagentTaskPlanMapKey(event);
      const plan = prev.taskPlansSubagent[key];
      const next = completeOne(plan);
      if (!next) return { ...prev, currentTaskId: undefined };
      return {
        ...prev,
        currentTaskId: undefined,
        taskPlansSubagent: { ...prev.taskPlansSubagent, [key]: next },
      };
    });
  }, [updateState, mergePlannedTask]);

  const mergeTaskPlan = useCallback((prevPlan: TaskPlan, incomingPlan: TaskPlan): TaskPlan => {
    const prevClean = scrubTaskPlanPathsForDisplay(prevPlan);
    const incomingClean = scrubTaskPlanPathsForDisplay(incomingPlan);
    const prevById = new Map(prevClean.tasks.map((t) => [t.id, t] as const));
    const incomingIds = new Set(incomingClean.tasks.map((t) => t.id));
    const mergedTasks = incomingClean.tasks.map((t) => {
      const existing = prevById.get(t.id);
      return existing ? mergePlannedTask(existing, t) : t;
    });
    const extras = prevClean.tasks.filter((t) => !incomingIds.has(t.id));
    return {
      ...prevClean,
      ...incomingClean,
      totalDurationMs: incomingClean.totalDurationMs || prevClean.totalDurationMs,
      tasks: [...mergedTasks, ...extras],
    };
  }, [mergePlannedTask]);

  const handlePlanComplete = useCallback((projectId: string, event: ThinkingEvent) => {
    if (!event.plan) return;
    const incoming = scrubTaskPlanPathsForDisplay(event.plan as TaskPlan);
    updateState(projectId, (prev) => {
      if (isMainTaskPlanScope(event)) {
        const next = prev.taskPlanMain ? mergeTaskPlan(prev.taskPlanMain, incoming) : incoming;
        return { ...prev, taskPlanMain: next };
      }
      const key = subagentTaskPlanMapKey(event);
      const prevSub = prev.taskPlansSubagent[key] ?? null;
      const nextSub = prevSub ? mergeTaskPlan(prevSub, incoming) : incoming;
      return {
        ...prev,
        taskPlansSubagent: { ...prev.taskPlansSubagent, [key]: nextSub },
      };
    });
  }, [updateState, mergeTaskPlan]);

  const handleParameterRequest = useCallback((projectId: string, event: ThinkingEvent) => {
    if (event.parameterRequests && event.parameterRequests.length > 0) {
      const refs = getProjectRefs(projectId);
      const interruptRid = String(
        (event as ThinkingEvent & { interruptRequestId?: string }).interruptRequestId || '',
      ).trim();
      if (interruptRid || event.id || event.requestId) {
        refs.pendingRequestId = interruptRid || event.id || event.requestId;
      }
      updateState(projectId, (prev) => ({
        ...prev,
        parameterRequests: event.parameterRequests!,
        parameterRequestDetail: typeof event.detail === 'string' ? event.detail : undefined,
        hitlParametersSubmitted: false,
      }));
    }
  }, [updateState, getProjectRefs]);

  const processConclusion = useCallback((projectId: string, content: string, input: string, lang: SupportedLanguage) => {
    const live = getLatestState(projectId);
    const refs = getProjectRefs(projectId);
    const hasTaskPlan = refs.hasTaskPlan;
    const hasResearchRoute = refs.hasResearchRoute;
    // Keep simple/direct answers in chat-only mode, but allow research route
    // to generate blocks even without task_plan/workspace events.
    if (!hasTaskPlan && !hasResearchRoute) return;
    const text = getTranslations(lang).streaming;
    const newBlocks: WorkspaceBlock[] = [];
    let result: StreamingAnalysisResult | null = null;
    try {
      result = JSON.parse(content);
    } catch {
      /* not JSON */
    }
    if (result) {
      newBlocks.push({
        type: 'summary',
        id: 'summary-1',
        severity: result.severity || 'info',
        title: result.title || text.analysisReport,
        description: result.summary || text.analysisComplete,
      });
      newBlocks.push({
        type: 'text',
        id: 'heading-evidence',
        content: text.originalEvidence,
        variant: 'heading',
      });
      const highlights: { start: number; end: number; type: 'ip' | 'url' | 'payload' }[] = [];
      result.entities?.ips?.forEach((ip) => {
        const idx = input.indexOf(ip);
        if (idx !== -1) highlights.push({ start: idx, end: idx + ip.length, type: 'ip' });
      });
      result.entities?.urls?.forEach((url) => {
        const idx = input.indexOf(url);
        if (idx !== -1) highlights.push({ start: idx, end: idx + url.length, type: 'url' });
      });
      ['${jndi:', 'eval(', '<script', 'base64,'].forEach((pattern) => {
        let searchStart = 0;
        while (true) {
          const idx = input.indexOf(pattern, searchStart);
          if (idx === -1) break;
          highlights.push({ start: idx, end: idx + pattern.length + 20, type: 'payload' });
          searchStart = idx + 1;
        }
      });
      newBlocks.push({ type: 'log', id: 'log-original', content: input, highlights });
      if (result.decodings?.length) {
        newBlocks.push({ type: 'text', id: 'heading-decode', content: text.decodingAnalysis, variant: 'heading' });
        result.decodings.forEach((d, idx) =>
          newBlocks.push({
            type: 'decoder',
            id: `decoder-${idx}`,
            encoded: d.encoded,
            decoded: d.decoded,
            algorithm: d.algorithm,
          })
        );
      }
      const allIndicators = [
        ...(result.entities?.ips || []),
        ...(result.entities?.domains || []),
        ...(result.entities?.hashes || []),
      ];
      if (allIndicators.length > 0) {
        newBlocks.push({ type: 'text', id: 'heading-intel', content: text.threatIntelligence, variant: 'heading' });
        allIndicators.slice(0, 10).forEach((indicator, idx) => {
          let indicatorType: 'ip' | 'domain' | 'hash' = 'domain';
          if (result?.entities?.ips?.includes(indicator)) indicatorType = 'ip';
          else if (result?.entities?.hashes?.includes(indicator)) indicatorType = 'hash';
          let threatScore: 'high' | 'medium' | 'low' | 'clean' = 'clean';
          if (result?.severity === 'critical' || result?.severity === 'high') threatScore = 'high';
          else if (result?.severity === 'medium') threatScore = 'medium';
          newBlocks.push({
            type: 'intel',
            id: `intel-${idx}`,
            indicator,
            indicatorType,
            threatScore,
            tags: result?.intelTags?.slice(0, 5),
          });
        });
      }
      if (result.attackPatterns?.length) {
        newBlocks.push({ type: 'text', id: 'heading-patterns', content: text.attackPatterns, variant: 'heading' });
        result.attackPatterns.forEach((p, idx) =>
          newBlocks.push({ type: 'text', id: `pattern-${idx}`, content: p, variant: 'bullet' })
        );
      }
      if (result.threatIndicators?.length) {
        newBlocks.push({ type: 'text', id: 'heading-threats', content: text.threatIndicators, variant: 'heading' });
        result.threatIndicators.forEach((t, idx) =>
          newBlocks.push({ type: 'text', id: `threat-${idx}`, content: t, variant: 'bullet' })
        );
      }
      if (result.recommendations?.length) {
        newBlocks.push({ type: 'text', id: 'heading-action', content: text.recommendations, variant: 'heading' });
        result.recommendations.forEach((r, idx) =>
          newBlocks.push({ type: 'text', id: `rec-${idx}`, content: r, variant: 'bullet' })
        );
      }
      if (result.fullAnalysis) {
        newBlocks.push({
          type: 'analysis',
          id: 'full-analysis',
          content: result.fullAnalysis,
          title: text.deepAgentDetailedAnalysis,
        });
      }
    } else if (content?.trim()) {
      newBlocks.push({
        type: 'analysis',
        id: 'full-analysis',
        content: extractFinalResultForDisplay(content),
        title: text.analysisReportTitle,
      });
    }
    if (newBlocks.length > 0) {
      const prev = pendingStateRef.current.get(projectId) ?? {};
      pendingStateRef.current.set(projectId, { ...prev, blocks: newBlocks });
      updateState(projectId, (prevState) => ({ ...prevState, blocks: newBlocks }));
    }
  }, [updateState, getProjectRefs, extractFinalResultForDisplay, getLatestState]);

  /** Apply workspace tab / stats tracking for a single tool_call SSE event. */
  const applyWorkspaceTabEvent = useCallback(
    (projectId: string, event: { type: string; toolName?: string; toolInput?: Record<string, unknown>; scope?: string }) => {
      if (event.type !== 'tool_call') return;
      const toolName = event.toolName ?? '';
      if (!toolName) return;
      updateState(projectId, (p) => {
        const newToolCallCount = p.toolCallCount + 1;
        const newSandboxRunCount = p.sandboxRunCount + (toolName.startsWith('sandbox_') ? 1 : 0);
        // Ensure we have the start time
        const startTime = p.resultStartTime ?? Date.now();
        const toolArgs = (event.toolInput ?? {}) as Record<string, unknown>;
        const action = resolveTabAction(toolName, toolArgs, p.workspaceTabs, toolTabConfigRef.current);
        if (!action) {
          return { ...p, toolCallCount: newToolCallCount, sandboxRunCount: newSandboxRunCount, resultStartTime: startTime };
        }
        if (action.action === 'append') {
          return { ...p, toolCallCount: newToolCallCount, sandboxRunCount: newSandboxRunCount, resultStartTime: startTime };
        }
        const { initialData, ...tabMeta } = action.tabConfig;
        const newTab = { ...tabMeta, data: initialData };
        return {
          ...p,
          toolCallCount: newToolCallCount,
          sandboxRunCount: newSandboxRunCount,
          resultStartTime: startTime,
          workspaceTabs: [...p.workspaceTabs, newTab],
        };
      });
    },
    [updateState]
  );

  const analyzeInput = useCallback(
    async (
      projectId: string,
      input: string,
      appendMode: boolean = false,
      language: SupportedLanguage = 'en',
      attachments: AnalyzeAttachment[] = [],
      modelId?: string
    ) => {
      const messageText = unwrapStructuredUserPrompt(input);
      const requestId = createRequestId();
      const refs = getProjectRefs(projectId);
      // Tear down restore/bootstrap progress polling synchronously whenever the
      // frontend owns a fresh SSE attempt — avoids a late periodic tick or
      // in-flight GET /analysis-progress calling reloadProjectMessages a few
      // seconds after a turn settles (conversation column "reload" flash).
      stopProgressRestorePollingRef.current?.(projectId);
      const supersededRequestId = refs.activeRequestId;
      // Append superseded request before overwriting state (its finally would skip due to activeRequestId mismatch)
      if (supersededRequestId) {
        const stateToAppend = getLatestState(projectId);
        const msgs = buildConversationMessages({ ...stateToAppend, currentRequestId: supersededRequestId });
        if (msgs) {
          const pid = projectId;
          const stateForPersist: PerProjectStreamingState = {
            ...stateToAppend,
            currentRequestId: supersededRequestId,
          };
          resetForProject(pid);
          deferPostStreamFinalize(() => {
            if (!isMountedRef.current) return;
            appendToConversation(pid, msgs);
            const onComplete = onProjectAnalysisCompleteRef.current;
            if (onComplete)
              onComplete(pid, { ...stateForPersist, completedRequestId: supersededRequestId });
          });
        }
      }
      refs.activeRequestId = requestId;
      refs.progressCorrelationRequestId = requestId;
      refs.timelineLocalSeq = 0;
      refs.hasTaskPlan = false;
      refs.hasResearchRoute = false;
      pendingStateRef.current.delete(projectId);
      refs.pendingInput = messageText;
      refs.pendingLanguage = language;

      const sessionId = projectId ?? effectiveSessionId;

      updateState(projectId, (prev) => ({
        ...prev,
        currentRequestId: requestId,
        isAnalyzing: true,
        taskPlanMain: null,
        taskPlansSubagent: {},
        currentTaskId: undefined,
        taskSummary: '',
        nextActions: [],
        understanding: null,
        conclusion: '',
        blocks: [],
        currentReasoning: '',
        timeline: [],
        userInput: formatUserMessageForChat(messageText, attachments),
        attachments:
          attachments.length > 0
            ? attachments.map((a) => ({
                filename: a.filename,
                size: a.size,
                file_path: a.file_path,
              }))
            : undefined,
        inputTimestamp: new Date(),
        thinkingStartTime: new Date(),
        hitlAwaiting: false,
        hitlSnapshot: null,
        hitlProgressRequestId: undefined,
        hitlParametersSubmitted: false,
        submittedParameters: {},
        workspaceTabs: [],
        resultStartTime: Date.now(),
        toolCallCount: 0,
        sandboxRunCount: 0,
        // Context usage is sticky across turns (append or fresh) so the ring
        // never disappears after a new query — it only re-fills when the next
        // llm_invoke_end arrives. prev.contextUsage will be empty on the very
        // first turn for a freshly opened project, which is fine.
        contextUsage: prev.contextUsage ?? createEmptyContextUsageState(),
        ...(appendMode ? {} : { tasks: [], decisions: [], resolvedDecisions: {}, parameterRequests: [] }),
      }));

      // Load workspace tab config once (lazy); failures are silent — no tabs generated.
      if (!toolTabConfigLoadedRef.current) {
        toolTabConfigLoadedRef.current = true;
        loadToolTabConfig().then((cfg) => {
          toolTabConfigRef.current = cfg;
        });
      }

      const controller = new AbortController();
      setAbortController(projectId, controller);

      const currentLang = language;

      const flags: MultiStreamProgressFlags = {
        sawConclusionEvent: false,
        sawErrorEvent: false,
        sawDoneEvent: false,
        sawHitlAwaiting: false,
      };
      const streamCtx: MultiStreamEventCtx = {
        logSSEEvent,
        getProjectRefs,
        updateState,
        pendingStateRef,
        handleTaskPlan,
        handleTaskCreate,
        handleTaskUpdate,
        handleDecisionRequest,
        handleUnderstanding,
        handleParameterRequest,
        handleTaskStart,
        handleTaskStep,
        handleTaskComplete,
        handlePlanComplete,
        processConclusion,
      };
      const applyEvent = (ev: ThinkingEvent) =>
        handleMultiAnalyzeStreamEvent(projectId, refs, currentLang, ev, flags, streamCtx);

      // Declared outside try so the catch block can read them.
      let idleTimeoutTriggered = false;
      let idleTimer: ReturnType<typeof setTimeout> | null = null;

      try {
        const headers: Record<string, string> = {
          ...getClientTimezoneHeaders(),
          'Content-Type': 'application/json',
        };
        const token = getAuthToken();
        if (token) headers['Authorization'] = `Bearer ${token}`;

        const response = await fetch(STREAM_URL, {
          method: 'POST',
          headers,
          body: JSON.stringify({
            message: messageText,
            attachments: serializeAttachmentsForAnalyze(attachments),
            analysis_scope: 'all_input',
            stream: true,
            language: currentLang,
            ui_language: currentLang,
            input_language: 'auto',
            session_id: sessionId,
            project_id: sessionId,
            request_id: requestId,
            client_timezone: Intl.DateTimeFormat().resolvedOptions().timeZone,
            model_id: modelId || undefined,
          }),
          signal: controller.signal,
        });

        if (!response.ok) {
          const { message, billingCode } = await parseAnalyzeHttpError(response);
          const st = getTranslations(currentLang).streaming;
          if (billingCode === 'BILLING_CAP_EXCEEDED') {
            toast.error(st.billingCapExceeded);
          } else if (billingCode === 'BILLING_PLAN_INACTIVE') {
            toast.error(st.billingPlanInactive);
          }
          throw new Error(message);
        }

        const reader = response.body?.getReader();
        if (!reader) throw new Error('No response body');

        const decoder = new TextDecoder();

        // If no SSE data arrives for this many ms we assume the backend is stuck
        // and abort the connection so the user sees an error instead of an infinite
        // "thinking" spinner.
        const SSE_IDLE_TIMEOUT_MS = 3_600_000; // 1 hour
        const resetIdleTimer = () => {
          if (idleTimer) clearTimeout(idleTimer);
          idleTimer = setTimeout(() => {
            idleTimeoutTriggered = true;
            controller.abort();
          }, SSE_IDLE_TIMEOUT_MS);
        };
        resetIdleTimer();

        for await (const raw of readSseJsonLines(reader, decoder, {
          shouldAbort: () => refs.activeRequestId !== requestId || !isMountedRef.current,
          onRawChunk: resetIdleTimer,
        })) {
          if (!isMountedRef.current) break;
          try {
            const event = parseAnalysisEvent(raw);
            if (applyEvent(event)) continue;
            applyWorkspaceTabEvent(projectId, event as { type: string; toolName?: string; toolInput?: Record<string, unknown> });
          } catch {
            /* ignore */
          }
        }
        if (idleTimer) clearTimeout(idleTimer);
      } catch (error) {
        if (refs.activeRequestId !== requestId) return;
        let msg: string;
        if ((error as Error).name === 'AbortError') {
          if (!idleTimeoutTriggered) return;
          msg = 'SSE connection timed out: no response from server for 1 hour.';
        } else {
          msg = (error as Error)?.message || String(error);
        }

        const text = getTranslations(currentLang).streaming;
        let friendly = msg;
        if (msg.includes('Failed to fetch') || msg.includes('NetworkError')) friendly = text.networkError;
        else if (msg.includes('401') || msg.includes('Unauthorized')) friendly = text.sessionExpired;
        else if (msg.includes('CORS')) friendly = text.networkError;

        updateState(projectId, (p) => {
          const rrefs = getProjectRefs(projectId);
          const errEv: ThinkingEvent = {
            type: 'error',
            id: 'client-stream-error',
            label: text.analysisFailed,
            status: 'error',
            detail: friendly,
          };
          let next: PerProjectStreamingState = {
            ...p,
            timeline: appendToAnalysisTimeline(p.timeline, errEv, () => ++rrefs.timelineLocalSeq),
            blocks: [
              {
                type: 'summary',
                id: 'summary-error',
                severity: 'medium',
                title: text.analysisFailed,
                description: friendly || text.checkNetwork,
              },
            ],
          };
          const markRunningErr = (plan: TaskPlan | null): TaskPlan | null => {
            if (!plan?.tasks.some((t) => t.status === 'running')) return plan;
            return {
              ...plan,
              tasks: plan.tasks.map((t) =>
                t.status === 'running' ? { ...t, status: 'error' as const, error: friendly } : t
              ),
            };
          };
          next = {
            ...next,
            taskPlanMain: markRunningErr(p.taskPlanMain),
            taskPlansSubagent: Object.fromEntries(
              Object.entries(p.taskPlansSubagent).map(([k, pl]) => [k, markRunningErr(pl)]),
            ),
          };
          return next;
        });
      } finally {
        // Turn-boundary flush: the 20s debounce in ``contextUsageSync``
        // collapses many `llm_invoke_end` events into at most one PATCH
        // per window. When the turn actually ends (normal done, user
        // abort, or unhandled error) we want the backend to have the
        // very last snapshot before the UI considers the analysis
        // finished. Fire-and-forget; errors are swallowed inside.
        void flushNow(projectId);
        // Seed progress-restore suppress for any non-HITL stream end, even when
        // the ``activeRequestId`` guard below is skipped (abort() clears the ref
        // early; superseded requests skip the inner block). Otherwise
        // useAnalysisProgressRestore's polling can call ``reloadProjectMessages``
        // a few seconds later and the chat column "reloads". Must run before
        // ``setAbortController(null)`` (see hook option doc).
        logger.info('sse_analyze_finally', {
          project_id: projectId,
          request_id: requestId,
          saw_hitl_awaiting: flags.sawHitlAwaiting,
          invoked_stop_progress_restore: !flags.sawHitlAwaiting,
          active_request_matches: isMountedRef.current && refs.activeRequestId === requestId,
        });
        if (!flags.sawHitlAwaiting) {
          stopProgressRestorePollingRef.current?.(projectId);
        }
        if (isMountedRef.current && refs.activeRequestId === requestId) {
          refs.activeRequestId = '';
          setAbortController(projectId, null);
          // IMPORTANT: React 18 runs setStateMap updaters lazily during the next
          // render, not synchronously at call time. In-stream updaters queued by
          // handleParameterRequest / done / etc. have NOT executed yet when this
          // finally block runs, so ``stateMapRef.current`` is still stale here.
          //
          // We therefore:
          //   1. Build the final state inside a *functional* updater (prev has
          //      everything the stream just wrote).
          //   2. Decide whether this turn is "truly done" using
          //      ``flags.sawHitlAwaiting`` — a plain local variable that is
          //      authoritative and NOT affected by React batching. Reading
          //      ``hitlAwaiting`` from a stale ref here used to misfire the
          //      completion branch, which called ``resetForProject`` and wiped
          //      the HITL form.
          //   3. Defer the conversation append + onComplete so ``stateToPersist``
          //      is populated by the time the setTimeout(0) callback runs.
          const pending = pendingStateRef.current.get(projectId);
          if (pending) {
            pendingStateRef.current.delete(projectId);
          }
          let stateToPersist: PerProjectStreamingState | null = null;
          updateState(projectId, (prev) => {
            let next: PerProjectStreamingState = {
              ...prev,
              isAnalyzing: false,
              currentRequestId: '',
            };
            if (flags.sawHitlAwaiting) {
              next.hitlAwaiting = true;
              next.hitlProgressRequestId = requestId;
            } else {
              if (prev.hitlProgressRequestId) {
                clearHitlSubmittedParams(projectId, prev.hitlProgressRequestId);
              }
              next.hitlProgressRequestId = undefined;
              refs.progressCorrelationRequestId = '';
            }
            if (pending) {
              if (pending.taskSummary !== undefined) next = { ...next, taskSummary: pending.taskSummary };
              if (pending.conclusion !== undefined) next = { ...next, conclusion: pending.conclusion };
              if (pending.blocks !== undefined && pending.blocks.length > 0) next = { ...next, blocks: pending.blocks };
            }
            stateToPersist = next;
            return next;
          });
          // Only finalize to conversation history when the turn is truly complete.
          // HITL-awaiting turns must leave the live state intact so the inline
          // form keeps rendering; progress will re-persist when the user resumes.
          if (!flags.sawHitlAwaiting) {
            const pid = projectId;
            resetForProject(pid);
            deferPostStreamFinalize(() => {
              if (!isMountedRef.current) return;
              const finalState = stateToPersist ?? getLatestState(pid);
              /** ``currentRequestId`` is cleared in the state snapshot; link + KB archive match on ``request_id`` */
              const msgs = buildConversationMessages({
                ...finalState,
                completedRequestId: requestId,
              });
              if (!msgs) return;
              appendToConversation(pid, msgs);
              const onComplete = onProjectAnalysisCompleteRef.current;
              if (onComplete) onComplete(pid, { ...finalState, completedRequestId: requestId });
            });
          }
        }
      }
    },
    [
      getLatestState,
      updateState,
      setAbortController,
      getProjectRefs,
      appendToConversation,
      resetForProject,
      effectiveSessionId,
      logSSEEvent,
      handleTaskPlan,
      handleTaskCreate,
      handleTaskUpdate,
      handleDecisionRequest,
      handleUnderstanding,
      handleParameterRequest,
      handleTaskStart,
      handleTaskStep,
      handleTaskComplete,
      handlePlanComplete,
      processConclusion,
    ]
  );

  const submitHitlResume = useCallback(
    async (
      projectId: string,
      resume: unknown,
      language?: SupportedLanguage,
      timelineContext?: HitlResumeTimelineContext,
    ) => {
      const requestId = createRequestId();
      const refs = getProjectRefs(projectId);
      // Match analyzeInput: silence progress polling before a new SSE leg.
      stopProgressRestorePollingRef.current?.(projectId);
      const progressRequestId =
        getLatestState(projectId).hitlProgressRequestId ||
        refs.progressCorrelationRequestId ||
        '';
      const resolvedLang = resolveHitlResumeUiLanguage(projectId, language);
      // Preserve flags from the interrupted first-leg so processConclusion
      // still recognises this session as having a task plan / research route.
      // analyzeInput resets these because it starts a fresh turn; resume continues
      // the same logical turn after a HITL pause.
      refs.activeRequestId = requestId;
      refs.pendingLanguage = resolvedLang;

      const sessionId = projectId ?? effectiveSessionId;

      updateState(projectId, (p) => ({
        ...p,
        currentRequestId: requestId,
        isAnalyzing: true,
        hitlAwaiting: false,
        hitlSnapshot: null,
      }));

      const controller = new AbortController();
      setAbortController(projectId, controller);

      const flags: MultiStreamProgressFlags = {
        sawConclusionEvent: false,
        sawErrorEvent: false,
        sawDoneEvent: false,
        sawHitlAwaiting: false,
      };
      const streamCtx: MultiStreamEventCtx = {
        logSSEEvent,
        getProjectRefs,
        updateState,
        pendingStateRef,
        handleTaskPlan,
        handleTaskCreate,
        handleTaskUpdate,
        handleDecisionRequest,
        handleUnderstanding,
        handleParameterRequest,
        handleTaskStart,
        handleTaskStep,
        handleTaskComplete,
        handlePlanComplete,
        processConclusion,
      };
      const applyEvent = (ev: ThinkingEvent) =>
        handleMultiAnalyzeStreamEvent(projectId, refs, resolvedLang, ev, flags, streamCtx);

      let idleTimeoutTriggered = false;
      let idleTimer: ReturnType<typeof setTimeout> | null = null;

      try {
        const headers: Record<string, string> = {
          ...getClientTimezoneHeaders(),
          'Content-Type': 'application/json',
        };
        const token = getAuthToken();
        if (token) headers['Authorization'] = `Bearer ${token}`;

        const resumeModelId = getLastSelectedModelIdForApi();
        const response = await fetch(analysisEndpoints.resumeStream, {
          method: 'POST',
          headers,
          body: JSON.stringify({
            session_id: sessionId,
            resume,
            request_id: requestId,
            ...(progressRequestId ? { progress_request_id: progressRequestId } : {}),
            project_id: sessionId,
            ui_language: resolvedLang,
            input_language: 'auto',
            client_timezone: Intl.DateTimeFormat().resolvedOptions().timeZone,
            ...(resumeModelId ? { model_id: resumeModelId } : {}),
            ...(timelineContext
              ? {
                  hitl_decision_ui_id: timelineContext.decisionUiId,
                  hitl_selected_options: timelineContext.selectedOptions,
                }
              : {}),
          }),
          signal: controller.signal,
        });

        if (!response.ok) {
          const { message, billingCode } = await parseAnalyzeHttpError(response);
          const st = getTranslations(resolvedLang).streaming;
          if (billingCode === 'BILLING_CAP_EXCEEDED') {
            toast.error(st.billingCapExceeded);
          } else if (billingCode === 'BILLING_PLAN_INACTIVE') {
            toast.error(st.billingPlanInactive);
          }
          throw new Error(message);
        }

        const reader = response.body?.getReader();
        if (!reader) throw new Error('No response body');

        const decoder = new TextDecoder();

        const SSE_IDLE_TIMEOUT_MS = 3_600_000; // 1 hour
        const resetIdleTimer = () => {
          if (idleTimer) clearTimeout(idleTimer);
          idleTimer = setTimeout(() => {
            idleTimeoutTriggered = true;
            controller.abort();
          }, SSE_IDLE_TIMEOUT_MS);
        };
        resetIdleTimer();

        for await (const raw of readSseJsonLines(reader, decoder, {
          shouldAbort: () => refs.activeRequestId !== requestId || !isMountedRef.current,
          onRawChunk: resetIdleTimer,
        })) {
          if (!isMountedRef.current) break;
          try {
            const event = parseAnalysisEvent(raw);
            if (applyEvent(event)) continue;
            applyWorkspaceTabEvent(projectId, event as { type: string; toolName?: string; toolInput?: Record<string, unknown> });
          } catch {
            /* ignore */
          }
        }
        if (idleTimer) clearTimeout(idleTimer);
      } catch (error) {
        if (refs.activeRequestId !== requestId) return;
        let msg: string;
        if ((error as Error).name === 'AbortError') {
          if (!idleTimeoutTriggered) return;
          msg = 'SSE connection timed out: no response from server for 1 hour.';
        } else {
          msg = (error as Error)?.message || String(error);
        }

        const text = getTranslations(resolvedLang).streaming;
        let friendly = msg;
        if (msg.includes('Failed to fetch') || msg.includes('NetworkError')) friendly = text.networkError;
        else if (msg.includes('401') || msg.includes('Unauthorized')) friendly = text.sessionExpired;
        else if (msg.includes('CORS')) friendly = text.networkError;

        updateState(projectId, (p) => {
          const rrefs = getProjectRefs(projectId);
          const errEv: ThinkingEvent = {
            type: 'error',
            id: 'client-hitl-resume-error',
            label: text.analysisFailed,
            status: 'error',
            detail: friendly,
          };
          let next: PerProjectStreamingState = {
            ...p,
            hitlAwaiting: true,
            timeline: appendToAnalysisTimeline(p.timeline, errEv, () => ++rrefs.timelineLocalSeq),
            blocks: [
              {
                type: 'summary',
                id: 'summary-hitl-resume-error',
                severity: 'medium',
                title: text.analysisFailed,
                description: friendly || text.checkNetwork,
              },
            ],
          };
          const markRunningErr = (plan: TaskPlan | null): TaskPlan | null => {
            if (!plan?.tasks.some((t) => t.status === 'running')) return plan;
            return {
              ...plan,
              tasks: plan.tasks.map((t) =>
                t.status === 'running' ? { ...t, status: 'error' as const, error: friendly } : t
              ),
            };
          };
          next = {
            ...next,
            taskPlanMain: markRunningErr(p.taskPlanMain),
            taskPlansSubagent: Object.fromEntries(
              Object.entries(p.taskPlansSubagent).map(([k, pl]) => [k, markRunningErr(pl)]),
            ),
          };
          return next;
        });
      } finally {
        // See sibling path: force a backend flush on every turn boundary
        // so the 20s debounce can't drop the tail of a long turn.
        void flushNow(projectId);
        if (!flags.sawHitlAwaiting) {
          stopProgressRestorePollingRef.current?.(projectId);
        }
        if (isMountedRef.current && refs.activeRequestId === requestId) {
          refs.activeRequestId = '';
          setAbortController(projectId, null);
          // See sibling path in analyzeInput for the full rationale: React 18
          // queues setStateMap updaters and only runs them at render time, so
          // in-stream updates (handleParameterRequest / done / etc.) have NOT
          // landed in the ref yet when this finally block fires. We must (1)
          // merge via functional updater, (2) decide completion from the
          // ``flags.sawHitlAwaiting`` local (not from stale state), and (3)
          // defer finalize so ``stateToPersist`` is populated before read.
          const pending = pendingStateRef.current.get(projectId);
          if (pending) {
            pendingStateRef.current.delete(projectId);
          }
          let stateToPersist: PerProjectStreamingState | null = null;
          updateState(projectId, (prev) => {
            let next: PerProjectStreamingState = {
              ...prev,
              isAnalyzing: false,
              currentRequestId: '',
            };
            if (flags.sawHitlAwaiting) {
              next.hitlAwaiting = true;
            } else {
              if (prev.hitlProgressRequestId) {
                clearHitlSubmittedParams(projectId, prev.hitlProgressRequestId);
              }
              next.hitlProgressRequestId = undefined;
              refs.progressCorrelationRequestId = '';
            }
            if (pending) {
              if (pending.taskSummary !== undefined) next = { ...next, taskSummary: pending.taskSummary };
              if (pending.conclusion !== undefined) next = { ...next, conclusion: pending.conclusion };
              if (pending.blocks !== undefined && pending.blocks.length > 0) next = { ...next, blocks: pending.blocks };
            }
            stateToPersist = next;
            return next;
          });
          if (!flags.sawHitlAwaiting) {
            const pid = projectId;
            resetForProject(pid);
            deferPostStreamFinalize(() => {
              if (!isMountedRef.current) return;
              const finalState = stateToPersist ?? getLatestState(pid);
              /** ``currentRequestId`` is cleared in the state snapshot; link + KB archive match on ``request_id`` */
              const msgs = buildConversationMessages({
                ...finalState,
                completedRequestId: requestId,
              });
              if (!msgs) return;
              appendToConversation(pid, msgs);
              const onComplete = onProjectAnalysisCompleteRef.current;
              if (onComplete) onComplete(pid, { ...finalState, completedRequestId: requestId });
            });
          }
        }
      }
    },
    [
      getLatestState,
      updateState,
      setAbortController,
      getProjectRefs,
      appendToConversation,
      resetForProject,
      effectiveSessionId,
      logSSEEvent,
      handleTaskPlan,
      handleTaskCreate,
      handleTaskUpdate,
      handleDecisionRequest,
      handleUnderstanding,
      handleParameterRequest,
      handleTaskStart,
      handleTaskStep,
      handleTaskComplete,
      handlePlanComplete,
      processConclusion,
      resolveHitlResumeUiLanguage,
    ]
  );

  const handleDecision = useCallback(
    (projectId: string, decisionUiId: string, selectedOptions: string[]) => {
      const live = getLatestState(projectId);
      const resumePayload = buildHitlResumeFromDecision(
        live.timeline,
        decisionUiId,
        selectedOptions,
        live.decisions.find((d) => d.id === decisionUiId),
      );
      updateState(projectId, (prev) => ({
        ...prev,
        resolvedDecisions: { ...prev.resolvedDecisions, [decisionUiId]: selectedOptions },
      }));
      const resolvedLang = resolveHitlResumeUiLanguage(projectId);
      void submitHitlResume(projectId, resumePayload, resolvedLang, {
        decisionUiId,
        selectedOptions,
      });
    },
    [getLatestState, updateState, submitHitlResume, resolveHitlResumeUiLanguage],
  );

  const abort = useCallback(
    (projectId: string) => {
      const refs = getProjectRefs(projectId);
      const requestId = refs.activeRequestId;
      const lang = resolveHitlResumeUiLanguage(projectId);
      const t = getTranslations(lang);

      const controller = getAbortController(projectId);
      if (controller) controller.abort();
      refs.activeRequestId = '';

      updateState(projectId, (p) => ({
        ...p,
        isAnalyzing: false,
        currentRequestId: '',
        conclusion: t.streaming.analysisCancelled,
        hitlAwaiting: false,
        hitlProgressRequestId: undefined,
        tasks: p.tasks.map((task) =>
          task.status === 'in_progress' ? { ...task, status: 'done' as const } : task,
        ),
      }));

      if (requestId) {
        analysisApi.cancelAnalysis(requestId);
      }
    },
    [getAbortController, getProjectRefs, updateState, resolveHitlResumeUiLanguage]
  );

  // Always mirror the selected project's row. `resolveStreamDisplayProjectId` previously
  // picked another analyzing project when the current id had no abort controller, which
  // stacked the wrong live turn under the current project's history (multi-tab analyze).
  const streamingState = currentProjectId
    ? getLatestState(currentProjectId)
    : createEmptyStreamingState();

  return {
    ...streamingState,
    /** @deprecated Prefer taskPlanMain; kept for callers that only need the orchestrator board. */
    taskPlan: streamingState.taskPlanMain,
    analyzeInput,
    submitHitlResume: (
      resume: unknown,
      language?: SupportedLanguage,
      timelineContext?: HitlResumeTimelineContext,
    ) =>
      currentProjectId
        ? submitHitlResume(currentProjectId, resume, language, timelineContext)
        : Promise.resolve(),
    handleDecision: (requestId: string, selectedOptions: string[]) =>
      handleDecision(currentProjectId!, requestId, selectedOptions),
    handleParameterSubmit: async (parameters: Record<string, string>) => {
      if (!currentProjectId) return;
      const refs = getProjectRefs(currentProjectId);
      const requestId = refs.pendingRequestId;

      const cleaned: Record<string, string> = Object.fromEntries(
        Object.entries(parameters).map(([k, v]) => [k, String(v ?? '').trim()]),
      );
      const fallbackReply =
        cleaned.reply ||
        Object.values(cleaned).find((v) => v.length > 0) ||
        '';

      const progressRid =
        getLatestState(currentProjectId).hitlProgressRequestId ||
        refs.progressCorrelationRequestId ||
        '';
      if (progressRid) {
        saveHitlSubmittedParams(currentProjectId, progressRid, cleaned);
      }

      // Keep the form visible in read-only mode; only mark as submitted.
      updateState(currentProjectId, (prev) => ({
        ...prev,
        submittedParameters: { ...prev.submittedParameters, ...cleaned },
        hitlParametersSubmitted: true,
      }));

      // HITL resume payload accepts either plain text or object.
      // Prefer a structured object so backend adapters can extract response/reply/answer robustly.
      const resumePayload: Record<string, unknown> = {
        ...cleaned,
        ...(requestId ? { requestId } : {}),
      };
      if (!resumePayload.response && !resumePayload.reply && !resumePayload.answer) {
        resumePayload.response = fallbackReply;
      }

      await submitHitlResume(currentProjectId, resumePayload);
    },
    isSubmittingParameters: false,
    isWaitingForResume: false,
    abort: () => currentProjectId && abort(currentProjectId),
    resetForProject,
    removeState,
    clearSSELogs: () => currentProjectId && clearSSELogs(currentProjectId),
  };
}
