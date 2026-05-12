import type {
  WorkspaceBlock,
  AgentTask,
  DecisionRequest,
  InputUnderstanding,
  ParameterRequest,
  TaskPlan,
  NextAction,
  SSEEventLog,
  AnalysisMode,
  AnalysisTimelineEntry,
  WorkspaceTabInstance,
  ContextUsageState,
  TaskStatsMeta,
} from './analysis';
import { createEmptyContextUsageState } from '@/lib/contextUsage';

/** Per-project streaming state for multi-session support */
export interface PerProjectStreamingState {
  /** Ordered SSE rows for unified replay (schemaVersion 1); see `analysis.ts` protocol note. */
  timeline: AnalysisTimelineEntry[];
  blocks: WorkspaceBlock[];
  isAnalyzing: boolean;
  currentReasoning: string;
  tasks: AgentTask[];
  decisions: DecisionRequest[];
  resolvedDecisions: Record<string, string[]>;
  understanding: InputUnderstanding | null;
  parameterRequests: ParameterRequest[];
  /** Prompt text from the most recent `parameter_request` SSE event (`detail` field). */
  parameterRequestDetail?: string;
  submittedParameters: Record<string, string>;
  userInput: string;
  inputTimestamp: Date | undefined;
  thinkingStartTime: Date | undefined;
  /** Primary (orchestrator) task board; `write_todos` / main-scope `task_plan`. */
  taskPlanMain: TaskPlan | null;
  /**
   * Subagent-local plans keyed by `subagentName` or `_default` (`taskPlanScope.SUBAGENT_PLAN_DEFAULT_KEY`).
   */
  taskPlansSubagent: Record<string, TaskPlan | null>;
  currentTaskId: string | undefined;
  taskSummary: string;
  nextActions: NextAction[];
  conclusion: string;
  currentRequestId: string;
  sseEventLogs: SSEEventLog[];
  analysisMode: AnalysisMode;
  /** Last request attachment summary (paths from server upload). */
  attachments?: Array<{ filename: string; size: number; file_path?: string }>;
  /** LangGraph interrupt: terminal ``done`` had ``awaitingHuman: true``. */
  hitlAwaiting?: boolean;
  hitlSnapshot?: { interruptIds?: string[] } | null;
  /** Original POST /analyze ``request_id`` while HITL is pending (progress + resume correlation). */
  hitlProgressRequestId?: string;
  /** True after the user submitted HITL parameter values (keeps the form visible in read-only). */
  hitlParametersSubmitted?: boolean;
  // --- workspace-task-panel live state ---
  /** Dynamic workspace tabs built from tool_call SSE events. */
  workspaceTabs: WorkspaceTabInstance[];
  /** epoch ms of the first SSE event for this analysis turn. */
  resultStartTime?: number;
  /** Total tool_call events received so far. */
  toolCallCount: number;
  /** tool_call events where toolName starts with "sandbox_". */
  sandboxRunCount: number;
  /** Realtime context-usage indicator state (see lib/contextUsage.ts). */
  contextUsage: ContextUsageState;
  /**
   * Backend-derived `TaskStatsMeta` pulled from the `conclusion` SSE event.
   * When set, `buildConversationMessages` persists it onto the assistant
   * message's `stats.taskKind/security/research`, driving `TaskStatsBar`.
   */
  statsMeta?: TaskStatsMeta;
  /** Populated only when invoking ``onProjectAnalysisComplete`` — correlation id for idempotency (knowledge archive). */
  completedRequestId?: string;
}

export const createEmptyStreamingState = (): PerProjectStreamingState => ({
  timeline: [],
  blocks: [],
  isAnalyzing: false,
  currentReasoning: '',
  tasks: [],
  decisions: [],
  resolvedDecisions: {},
  understanding: null,
  parameterRequests: [],
  parameterRequestDetail: undefined,
  submittedParameters: {},
  userInput: '',
  inputTimestamp: undefined,
  thinkingStartTime: undefined,
  taskPlanMain: null,
  taskPlansSubagent: {},
  currentTaskId: undefined,
  taskSummary: '',
  nextActions: [],
  conclusion: '',
  currentRequestId: '',
  sseEventLogs: [],
  analysisMode: 'unknown',
  hitlAwaiting: false,
  hitlSnapshot: null,
  hitlProgressRequestId: undefined,
  hitlParametersSubmitted: false,
  workspaceTabs: [],
  resultStartTime: undefined,
  toolCallCount: 0,
  sandboxRunCount: 0,
  contextUsage: createEmptyContextUsageState(),
  statsMeta: undefined,
  completedRequestId: undefined,
});
