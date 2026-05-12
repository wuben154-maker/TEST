export type ThinkingStepStatus =
  | 'pending'
  | 'running'
  | 'success'
  | 'warning'
  | 'error'
  | 'skipped';

/**
 * Structured task-stats payload attached to the final `conclusion` SSE event.
 * Source of truth for `TaskStatsBar`. Kept separate from `AnalysisResultStats`
 * so the stream-envelope type and the persisted-stats type can evolve
 * independently.
 */
export type TaskKind = 'security' | 'research';

export type SecuritySeverity = 'critical' | 'high' | 'medium' | 'low' | 'info';

export type ResearchFreshness = '<=7d' | '<=30d' | '<=90d' | 'older' | 'n/a';

export type SecurityValidationLiteral = 'static' | 'yara' | 'sandbox' | 'ti';

export interface SecurityActionableBreakdown {
  total: number;
  critical: number;
  high: number;
  medium: number;
}

export interface SecurityStats {
  severity: SecuritySeverity;
  riskScore?: number;
  actionable?: SecurityActionableBreakdown;
  threatClasses?: string[];
  validation?: SecurityValidationLiteral[];
}

export interface ResearchStats {
  keyFindings?: number;
  recommendations?: number;
  sources?: number;
  freshness?: ResearchFreshness;
  gaps?: number;
}

export interface TaskStatsMeta {
  taskKind: TaskKind;
  security?: SecurityStats;
  research?: ResearchStats;
}

/**
 * Analysis SSE protocol (schemaVersion 1)
 *
 * The SecManus web app supports a single active stream schema. Every user-visible
 * event from `POST /analyze` SHOULD include `schemaVersion`, monotonic `seq`, and
 * `scope` (`main` | `subagent`). There is no legacy-client compatibility layer in
 * the UI; optional JSON keys may be ignored until consumed.
 *
 * Persistence: assistant turns store a `timeline` JSON array of canonical events
 * (see `ConversationMessage.timeline` and Supabase `messages.timeline`).
 *
 * Design tiers (see docs/Process/SSE_EVENT_CATALOG.md):
 * - ReAct core (live SSE): `llm_invoke_start` / `llm_delta` / `llm_invoke_end` + `tool_call` /
 *   `tool_result` (+ `turn` for cycle boundaries). Types `reasoning` / `answer` are **not** emitted
 *   by the Python adapter anymore; kept on the client only for **persisted timeline** replay.
 * - Session: `done`, `conclusion`, `error`.
 * - Product orchestration: `understanding`, task plan lifecycle, HITL, etc.
 * - Subagent: same canonical types as main when merged into main SSE; `skill_*`
 *   may appear only on standalone subagent streams (legacy / transport).
 * - User-hidden: `debug`, `type: internal`, or `internal: true` (see timelineDisplay).
 */

export type ThinkingEventType =
  // --- ReAct (think / act / observe) ---
  /** Begin one LLM generation (wall-clock timing boundary); payload: `invokeId`. */
  | 'llm_invoke_start'
  /** Streaming token delta; `channel`: `reasoning` | `text` (user-visible). */
  | 'llm_delta'
  /** End one LLM generation; closes the matching `invokeId`. */
  | 'llm_invoke_end'
  /** Emitted once per cutoff when SummarizationMiddleware compacts history. */
  | 'context_summarized'
  /** Persisted timelines only; live backend uses `llm_delta` + `channel: reasoning`. */
  | 'reasoning'
  /** Persisted timelines only; live backend uses `llm_delta` + `channel: text`. */
  | 'answer'
  | 'tool_call'
  | 'tool_result'
  // --- Session boundaries ---
  | 'conclusion'
  | 'error'
  | 'done'
  // --- Milestones (non-LLM phase lines; optional) ---
  | 'step'
  // --- Intent & HITL ---
  | 'understanding'
  | 'task_create'
  | 'task_update'
  | 'decision_request'
  | 'decision_response'
  | 'parameter_request'
  | 'parameter_response'
  // --- Task plan & execution (planner / executor) ---
  | 'task_plan'
  | 'task_start'
  | 'task_step'
  | 'task_complete'
  | 'task_error'
  | 'plan_complete'
  | 'task_summary'
  | 'next_actions'
  | 'workflow_step'
  // --- Skill subgraph transport (prefer canonical types above when merged) ---
  | 'skill_start'
  | 'skill_complete'
  | 'skill_reasoning'
  | 'skill_error'
  // --- Diagnostics (dev-only in UI; not shown on end-user timeline) ---
  | 'debug'
  | 'internal';

