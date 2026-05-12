'use client';

import { Fragment, memo, useEffect, useLayoutEffect, useRef, useState, type CSSProperties, type MouseEvent } from 'react';
import {
  BookOpen,
  Bot,
  Brain,
  Check,
  CheckCircle2,
  ChevronDown,
  ChevronRight,
  Circle,
  CircleDot,
  Copy,
  Cpu,
  FileCode,
  Globe,
  ListTodo,
  Loader2,
  Mail,
  Sparkles,
  Terminal,
  Wrench,
  XCircle,
  type LucideIcon,
} from 'lucide-react';
import { cn } from '@/lib/utils';
import { useLanguage } from '@/contexts/LanguageContext';
import { formatThinkingElapsed, formatThoughtDuration } from '@/lib/thinkingDurationLabel';
import { useLiveElapsedSeconds } from '@/lib/liveElapsedSeconds';
import type { ReActBlock, ReActStepBlock, ReActToolChild } from '@/lib/buildReActTimeline';
import { REASONING_STREAM_SHIMMER_CLASS } from '@/lib/reasoningStreamShimmer';
import { Tooltip, TooltipContent, TooltipProvider, TooltipTrigger } from '@/components/ui/tooltip';

type SubagentAccent = {
  Icon: LucideIcon;
  borderClass: string;
  badgeClass: string;
};

const SUBAGENT_ACCENT: Record<string, SubagentAccent> = {
  'email-security': {
    Icon: Mail,
    borderClass: 'border-amber-400/70',
    badgeClass: 'bg-amber-400/15 text-amber-600 dark:text-amber-400',
  },
  'binary-analysis': {
    Icon: Cpu,
    borderClass: 'border-blue-400/70',
    badgeClass: 'bg-blue-400/15 text-blue-600 dark:text-blue-400',
  },
  'web-security': {
    Icon: Globe,
    borderClass: 'border-emerald-400/70',
    badgeClass: 'bg-emerald-400/15 text-emerald-600 dark:text-emerald-400',
  },
  'deep-research': {
    Icon: BookOpen,
    borderClass: 'border-violet-400/70',
    badgeClass: 'bg-violet-400/15 text-violet-600 dark:text-violet-400',
  },
};

function interpolate(template: string, vars: Record<string, string>): string {
  return template.replace(/\{(\w+)\}/g, (_, key: string) => vars[key] ?? `{${key}}`);
}

export type ReActTimelineViewProps = {
  blocks: ReActBlock[];
  isStreaming?: boolean;
  /** True only when the stream ended with awaitingHuman — distinguishes HITL pause from normal completion. */
  hitlAwaiting?: boolean;
  /** Wall-clock thinking duration for this analysis turn (from persisted or live timer). */
  thinkingDurationSec?: number;
  /**
   * `subagentInline`: no tinted row backgrounds; timers + spinners only on active rows/steps.
   * Used for sub-agent timeline chunks so chrome matches the main column.
   */
  visualTone?: 'default' | 'subagentInline';
};

function TruncatedWithTooltip({
  text,
  className,
  tooltipClassName,
}: {
  text: string;
  className?: string;
  tooltipClassName?: string;
}) {
  return (
    <Tooltip>
      <TooltipTrigger asChild>
        <span className={cn('block truncate whitespace-nowrap', className)} title={text}>
          {text}
        </span>
      </TooltipTrigger>
      <TooltipContent className={cn('max-w-[70vw] break-all text-xs', tooltipClassName)}>
        {text}
      </TooltipContent>
    </Tooltip>
  );
}

