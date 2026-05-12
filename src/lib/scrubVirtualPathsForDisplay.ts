import type { TaskPlan } from '@/types/analysis';
import path from 'node:path';

/** UNC \\server\share\last — same ordering as Python path_display_redact. */
const UNC_PATH_RE = /(?<![\\])(\\{2}[^\\\r\n]+(?:\\[^\\\r\n]+)+)/g;
const WIN_ABS_PATH_RE =
  /(?<![A-Za-z0-9])([A-Za-z]:)(?:\\|\/)(?:[^\\/:*?"<>|\r\n]+(?:\\|\/))*[^\\/:*?"<>|\r\n]+/g;
const UNIX_UPLOADS_RE = /(?<![A-Za-z0-9/])\/[^\s\r\n]*?\/uploads\/u_[^\s\r\n]+/g;

function workspaceBasenameLabel(raw: string): string {
  let t = raw.trim();
  while (t.length > 0 && '.,;:!?)\'"'.includes(t[t.length - 1]!)) {
    t = t.slice(0, -1).trimEnd();
  }
  if (!t) return '/workspace/<redacted>';
  const isWin = /^[A-Za-z]:[\\/]/.test(t) || t.startsWith('\\\\');
  const name = isWin ? path.win32.basename(t) : path.posix.basename(t.replace(/\\/g, '/'));
  if (!name || name === '.' || name === '..') return '/workspace/<redacted>';
  return `/workspace/${name}`;
}

/**
 * Replace host absolute paths (Windows drive, UNC, unix .../uploads/u_...) with
 * ``/workspace/<basename>`` so task lists never leak server layout.
 */
export function redactHostPathsForDisplay(text: string): string {
  if (!text) return text;
  const repl = (m: string) => workspaceBasenameLabel(m);
  return text.replace(UNC_PATH_RE, repl).replace(WIN_ABS_PATH_RE, repl).replace(UNIX_UPLOADS_RE, repl);
}

/**
 * Normalize SecManus virtual path spellings in short user-visible strings
 * (task titles, tool labels not passed through backend path_scrub).
 *
 * Mirrors Python `fold_workspace_ui_spelling` / scrub workspace label: PascalCase
 * `Workspace/` → `workspace/`.
 * Also redacts host filesystem paths (same policy as backend path_display_redact).
 */
export function scrubVirtualPathsForDisplay(text: string): string {
  if (!text) return text;
  const normalized = text
    .replace(/\/Workspace\//g, '/workspace/')
    .replace(/(?<![\w/])Workspace\//g, 'workspace/');
  return redactHostPathsForDisplay(normalized);
}

/** Apply {@link scrubVirtualPathsForDisplay} to every task title / plan heading field. */
export function scrubTaskPlanPathsForDisplay(plan: TaskPlan): TaskPlan {
  const scrub = scrubVirtualPathsForDisplay;
  return {
    ...plan,
    workspaceTitle: plan.workspaceTitle ? scrub(plan.workspaceTitle) : plan.workspaceTitle,
    tasks: plan.tasks.map((t) => ({
      ...t,
      title: scrub(t.title),
      description:
        t.description !== undefined && t.description !== null
          ? scrub(String(t.description))
          : t.description,
      result:
        t.result !== undefined && t.result !== null ? scrub(String(t.result)) : t.result,
      error: t.error !== undefined && t.error !== null ? scrub(String(t.error)) : t.error,
    })),
  };
}