// Follow-up suggested action
export interface NextAction {
  id: string;
  label: string;           // Display text
  message: string;         // Message to send after click
  icon?: string;           // Optional icon name
}

// Task category
export type TaskCategory = 'security' | 'research' | 'parameter_needed' | 'unknown';

// Security subtype
export type SecuritySubType = 
  | 'email_analysis' 
  | 'malware_analysis' 
  | 'web_attack' 
  | 'soc_alert' 
  | 'vuln_scan' 
  | 'ioc_lookup' 
  | 'generic_security';

// Parameter request
export interface ParameterRequest {
  id: string;
  name: string;
  description: string;
  paramType: 'text' | 'password' | 'url' | 'json' | 'boolean';
  required: boolean;
  placeholder?: string;
  validationRegex?: string;
  encrypted: boolean;
  /** True when request comes from HITL clarification (`interruptKind=user_input_v1`). */
  isClarification?: boolean;
}

// AI understanding result for user input (SSE `understanding` events, if emitted)
export interface InputUnderstanding {
  inputType: string;           // Input type (email, log, code, etc.)
  summary: string;             // Short summary
  reasoningSummary?: string;   // User-facing reasoning summary
  keyEntities: string[];       // Key entities
  analysisGoals: string[];     // Analysis goals
  suggestedApproach: string;   // Recommended analysis approach
  confidence: number;          // Confidence score
  taskCategory?: TaskCategory; // Task category
  securitySubtype?: SecuritySubType; // Security subtype (security tasks only)
  researchTopic?: string;      // Research topic (research tasks only)
  parameterRequests?: ParameterRequest[]; // Required parameters
}

export interface ThinkingStep {
  id: string;
  label: string;
  status: ThinkingStepStatus;
  detail?: string;
  reasoning?: string;
  toolCalls?: ToolCallInfo[];
  timestamp?: number;
  internal?: boolean;  // If true, should not be displayed to users
}

export interface ToolCallInfo {
  id: string;
  toolName: string;
  toolInput?: Record<string, unknown>;
  toolOutput?: unknown;
  status: ThinkingStepStatus;
  timestamp?: number;
}

export interface AgentTask {
  id: string;
  title: string;
  description?: string;
  status: 'pending' | 'in_progress' | 'done';
  timestamp?: number;
}

// Task execution step
export interface TaskStep {
  id: string;
  label: string;
  description?: string;
  status: 'pending' | 'running' | 'success' | 'warning' | 'error';
  detail?: string;
  toolName?: string;
  toolInput?: Record<string, unknown>;
  toolOutput?: string;
  durationMs?: number;
  timestamp?: number;
  internal?: boolean;  // If true, should not be displayed to users
  isWorkflowStep?: boolean;  // True if this comes from SKILL.md workflow_steps
}

// Planned task
export interface PlannedTask {
  id: string;
  title: string;
  description: string;
  taskType: 'security' | 'research';
  skillName?: string;
  priority: number;
  status: 'pending' | 'running' | 'success' | 'error' | 'skipped';
  result?: string;
  error?: string;
  durationMs: number;
  steps: TaskStep[];
  dependsOn?: string[];  // Dependent task IDs
}

// Task plan
export interface TaskPlan {
  id: string;
  tasks: PlannedTask[];
  isSingleTask: boolean;
  totalDurationMs: number;
  status: 'pending' | 'running' | 'success' | 'error';
  createdAt: string;
  reasoning?: string;  // Rationale for task decomposition
  workspaceTitle?: string;  // LLM-generated workspace tab title
}

export interface DecisionOption {
  id: string;
  label: string;
  description?: string;
  variant?: 'default' | 'destructive' | 'success';
}

export interface DecisionRequest {
  id: string;
  question: string;
  options: DecisionOption[];
  allowMultiple?: boolean;
  timestamp?: number;
}

