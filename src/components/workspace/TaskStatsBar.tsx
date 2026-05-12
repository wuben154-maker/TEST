import { useLanguage } from '@/contexts/LanguageContext';
import type {
  ResearchStats,
  SecurityStats,
  SecurityValidationLiteral,
  ResearchFreshness,
} from '@/types/analysis';
import type { AnalysisResultStats, AnalysisResultStatus } from '@/types/project';
import { cn } from '@/lib/utils';

/**
 * Task-stats summary bar (stats-bar-value-redesign).
 *
 * Renders either a security profile (5 chips) or a research profile (5 chips)
 * based on `stats.taskKind`. Hidden entirely when `taskKind` is absent or the
 * matching profile payload is missing.
 *
 * Running state keeps the pulse "analyzing" chip plus the optional
 * `sourceLabel` chip so the user still sees *something is happening*
 * before `conclusion.meta` arrives (see acceptance-ui U-06).
 *
 * No "technical row", no right-side severity pill, no action / popovers.
 */

interface TaskStatsBarProps {
  stats?: AnalysisResultStats;
  status: AnalysisResultStatus;
  /** Optional chip shown only in the running variant. */
  sourceLabel?: string;
}

const CHIP_NEUTRAL =
  'inline-flex items-center rounded-md border border-border bg-card px-2 py-0.5 text-xs font-medium shadow-sm';
const CHIP_RISK =
  'inline-flex items-center rounded-md border border-red-500/50 bg-red-500/10 px-2 py-0.5 text-xs font-medium text-red-600 dark:text-red-400';
const CHIP_SEVERITY_HIGH =
  'inline-flex items-center rounded-md border border-destructive/60 bg-destructive/10 px-2 py-0.5 text-xs font-semibold text-destructive';
const CHIP_SEVERITY_MEDIUM =
  'inline-flex items-center rounded-md border border-amber-500/50 bg-amber-500/10 px-2 py-0.5 text-xs font-semibold text-amber-700 dark:text-amber-300';
const CHIP_SEVERITY_LOW =
  'inline-flex items-center rounded-md border border-border bg-muted/40 px-2 py-0.5 text-xs font-medium';

function severityClass(sev: SecurityStats['severity']): string {
  if (sev === 'critical' || sev === 'high') return CHIP_SEVERITY_HIGH;
  if (sev === 'medium') return CHIP_SEVERITY_MEDIUM;
  return CHIP_SEVERITY_LOW;
}

function Chip(props: {
  label: string;
  value: string;
  className?: string;
  title?: string;
}) {
  const { label, value, className, title } = props;
  return (
    <span className={className ?? CHIP_NEUTRAL} title={title}>
      <span className="text-muted-foreground">{label}</span>
      <span className="mx-1 text-muted-foreground/50" aria-hidden>
        :
      </span>
      <span className="font-medium text-foreground">{value}</span>
    </span>
  );
}

function formatActionable(a: SecurityStats['actionable']): string | undefined {
  if (!a || a.total <= 0) return undefined;
  const parts: string[] = [];
  if (a.critical > 0) parts.push(`${a.critical}C`);
  if (a.high > 0) parts.push(`${a.high}H`);
  if (a.medium > 0) parts.push(`${a.medium}M`);
  return parts.length > 0 ? `${a.total}·${parts.join('/')}` : String(a.total);
}

function formatThreatClasses(classes: string[] | undefined): string | undefined {
  if (!classes || classes.length === 0) return undefined;
  const top = classes.slice(0, 2).map((c) => c.replace(/_/g, ' '));
  const extra = classes.length > 2 ? ` +${classes.length - 2}` : '';
  return `${top.join(' · ')}${extra}`;
}

function formatValidation(
  validation: SecurityValidationLiteral[] | undefined,
  labels: Record<SecurityValidationLiteral, string>,
): string | undefined {
  if (!validation || validation.length === 0) return undefined;
  return validation.map((v) => labels[v]).join(' · ');
}

function freshnessLabel(
  band: ResearchFreshness | undefined,
  labels: Record<string, string>,
): string | undefined {
  if (!band) return undefined;
  const map: Record<ResearchFreshness, string> = {
    '<=7d': labels['lte7d'] ?? '≤7d',
    '<=30d': labels['lte30d'] ?? '≤30d',
    '<=90d': labels['lte90d'] ?? '≤90d',
    older: labels['older'] ?? 'Older',
    'n/a': labels['na'] ?? 'n/a',
  };
  return map[band];
}