function ThinkingBlockView({
  reasoning,
  answer,
  isRunning,
  showDuration,
  invokeDurationSec,
  thinkingDurationSec,
  invokeStartMs,
  invokeState,
}: {
  reasoning: string;
  answer: string;
  isRunning: boolean;
  showDuration: boolean;
  invokeDurationSec?: number;
  thinkingDurationSec?: number;
  invokeStartMs?: number;
  invokeState?: 'running' | 'done';
}) {
  const { t } = useLanguage();
  const hasReasoning = reasoning.trim().length > 0;
  const hasAnswer = answer.trim().length > 0;
  const noVisibleModelContent = !hasReasoning && !hasAnswer;

  const [streamFallbackStartMs, setStreamFallbackStartMs] = useState<number | undefined>(undefined);
  useLayoutEffect(() => {
    if (!isRunning) {
      setStreamFallbackStartMs(undefined);
      return;
    }
    if (invokeStartMs != null) return;
    setStreamFallbackStartMs((prev) => prev ?? Date.now());
  }, [isRunning, invokeStartMs]);

  const effectiveInvokeStartMs = invokeStartMs ?? streamFallbackStartMs;
  const liveElapsedSec = useLiveElapsedSeconds(effectiveInvokeStartMs, isRunning);

  const [expanded, setExpanded] = useState(() => Boolean(isRunning && hasReasoning));

  useEffect(() => {
    if (isRunning && hasReasoning) setExpanded(true);
  }, [isRunning, hasReasoning]);

  useEffect(() => {
    if (!isRunning && hasReasoning) setExpanded(false);
  }, [isRunning, hasReasoning]);

  // Finished visible reply only (text channel), no invoke chrome —
  // but only when the block was NOT created from an llm_invoke boundary.
  // Subagent text-only responses still need Brain icon + duration.
  if (!hasReasoning && hasAnswer && !isRunning && !invokeState) {
    return (
      <div className="relative pb-3">
        <p className="text-sm leading-relaxed text-foreground/90 whitespace-pre-wrap">{answer}</p>
      </div>
    );
  }

  const durationFmtOpts = noVisibleModelContent ? { brief: true as const } : undefined;
  const headerLabel =
    showDuration && !isRunning && (invokeDurationSec != null || thinkingDurationSec != null)
      ? formatThoughtDuration(invokeDurationSec ?? thinkingDurationSec ?? 0, durationFmtOpts)
      : isRunning && liveElapsedSec != null
        ? formatThinkingElapsed(liveElapsedSec)
        : t.reasoning.reactThinking;

  const headerLabelShimmer = isRunning && liveElapsedSec == null;

  return (
    <div className="relative pb-3">
      <div
        className={cn(
          'group flex items-center gap-1.5',
          hasReasoning ? 'cursor-pointer' : 'cursor-default',
        )}
        onClick={() => hasReasoning && setExpanded(!expanded)}
        onKeyDown={(e) => {
          if (!hasReasoning) return;
          if (e.key === 'Enter' || e.key === ' ') {
            e.preventDefault();
            setExpanded(!expanded);
          }
        }}
        role={hasReasoning ? 'button' : undefined}
        tabIndex={hasReasoning ? 0 : undefined}
        aria-expanded={hasReasoning ? expanded : undefined}
      >
        <div className="flex shrink-0 items-center gap-1">
          <div className="relative flex h-4 w-4 items-center justify-center">
            <Brain
              className={cn(
                'h-4 w-4 text-muted-foreground',
                hasReasoning && 'transition-opacity group-hover:opacity-0',
              )}
              aria-hidden
            />
            {!isRunning && hasReasoning ? (
              <div className="absolute inset-0 flex items-center justify-center opacity-0 transition-opacity group-hover:opacity-100">
                {expanded ? (
                  <ChevronDown className="h-4 w-4 text-muted-foreground" aria-hidden />
                ) : (
                  <ChevronRight className="h-4 w-4 text-muted-foreground" aria-hidden />
                )}
              </div>
            ) : null}
          </div>
          {isRunning ? (
            <Loader2 className="h-3.5 w-3.5 animate-spin text-muted-foreground/90" aria-hidden />
          ) : null}
        </div>
        <span
          className={cn(
            'text-sm',
            headerLabelShimmer
              ? 'bg-gradient-to-r from-muted-foreground/45 via-muted-foreground/90 to-muted-foreground/45 bg-[length:200%_100%] bg-clip-text text-transparent animate-shimmer'
              : 'text-muted-foreground',
          )}
          lang={
            !isRunning && (invokeDurationSec != null || thinkingDurationSec != null)
              ? 'en'
              : isRunning && liveElapsedSec != null
                ? 'en'
                : undefined
          }
        >
          {headerLabel}
        </span>
      </div>
      {hasReasoning && expanded ? (
        <p
          className={cn(
            'mt-1.5 pl-[22px] text-sm leading-relaxed',
            isRunning ? REASONING_STREAM_SHIMMER_CLASS : 'text-foreground/90',
          )}
        >
          {reasoning}
        </p>
      ) : null}
      {answer.trim() ? (
        <p className="mt-2 pl-[22px] text-sm leading-relaxed text-foreground/90 whitespace-pre-wrap">
          {answer}
        </p>
      ) : null}
    </div>
  );
}