/** One persisted or in-flight SSE row for replay / unified UI (schemaVersion 1). */
export type AnalysisTimelineEntry = Record<string, unknown> & {
  type: string;
  seq: number;
  schemaVersion?: number;
  /**
   * `main` (default) vs `subagent`. Task plan and lifecycle events with `subagent` MUST update
   * subagent-scoped UI state only; omitting `scope` means main (backward compatible).
   */
  scope?: 'main' | 'subagent';
  /** When `scope` is `subagent`, identifies which subagent board receives `task_plan` updates. */
  subagentName?: string;
  /**
   * Optional nested-delegation envelope (schemaVersion 1 extension; see `docs/SSE_EVENT_CATALOG.md`).
   * Omitted on `scope === 'main'` and on legacy persisted rows — UI must not infer hierarchy without these.
   */
  delegationDepth?: number;
  /** Top-level `task()` tool_call.id for this user turn (parallel runs distinguished by this id). */
  rootDelegationId?: string;
  /** Nested `task()` tool_call.id when `delegationDepth >= 2`. */
  parentToolCallId?: string;
  /** ReAct cycle id from backend (``ReactTurnTracker``); groups think + act before next think. */
  turn?: number;
  id?: string;
};

export interface ThinkingEvent {
  type: ThinkingEventType;
  id: string;
  /** Stream envelope (Python `adapt_astream_to_sse`, schemaVersion 1). */
  schemaVersion?: number;
  seq?: number;
  scope?: 'main' | 'subagent';
  /** ReAct cycle (1-based); aligns think stream and tool_call/tool_result in the same cycle. */
  turn?: number;
  subagentStream?: boolean;
  researchSubgraph?: boolean;
  subagentName?: string;
  /** See `AnalysisTimelineEntry` / SSE_EVENT_CATALOG — nested `task()` envelope. */
  delegationDepth?: number;
  rootDelegationId?: string;
  parentToolCallId?: string;
  label?: string;
  status?: ThinkingStepStatus;
  /** Deep research (and similar): fixed UI phase slot id, e.g. deep_research_clarify. */
  phaseId?: string;
  phaseIndex?: number;
  /** Step visibility; `debug` hides from user timeline (see SSE_EVENT_CATALOG appendix B). */
  visibility?: 'debug' | 'internal';
  detail?: string;
  content?: string;
  toolName?: string;
  /**
   * Canonical tool id for UX/analytics when `toolName` is a research-graph alias
   * (e.g. ConductResearch → web_search, ResearchComplete → scrape_url).
   */
  displayToolName?: string;
  /** SSE catalog §6 — from backend tool presentation registry. */
  toolPresentation?: 'task' | 'action' | 'state' | 'parameter' | 'research_task';
  parameterControl?: 'single' | 'multi' | 'fill';
  toolInput?: Record<string, unknown>;
  toolOutput?: unknown;
  timestamp?: number;
  requestId?: string;
  /** Correlates `llm_invoke_start` / `llm_delta` / `llm_invoke_end`. */
  invokeId?: string;
  /** On `llm_delta`: `reasoning` (chain-of-thought) or `text` (visible reply stream). */
  channel?: 'reasoning' | 'text';
  /** `llm_invoke_start`: gateway model id (provider/model). Used by the context-usage indicator. */
  modelId?: string;
  /** `llm_invoke_end`: latest observed token usage for this invocation. */
  usage?: { inputTokens: number; outputTokens: number };
  /** `context_summarized`: cutoff index reported by SummarizationMiddleware. */
  cutoffIndex?: number;
  // Internal flag - if true, this event should not be displayed to users
  internal?: boolean;
  // Task-specific
  task?: AgentTask | PlannedTask;
  taskStatus?: 'pending' | 'in_progress' | 'done';
  // Decision-specific
  decision?: DecisionRequest;
  selectedOptions?: string[];
  // Understanding-specific
  understanding?: InputUnderstanding;
  // Parameter-specific
  parameterRequests?: ParameterRequest[];
  parameters?: Record<string, string>;
  // Task plan specific
  plan?: TaskPlan;
  taskId?: string;
  step?: TaskStep;
  // Task summary specific
  summary?: string;           // LLM-generated task summary
  // Next actions specific
  nextActions?: NextAction[]; // Follow-up suggested action list
  // HITL (LangGraph interrupt) — optional envelope keys
  interruptKind?: string;
  interruptId?: string;
  hitlRequest?: Record<string, unknown>;
  userInputKind?: 'choice' | 'form' | 'text';
  /** Present on terminal ``done`` when the graph is waiting for ``POST /analyze/resume``. */
  awaitingHuman?: boolean;
  hitl?: { interruptIds?: string[] };
  /** Present on `conclusion` events (schemaVersion 1) for research / security tasks. */
  meta?: TaskStatsMeta;
}

