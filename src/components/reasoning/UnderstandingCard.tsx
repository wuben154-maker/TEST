import { InputUnderstanding } from '@/types/analysis';
import { cn } from '@/lib/utils';
import { normalizeMultilineText } from '@/lib/text';
import { memo, useMemo, useState } from 'react';
import { useLanguage } from '@/contexts/LanguageContext';
import { Brain, Target, Lightbulb, Tag, Sparkles, ChevronDown, ChevronUp } from 'lucide-react';

interface UnderstandingCardProps {
  understanding: InputUnderstanding;
}

// Confidence badge
const ConfidenceBadge = memo(function ConfidenceBadge({ confidence }: { confidence: number }) {
  const { t } = useLanguage();
  const percent = Math.round(confidence * 100);
  const color = percent >= 80
    ? 'text-emerald-600 bg-emerald-500/10 border-emerald-500/20'
    : percent >= 60
      ? 'text-amber-600 bg-amber-500/10 border-amber-500/20'
      : 'text-muted-foreground bg-muted/50 border-border/30';

  return (
    <span
      className={cn(
        'text-[10px] px-2 py-0.5 rounded-full font-medium border',
        color,
      )}
    >
      {percent}% {t.understanding.confidenceSuffix}
    </span>
  );
});

interface CollapsibleSectionProps {
  icon: React.ElementType;
  title: string;
  children: React.ReactNode;
  defaultOpen?: boolean;
  badge?: React.ReactNode;
}

const CollapsibleSection = memo(function CollapsibleSection({
  icon: Icon,
  title,
  children,
  defaultOpen = true,
  badge,
}: CollapsibleSectionProps) {
  const [isOpen, setIsOpen] = useState(defaultOpen);

  return (
    <div className="space-y-2">
      <button
        type="button"
        onClick={() => setIsOpen(!isOpen)}
        className="flex items-center gap-2 w-full text-left group"
      >
        <Icon className="w-3.5 h-3.5 text-muted-foreground/60" />
        <span className="text-xs font-medium text-muted-foreground flex-1">{title}</span>
        {badge}
        <span className="text-muted-foreground/40 group-hover:text-muted-foreground transition-colors">
          {isOpen ? <ChevronUp className="w-3.5 h-3.5" /> : <ChevronDown className="w-3.5 h-3.5" />}
        </span>
      </button>

      <div
        className={cn(
          'overflow-hidden transition-all duration-200',
          isOpen ? 'max-h-96 opacity-100' : 'max-h-0 opacity-0',
        )}
      >
        {children}
      </div>
    </div>
  );
});

export const UnderstandingCard = memo(function UnderstandingCard({ understanding }: UnderstandingCardProps) {
  const { t } = useLanguage();
  const analysisGoals = understanding.analysisGoals ?? [];
  const keyEntities = understanding.keyEntities ?? [];

  const summaryText = useMemo(
    () => normalizeMultilineText(understanding.summary ?? ''),
    [understanding.summary],
  );
  const approachText = useMemo(
    () => normalizeMultilineText(understanding.suggestedApproach ?? ''),
    [understanding.suggestedApproach],
  );

  const hasGoals = analysisGoals.length > 0;
  const hasEntities = keyEntities.length > 0;
  const hasApproach = !!understanding.suggestedApproach;
  const hasDetails = hasGoals || hasEntities || hasApproach;

  return (
    <div className="space-y-3 animate-fade-in">
      <div className="flex items-start gap-3">
        <div className="w-8 h-8 rounded-lg bg-gradient-to-br from-primary/20 to-primary/5 flex items-center justify-center flex-shrink-0 mt-0.5">
          <Brain className="w-4 h-4 text-primary" />
        </div>

        <div className="flex-1 min-w-0 space-y-2">
          <div className="flex items-center gap-2 flex-wrap">
            <span className="text-sm font-semibold text-foreground">{t.reasoning.understandingTitle}</span>
            <ConfidenceBadge confidence={understanding.confidence} />
          </div>

          {summaryText && (
            <p className="text-sm text-foreground/90 leading-relaxed whitespace-pre-wrap">{summaryText}</p>
          )}
        </div>
      </div>

      {hasDetails && (
        <div className="ml-11 space-y-3 pt-2 border-t border-border/20">
          {hasGoals && (
            <CollapsibleSection icon={Target} title={t.understanding.analysisGoals} defaultOpen={true}>
              <div className="space-y-1.5 pl-5">
                {analysisGoals.map((goal, idx) => {
                  const goalText =
                    typeof goal === 'string'
                      ? goal
                      : (goal as { text?: string })?.text ?? JSON.stringify(goal);
                  return (
                    <div key={idx} className="flex items-start gap-2 text-sm">
                      <Sparkles className="w-3 h-3 text-primary/60 mt-1 flex-shrink-0" />
                      <span className="text-foreground/80 leading-relaxed">{goalText}</span>
                    </div>
                  );
                })}
              </div>
            </CollapsibleSection>
          )}

          {hasEntities && (
            <CollapsibleSection
              icon={Tag}
              title={t.understanding.identifiedEntities}
              defaultOpen={false}
              badge={
                <span className="text-[10px] text-muted-foreground/50">{keyEntities.length}</span>
              }
            >
              <div className="flex flex-wrap gap-1.5 pl-5">
                {keyEntities.slice(0, 10).map((entity, idx) => {
                  const entityText =
                    typeof entity === 'string'
                      ? entity
                      : (entity as { text?: string })?.text ?? JSON.stringify(entity);
                  return (
                    <span
                      key={idx}
                      className="text-xs px-2 py-0.5 rounded bg-muted/40 text-foreground/70 font-mono"
                    >
                      {entityText}
                    </span>
                  );
                })}
                {keyEntities.length > 10 && (
                  <span className="text-[10px] text-muted-foreground self-center">
                    +{keyEntities.length - 10}
                  </span>
                )}
              </div>
            </CollapsibleSection>
          )}

          {hasApproach && (
            <CollapsibleSection icon={Lightbulb} title={t.understanding.analysisApproach} defaultOpen={false}>
              <p className="text-xs text-foreground/60 leading-relaxed pl-5 whitespace-pre-wrap">
                {approachText}
              </p>
            </CollapsibleSection>
          )}
        </div>
      )}
    </div>
  );
});

export default UnderstandingCard;
