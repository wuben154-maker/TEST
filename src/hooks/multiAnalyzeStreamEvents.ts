/**
 * SSE dispatch for useStreamingAnalysisMulti (timeline + per-project state).
 * Shared by POST /analyze and POST /analyze/resume.
 */
import type { PlannedTask, ThinkingEvent, TaskPlan, WorkspaceBlock } from '@/types/analysis';
import { buildTaskPlanFromWriteTodosToolCall } from '@/lib/streaming/writeTodosTaskPlan';
import type { PerProjectStreamingState } from '@/types/streaming';
import { getTranslations, type Language } from '@/i18n';
import { appendToAnalysisTimeline } from '@/lib/timelineReducer';
import { isMainTaskPlanScope, mapTaskInPlan, subagentTaskPlanMapKey } from '@/lib/taskPlanScope';
import { effectiveToolPresentation } from '@/lib/toolPresentation';
import { applyEventToContextUsage } from '@/lib/contextUsage';
import { flushNow as flushContextUsage } from '@/lib/contextUsageSync';
import { toast } from 'sonner';

export type MultiProjectStreamRefs = {
  hasTaskPlan: boolean;
  hasResearchRoute: boolean;
  activeRequestId: string;
  pendingRequestId: string;
  pendingInput: string;
  pendingLanguage: Language;
  timelineLocalSeq: number;
};

export type MultiStreamProgressFlags = {
  sawConclusionEvent: boolean;
  sawErrorEvent: boolean;
  sawDoneEvent: boolean;
  sawHitlAwaiting: boolean;
};

export type MultiStreamEventCtx = {
  logSSEEvent: (projectId: string, event: ThinkingEvent) => void;
  getProjectRefs: (projectId: string) => MultiProjectStreamRefs;
  updateState: (
    projectId: string,
    updater: (prev: PerProjectStreamingState) => PerProjectStreamingState,
  ) => void;
  pendingStateRef: { current: Map<string, { taskSummary?: string; conclusion?: string; blocks?: WorkspaceBlock[] }> };
  handleTaskPlan: (projectId: string, event: ThinkingEvent) => void;
  handleTaskCreate: (projectId: string, event: ThinkingEvent) => void;
  handleTaskUpdate: (projectId: string, event: ThinkingEvent) => void;
  handleDecisionRequest: (projectId: string, event: ThinkingEvent) => void;
  handleUnderstanding: (projectId: string, event: ThinkingEvent) => void;
  handleParameterRequest: (projectId: string, event: ThinkingEvent) => void;
  handleTaskStart: (projectId: string, event: ThinkingEvent) => void;
  handleTaskStep: (projectId: string, event: ThinkingEvent) => void;
  handleTaskComplete: (projectId: string, event: ThinkingEvent) => void;
  handlePlanComplete: (projectId: string, event: ThinkingEvent) => void;
  processConclusion: (
    projectId: string,
    content: string,
    input: string,
    lang: Language,
  ) => void;
};

