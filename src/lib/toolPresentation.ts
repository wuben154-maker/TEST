/**
 * Prefer SSE `toolPresentation` (catalog §6); infer from `toolName` for legacy rows.
 * Aligns with python-agent-service `app/sse/tool_presentation.py`.
 */

export type ToolPresentationKind = 'task' | 'action' | 'state' | 'parameter' | 'research_task';

const CONTEXT_ENRICHMENT_TOOLS = new Set([
  'web_search',
  'web_searchs',
  'web_search_deep_research',
  'scrape_url',
  'read_file',
  'analyze_file_structure',
]);

export function inferToolPresentationFromToolName(toolName: string | undefined): ToolPresentationKind {
  const n = (toolName || '').trim();
  if (!n) return 'action';
  if (n === 'write_todos' || n === 'task') return 'task';
  if (n === 'think_tool') return 'state';
  if (n === 'ConductResearch') return 'research_task';
  if (n === 'ResearchComplete') return 'state';
  if (n === 'ResearchQuestion') return 'state';
  if (n === 'request_user_input') return 'parameter';
  const lower = n.toLowerCase();
  if (lower.startsWith('internal_') || lower.startsWith('hitl_')) return 'state';
  return 'action';
}

/** Accepts ThinkingEvent, AnalysisTimelineEntry, or any object with optional tool fields. */
export function effectiveToolPresentation(ev: object): ToolPresentationKind {
  const o = ev as { toolPresentation?: unknown; toolName?: unknown };
  const raw = o.toolPresentation;
  if (
    raw === 'task' ||
    raw === 'action' ||
    raw === 'state' ||
    raw === 'parameter' ||
    raw === 'research_task'
  ) {
    return raw;
  }
  const name = typeof o.toolName === 'string' ? o.toolName : undefined;
  return inferToolPresentationFromToolName(name);
}

export function isContextEnrichmentToolName(toolName: string | undefined): boolean {
  if (!toolName) return false;
  return CONTEXT_ENRICHMENT_TOOLS.has(toolName);
}
