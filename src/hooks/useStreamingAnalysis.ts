import { useState, useCallback, useRef, useEffect } from 'react';
import { ThinkingStep, ThinkingEvent, WorkspaceBlock, ToolCallInfo, StreamingAnalysisResult, AgentTask, DecisionRequest, InputUnderstanding, ParameterRequest, TaskPlan, PlannedTask, TaskStep, NextAction, AnalyzeAttachment, StreamEvent, ContextUsageState } from '@/types/analysis';
import { applyEventToContextUsage, createEmptyContextUsageState } from '@/lib/contextUsage';
import { analysisEndpoints } from '@/lib/config';
import { getLastSelectedModelIdForApi } from '@/lib/lastSelectedModel';
import { getAuthToken, getClientTimezoneHeaders } from '@/lib/api-client';
import { formatUserMessageForChat } from '@/lib/formatUserMessageDisplay';
import { unwrapStructuredUserPrompt } from '@/lib/unwrapStructuredUserPrompt';
import { shouldHideStepRow } from '@/lib/toolCallDisplay';
import { getTranslations, Language } from '@/i18n';
import { applyStreamingSwitch, type AnalyzeStreamTrace, type StreamingSwitchHelpers } from '@/hooks/applyStreamingSwitch';
import { readSseJsonLines } from '@/lib/sse/readSseJsonLines';
import { parseAnalysisEvent } from '@/lib/sse/parseAnalysisEvent';
import { logger } from '@/lib/logger';

/** Legacy single-session streaming hook (thinkingSteps/streamEvents). Prefer `useStreamingAnalysisMulti` + timeline. */

// Use centralized config for backend URL
const STREAM_URL = analysisEndpoints.stream;

type SupportedLanguage = Language;

const createRequestId = (): string => {
  if (typeof crypto !== 'undefined' && typeof crypto.randomUUID === 'function') {
    return crypto.randomUUID();
  }
  return `req-${Date.now()}-${Math.random().toString(36).slice(2, 10)}`;
};
// Re-export for backward compatibility
export type { SSEEventLog, AnalysisMode, AnalyzeAttachment } from '@/types/analysis';

export interface UseStreamingAnalysisOptions {
  /** Project ID for session isolation. Each project gets its own backend session/thread. */
  currentProjectId?: string | null;
}

/**
 * @deprecated Use useStreamingAnalysisMulti for multi-session support. This hook uses single shared state.
 */
