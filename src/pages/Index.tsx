import { useEffect, useState, useCallback, useRef, useMemo } from 'react';
import { flushSync } from 'react-dom';
import { useOutletContext, useNavigate, useLocation } from 'react-router-dom';
import { Columns2, FileText, MessageSquare } from 'lucide-react';
import {
  Panel,
  PanelGroup,
  PanelResizeHandle,
  type ImperativePanelHandle,
} from 'react-resizable-panels';
import { Button } from '@/components/ui/button';
import { Tooltip, TooltipContent, TooltipTrigger } from '@/components/ui/tooltip';
import { CommandCenter } from '@/components/CommandCenter';
import { PostLoginWorkspaceStart } from '@/components/PostLoginWorkspaceStart';
import { LiveWorkspace } from '@/components/LiveWorkspace';
import { DevModePanel } from '@/components/DevModePanel';
import { TopNavbar } from '@/components/TopNavbar';
import type { WorkspaceOutletContext } from '@/components/AppWorkspaceShell';
import { useStreamingAnalysisMulti } from '@/hooks/useStreamingAnalysisMulti';
import { useStreamingStateContext } from '@/contexts/StreamingStateContext';
import { useWorkspaceProjects } from '@/contexts/WorkspaceProjectsContext';
import { useAnalysisProgressRestore } from '@/hooks/useAnalysisProgressRestore';
import { createEmptyStreamingState } from '@/types/streaming';
import { useConversationPersistence } from '@/hooks/useConversationPersistence';
import { useLanguage } from '@/contexts/LanguageContext';
import { UploadedAttachment } from '@/components/CommandCenter';
import { projectsApi, messagesApi } from '@/lib/api-client';
import { logger } from '@/lib/logger';
import { toast } from 'sonner';
import {
  readPostLoginLandingSession,
  clearPostLoginLandingSession,
  POST_LOGIN_LANDING_DISMISS_EVENT,
  POST_LOGIN_LANDING_SHOW_EVENT,
  WORKSPACE_START_COLLAPSE_SIDEBAR_EVENT,
} from '@/lib/postLoginLanding';
import {
  markWorkspacePanelLayoutUserCustomized,
  projectShouldExpandReportPanel,
  readWorkspacePanelLayoutUserCustomized,
} from '@/lib/workspaceReportPanelLayout';
import { streamingConclusionForChat } from '@/lib/streamingConclusionForChat';
import { AUTO_PROJECT_TITLE_MAX_LEN } from '@/lib/deriveAutoProjectTitle';
import { tryArchiveProfessionalReportToKnowledge } from '@/lib/knowledgeArchive';
import type { MarketingLaunchState } from '@/components/MarketingHomeComposer';

function isMarketingLaunchPayload(v: unknown): v is MarketingLaunchState {
  if (!v || typeof v !== 'object') return false;
  const o = v as Record<string, unknown>;
  if (
    typeof o.projectName !== 'string' ||
    typeof o.input !== 'string' ||
    typeof o.existingProjectId !== 'string'
  ) {
    return false;
  }
  if (!Array.isArray(o.attachments)) return false;
  for (const item of o.attachments) {
    if (!item || typeof item !== 'object') return false;
    const a = item as Record<string, unknown>;
    if (
      typeof a.filename !== 'string' ||
      typeof a.content_type !== 'string' ||
      typeof a.size !== 'number'
    ) {
      return false;
    }
  }
  if (o.modelId !== undefined && typeof o.modelId !== 'string') return false;
  return true;
}

type WorkspacePanelLayoutMode = 'split' | 'chat' | 'report';