function StepBlockView({
  block,
  minimalChrome,
  isStreaming = true,
  hitlAwaiting = false,
}: {
  block: ReActStepBlock;
  minimalChrome: boolean;
  isStreaming?: boolean;
  hitlAwaiting?: boolean;
}) {
  const { t } = useLanguage();
  const name =
    (block.detail && block.detail.trim()) ||
    block.label.replace(/\s+/g, ' ').trim() ||
    t.reasoning.subagentFallbackName;

  const isPhaseSlot = !!block.phaseId;
  const statusRunningLike = block.status === 'running' || block.status === 'pending' || block.status === 'waiting';
  const running = isStreaming && !isPhaseSlot && statusRunningLike;
  const pausedForHitl = !isStreaming && hitlAwaiting && !isPhaseSlot && statusRunningLike && block.stepVariant === 'subagent_task';

  /** Text shimmer: only while the step row is actively ``running``; stops on ``success`` (and other terminals). */
  const stepStatusRunning = block.status === 'running';

  const [runStartMs, setRunStartMs] = useState<number | undefined>();
  useEffect(() => {
    if (running) setRunStartMs((s) => s ?? Date.now());
    else setRunStartMs(undefined);
  }, [running]);
  const liveStepSec = useLiveElapsedSeconds(runStartMs, running);

  let primary: string;
  if (block.stepVariant === 'subagent_task') {
    if (running) {
      primary = interpolate(t.reasoning.reactSubagentProfessionalAnalyzing, { name });
    } else if (pausedForHitl) {
      primary = interpolate(t.reasoning.reactSubagentProfessionalWaiting, { name });
    } else if (block.subagentDurationSec != null && block.subagentDurationSec > 0) {
      primary = interpolate(t.reasoning.reactSubagentProfessionalDone, {
        name,
        seconds: String(block.subagentDurationSec),
      });
    } else {
      primary = interpolate(t.reasoning.reactSubagentProfessionalDoneUnknown, { name });
    }
  } else {
    primary = block.label;
  }

  const isDelegationGroup = block.stepVariant === 'delegation_group';
  const delegationAccent =
    isDelegationGroup && block.subagentId ? SUBAGENT_ACCENT[block.subagentId] : undefined;

  const Icon =
    block.stepVariant === 'subagent_task'
      ? Bot
      : isDelegationGroup
        ? (delegationAccent?.Icon ?? Bot)
        : CircleDot;
  const showSecondary =
    block.stepVariant !== 'subagent_task' && block.detail && block.detail !== block.label;
  const stepTextShimmer = stepStatusRunning;
  const delegationDepth = block.delegationDepth;
  const delegationGroupStyle: CSSProperties | undefined =
    isDelegationGroup &&
    delegationDepth != null &&
    delegationDepth > 1
      ? { marginLeft: (delegationDepth - 1) * 12 }
      : undefined;

  return (
    <div className="relative pb-3">
      <div className="flex items-start gap-2">
        <div className="relative shrink-0 text-foreground/90">
          <Icon
            className={cn(
              'mt-0.5 h-4 w-4 shrink-0',
              stepTextShimmer && 'text-muted-foreground',
            )}
            aria-hidden
          />
        </div>
        <div
          className={cn(
            'min-w-0 flex-1 py-1 transition-colors duration-200',
            stepTextShimmer
              ? 'border-l-0 pl-0'
              : 'border-l-2 pl-3',
            !stepTextShimmer &&
              (minimalChrome
                ? 'border-border/40'
                : isDelegationGroup
                  ? (delegationAccent?.borderClass ?? 'border-border/40')
                  : running
                    ? 'border-primary/45 bg-primary/[0.04]'
                    : 'border-border/40'),
          )}
          style={delegationGroupStyle}
        >
          <p
            className={cn(
              'flex flex-wrap items-center gap-x-2 gap-y-0.5 text-sm font-medium leading-relaxed text-foreground/90',
            )}
            data-testid={
              stepTextShimmer && block.stepVariant === 'subagent_task'
                ? 'subagent-delegation-running'
                : stepTextShimmer
                  ? 'react-step-running'
                  : undefined
            }
          >
            {stepTextShimmer ? (
              <>
                <span className={cn(REASONING_STREAM_SHIMMER_CLASS)}>{primary}</span>
                {liveStepSec != null ? (
                  <span className="text-xs font-normal tabular-nums text-muted-foreground/90" lang="en">
                    {formatThoughtDuration(liveStepSec)}
                  </span>
                ) : null}
              </>
            ) : (
              <>
                <span>{primary}</span>
                {running && liveStepSec != null ? (
                  <span className="text-xs font-normal tabular-nums text-muted-foreground/90" lang="en">
                    {formatThoughtDuration(liveStepSec)}
                  </span>
                ) : null}
              </>
            )}
            {isDelegationGroup && block.subagentId ? (
              <span
                className={cn(
                  'rounded-full px-1.5 py-0.5 text-[10px] font-medium',
                  delegationAccent?.badgeClass ?? 'bg-muted/60 text-muted-foreground',
                )}
              >
                {block.subagentId}
              </span>
            ) : null}
          </p>
          {showSecondary ? (
            <p className="mt-0.5 text-xs leading-relaxed text-foreground/90">{block.detail}</p>
          ) : null}
        </div>
      </div>
    </div>
  );
}

