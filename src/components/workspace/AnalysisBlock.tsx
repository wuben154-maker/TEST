import type { AnalysisBlock as AnalysisBlockType } from '@/types/analysis';
import { MarkdownRenderer } from './MarkdownRenderer';

interface Props {
  block: AnalysisBlockType;
}

export function AnalysisBlock({ block }: Props) {
  return (
    <div className="w-full">
      <MarkdownRenderer markdown={block.content} />
    </div>
  );
}
