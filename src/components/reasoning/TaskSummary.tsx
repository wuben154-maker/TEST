import { memo, useMemo, useState } from 'react';
import { CheckCircle2 } from 'lucide-react';
import { useLanguage } from '@/contexts/LanguageContext';

interface TaskSummaryProps {
  content: string;
}

export const TaskSummary = memo(function TaskSummary({ content }: TaskSummaryProps) {
  const { t } = useLanguage();
  const [isExpanded, setIsExpanded] = useState(false);
  const fullSummary = content || '';
  const PREVIEW_LENGTH = 300;
  const isTruncated = fullSummary.length > PREVIEW_LENGTH;
  const previewSummary = useMemo(
    () => (isTruncated ? `${fullSummary.slice(0, PREVIEW_LENGTH)}...` : fullSummary),
    [fullSummary, isTruncated]
  );

  if (!fullSummary.trim()) return null;

  return (
    <div className="flex items-start gap-2.5">
      {/* Success icon */}
      <div className="flex-shrink-0 mt-0.5">
        <CheckCircle2 className="w-4 h-4 text-emerald-500" />
      </div>

      <div className="min-w-0">
        <p className="text-sm text-foreground/90 leading-relaxed whitespace-pre-wrap">
          {isExpanded ? fullSummary : previewSummary}
        </p>
        {isTruncated && (
          <button
            type="button"
            className="mt-1 text-xs text-primary hover:underline"
            onClick={() => setIsExpanded((prev) => !prev)}
          >
            {isExpanded ? t.reasoning.collapseFullSummary : t.reasoning.expandFullSummary}
          </button>
        )}
      </div>
    </div>
  );
});

export default TaskSummary;
