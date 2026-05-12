import { useRef, useEffect, useCallback, useMemo, useState } from 'react';
import { Link as RouterLink } from 'react-router-dom';
import { isHitlResumePlaceholderUserContent } from '@/lib/formatUserMessageDisplay';
import { extractHitlUiStateFromTimeline } from '@/lib/hitlRestoreFromTimeline';
import { readHitlSubmittedParams } from '@/lib/hitlSubmittedParamsStorage';
import { Shield, LogOut, Globe, LayoutDashboard, UserCircle, CreditCard, BarChart3, Loader2 } from 'lucide-react';
import { Button } from '@/components/ui/button';
import type {
  ParameterRequest,
  InputUnderstanding,
  NextAction,
  AnalysisTimelineEntry,
  TaskPlan,
  ContextUsageState,
} from '@/types/analysis';
import { AnalysisTurnPanel, UserDecisionRequest, ChatMessage } from './reasoning';
import { useAuth } from '@/hooks/useAuth';
import { useLanguage } from '@/contexts/LanguageContext';
import { languages, Language } from '@/i18n';
import { Avatar, AvatarFallback, AvatarImage } from '@/components/ui/avatar';
import { AnalysisInputComposer, type UploadedAttachment } from '@/components/AnalysisInputComposer';
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuTrigger,
  DropdownMenuSeparator,
} from '@/components/ui/dropdown-menu';
import { ConversationMessage } from '@/types/project';

export type { UploadedAttachment } from '@/components/AnalysisInputComposer';

interface CommandCenterProps {
  onSubmit: (input: string, attachments?: UploadedAttachment[], modelId?: string) => void;
  isAnalyzing: boolean;
  currentReasoning?: string;
  /** Canonical SSE timeline (schemaVersion 1) for reasoning + tools + sub-agent UI */
  timeline?: AnalysisTimelineEntry[];
  onAbort?: () => void;
  decisions?: UserDecisionRequest[];
  resolvedDecisions?: Record<string, string[]>;
  onDecision?: (requestId: string, selectedOptions: string[]) => void;
  userInput?: string;
  inputTimestamp?: Date;
  thinkingStartTime?: Date;
  onMenuClick?: () => void;
  conversationHistory?: ConversationMessage[];
  understanding?: InputUnderstanding | null;
  parameterRequests?: ParameterRequest[];
  parameterRequestDetail?: string;
  onParameterSubmit?: (parameters: Record<string, string>) => void;
  isSubmittingParameters?: boolean;
  hitlParametersSubmitted?: boolean;
  /** LangGraph HITL pause — composer should not stay in "executing" spin. */
  hitlAwaiting?: boolean;
  taskSummary?: string;
  /** SSE final answer; shown when not duplicated in workspace (parent filters). */
  conclusionText?: string;
  nextActions?: NextAction[];
  hideHeader?: boolean;
  /** Thought duration (seconds) for Thinking chrome when replaying history. */
  thoughtDurationSeconds?: number;
  /** Binds uploads to this project/session (POST /uploads session_id). */
  uploadSessionId?: string | null;
  /** Main-agent task plan for ``TimelineActivity`` (from streaming state or replay). */
  taskPlan?: TaskPlan | null;
  taskPlansSubagent?: Record<string, TaskPlan | null>;
  /**
   * Hide user/assistant rows with this ``requestId`` from history (live HITL panel owns the turn).
   */
  omitMessagesWithRequestId?: string | null;
  /** HITL form values for read-only replay after refresh. */
  submittedParameters?: Record<string, string>;
  /** Realtime context-usage aggregate for the indicator in the composer bottom bar. */
  contextUsage?: ContextUsageState;
  /** Desktop: expand the report panel (split view). */
  onOpenReportPanel?: () => void;
  /** Optional test id for the max-width chat column (desktop only; avoid duplicate in mobile DOM). */
  chatColumnTestId?: string;
}