function ToolRowCollapsible({
  child,
  isStreaming,
  isActivelyRunning,
}: {
  child: ReActToolChild;
  isStreaming: boolean;
  isActivelyRunning: boolean;
}) {
  const { t } = useLanguage();
  const [expanded, setExpanded] = useState(false);
  const [copiedOutput, setCopiedOutput] = useState(false);
  const pending = isStreaming && !child.done;
  const queuedPending = pending && !isActivelyRunning;
  const hasOutput = Boolean(child.toolOutput?.trim());
  const canExpand = child.done && hasOutput;

  const [startMs, setStartMs] = useState<number | undefined>();
  useEffect(() => {
    if (isActivelyRunning) setStartMs((s) => s ?? Date.now());
    else setStartMs(undefined);
  }, [isActivelyRunning]);
  const liveSec = useLiveElapsedSeconds(startMs, isActivelyRunning);

  const handleCopyOutput = async (e: MouseEvent<HTMLButtonElement>) => {
    e.stopPropagation();
    const text = child.toolOutput ?? '';
    try {
      await navigator.clipboard.writeText(text);
      setCopiedOutput(true);
      window.setTimeout(() => setCopiedOutput(false), 2000);
    } catch {
      // Clipboard may be unavailable (non-secure context, permission denied).
    }
  };

  return (
    <div className="w-full min-w-0">
      <div
        className={cn(
          // Cursor-style pill row: subtle border + typography aligned with ThinkingBlockView header
          'flex w-full items-center gap-1.5 rounded-lg border border-border/40 bg-muted/20 px-2.5 py-1.5 min-w-0',
          canExpand && 'cursor-pointer hover:bg-muted/35',
        )}
        onClick={() => canExpand && setExpanded(!expanded)}
        role={canExpand ? 'button' : undefined}
        tabIndex={canExpand ? 0 : undefined}
        aria-expanded={canExpand ? expanded : undefined}
        onKeyDown={canExpand ? (e) => {
          if (e.key === 'Enter' || e.key === ' ') {
            e.preventDefault();
            setExpanded(!expanded);
          }
        } : undefined}
      >
        {/* Status icon */}
        {isActivelyRunning ? (
          <Loader2 className="h-3.5 w-3.5 shrink-0 animate-spin text-muted-foreground/90" aria-hidden />
        ) : child.done && child.isError ? (
          <XCircle className="h-3.5 w-3.5 shrink-0 text-destructive" aria-hidden />
        ) : child.done ? (
          <CheckCircle2 className="h-3.5 w-3.5 shrink-0 text-emerald-600/80 dark:text-emerald-400/90" aria-hidden />
        ) : queuedPending ? (
          <Circle className="h-3 w-3 shrink-0 text-muted-foreground/40" aria-hidden />
        ) : (
          <Terminal className="h-3.5 w-3.5 shrink-0 text-muted-foreground" aria-hidden />
        )}

        {/* Expand chevron (only for rows with output) */}
        {canExpand ? (
          <ChevronRight
            className={cn(
              'h-3.5 w-3.5 shrink-0 text-muted-foreground transition-transform duration-150',
              expanded && 'rotate-90',
            )}
            aria-hidden
          />
        ) : null}

        {/* Tool name — sits between body text and detail to establish hierarchy */}
        <TruncatedWithTooltip
          text={child.toolName}
          className={cn(
            'shrink-0 text-sm',
            child.isError ? 'text-destructive' : 'text-foreground/80',
            queuedPending && 'text-muted-foreground/50',
          )}
        />

        {/* Detail (secondary, still muted like thought chrome) */}
        {child.detail ? (
          <TruncatedWithTooltip
            text={child.detail}
            className={cn(
              'min-w-0 flex-1 text-sm text-muted-foreground',
              queuedPending && 'opacity-50',
            )}
          />
        ) : null}

        {/* Live timer */}
        {isActivelyRunning && liveSec != null ? (
          <span className="shrink-0 text-sm tabular-nums text-muted-foreground" lang="en">
            {formatThoughtDuration(liveSec)}
          </span>
        ) : null}
      </div>

      {/* Expanded result panel — full width aligned with header row */}
      {expanded && hasOutput ? (
        <div className="mt-1 mb-1.5 flex max-h-40 w-full flex-col overflow-hidden rounded-lg border border-border/40 bg-muted/20">
          <div className="flex shrink-0 justify-end px-1 pt-1">
            <Tooltip>
              <TooltipTrigger asChild>
                <button
                  type="button"
                  className="rounded p-1 text-muted-foreground transition-colors hover:bg-muted/60 hover:text-foreground"
                  aria-label={t.reasoning.copyToolResult}
                  data-testid="react-tool-output-copy"
                  onClick={handleCopyOutput}
                >
                  {copiedOutput ? (
                    <Check className="h-3.5 w-3.5 text-emerald-600 dark:text-emerald-400" aria-hidden />
                  ) : (
                    <Copy className="h-3.5 w-3.5" aria-hidden />
                  )}
                </button>
              </TooltipTrigger>
              <TooltipContent side="left" className="text-xs">
                {t.reasoning.copyToolResult}
              </TooltipContent>
            </Tooltip>
          </div>
          <div className="min-h-0 flex-1 overflow-y-auto px-2 pb-2 pt-0">
            <pre
              className={cn(
                'font-mono text-[11px] whitespace-pre-wrap break-all',
                child.isError ? 'text-destructive/80' : 'text-muted-foreground/70',
              )}
            >
              {child.toolOutput}
            </pre>
          </div>
        </div>
      ) : null}
    </div>
  );
}

