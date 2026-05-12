import type {
  ReportContentBlock,
  ReportCover,
  ReportDocument,
  ReportSection,
  ReportSectionKind,
  ReportTemplateId,
  SecuritySeverity,
  WorkspaceBlock,
} from '@/types/analysis';
import type { AnalysisResultStats } from '@/types/project';

export interface NormalizeReportInput {
  id: string;
  title?: string;
  blocks: WorkspaceBlock[];
  stats?: AnalysisResultStats;
  generatedAt?: string;
  copy?: ReportDocumentCopy;
}

export interface ReportDocumentCopy {
  templates: Record<ReportTemplateId, string>;
  risk: string;
  sources: string;
  severityLabels: Record<SecuritySeverity, string>;
}

const DEFAULT_COPY: ReportDocumentCopy = {
  templates: {
    security_analysis: 'Security Analysis',
    research_brief: 'Research Brief',
    executive_summary: 'Executive Summary',
    generic_analysis: 'Analysis Report',
  },
  risk: 'Risk',
  sources: 'sources',
  severityLabels: {
    critical: 'Critical',
    high: 'High',
    medium: 'Medium',
    low: 'Low',
    info: 'Info',
  },
};

const TEMPLATE_KICKERS: Record<ReportTemplateId, string> = {
  security_analysis: 'Security Analysis',
  research_brief: 'Research Brief',
  executive_summary: 'Executive Summary',
  generic_analysis: 'Analysis Report',
};

function chooseTemplate(stats?: AnalysisResultStats): ReportTemplateId {
  if (stats?.taskKind === 'security') return 'security_analysis';
  if (stats?.taskKind === 'research') return 'research_brief';
  return 'generic_analysis';
}

function blockTitle(block: WorkspaceBlock): string {
  if (block.type === 'analysis') return block.title || 'Analysis';
  if (block.type === 'summary') return block.title || 'Executive Summary';
  if (block.type === 'log') return 'Evidence log';
  if (block.type === 'decoder') return 'Decoded artifact';
  if (block.type === 'intel') return 'Threat intelligence';
  if (block.type === 'text' && block.variant === 'heading') return block.content;
  return 'Appendix';
}

function sectionKind(block: WorkspaceBlock): ReportSectionKind {
  if (block.type === 'summary') return 'executive_summary';
  if (block.type === 'analysis') return 'custom';
  if (block.type === 'intel') return 'evidence';
  return 'appendix';
}

function sectionBlock(block: WorkspaceBlock): ReportContentBlock {
  if (block.type === 'analysis') {
    return { type: 'markdown', markdown: block.content };
  }
  return { type: 'legacy_workspace_block', block };
}

function buildCover(input: NormalizeReportInput, templateId: ReportTemplateId): ReportCover {
  const copy = input.copy ?? DEFAULT_COPY;
  const badges: string[] = [];
  if (input.stats?.taskKind === 'security' && input.stats.security) {
    badges.push(copy.severityLabels[input.stats.security.severity]);
    if (typeof input.stats.security.riskScore === 'number') {
      badges.push(`${copy.risk} ${input.stats.security.riskScore}`);
    }
  }
  if (input.stats?.taskKind === 'research' && input.stats.research) {
    if (typeof input.stats.research.sources === 'number') {
      badges.push(`${input.stats.research.sources} ${copy.sources}`);
    }
    if (input.stats.research.freshness) {
      badges.push(input.stats.research.freshness);
    }
  }

  return {
    title: input.title || 'Analysis Report',
    kicker: copy.templates[templateId] ?? TEMPLATE_KICKERS[templateId],
    generatedAt: input.generatedAt,
    badges,
  };
}

function sectionToMarkdown(section: ReportSection): string {
  const parts = [`## ${section.title}`];
  for (const block of section.blocks) {
    if (block.type === 'markdown') {
      parts.push(block.markdown.trim());
      continue;
    }
    if (block.type === 'legacy_workspace_block') {
      const legacy = block.block;
      if (legacy.type === 'summary') {
        parts.push(`> **${legacy.title}** (${legacy.severity})\n> ${legacy.description}`);
      } else if (legacy.type === 'text') {
        parts.push(legacy.variant === 'heading' ? `### ${legacy.content}` : legacy.content);
      } else if (legacy.type === 'log') {
        parts.push(`\`\`\`\n${legacy.content}\n\`\`\``);
      } else if (legacy.type === 'decoder') {
        parts.push(
          [
            `**Algorithm:** ${legacy.algorithm}`,
            '',
            '**Encoded:**',
            `\`\`\`\n${legacy.encoded}\n\`\`\``,
            '',
            '**Decoded:**',
            `\`\`\`\n${legacy.decoded}\n\`\`\``,
          ].join('\n'),
        );
      } else if (legacy.type === 'intel') {
        parts.push(`**Indicator:** ${legacy.indicator} (${legacy.threatScore})`);
      }
    }
  }
  return parts.filter(Boolean).join('\n\n');
}

export function serializeReportMarkdown(doc: ReportDocument): string {
  const parts = [`# ${doc.title}`];
  if (doc.generatedAt) {
    parts.push(`Generated at: ${doc.generatedAt}`);
  }
  if (doc.cover?.kicker) {
    parts.push(`Template: ${doc.cover.kicker}`);
  }
  for (const section of doc.sections) {
    parts.push(sectionToMarkdown(section));
  }
  return parts.filter(Boolean).join('\n\n');
}

export function normalizeReportDocument(input: NormalizeReportInput): ReportDocument {
  const templateId = chooseTemplate(input.stats);
  const title = input.title || 'Analysis Report';
  const sections: ReportSection[] = input.blocks.map((block, index) => ({
    id: `${block.id || 'block'}-${index}`,
    title: blockTitle(block),
    kind: sectionKind(block),
    blocks: [sectionBlock(block)],
  }));
  const cover = buildCover({ ...input, title }, templateId);
  const docWithoutFallback: Omit<ReportDocument, 'markdownFallback'> = {
    schemaVersion: 1,
    id: input.id,
    title,
    templateId,
    generatedAt: input.generatedAt,
    cover,
    sections,
  };

  const markdownFallback = serializeReportMarkdown({
    ...docWithoutFallback,
    markdownFallback: '',
  });

  return {
    ...docWithoutFallback,
    markdownFallback,
  };
}