export interface LogBlock {
  type: 'log';
  id: string;
  content: string;
  highlights?: { start: number; end: number; type: 'ip' | 'url' | 'payload' }[];
}

export interface DecoderBlock {
  type: 'decoder';
  id: string;
  encoded: string;
  decoded: string;
  algorithm: string;
}

export interface IntelCard {
  type: 'intel';
  id: string;
  indicator: string;
  indicatorType: 'ip' | 'domain' | 'hash';
  location?: string;
  asn?: string;
  threatScore: 'high' | 'medium' | 'low' | 'clean';
  tags?: string[];
}

export interface TextBlock {
  type: 'text';
  id: string;
  content: string;
  variant?: 'heading' | 'paragraph' | 'bullet';
}

export interface SummaryBlock {
  type: 'summary';
  id: string;
  severity: 'critical' | 'high' | 'medium' | 'low' | 'info';
  title: string;
  description: string;
}

export interface AnalysisBlock {
  type: 'analysis';
  id: string;
  content: string;  // Markdown content from AI analysis
  title?: string;
}

export type WorkspaceBlock = LogBlock | DecoderBlock | IntelCard | TextBlock | SummaryBlock | AnalysisBlock;

// ---------------------------------------------------------------------------
// Report document view model (report-content-display-upgrade)
// ---------------------------------------------------------------------------

export type ReportTemplateId =
  | 'security_analysis'
  | 'research_brief'
  | 'executive_summary'
  | 'generic_analysis';

export interface ReportCover {
  title: string;
  kicker: string;
  generatedAt?: string;
  badges?: string[];
}

export interface ReportSummary {
  title: string;
  description: string;
}

export interface ReportMetric {
  label: string;
  value: string;
}

export interface ReportArtifact {
  id: string;
  label: string;
  kind: string;
}

export type ReportSectionKind =
  | 'executive_summary'
  | 'finding'
  | 'evidence'
  | 'recommendation'
  | 'timeline'
  | 'source'
  | 'appendix'
  | 'custom';

export type ReportContentBlock =
  | { type: 'markdown'; markdown: string }
  | { type: 'legacy_workspace_block'; block: WorkspaceBlock }
  | { type: 'metric_cards'; metrics: ReportMetric[] }
  | { type: 'custom'; renderer: string; payload: unknown };

export interface ReportSection {
  id: string;
  title: string;
  kind: ReportSectionKind;
  blocks: ReportContentBlock[];
}

export interface ReportDocument {
  schemaVersion: 1;
  id: string;
  title: string;
  templateId: ReportTemplateId;
  generatedAt?: string;
  cover?: ReportCover;
  summary?: ReportSummary;
  sections: ReportSection[];
  artifacts?: ReportArtifact[];
  markdownFallback: string;
}

export interface AnalysisSession {
  id: string;
  input: string;
  inputType: 'log' | 'code' | 'text' | 'file';
  thinkingSteps: ThinkingStep[];
  blocks: WorkspaceBlock[];
  timestamp: Date;
}

export interface StreamingAnalysisResult {
  inputType: string;
  severity: 'critical' | 'high' | 'medium' | 'low' | 'info';
  title: string;
  summary: string;
  entities: {
    ips?: string[];
    urls?: string[];
    domains?: string[];
    timestamps?: string[];
    hashes?: string[];
  };
  decodings?: Array<{
    encoded: string;
    decoded: string;
    algorithm: string;
  }>;
  threatIndicators?: string[];
  attackPatterns?: string[];
  recommendations?: string[];
  intelTags?: string[];
  fullAnalysis?: string; // Full analysis text from DeepAgent
}