function SecurityStatsChips({ data, tp }: { data: SecurityStats; tp: TaskPanelCopy }) {
  const chips: JSX.Element[] = [];

  const severityLabels = tp.severityLabels as Record<string, string>;
  const sevText = severityLabels[data.severity] ?? data.severity;
  chips.push(
    <Chip
      key="severity"
      label={tp.threat}
      value={sevText}
      className={severityClass(data.severity)}
    />,
  );

  if (typeof data.riskScore === 'number') {
    const riskChip = data.riskScore >= 70 ? CHIP_RISK : CHIP_NEUTRAL;
    chips.push(
      <Chip key="risk" label={tp.risk} value={String(data.riskScore)} className={riskChip} />,
    );
  }

  const actionable = formatActionable(data.actionable);
  if (actionable) {
    chips.push(
      <Chip key="actionable" label={tp.actionableFindings} value={actionable} />,
    );
  }

  const threat = formatThreatClasses(data.threatClasses);
  if (threat) {
    chips.push(<Chip key="threats" label={tp.threatClasses} value={threat} />);
  }

  const validation = formatValidation(
    data.validation,
    tp.validationLabels as Record<SecurityValidationLiteral, string>,
  );
  if (validation) {
    chips.push(<Chip key="validation" label={tp.validation} value={validation} />);
  }

  return <>{chips}</>;
}

function ResearchStatsChips({ data, tp }: { data: ResearchStats; tp: TaskPanelCopy }) {
  const chips: JSX.Element[] = [];

  if (typeof data.keyFindings === 'number') {
    chips.push(<Chip key="keyFindings" label={tp.keyFindings} value={String(data.keyFindings)} />);
  }
  if (typeof data.recommendations === 'number') {
    chips.push(
      <Chip key="recommendations" label={tp.recommendations} value={String(data.recommendations)} />,
    );
  }
  if (typeof data.sources === 'number') {
    chips.push(<Chip key="sources" label={tp.sourceCount} value={String(data.sources)} />);
  }
  const fresh = freshnessLabel(data.freshness, tp.freshnessLabels as Record<string, string>);
  if (fresh) {
    chips.push(<Chip key="freshness" label={tp.freshness} value={fresh} />);
  }
  if (typeof data.gaps === 'number') {
    chips.push(<Chip key="gaps" label={tp.gaps} value={String(data.gaps)} />);
  }

  return <>{chips}</>;
}

type TaskPanelCopy = ReturnType<typeof useLanguage>['t']['workspace']['taskPanel'];

export function TaskStatsBar({ stats, status, sourceLabel }: TaskStatsBarProps) {
  const { t } = useLanguage();
  const tp = t.workspace.taskPanel;

  if (status === 'running') {
    return (
      <div
        className="flex flex-col gap-1.5 border-b border-border bg-muted/30 px-4 py-2"
        data-testid="task-stats-bar"
        aria-label={tp.statsBarAria}
      >
        <div className="flex flex-wrap items-center gap-2">
          <span className="inline-flex items-center gap-1.5 rounded-md border border-blue-500/40 bg-blue-500/5 px-2 py-0.5 text-xs font-medium text-blue-600 dark:text-blue-400">
            <span className="relative flex h-1.5 w-1.5 flex-shrink-0">
              <span className="absolute inline-flex h-full w-full animate-ping rounded-full bg-blue-400 opacity-75" />
              <span className="relative inline-flex h-1.5 w-1.5 rounded-full bg-blue-500" />
            </span>
            {tp.analyzing}
          </span>
          {sourceLabel ? (
            <Chip label={tp.source} value={sourceLabel} title={sourceLabel} />
          ) : null}
        </div>
      </div>
    );
  }

  if (!stats?.taskKind) {
    return null;
  }

  let chips: JSX.Element | null = null;
  if (stats.taskKind === 'security' && stats.security) {
    chips = <SecurityStatsChips data={stats.security} tp={tp} />;
  } else if (stats.taskKind === 'research' && stats.research) {
    chips = <ResearchStatsChips data={stats.research} tp={tp} />;
  }

  if (!chips) return null;

  return (
    <div
      className={cn(
        'flex flex-wrap items-center gap-2 border-b border-border bg-muted/30 px-4 py-2',
        'animate-in fade-in slide-in-from-top-1 duration-300',
      )}
      data-testid="task-stats-bar"
      aria-label={tp.statsBarAria}
    >
      {chips}
    </div>
  );
}