function ToolExecutionBlockView({
  children,
  isStreaming = false,
}: {
  children: ReActToolChild[];
  isStreaming?: boolean;
}) {
  if (!children.length) return null;

  let activePendingIndex = -1;
  if (isStreaming) {
    for (let i = children.length - 1; i >= 0; i--) {
      if (!children[i].done) {
        activePendingIndex = i;
        break;
      }
    }
  }

  return (
    <TooltipProvider delayDuration={150}>
      <div className="relative w-full min-w-0 pb-3 space-y-0.5">
        {children.map((c, i) => (
          <ToolRowCollapsible
            key={c.toolCallId}
            child={c}
            isStreaming={isStreaming}
            isActivelyRunning={isStreaming && i === activePendingIndex}
          />
        ))}
      </div>
    </TooltipProvider>
  );
}

function TaskTodoRow({
  it,
  rowActive,
}: {
  it: { id: string; title: string; done: boolean };
  rowActive: boolean;
}) {
  const [startMs, setStartMs] = useState<number | undefined>();
  useEffect(() => {
    if (rowActive) setStartMs((s) => s ?? Date.now());
    else setStartMs(undefined);
  }, [rowActive]);
  const liveSec = useLiveElapsedSeconds(startMs, rowActive);

  return (
    <div className="flex items-center gap-1.5 py-0.5">
      <FileCode className="h-3 w-3 shrink-0 text-foreground/55" aria-hidden />
      <span
        className={cn(
          'min-w-0 flex-1 text-xs text-foreground/90',
          it.done && 'text-muted-foreground/80 line-through',
          !it.done && !rowActive && 'text-muted-foreground/55',
        )}
      >
        {it.title}
      </span>
      {rowActive && liveSec != null ? (
        <span className="shrink-0 text-[10px] tabular-nums text-muted-foreground/90" lang="en">
          {formatThoughtDuration(liveSec)}
        </span>
      ) : null}
      {it.done ? <CheckCircle2 className="h-3 w-3 shrink-0 text-foreground/70" aria-hidden /> : null}
    </div>
  );
}