const Index = () => {
  const navigate = useNavigate();
  const location = useLocation();
  const { openMobileSidebar, closeMobileSidebar } = useOutletContext<WorkspaceOutletContext>();
  const [devModeOpen, setDevModeOpen] = useState(false);
  const [showAuthLanding, setShowAuthLanding] = useState(() => readPostLoginLandingSession());
  /** After early createProject on the transition page, stay on landing until first analyze completes. */
  const [keepLandingAfterCreate, setKeepLandingAfterCreate] = useState(false);
  const [panelLayoutMode, setPanelLayoutMode] = useState<WorkspacePanelLayoutMode>('chat');
  const chatPanelRef = useRef<ImperativePanelHandle>(null);
  const reportPanelRef = useRef<ImperativePanelHandle>(null);
  const lastExpandLayoutKeyRef = useRef<string>('');
  const resizeDragWasActiveRef = useRef(false);
  const prevAnalyzingForPanelCollapseRef = useRef<boolean | undefined>(undefined);
  const prevWorkspaceTabsLenRef = useRef(0);
  
  const {
    projects,
    currentProject,
    currentProjectId,
    createProject,
    selectProject,
    updateProjectBlocks,
    appendToConversation,
    addAnalysisResult,
    setActiveResultId,
    removeAnalysisResult,
    updateAnalysisResultTitle,
    reloadProjects,
    reloadProjectMessages,
    updateProjectTitle,
    isLoading: projectsLoading,
    setAssistantKnowledgeArchive,
  } = useWorkspaceProjects();

  const { language, t } = useLanguage();
  const { clearState, updateState, getAbortController } = useStreamingStateContext();

  const resetForProject = useCallback((projectId: string) => clearState(projectId), [clearState]);

  const isLocallyStreaming = useCallback(
    (projectId: string) => getAbortController(projectId) !== null,
    [getAbortController],
  );

  const { cancelRestore, stopPolling: stopProgressRestorePolling } = useAnalysisProgressRestore(
    projects.map((p) => p.id),
    updateState,
    reloadProjects,
    reloadProjectMessages,
    isLocallyStreaming,
  );

  const { persistProjectAnalysis, resetPersistence } = useConversationPersistence({
    currentProjectId,
    updateProjectBlocks,
    appendToConversation: (projectId, msgs) => appendToConversation(projectId, msgs),
    addAnalysisResult,
    resetForProject,
  });
  const persistProjectAnalysisRef = useRef(persistProjectAnalysis);
  persistProjectAnalysisRef.current = persistProjectAnalysis;

  useEffect(() => {
    const onDismissLanding = () => {
      setShowAuthLanding(false);
      setKeepLandingAfterCreate(false);
      resetPersistence();
    };
    const onShowLanding = () => setShowAuthLanding(true);
    window.addEventListener(POST_LOGIN_LANDING_DISMISS_EVENT, onDismissLanding);
    window.addEventListener(POST_LOGIN_LANDING_SHOW_EVENT, onShowLanding);
    return () => {
      window.removeEventListener(POST_LOGIN_LANDING_DISMISS_EVENT, onDismissLanding);
      window.removeEventListener(POST_LOGIN_LANDING_SHOW_EVENT, onShowLanding);
    };
  }, [resetPersistence]);

  const {
    blocks,
    isAnalyzing,
    currentReasoning,
    decisions,
    resolvedDecisions,
    understanding,
    parameterRequests,
    parameterRequestDetail,
    isSubmittingParameters,
    hitlParametersSubmitted,
    hitlAwaiting,
    hitlProgressRequestId,
    submittedParameters,
    userInput,
    inputTimestamp,
    thinkingStartTime,
    taskSummary,
    taskPlan,
    taskPlansSubagent,
    conclusion,
    nextActions,
    sseEventLogs,
    timeline,
    analysisMode,
    workspaceTabs,
    toolCallCount,
    sandboxRunCount,
    resultStartTime,
    contextUsage,
    currentRequestId,
    attachments,
    statsMeta,
    analyzeInput,
    handleDecision,
    handleParameterSubmit,
    abort,
    clearSSELogs,
    removeState,
  } = useStreamingAnalysisMulti({
    currentProjectId,
    uiLanguage: language,
    appendToConversation: (projectId, msgs) => appendToConversation(projectId, msgs),
    resetForProject,
    stopProgressRestorePolling,
    onProjectAnalysisComplete: (projectId, state) => {
      persistProjectAnalysisRef.current(
        projectId,
        { ...state, requestId: state.completedRequestId || state.currentRequestId },
        { skipAppendAndReset: true },
      );
      // Idempotent: the streaming hook also calls this synchronously before
      // clearing the abort handle so restore polling cannot race ahead of the
      // post-stream quiet window.
      stopProgressRestorePolling(projectId);
      void tryArchiveProfessionalReportToKnowledge({
        language,
        projectId,
        projectTitle: projects.find((p) => p.id === projectId)?.title,
        state,
        onArchivingPhase: (phase, mid) => {
          if (phase === 'start') {
            setAssistantKnowledgeArchive(projectId, mid, {
              pending: true,
              filename: '',
              displayPath: '',
              reportLabel: '',
            });
          } else {
            setAssistantKnowledgeArchive(projectId, mid, null);
          }
        },
        onSuccess: (info) => {
          const notice = {
            pending: false as const,
            filename: info.filename,
            displayPath: info.displayPath,
            reportLabel: info.reportLabel,
          };
          setAssistantKnowledgeArchive(projectId, info.requestId, notice);
          void messagesApi.patchKnowledgeArchive(projectId, info.requestId, notice).catch((e: unknown) => {
            logger.warn('knowledge_archive_persist_failed', { projectId, error: String(e) });
          });
        },
      });
    },
  });

  // Task list panel: thought duration when analysis ends (full turn, not task_plan-gated)
  const [thoughtDurationSeconds, setThoughtDurationSeconds] = useState<number | undefined>();
  const prevAnalyzingRef = useRef<boolean | undefined>(undefined);
  useEffect(() => {
    if (!currentProjectId) {
      setThoughtDurationSeconds(undefined);
      prevAnalyzingRef.current = undefined;
      return;
    }
    if (prevAnalyzingRef.current === true && !isAnalyzing && thinkingStartTime) {
      setThoughtDurationSeconds(Math.round((Date.now() - thinkingStartTime.getTime()) / 1000));
    }
    prevAnalyzingRef.current = isAnalyzing;
    if (isAnalyzing) {
      setThoughtDurationSeconds(undefined);
    }
  }, [currentProjectId, isAnalyzing, thinkingStartTime]);

  // Handle submit - start analysis for current project
  const handleSubmit = useCallback(
    async (input: string, attachments: UploadedAttachment[] = [], modelId?: string) => {
      console.log('[INDEX] handleSubmit called', {
        hasCurrentProjectId: Boolean(currentProjectId),
        inputLength: input.trim().length,
        attachments: attachments.length,
      });
      let targetProjectId = currentProjectId;
      if (!targetProjectId) {
        console.warn('[INDEX] no currentProjectId, creating one');
        const created = await createProject(t.sidebar.newConversation);
        if (!created?.id) {
          toast.error(t.projects.createFailed);
          console.error('[INDEX] createProject failed, submit aborted');
          return;
        }
        targetProjectId = created.id;
        console.log('[INDEX] project created for submit', { projectId: targetProjectId });
      }
      console.log('[INDEX] calling analyzeInput', { projectId: targetProjectId });
      analyzeInput(targetProjectId, input, true, language, attachments, modelId);
    },
    [currentProjectId, analyzeInput, language, createProject, t.sidebar.newConversation, t.projects.createFailed]
  );

  /**
   * Create a project as soon as the user confirms the title on the transition page so
   * POST /uploads can bind to u_<uid>/p_<projectId>/ before the first message.
   */
  const ensureProjectForLanding = useCallback(
    async (title: string): Promise<string | null> => {
      setKeepLandingAfterCreate(true);
      const created = await createProject(title);
      if (!created) {
        setKeepLandingAfterCreate(false);
        return null;
      }
      flushSync(() => selectProject(created.id));
      return created.id;
    },
    [createProject, selectProject],
  );

  const handleWorkspaceStart = useCallback(
    async (
      projectName: string,
      input: string,
      attachments: UploadedAttachment[],
      modelId?: string,
      opts?: { existingProjectId?: string },
    ): Promise<boolean> => {
      resetPersistence();
      const existingId = opts?.existingProjectId;
      if (existingId) {
        clearPostLoginLandingSession();
        flushSync(() => {
          selectProject(existingId);
          setShowAuthLanding(false);
          setKeepLandingAfterCreate(false);
        });
        const nextTitle = projectName.trim().slice(0, AUTO_PROJECT_TITLE_MAX_LEN);
        if (nextTitle) {
          const current = projects.find((p) => p.id === existingId)?.title?.trim() ?? '';
          if (current !== nextTitle) {
            await updateProjectTitle(existingId, nextTitle);
          }
        }
        analyzeInput(existingId, input, true, language, attachments, modelId);
        if (typeof window !== 'undefined') {
          window.dispatchEvent(new CustomEvent(WORKSPACE_START_COLLAPSE_SIDEBAR_EVENT));
        }
        return true;
      }
      const created = await createProject(projectName);
      if (!created) return false;
      clearPostLoginLandingSession();
      flushSync(() => {
        selectProject(created.id);
        setShowAuthLanding(false);
        setKeepLandingAfterCreate(false);
      });
      analyzeInput(created.id, input, true, language, attachments, modelId);
      if (typeof window !== 'undefined') {
        window.dispatchEvent(new CustomEvent(WORKSPACE_START_COLLAPSE_SIDEBAR_EVENT));
      }
      return true;
    },
    [resetPersistence, createProject, selectProject, analyzeInput, language, projects, updateProjectTitle],
  );

  useEffect(() => {
    const raw = (location.state as { marketingLaunch?: unknown } | null)?.marketingLaunch;
    if (!isMarketingLaunchPayload(raw)) return;
    navigate(`${location.pathname}${location.search}`, { replace: true, state: {} });
    void handleWorkspaceStart(raw.projectName, raw.input, raw.attachments, raw.modelId, {
      existingProjectId: raw.existingProjectId,
    });
  }, [location.state, location.pathname, location.search, navigate, handleWorkspaceStart]);

  // Handle tab selection in workspace
  const handleSelectResult = useCallback((resultId: string) => {
    if (currentProjectId) {
      setActiveResultId(currentProjectId, resultId);
    }
  }, [currentProjectId, setActiveResultId]);

  // Handle removing a result tab
  const handleRemoveResult = useCallback((resultId: string) => {
    if (currentProjectId) {
      removeAnalysisResult(currentProjectId, resultId);
    }
  }, [currentProjectId, removeAnalysisResult]);

  // Handle renaming a result tab
  const handleRenameResult = useCallback((resultId: string, newTitle: string) => {
    if (currentProjectId) {
      updateAnalysisResultTitle(currentProjectId, resultId, newTitle);
    }
  }, [currentProjectId, updateAnalysisResultTitle]);

  const handleAbort = useCallback(async () => {
    if (!currentProjectId) return;
    const controller = getAbortController(currentProjectId);
    if (controller) {
      abort();
      return;
    }
    cancelRestore(currentProjectId);
    try {
      await projectsApi.cancelAnalysisProgress(currentProjectId);
    } catch {
      // best-effort
    }
    updateState(currentProjectId, (p) => ({
      ...createEmptyStreamingState(),
      sseEventLogs: p.sseEventLogs,
      conclusion: t.streaming.analysisCancelled,
    }));
  }, [currentProjectId, getAbortController, abort, cancelRestore, updateState, t]);

  // Get current blocks for navbar
  const currentBlocks = currentProject.blocks.length > 0 ? currentProject.blocks : blocks;

  /** Show SSE `conclusion` in left chat only when the canonical answer is not the report body.
   *  Deep research emits `conclusion` before `blocks`; also gate on task_plan / tabs / timeline. */
  const conclusionForChat = useMemo(
    () =>
      streamingConclusionForChat(conclusion, {
        blocksCount: blocks.length,
        taskPlan,
        taskPlansSubagent,
        workspaceTabsCount: workspaceTabs?.length ?? 0,
        timeline,
        taskKind: statsMeta?.taskKind,
      }),
    [
      conclusion,
      blocks.length,
      taskPlan,
      taskPlansSubagent,
      workspaceTabs,
      timeline,
      statsMeta?.taskKind,
    ],
  );

  const liveExpandHint = useMemo(
    () => ({
      taskKind: statsMeta?.taskKind,
      blocksCount: blocks.length,
      workspaceTabsCount: workspaceTabs?.length ?? 0,
    }),
    [statsMeta?.taskKind, blocks.length, workspaceTabs],
  );

  const expandLayoutKey = useMemo(() => {
    if (!currentProjectId || !currentProject) return '';
    return `${currentProjectId}:${projectShouldExpandReportPanel(currentProject, liveExpandHint)}`;
  }, [currentProjectId, currentProject, liveExpandHint]);

  useEffect(() => {
    lastExpandLayoutKeyRef.current = '';
  }, [currentProjectId]);

  useEffect(() => {
    prevAnalyzingForPanelCollapseRef.current = undefined;
  }, [currentProjectId]);

  useEffect(() => {
    prevWorkspaceTabsLenRef.current = 0;
  }, [currentProjectId, currentRequestId]);

  /** Collapse/expand report from persisted project data (incl. refresh). Per-project key avoids skipping after navigation. */
  useEffect(() => {
    if (!currentProjectId || projectsLoading || !expandLayoutKey) return;
    if (lastExpandLayoutKeyRef.current === expandLayoutKey) return;
    lastExpandLayoutKeyRef.current = expandLayoutKey;

    const shouldExpand = projectShouldExpandReportPanel(currentProject, liveExpandHint);
    if (shouldExpand) {
      setPanelLayoutMode('split');
      requestAnimationFrame(() => {
        const report = reportPanelRef.current;
        const chat = chatPanelRef.current;
        if (!report?.isCollapsed?.()) return;
        chat?.expand(15);
        report.expand(15);
        requestAnimationFrame(() => {
          chatPanelRef.current?.resize(30);
          reportPanelRef.current?.resize(70);
        });
      });
    } else {
      // Do not override split/autoSave after the user adjusted layout (drag, cycle, open workspace).
      if (readWorkspacePanelLayoutUserCustomized(currentProjectId)) {
        lastExpandLayoutKeyRef.current = expandLayoutKey;
        return;
      }
      setPanelLayoutMode('chat');
      requestAnimationFrame(() => {
        reportPanelRef.current?.collapse();
      });
    }
  }, [currentProjectId, projectsLoading, expandLayoutKey, currentProject, liveExpandHint]);

  /** New analysis turn: default to chat-only unless the user dragged the split for this project,
   *  or the report column is already visible (split / fullscreen report) — do not yank it on follow-up. */
  useEffect(() => {
    if (!currentProjectId) {
      prevAnalyzingForPanelCollapseRef.current = undefined;
      return;
    }
    const was = prevAnalyzingForPanelCollapseRef.current;
    if (was === undefined) {
      prevAnalyzingForPanelCollapseRef.current = isAnalyzing;
      return;
    }
    prevAnalyzingForPanelCollapseRef.current = isAnalyzing;
    if (isAnalyzing && !was) {
      if (readWorkspacePanelLayoutUserCustomized(currentProjectId)) return;
      if (panelLayoutMode === 'split' || panelLayoutMode === 'report') return;
      setPanelLayoutMode('chat');
      requestAnimationFrame(() => {
        reportPanelRef.current?.collapse();
      });
    }
  }, [isAnalyzing, currentProjectId, panelLayoutMode]);

  /** First workspace tab(s) in this stream: expand report if still collapsed. */
  useEffect(() => {
    const len = workspaceTabs?.length ?? 0;
    if (len > 0 && prevWorkspaceTabsLenRef.current === 0 && isAnalyzing) {
      requestAnimationFrame(() => {
        const report = reportPanelRef.current;
        if (!report?.isCollapsed?.()) return;
        setPanelLayoutMode('split');
        chatPanelRef.current?.expand(15);
        report.expand(15);
        requestAnimationFrame(() => {
          chatPanelRef.current?.resize(30);
          reportPanelRef.current?.resize(70);
        });
      });
    }
    prevWorkspaceTabsLenRef.current = len;
  }, [workspaceTabs, isAnalyzing]);

  const openReportPanelSplit = useCallback(() => {
    if (currentProjectId) markWorkspacePanelLayoutUserCustomized(currentProjectId);
    setPanelLayoutMode('split');
    requestAnimationFrame(() => {
      const report = reportPanelRef.current;
      const chat = chatPanelRef.current;
      if (!report || !chat) return;
      if (report.isCollapsed()) {
        chat.expand(15);
        report.expand(15);
        requestAnimationFrame(() => {
          chatPanelRef.current?.resize(30);
          reportPanelRef.current?.resize(70);
        });
      }
    });
  }, [currentProjectId]);

  const handleResizeHandleDragging = useCallback(
    (dragging: boolean) => {
      if (dragging) {
        resizeDragWasActiveRef.current = true;
      } else if (resizeDragWasActiveRef.current && currentProjectId) {
        resizeDragWasActiveRef.current = false;
        markWorkspacePanelLayoutUserCustomized(currentProjectId);
      }
    },
    [currentProjectId],
  );

  const toggleReportPanelMaximize = useCallback(() => {
    if (currentProjectId) markWorkspacePanelLayoutUserCustomized(currentProjectId);
    const chat = chatPanelRef.current;
    const report = reportPanelRef.current;
    if (!chat || !report) return;

    if (panelLayoutMode === 'report') {
      setPanelLayoutMode('split');
      requestAnimationFrame(() => {
        chatPanelRef.current?.expand(15);
        reportPanelRef.current?.expand(15);
        requestAnimationFrame(() => {
          chatPanelRef.current?.resize(30);
          reportPanelRef.current?.resize(70);
        });
      });
    } else {
      setPanelLayoutMode('report');
      requestAnimationFrame(() => {
        reportPanelRef.current?.expand(15);
        requestAnimationFrame(() => {
          chatPanelRef.current?.collapse();
        });
      });
    }
  }, [panelLayoutMode, currentProjectId]);

  const cycleWorkspacePanelLayout = useCallback(() => {
    if (currentProjectId) markWorkspacePanelLayoutUserCustomized(currentProjectId);
    const chat = chatPanelRef.current;
    const report = reportPanelRef.current;
    if (!chat || !report) return;

    setPanelLayoutMode((prev) => {
      const next: WorkspacePanelLayoutMode =
        prev === 'split' ? 'chat' : prev === 'chat' ? 'report' : 'split';

      requestAnimationFrame(() => {
        const c = chatPanelRef.current;
        const r = reportPanelRef.current;
        if (!c || !r) return;
        if (next === 'chat') {
          r.collapse();
        } else if (next === 'report') {
          r.expand(15);
          requestAnimationFrame(() => {
            chatPanelRef.current?.collapse();
          });
        } else {
          c.expand(15);
          r.expand(15);
          requestAnimationFrame(() => {
            chatPanelRef.current?.resize(30);
            reportPanelRef.current?.resize(70);
          });
        }
      });

      return next;
    });
  }, [currentProjectId]);

  const panelLayoutTooltip =
    panelLayoutMode === 'split'
      ? t.workspace.panelLayoutNextChat
      : panelLayoutMode === 'chat'
        ? t.workspace.panelLayoutNextReport
        : t.workspace.panelLayoutNextSplit;

  const PanelLayoutIcon =
    panelLayoutMode === 'split' ? MessageSquare : panelLayoutMode === 'chat' ? FileText : Columns2;

  const showWorkspaceStart =
    !projectsLoading &&
    (showAuthLanding || projects.length === 0 || keepLandingAfterCreate);

  if (showWorkspaceStart) {
    return (
      <PostLoginWorkspaceStart
        onStart={handleWorkspaceStart}
        ensureProjectForLanding={ensureProjectForLanding}
        // Never use global streaming `isAnalyzing` here: user may open this flow while another project is still
        // analyzing; the transition composer must stay usable. Local `submitting` covers project creation.
        isAnalyzing={false}
        onAbort={handleAbort}
      />
    );
  }

  if (projectsLoading) {
    return (
      <div className="flex min-h-[50vh] w-full items-center justify-center bg-background">
        <div className="text-muted-foreground">{t.common.loading}</div>
      </div>
    );
  }

  return (
    <div className="flex min-h-0 min-w-0 flex-1 flex-col overflow-hidden bg-sidebar">
      <TopNavbar onMobileSidebarOpen={openMobileSidebar} blocksCount={currentBlocks.length} />

      <div className="flex min-h-0 flex-1 flex-col overflow-hidden">
      {/* Desktop: Resizable Panels — main is flex + overflow-hidden so chat/report scroll only inside their panes */}
      <div className="hidden min-h-0 md:flex md:flex-1 md:overflow-hidden">
        <PanelGroup
          direction="horizontal"
          autoSaveId={
            currentProjectId
              ? `secmanus-workspace-chat-report-${currentProjectId}`
              : 'secmanus-workspace-chat-report-none'
          }
          className="h-full min-h-0 w-full"
        >
          {/* Left Panel - Command Center (no header) */}
          <Panel
            ref={chatPanelRef}
            defaultSize={30}
            minSize={15}
            collapsedSize={0}
            collapsible
            className="flex min-h-0 min-w-0 flex-col"
          >
            <div className="flex h-full min-h-0 min-w-0 flex-col overflow-hidden">
            <CommandCenter 
              onSubmit={handleSubmit}
              isAnalyzing={isAnalyzing}
              currentReasoning={currentReasoning}
              timeline={timeline}
              onAbort={handleAbort}
              decisions={decisions}
              resolvedDecisions={resolvedDecisions}
              onDecision={handleDecision}
              userInput={userInput}
              inputTimestamp={inputTimestamp}
              thinkingStartTime={thinkingStartTime}
              conversationHistory={currentProject.messages}
              understanding={understanding}
              parameterRequests={parameterRequests}
              parameterRequestDetail={parameterRequestDetail}
              onParameterSubmit={handleParameterSubmit}
              isSubmittingParameters={isSubmittingParameters}
              hitlParametersSubmitted={hitlParametersSubmitted}
              hitlAwaiting={hitlAwaiting}
              taskSummary={taskSummary}
              conclusionText={conclusionForChat}
              nextActions={nextActions}
              thoughtDurationSeconds={thoughtDurationSeconds}
              uploadSessionId={currentProjectId}
              hideHeader
              taskPlan={taskPlan}
              taskPlansSubagent={taskPlansSubagent}
              submittedParameters={submittedParameters}
              omitMessagesWithRequestId={hitlProgressRequestId ?? null}
              contextUsage={contextUsage}
              onOpenReportPanel={openReportPanelSplit}
              chatColumnTestId="chat-column"
            />
            </div>
          </Panel>

          <PanelResizeHandle
            hitAreaMargins={{ fine: 6, coarse: 10 }}
            onDragging={handleResizeHandleDragging}
            className="group relative z-10 flex w-px cursor-col-resize items-center justify-center bg-border/70 hover:bg-primary/35"
          >
            <Tooltip>
              <TooltipTrigger asChild>
                <Button
                  type="button"
                  variant="secondary"
                  size="icon"
                  className="pointer-events-none absolute left-1/2 top-1/2 z-20 h-8 w-8 -translate-x-1/2 -translate-y-1/2 rounded-full border bg-background shadow-md opacity-0 transition-opacity group-hover:pointer-events-auto group-hover:opacity-100"
                  aria-label={t.workspace.panelLayoutAria}
                  onPointerDown={(e) => e.stopPropagation()}
                  onClick={(e) => {
                    e.preventDefault();
                    e.stopPropagation();
                    cycleWorkspacePanelLayout();
                  }}
                >
                  <PanelLayoutIcon className="h-4 w-4" aria-hidden />
                </Button>
              </TooltipTrigger>
              <TooltipContent side="bottom" className="max-w-xs text-xs">
                {panelLayoutTooltip}
              </TooltipContent>
            </Tooltip>
          </PanelResizeHandle>

          {/* Right Panel - Live Workspace with rounded corners */}
          <Panel
            ref={reportPanelRef}
            defaultSize={70}
            minSize={15}
            collapsedSize={0}
            collapsible
            className="flex min-h-0 min-w-0 flex-col py-2 pr-2"
          >
            <div className="flex h-full min-h-0 flex-col overflow-hidden rounded-xl border border-border bg-background shadow-sm">
              <LiveWorkspace
                analysisResults={currentProject.analysisResults}
                activeResultId={currentProject.activeResultId}
                onSelectResult={handleSelectResult}
                onRemoveResult={handleRemoveResult}
                onRenameResult={handleRenameResult}
                reportPanelMaximized={panelLayoutMode === 'report'}
                onToggleReportPanelMaximize={toggleReportPanelMaximize}
                liveResult={{
                  isActive: isAnalyzing,
                  blocks,
                  workspaceTabs: workspaceTabs,
                  toolCallCount: toolCallCount,
                  sandboxRunCount: sandboxRunCount,
                  resultStartTime: resultStartTime,
                  userInput,
                  hasTaskPlan: !!taskPlan,
                  currentRequestId: currentRequestId || undefined,
                  hasAttachments: (attachments?.length ?? 0) > 0,
                  statsMeta,
                }}
              />
            </div>
          </Panel>
        </PanelGroup>
      </div>

      {/* Mobile: Full width Command Center */}
      <div className="flex min-h-0 w-full min-w-0 flex-1 md:hidden">
        <CommandCenter 
          onSubmit={handleSubmit}
          isAnalyzing={isAnalyzing}
          currentReasoning={currentReasoning}
          timeline={timeline}
          onAbort={handleAbort}
          decisions={decisions}
          resolvedDecisions={resolvedDecisions}
          onDecision={handleDecision}
          userInput={userInput}
          inputTimestamp={inputTimestamp}
          thinkingStartTime={thinkingStartTime}
          onMenuClick={openMobileSidebar}
          conversationHistory={currentProject.messages}
          understanding={understanding}
          parameterRequests={parameterRequests}
          parameterRequestDetail={parameterRequestDetail}
          onParameterSubmit={handleParameterSubmit}
          isSubmittingParameters={isSubmittingParameters}
          hitlParametersSubmitted={hitlParametersSubmitted}
          hitlAwaiting={hitlAwaiting}
          taskSummary={taskSummary}
          conclusionText={conclusionForChat}
          nextActions={nextActions}
          thoughtDurationSeconds={thoughtDurationSeconds}
          uploadSessionId={currentProjectId}
          taskPlan={taskPlan}
          taskPlansSubagent={taskPlansSubagent}
          submittedParameters={submittedParameters}
          omitMessagesWithRequestId={hitlProgressRequestId ?? null}
          contextUsage={contextUsage}
        />
      </div>
      </div>

      {/* Mobile: Workspace as overlay when has content */}
      {(currentProject.analysisResults.length > 0 || isAnalyzing) && (
        <div className="fixed inset-0 md:hidden bg-background z-30 overflow-hidden">
          <LiveWorkspace
            analysisResults={currentProject.analysisResults}
            activeResultId={currentProject.activeResultId}
            onSelectResult={handleSelectResult}
            onRemoveResult={handleRemoveResult}
            onRenameResult={handleRenameResult}
            liveResult={{
              isActive: isAnalyzing,
              blocks,
              workspaceTabs,
              toolCallCount,
              sandboxRunCount,
              resultStartTime,
              userInput,
              hasTaskPlan: !!taskPlan,
              currentRequestId: currentRequestId || undefined,
              hasAttachments: (attachments?.length ?? 0) > 0,
              statsMeta,
            }}
          />
        </div>
      )}

      {/* Developer Mode Panel: only in dev build (Vite import.meta.env.DEV) */}
      {import.meta.env.DEV && (
        <DevModePanel
          isOpen={devModeOpen}
          onToggle={() => setDevModeOpen(!devModeOpen)}
          sseEventLogs={sseEventLogs}
          onClearLogs={clearSSELogs}
          analysisMode={analysisMode}
          understanding={understanding}
        />
      )}
    </div>
  );
};

export default Index;
