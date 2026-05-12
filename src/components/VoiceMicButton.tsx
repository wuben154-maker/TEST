import { Mic, MicOff } from 'lucide-react';
import { cn } from '@/lib/utils';
import { Button } from '@/components/ui/button';
import {
  Tooltip,
  TooltipContent,
  TooltipProvider,
  TooltipTrigger,
} from '@/components/ui/tooltip';
import { useLanguage } from '@/contexts/LanguageContext';

interface VoiceMicButtonProps {
  isSupported: boolean;
  isListening: boolean;
  disabled?: boolean;
  onToggle: () => void;
  className?: string;
}

export function VoiceMicButton({
  isSupported,
  isListening,
  disabled = false,
  onToggle,
  className,
}: VoiceMicButtonProps) {
  const { t } = useLanguage();

  if (!isSupported) {
    return (
      <TooltipProvider>
        <Tooltip>
          <TooltipTrigger asChild>
            <Button
              variant="ghost"
              size="icon"
              className={cn("h-7 w-7 text-muted-foreground opacity-50 cursor-not-allowed shrink-0", className)}
              disabled
            >
              <MicOff className="w-3.5 h-3.5" />
            </Button>
          </TooltipTrigger>
          <TooltipContent>
            <p>{t.voice?.notSupported || 'Voice input not supported'}</p>
          </TooltipContent>
        </Tooltip>
      </TooltipProvider>
    );
  }

  return (
    <TooltipProvider>
      <Tooltip>
        <TooltipTrigger asChild>
          <Button
            variant="ghost"
            size="icon"
            className={cn(
              "h-7 w-7 shrink-0 transition-all duration-200",
              isListening
                ? 'bg-destructive/20 text-destructive hover:bg-destructive/30 animate-pulse'
                : 'text-muted-foreground hover:text-foreground',
              className
            )}
            onClick={onToggle}
            disabled={disabled}
          >
            <Mic className="w-3.5 h-3.5" />
          </Button>
        </TooltipTrigger>
        <TooltipContent>
          <p>
            {isListening
              ? t.voice?.listening || 'Listening...'
              : t.voice?.voiceInput || 'Voice input'}
          </p>
        </TooltipContent>
      </Tooltip>
    </TooltipProvider>
  );
}
