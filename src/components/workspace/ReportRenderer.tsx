import type { ReportContentBlock, ReportDocument, WorkspaceBlock } from '@/types/analysis';
import { cn } from '@/lib/utils';
import { DecoderBlock } from './DecoderBlock';
import { IntelCard } from './IntelCard';
import { LogBlock } from './LogBlock';
import { SummaryBlock } from './SummaryBlock';
import { TextBlock } from './TextBlock';
import { MarkdownRenderer } from './MarkdownRenderer';

interface ReportRendererProps {
  document: ReportDocument;
  className?: string;
}

function renderLegacyBlock(block: WorkspaceBlock) {
  switch (block.type) {
    case 'log':
      return <LogBlock key={block.id} block={block} />;
    case 'decoder':
      return <DecoderBlock key={block.id} block={block} />;
    case 'intel':
      return <IntelCard key={block.id} block={block} />;
    case 'text':
      return <TextBlock key={block.id} block={block} />;
    case 'summary':
      return <SummaryBlock key={block.id} block={block} />;
    case 'analysis':
      return <MarkdownRenderer key={block.id} markdown={block.content} />;
    default:
      return null;
  }
}

function renderContentBlock(block: ReportContentBlock, key: string) {
  if (block.type === 'markdown') {
    return <MarkdownRenderer key={key} markdown={block.markdown} />;
  }
  if (block.type === 'legacy_workspace_block') {
    return <div key={key}>{renderLegacyBlock(block.block)}</div>;
  }
  if (block.type === 'metric_cards') {
    return (
      <div key={key} className="grid gap-2 sm:grid-cols-2 lg:grid-cols-3">
        {block.metrics.map((metric) => (
          <div key={metric.label} className="rounded-lg border border-border bg-card p-3">
            <div className="text-xs text-muted-foreground">{metric.label}</div>
            <div className="mt-1 text-sm font-semibold text-foreground">{metric.value}</div>
          </div>
        ))}
      </div>
    );
  }
  return null;
}

export function ReportRenderer({ document, className }: ReportRendererProps) {
  return (
    <article className={cn('mx-auto max-w-4xl space-y-7 py-4', className)}>
      {document.sections.map((section) => (
        <section key={section.id} className="space-y-3">
          <h2 className="text-xs font-semibold uppercase tracking-wide text-muted-foreground">
            {section.title}
          </h2>
          <div className="space-y-4">
            {section.blocks.map((block, index) =>
              renderContentBlock(block, `${section.id}-${index}`),
            )}
          </div>
        </section>
      ))}
    </article>
  );
}
