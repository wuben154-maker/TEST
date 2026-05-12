import { useState, useCallback, useMemo } from 'react';
import { Sparkles, X, Download, FileText, Link, Loader2, Maximize2, Minimize2 } from 'lucide-react';
import { Button } from '@/components/ui/button';
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuTrigger,
} from '@/components/ui/dropdown-menu';
import type { TaskStatsMeta, WorkspaceBlock, WorkspaceTabInstance } from '@/types/analysis';
import { AnalysisResult, AnalysisResultStats, AnalysisResultStatus } from '@/types/project';
import { buildActiveDisplayStats, buildLiveDisplayStats } from '@/lib/liveDisplayStats';
import { normalizeReportDocument, serializeReportMarkdown } from '@/lib/reportDocument';
import { exportToDocx } from '@/lib/docx-export';
import { exportHtmlFragmentToPdf } from '@/lib/reportPdf';
import { logger } from '@/lib/logger';
import { toast } from 'sonner';
import { useLanguage } from '@/contexts/LanguageContext';
import { useShareReport } from '@/hooks/useShareReport';
import { ScrollArea, ScrollBar } from '@/components/ui/scroll-area';
import { TaskHeader } from './workspace/TaskHeader';
import { TaskStatsBar } from './workspace/TaskStatsBar';
import { TaskTabPanel } from './workspace/TaskTabPanel';
import { ReportTab } from './workspace/tabs/ReportTab';

/** A task is "complex" (deserves the full panel layout) when it involves tool calls,
 *  workspace tabs, task plan, sandbox runs, or persisted chrome flag. Pure Q&A chat stays simple. */
function isComplexResult(result: AnalysisResult): boolean {
  if (result.useWorkspaceTaskPanel === true) return true;
  return (
    (result.stats.toolCallCount ?? 0) > 0 ||
    result.workspaceTabs.length > 0 ||
    (result.stats.sandboxRunCount ?? 0) > 0
  );
}

/** Minimal thinking dots for simple streaming when previous tabs already exist. */
function SimpleThinkingView() {
  return (
    <div className="flex-1 flex items-start justify-start p-6">
      <div className="flex items-center gap-1.5 text-muted-foreground">
        <span className="inline-block w-1.5 h-1.5 rounded-full bg-current animate-bounce [animation-delay:-0.3s]" />
        <span className="inline-block w-1.5 h-1.5 rounded-full bg-current animate-bounce [animation-delay:-0.15s]" />
        <span className="inline-block w-1.5 h-1.5 rounded-full bg-current animate-bounce" />
      </div>
    </div>
  );
}

/**
 * Animated center shown when a simple (non-agentic) response is streaming
 * and there are no prior result tabs. Keeps the Smart Canvas branding visible
 * and replaces the static star with a continuously rotating one.
 */
function AnimatedSparkleCenter({ smartCanvasTitle, smartCanvasDesc }: {
  smartCanvasTitle: string;
  smartCanvasDesc: string;
}) {
  return (
    <div className="flex-1 flex flex-col items-center justify-center min-h-[400px] text-muted-foreground px-6">
      <div className="relative w-20 h-20 flex items-center justify-center mb-6">
        {/* Expanding halo */}
        <span
          className="absolute inset-0 rounded-2xl bg-primary/10 animate-ping"
          style={{ animationDuration: '2s', animationTimingFunction: 'ease-out' }}
        />
        {/* Rotating icon box */}
        <div className="relative w-20 h-20 rounded-2xl bg-muted/30 flex items-center justify-center">
          <Sparkles
            className="w-10 h-10 text-primary/70 animate-spin"
            style={{ animationDuration: '4s', animationTimingFunction: 'linear' }}
          />
        </div>
      </div>
      <h3 className="text-lg font-medium text-foreground mb-2">{smartCanvasTitle}</h3>
      <p className="text-sm text-center max-w-sm text-muted-foreground">{smartCanvasDesc}</p>
    </div>
  );
}