/** Stream event for Cursor-style unified flow (reasoning + tool_call + tool_result + task) */
export interface StreamEvent {
  type: 'reasoning' | 'tool_call' | 'tool_result' | 'task_start' | 'task_complete';
  id: string;
  /** Source timeline `seq` when buffered from `AnalysisTimelineEntry` (explore chunks). */
  seq?: number;
  scope?: string;
  subagentName?: string;
  timestamp?: number;
  content?: string;
  toolName?: string;
  /** SSE catalog §6 — echoed from timeline when present. */
  toolPresentation?: 'task' | 'action' | 'state' | 'parameter' | 'research_task';
  toolInput?: Record<string, unknown>;
  toolOutput?: unknown;
  taskId?: string;
  taskTitle?: string;
  taskStatus?: 'pending' | 'running' | 'success' | 'error';
}

/** SSE event log for developer mode panel */
export interface SSEEventLog {
  type: string;
  id: string;
  timestamp: number;
  preview?: string;
  rawData?: Record<string, unknown>;
}

/** Analysis mode (deepagent vs simple) */
export type AnalysisMode = 'unknown' | 'deepagent';

// ---------------------------------------------------------------------------
// Realtime context-usage indicator (see docs/Process/realtime-context-usage-indicator/)
// ---------------------------------------------------------------------------

/** Per-invocation usage snapshot derived from `llm_invoke_start` + `llm_invoke_end`. */
export interface InvokeUsageSnapshot {
  invokeId: string;
  modelId?: string;
  inputTokens: number;
  outputTokens: number;
  /** When the end event was received (ms epoch). */
  endedAt?: number;
}

/** Per-subagent aggregated usage for the popover attribution breakdown. */
export interface SubagentUsageAggregate {
  subagentName: string;
  invocations: number;
  inputTokens: number;
  outputTokens: number;
}

/** Aggregated realtime context-usage state exposed by `useStreamingAnalysis`. */
export interface ContextUsageState {
  /**
   * Most recent completed **main**-scope invocation (drives the primary ring
   * vs the selected main model’s context window). Subagent invokes update
   * `latestSubagentByName` only so the ring is never overwritten by a sub-run.
   * @deprecated Kept for older persisted payloads; use `latestMain` when present.
   */
  latest?: InvokeUsageSnapshot;
  /** Same as `latest` when the last completed invoke was main-scoped; prefer this field. */
  latestMain?: InvokeUsageSnapshot;
  /** Last completed invoke per subagent name (separate from main; each pairs with its own model window). */
  latestSubagentByName?: Record<string, InvokeUsageSnapshot>;
  /** Running totals across all invocations in this session (secondary metric; sum of per-call usage). */
  cumulative: { inputTokens: number; outputTokens: number; invocations: number };
  /** Attribution breakdown keyed by `subagentName` (includes `main`). */
  bySubagent: SubagentUsageAggregate[];
  /** ms-epoch of the last `context_summarized` event, or undefined. */
  lastSummarizedAt?: number;
}

// ---------------------------------------------------------------------------
// Workspace tab types (workspace-task-panel feature)
// ---------------------------------------------------------------------------

/** Config entry from GET /tool-tab-config (mirrors workspace_tab YAML block). */
export interface WorkspaceTabConfig {
  type: string;
  label: string;
  icon: string;
  merge_strategy: 'by_arg' | 'always' | 'never';
  merge_key?: string;
}

/** A single rendered shell output line. */
export interface ShellLine {
  ts: number;
  stream: 'stdout' | 'stderr';
  text: string;
}

/** Discriminated union for tab payload. */
export type WorkspaceTabData =
  | { kind: 'shell'; lines: ShellLine[] }
  | { kind: 'ioc_table'; raw: string }
  | { kind: 'placeholder'; message: string };

/** A live tab instance inside the workspace tab panel. */
export interface WorkspaceTabInstance {
  id: string;
  type: string;
  label: string;
  icon: string;
  instanceKey: string;
  data: WorkspaceTabData;
}

/** Attachment for analysis requests */
export interface AnalyzeAttachment {
  filename: string;
  content_type: string;
  /** Omitted when using server pre-upload (`file_path` only). */
  content?: string;
  size: number;
  hash_sha256?: string;
  /** Virtual path from POST /uploads (e.g. /uploads/s_xxx/file). */
  file_path?: string;
  /** LLM/UI-facing workspace path from POST /uploads (e.g. /workspace/file). */
  workspace_path?: string;
  display_path?: string;
  virtual_path?: string;
  sha256?: string;
}
