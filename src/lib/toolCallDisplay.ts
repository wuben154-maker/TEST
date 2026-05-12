/**
 * User-facing lines for tool activity (no protocol terms like tool_call / step).
 * All copy comes from i18n locales (see AGENT.md 6.2).
 */

import { getTranslations, type Language, type TranslationKeys } from '@/i18n';

function truncate(str: string, maxLen: number): string {
  if (!str) return '';
  return str.length > maxLen ? str.slice(0, maxLen) + '…' : str;
}

/** JSON array of paths (e.g. glob) → first path + count; avoids huge badges and flex shrink bugs. */
function summarizePathLikeList(raw: string, maxLen: number): string {
  const t = raw.trim();
  if (!t.startsWith('[') || !t.endsWith(']')) {
    return truncate(t, maxLen);
  }
  try {
    const parsed: unknown = JSON.parse(t);
    if (!Array.isArray(parsed) || parsed.length === 0) {
      return truncate(t, maxLen);
    }
    const first = String(parsed[0] ?? '').trim();
    const n = parsed.length;
    const suffix = n > 1 ? ` (+${n - 1} more)` : '';
    const combined = first ? `${first}${suffix}` : `${n} items`;
    return truncate(combined, maxLen);
  } catch {
    return truncate(t, maxLen);
  }
}

/** Replace {key} placeholders in locale strings. */
function interpolate(template: string, vars: Record<string, string>): string {
  return template.replace(/\{(\w+)\}/g, (_, key: string) => vars[key] ?? `{${key}}`);
}

type ToolActivityCopy = TranslationKeys['toolActivity'];

/** Segments for Cursor-style tool rows: muted verb, optional connectors, path/query as badge. */
export type TraceToolSegment =
  | { kind: 'verb'; text: string }
  | { kind: 'muted'; text: string }
  | { kind: 'badge'; text: string }
  | { kind: 'plain'; text: string };

function friendlyCapability(toolName: string, ta: ToolActivityCopy): string {
  const s = toolName.replace(/_/g, ' ').trim();
  if (!s) return ta.genericStep;
  return interpolate(ta.genericWithName, { name: truncate(s, 80) });
}

/** web_search uses `query`; open_deep_research uses `queries: string[]` in one tool call. */
function webSearchQuerySummary(input: Record<string, unknown>): string {
  const rawQueries = input['queries'];
  if (Array.isArray(rawQueries)) {
    const strs = rawQueries.map((x) => String(x).trim()).filter(Boolean);
    if (strs.length === 0) return '';
    const first = truncate(strs[0]!, 50);
    if (strs.length === 1) return first;
    return `${first} (+${strs.length - 1})`;
  }
  return truncate(String(input['query'] ?? '').trim(), 50);
}

/**
 * One human-readable line for a tool_call (and optional paired result preview elsewhere).
 */
export function humanizeToolCallLine(
  toolName: string,
  toolInput: Record<string, unknown> | undefined,
  language: Language,
): string {
  const ta = getTranslations(language).toolActivity;
  const input = toolInput || {};
  const q = (k: string) => String(input[k] ?? '');

  switch (toolName) {
    case 'web_search':
    case 'web_searchs':
    case 'web_search_deep_research':
      return interpolate(ta.webSearch, { query: webSearchQuerySummary(input) });
    case 'scrape_url':
      return interpolate(ta.scrapeUrl, { url: truncate(q('url'), 60) });
    case 'read_file':
      return interpolate(ta.readFile, {
        path: truncate(q('file_path') || q('path'), 55),
      });
    case 'execute':
    case 'run_terminal_cmd':
    case 'shell': {
      const cmd = truncate(q('command') || q('cmd') || q('shell_command') || q('args'), 100);
      if (!cmd.trim()) return friendlyCapability(toolName, ta);
      return interpolate(ta.runCommand, { cmd });
    }
    case 'run_script':
    case 'python': {
      const path = truncate(q('file_path') || q('path') || q('script'), 60);
      if (!path.trim()) return friendlyCapability(toolName, ta);
      return interpolate(ta.runScript, { path });
    }
    case 'grep':
      return interpolate(ta.grepIn, {
        where: truncate(q('path') || q('glob') || '.', 30),
        pattern: truncate(q('pattern'), 40),
      });
    case 'glob':
      return interpolate(ta.globListed, { pattern: summarizePathLikeList(q('pattern'), 56) });
    case 'ls':
      return interpolate(ta.lsListed, { path: summarizePathLikeList(q('path'), 56) });
    case 'decode_base64':
      return ta.decodeBase64;
    case 'decode_url':
      return ta.decodeUrl;
    case 'extract_iocs':
      return ta.extractIocs;
    case 'lookup_threat_intel':
      return ta.lookupThreatIntel;
    case 'summarize_content':
      return ta.summarizeContent;
    case 'analyze_email_headers':
      return ta.analyzeEmailHeaders;
    case 'task':
    case 'write_todos':
      return '';
    default:
      return friendlyCapability(toolName, ta);
  }
}

/**
 * Same tools as {@link humanizeToolCallLine}, split for verb / badge styling in the trace UI.
 */
