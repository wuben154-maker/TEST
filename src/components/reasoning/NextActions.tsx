import { NextAction } from '@/types/analysis';
import { ArrowRight, Sparkles, Zap } from 'lucide-react';
import { cn } from '@/lib/utils';
import { useLanguage } from '@/contexts/LanguageContext';

interface NextActionsProps {
  actions: NextAction[];
  onActionClick: (message: string) => void;
}

export function NextActions({ actions, onActionClick }: NextActionsProps) {
  const { t } = useLanguage();
  if (!actions || actions.length === 0) return null;

  return (
    <div className="mt-6 animate-fade-in">
      {/* Header with gradient accent */}
      <div className="flex items-center gap-2 mb-3">
        <div className="relative">
          <div className="absolute inset-0 bg-gradient-to-r from-violet-500 to-pink-500 rounded-full blur-sm opacity-50" />
          <div className="relative w-5 h-5 rounded-full bg-gradient-to-r from-violet-500 to-pink-500 flex items-center justify-center">
            <Sparkles className="w-3 h-3 text-white" />
          </div>
        </div>
        <span className="text-sm font-medium text-foreground/80">{t.reasoning.nextActions}</span>
      </div>

      {/* Action buttons with enhanced styling */}
      <div className="flex flex-col gap-2">
        {actions.map((action, index) => (
          <button
            key={action.id}
            onClick={() => onActionClick(action.message)}
            className={cn(
              "group relative flex items-center gap-3 w-full px-4 py-3 rounded-xl",
              "bg-gradient-to-r from-primary/5 via-primary/10 to-transparent",
              "border border-primary/20 hover:border-primary/40",
              "hover:from-primary/10 hover:via-primary/15 hover:to-primary/5",
              "transition-all duration-300 cursor-pointer",
              "hover:shadow-lg hover:shadow-primary/10",
              "hover:-translate-y-0.5"
            )}
          >
            {/* Action icon */}
            <div className={cn(
              "flex-shrink-0 w-8 h-8 rounded-lg flex items-center justify-center",
              "bg-gradient-to-br from-primary/20 to-primary/10",
              "group-hover:from-primary/30 group-hover:to-primary/20",
              "transition-colors duration-300"
            )}>
              <Zap className={cn(
                "w-4 h-4 text-primary",
                "group-hover:scale-110 transition-transform duration-300"
              )} />
            </div>

            {/* Action text */}
            <span className={cn(
              "flex-1 text-left text-sm font-medium text-foreground/80",
              "group-hover:text-foreground transition-colors duration-300"
            )}>
              {action.label}
            </span>

            {/* Arrow indicator */}
            <div className={cn(
              "flex-shrink-0 w-6 h-6 rounded-full flex items-center justify-center",
              "bg-primary/10 group-hover:bg-primary/20",
              "transition-all duration-300"
            )}>
              <ArrowRight className={cn(
                "w-3.5 h-3.5 text-primary/60 group-hover:text-primary",
                "transform group-hover:translate-x-0.5 transition-all duration-300"
              )} />
            </div>

            {/* Subtle shine effect on hover */}
            <div className={cn(
              "absolute inset-0 rounded-xl opacity-0 group-hover:opacity-100",
              "bg-gradient-to-r from-transparent via-white/5 to-transparent",
              "transition-opacity duration-500 pointer-events-none"
            )} />
          </button>
        ))}
      </div>
    </div>
  );
}
