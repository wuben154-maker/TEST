import type { Dispatch, MutableRefObject, SetStateAction } from 'react';
import type { ThinkingEvent, TaskPlan, NextAction } from '@/types/analysis';
import { buildTaskPlanFromWriteTodosToolCall } from '@/lib/streaming/writeTodosTaskPlan';
import type { Language } from '@/i18n';
import { effectiveToolPresentation, isContextEnrichmentToolName } from '@/lib/toolPresentation';

export type AnalyzeStreamTrace = {
  sawConclusionEvent: boolean;
  sawErrorEvent: boolean;
  sawDoneEvent: boolean;
  sawReasoningEvent: boolean;
  receivedEventCount: number;
  droppedByRequestMismatch: number;
  mismatchLogged: boolean;
  sawHitlAwaiting: boolean;
};

export type SupportedStreamLanguage = Language;

export type StreamingSwitchHelpers = {
  updateOrAddStep: (event: ThinkingEvent) => void;
  addToolCallToStep: (event: ThinkingEvent) => void;
  updateToolCallResult: (event: ThinkingEvent) => void;
  handleContextEnrichment: (event: ThinkingEvent) => void;
  handleTaskPlan: (event: ThinkingEvent) => void;
  extractDisplayReasoning: (raw: string) => string;
  reasoningBufferRef: MutableRefObject<string>;
  setCurrentReasoning: (v: string | ((p: string) => string)) => void;
  setConclusion: (v: string) => void;
  processConclusion: (content: string, input: string, lang: SupportedStreamLanguage) => void;
  handleTaskCreate: (event: ThinkingEvent) => void;
  handleTaskUpdate: (event: ThinkingEvent) => void;
  handleDecisionRequest: (event: ThinkingEvent) => void;
  handleUnderstanding: (event: ThinkingEvent) => void;
  handleParameterRequest: (event: ThinkingEvent) => void;
  pendingRequestIdRef: MutableRefObject<string>;
  handleTaskStart: (event: ThinkingEvent) => void;
  handleTaskStep: (event: ThinkingEvent) => void;
  handleTaskComplete: (event: ThinkingEvent) => void;
  setStreamEvents: Dispatch<SetStateAction<StreamEvent[]>>;
  setTaskPlan: Dispatch<SetStateAction<TaskPlan | null>>;
  handlePlanComplete: (event: ThinkingEvent) => void;
  setTaskSummary: (v: string) => void;
  setNextActions: (v: NextAction[]) => void;
  handleWorkflowStep: (event: ThinkingEvent) => void;
  setHitlAwaiting: (v: boolean) => void;
  setHitlSnapshot: (v: { interruptIds?: string[] } | null) => void;
};

/**
 * Shared SSE event dispatch for POST /analyze and POST /analyze/resume streams.
 */
