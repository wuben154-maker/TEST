/**
 * Realtime context-usage badge — rendered next to the Model selector.
 * Visual: minimalist Cursor-style circular progress ring. The trigger shows
 * **only** the ring (no percent or fraction text); numbers and breakdown live
 * inside the popover. Hidden entirely when no `llm_invoke_end` has produced
 * usage yet (no data → no UI; avoids a placeholder chip).
 */
import { useMemo, useState } from 'react';
import { AlertTriangle, Layers } from 'lucide-react';
import { Popover, PopoverContent, PopoverTrigger } from '@/components/ui/popover';
import { cn } from '@/lib/utils';
import type { ContextUsageState } from '@/types/analysis';
import {
  MAIN_SUBAGENT_KEY,
  deriveIndicator,
  deriveSubagentPromptIndicator,
  getMainUsageSnapshot,
  type IndicatorSeverity,
} from '@/lib/contextUsage';
import { useLanguage } from '@/contexts/LanguageContext';
import { useModelLimits } from '@/hooks/useModelLimits';

export interface ContextUsageBadgeProps {
  state: ContextUsageState;
  /** Context window size (tokens) for the active model. */
  contextWindow: number;
  /** Optional display name for the active model. Shown inside the popover. */
  modelDisplayName?: string;
  /** Optional extra classes for the trigger button. */
  className?: string;
}

function formatTokens(n: number): string {
  if (n < 1000) return String(n);
  if (n < 1_000_000) return `${(n / 1000).toFixed(n < 10_000 ? 1 : 0)}k`;
  return `${(n / 1_000_000).toFixed(1)}M`;
}

/**
 * Ring geometry. 20 px outer box; 8 px radius; 2 px stroke. The slightly
 * larger size (vs. the previous chip layout with inline text) keeps the
 * ring scannable now that the percent label is gone. ``circumference`` is
 * pre-computed so the dashoffset math is a single multiply at render.
 */
const RING_SIZE = 20;
const RING_RADIUS = 8;
const RING_CIRCUMFERENCE = 2 * Math.PI * RING_RADIUS;

const SEVERITY_RING_CLASS: Record<IndicatorSeverity, string> = {
  idle: 'text-muted-foreground',
  safe: 'text-muted-foreground',
  warn: 'text-amber-500 dark:text-amber-400',
  danger: 'text-red-500 dark:text-red-400',
  critical: 'text-red-500 dark:text-red-400',
};

const SEVERITY_TRIGGER_CLASS: Record<IndicatorSeverity, string> = {
  idle: 'hover:bg-muted/50',
  safe: 'hover:bg-muted/50',
  warn: 'hover:bg-amber-500/10',
  danger: 'hover:bg-red-500/10',
  // Pulse only on critical so the ring itself communicates urgency without copy.
  critical: 'bg-red-500/10 animate-pulse hover:bg-red-500/20',
};

