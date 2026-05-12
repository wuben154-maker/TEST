import { ArrowRight, Code2, Copy, Check } from 'lucide-react';
import { useState } from 'react';
import { DecoderBlock as DecoderBlockType } from '@/types/analysis';
import { useLanguage } from '@/contexts/LanguageContext';

interface DecoderBlockProps {
  block: DecoderBlockType;
}

export function DecoderBlock({ block }: DecoderBlockProps) {
  const { t } = useLanguage();
  const [copiedEncoded, setCopiedEncoded] = useState(false);
  const [copiedDecoded, setCopiedDecoded] = useState(false);

  const handleCopy = (text: string, setter: (v: boolean) => void) => {
    navigator.clipboard.writeText(text);
    setter(true);
    setTimeout(() => setter(false), 2000);
  };

  return (
    <div className="rounded-lg border border-border bg-secondary/30 overflow-hidden animate-slide-up">
      <div className="flex items-center justify-between px-4 py-2 bg-secondary/50 border-b border-border">
        <div className="flex items-center gap-2 text-muted-foreground">
          <Code2 className="w-4 h-4" />
          <span className="text-xs font-medium uppercase tracking-wide">
            {t.workspaceBlocks.decodingAnalysis}
          </span>
        </div>
        <span className="px-2 py-0.5 rounded text-xs font-mono bg-primary/20 text-primary border border-primary/30">
          {block.algorithm}
        </span>
      </div>
      
      <div className="grid md:grid-cols-2 divide-x divide-border">
        {/* Encoded */}
        <div className="p-4">
          <div className="flex items-center justify-between mb-2">
            <span className="text-xs text-muted-foreground uppercase tracking-wide">
              {t.workspace.ciphertext} / Encoded
            </span>
            <button
              onClick={() => handleCopy(block.encoded, setCopiedEncoded)}
              className="p-1 rounded hover:bg-muted transition-colors text-muted-foreground hover:text-foreground"
            >
              {copiedEncoded ? <Check className="w-3 h-3 text-success" /> : <Copy className="w-3 h-3" />}
            </button>
          </div>
          <pre className="text-sm font-mono text-destructive/80 bg-destructive/10 p-3 rounded overflow-x-auto whitespace-pre-wrap break-all">
            {block.encoded}
          </pre>
        </div>

        {/* Arrow for mobile */}
        <div className="md:hidden flex items-center justify-center py-2 bg-secondary/30">
          <ArrowRight className="w-4 h-4 text-primary rotate-90" />
        </div>

        {/* Decoded */}
        <div className="p-4">
          <div className="flex items-center justify-between mb-2">
            <span className="text-xs text-muted-foreground uppercase tracking-wide">
              {t.workspace.plaintext} / Decoded
            </span>
            <button
              onClick={() => handleCopy(block.decoded, setCopiedDecoded)}
              className="p-1 rounded hover:bg-muted transition-colors text-muted-foreground hover:text-foreground"
            >
              {copiedDecoded ? <Check className="w-3 h-3 text-success" /> : <Copy className="w-3 h-3" />}
            </button>
          </div>
          <pre className="text-sm font-mono text-success/90 bg-success/10 p-3 rounded overflow-x-auto whitespace-pre-wrap break-all">
            {block.decoded}
          </pre>
        </div>
      </div>
    </div>
  );
}
