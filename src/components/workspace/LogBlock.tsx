import { FileText, Copy, Check } from 'lucide-react';
import { useState } from 'react';
import { LogBlock as LogBlockType } from '@/types/analysis';
import { useLanguage } from '@/contexts/LanguageContext';

interface LogBlockProps {
  block: LogBlockType;
}

export function LogBlock({ block }: LogBlockProps) {
  const { t } = useLanguage();
  const [copied, setCopied] = useState(false);

  const handleCopy = () => {
    navigator.clipboard.writeText(block.content);
    setCopied(true);
    setTimeout(() => setCopied(false), 2000);
  };

  const highlightContent = () => {
    if (!block.highlights || block.highlights.length === 0) {
      return <span>{block.content}</span>;
    }

    let result: React.ReactNode[] = [];
    let lastIndex = 0;

    const sortedHighlights = [...block.highlights].sort((a, b) => a.start - b.start);

    sortedHighlights.forEach((highlight, idx) => {
      if (highlight.start > lastIndex) {
        result.push(<span key={`text-${idx}`}>{block.content.slice(lastIndex, highlight.start)}</span>);
      }

      const highlightClass = {
        ip: 'bg-destructive/30 text-destructive px-1 rounded cursor-pointer hover:bg-destructive/50',
        url: 'bg-accent/30 text-accent px-1 rounded cursor-pointer hover:bg-accent/50',
        payload: 'bg-warning/30 text-warning px-1 rounded',
      }[highlight.type];

      result.push(
        <span key={`highlight-${idx}`} className={highlightClass}>
          {block.content.slice(highlight.start, highlight.end)}
        </span>
      );

      lastIndex = highlight.end;
    });

    if (lastIndex < block.content.length) {
      result.push(<span key="text-end">{block.content.slice(lastIndex)}</span>);
    }

    return result;
  };

  return (
    <div className="rounded-lg border border-border bg-secondary/30 overflow-hidden animate-slide-up">
      <div className="flex items-center justify-between px-4 py-2 bg-secondary/50 border-b border-border">
        <div className="flex items-center gap-2 text-muted-foreground">
          <FileText className="w-4 h-4" />
          <span className="text-xs font-medium uppercase tracking-wide">{t.workspaceBlocks.rawLog}</span>
        </div>
        <button
          onClick={handleCopy}
          className="p-1.5 rounded hover:bg-muted transition-colors text-muted-foreground hover:text-foreground"
        >
          {copied ? <Check className="w-4 h-4 text-success" /> : <Copy className="w-4 h-4" />}
        </button>
      </div>
      <pre className="p-4 text-sm font-mono text-foreground/90 overflow-x-auto whitespace-pre-wrap break-all">
        {highlightContent()}
      </pre>
    </div>
  );
}