/** Props for the "live" currently-running result (from streaming state). */
export interface LiveResultProps {
  isActive: boolean;
  blocks: WorkspaceBlock[];
  workspaceTabs: WorkspaceTabInstance[];
  toolCallCount: number;
  sandboxRunCount: number;
  resultStartTime?: number;
  userInput: string;
  /** True once a task_plan event has been received — triggers complex layout. */
  hasTaskPlan?: boolean;
  /** Backend correlation id for the current turn. */
  currentRequestId?: string;
  /** True when the current turn included file uploads. */
  hasAttachments?: boolean;
  /** Backend-owned TaskStatsMeta from SSE conclusion.meta (security/research). */
  statsMeta?: TaskStatsMeta;
}

interface LiveWorkspaceProps {
  analysisResults?: AnalysisResult[];
  activeResultId?: string;
  onSelectResult?: (resultId: string) => void;
  onRemoveResult?: (resultId: string) => void;
  onRenameResult?: (resultId: string, newTitle: string) => void;
  /** Live streaming state for the currently running analysis. */
  liveResult?: LiveResultProps;
  /** Desktop: report panel is expanded (chat collapsed). */
  reportPanelMaximized?: boolean;
  /** Toggle expand report / restore split (desktop). */
  onToggleReportPanelMaximize?: () => void;
}

const LIVE_TAB_ID = '__live__';
const EMPTY_WORKSPACE_BLOCKS: WorkspaceBlock[] = [];
const EMPTY_WORKSPACE_TABS: WorkspaceTabInstance[] = [];

/** When follow-up clears live blocks before SSE arrives, keep showing the user's selected turn. */
function pickHistoricalAnalysisResult(
  analysisResults: AnalysisResult[],
  activeResultId?: string,
): AnalysisResult | undefined {
  if (analysisResults.length === 0) return undefined;
  if (activeResultId) {
    const found = analysisResults.find((r) => r.id === activeResultId);
    if (found) return found;
  }
  return analysisResults[analysisResults.length - 1];
}

