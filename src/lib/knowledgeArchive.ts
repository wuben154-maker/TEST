/**
 * Archive professional-task reports (security / research) to backend knowledge storage as .docx.
 */
import type { WorkspaceBlock } from '@/types/analysis';
import type { Language } from '@/i18n';
import type { PerProjectStreamingState } from '@/types/streaming';
import type { AnalysisResultStats } from '@/types/project';
import type { KnowledgeArchiveNotice } from '@/types/project';
import { getTranslations } from '@/i18n';
import { logger } from '@/lib/logger';
import { htmlToDocxBlob } from '@/lib/docx-export';
import { normalizeReportDocument, serializeReportMarkdown, type ReportDocumentCopy } from '@/lib/reportDocument';
import { parseMarkdownToHtml } from '@/lib/documentWorkspaceMarkdown';
import { knowledgeApi, getAuthToken } from '@/lib/api-client';
import { toast } from 'sonner';
import { analysisTurnHasBlockingError } from '@/lib/analysisTurnErrors';

const STORAGE_PREFIX = 'kb-archived:';

/** Max wall-clock wait for Markdown → HTML → `.docx` → upload (`POST /knowledge/reports`). */
export const KNOWLEDGE_ARCHIVE_TIMEOUT_MS = 3 * 60 * 1000;

class KnowledgeArchiveDeadlineError extends Error {
  override readonly name = 'KnowledgeArchiveDeadlineError';
  constructor() {
    super('Knowledge archive deadline exceeded');
  }
}

/**
 * Completes ``promise`` or rejects with ``KnowledgeArchiveDeadlineError`` after ``ms``.
 * Runs ``onDeadline`` synchronously before rejecting so callers can e.g. ``AbortSignal``.
 */
export function attachKnowledgeArchiveDeadline<T>(
  promise: Promise<T>,
  ms: number,
  onDeadline: () => void,
): Promise<T> {
  return new Promise((resolve, reject) => {
    const tid = window.setTimeout(() => {
      promise.catch(() => {
        /* Swallow orphaned rejection when we fire the deadline instead (e.g. fetch AbortError). */
      });
      try {
        onDeadline();
      } catch {
        /* ignore */
      }
      reject(new KnowledgeArchiveDeadlineError());
    }, ms);

    promise.then(
      (v) => {
        window.clearTimeout(tid);
        resolve(v);
      },
      (err) => {
        window.clearTimeout(tid);
        reject(err instanceof Error ? err : new Error(String(err)));
      },
    );
  });
}

function buildReportCopy(lang: Language): ReportDocumentCopy {
  const tw = getTranslations(lang).workspace;
  return {
    templates: tw.reportTemplates,
    risk: tw.taskPanel.risk,
    sources: tw.taskPanel.sourceCount,
    severityLabels: tw.taskPanel.severityLabels,
  };
}

/** Derive a short human-readable label for filenames + UI (not the raw message id). */
function deriveReportTitleLabel(
  docTitle: string,
  projectTitle: string | undefined,
  userInput: string | undefined,
  language: Language,
): string {
  const fromDoc = (docTitle || '').trim();
  if (fromDoc && !/^analysis report$/i.test(fromDoc)) {
    return fromDoc.slice(0, 120);
  }
  const pt = (projectTitle || '').trim();
  if (pt) return pt.slice(0, 120);
  const ui = (userInput || '').trim().replace(/\s+/g, ' ');
  if (ui) return ui.slice(0, 80);
  return getTranslations(language).knowledgeBase.reportDefaultTitle;
}

export type KnowledgeArchivingPhase = 'start' | 'error' | 'timeout';

export interface ArchiveKnowledgeParams {
  language: Language;
  projectId: string;
  projectTitle?: string;
  state: PerProjectStreamingState;
  /** Called when .docx generation begins (slow) so the chat row can show a “saving” line */
  onArchivingPhase?: (phase: KnowledgeArchivingPhase, messageId: string) => void;
  /** Called after successful POST so the UI can deep-link the saved file. */
  onSuccess?: (info: KnowledgeArchiveNotice & { requestId: string }) => void;
}

/**
 * When a professional turn completes, generate a .docx and POST to `/knowledge/reports`.
 * Idempotent per (projectId, messageId) via sessionStorage and stable filename on server.
 */
