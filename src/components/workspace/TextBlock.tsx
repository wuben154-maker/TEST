import { TextBlock as TextBlockType } from '@/types/analysis';

interface TextBlockProps {
  block: TextBlockType;
}

export function TextBlock({ block }: TextBlockProps) {
  if (block.variant === 'heading') {
    return (
      <h2 className="text-lg font-semibold text-foreground border-b border-border pb-2 mb-4 animate-fade-in">
        {block.content}
      </h2>
    );
  }

  if (block.variant === 'bullet') {
    return (
      <div className="flex items-start gap-2 animate-fade-in">
        <span className="text-primary mt-1.5">•</span>
        <p className="text-sm text-foreground/80 leading-relaxed">{block.content}</p>
      </div>
    );
  }

  return (
    <p className="text-sm text-foreground/80 leading-relaxed animate-fade-in">
      {block.content}
    </p>
  );
}