export function LiveWorkspace({
  analysisResults = [],
  activeResultId,
  onSelectResult,
  onRemoveResult,
  onRenameResult,
  liveResult,
  reportPanelMaximized = false,
  onToggleReportPanelMaximize,
}: LiveWorkspaceProps) {
  const { t } = useLanguage();
  const { shareAsLink, isSharing } = useShareReport();
  const [editingTabId, setEditingTabId] = useState<string | null>(null);
  const [exportingDocx, setExportingDocx] = useState(false);
  const [exportingPdf, setExportingPdf] = useState(false);
  // Local edit state: resultId → edited plain text (session-only, not persisted)
  const [editedReports, setEditedReports] = useState<Map<string, string>>(new Map());

  const handleEditReport = useCallback((resultId: string, text: string) => {
    setEditedReports((prev) => new Map(prev).set(resultId, text));
  }, []);

  const isStreaming = liveResult?.isActive ?? false;

  // Build the unified result list: completed results + optionally a live one
  const hasResults = analysisResults.length > 0;

  const historicalResult = useMemo(
    () => pickHistoricalAnalysisResult(analysisResults, activeResultId),
    [analysisResults, activeResultId],
  );

  // Prefer the selected/completed tab while streaming a follow-up so the outer
  // chrome does not mimic a synthetic "__live__" tab and discard report content.
  const currentActiveId =
    isStreaming && hasResults
      ? historicalResult?.id
      : isStreaming
        ? LIVE_TAB_ID
        : activeResultId || historicalResult?.id;

  const activeResult = analysisResults.find((r) => r.id === currentActiveId);

  // After a stream completes (isActive=false), there is a brief gap before the
  // analysis is persisted into analysisResults and the live state is cleared.
  // During that gap, fall back to the live result data so the user doesn't see
  // a flash of empty content or a stale previous result.
  const liveBlocks = liveResult?.blocks ?? EMPTY_WORKSPACE_BLOCKS;
  const pendingFinalize = !isStreaming && liveBlocks.length > 0;

  /** Live state cleared for a new turn, but UI still renders the prior turn's snapshot — pin title/date/stats there. */
  const streamingPinsPriorCompletedReportChrome = Boolean(
    isStreaming &&
    hasResults &&
    !!historicalResult &&
    liveBlocks.length === 0 &&
    (historicalResult.blocks?.length ?? 0) > 0,
  );

  // Determine the content to render
  const displayStatus: AnalysisResultStatus = isStreaming
    ? 'running'
    : (pendingFinalize ? 'done' : (activeResult?.status ?? 'done'));

  const displayBlocks: WorkspaceBlock[] = useMemo(() => {
    if (isStreaming) {
      if (liveBlocks.length > 0) return liveBlocks;
      if (hasResults && historicalResult?.blocks?.length) {
        return historicalResult.blocks;
      }
      return EMPTY_WORKSPACE_BLOCKS;
    }
    if (pendingFinalize) return liveBlocks;
    return activeResult?.blocks ?? EMPTY_WORKSPACE_BLOCKS;
  }, [activeResult?.blocks, hasResults, historicalResult, isStreaming, liveBlocks, pendingFinalize]);

  const displayTabs: WorkspaceTabInstance[] = useMemo(() => {
    if (isStreaming) {
      const liveTabs = liveResult?.workspaceTabs ?? EMPTY_WORKSPACE_TABS;
      if (liveTabs.length > 0) return liveTabs;
      if (hasResults && historicalResult?.workspaceTabs?.length) {
        return historicalResult.workspaceTabs;
      }
      return EMPTY_WORKSPACE_TABS;
    }
    if (pendingFinalize) return liveResult?.workspaceTabs ?? EMPTY_WORKSPACE_TABS;
    return activeResult?.workspaceTabs ?? EMPTY_WORKSPACE_TABS;
  }, [
    activeResult?.workspaceTabs,
    hasResults,
    historicalResult,
    isStreaming,
    liveResult?.workspaceTabs,
    pendingFinalize,
  ]);

  const displayStats: AnalysisResultStats = useMemo(
    () => {
      if (streamingPinsPriorCompletedReportChrome && historicalResult) {
        return buildActiveDisplayStats({ stats: historicalResult.stats });
      }
      if (isStreaming || pendingFinalize) {
        return buildLiveDisplayStats({
          statsMeta: liveResult?.statsMeta,
          toolCallCount: liveResult?.toolCallCount,
          sandboxRunCount: liveResult?.sandboxRunCount,
          resultStartTime: liveResult?.resultStartTime,
        });
      }
      return buildActiveDisplayStats({ stats: activeResult?.stats });
    },
    [
      activeResult?.stats,
      historicalResult,
      isStreaming,
      liveResult?.resultStartTime,
      liveResult?.sandboxRunCount,
      liveResult?.statsMeta,
      liveResult?.toolCallCount,
      pendingFinalize,
      streamingPinsPriorCompletedReportChrome,
    ],
  );

  // Stats bar now renders straight from the backend-owned profile
  // (`conclusion.meta`) that lives on `displayStats`. No more block-regex
  // derivation of severity / risk / actionable from frontend markdown.

  const displayHeadline = useMemo(() => {
    if (isStreaming) {
      if (streamingPinsPriorCompletedReportChrome && historicalResult) {
        const u = historicalResult.userInput?.trim();
        if (u) return u;
        return historicalResult.title?.trim() || t.workspace.taskPanel.analysisResult;
      }
      return liveResult?.userInput?.trim() || t.command.analyzing;
    }
    if (pendingFinalize) {
      return liveResult?.userInput?.trim() || t.workspace.taskPanel.analysisResult;
    }
    if (!activeResult) return '';
    const u = activeResult.userInput?.trim();
    if (u) return u;
    return activeResult.title?.trim() || t.workspace.taskPanel.analysisResult;
  }, [
    activeResult,
    historicalResult,
    isStreaming,
    pendingFinalize,
    liveResult,
    streamingPinsPriorCompletedReportChrome,
    t,
  ]);

  const tp = t.workspace.taskPanel;
  const sourceLabel = useMemo(() => {
    const parts: string[] = [];
    if (liveResult?.hasAttachments) parts.push(tp.sourceUpload);
    if ((displayStats.sandboxRunCount ?? 0) > 0) parts.push(tp.sourceSandbox);
    if (displayBlocks.some((b) => b.type === 'intel')) parts.push(tp.sourceTi);
    return parts.length > 0 ? parts.join(' / ') : undefined;
  }, [displayBlocks, liveResult?.hasAttachments, displayStats.sandboxRunCount, tp]);

  const displayGeneratedAt = useMemo(() => {
    if (isStreaming || pendingFinalize) {
      if (streamingPinsPriorCompletedReportChrome && historicalResult?.timestamp) {
        return historicalResult.timestamp instanceof Date
          ? historicalResult.timestamp.toISOString()
          : undefined;
      }
      return liveResult?.resultStartTime
        ? new Date(liveResult.resultStartTime).toISOString()
        : undefined;
    }
    return activeResult?.timestamp instanceof Date
      ? activeResult.timestamp.toISOString()
      : undefined;
  }, [
    activeResult?.timestamp,
    historicalResult,
    isStreaming,
    liveResult?.resultStartTime,
    pendingFinalize,
    streamingPinsPriorCompletedReportChrome,
  ]);

  // Determine whether to use the complex layout (Task header + stats bar + inner tabs).
  // Simple Q&A (no tool calls, no task plan, no workspace tabs) uses a lightweight display.
  const liveIsComplex =
    (liveResult?.toolCallCount ?? 0) > 0 ||
    (liveResult?.workspaceTabs ?? []).length > 0 ||
    (liveResult?.sandboxRunCount ?? 0) > 0 ||
    !!liveResult?.hasTaskPlan;

  const streamingStickyComplexChrome = Boolean(
    isStreaming &&
    hasResults &&
    historicalResult &&
    isComplexResult(historicalResult) &&
    !liveIsComplex,
  );

  const isComplex: boolean = isStreaming || pendingFinalize
    ? (liveIsComplex || streamingStickyComplexChrome)
    : (activeResult ? isComplexResult(activeResult) : false);

  // Simple streaming with no prior tabs → replace the whole workspace with the animated center.
  // No outer tab entry is created; the empty-state canvas is reused with a rotating star.
  // Once a tool call / task plan arrives (liveIsComplex = true) we switch to the full layout.
  const showAnimatedCenter = isStreaming && !hasResults && !liveIsComplex;

  // The outer tab bar and main content only render when there is real tabbed content.
  // showAnimatedCenter deliberately suppresses hasAnyContent so no streaming tab is created.
  const hasAnyContent = !showAnimatedCenter && (hasResults || isStreaming || pendingFinalize);

  const buildReportExportMarkdown = useCallback(() => {
    const footer = `\n\n---\n*${t.workspace.generatedBy}*`;
    const edited =
      currentActiveId && !isStreaming ? editedReports.get(currentActiveId) : undefined;
    if (edited !== undefined) {
      const body = edited.trimEnd();
      if (body.length > 0) {
        return `${body}${footer}`;
      }
    }

    const reportDocument = normalizeReportDocument({
      id: currentActiveId || 'report',
      title: displayHeadline || t.workspace.title,
      blocks: displayBlocks,
      stats: displayStats,
      generatedAt: displayGeneratedAt,
      copy: {
        templates: t.workspace.reportTemplates,
        risk: tp.risk,
        sources: tp.sourceCount,
        severityLabels: tp.severityLabels,
      },
    });
    return `${serializeReportMarkdown(reportDocument)}${footer}`;
  }, [
    currentActiveId,
    displayBlocks,
    displayGeneratedAt,
    displayHeadline,
    displayStats,
    editedReports,
    isStreaming,
    t.workspace.generatedBy,
    t.workspace.reportTemplates,
    t.workspace.title,
    tp.risk,
    tp.severityLabels,
    tp.sourceCount,
  ]);

  const handleExportMarkdown = useCallback(() => {
    const markdown = buildReportExportMarkdown();
    const blob = new Blob([markdown], { type: 'text/markdown' });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = `secmanus-report-${Date.now()}.md`;
    a.click();
    URL.revokeObjectURL(url);
  }, [buildReportExportMarkdown]);

  const handleExportDocx = useCallback(async () => {
    setExportingDocx(true);
    try {
      const md = buildReportExportMarkdown();
      const { reportMarkdownToExportHtml } = await import('@/lib/reportMarkdownHtml');
      const html = reportMarkdownToExportHtml(md);
      await exportToDocx(html, `secmanus-report-${Date.now()}`);
      toast.success(t.document.wordExportSuccess);
    } catch (error) {
      logger.error('workspace_docx_export_failed', { error: String(error) });
      toast.error(t.document.exportFailedRetry);
    } finally {
      setExportingDocx(false);
    }
  }, [buildReportExportMarkdown, t.document.exportFailedRetry, t.document.wordExportSuccess]);

  const handleExportPdf = useCallback(async () => {
    setExportingPdf(true);
    try {
      const md = buildReportExportMarkdown();
      const { reportMarkdownToExportHtml } = await import('@/lib/reportMarkdownHtml');
      const html = reportMarkdownToExportHtml(md);
      await exportHtmlFragmentToPdf(html, `secmanus-report-${Date.now()}`);
      toast.success(t.document.pdfExportSuccess);
    } catch (error) {
      logger.error('workspace_pdf_export_failed', { error: String(error) });
      toast.error(t.document.pdfExportFailedRetry);
    } finally {
      setExportingPdf(false);
    }
  }, [buildReportExportMarkdown, t.document.pdfExportFailedRetry, t.document.pdfExportSuccess]);

  const showReportActions = displayBlocks.length > 0 && displayStatus !== 'running';

  const shareAndExportButtons = showReportActions ? (
    <>
      <Button
        type="button"
        variant="outline"
        size="sm"
        className="h-8 gap-1.5 px-2.5 text-xs text-muted-foreground hover:text-foreground"
        onClick={() => shareAsLink(displayBlocks, t.workspace.title)}
        disabled={isSharing}
        aria-label={t.workspace.share}
      >
        {isSharing ? (
          <Loader2 className="h-3.5 w-3.5 animate-spin" />
        ) : (
          <Link className="h-3.5 w-3.5" />
        )}
        <span className="hidden sm:inline">{t.workspace.share}</span>
      </Button>
      <DropdownMenu>
        <DropdownMenuTrigger asChild>
          <Button
            type="button"
            variant="outline"
            size="sm"
            className="h-8 gap-1.5 border-border px-2.5 text-xs text-muted-foreground hover:text-foreground"
            aria-label={t.workspace.export}
          >
            <Download className="h-3.5 w-3.5" />
            <span className="hidden sm:inline">{t.workspace.export}</span>
          </Button>
        </DropdownMenuTrigger>
        <DropdownMenuContent align="end" className="min-w-[160px]">
          <DropdownMenuItem onClick={handleExportMarkdown}>
            <FileText className="mr-2 h-3.5 w-3.5 text-muted-foreground" />
            {t.workspace.exportMarkdownFile}
          </DropdownMenuItem>
          <DropdownMenuItem onClick={handleExportPdf} disabled={exportingPdf}>
            {exportingPdf ? (
              <Loader2 className="mr-2 h-3.5 w-3.5 animate-spin text-muted-foreground" />
            ) : (
              <FileText className="mr-2 h-3.5 w-3.5 text-muted-foreground" />
            )}
            {t.document.pdfDoc}
          </DropdownMenuItem>
          <DropdownMenuItem onClick={handleExportDocx} disabled={exportingDocx}>
            {exportingDocx ? (
              <Loader2 className="mr-2 h-3.5 w-3.5 animate-spin text-muted-foreground" />
            ) : (
              <FileText className="mr-2 h-3.5 w-3.5 text-muted-foreground" />
            )}
            {t.document.wordDoc}
          </DropdownMenuItem>
        </DropdownMenuContent>
      </DropdownMenu>
    </>
  ) : null;

  const reportActionsToolbar =
    !isComplex && showReportActions ? (
      <div className="flex shrink-0 items-center justify-end gap-1.5 border-b border-border bg-background px-3 py-1.5">
        {shareAndExportButtons}
      </div>
    ) : null;

  const complexHeaderActions =
    isComplex && (showReportActions || onToggleReportPanelMaximize) ? (
      <>
        {shareAndExportButtons}
        {onToggleReportPanelMaximize ? (
          <Button
            type="button"
            variant="outline"
            size="sm"
            className="h-8 px-2.5 text-muted-foreground hover:text-foreground"
            onClick={onToggleReportPanelMaximize}
            aria-label={
              reportPanelMaximized ? tp.reportExitFullscreen : tp.reportFullscreen
            }
            title={reportPanelMaximized ? tp.reportExitFullscreen : tp.reportFullscreen}
          >
            {reportPanelMaximized ? (
              <Minimize2 className="h-3.5 w-3.5" />
            ) : (
              <Maximize2 className="h-3.5 w-3.5" />
            )}
          </Button>
        ) : null}
      </>
    ) : null;

  return (
    <div className="flex flex-col h-full w-full bg-background overflow-hidden">

      {/* ── Outer result Tab Bar (GitHub underline style) ───────── */}
      {hasAnyContent && (
        <div className="flex-shrink-0 border-b border-border bg-background">
          <ScrollArea className="w-full whitespace-nowrap">
            <div className="flex px-4">
              {/* Completed result tabs */}
              {analysisResults.map((result, index) => {
                const isActive = result.id === currentActiveId;
                return (
                  <div
                    key={result.id}
                    className={`
                      inline-flex items-center gap-1 px-3 py-2.5 text-xs font-medium
                      border-b-2 -mb-px transition-colors group cursor-pointer
                      ${isActive
                        ? 'border-primary text-foreground'
                        : 'border-transparent text-muted-foreground hover:text-foreground hover:border-muted-foreground/40'
                      }
                    `}
                  >
                    {editingTabId === result.id ? (
                      <input
                        autoFocus
                        className="max-w-[120px] bg-transparent border-b border-current outline-none text-xs"
                        defaultValue={result.title || `${t.projects.analysisTitlePrefix} ${index + 1}`}
                        onBlur={(e) => {
                          const val = e.target.value.trim();
                          if (val && val !== result.title) onRenameResult?.(result.id, val);
                          setEditingTabId(null);
                        }}
                        onKeyDown={(e) => {
                          if (e.key === 'Enter') e.currentTarget.blur();
                          if (e.key === 'Escape') setEditingTabId(null);
                        }}
                      />
                    ) : (
                      <button
                        onClick={() => !isStreaming && onSelectResult?.(result.id)}
                        onDoubleClick={() => setEditingTabId(result.id)}
                        className="max-w-[120px] truncate text-left"
                        title={result.userInput}
                      >
                        {result.title || `${t.projects.analysisTitlePrefix} ${index + 1}`}
                      </button>
                    )}
                    <button
                      onClick={(e) => {
                        e.stopPropagation();
                        onRemoveResult?.(result.id);
                      }}
                      className="p-0.5 rounded opacity-0 group-hover:opacity-60 hover:!opacity-100 transition-opacity hover:bg-muted"
                      title={t.document.closeTab}
                    >
                      <X className="w-3 h-3" />
                    </button>
                  </div>
                );
              })}

              {/* Live streaming / pending-finalize affordance — skip the extra pulsing
                  tab when a follow-up already has history tabs (redundant tab animation). */}
              {(isStreaming || pendingFinalize) && !(isStreaming && hasResults) && (
                <div className={`inline-flex items-center gap-1.5 px-3 py-2.5 text-xs font-medium border-b-2 -mb-px ${
                  isStreaming
                    ? 'border-blue-500 text-blue-600 dark:text-blue-400'
                    : 'border-primary text-foreground'
                }`}>
                  {isStreaming && (
                    <span className="relative flex h-1.5 w-1.5 flex-shrink-0">
                      <span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-blue-400 opacity-75" />
                      <span className="relative inline-flex rounded-full h-1.5 w-1.5 bg-blue-500" />
                    </span>
                  )}
                  <span className="max-w-[120px] truncate">
                    {liveResult?.userInput?.slice(0, 20) || t.command.analyzing}
                  </span>
                </div>
              )}
            </div>
            <ScrollBar orientation="horizontal" />
          </ScrollArea>
        </div>
      )}

      {/* ── Main content area ────────────────────────────────────── */}
      {showAnimatedCenter ? (
        /* ── Animated center: simple streaming, no prior tabs, no outer tab created ── */
        <AnimatedSparkleCenter
          smartCanvasTitle={t.workspace.smartCanvas}
          smartCanvasDesc={t.workspace.empty}
        />
      ) : hasAnyContent ? (
        <div className="flex flex-col flex-1 min-h-0">
          {isComplex ? (
            /* ── Complex layout: header + stats + inner tabs ── */
            <>
              <TaskHeader title={displayHeadline} headerActions={complexHeaderActions} />
              <TaskStatsBar
                stats={displayStats}
                status={displayStatus}
                sourceLabel={sourceLabel}
              />
              <div id="workspace-content" className="flex min-h-0 flex-1 flex-col overflow-hidden">
                <div className="flex min-h-0 flex-1 flex-col overflow-hidden">
                  <TaskTabPanel
                    status={displayStatus}
                    blocks={displayBlocks}
                    workspaceTabs={displayTabs}
                    reportTitle={displayHeadline}
                    generatedAt={displayGeneratedAt}
                    stats={displayStats}
                    editedReportText={currentActiveId && !isStreaming ? editedReports.get(currentActiveId) : undefined}
                    onEditReport={!isStreaming && currentActiveId ? (text) => handleEditReport(currentActiveId, text) : undefined}
                  />
                </div>
              </div>
            </>
          ) : (
            /* ── Simple layout: no header/stats/tabs chrome ── */
            <div className="flex min-h-0 flex-1 flex-col overflow-hidden">
              {isStreaming ? (
                displayBlocks.length === 0 ? (
                  <SimpleThinkingView />
                ) : (
                  <>
                    {reportActionsToolbar}
                    <ScrollArea className="min-h-0 flex-1">
                      <div id="workspace-content" className="p-4 md:p-6">
                        <ReportTab
                          status={displayStatus}
                          blocks={displayBlocks}
                          title={displayHeadline}
                          generatedAt={displayGeneratedAt}
                          stats={displayStats}
                        />
                      </div>
                    </ScrollArea>
                  </>
                )
              ) : (
                <>
                  {reportActionsToolbar}
                  <ScrollArea className="min-h-0 flex-1">
                    <div id="workspace-content" className="p-4 md:p-6">
                      <ReportTab
                        status={displayStatus}
                        blocks={displayBlocks}
                        title={displayHeadline}
                        generatedAt={displayGeneratedAt}
                        stats={displayStats}
                        editedText={currentActiveId && !isStreaming ? editedReports.get(currentActiveId) : undefined}
                        onSave={!isStreaming && currentActiveId ? (text) => handleEditReport(currentActiveId, text) : undefined}
                      />
                    </div>
                  </ScrollArea>
                </>
              )}
            </div>
          )}
        </div>
      ) : (
        /* Empty state */
        <div className="flex-1 flex flex-col items-center justify-center min-h-[400px] text-muted-foreground px-6">
          <div className="w-20 h-20 rounded-2xl bg-muted/30 flex items-center justify-center mb-6">
            <Sparkles className="w-10 h-10 text-muted-foreground/40 animate-pulse" style={{ animationDuration: '3s' }} />
          </div>
          <h3 className="text-lg font-medium text-foreground mb-2">{t.workspace.smartCanvas}</h3>
          <p className="text-sm text-center max-w-sm text-muted-foreground">
            {t.workspace.empty}
          </p>
        </div>
      )}
    </div>
  );
}