export function humanizeToolCallSegments(
  toolName: string,
  toolInput: Record<string, unknown> | undefined,
  language: Language,
): TraceToolSegment[] {
  const ta = getTranslations(language).toolActivity;
  const input = toolInput || {};
  const q = (k: string) => String(input[k] ?? '');

  const plain = (text: string): TraceToolSegment[] => [{ kind: 'plain', text }];

  switch (toolName) {
    case 'web_search':
    case 'web_searchs':
    case 'web_search_deep_research':
      return [
        { kind: 'verb', text: ta.traceVerbWebSearch },
        { kind: 'badge', text: webSearchQuerySummary(input) },
      ];
    case 'scrape_url':
      return [
        { kind: 'verb', text: ta.traceVerbScrape },
        { kind: 'badge', text: truncate(q('url'), 60) },
      ];
    case 'read_file':
      return [
        { kind: 'verb', text: ta.traceVerbRead },
        { kind: 'badge', text: truncate(q('file_path') || q('path'), 55) },
      ];
    case 'execute':
    case 'run_terminal_cmd':
    case 'shell': {
      const cmd = truncate(q('command') || q('cmd') || q('shell_command') || q('args'), 100);
      if (!cmd.trim()) return plain(friendlyCapability(toolName, ta));
      return [
        { kind: 'verb', text: ta.traceVerbRunCommand },
        { kind: 'badge', text: cmd },
      ];
    }
    case 'run_script':
    case 'python': {
      const path = truncate(q('file_path') || q('path') || q('script'), 60);
      if (!path.trim()) return plain(friendlyCapability(toolName, ta));
      return [
        { kind: 'verb', text: ta.traceVerbRunScript },
        { kind: 'badge', text: path },
      ];
    }
    case 'grep': {
      const pattern = truncate(q('pattern'), 40);
      const where = truncate(q('path') || q('glob') || '.', 30);
      if (language === 'zh') {
        return [
          { kind: 'muted', text: '在 ' },
          { kind: 'badge', text: where },
          { kind: 'muted', text: ' 中搜索 ' },
          { kind: 'badge', text: pattern },
        ];
      }
      if (language === 'ja') {
        return [
          { kind: 'badge', text: where },
          { kind: 'muted', text: ' で「' },
          { kind: 'badge', text: pattern },
          { kind: 'muted', text: '」を検索' },
        ];
      }
      if (language === 'ko') {
        return [
          { kind: 'badge', text: where },
          { kind: 'muted', text: '에서 「' },
          { kind: 'badge', text: pattern },
          { kind: 'muted', text: '」 검색' },
        ];
      }
      return [
        { kind: 'verb', text: ta.traceVerbGrep },
        { kind: 'badge', text: pattern },
        { kind: 'muted', text: ` ${ta.traceMutedIn} ` },
        { kind: 'badge', text: where },
      ];
    }
    case 'glob':
      return [
        { kind: 'verb', text: ta.traceVerbGlob },
        { kind: 'badge', text: summarizePathLikeList(q('pattern'), 56) },
      ];
    case 'ls':
      return [
        { kind: 'verb', text: ta.traceVerbLs },
        { kind: 'badge', text: summarizePathLikeList(q('path'), 56) },
      ];
    case 'decode_base64':
      return plain(ta.decodeBase64);
    case 'decode_url':
      return plain(ta.decodeUrl);
    case 'extract_iocs':
      return plain(ta.extractIocs);
    case 'lookup_threat_intel':
      return plain(ta.lookupThreatIntel);
    case 'summarize_content':
      return plain(ta.summarizeContent);
    case 'analyze_email_headers':
      return plain(ta.analyzeEmailHeaders);
    case 'task':
    case 'write_todos':
      return [];
    default:
      return plain(friendlyCapability(toolName, ta));
  }
}

/**
 * When humanizeToolCallLine is empty, UI may fall back to raw toolName.
 * Subagent delegation tool name is hidden (no label); show output preview / timeline only.
 */
export function fallbackToolDisplayName(toolName: string, _language: Language): string {
  if (toolName === 'task') {
    return '';
  }
  return toolName;
}

/**
 * Compact tool label for ReAct tool rows: tool id only (no path/query), detail shows target separately.
 */
export function compactToolRowLabel(toolName: string): string {
  if (!toolName || toolName === 'task') return '';
  return toolName.replace(/_/g, ' ').trim();
}

export function formatToolResultPreview(
  toolOutput: unknown,
  maxLen = 140,
): string {
  if (toolOutput == null) return '';
  const s =
    typeof toolOutput === 'string' ? toolOutput : JSON.stringify(toolOutput);
  return truncate(s.trim(), maxLen);
}

/** Subagent graph tick steps from deepagents (legacy id shape); one row per astream chunk — too noisy. */
const SUBAGENT_VALUES_STEP_ID = /^subagent-.+-values-\d+$/;

/** SSE `step` ids for adapter heartbeat labels (e.g. "开始分析...", "分析完成") — hide from user UI. */
const ADAPTER_CHROME_STEP_IDS = new Set([
  'analysis-start',
  'analysis-complete',
  'stream-init',
  'stream-init-resume',
  'hitl-waiting',
]);

/** True when this step id is synthetic progress chrome, not meaningful task content. */
export function isAdapterChromeStepId(id: string | undefined): boolean {
  if (!id) return false;
  return ADAPTER_CHROME_STEP_IDS.has(id);
}

/** Hide noisy progress steps that duplicate task UI. */
export function shouldHideStepRow(ev: { type: string; id?: string }): boolean {
  if (ev.type !== 'step') return false;
  const id = String(ev.id ?? '');
  if (isAdapterChromeStepId(id)) return true;
  return SUBAGENT_VALUES_STEP_ID.test(id);
}