export async function tryArchiveProfessionalReportToKnowledge(params: ArchiveKnowledgeParams): Promise<void> {
  const { language, projectId, projectTitle, state, onSuccess, onArchivingPhase } = params;

  if (analysisTurnHasBlockingError(state)) {
    logger.info('knowledge_archive_skipped_error_turn', { projectId });
    return;
  }

  const tk = state.statsMeta?.taskKind;
  if (tk !== 'security' && tk !== 'research') return;
  if (!getAuthToken()) return;
  if (!state.blocks?.length) return;

  const messageId = (state.completedRequestId || '').trim();
  if (!messageId) {
    logger.warn('knowledge_archive_missing_message_id', { projectId });
    return;
  }

  const storeKey = `${STORAGE_PREFIX}${projectId}:${messageId}`;
  try {
    if (typeof sessionStorage !== 'undefined' && sessionStorage.getItem(storeKey)) {
      return;
    }
  } catch {
    /* ignore */
  }

  const headline = (projectTitle || '').trim() || `Project ${projectId.slice(0, 8)}`;
  const generatedAt = state.resultStartTime
    ? new Date(state.resultStartTime).toISOString()
    : new Date().toISOString();

  const tp = getTranslations(language).knowledgeBase;

  let archivingUiStarted = false;
  const uploadAbort = new AbortController();

  try {
    const doc = normalizeReportDocument({
      id: messageId,
      title: headline,
      blocks: state.blocks as WorkspaceBlock[],
      stats: state.statsMeta as AnalysisResultStats | undefined,
      generatedAt,
      copy: buildReportCopy(language),
    });
    const reportLabel = deriveReportTitleLabel(doc.title, projectTitle, state.userInput, language);
    const md = serializeReportMarkdown(doc).trim();
    if (!md) return;

    const html = parseMarkdownToHtml(md);
    onArchivingPhase?.('start', messageId);
    archivingUiStarted = true;

    const pipeline = async (): Promise<Record<string, unknown>> => {
      const blob = await htmlToDocxBlob(html);
      const fd = new FormData();
      fd.append('file', blob, 'report.docx');
      fd.append('message_id', messageId);
      fd.append('project_id', projectId);
      fd.append('task_kind', tk);
      fd.append('report_title', reportLabel);
      return knowledgeApi.uploadReport(fd, { signal: uploadAbort.signal });
    };

    const raw = await attachKnowledgeArchiveDeadline(
      pipeline(),
      KNOWLEDGE_ARCHIVE_TIMEOUT_MS,
      () => uploadAbort.abort(),
    );

    const filename = typeof raw.filename === 'string' ? raw.filename : '';
    const displayPath = typeof raw.display_path === 'string' ? raw.display_path : '';
    if (!filename || !displayPath) {
      logger.warn('knowledge_archive_missing_response_fields', { projectId, raw });
    }

    try {
      sessionStorage.setItem(storeKey, '1');
    } catch {
      /* ignore */
    }

    if (filename && displayPath && onSuccess) {
      onSuccess({
        requestId: messageId,
        filename,
        displayPath,
        reportLabel,
      });
    } else if (archivingUiStarted) {
      onArchivingPhase?.('error', messageId);
    }
  } catch (e) {
    if (e instanceof KnowledgeArchiveDeadlineError) {
      logger.warn('knowledge_archive_deadline', { projectId, messageId, ms: KNOWLEDGE_ARCHIVE_TIMEOUT_MS });
      if (archivingUiStarted) {
        onArchivingPhase?.('timeout', messageId);
        toast.error(tp.archivingTimeout);
      }
      return;
    }

    const msg = e instanceof Error ? e.message : String(e);
    logger.error('knowledge_archive_failed', { projectId, error: msg });
    if (archivingUiStarted) {
      onArchivingPhase?.('error', messageId);
    }
    toast.error(tp.archiveFailed, { description: msg });
  }
}

/**
 * Maps ``GET /messages/project/...`` row field ``knowledge_archive`` (snake_case JSON or camelCase)
 * into {@link KnowledgeArchiveNotice} for chat hydration after refresh.
 */
export function parseKnowledgeArchiveFromRow(raw: unknown): KnowledgeArchiveNotice | undefined {
  if (raw == null || typeof raw !== 'object' || Array.isArray(raw)) return undefined;
  const o = raw as Record<string, unknown>;
  const filename = typeof o.filename === 'string' ? o.filename : '';
  const displayPath =
    typeof o.displayPath === 'string'
      ? o.displayPath
      : typeof o.display_path === 'string'
        ? o.display_path
        : '';
  const reportLabel =
    typeof o.reportLabel === 'string'
      ? o.reportLabel
      : typeof o.report_label === 'string'
        ? o.report_label
        : '';
  const pending = typeof o.pending === 'boolean' ? o.pending : undefined;
  if (!filename && pending !== true) return undefined;
  return {
    pending,
    filename: filename || '',
    displayPath: displayPath || '',
    reportLabel: reportLabel || '',
  };
}
