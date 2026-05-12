import type { AnalysisTimelineEntry, WorkspaceBlock } from '@/types/analysis';
import type { ConversationMessage } from '@/types/project';

/**
 * Tools / events that indicate this turn should keep a dedicated workspace report tab
 * (deep research, task execution, file-backed analysis). Must stay in sync with product intent:
 * simple follow-up Q&A stays chat-only; these flows stay in blocks after refresh.
 */
const WORKSPACE_TAB_TOOL_NAMES = new Set([
  'read_file',
  'write_file',
  'list_dir',
  'glob_file_search',
  'write_todos',
]);

/**
 * Returns true when persisted timeline shows a "heavy" turn that should retain workspace blocks.
 */
export function timelineSuggestsWorkspaceReportTab(timeline: AnalysisTimelineEntry[]): boolean {
  for (const e of timeline) {
    const ty = String(e.type ?? '');
    if (ty === 'task_plan') return true;
    if (
      ty === 'task_create' ||
      ty === 'task_update' ||
      ty === 'task_start' ||
      ty === 'task_complete' ||
      ty === 'task_step' ||
      ty === 'plan_complete'
    ) {
      return true;
    }
    if (ty === 'task_summary') return true;
    if (ty === 'workflow_step') return true;
    if (ty === 'step' && String(e.id ?? '') === 'open-deep-research-start') return true;
    if (ty === 'research_clarification_required') return true;
    if (ty === 'tool_call') {
      const name = String(e.toolName ?? '');
      if (WORKSPACE_TAB_TOOL_NAMES.has(name)) return true;
      if (name === 'task') return true;
    }
  }
  return false;
}

function turnClearlyOwnsWorkspaceTab(msg: ConversationMessage): boolean {
  const tasks = msg.taskPlan?.tasks;
  if (tasks != null && tasks.length > 0) return true;
  if (msg.taskPlansSubagent && Object.keys(msg.taskPlansSubagent).length > 0) return true;
  const u = msg.understanding as { taskCategory?: string } | undefined;
  if (u?.taskCategory === 'research') return true;
  return timelineSuggestsWorkspaceReportTab(msg.timeline ?? []);
}

/**
 * Drop a single synthetic `analysis` block that only mirrors `messages.content` for **chat-only**
 * turns (legacy backend Fallback 3 + same-shaped rows). Never removes blocks for deep research,
 * task-plan runs, file tooling, etc.
 */
export function collapseSyntheticConclusionMirrorBlock(
  msg: ConversationMessage,
): ConversationMessage {
  if (msg.type !== 'assistant' || !msg.blocks || msg.blocks.length !== 1) {
    return msg;
  }
  if (turnClearlyOwnsWorkspaceTab(msg)) {
    return msg;
  }

  const b = msg.blocks[0] as WorkspaceBlock & { id?: string };
  if (b.type !== 'analysis') return msg;
  const id = String(b.id ?? '');
  // Backend / legacy mirrors use these ids; other ids are treated as real workspace payloads.
  const isBackendMirror = id === 'full-analysis';
  // legacy-analysis-* is only added when timeline was empty (rowToConversation); cannot tell
  // research vs chat — do not collapse to avoid stripping real report tabs.
  if (!isBackendMirror) return msg;

  const contentText = (msg.content || '').trim();
  if (!contentText) return msg;
  return { ...msg, blocks: [] };
}
