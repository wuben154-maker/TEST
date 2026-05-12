import { AlertTriangle, AlertCircle, Info, CheckCircle, ShieldAlert } from 'lucide-react';
import { SummaryBlock as SummaryBlockType } from '@/types/analysis';

interface SummaryBlockProps {
  block: SummaryBlockType;
}

const severityConfig = {
  critical: { icon: ShieldAlert, color: 'text-destructive', bg: 'bg-destructive/20', border: 'border-destructive/50' },
  high: { icon: AlertTriangle, color: 'text-destructive', bg: 'bg-destructive/15', border: 'border-destructive/40' },
  medium: { icon: AlertCircle, color: 'text-warning', bg: 'bg-warning/20', border: 'border-warning/50' },
  low: { icon: Info, color: 'text-accent', bg: 'bg-accent/20', border: 'border-accent/50' },
  info: { icon: CheckCircle, color: 'text-success', bg: 'bg-success/20', border: 'border-success/50' },
};

export function SummaryBlock({ block }: SummaryBlockProps) {
  const config = severityConfig[block.severity];
  const Icon = config.icon;

  return (
    <div className={`rounded-lg border ${config.border} ${config.bg} p-4 animate-slide-up`}>
      <div className="flex items-start gap-3">
        <div className={`mt-0.5 ${config.color}`}>
          <Icon className="w-5 h-5" />
        </div>
        <div className="flex-1">
          <h3 className={`font-semibold ${config.color}`}>{block.title}</h3>
          <p className="text-sm text-foreground/80 mt-1 leading-relaxed whitespace-pre-wrap">{block.description}</p>
        </div>
      </div>
    </div>
  );
}