/** ConductResearch topic rows: clamp to two lines; expand/collapse when content overflows. */
function ResearchTaskTodoRow({
  it,
  rowActive,
}: {
  it: { id: string; title: string; done: boolean };
  rowActive: boolean;
}) {
  const { t } = useLanguage();
  const [textExpanded, setTextExpanded] = useState(false);
  const [clampedOverflow, setClampedOverflow] = useState(false);
  const textRef = useRef<HTMLSpanElement>(null);
  const [startMs, setStartMs] = useState<number | undefined>();
  useEffect(() => {
    if (rowActive) setStartMs((s) => s ?? Date.now());
    else setStartMs(undefined);
  }, [rowActive]);
  const liveSec = useLiveElapsedSeconds(startMs, rowActive);

  useLayoutEffect(() => {
    const el = textRef.current;
    if (!el || textExpanded) return;
    setClampedOverflow(el.scrollHeight > el.clientHeight + 2);
  }, [it.title, textExpanded]);

  const showToggle = clampedOverflow || textExpanded;

  return (
    <div className="flex items-start gap-1.5 py-0.5">
      <div className="mt-0.5 shrink-0">
        <FileCode className="h-3 w-3 text-foreground/55" aria-hidden />
      </div>
      <div className="min-w-0 flex-1">
        <span
          ref={textRef}
          title={!textExpanded && clampedOverflow ? it.title : undefined}
          className={cn(
            'block text-xs text-foreground/90',
            !textExpanded && 'line-clamp-2 break-words',
            it.done && 'text-muted-foreground/80 line-through',
            !it.done && !rowActive && 'text-muted-foreground/55',
          )}
        >
          {it.title}
        </span>
        {showToggle ? (
          <button
            type="button"
            className="mt-0.5 block text-left text-[10px] font-medium text-primary/90 hover:underline"
            aria-expanded={textExpanded}
            onClick={(e) => {
              e.stopPropagation();
              setTextExpanded((v) => !v);
            }}
          >
            {textExpanded ? t.tasks.collapse : t.tasks.expand}
          </button>
        ) : null}
      </div>
      {rowActive && liveSec != null ? (
        <span className="mt-0.5 shrink-0 text-[10px] tabular-nums text-muted-foreground/90" lang="en">
          {formatThoughtDuration(liveSec)}
        </span>
      ) : null}
      {it.done ? (
        <CheckCircle2 className="mt-0.5 h-3 w-3 shrink-0 text-foreground/70" aria-hidden />
      ) : null}
    </div>
  );
}

function TaskListBlockView({
  items,
  isStreaming = false,
  listVariant = 'default',
}: {
  items: { id: string; title: string; done: boolean }[];
  isStreaming?: boolean;
  listVariant?: 'default' | 'research';
}) {
  const { t } = useLanguage();
  const [expanded, setExpanded] = useState(true);
  const allDone = items.length > 0 && items.every((it) => it.done);
  const wasAllDone = useRef(allDone);

  useEffect(() => {
    if (allDone && !wasAllDone.current && listVariant === 'research') {
      setExpanded(false);
    }
    wasAllDone.current = allDone;
  }, [allDone, listVariant]);

  if (!items.length) return null;

  const heading =
    listVariant === 'research' ? t.reasoning.researchTaskList : t.reasoning.taskList;

  const doneCount = items.filter((it) => it.done).length;
  const total = items.length;
  const progressLabel = interpolate(t.tasks.progressDone, {
    done: String(doneCount),
    total: String(total),
  });
  const parallelExecution = listVariant === 'research';
  let activeTodoIndex = -1;
  if (isStreaming && !parallelExecution) {
    for (let i = 0; i < items.length; i++) {
      if (!items[i].done) {
        activeTodoIndex = i;
        break;
      }
    }
  }
  const todoRowAnimates = isStreaming && doneCount < total;

  return (
    <div className="relative pb-3">
      <div
        className="flex cursor-pointer items-center gap-2"
        onClick={() => setExpanded(!expanded)}
        role="button"
        tabIndex={0}
        aria-expanded={expanded}
        onKeyDown={(e) => {
          if (e.key === 'Enter' || e.key === ' ') {
            e.preventDefault();
            setExpanded(!expanded);
          }
        }}
      >
        <div className="shrink-0 text-muted-foreground">
          <ListTodo className="h-4 w-4" aria-hidden />
        </div>
        <div className="flex min-w-0 flex-1 items-center gap-1.5">
          {expanded ? (
            <ChevronDown className="h-3 w-3 shrink-0 text-muted-foreground" aria-hidden />
          ) : (
            <ChevronRight className="h-3 w-3 shrink-0 text-muted-foreground" aria-hidden />
          )}
          <span
            className="min-w-0 truncate text-sm font-medium text-muted-foreground"
            title={`${heading} · ${progressLabel}`}
          >
            {heading}
            <span className="font-normal text-muted-foreground/90"> · {progressLabel}</span>
          </span>
          {todoRowAnimates ? (
            <Loader2 className="h-3 w-3 shrink-0 animate-spin text-muted-foreground" aria-hidden />
          ) : (
            <CheckCircle2 className="h-3 w-3 shrink-0 text-muted-foreground" aria-hidden />
          )}
        </div>
      </div>
      {expanded ? (
        <div className="ml-2 mt-2 space-y-1.5 border-l border-border/30 pl-6">
          {items.map((it, idx) => {
            const rowActive = isStreaming && !it.done && (parallelExecution || idx === activeTodoIndex);
            return listVariant === 'research' ? (
              <ResearchTaskTodoRow key={it.id} it={it} rowActive={rowActive} />
            ) : (
              <TaskTodoRow key={it.id} it={it} rowActive={rowActive} />
            );
          })}
        </div>
      ) : null}
    </div>
  );
}

