import type { TaskPlan } from '@/types/analysis';
import type { AnalysisResult, ConversationMessage } from '@/types/project';
import { extractWorkspaceTitleFromTimeline } from '@/lib/timelineDisplay';
import { inferUseWorkspaceTaskPanelFromMessage } from '@/lib/analysisWorkspaceChrome';

/**
 * Whether this assistant turn should be materialised as a report `analysisResults` tab.
 *
 * A tab only makes sense when the user actually has something to look at in the report
 * panel, i.e. one of:
 *   1. Report blocks were produced (`blocks.length > 0`).
 *   2. Workspace tab instances were produced (shell / ioc / file-viewer runtime output).
 *
 * Tool calls and sandbox runs alone are intentionally NOT enough: the backend always
 * projects user-facing output into either a `block` or a `workspace_tab` event. A turn
 * whose only side-effects are internal helper tool calls (`write_todos`, `ls`, ...)
 * followed by a plain conversational conclusion — e.g. a HITL turn where the user said
 * "I haven't uploaded yet" and the agent replied "please upload the file" — produces
 * a tab whose Report panel would read "No report content". That empty shell is worse
 * than no tab, so such turns stay plain chat replies.
 *
 * This is deliberately stricter than {@link inferUseWorkspaceTaskPanelFromMessage},
 * which governs the *chrome* of an already-displayed result and may light up earlier
 * (e.g. while a task is running, before any block is emitted).
 */
export function assistantMessageYieldsAnalysisTab(msg: ConversationMessage): boolean {
  if (msg.type !== 'assistant') return false;
  if (Array.isArray(msg.blocks) && msg.blocks.length > 0) return true;
  if (Array.isArray(msg.workspaceTabs) && msg.workspaceTabs.length > 0) return true;
  return false;
}

/**
 * Build a tab {@link AnalysisResult} from an assistant {@link ConversationMessage}.
 * `allMessages` must include this message (e.g. [...existing, ...appended]).
 */
export function buildAnalysisResultFromAssistantMessage(
  msg: ConversationMessage,
  allMessages: ConversationMessage[],
  analysisTitlePrefix: string,
  resultIndex: number,
): AnalysisResult {
  const msgIndex = allMessages.indexOf(msg);
  const userMsg =
    msgIndex > 0
      ? allMessages.slice(0, msgIndex).reverse().find((m) => m.type === 'user')
      : undefined;

  const timelineTitle = extractWorkspaceTitleFromTimeline(msg.timeline ?? []);
  const planTitle = (msg.taskPlan as TaskPlan | null | undefined)?.workspaceTitle;
  const title =
    timelineTitle ||
    planTitle ||
    (userMsg?.content
      ? userMsg.content.slice(0, 20) + (userMsg.content.length > 20 ? '...' : '')
      : `${analysisTitlePrefix} ${resultIndex + 1}`);

  return {
    id: msg.id,
    title,
    userInput: userMsg?.content || '',
    blocks: Array.isArray(msg.blocks) ? msg.blocks : [],
    timestamp: msg.timestamp,
    requestId: msg.requestId,
    useWorkspaceTaskPanel: inferUseWorkspaceTaskPanelFromMessage(msg),
    status: 'done',
    stats: msg.stats ?? {},
    workspaceTabs: msg.workspaceTabs ?? [],
  };
}
