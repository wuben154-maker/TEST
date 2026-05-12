import {
  WorkspaceBlock,
  AgentTask,
  DecisionRequest,
  TaskPlan,
  InputUnderstanding,
  AnalysisTimelineEntry,
  WorkspaceTabInstance,
  TaskKind,
  SecurityStats,
  ResearchStats,
} from './analysis';

export interface ConversationMessage {
  id: string;
  type: 'user' | 'assistant';
  content: string;
  reasoning?: string;
  blocks?: WorkspaceBlock[];
  timestamp: Date;
  /** Seconds; display with fixed English `Thought {n}s` / `Thought brief {n}s` when no text (see formatThoughtDuration). */
  thinkingDuration?: number;
  // Extended fields for task execution display
  taskPlan?: TaskPlan | null;
  /** Subagent-local plans keyed by `subagentName` or `_default`. */
  taskPlansSubagent?: Record<string, TaskPlan | null>;
  understanding?: InputUnderstanding | null;
  taskSummary?: string;
  /** Canonical SSE timeline for replay (schemaVersion 1). */
  timeline?: AnalysisTimelineEntry[];
  /** Same-project correlation id as backend ``messages.request_id`` / analysis progress. */
  requestId?: string;
  /** Workspace-task-panel stats — persisted so stats bar survives page reload. */
  stats?: AnalysisResultStats;
  /** Dynamic workspace tabs — persisted so tabs survive page reload. */
  workspaceTabs?: WorkspaceTabInstance[];
  /**
   * Set after a successful knowledge-base upload for this turn (same ``requestId``).
   * Ephemeral until message persistence stores it.
   */
  knowledgeArchive?: KnowledgeArchiveNotice;
}

/** Shallow metadata for “report saved to knowledge base” UI + deep-link. */
export interface KnowledgeArchiveNotice {
  /** Client is building .docx and uploading; hide link until done */
  pending?: boolean;
  filename: string;
  displayPath: string;
  /** Human-readable title used in filename + link label. */
  reportLabel: string;
}

export type AnalysisResultStatus = 'running' | 'done' | 'error';

export interface AnalysisResultStats {
  /**
   * Profile selector. When absent, `TaskStatsBar` renders nothing.
   * Set from the backend `conclusion.meta.taskKind` for `deep-research` and
   * the four security subagents (web / email / binary / soc).
   */
  taskKind?: TaskKind;
  /** Present iff `taskKind === 'security'`. See `analysis.ts#SecurityStats`. */
  security?: SecurityStats;
  /** Present iff `taskKind === 'research'`. See `analysis.ts#ResearchStats`. */
  research?: ResearchStats;
  /**
   * Wall-clock ms — kept for hydration invariance / analytics; **not rendered**
   * by `TaskStatsBar` in the new design.
   */
  durationMs?: number;
  /**
   * Internal layout-routing signals. Not rendered. Used by
   * `isComplexResult` and `inferUseWorkspaceTaskPanelFromMessage` to decide
   * whether to keep the complex workspace chrome after the turn ends.
   */
  toolCallCount?: number;
  sandboxRunCount?: number;
}

// Single analysis result used for tab display
export interface AnalysisResult {
  id: string;
  title: string;           // User-input summary as tab title
  userInput: string;       // Full user input
  blocks: WorkspaceBlock[];
  timestamp: Date;
  /** Same as assistant message `requestId` / backend correlation when available. */
  requestId?: string;
  // --- workspace-task-panel extension ---
  /** When true, keep header + stats bar + inner tabs after stream ends (matches live "complex" layout). */
  useWorkspaceTaskPanel?: boolean;
  status: AnalysisResultStatus;
  stats: AnalysisResultStats;
  workspaceTabs: WorkspaceTabInstance[];
}

export interface Project {
  id: string;
  title: string;
  messages: ConversationMessage[];
  blocks: WorkspaceBlock[];
  analysisResults: AnalysisResult[];  // All analysis results (tabbed)
  activeResultId?: string;            // Currently active tab ID
  tasks: AgentTask[];
  decisions: DecisionRequest[];
  resolvedDecisions: Record<string, string[]>;
  createdAt: Date;
  updatedAt: Date;
}