export function ContextUsageBadge({
  state,
  contextWindow,
  modelDisplayName,
  className,
}: ContextUsageBadgeProps) {
  const [open, setOpen] = useState(false);
  const { t } = useLanguage();
  const copy = t.command.contextUsage;
  const { getContextWindow, getLimit } = useModelLimits();

  const indicator = useMemo(
    () => deriveIndicator(state, contextWindow),
    [state, contextWindow],
  );

  /** Option A: after `context_summarized`, main snapshots are cleared — show idle icon until next `llm_invoke_end`. */
  const awaitingAfterCompact =
    indicator == null && state.lastSummarizedAt != null && contextWindow > 0;

  if (!indicator && !awaitingAfterCompact) return null;

  const percent = indicator ? Math.round(indicator.percent) : 0;
  const tokens = indicator ? indicator.tokens : 0;
  const severity = indicator?.severity ?? 'idle';
  const totalFmt = formatTokens(contextWindow);
  const usedFmt = formatTokens(tokens);
  const percentLabel = copy.percentOfWindow
    .replace('{percent}', String(percent))
    .replace('{total}', totalFmt);
  const fractionLabel = copy.fraction
    .replace('{used}', usedFmt)
    .replace('{total}', totalFmt);
  const ariaLabel = awaitingAfterCompact
    ? copy.compressedAwaitingAria
    : copy.ariaLabel
        .replace('{percent}', String(percent))
        .replace('{total}', totalFmt);

  const { cumulative, bySubagent, lastSummarizedAt } = state;
  const mainSnap = getMainUsageSnapshot(state);
  const mainRow = bySubagent.find((b) => b.subagentName === MAIN_SUBAGENT_KEY);
  const subagentRows = bySubagent
    .filter((b) => b.subagentName !== MAIN_SUBAGENT_KEY)
    .slice()
    .sort((a, b) => b.inputTokens - a.inputTokens);

  const fillRatio = indicator
    ? Math.min(1, Math.max(0, indicator.percent / 100))
    : 0;
  const dashOffset = RING_CIRCUMFERENCE * (1 - fillRatio);

  const titleHint = awaitingAfterCompact
    ? copy.compressedAwaitingTitle
    : `${percentLabel} · ${fractionLabel}`;

  return (
    <Popover open={open} onOpenChange={setOpen}>
      <PopoverTrigger asChild>
        <button
          type="button"
          aria-label={ariaLabel}
          aria-live="polite"
          data-testid="context-usage-badge"
          data-severity={severity}
          data-pct={awaitingAfterCompact ? '' : String(percent)}
          data-awaiting-measure={awaitingAfterCompact ? 'true' : undefined}
          className={cn(
            'h-7 w-7 shrink-0 inline-flex items-center justify-center rounded-md bg-transparent transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary/60',
            SEVERITY_TRIGGER_CLASS[severity],
            className,
          )}
          title={titleHint}
        >
          {awaitingAfterCompact ? (
            <Layers className="h-3.5 w-3.5 text-muted-foreground" aria-hidden />
          ) : (
            <svg
              width={RING_SIZE}
              height={RING_SIZE}
              viewBox={`0 0 ${RING_SIZE} ${RING_SIZE}`}
              className={cn('shrink-0', SEVERITY_RING_CLASS[indicator!.severity])}
              aria-hidden
            >
              {/* Track */}
              <circle
                cx={RING_SIZE / 2}
                cy={RING_SIZE / 2}
                r={RING_RADIUS}
                fill="none"
                stroke="currentColor"
                strokeOpacity={0.2}
                strokeWidth={2}
              />
              {/* Progress — rotated −90° so fill starts at 12 o'clock */}
              <circle
                cx={RING_SIZE / 2}
                cy={RING_SIZE / 2}
                r={RING_RADIUS}
                fill="none"
                stroke="currentColor"
                strokeWidth={2}
                strokeLinecap="round"
                strokeDasharray={RING_CIRCUMFERENCE}
                strokeDashoffset={dashOffset}
                transform={`rotate(-90 ${RING_SIZE / 2} ${RING_SIZE / 2})`}
                style={{ transition: 'stroke-dashoffset 200ms ease-out' }}
              />
            </svg>
          )}
        </button>
      </PopoverTrigger>
      <PopoverContent
        align="end"
        className="w-80 p-4 text-sm"
        data-testid="context-usage-popover"
      >
        <div className="flex items-start justify-between gap-3">
          <div>
            <div className="font-medium">{copy.popoverTitle}</div>
            <div className="text-xs text-muted-foreground mt-0.5">
              {copy.popoverSubtitle}
            </div>
          </div>
          {awaitingAfterCompact ? null : (
            <span
              className={cn(
                'text-xs font-medium tabular-nums',
                severity === 'critical' || severity === 'danger'
                  ? 'text-red-600 dark:text-red-400'
                  : severity === 'warn'
                    ? 'text-amber-600 dark:text-amber-400'
                    : 'text-foreground',
              )}
            >
              {percentLabel}
            </span>
          )}
        </div>

        {!awaitingAfterCompact &&
          (severity === 'danger' || severity === 'critical') && (
          <div
            role="alert"
            className="mt-3 flex items-start gap-2 rounded-md border border-red-500/40 bg-red-500/10 px-2 py-1.5 text-xs text-red-700 dark:text-red-300"
          >
            <AlertTriangle className="h-3.5 w-3.5 mt-0.5 shrink-0" aria-hidden />
            <span>
              {severity === 'critical' ? copy.critical : copy.warning}
            </span>
          </div>
        )}

        <div className="mt-3 space-y-1">
          <div className="flex items-center justify-between gap-2 text-xs">
            <span className="text-muted-foreground shrink-0">{copy.mainAgent}</span>
            <span className="tabular-nums text-right min-w-0">
              {awaitingAfterCompact ? (
                <span className="text-muted-foreground font-normal">
                  {copy.mainAfterCompact}
                </span>
              ) : mainSnap ? (
                copy.mainLastPromptLine
                    .replace('{used}', formatTokens(mainSnap.inputTokens))
                    .replace('{total}', formatTokens(contextWindow))
                    .replace('{percent}', String(Math.round(indicator!.percent)))
              ) : (
                copy.tokens.replace(
                    '{count}',
                    formatTokens(mainRow?.inputTokens ?? 0),
                  )
              )}
              {modelDisplayName ? (
                <span className="ml-1 text-muted-foreground">· {modelDisplayName}</span>
              ) : null}
            </span>
          </div>
        </div>

        <div className="mt-3">
          <div className="text-xs text-muted-foreground mb-1">{copy.subagents}</div>
          {subagentRows.length === 0 ? (
            <div className="text-xs text-muted-foreground italic">
              {copy.noSubagentUsage}
            </div>
          ) : (
            <ul className="space-y-1.5">
              {subagentRows.map((row) => {
                const sSnap = state.latestSubagentByName?.[row.subagentName];
                const sWin = getContextWindow(sSnap?.modelId);
                const sInd = deriveSubagentPromptIndicator(sSnap, sWin);
                const sModel = getLimit(sSnap?.modelId)?.name;
                return (
                  <li
                    key={row.subagentName}
                    className="flex items-start justify-between gap-2 text-xs"
                  >
                    <span className="truncate mr-2" title={row.subagentName}>
                      {row.subagentName}
                    </span>
                    <span className="tabular-nums text-muted-foreground text-right shrink-0">
                      {sSnap && sInd
                        ? copy.subagentLastPromptLine
                            .replace('{used}', formatTokens(sSnap.inputTokens))
                            .replace('{total}', formatTokens(sWin))
                            .replace('{percent}', String(Math.round(sInd.percent)))
                        : copy.tokens.replace(
                            '{count}',
                            formatTokens(row.inputTokens),
                          )}
                      {sModel ? (
                        <span className="ml-1">· {sModel}</span>
                      ) : null}
                      {row.invocations > 1 ? (
                        <span className="ml-1">× {row.invocations}</span>
                      ) : null}
                    </span>
                  </li>
                );
              })}
            </ul>
          )}
        </div>

        <div className="mt-3 border-t border-border/50 pt-2 text-[11px] text-muted-foreground">
          <div>{copy.cumulativeLabel}</div>
          <div className="tabular-nums text-foreground">
            {copy.cumulativeValue
              .replace('{input}', formatTokens(cumulative.inputTokens))
              .replace('{output}', formatTokens(cumulative.outputTokens))
              .replace('{count}', String(cumulative.invocations))}
          </div>
          <p className="mt-1.5 leading-snug">{copy.cumulativeSessionNote}</p>
          {lastSummarizedAt ? (
            <div className="mt-1 italic">{copy.summarizedPopover}</div>
          ) : null}
        </div>
      </PopoverContent>
    </Popover>
  );
}
