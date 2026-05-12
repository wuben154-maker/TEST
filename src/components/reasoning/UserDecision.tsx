import { useState } from 'react';
import { Check } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { cn } from '@/lib/utils';
import { useLanguage } from '@/contexts/LanguageContext';

export interface DecisionOption {
  id: string;
  label: string;
  description?: string;
  variant?: 'default' | 'destructive' | 'success';
}

export interface UserDecisionRequest {
  id: string;
  question: string;
  options: DecisionOption[];
  allowMultiple?: boolean;
}

interface UserDecisionProps {
  request: UserDecisionRequest;
  onDecision: (requestId: string, selectedOptions: string[]) => void;
  isResolved?: boolean;
  resolvedAnswer?: string[];
}

export function UserDecision({ request, onDecision, isResolved, resolvedAnswer }: UserDecisionProps) {
  const { t } = useLanguage();
  const [selectedOptions, setSelectedOptions] = useState<Set<string>>(new Set());
  const [submitError, setSubmitError] = useState(false);
  const multi = !!request.allowMultiple;

  const handleOptionClick = (optionId: string) => {
    if (isResolved) return;

    if (multi) {
      setSelectedOptions((prev) => {
        const next = new Set(prev);
        if (next.has(optionId)) {
          next.delete(optionId);
        } else {
          next.add(optionId);
        }
        return next;
      });
      setSubmitError(false);
    } else {
      setSelectedOptions(new Set([optionId]));
      setSubmitError(false);
    }
  };

  const handleSubmit = () => {
    if (selectedOptions.size === 0) {
      setSubmitError(true);
      return;
    }
    setSubmitError(false);
    onDecision(request.id, Array.from(selectedOptions));
  };

  return (
    <div className="rounded-2xl border border-border/50 bg-card/80 shadow-sm p-4 dark:bg-card/40 animate-fade-in">
      <p className="text-[13px] text-foreground mb-3">{request.question}</p>

      <div className="space-y-2 mb-3">
        {request.options.map((option) => {
          const isSelected = selectedOptions.has(option.id) || resolvedAnswer?.includes(option.id);

          return (
            <button
              key={option.id}
              type="button"
              onClick={() => handleOptionClick(option.id)}
              disabled={isResolved}
              className={cn(
                'w-full text-left px-3 py-2.5 rounded-xl border transition-all',
                isSelected
                  ? 'border-primary/50 bg-primary/10'
                  : 'border-border/50 hover:border-primary/30 hover:bg-muted/30',
                isResolved && 'opacity-60 cursor-not-allowed',
              )}
            >
              <div className="flex items-center gap-2.5">
                {multi ? (
                  <div
                    className={cn(
                      'w-4 h-4 rounded border flex items-center justify-center shrink-0 transition-colors',
                      isSelected ? 'border-primary bg-primary' : 'border-muted-foreground/40',
                    )}
                    aria-hidden
                  >
                    {isSelected ? <Check className="w-2.5 h-2.5 text-primary-foreground" strokeWidth={3} /> : null}
                  </div>
                ) : (
                  <div
                    className={cn(
                      'w-4 h-4 rounded-full border flex items-center justify-center transition-colors shrink-0',
                      isSelected ? 'border-primary bg-primary' : 'border-muted-foreground/40',
                    )}
                    aria-hidden
                  >
                    {isSelected && <Check className="w-2.5 h-2.5 text-primary-foreground" />}
                  </div>
                )}
                <div className="flex-1 min-w-0">
                  <span className="text-xs text-foreground">{option.label}</span>
                  {option.description && (
                    <p className="text-[10px] text-muted-foreground mt-0.5">{option.description}</p>
                  )}
                </div>
              </div>
            </button>
          );
        })}
      </div>

      {submitError && multi ? (
        <p className="text-xs text-destructive mb-2" role="alert">
          {t.reasoning.pickAtLeastOneOption}
        </p>
      ) : null}

      {!isResolved ? (
        <Button
          type="button"
          onClick={handleSubmit}
          disabled={isResolved || (!multi && selectedOptions.size === 0)}
          size="sm"
          className="h-9 text-xs rounded-xl"
        >
          {t.common.confirm}
        </Button>
      ) : (
        <div className="flex items-center gap-1.5 text-[10px] text-emerald-500">
          <Check className="w-3 h-3" />
          <span>{t.reasoning.decisionSubmitted}</span>
        </div>
      )}
    </div>
  );
}