/** @returns true if the caller should skip further handling for this line (request id mismatch). */
export function handleMultiAnalyzeStreamEvent(
  projectId: string,
  refs: MultiProjectStreamRefs,
  currentLang: Language,
  ev: ThinkingEvent,
  flags: MultiStreamProgressFlags,
  ctx: MultiStreamEventCtx,
): boolean {
  const hitlResumeId =
    (typeof (ev as { interruptRequestId?: unknown }).interruptRequestId === 'string' &&
    String((ev as { interruptRequestId?: unknown }).interruptRequestId).trim())
      ? String((ev as { interruptRequestId?: unknown }).interruptRequestId).trim()
      : '';
  if (import.meta.env.DEV) {
    console.log('[SSE-MULTI] event', {
      projectId,
      type: ev.type,
      id: ev.id,
      requestId: ev.requestId,
      activeRequestId: refs.activeRequestId,
    });
  }
  // Dev panel: record every raw line first; stale requestId lines are labeled in rawData.
  ctx.logSSEEvent(projectId, ev);
  // HITL events carry ``requestId`` as the *interrupt / tool correlation id* (e.g. dr-clarify-*),
  // not the HTTP stream ``request_id``.  Dropping them here prevented timeline + form state updates.
  // ``conclusion`` may use the parent / graph correlation id while the client tracks the POST
  // stream ``request_id`` (especially after ``/analyze/resume``); Dev panel still logs the line first.
  const bypassStreamRequestIdGate =
    ev.type === 'parameter_request' ||
    ev.type === 'decision_request' ||
    ev.type === 'research_clarification_required' ||
    ev.type === 'conclusion' ||
    ev.type === 'done';
  if (
    ev.requestId &&
    ev.requestId !== refs.activeRequestId &&
    !bypassStreamRequestIdGate
  ) {
    if (import.meta.env.DEV) {
      console.warn('[SSE-MULTI] dropped by request mismatch', {
        type: ev.type,
        eventRequestId: ev.requestId,
        activeRequestId: refs.activeRequestId,
      });
    }
    return true;
  }
  if (ev.internal) {
    return true;
  }

  const rrefs = ctx.getProjectRefs(projectId);
  ctx.updateState(projectId, (p) => ({
    ...p,
    timeline: appendToAnalysisTimeline(p.timeline, ev, () => ++rrefs.timelineLocalSeq),
  }));

  switch (ev.type) {
    case 'step':
      if (ev.id === 'open-deep-research-start') {
        refs.hasResearchRoute = true;
      }
      break;
    case 'research_clarification_required':
      refs.hasResearchRoute = true;
      break;
    case 'tool_call': {
      const todoNs = refs.activeRequestId || 'wt';
      const plan = buildTaskPlanFromWriteTodosToolCall(ev, (idx) => `main:todo:${todoNs}:${idx}`);
      if (plan) {
        ctx.handleTaskPlan(projectId, {
          type: 'task_plan',
          id: 'task-plan',
          scope: 'main',
          plan,
        });
        break;
      }
      if (
        ev.toolName === 'ConductResearch' ||
        effectiveToolPresentation(ev) === 'research_task'
      ) {
        const tid = String(ev.id ?? '');
        if (tid) {
          refs.hasTaskPlan = true;
          const inp = (ev.toolInput ?? {}) as Record<string, unknown>;
          const rawTitle = String(inp.research_topic ?? '').trim();
          const titleBase =
            rawTitle || getTranslations(currentLang).reasoning.researchTopicPending;
          const displayTitle =
            titleBase.length > 2000 ? `${titleBase.slice(0, 2000)}…` : titleBase;
          ctx.updateState(projectId, (prev) => {
            const seed = (): TaskPlan => ({
              id: 'conduct-research-plan',
              tasks: [],
              isSingleTask: true,
              totalDurationMs: 0,
              status: 'running',
              createdAt: '',
            });
            const appendOrRefresh = (plan: TaskPlan | null): TaskPlan => {
              const p = plan ?? seed();
              const pos = p.tasks.findIndex((t) => t.id === tid);
              if (pos >= 0) {
                if (!rawTitle || displayTitle === p.tasks[pos]!.title) return p;
                const tasks = [...p.tasks];
                tasks[pos] = {
                  ...tasks[pos]!,
                  title: displayTitle,
                  description: displayTitle,
                };
                return { ...p, tasks };
              }
              const planned: PlannedTask = {
                id: tid,
                title: displayTitle,
                description: displayTitle,
                taskType: 'security',
                priority: p.tasks.length + 1,
                status: 'pending',
                durationMs: 0,
                steps: [],
              };
              const tasks = [...p.tasks, planned];
              return {
                ...p,
                tasks,
                isSingleTask: tasks.length === 1,
              };
            };
            if (isMainTaskPlanScope(ev)) {
              return { ...prev, taskPlanMain: appendOrRefresh(prev.taskPlanMain) };
            }
            const sk = subagentTaskPlanMapKey(ev);
            return {
              ...prev,
              taskPlansSubagent: {
                ...prev.taskPlansSubagent,
                [sk]: appendOrRefresh(prev.taskPlansSubagent[sk] ?? null),
              },
            };
          });
        }
      }
      break;
    }
    case 'tool_result': {
      if (
        ev.toolName === 'ConductResearch' ||
        effectiveToolPresentation(ev) === 'research_task'
      ) {
        const tid = String(ev.id ?? '');
        if (tid) {
          ctx.updateState(projectId, (prev) => {
            const mark = (plan: TaskPlan | null): TaskPlan | null => {
              if (!plan) return null;
              return {
                ...plan,
                tasks: plan.tasks.map((t) =>
                  t.id === tid ? { ...t, status: 'success' as const } : t,
                ),
              };
            };
            if (isMainTaskPlanScope(ev)) {
              return { ...prev, taskPlanMain: mark(prev.taskPlanMain) };
            }
            const sk = subagentTaskPlanMapKey(ev);
            return {
              ...prev,
              taskPlansSubagent: {
                ...prev.taskPlansSubagent,
                [sk]: mark(prev.taskPlansSubagent[sk] ?? null),
              },
            };
          });
        }
      }
      break;
    }
    case 'reasoning':
      break;
    case 'llm_delta':
      break;
    case 'llm_invoke_start':
    case 'llm_invoke_end':
      ctx.updateState(projectId, (p) => ({
        ...p,
        contextUsage: applyEventToContextUsage(p.contextUsage, ev),
      }));
      break;
    case 'context_summarized':
      ctx.updateState(projectId, (p) => ({
        ...p,
        contextUsage: applyEventToContextUsage(p.contextUsage, ev),
      }));
      {
        // One-shot notice so the user knows the backend compacted history;
        // keeps message replay clean (no extra timeline row — state is enough).
        const text = getTranslations(currentLang);
        toast.info(text.command.contextUsage.summarizedToast);
      }
      // Summarisation is a meaningful milestone — bypass the 20s debounce
      // so a post-compact reload shows the compacted figure on the ring.
      void flushContextUsage(projectId);
      break;
    case 'answer':
      break;
    case 'conclusion':
      flags.sawConclusionEvent = true;
      {
        const conclusionContent = ev.content || '';
        const prev = ctx.pendingStateRef.current.get(projectId) ?? {};
        ctx.pendingStateRef.current.set(projectId, { ...prev, conclusion: conclusionContent });
        // Backend-owned TaskStatsMeta rides the conclusion event (schemaVersion 1).
        // Persist it so the stats bar survives hydration and reload.
        const meta = ev.meta;
        ctx.updateState(projectId, (p) => ({
          ...p,
          conclusion: conclusionContent,
          ...(meta && meta.taskKind ? { statsMeta: meta } : {}),
        }));
        ctx.processConclusion(projectId, conclusionContent, refs.pendingInput, currentLang);
      }
      break;
    case 'task_create':
      ctx.handleTaskCreate(projectId, ev);
      break;
    case 'task_update':
      ctx.handleTaskUpdate(projectId, ev);
      break;
    case 'decision_request':
      ctx.handleDecisionRequest(projectId, ev);
      break;
    case 'understanding':
      ctx.handleUnderstanding(projectId, ev);
      break;
    case 'parameter_request':
      if (import.meta.env.DEV) {
        console.log('[SSE-MULTI] parameter_request received', {
          requestId: ev.requestId,
          id: ev.id,
          interruptId: (ev as { interruptId?: string }).interruptId,
          count: Array.isArray(ev.parameterRequests) ? ev.parameterRequests.length : 0,
          detail: ev.detail,
        });
      }
      // Debug fallback bus: ensure UI can render HITL form even if project state chain drops it.
      if (typeof window !== 'undefined') {
        window.dispatchEvent(
          new CustomEvent('secmanus-hitl-parameter-request', { detail: ev }),
        );
      }
      if (hitlResumeId || ev.id || ev.requestId) {
        refs.pendingRequestId = hitlResumeId || ev.id || ev.requestId;
      }
      if (Array.isArray(ev.parameterRequests) && ev.parameterRequests.length > 0) {
        const isClarification = ev.interruptKind === 'user_input_v1';
        ev.parameterRequests = ev.parameterRequests.map((req) => ({
          ...req,
          isClarification: isClarification || req.isClarification === true,
        }));
      }
      ctx.handleParameterRequest(projectId, ev);
      break;
    case 'task_plan':
      ctx.handleTaskPlan(projectId, ev);
      break;
    case 'task_start':
      ctx.handleTaskStart(projectId, ev);
      break;
    case 'task_step':
      ctx.handleTaskStep(projectId, ev);
      break;
    case 'task_complete':
      ctx.handleTaskComplete(projectId, ev);
      break;
    case 'task_error':
      if (ev.id) {
        const tid = ev.id;
        const detail = ev.detail;
        ctx.updateState(projectId, (p) => {
          if (isMainTaskPlanScope(ev)) {
            if (!p.taskPlanMain) return p;
            return {
              ...p,
              taskPlanMain: mapTaskInPlan(p.taskPlanMain, tid, (t) => ({
                ...t,
                status: 'error' as const,
                error: detail,
              })),
            };
          }
          const sk = subagentTaskPlanMapKey(ev);
          const plan = p.taskPlansSubagent[sk];
          if (!plan) return p;
          return {
            ...p,
            taskPlansSubagent: {
              ...p.taskPlansSubagent,
              [sk]: mapTaskInPlan(plan, tid, (t) => ({
                ...t,
                status: 'error' as const,
                error: detail,
              })),
            },
          };
        });
      }
      break;
    case 'plan_complete':
      ctx.handlePlanComplete(projectId, ev);
      break;
    case 'task_summary':
      if (ev.summary) {
        const prev = ctx.pendingStateRef.current.get(projectId) ?? {};
        ctx.pendingStateRef.current.set(projectId, { ...prev, taskSummary: ev.summary });
        ctx.updateState(projectId, (p) => ({ ...p, taskSummary: ev.summary }));
      }
      break;
    case 'next_actions':
      if (ev.nextActions?.length) {
        ctx.updateState(projectId, (p) => ({ ...p, nextActions: ev.nextActions }));
      }
      break;
    case 'workflow_step':
    case 'skill_start':
    case 'skill_complete':
    case 'skill_reasoning':
    case 'skill_error':
      break;
    case 'error':
      flags.sawErrorEvent = true;
      ctx.updateState(projectId, (p) => {
        const detail = ev.detail;
        const markRunningErr = (plan: TaskPlan | null) => {
          if (!plan?.tasks.some((t) => t.status === 'running')) return plan;
          return {
            ...plan,
            tasks: plan.tasks.map((t) =>
              t.status === 'running' ? { ...t, status: 'error' as const, error: detail } : t,
            ),
          };
        };
        return {
          ...p,
          taskPlanMain: markRunningErr(p.taskPlanMain),
          taskPlansSubagent: Object.fromEntries(
            Object.entries(p.taskPlansSubagent).map(([k, pl]) => [k, markRunningErr(pl)]),
          ),
        };
      });
      break;
    case 'done':
      flags.sawDoneEvent = true;
      if (ev.awaitingHuman === true) {
        flags.sawHitlAwaiting = true;
        ctx.updateState(projectId, (p) => ({
          ...p,
          hitlAwaiting: true,
          isAnalyzing: false,
          hitlProgressRequestId: p.hitlProgressRequestId || p.currentRequestId || undefined,
          hitlSnapshot:
            ev.hitl?.interruptIds != null ? { interruptIds: ev.hitl.interruptIds } : ev.hitl ?? null,
        }));
      } else {
        const markIncompleteSuccess = (plan: TaskPlan | null) => {
          if (!plan?.tasks.some((t) => t.status === 'running' || t.status === 'pending')) return plan;
          return {
            ...plan,
            tasks: plan.tasks.map((t) =>
              t.status === 'running' || t.status === 'pending'
                ? { ...t, status: 'success' as const }
                : t,
            ),
          };
        };
        ctx.updateState(projectId, (p) => ({
          ...p,
          isAnalyzing: false,
          hitlAwaiting: false,
          hitlSnapshot: null,
          hitlProgressRequestId: undefined,
          taskPlanMain: markIncompleteSuccess(p.taskPlanMain),
          taskPlansSubagent: Object.fromEntries(
            Object.entries(p.taskPlansSubagent).map(([k, pl]) => [k, markIncompleteSuccess(pl)]),
          ),
        }));
      }
      break;
    default:
      break;
  }
  return false;
}