export function applyStreamingSwitch(
  event: ThinkingEvent,
  trace: AnalyzeStreamTrace,
  currentLang: SupportedStreamLanguage,
  inputForConclusion: string,
  h: StreamingSwitchHelpers,
): void {
  switch (event.type) {
    case 'step':
      h.updateOrAddStep(event);
      break;

    case 'tool_call': {
      const presCall = effectiveToolPresentation(event);
      if (event.toolName && presCall !== 'task' && presCall !== 'state') {
        h.setStreamEvents((prev) => [
          ...prev,
          {
            type: 'tool_call',
            id: event.id || `tc-${Date.now()}`,
            timestamp: event.timestamp,
            toolName: event.toolName,
            toolInput: event.toolInput,
            ...(event.toolPresentation != null ? { toolPresentation: event.toolPresentation } : {}),
          },
        ]);
      }
      if (
        event.id === 'context_enrichment' ||
        (presCall === 'action' && isContextEnrichmentToolName(event.toolName))
      ) {
        h.handleContextEnrichment(event);
      }
      {
        const plan = buildTaskPlanFromWriteTodosToolCall(event, (idx) => String(idx));
        if (plan) {
          h.handleTaskPlan({
            type: 'task_plan',
            id: 'task-plan',
            plan,
          });
        }
      }
      h.addToolCallToStep(event);
      break;
    }

    case 'tool_result': {
      const presRes = effectiveToolPresentation(event);
      if (presRes !== 'task' && presRes !== 'state') {
        h.setStreamEvents((prev) => [
          ...prev,
          {
            type: 'tool_result',
            id: event.id || `tr-${Date.now()}`,
            timestamp: event.timestamp,
            toolName: event.toolName,
            toolOutput: event.toolOutput,
            ...(event.toolPresentation != null ? { toolPresentation: event.toolPresentation } : {}),
          },
        ]);
      }
      if (presRes === 'action' && isContextEnrichmentToolName(event.toolName)) {
        h.handleContextEnrichment(event);
      }
      h.updateToolCallResult(event);
      break;
    }

    case 'reasoning':
      trace.sawReasoningEvent = true;
      if (event.content) {
        const visibleReasoning = h.extractDisplayReasoning(event.content);
        if (visibleReasoning) {
          h.reasoningBufferRef.current += visibleReasoning;
          h.setCurrentReasoning(h.reasoningBufferRef.current);
        }
      }
      break;

    case 'llm_delta':
      if (String(event.channel) === 'reasoning' && event.content) {
        trace.sawReasoningEvent = true;
        const visibleReasoning = h.extractDisplayReasoning(event.content);
        if (visibleReasoning) {
          h.reasoningBufferRef.current += visibleReasoning;
          h.setCurrentReasoning(h.reasoningBufferRef.current);
        }
      }
      break;

    case 'llm_invoke_start':
    case 'llm_invoke_end':
      break;

    case 'answer':
      break;

    case 'conclusion':
      trace.sawConclusionEvent = true;
      h.setConclusion(event.content || '');
      h.processConclusion(event.content || '', inputForConclusion, currentLang);
      break;

    case 'task_create':
      h.handleTaskCreate(event);
      break;

    case 'task_update':
      h.handleTaskUpdate(event);
      break;

    case 'decision_request':
      h.handleDecisionRequest(event);
      break;

    case 'understanding':
      h.handleUnderstanding(event);
      break;

    case 'parameter_request':
      if (event.requestId || event.id) {
        h.pendingRequestIdRef.current = event.requestId || event.id;
      }
      if (Array.isArray(event.parameterRequests) && event.parameterRequests.length > 0) {
        const isClarification = event.interruptKind === 'user_input_v1';
        event.parameterRequests = event.parameterRequests.map((req) => ({
          ...req,
          isClarification: isClarification || req.isClarification === true,
        }));
      }
      h.handleParameterRequest(event);
      break;

    case 'task_plan':
      h.handleTaskPlan(event);
      break;

    case 'task_start':
      h.handleTaskStart(event);
      h.setStreamEvents((prev) => [
        ...prev,
        {
          type: 'task_start',
          id: event.id || `ts-${Date.now()}`,
          taskId: event.id,
          timestamp: event.timestamp,
        },
      ]);
      break;

    case 'task_step':
      h.handleTaskStep(event);
      break;

    case 'task_complete':
      h.handleTaskComplete(event);
      h.setStreamEvents((prev) => [
        ...prev,
        {
          type: 'task_complete',
          id: event.id || `tc-${Date.now()}`,
          taskId: event.id,
          taskStatus: 'success',
          timestamp: event.timestamp,
        },
      ]);
      break;

    case 'task_error':
      if (event.id) {
        h.setTaskPlan((prev) => {
          if (!prev) return prev;
          return {
            ...prev,
            tasks: prev.tasks.map((t) =>
              t.id === event.id ? { ...t, status: 'error' as const, error: event.detail } : t,
            ),
          };
        });
      }
      break;

    case 'plan_complete':
      h.handlePlanComplete(event);
      break;

    case 'task_summary':
      if (event.summary) {
        h.setTaskSummary(event.summary);
      }
      break;

    case 'next_actions':
      if (event.nextActions && event.nextActions.length > 0) {
        h.setNextActions(event.nextActions);
      }
      break;

    case 'workflow_step':
    case 'skill_start':
    case 'skill_complete':
    case 'skill_reasoning':
    case 'skill_error':
      h.handleWorkflowStep(event);
      break;

    case 'error':
      trace.sawErrorEvent = true;
      h.updateOrAddStep({
        ...event,
        status: 'error',
      });
      h.setTaskPlan((prev) => {
        if (!prev) return prev;
        const hasRunning = prev.tasks.some((t) => t.status === 'running');
        if (!hasRunning) return prev;
        return {
          ...prev,
          tasks: prev.tasks.map((t) =>
            t.status === 'running' ? { ...t, status: 'error' as const, error: event.detail } : t,
          ),
        };
      });
      break;

    case 'done':
      trace.sawDoneEvent = true;
      if (event.awaitingHuman === true) {
        trace.sawHitlAwaiting = true;
        h.setHitlAwaiting(true);
        h.setHitlSnapshot(event.hitl?.interruptIds != null ? { interruptIds: event.hitl.interruptIds } : event.hitl ?? null);
      }
      break;

    default:
      break;
  }
}
