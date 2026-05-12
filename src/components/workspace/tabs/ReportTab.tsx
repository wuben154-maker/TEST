import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { Bot, Sparkles } from 'lucide-react';
import type { WorkspaceBlock } from '@/types/analysis';
import type { AnalysisResultStats, AnalysisResultStatus } from '@/types/project';
import { useLanguage } from '@/contexts/LanguageContext';
import { normalizeReportDocument } from '@/lib/reportDocument';
import { ReportRenderer } from '../ReportRenderer';

const AUTO_SAVE_INTERVAL_MS = 3000;

function ReportSkeleton({ title, desc }: { title: string; desc: string }) {
  return (
    <div
      className="flex flex-col items-center justify-center py-14 gap-6 select-none text-muted-foreground px-6"
      data-testid="report-skeleton"
    >
      <div className="relative w-20 h-20 flex items-center justify-center">
        <span
          className="absolute inset-0 rounded-2xl bg-primary/10 animate-ping"
          style={{ animationDuration: '2s', animationTimingFunction: 'ease-out' }}
        />
        <div className="relative w-20 h-20 rounded-2xl bg-muted/30 flex items-center justify-center">
          <Sparkles
            className="w-10 h-10 text-primary/70 animate-spin"
            style={{ animationDuration: '4s', animationTimingFunction: 'linear' }}
          />
        </div>
      </div>
      <h3 className="text-lg font-medium text-foreground">{title}</h3>
      <p className="text-sm text-center max-w-sm">{desc}</p>
    </div>
  );
}

interface ReportTabProps {
  status: AnalysisResultStatus;
  blocks: WorkspaceBlock[];
  title?: string;
  generatedAt?: string;
  stats?: AnalysisResultStats;
  editedText?: string;
  onSave?: (text: string) => void;
}

export function ReportTab({
  status,
  blocks,
  title,
  generatedAt,
  stats,
  editedText,
  onSave,
}: ReportTabProps) {
  const { t } = useLanguage();
  const tp = t.workspace.taskPanel;
  const [isEditing, setIsEditing] = useState(false);
  const contentRef = useRef<HTMLDivElement>(null);
  const dirtyRef = useRef(false);
  const savingRef = useRef(false);

  const flush = useCallback(() => {
    if (!dirtyRef.current || savingRef.current || !contentRef.current || !onSave) return;
    savingRef.current = true;
    const text = contentRef.current.innerText ?? '';
    onSave(text);
    dirtyRef.current = false;
    savingRef.current = false;
  }, [onSave]);

  useEffect(() => {
    if (!isEditing) return;
    const timer = setInterval(flush, AUTO_SAVE_INTERVAL_MS);
    return () => clearInterval(timer);
  }, [isEditing, flush]);

  const isEmpty = blocks.length === 0 && !editedText;
  const reportDocument = useMemo(
    () =>
      normalizeReportDocument({
        id: 'report',
        title: title || t.workspace.title,
        blocks,
        stats,
        generatedAt,
        copy: t.workspace.reportTemplates
          ? {
              templates: t.workspace.reportTemplates,
              risk: tp.risk,
              sources: tp.sourceCount,
              severityLabels: tp.severityLabels,
            }
          : undefined,
      }),
    [blocks, generatedAt, stats, title, t.workspace.reportTemplates, t.workspace.title, tp],
  );

  // Bug #1: skeleton only while truly empty-and-running. Once blocks or
  // editedText have streamed in, render them immediately so the report panel
  // catches up with the chat-side conclusion instead of flashing empty for 1–2s.
  if (status === 'running' && isEmpty) {
    return <ReportSkeleton title={t.workspace.smartCanvas} desc={t.workspace.empty} />;
  }

  if (isEmpty) {
    return (
      <div className="flex flex-col items-center justify-center py-16 text-muted-foreground text-sm gap-2">
        <Bot className="w-8 h-8 text-muted-foreground/40" />
        <span>{tp.noReport}</span>
      </div>
    );
  }

  const handleDoubleClick = () => {
    if (!onSave || isEditing) return;
    setIsEditing(true);
    requestAnimationFrame(() => {
      if (!contentRef.current) return;
      contentRef.current.focus();
      const sel = window.getSelection();
      if (sel) {
        sel.selectAllChildren(contentRef.current);
        sel.collapseToEnd();
      }
    });
  };

  const handleBlur = (e: React.FocusEvent<HTMLDivElement>) => {
    if (contentRef.current?.contains(e.relatedTarget as Node)) return;
    flush();
    setIsEditing(false);
  };

  const handleInput = () => {
    dirtyRef.current = true;
  };

  const editable = !!onSave;

  return (
    <div
      ref={contentRef}
      className={`
        space-y-6 py-4 outline-none rounded-md transition-shadow
        ${isEditing ? 'ring-2 ring-primary/30 bg-muted/10' : ''}
      `}
      contentEditable={isEditing}
      suppressContentEditableWarning
      onDoubleClick={handleDoubleClick}
      onBlur={handleBlur}
      onInput={handleInput}
      title={editable && !isEditing ? tp.doubleClickToEdit : undefined}
      style={editable && !isEditing ? { cursor: 'text' } : undefined}
    >
      {editedText !== undefined ? (
        <div className="whitespace-pre-wrap text-sm leading-relaxed text-foreground">
          {editedText}
        </div>
      ) : (
        <ReportRenderer document={reportDocument} />
      )}
    </div>
  );
}
