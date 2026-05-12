import { cn } from '@/lib/utils';

interface ThinkingIndicatorProps {
  isThinking: boolean;
  label?: string;
}

export function ThinkingIndicator({ isThinking, label = 'Thinking' }: ThinkingIndicatorProps) {
  if (!isThinking) return null;

  return (
    <div className="flex items-center gap-2 py-1 animate-fade-in">
      <span className="text-[15px] text-foreground">{label}</span>
      <span className="inline-block w-[2px] h-[18px] bg-foreground/80 animate-pulse" />
    </div>
  );
}