function ResultBlockView({ summary }: { summary: string }) {
  const { t } = useLanguage();
  return (
    <div className="relative pb-3">
      <div className="flex items-center gap-2 text-muted-foreground">
        <Sparkles className="h-4 w-4 shrink-0" aria-hidden />
        <span className="text-sm font-medium">{t.reasoning.reactResultSummary}</span>
        <CheckCircle2 className="h-3 w-3 shrink-0" aria-hidden />
      </div>
      <p className="mt-1.5 text-sm leading-relaxed text-foreground/90">{summary}</p>
    </div>
  );
}

export const ReActTimelineView = memo(function ReActTimelineView({
  blocks,
  isStreaming = false,
  hitlAwaiting = false,
  thinkingDurationSec,
  visualTone = 'default',
}: ReActTimelineViewProps) {
  if (!blocks.length && !isStreaming) return null;

  const minimalChrome = visualTone === 'subagentInline';

  let lastThinkingIdx = -1;
  for (let i = blocks.length - 1; i >= 0; i--) {
    if (blocks[i]?.kind === 'thinking') {
      lastThinkingIdx = i;
      break;
    }
  }

  return (
    <div className="animate-fade-in space-y-1">
      {blocks.length === 0 && isStreaming ? (
        <ThinkingBlockView
          reasoning=""
          answer=""
          isRunning
          showDuration={false}
        />
      ) : null}
      {blocks.map((b, idx) => {
        const key =
          b.kind === 'step' && b.phaseId ? `step-phase-${b.phaseId}` : `${b.kind}-${idx}`;
        switch (b.kind) {
          case 'thinking':
            {
              const isRunning =
                (b.invokeState === 'running' && isStreaming) ||
                (b.invokeState !== 'done' && isStreaming && idx === blocks.length - 1);
              const showDuration = b.invokeState === 'done' ? true : idx === lastThinkingIdx;
            return (
              <ThinkingBlockView
                key={key}
                reasoning={b.reasoning}
                answer={b.answer}
                isRunning={isRunning}
                showDuration={showDuration}
                invokeDurationSec={b.invokeDurationSec}
                thinkingDurationSec={thinkingDurationSec}
                invokeStartMs={b.invokeStartMs}
                invokeState={b.invokeState}
              />
            );
            }
          case 'step':
            return (
              <Fragment key={key}>
                {b.stepVariant === 'delegation_group' ? (
                  <hr className="border-border/20 my-1.5" />
                ) : null}
                <StepBlockView block={b} minimalChrome={minimalChrome} isStreaming={isStreaming} hitlAwaiting={hitlAwaiting} />
              </Fragment>
            );
          case 'tool_execution':
            return (
              <ToolExecutionBlockView key={key} children={b.children} isStreaming={isStreaming} />
            );
          case 'task_list':
            return (
              <TaskListBlockView
                key={key}
                items={b.items}
                isStreaming={isStreaming}
                listVariant={b.listVariant ?? 'default'}
              />
            );
          case 'result':
            return <ResultBlockView key={key} summary={b.summary} />;
          default:
            return null;
        }
      })}
    </div>
  );
});
