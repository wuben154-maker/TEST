import type { ReactNode } from 'react';

interface TaskHeaderProps {
  /** Full task / project headline (may wrap; not truncated for display). */
  title: string;
  /** Share, export, fullscreen controls (right side). */
  headerActions?: ReactNode;
}

export function TaskHeader({ title, headerActions }: TaskHeaderProps) {
  return (
    <div className="flex min-w-0 items-start justify-between gap-3 border-b border-border bg-background px-4 py-3">
      <h2
        className="min-w-0 flex-1 text-base font-semibold leading-snug text-foreground break-words"
        title={title}
      >
        {title}
      </h2>
      {headerActions ? (
        <div className="flex shrink-0 flex-wrap items-center justify-end gap-1.5">{headerActions}</div>
      ) : null}
    </div>
  );
}