export function useStreamingAnalysis(options: UseStreamingAnalysisOptions = {}) {
  const { currentProjectId } = options;
  const [thinkingSteps, setThinkingSteps] = useState<ThinkingStep[]>([]);
  const [blocks, setBlocks] = useState<WorkspaceBlock[]>([]);
  const [isAnalyzing, setIsAnalyzing] = useState(false);
  const [currentReasoning, setCurrentReasoning] = useState<string>('');
  const [tasks, setTasks] = useState<AgentTask[]>([]);
  const [decisions, setDecisions] = useState<DecisionRequest[]>([]);
  const [resolvedDecisions, setResolvedDecisions] = useState<Record<string, string[]>>({});
  const [understanding, setUnderstanding] = useState<InputUnderstanding | null>(null);
  const [parameterRequests, setParameterRequests] = useState<ParameterRequest[]>([]);
  const [parameterRequestDetail, setParameterRequestDetail] = useState<string | undefined>();
  const [submittedParameters, setSubmittedParameters] = useState<Record<string, string>>({});
  const [userInput, setUserInput] = useState<string>('');
  const [inputTimestamp, setInputTimestamp] = useState<Date | undefined>();
  const [thinkingStartTime, setThinkingStartTime] = useState<Date | undefined>();
  // Task planning state
  const [taskPlan, setTaskPlan] = useState<TaskPlan | null>(null);
  const [currentTaskId, setCurrentTaskId] = useState<string | undefined>();
  // Task summary and follow-up suggestions
  const [taskSummary, setTaskSummary] = useState<string>('');
  const [nextActions, setNextActions] = useState<NextAction[]>([]);
  // Conclusion content (for simple-question chat display)
  const [conclusion, setConclusion] = useState<string>('');
  const [currentRequestId, setCurrentRequestId] = useState<string>('');
  // Developer mode - SSE event logs
  const [sseEventLogs, setSSEEventLogs] = useState<SSEEventLog[]>([]);
  // Cursor-style unified stream (reasoning + tool_call + tool_result + task)
  const [streamEvents, setStreamEvents] = useState<StreamEvent[]>([]);
  // Analysis mode detection
  const [analysisMode, setAnalysisMode] = useState<AnalysisMode>('unknown');
  // Realtime context-usage indicator (per-session aggregation).
  const [contextUsage, setContextUsage] = useState<ContextUsageState>(() => createEmptyContextUsageState());
  const abortControllerRef = useRef<AbortController | null>(null);
  const reasoningBufferRef = useRef<string>('');
  const hasTaskPlanRef = useRef<boolean>(false);
  const isMountedRef = useRef(true);

  useEffect(() => {
    isMountedRef.current = true;
    return () => {
      isMountedRef.current = false;
      abortControllerRef.current?.abort();
    };
  }, []);

  // Log SSE events and detect analysis mode
  const logSSEEvent = useCallback((event: ThinkingEvent) => {
    const toPreviewString = (v: unknown): string => {
      if (typeof v === 'string') return v;
      if (v === null || v === undefined) return '';
      try {
        return JSON.stringify(v);
      } catch {
        return String(v);
      }
    };

    // IMPORTANT: ensure preview is always a string (React cannot render raw objects)
    // For debug events, prioritize error_message as preview
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

    // Detect analysis mode
    // DeepAgent signals: task_plan, task_start, task_step, understanding, etc.
    // Edge fallback signals: simple step/reasoning/conclusion events only
    // Current mode detection keeps DeepAgent only
    if (event.type === 'task_plan' || event.type === 'task_start' || event.type === 'understanding' || event.type === 'step') {
      setAnalysisMode('deepagent');
    }

    setSSEEventLogs(prev => {
      const newLog: SSEEventLog = {
        type: event.type,
        id: event.id || 'no-id',
        timestamp: typeof event.timestamp === 'number' ? event.timestamp : Date.now(),
        preview,
        rawData: event as unknown as Record<string, unknown>, // Keep full payload
      };
      // Keep only the latest 30 logs (expanded for debug events)
      const updated = [newLog, ...prev].slice(0, 30);
      return updated;
    });
  }, [analysisMode]);

  // Clear event logs
  const clearSSELogs = useCallback(() => {
    setSSEEventLogs([]);
  }, []);

  const extractDisplayReasoning = useCallback((rawContent: string): string => {
    if (!rawContent) return '';

    // Remove fenced blocks (especially ```json ... ```) and keep plain text.
    const withoutFencedBlocks = rawContent.replace(/```[\s\S]*?```/g, '').trim();

    // If the remaining content is still a pure intent JSON payload, don't render it.
    const isPureIntentJson =
      withoutFencedBlocks.startsWith('{') &&
      withoutFencedBlocks.endsWith('}') &&
      (
        withoutFencedBlocks.includes('"task_category"') ||
        withoutFencedBlocks.includes('"input_type"') ||
        withoutFencedBlocks.includes('"confidence"')
      );

    return isPureIntentJson ? '' : withoutFencedBlocks;
  }, []);

  const updateOrAddStep = useCallback((event: ThinkingEvent) => {
    // Skip internal events - they should not be displayed
    if (event.internal) {
      return;
    }
    if (event.type === 'step' && shouldHideStepRow({ type: 'step', id: event.id })) {
      return;
    }

    setThinkingSteps(prev => {
      const existingIndex = prev.findIndex(s => s.id === event.id);
      
      if (existingIndex >= 0) {
        return prev.map((s, i) => 
          i === existingIndex 
            ? { 
                ...s, 
                label: event.label || s.label,
                status: event.status || s.status,
                detail: event.detail || s.detail,
                timestamp: event.timestamp || s.timestamp,
                internal: event.internal,
              }
            : s
        );
      } else {
        return [...prev, {
          id: event.id,
          label: event.label || '',
          status: event.status || 'pending',
          detail: event.detail,
          timestamp: event.timestamp,
          internal: event.internal,
        }];
      }
    });
  }, []);

  const addToolCallToStep = useCallback((event: ThinkingEvent) => {
    const toolCall: ToolCallInfo = {
      id: event.id,
      toolName: event.toolName || '',
      toolInput: event.toolInput,
      status: event.status || 'running',
      timestamp: event.timestamp
    };

    setThinkingSteps(prev => {
      const runningIndex = prev.findIndex(s => s.status === 'running');
      if (runningIndex >= 0) {
        return prev.map((s, i) => 
          i === runningIndex 
            ? { 
                ...s, 
                toolCalls: [...(s.toolCalls || []), toolCall]
              }
            : s
        );
      }
      return prev;
    });
  }, []);

  const updateToolCallResult = useCallback((event: ThinkingEvent) => {
    setThinkingSteps(prev => {
      return prev.map(step => {
        if (step.toolCalls?.some(tc => tc.toolName === event.toolName && tc.status === 'running')) {
          return {
            ...step,
            toolCalls: step.toolCalls.map(tc => 
              tc.toolName === event.toolName && tc.status === 'running'
                ? { ...tc, toolOutput: event.toolOutput, status: event.status || 'success' }
                : tc
            )
          };
        }
        return step;
      });
    });
  }, []);

  // Task management
  const handleTaskCreate = useCallback((event: ThinkingEvent) => {
    if (event.task && 'title' in event.task && !('taskType' in event.task)) {
      setTasks(prev => [...prev, event.task as AgentTask]);
    }
  }, []);

  const handleTaskUpdate = useCallback((event: ThinkingEvent) => {
    if (event.id && event.taskStatus) {
      setTasks(prev => prev.map(task => 
        task.id === event.id 
          ? { ...task, status: event.taskStatus! }
          : task
      ));
    }
  }, []);

  // Decision management
  const handleDecisionRequest = useCallback((event: ThinkingEvent) => {
    if (event.decision) {
      setDecisions(prev => [...prev, event.decision!]);
    }
  }, []);

  const handleDecision = useCallback((requestId: string, selectedOptions: string[]) => {
    setResolvedDecisions(prev => ({
      ...prev,
      [requestId]: selectedOptions
    }));
    
    // TODO: Send decision back to backend via WebSocket or API
    logger.debug('decision_made', { requestId, selectedOptions });
  }, []);

  const handleUnderstanding = useCallback((event: ThinkingEvent) => {
    if (event.understanding) {
      setUnderstanding(event.understanding);
      if (event.understanding.parameterRequests && event.understanding.parameterRequests.length > 0) {
        setParameterRequests(event.understanding.parameterRequests);
      }
    }
  }, []);

  const handleContextEnrichment = useCallback((_event: ThinkingEvent) => {
    // Legacy no-op: intent-phase context-query UI removed; main agent tools are shown via steps/stream.
  }, []);

  // Parameter request management
  const handleParameterRequest = useCallback((event: ThinkingEvent) => {
    if (event.parameterRequests && event.parameterRequests.length > 0) {
      setParameterRequests(event.parameterRequests);
      setParameterRequestDetail(typeof event.detail === 'string' ? event.detail : undefined);
    }
  }, []);

  // Task plan management
  const handleTaskPlan = useCallback((event: ThinkingEvent) => {
    if (!event.plan) return;
    hasTaskPlanRef.current = true;

    // IMPORTANT: The backend may send multiple plan snapshots. Some of them can be partial and
    // miss step history, which would make the UI look like the execution process “disappeared”.
    // We merge with the existing plan to preserve already-received step details.
    setTaskPlan(prev => {
      const incoming = event.plan as TaskPlan;
      if (!prev) return incoming;

      const prevById = new Map(prev.tasks.map(t => [t.id, t] as const));
      const incomingIds = new Set(incoming.tasks.map(t => t.id));

      const mergedTasks = incoming.tasks.map(t => {
        const existing = prevById.get(t.id);
        if (!existing) return t;

        const incomingSteps = (t.steps || []).filter(Boolean);
        const prevSteps = (existing.steps || []).filter(Boolean);

        return {
          ...existing,
          ...t,
          // Never drop richer fields that may only exist locally from streaming events
          result: (t as PlannedTask).result ?? (existing as PlannedTask).result,
          error: (t as PlannedTask).error ?? (existing as PlannedTask).error,
          durationMs: (t as PlannedTask).durationMs || (existing as PlannedTask).durationMs,
          skillName: (t as PlannedTask).skillName ?? (existing as PlannedTask).skillName,
          steps: incomingSteps.length > 0 ? incomingSteps : prevSteps,
        } as PlannedTask;
      });

      const extras = prev.tasks.filter(t => !incomingIds.has(t.id));

      return {
        ...prev,
        ...incoming,
        totalDurationMs: incoming.totalDurationMs || prev.totalDurationMs,
        tasks: [...mergedTasks, ...extras],
      };
    });
  }, []);

  const handleTaskStart = useCallback((event: ThinkingEvent) => {
    const taskId = event.id;
    if (taskId) {
      setCurrentTaskId(taskId);
      setTaskPlan(prev => {
        if (!prev) return prev;
        return {
          ...prev,
          tasks: prev.tasks.map(t => 
            t.id === taskId ? { ...t, status: 'running' as const } : t
          ),
        };
      });
    }
  }, []);

  const handleTaskStep = useCallback((event: ThinkingEvent) => {
    const taskId = event.taskId;
    const step = event.step;
    if (taskId && step) {
      setTaskPlan(prev => {
        if (!prev) return prev;
        return {
          ...prev,
          tasks: prev.tasks.map(t => {
            if (t.id === taskId) {
              const existingStepIndex = t.steps.findIndex(s => s.id === step.id);
              if (existingStepIndex >= 0) {
                return {
                  ...t,
                  steps: t.steps.map((s, i) => i === existingStepIndex ? step : s),
                };
              }
              return {
                ...t,
                steps: [...t.steps, step],
              };
            }
            return t;
          }),
        };
      });
    }
  }, []);

  const mergePlannedTask = useCallback((prevTask: PlannedTask, incomingTask: PlannedTask): PlannedTask => {
    // Preserve detailed step history if backend sends an empty/partial task snapshot at the end.
    const incomingSteps = (incomingTask.steps || []).filter(Boolean);
    const prevSteps = (prevTask.steps || []).filter(Boolean);

    return {
      ...prevTask,
      ...incomingTask,
      // Prefer incoming fields when present, but never drop existing rich data.
      result: incomingTask.result ?? prevTask.result,
      error: incomingTask.error ?? prevTask.error,
      durationMs: incomingTask.durationMs || prevTask.durationMs,
      skillName: incomingTask.skillName ?? prevTask.skillName,
      steps: incomingSteps.length > 0 ? incomingSteps : prevSteps,
    };
  }, []);

  const mergeTaskPlan = useCallback((prevPlan: TaskPlan, incomingPlan: TaskPlan): TaskPlan => {
    const prevById = new Map(prevPlan.tasks.map(t => [t.id, t] as const));
    const incomingIds = new Set(incomingPlan.tasks.map(t => t.id));

    const mergedTasks = incomingPlan.tasks.map(t => {
      const existing = prevById.get(t.id);
      return existing ? mergePlannedTask(existing, t) : t;
    });

    // Keep any tasks that existed locally but are missing from incoming snapshot
    const extras = prevPlan.tasks.filter(t => !incomingIds.has(t.id));

    return {
      ...prevPlan,
      ...incomingPlan,
      totalDurationMs: incomingPlan.totalDurationMs || prevPlan.totalDurationMs,
      tasks: [...mergedTasks, ...extras],
    };
  }, [mergePlannedTask]);

  const handleTaskComplete = useCallback((event: ThinkingEvent) => {
    const taskId = event.id;
    if (!taskId) return;

    setTaskPlan(prev => {
      if (!prev) return prev;
      return {
        ...prev,
        tasks: prev.tasks.map(t => {
          if (t.id !== taskId) return t;

          // Backend may include a task snapshot (often missing steps). Merge to avoid losing history.
          if (event.task && 'taskType' in event.task) {
            return mergePlannedTask(t, {
              ...(event.task as PlannedTask),
              status: 'success' as const,
            });
          }

          return { ...t, status: 'success' as const };
        }),
      };
    });

    setCurrentTaskId(undefined);
  }, [mergePlannedTask]);

  const handlePlanComplete = useCallback((event: ThinkingEvent) => {
    if (!event.plan) return;

    // IMPORTANT: Python security execution streams real steps, but its final plan snapshot may omit them.
    // We merge to prevent the UI from "dropping" the execution process after completion.
    setTaskPlan(prev => (prev ? mergeTaskPlan(prev, event.plan as TaskPlan) : (event.plan as TaskPlan)));
  }, [mergeTaskPlan]);

  // Handle workflow step events from SubAgentMiddleware
  // These are real-time SOP steps mapped to skill workflow_steps
  const handleWorkflowStep = useCallback((event: ThinkingEvent) => {
    // Convert workflow events to task_step format
    const step: TaskStep = {
      id: event.id || `workflow-${Date.now()}`,
      label: event.label || event.toolName || 'Step',
      status: (event.status as TaskStep['status']) || 'running',
      detail: event.detail || '',
      toolName: event.toolName,
      timestamp: event.timestamp,
    };
    
    // For skill_start/complete, also update thinking steps for visibility
    if (event.type === 'skill_start' || event.type === 'skill_complete') {
      updateOrAddStep({
        ...event,
        type: 'step',
      });
    }
    
    // If there is a current task, append/update step there
    setTaskPlan(prev => {
      if (!prev || prev.tasks.length === 0) {
        // No plan yet - create a temporary one
        return {
          id: 'temp-plan',
          tasks: [{
            id: 'temp-task',
            title: 'Security Analysis',
            description: '',
            taskType: 'security' as const,
            priority: 1,
            status: 'running' as const,
            durationMs: 0,
            steps: [step],
          }],
          isSingleTask: true,
          totalDurationMs: 0,
          status: 'running' as const,
          createdAt: new Date().toISOString(),
        };
      }
      
      // Pick the running task, or fall back to the first task
      const runningTaskIndex = prev.tasks.findIndex(t => t.status === 'running');
      const targetIndex = runningTaskIndex >= 0 ? runningTaskIndex : 0;
      
      return {
        ...prev,
        tasks: prev.tasks.map((t, i) => {
          if (i !== targetIndex) return t;
          
          // Check whether this step already exists
          const existingIndex = t.steps.findIndex(s => s.id === step.id);
          if (existingIndex >= 0) {
            // Update existing step
            return {
              ...t,
              steps: t.steps.map((s, si) => si === existingIndex ? step : s),
            };
          }
          // Add new step
          return {
            ...t,
            steps: [...t.steps, step],
          };
        }),
      };
    });
    
    // Also reflect tool events in the thinking chain display
    if (event.type === 'tool_call' || event.type === 'tool_result') {
      if (event.type === 'tool_call') {
        addToolCallToStep(event);
      } else {
        updateToolCallResult(event);
      }
    }
  }, [updateOrAddStep, addToolCallToStep, updateToolCallResult]);

  // Session ID: bind to project for isolation. Each project gets its own backend thread/checkpoint.
  const fallbackSessionRef = useRef<string>(`session-${Date.now()}-${Math.random().toString(36).slice(2)}`);
  const effectiveSessionId = currentProjectId ?? fallbackSessionRef.current;
  const pendingRequestIdRef = useRef<string>('');
  const activeRequestIdRef = useRef<string>('');
  const [isSubmittingParameters, setIsSubmittingParameters] = useState(false);
  const [isWaitingForResume, setIsWaitingForResume] = useState(false);
  const [hitlAwaiting, setHitlAwaiting] = useState(false);
  const [hitlSnapshot, setHitlSnapshot] = useState<{ interruptIds?: string[] } | null>(null);
  const pendingInputRef = useRef<string>('');
  const pendingLanguageRef = useRef<SupportedLanguage>('en');

  // Handle parameter submission - send to backend and resume analysis
  const handleParameterSubmit = useCallback(async (parameters: Record<string, string>) => {
    setIsSubmittingParameters(true);
    
    try {
      const headers: Record<string, string> = {
        ...getClientTimezoneHeaders(),
        'Content-Type': 'application/json',
        'x-session-id': effectiveSessionId,
        'x-request-id': pendingRequestIdRef.current,
      };
      
      const token = getAuthToken();
      if (token) {
        headers['Authorization'] = `Bearer ${token}`;
      }
      
      const response = await fetch(analysisEndpoints.submitParameters, {
        method: 'POST',
        headers,
        body: JSON.stringify({
          sessionId: effectiveSessionId,
          requestId: pendingRequestIdRef.current,
          parameters,
        }),
      });
      
      if (!response.ok) {
        const errorData = await response.json().catch(() => ({}));
        throw new Error(errorData.error || `HTTP ${response.status}`);
      }
      
      const result = await response.json();
      logger.debug('parameters_submitted', { result });
      
      // Update local state
      setSubmittedParameters(prev => ({ ...prev, ...parameters }));
      setParameterRequests([]);
      setParameterRequestDetail(undefined);
      
      // Resume analysis with submitted parameters
      if (pendingInputRef.current) {
        setIsWaitingForResume(true);
        
        // Add a step to indicate resume is in progress
        setThinkingSteps(prev => [...prev, {
          id: `resume-${Date.now()}`,
          label: getTranslations(pendingLanguageRef.current).streaming.resumeRunning,
          status: 'running',
          timestamp: Date.now()
        }]);

        // Short delay to allow backend parameter processing
        await new Promise(resolve => setTimeout(resolve, 500));
        
        // Resume with append mode and include parameter context
        const resumeInput = buildResumeInput(pendingInputRef.current, parameters, pendingLanguageRef.current);
        
        // Call streaming endpoint with resume context
        await resumeAnalysis(resumeInput, parameters, pendingLanguageRef.current);
      }
      
      pendingRequestIdRef.current = '';
      
    } catch (error) {
      logger.error('parameters_submit_failed', { error: String(error) });
      // Keep form open so the user can retry
    } finally {
      setIsSubmittingParameters(false);
      setIsWaitingForResume(false);
    }
  }, []);

  // Build resume input using parameter context
  const buildResumeInput = (originalInput: string, parameters: Record<string, string>, lang: SupportedLanguage): string => {
    const paramContext = Object.entries(parameters)
      .map(([key, value]) => `${key}: ${value.substring(0, 50)}${value.length > 50 ? '...' : ''}`)
      .join('\n');

    return getTranslations(lang).streaming.resumeInputTemplate
      .replace('{originalInput}', originalInput)
      .replace('{paramContext}', paramContext);
  };

  const processConclusion = useCallback((content: string, input: string, lang: SupportedLanguage = 'en') => {
    // Direct reply (no task_plan): do not create workspace blocks or tabs
    if (!hasTaskPlanRef.current) {
      return;
    }

    const text = getTranslations(lang).streaming;
    const newBlocks: WorkspaceBlock[] = [];

    // Try parsing as JSON first
    let result: StreamingAnalysisResult | null = null;
    try {
      result = JSON.parse(content);
    } catch {
      // Not JSON - treat as markdown/text content
      logger.debug('process_conclusion_markdown_fallback');
    }

    if (result) {
      // JSON format - structured report
      // Summary block
      newBlocks.push({
        type: 'summary',
        id: 'summary-1',
        severity: result.severity || 'info',
        title: result.title || text.analysisReport,
        description: result.summary || text.analysisComplete
      });

      // Original evidence
      newBlocks.push({
        type: 'text',
        id: 'heading-evidence',
        content: text.originalEvidence,
        variant: 'heading'
      });

      // Build highlights
      const highlights: { start: number; end: number; type: 'ip' | 'url' | 'payload' }[] = [];
      
      result.entities?.ips?.forEach(ip => {
        const idx = input.indexOf(ip);
        if (idx !== -1) {
          highlights.push({ start: idx, end: idx + ip.length, type: 'ip' });
        }
      });

      result.entities?.urls?.forEach(url => {
        const idx = input.indexOf(url);
        if (idx !== -1) {
          highlights.push({ start: idx, end: idx + url.length, type: 'url' });
        }
      });

      // Detect payload patterns
      const payloadPatterns = ['${jndi:', 'eval(', '<script', 'base64,'];
      payloadPatterns.forEach(pattern => {
        let searchStart = 0;
        while (true) {
          const idx = input.indexOf(pattern, searchStart);
          if (idx === -1) break;
          highlights.push({ start: idx, end: idx + pattern.length + 20, type: 'payload' });
          searchStart = idx + 1;
        }
      });

      newBlocks.push({
        type: 'log',
        id: 'log-original',
        content: input,
        highlights
      });

      // Decodings
      if (result.decodings?.length > 0) {
        newBlocks.push({
          type: 'text',
          id: 'heading-decode',
          content: text.decodingAnalysis,
          variant: 'heading'
        });

        result.decodings.forEach((decoding, idx) => {
          newBlocks.push({
            type: 'decoder',
            id: `decoder-${idx}`,
            encoded: decoding.encoded,
            decoded: decoding.decoded,
            algorithm: decoding.algorithm
          });
        });
      }

      // Threat intelligence
      const allIndicators = [
        ...(result.entities?.ips || []),
        ...(result.entities?.domains || []),
        ...(result.entities?.hashes || [])
      ];

      if (allIndicators.length > 0) {
        newBlocks.push({
          type: 'text',
          id: 'heading-intel',
          content: text.threatIntelligence,
          variant: 'heading'
        });

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
            tags: result?.intelTags?.slice(0, 5)
          });
        });
      }

      // Attack patterns
      if (result.attackPatterns?.length > 0) {
        newBlocks.push({
          type: 'text',
          id: 'heading-patterns',
          content: text.attackPatterns,
          variant: 'heading'
        });

        result.attackPatterns.forEach((pattern, idx) => {
          newBlocks.push({
            type: 'text',
            id: `pattern-${idx}`,
            content: pattern,
            variant: 'bullet'
          });
        });
      }

      // Threat indicators
      if (result.threatIndicators?.length > 0) {
        newBlocks.push({
          type: 'text',
          id: 'heading-threats',
          content: text.threatIndicators,
          variant: 'heading'
        });

        result.threatIndicators.forEach((threat, idx) => {
          newBlocks.push({
            type: 'text',
            id: `threat-${idx}`,
            content: threat,
            variant: 'bullet'
          });
        });
      }

      // Recommendations
      if (result.recommendations?.length > 0) {
        newBlocks.push({
          type: 'text',
          id: 'heading-action',
          content: text.recommendations,
          variant: 'heading'
        });

        result.recommendations.forEach((rec, idx) => {
          newBlocks.push({
            type: 'text',
            id: `rec-${idx}`,
            content: rec,
            variant: 'bullet'
          });
        });
      }

      // Full analysis from DeepAgent (if available)
      if (result.fullAnalysis) {
        newBlocks.push({
          type: 'analysis',
          id: 'full-analysis',
          content: result.fullAnalysis,
          title: text.deepAgentDetailedAnalysis
        });
      }
    } else {
      // Plain markdown/text content - create analysis block directly
      if (content && content.trim().length > 0) {
        newBlocks.push({
          type: 'analysis',
          id: 'full-analysis',
          content: content,
          title: text.analysisReportTitle
        });
      }
    }

    if (newBlocks.length > 0) {
      setBlocks(newBlocks);
    }
  }, []);

  // Resume analysis after parameter submission
  const resumeAnalysis = useCallback(async (
    resumeInput: string, 
    parameters: Record<string, string>,
    language: SupportedLanguage,
  ) => {
    try {
      const headers: Record<string, string> = {
        ...getClientTimezoneHeaders(),
        'Content-Type': 'application/json',
      };
      
      const token = getAuthToken();
      if (token) {
        headers['Authorization'] = `Bearer ${token}`;
      }

      const response = await fetch(STREAM_URL, {
        method: 'POST',
        headers,
        body: JSON.stringify({ 
          input: resumeInput, 
          language,
          session_id: effectiveSessionId,
          parameters,  // Include parameters for backend context
          resume: true  // Flag indicating a resume request
        }),
      });

      if (!response.ok) {
        throw new Error(`HTTP ${response.status}`);
      }

      const reader = response.body?.getReader();
      if (!reader) throw new Error('No response body');

      const decoder = new TextDecoder();
      for await (const raw of readSseJsonLines(reader, decoder)) {
        try {
          const event = parseAnalysisEvent(raw);
          switch (event.type) {
            case 'step':
              updateOrAddStep(event);
              break;
            case 'tool_call':
              addToolCallToStep(event);
              break;
            case 'tool_result':
              updateToolCallResult(event);
              break;
            case 'reasoning':
              if (event.content) {
                reasoningBufferRef.current += event.content;
                setCurrentReasoning(reasoningBufferRef.current);
              }
              break;
            case 'llm_delta':
              if (String(event.channel) === 'reasoning' && event.content) {
                reasoningBufferRef.current += event.content;
                setCurrentReasoning(reasoningBufferRef.current);
              }
              break;
            case 'llm_invoke_start':
            case 'llm_invoke_end':
            case 'context_summarized':
              setContextUsage((prev) => applyEventToContextUsage(prev, event));
              break;
            case 'answer':
              break;
            case 'conclusion':
              processConclusion(event.content || '', pendingInputRef.current, language);
              break;
            case 'error':
              updateOrAddStep({ ...event, status: 'error' });
              break;
            case 'done':
              break;
          }
        } catch {
          // Ignore malformed events
        }
      }

      // Mark resume step as success
      const resumeRunningLabel = getTranslations(language).streaming.resumeRunning;
      setThinkingSteps(prev => prev.map(step => 
        step.label === resumeRunningLabel
          ? { ...step, status: 'success' }
          : step
      ));

    } catch (error) {
      logger.error('resume_analysis_error', { error: String(error) });
      setThinkingSteps(prev => [...prev, {
        id: 'resume-error',
        label: getTranslations(language).streaming.resumeFailed,
        status: 'error',
        detail: (error as Error)?.message
      }]);
    }
  }, [updateOrAddStep, addToolCallToStep, updateToolCallResult, processConclusion]);

  const analyzeInput = useCallback(async (
    input: string,
    appendMode: boolean = false,
    language: SupportedLanguage = 'en',
    attachments: AnalyzeAttachment[] = [],
  ) => {
    const messageText = unwrapStructuredUserPrompt(input);
    const requestId = createRequestId();
    activeRequestIdRef.current = requestId;
    setCurrentRequestId(requestId);
    const trace: AnalyzeStreamTrace = {
      sawConclusionEvent: false,
      sawErrorEvent: false,
      sawDoneEvent: false,
      sawReasoningEvent: false,
      receivedEventCount: 0,
      droppedByRequestMismatch: 0,
      mismatchLogged: false,
      sawHitlAwaiting: false,
    };
    setIsAnalyzing(true);

    hasTaskPlanRef.current = false;

    // Always reset task-related state for a new analysis
    setTaskPlan(null);
    setCurrentTaskId(undefined);
    setTaskSummary('');
    setNextActions([]);
    setUnderstanding(null);
    setConclusion('');
    setStreamEvents([]);
    
    // Always clear blocks so each analysis starts fresh (avoids showing previous result).
    setBlocks([]);
    // In append mode, keep conversation history; otherwise do a full reset
    if (!appendMode) {
      setThinkingSteps([]);
      setTasks([]);
      setDecisions([]);
      setResolvedDecisions({});
      setParameterRequests([]);
      setParameterRequestDetail(undefined);
    }
    setCurrentReasoning('');
    setUserInput(formatUserMessageForChat(messageText, attachments));
    setInputTimestamp(new Date());
    setThinkingStartTime(new Date());
    reasoningBufferRef.current = '';

    // Store input and language for post-parameter resume
    pendingInputRef.current = messageText;
    pendingLanguageRef.current = language;

    // Store language for processConclusion
    const currentLang = language;

    const streamHelpers: StreamingSwitchHelpers = {
      updateOrAddStep,
      addToolCallToStep,
      updateToolCallResult,
      handleContextEnrichment,
      handleTaskPlan,
      extractDisplayReasoning,
      reasoningBufferRef,
      setCurrentReasoning,
      setConclusion,
      processConclusion,
      handleTaskCreate,
      handleTaskUpdate,
      handleDecisionRequest,
      handleUnderstanding,
      handleParameterRequest,
      pendingRequestIdRef,
      handleTaskStart,
      handleTaskStep,
      handleTaskComplete,
      setStreamEvents,
      setTaskPlan,
      handlePlanComplete,
      setTaskSummary,
      setNextActions,
      handleWorkflowStep,
      setHitlAwaiting,
      setHitlSnapshot,
    };

    if (abortControllerRef.current) {
      abortControllerRef.current.abort();
    }
    abortControllerRef.current = new AbortController();

    try {
      const headers: Record<string, string> = {
        ...getClientTimezoneHeaders(),
        'Content-Type': 'application/json',
      };
      
      // Add auth header if logged in (optional, useful for user tracking)
      const token = getAuthToken();
      if (token) {
        headers['Authorization'] = `Bearer ${token}`;
      }

      const response = await fetch(STREAM_URL, {
        method: 'POST',
        headers,
        body: JSON.stringify({
          message: messageText,
          attachments,
          analysis_scope: 'all_input',
          stream: true,
          language: currentLang,
          ui_language: currentLang,
          session_id: effectiveSessionId,
          request_id: requestId,
        }),
        signal: abortControllerRef.current.signal
      });

      logger.info('streaming_analysis_request_start', {
        request_id: requestId,
        session_id: effectiveSessionId,
        input_length: input.length,
        attachment_count: attachments.length,
      });

      if (!response.ok) {
        const errorData = await response.json().catch(() => ({}));
        logger.error('streaming_analysis_response_error', { status: response.status, detail: errorData });
        throw new Error(errorData.error || `HTTP ${response.status}`);
      }

      logger.debug('streaming_analysis_stream_read_start');

      const reader = response.body?.getReader();
      if (!reader) throw new Error('No response body');

      const decoder = new TextDecoder();
      for await (const raw of readSseJsonLines(reader, decoder, {
        shouldAbort: () =>
          activeRequestIdRef.current !== requestId || !isMountedRef.current,
      })) {
        if (!isMountedRef.current) break;
        try {
          const event = parseAnalysisEvent(raw);
          logger.debug('streaming_analysis_event_received', { type: event.type, id: event.id });

          if (event.requestId && event.requestId !== activeRequestIdRef.current) {
            trace.droppedByRequestMismatch += 1;
            if (!trace.mismatchLogged) {
              trace.mismatchLogged = true;
            }
            continue;
          }
          trace.receivedEventCount += 1;

          logSSEEvent(event);

          if (event.internal) {
            logger.debug('streaming_analysis_skip_internal_event', { id: event.id });
            continue;
          }

          applyStreamingSwitch(event, trace, currentLang, pendingInputRef.current, streamHelpers);
        } catch (e) {
          logger.warn('streaming_analysis_event_handling_error', { error: String(e), payload_preview: String(raw).slice(0, 200) });
        }
      }

      logger.info('streaming_analysis_stream_completed');

    } catch (error) {
      if (activeRequestIdRef.current !== requestId) {
        return;
      }
      if ((error as Error).name === 'AbortError') {
        logger.info('streaming_analysis_aborted');
        return;
      }

      const text = getTranslations(currentLang).streaming;
      const msg = (error as Error)?.message || String(error);
      
      // Determine the appropriate user-facing error message
      let friendly = msg;
      if (msg.includes('Failed to fetch') || msg.includes('NetworkError')) {
        friendly = text.networkError;
      } else if (msg.includes('401') || msg.includes('Unauthorized')) {
        friendly = text.sessionExpired;
      } else if (msg.includes('CORS')) {
        friendly = text.networkError;
      }

      logger.error('streaming_analysis_error', { error: msg, url: STREAM_URL });
      logger.warn('streaming_analysis_request_trace_failed', {
        request_id: requestId,
        saw_conclusion: trace.sawConclusionEvent,
        saw_error: trace.sawErrorEvent,
        saw_done: trace.sawDoneEvent,
        sawReasoningEvent: trace.sawReasoningEvent,
        receivedEventCount: trace.receivedEventCount,
        droppedByRequestMismatch: trace.droppedByRequestMismatch,
      });

      if (!isMountedRef.current) return;

      // Mark all running tasks as error when stream fails (network/other exception)
      setTaskPlan(prev => {
        if (!prev) return prev;
        const hasRunning = prev.tasks.some(t => t.status === 'running');
        if (!hasRunning) return prev;
        return {
          ...prev,
          tasks: prev.tasks.map(t =>
            t.status === 'running' ? { ...t, status: 'error' as const, error: friendly } : t
          ),
        };
      });

      setThinkingSteps(prev => [...prev, {
        id: 'error',
        label: text.analysisFailed,
        status: 'error',
        detail: friendly,
      }]);

      setBlocks([{
        type: 'summary',
        id: 'summary-error',
        severity: 'medium',
        title: text.analysisFailed,
        description: friendly || text.checkNetwork,
      }]);

    } finally {
      if (isMountedRef.current && activeRequestIdRef.current === requestId) {
        if (!trace.sawConclusionEvent && !trace.sawErrorEvent) {
          logger.warn('streaming_analysis_no_conclusion', {
            request_id: requestId,
            saw_done: trace.sawDoneEvent,
            saw_reasoning: trace.sawReasoningEvent,
            event_count: trace.receivedEventCount,
            dropped_mismatch: trace.droppedByRequestMismatch,
          });
        } else {
          logger.info('streaming_analysis_request_trace_complete', {
            request_id: requestId,
            saw_conclusion: trace.sawConclusionEvent,
            saw_error: trace.sawErrorEvent,
            saw_done: trace.sawDoneEvent,
            saw_reasoning: trace.sawReasoningEvent,
            event_count: trace.receivedEventCount,
            droppedByRequestMismatch: trace.droppedByRequestMismatch,
          });
        }
        if (!trace.sawHitlAwaiting) {
          setHitlAwaiting(false);
          setHitlSnapshot(null);
        }
        setIsAnalyzing(false);
        setCurrentRequestId('');
        activeRequestIdRef.current = '';
      }
      abortControllerRef.current = null;
    }
  }, [
    updateOrAddStep,
    addToolCallToStep,
    updateToolCallResult,
    processConclusion,
    handleTaskCreate,
    handleTaskUpdate,
    handleDecisionRequest,
    handleUnderstanding,
    handleTaskPlan,
    handleTaskStart,
    handleTaskStep,
    handleTaskComplete,
    handlePlanComplete,
    extractDisplayReasoning,
    effectiveSessionId,
    logSSEEvent,
    handleContextEnrichment,
    handleParameterRequest,
    handleWorkflowStep,
  ]);

  const submitHitlResume = useCallback(
    async (resume: unknown, language: SupportedLanguage = 'en') => {
      const requestId = createRequestId();
      activeRequestIdRef.current = requestId;
      setCurrentRequestId(requestId);
      const trace: AnalyzeStreamTrace = {
        sawConclusionEvent: false,
        sawErrorEvent: false,
        sawDoneEvent: false,
        sawReasoningEvent: false,
        receivedEventCount: 0,
        droppedByRequestMismatch: 0,
        mismatchLogged: false,
        sawHitlAwaiting: false,
      };

      const streamHelpers: StreamingSwitchHelpers = {
        updateOrAddStep,
        addToolCallToStep,
        updateToolCallResult,
        handleContextEnrichment,
        handleTaskPlan,
        extractDisplayReasoning,
        reasoningBufferRef,
        setCurrentReasoning,
        setConclusion,
        processConclusion,
        handleTaskCreate,
        handleTaskUpdate,
        handleDecisionRequest,
        handleUnderstanding,
        handleParameterRequest,
        pendingRequestIdRef,
        handleTaskStart,
        handleTaskStep,
        handleTaskComplete,
        setStreamEvents,
        setTaskPlan,
        handlePlanComplete,
        setTaskSummary,
        setNextActions,
        handleWorkflowStep,
        setHitlAwaiting,
        setHitlSnapshot,
      };

      setIsAnalyzing(true);
      setHitlAwaiting(false);
      setHitlSnapshot(null);

      if (abortControllerRef.current) {
        abortControllerRef.current.abort();
      }
      abortControllerRef.current = new AbortController();

      try {
        const headers: Record<string, string> = {
          ...getClientTimezoneHeaders(),
          'Content-Type': 'application/json',
        };
        const token = getAuthToken();
        if (token) {
          headers['Authorization'] = `Bearer ${token}`;
        }

        const resumeModelId = getLastSelectedModelIdForApi();
        const response = await fetch(analysisEndpoints.resumeStream, {
          method: 'POST',
          headers,
          body: JSON.stringify({
            session_id: effectiveSessionId,
            resume,
            request_id: requestId,
            ...(currentProjectId != null && currentProjectId !== ''
              ? { project_id: currentProjectId }
              : {}),
            ui_language: language,
            ...(resumeModelId ? { model_id: resumeModelId } : {}),
          }),
          signal: abortControllerRef.current.signal,
        });

        if (!response.ok) {
          const errBody = (await response.json().catch(() => ({}))) as {
            detail?: unknown;
            error?: unknown;
          };
          const detail = errBody.detail ?? errBody.error;
          throw new Error(
            typeof detail === 'string'
              ? detail
              : detail != null
                ? JSON.stringify(detail)
                : `HTTP ${response.status}`,
          );
        }

        const reader = response.body?.getReader();
        if (!reader) throw new Error('No response body');

        const decoder = new TextDecoder();
        for await (const raw of readSseJsonLines(reader, decoder, {
          shouldAbort: () =>
            activeRequestIdRef.current !== requestId || !isMountedRef.current,
        })) {
          if (!isMountedRef.current) break;
          try {
            const event = parseAnalysisEvent(raw);
            if (event.requestId && event.requestId !== activeRequestIdRef.current) {
              trace.droppedByRequestMismatch += 1;
              if (!trace.mismatchLogged) trace.mismatchLogged = true;
              continue;
            }
            trace.receivedEventCount += 1;
            logSSEEvent(event);
            if (event.internal) continue;
            applyStreamingSwitch(event, trace, language, pendingInputRef.current, streamHelpers);
          } catch (e) {
            logger.warn('streaming_analysis_hitl_resume_event_error', { error: String(e), payload_preview: String(raw).slice(0, 200) });
          }
        }
      } catch (error) {
        if (activeRequestIdRef.current !== requestId) return;
        if ((error as Error).name === 'AbortError') return;

        setHitlAwaiting(true);
        const text = getTranslations(language).streaming;
        const msg = (error as Error)?.message || String(error);
        if (!isMountedRef.current) return;
        setThinkingSteps((prev) => [
          ...prev,
          {
            id: 'hitl-resume-error',
            label: text.analysisFailed,
            status: 'error',
            detail: msg,
          },
        ]);
      } finally {
        if (isMountedRef.current && activeRequestIdRef.current === requestId) {
          if (!trace.sawHitlAwaiting) {
            setHitlAwaiting(false);
            setHitlSnapshot(null);
          }
          setIsAnalyzing(false);
          setCurrentRequestId('');
          activeRequestIdRef.current = '';
        }
        abortControllerRef.current = null;
      }
    },
    [
      effectiveSessionId,
      currentProjectId,
      updateOrAddStep,
      addToolCallToStep,
      updateToolCallResult,
      handleContextEnrichment,
      handleTaskPlan,
      extractDisplayReasoning,
      processConclusion,
      handleTaskCreate,
      handleTaskUpdate,
      handleDecisionRequest,
      handleUnderstanding,
      handleParameterRequest,
      handleTaskStart,
      handleTaskStep,
      handleTaskComplete,
      handlePlanComplete,
      handleWorkflowStep,
      logSSEEvent,
    ],
  );

  const clearStreamingState = useCallback((abortInFlight: boolean) => {
    if (abortInFlight && abortControllerRef.current) {
      abortControllerRef.current.abort();
    }
    setThinkingSteps([]);
    setBlocks([]);
    setIsAnalyzing(false);
    setCurrentReasoning('');
    setTasks([]);
    setDecisions([]);
    setResolvedDecisions({});
    setUnderstanding(null);
    setParameterRequests([]);
    setParameterRequestDetail(undefined);
    setSubmittedParameters({});
    setIsSubmittingParameters(false);
    setTaskPlan(null);
    setCurrentTaskId(undefined);
    setTaskSummary('');
    setConclusion('');
    setNextActions([]);
    setStreamEvents([]);
    pendingRequestIdRef.current = '';
    activeRequestIdRef.current = '';
    setCurrentRequestId('');
    setUserInput('');
    setInputTimestamp(undefined);
    setThinkingStartTime(undefined);
    reasoningBufferRef.current = '';
    setAnalysisMode('unknown');
    setHitlAwaiting(false);
    setHitlSnapshot(null);
    setContextUsage(createEmptyContextUsageState());
  }, []);

  /** Full reset including abort (for new project, switch project, user cancel). */
  const reset = useCallback(() => {
    clearStreamingState(true);
  }, [clearStreamingState]);

  /** Clear UI state without aborting. Use when persisting after analysis completes.
   * Avoids race: if user submits a second request before persistence runs,
   * we must not abort that in-flight request. */
  const resetWithoutAbort = useCallback(() => {
    clearStreamingState(false);
  }, [clearStreamingState]);

  const abort = useCallback(() => {
    if (abortControllerRef.current) {
      abortControllerRef.current.abort();
    }
    activeRequestIdRef.current = '';
    setCurrentRequestId('');
    setIsAnalyzing(false);
  }, []);

  return {
    thinkingSteps,
    blocks,
    isAnalyzing,
    currentReasoning,
    tasks,
    decisions,
    resolvedDecisions,
    understanding,
    parameterRequests,
    parameterRequestDetail,
    submittedParameters,
    isSubmittingParameters,
    isWaitingForResume,
    hitlAwaiting,
    hitlSnapshot,
    userInput,
    inputTimestamp,
    thinkingStartTime,
    taskPlan,
    currentTaskId,
    taskSummary,
    conclusion,
    currentRequestId,
    nextActions,
    sseEventLogs,
    streamEvents,
    analysisMode,
    contextUsage,
    analyzeInput,
    submitHitlResume,
    handleDecision,
    handleParameterSubmit,
    reset,
    resetWithoutAbort,
    abort,
    clearSSELogs,
  };
}