export function CommandCenter({ 
  onSubmit, 
  isAnalyzing, 
  currentReasoning,
  timeline = [],
  onAbort,
  decisions = [],
  resolvedDecisions = {},
  onDecision,
  userInput: propsUserInput,
  inputTimestamp,
  thinkingStartTime,
  onMenuClick,
  conversationHistory = [],
  understanding,
  parameterRequests = [],
  parameterRequestDetail,
  onParameterSubmit,
  isSubmittingParameters = false,
  hitlParametersSubmitted = false,
  hitlAwaiting = false,
  taskSummary,
  conclusionText,
  nextActions = [],
  hideHeader = false,
  thoughtDurationSeconds,
  uploadSessionId = null,
  taskPlan = null,
  taskPlansSubagent = {},
  omitMessagesWithRequestId = null,
  submittedParameters = {},
  contextUsage,
  onOpenReportPanel,
  chatColumnTestId,
}: CommandCenterProps) {
  const scrollAreaRef = useRef<HTMLDivElement>(null);
  const isUserScrollingRef = useRef(false);
  const scrollTimeoutRef = useRef<NodeJS.Timeout | null>(null);
  const { user, signOut } = useAuth();
  const { language, setLanguage, t } = useLanguage();
  const [fallbackHitlRequests, setFallbackHitlRequests] = useState<ParameterRequest[]>([]);
  const [fallbackHitlDetail, setFallbackHitlDetail] = useState<string>('');
  const [fallbackHitlAwaiting, setFallbackHitlAwaiting] = useState(false);

  // Check if user is near bottom of scroll area
  const isNearBottom = useCallback(() => {
    if (!scrollAreaRef.current) return true;
    const { scrollTop, scrollHeight, clientHeight } = scrollAreaRef.current;
    // Consider "near bottom" if within 100px of the bottom
    return scrollHeight - scrollTop - clientHeight < 100;
  }, []);

  // Handle scroll events to detect user manual scrolling
  const handleScroll = useCallback(() => {
    if (!scrollAreaRef.current) return;
    
    // Clear existing timeout
    if (scrollTimeoutRef.current) {
      clearTimeout(scrollTimeoutRef.current);
    }
    
    // Check if user scrolled away from bottom
    if (!isNearBottom()) {
      isUserScrollingRef.current = true;
    } else {
      // If near bottom, reset the flag after a short delay
      scrollTimeoutRef.current = setTimeout(() => {
        isUserScrollingRef.current = false;
      }, 150);
    }
  }, [isNearBottom]);

  // Attach scroll listener
  useEffect(() => {
    const scrollEl = scrollAreaRef.current;
    if (scrollEl) {
      scrollEl.addEventListener('scroll', handleScroll, { passive: true });
      return () => scrollEl.removeEventListener('scroll', handleScroll);
    }
  }, [handleScroll]);

  // Reset scroll when switching projects — avoids inheriting scrollTop from a longer thread.
  useEffect(() => {
    const el = scrollAreaRef.current;
    if (!el) return;
    el.scrollTop = 0;
    isUserScrollingRef.current = false;
  }, [uploadSessionId]);

  const filteredConversationHistory = useMemo(() => {
    let list = conversationHistory;
    if (omitMessagesWithRequestId?.trim()) {
      const rid = omitMessagesWithRequestId.trim();
      list = list.filter((m) => m.requestId !== rid);
    }
    return list.filter(
      (m) => !(m.type === 'user' && isHitlResumePlaceholderUserContent(m.content)),
    );
  }, [conversationHistory, omitMessagesWithRequestId]);

  const timelineScrollKey = useMemo(() => {
    const last = timeline[timeline.length - 1];
    const seq =
      last && typeof (last as { seq?: unknown }).seq === 'number'
        ? (last as { seq: number }).seq
        : 0;
    return `${timeline.length}-${seq}`;
  }, [timeline]);

  useEffect(() => {
    const handler = (evt: Event) => {
      const ce = evt as CustomEvent<{
        parameterRequests?: ParameterRequest[];
        detail?: string;
      }>;
      const reqs = Array.isArray(ce.detail?.parameterRequests)
        ? ce.detail.parameterRequests
        : [];
      if (reqs.length === 0) return;
      setFallbackHitlRequests(reqs);
      setFallbackHitlDetail(typeof ce.detail?.detail === 'string' ? ce.detail.detail : '');
      setFallbackHitlAwaiting(true);
    };
    window.addEventListener('secmanus-hitl-parameter-request', handler as EventListener);
    return () => window.removeEventListener('secmanus-hitl-parameter-request', handler as EventListener);
  }, []);

  useEffect(() => {
    // Clear fallback state once normal chain finishes/submits.
    if (!hitlAwaiting || hitlParametersSubmitted) {
      setFallbackHitlAwaiting(false);
      setFallbackHitlRequests([]);
      setFallbackHitlDetail('');
    }
  }, [hitlAwaiting, hitlParametersSubmitted]);

  const effectiveParameterRequests =
    parameterRequests.length > 0 ? parameterRequests : fallbackHitlRequests;
  const effectiveParameterRequestDetail =
    parameterRequestDetail ?? (fallbackHitlDetail || undefined);
  const effectiveHitlAwaiting = hitlAwaiting || (fallbackHitlAwaiting && effectiveParameterRequests.length > 0);

  // Smart auto-scroll: rAF after paint so streamed content height is applied; respect user scroll-up.
  useEffect(() => {
    if (!scrollAreaRef.current || isUserScrollingRef.current) return;
    let canceled = false;
    const id = requestAnimationFrame(() => {
      requestAnimationFrame(() => {
        const el = scrollAreaRef.current;
        if (canceled || !el || isUserScrollingRef.current) return;
        el.scrollTo({ top: el.scrollHeight, behavior: 'smooth' });
      });
    });
    return () => {
      canceled = true;
      cancelAnimationFrame(id);
    };
  }, [
    filteredConversationHistory,
    currentReasoning,
    propsUserInput,
    isAnalyzing,
    taskSummary,
    nextActions,
    parameterRequests,
    timelineScrollKey,
    conclusionText,
  ]);

  // Force scroll to bottom when user sends a new message
  useEffect(() => {
    if (propsUserInput && scrollAreaRef.current) {
      isUserScrollingRef.current = false;
      scrollAreaRef.current.scrollTo({
        top: scrollAreaRef.current.scrollHeight,
        behavior: 'smooth'
      });
    }
  }, [propsUserInput]);

  const userInitial = user?.email?.charAt(0).toUpperCase() || 'U';
  const userAvatar = (user as any)?.user_metadata?.avatar_url || (user as any)?.avatar_url;

  return (
    <div className="flex h-full min-h-0 min-w-0 flex-col overflow-hidden bg-sidebar">
      {/* Header - conditionally shown */}
      {!hideHeader && (
        <div className="flex-shrink-0 flex items-center justify-between px-6 py-4 bg-sidebar">
          
            <div className="flex items-center gap-3">
              {/* Menu Button - Clickable SecManus icon */}
              <button
                onClick={onMenuClick}
                className="w-9 h-9 rounded-xl bg-primary/10 flex items-center justify-center hover:bg-primary/20 transition-colors cursor-pointer"
              >
                <Shield className="w-5 h-5 text-primary" />
              </button>
              <div>
                <h1 className="text-base font-semibold text-foreground">SecManus</h1>
                <p className="text-xs text-muted-foreground">{t.auth.subtitle}</p>
              </div>
            </div>
            
            <div className="flex items-center gap-1">
              {/* Language Switcher */}
              <DropdownMenu>
                <DropdownMenuTrigger asChild>
                  <Button variant="ghost" size="icon" className="h-9 w-9">
                    <Globe className="w-4 h-4 text-muted-foreground" />
                  </Button>
                </DropdownMenuTrigger>
                <DropdownMenuContent align="end" className="bg-popover border border-border z-50">
                  {(Object.keys(languages) as Language[]).map((lang) => (
                    <DropdownMenuItem
                      key={lang}
                      onClick={() => setLanguage(lang)}
                      className={language === lang ? "bg-accent" : ""}
                    >
                      {languages[lang].nativeName}
                    </DropdownMenuItem>
                  ))}
                </DropdownMenuContent>
              </DropdownMenu>

              {/* User Menu */}
              <DropdownMenu>
                <DropdownMenuTrigger asChild>
                  <Button variant="ghost" size="icon" className="h-9 w-9 rounded-full">
                    <Avatar className="h-8 w-8">
                      <AvatarImage src={userAvatar} />
                      <AvatarFallback className="bg-primary/10 text-primary text-sm">
                        {userInitial}
                      </AvatarFallback>
                    </Avatar>
                  </Button>
                </DropdownMenuTrigger>
                <DropdownMenuContent align="end" className="min-w-[12rem] bg-popover border border-border z-50">
                  <DropdownMenuItem className="text-muted-foreground text-xs py-1" disabled>
                    {user?.email}
                  </DropdownMenuItem>
                  <DropdownMenuSeparator />
                  <DropdownMenuItem asChild>
                    <RouterLink to="/account/overview" className="cursor-pointer">
                      <LayoutDashboard className="w-4 h-4 mr-2" />
                      {t.account.navOverview}
                    </RouterLink>
                  </DropdownMenuItem>
                  <DropdownMenuItem asChild>
                    <RouterLink to="/account/settings" className="cursor-pointer">
                      <UserCircle className="w-4 h-4 mr-2" />
                      {t.account.navSettings}
                    </RouterLink>
                  </DropdownMenuItem>
                  <DropdownMenuItem asChild>
                    <RouterLink to="/billing" className="cursor-pointer">
                      <CreditCard className="w-4 h-4 mr-2" />
                      {t.billing.navBilling}
                    </RouterLink>
                  </DropdownMenuItem>
                  <DropdownMenuItem asChild>
                    <RouterLink to="/usage" className="cursor-pointer">
                      <BarChart3 className="w-4 h-4 mr-2" />
                      {t.billing.navUsage}
                    </RouterLink>
                  </DropdownMenuItem>
                  <DropdownMenuSeparator />
                  <DropdownMenuItem onClick={signOut} className="text-destructive focus:text-destructive">
                    <LogOut className="w-4 h-4 mr-2" />
                    {t.nav.signOut}
                  </DropdownMenuItem>
                </DropdownMenuContent>
            </DropdownMenu>
          </div>
        </div>
      )}

      {/* Reasoning Panel Area — max-width column for readability on wide chat pane */}
      <div ref={scrollAreaRef} className="min-h-0 flex-1 overflow-auto p-4 scroll-smooth">
        <div
          className="mx-auto w-full max-w-3xl"
          {...(chatColumnTestId ? { 'data-testid': chatColumnTestId } : {})}
        >
        {/* Conversation history (rendered as turns to preserve order + show steps) */}
        {filteredConversationHistory.length > 0 && (
          <div className="space-y-4 mb-4">
            {(() => {
              const turns: Array<{ user?: ConversationMessage; assistant?: ConversationMessage }> = [];
              let pendingUser: ConversationMessage | undefined;

              for (const msg of filteredConversationHistory) {
                if (msg.type === 'user') {
                  pendingUser = msg;
                  continue;
                }

                // assistant
                turns.push({ user: pendingUser, assistant: msg });
                pendingUser = undefined;
              }

              if (pendingUser) turns.push({ user: pendingUser });

              return turns.map((turn, idx) => {
                const key = turn.assistant?.id || turn.user?.id || `turn-${idx}`;

                if (!turn.assistant) {
                  return (
                    <div key={key}>
                      <ChatMessage
                        type="user"
                        content={turn.user?.content || ''}
                        timestamp={turn.user?.timestamp}
                      />
                    </div>
                  );
                }

                const tl = turn.assistant.timeline ?? [];
                const hasStoredBlocks =
                  turn.assistant.blocks && turn.assistant.blocks.length > 0;
                const historyConclusion =
                  turn.assistant.content?.trim() && !hasStoredBlocks
                    ? turn.assistant.content.trim()
                    : undefined;
                // Persisted timeline is canonical; legacy reasoning duplicates the same text in ReAct UI.
                const historyReasoning = tl.length > 0 ? '' : (turn.assistant.reasoning || '');
                const histHitl = extractHitlUiStateFromTimeline(tl);
                const histRid = (turn.assistant.requestId || turn.user?.requestId || '').trim();
                const histPid = (uploadSessionId || '').trim();
                const histShouldStorage =
                  Boolean(histPid && histRid) &&
                  (histHitl.parameterRequests.length > 0 ||
                    histHitl.decisions.length > 0 ||
                    histHitl.hitlAwaiting ||
                    histHitl.hitlResumeInFlight);
                const histStored = histShouldStorage
                  ? readHitlSubmittedParams(histPid, histRid)
                  : {};
                const histSubmittedMerged = {
                  ...histStored,
                  ...histHitl.submittedParametersFromTimeline,
                };
                const histParamsSubmitted =
                  histHitl.hitlResumeInFlight ||
                  Object.keys(histSubmittedMerged).length > 0 ||
                  Object.keys(histHitl.resolvedDecisionsFromTimeline).length > 0;
                const showOpenWorkspace =
                  typeof onOpenReportPanel === 'function' &&
                  (turn.assistant.workspaceTabs?.length ?? 0) > 0;
                return (
                  <div key={key} className="space-y-4">
                    {showOpenWorkspace ? (
                      <div className="flex justify-end">
                        <Button
                          type="button"
                          variant="ghost"
                          size="sm"
                          className="h-7 text-xs"
                          onClick={() => onOpenReportPanel?.()}
                        >
                          {t.workspace.openWorkspacePanel}
                        </Button>
                      </div>
                    ) : null}
                    <AnalysisTurnPanel
                      isAnalyzing={false}
                      timeline={tl}
                      currentReasoning={historyReasoning}
                      userInput={turn.user?.content}
                      inputTimestamp={turn.user?.timestamp}
                      savedThinkingDurationSec={turn.assistant.thinkingDuration}
                      understanding={turn.assistant.understanding ?? null}
                      parameterRequests={histHitl.parameterRequests}
                      parameterRequestDetail={histHitl.parameterRequestDetail}
                      decisions={histHitl.decisions}
                      resolvedDecisions={histHitl.resolvedDecisionsFromTimeline}
                      taskSummary={turn.assistant.taskSummary}
                      conclusionText={historyConclusion}
                      nextActions={[]}
                      taskPlan={turn.assistant.taskPlan ?? null}
                      taskPlansSubagent={turn.assistant.taskPlansSubagent ?? {}}
                      hitlAwaiting={histHitl.hitlAwaiting}
                      hitlParametersSubmitted={histParamsSubmitted}
                      submittedParameters={histSubmittedMerged}
                    />
                    {turn.assistant.knowledgeArchive?.pending ? (
                      <div
                        role="status"
                        aria-live="polite"
                        className="relative mt-2 flex items-start gap-2.5 overflow-hidden px-0 py-1 text-xs leading-relaxed text-muted-foreground motion-safe:animate-pulse motion-reduce:animate-none"
                      >
                        <Loader2
                          className="mt-0.5 h-4 w-4 shrink-0 animate-spin text-muted-foreground/60 motion-reduce:animate-none"
                          aria-hidden
                        />
                        <span className="min-w-0 flex-1">{t.knowledgeBase.archivingHint}</span>
                      </div>
                    ) : turn.assistant.knowledgeArchive ? (
                      <div className="mt-2 text-xs leading-relaxed text-foreground/90">
                        <RouterLink
                          to={`/knowledge?highlight=${encodeURIComponent(turn.assistant.knowledgeArchive.filename)}`}
                          className="cursor-pointer text-foreground/90 underline decoration-transparent underline-offset-[3px] transition-[color,text-decoration-color] hover:text-foreground hover:underline hover:decoration-foreground/45 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2"
                        >
                          {t.knowledgeBase.savedLinkLabel.replace(
                            '{label}',
                            turn.assistant.knowledgeArchive.reportLabel,
                          )}
                        </RouterLink>
                      </div>
                    ) : null}
                  </div>
                );
              });
            })()}
          </div>
        )}

        {/* Current analysis: show when analyzing or has any results to display */}
        {(isAnalyzing ||
          effectiveHitlAwaiting ||
          propsUserInput ||
          effectiveParameterRequests.length > 0 ||
          taskSummary ||
          conclusionText ||
          nextActions.length > 0 ||
          understanding ||
          currentReasoning ||
          timeline.length > 0 ||
          decisions.length > 0) && (
          <div className="space-y-4">
            <AnalysisTurnPanel
              isAnalyzing={isAnalyzing}
              timeline={timeline}
              currentReasoning={currentReasoning}
              userInput={propsUserInput}
              inputTimestamp={inputTimestamp}
              thinkingStartTime={thinkingStartTime}
              savedThinkingDurationSec={thoughtDurationSeconds}
              understanding={understanding ?? null}
              parameterRequests={effectiveParameterRequests}
              parameterRequestDetail={effectiveParameterRequestDetail}
              decisions={decisions}
              resolvedDecisions={resolvedDecisions}
              taskSummary={taskSummary}
              conclusionText={conclusionText}
              nextActions={nextActions}
              taskPlan={taskPlan}
              taskPlansSubagent={taskPlansSubagent}
              hitlAwaiting={effectiveHitlAwaiting}
              hitlParametersSubmitted={hitlParametersSubmitted}
              submittedParameters={submittedParameters}
              onParameterSubmit={onParameterSubmit}
              isSubmittingParameters={isSubmittingParameters}
              onDecision={onDecision}
              onNextActionClick={onSubmit}
            />
          </div>
        )}
        
        {/* Empty state */}
        {!isAnalyzing &&
        !effectiveHitlAwaiting &&
        !propsUserInput &&
        filteredConversationHistory.length === 0 ? (
          <div className="flex flex-col items-center justify-center h-full text-muted-foreground px-6">
            <div className="w-16 h-16 rounded-2xl bg-muted/50 flex items-center justify-center mb-4">
              <Shield className="w-8 h-8 text-muted-foreground/50" />
            </div>
            <p className="text-sm font-medium text-foreground/80 mb-1">{t.command.waitingTitle}</p>
            <p className="text-xs text-center text-muted-foreground">
              {t.command.waitingDesc}
            </p>
          </div>
        ) : null}
        </div>
      </div>

      {/* Input Area - Fixed at bottom */}
      <div className="p-4 bg-sidebar">
        <div className="mx-auto w-full max-w-3xl">
        <AnalysisInputComposer
          onSubmit={onSubmit}
          // While waiting for HITL (including fallback parameter requests), the SSE stream
          // may have ended but the turn is not complete — user answers via the inline HITL
          // form. Keep the composer "busy" so send/upload stay disabled.
          isAnalyzing={isAnalyzing || effectiveHitlAwaiting}
          onAbort={onAbort}
          uploadSessionId={uploadSessionId}
          contextUsage={contextUsage}
        />
        </div>
      </div>
    </div>
  );
}
