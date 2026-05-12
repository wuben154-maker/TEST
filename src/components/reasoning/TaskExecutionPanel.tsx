import { useState, useEffect, useRef, memo, useCallback, useMemo } from 'react';
import { 
  ChevronDown, 
  ChevronRight, 
  Check, 
  Loader2, 
  AlertCircle,
  Circle,
  Sparkles
} from 'lucide-react';
import { cn } from '@/lib/utils';
import { normalizeMultilineText } from '@/lib/text';
import { PlannedTask, TaskPlan, TaskStep } from '@/types/analysis';
import { useLanguage } from '@/contexts/LanguageContext';
import { Skeleton } from '@/components/ui/skeleton';
import { formatThoughtDuration } from '@/lib/thinkingDurationLabel';
import { useLiveElapsedSeconds } from '@/lib/liveElapsedSeconds';
import { REASONING_STREAM_SHIMMER_CLASS } from '@/lib/reasoningStreamShimmer';

// Legacy task type for backward compatibility
export interface LegacyTask {
  id: string;
  title: string;
  status: 'pending' | 'in_progress' | 'done';
  description?: string;
}

type TaskLabels = {
  executing: string;
  executingTask: string;
  completed: string;
  failed: string;
  pending: string;
  expand: string;
  collapse: string;
  taskOverview: string;
  /** Shown next to progress in the task list header (e.g. "Task List · 2 / 4 Done"). */
  taskListTitle: string;
  progressDone: string;
};

// Filter steps based on the `internal` property from backend
function shouldFilterStep(step: TaskStep): boolean {
  return step.internal === true;
}

// ============================================
// 1. Cursor-style task list: collapsible "X of Y Done" + flat task rows
// ============================================
interface TaskOverviewProps {
  tasks: PlannedTask[];
  labels: TaskLabels;
}

const TaskOverview = memo(function TaskOverview({ tasks, labels }: TaskOverviewProps) {
  const [expanded, setExpanded] = useState(true);
  const completedCount = tasks.filter((t) => t.status === 'success').length;
  const total = tasks.length;
  const progressText = labels.progressDone
    .replace('{done}', String(completedCount))
    .replace('{total}', String(total));

  return (
    <div className="mb-2">
      <button
        type="button"
        onClick={() => setExpanded((e) => !e)}
        className="flex items-center gap-2 w-full text-left text-xs text-muted-foreground hover:text-foreground/80 transition-colors py-1"
      >
        {expanded ? (
          <ChevronDown className="w-3.5 h-3.5 shrink-0" />
        ) : (
          <ChevronRight className="w-3.5 h-3.5 shrink-0" />
        )}
        <span className="flex min-w-0 flex-1 items-baseline gap-2">
          <span className="font-medium text-foreground/85 shrink-0">{labels.taskListTitle}</span>
          <span className="truncate text-muted-foreground">{progressText}</span>
        </span>
      </button>
      {expanded && (
        <div className="space-y-0.5 mt-1">
          {tasks.map((task) => (
            <TaskOverviewItem key={task.id} task={task} labels={labels} />
          ))}
        </div>
      )}
    </div>
  );
});

// Flat task row - Cursor-style: icon + title only, no border/bg
interface TaskOverviewItemProps {
  task: PlannedTask;
  labels: TaskLabels;
}

const TaskOverviewItem = memo(function TaskOverviewItem({ task, labels }: TaskOverviewItemProps) {
  const isRunning = task.status === 'running';
  const isSuccess = task.status === 'success';
  const isError = task.status === 'error';
  const isPending = task.status === 'pending';

  return (
    <div className="flex items-center gap-2 py-1 text-xs">
      <div className="w-4 flex-shrink-0 flex items-center justify-center">
        {isRunning && <Loader2 className="w-3.5 h-3.5 animate-spin text-primary" />}
        {isSuccess && (
          <div className="w-4 h-4 rounded-full bg-emerald-500 flex items-center justify-center">
            <Check className="w-2.5 h-2.5 text-white" />
          </div>
        )}
        {isError && (
          <div className="w-4 h-4 rounded-full bg-destructive flex items-center justify-center">
            <AlertCircle className="w-2.5 h-2.5 text-white" />
          </div>
        )}
        {isPending && <Circle className="w-3 h-3 text-muted-foreground/40" />}
      </div>
      <span
        className={cn(
          "flex-1 truncate",
          isSuccess && "text-muted-foreground",
          isError && "text-destructive",
          isPending && "text-muted-foreground/60"
        )}
      >
        {task.title}
      </span>
    </div>
  );
});

// ============================================
// 2. Single task execution block - expandable steps and summary
// ============================================
interface TaskExecutionBlockProps {
  task: PlannedTask;
  index: number;
  labels: TaskLabels;
  /** Force show even if pending */
  forceShow?: boolean;
}

const TaskExecutionBlock = memo(function TaskExecutionBlock({ task, index, labels, forceShow = false }: TaskExecutionBlockProps) {
  const [isExpanded, setIsExpanded] = useState(false);
  const [justCompleted, setJustCompleted] = useState(false);
  const prevStatusRef = useRef(task.status);
  
  const isRunning = task.status === 'running';
  const isSuccess = task.status === 'success';
  const isError = task.status === 'error';
  const isPending = task.status === 'pending';
  
  // Filter steps - memoized
  const filteredSteps = useMemo(
    () => (task.steps || []).filter(step => !shouldFilterStep(step)),
    [task.steps]
  );
  const hasSteps = filteredSteps.length > 0;

  const resultText = useMemo(() => normalizeMultilineText(task.result), [task.result]);
  const errorText = useMemo(() => normalizeMultilineText(task.error), [task.error]);

  const hasContent = hasSteps || resultText || errorText;
  
  // Toggle expand handler - memoized
  const handleToggle = useCallback(() => {
    if (hasContent) {
      setIsExpanded(prev => !prev);
    }
  }, [hasContent]);
  
  // Auto-expand while running
  useEffect(() => {
    if (isRunning) {
      setIsExpanded(true);
    }
  }, [isRunning]);
  
  // Detect completion for animation
  useEffect(() => {
    if (prevStatusRef.current === 'running' && task.status === 'success') {
      setJustCompleted(true);
      const timer = setTimeout(() => setJustCompleted(false), 600);
      return () => clearTimeout(timer);
    }
    prevStatusRef.current = task.status;
  }, [task.status]);
  
  // Do not render pending tasks as blocks (unless forceShow is true)
  if (isPending && !forceShow) {
    return null;
  }
  
  return (
    <div 
      className={cn(
        "rounded-lg border transition-all duration-300",
        isRunning && "border-primary/30 bg-primary/5",
        isSuccess && "border-emerald-500/20 bg-emerald-500/5",
        isError && "border-destructive/30 bg-destructive/5",
        justCompleted && "ring-2 ring-emerald-500/30"
      )}
      style={{ 
        animationDelay: `${index * 50}ms`,
        animationFillMode: 'both'
      }}
    >
      {/* Header - clickable to expand/collapse */}
      <button
        onClick={handleToggle}
        className={cn(
          "w-full flex items-center gap-3 p-3 text-left transition-all duration-200",
          hasContent && "cursor-pointer hover:bg-muted/20"
        )}
      >
        {/* Expand/Collapse Icon */}
        {hasContent && (
          <div className={cn(
            "text-muted-foreground/50 transition-transform duration-200 flex-shrink-0",
            isExpanded && "rotate-90"
          )}>
            <ChevronRight className="w-4 h-4" />
          </div>
        )}
        
        {/* Status Indicator */}
        <div className="flex-shrink-0 w-5 h-5 flex items-center justify-center">
          {isRunning && (
            <div className="relative">
              <Loader2 className="w-4 h-4 text-primary animate-spin" />
            </div>
          )}
          {isSuccess && (
            <div className={cn(
              "w-4 h-4 rounded-full bg-emerald-500 flex items-center justify-center",
              justCompleted && "scale-110"
            )}>
              <Check className="w-2.5 h-2.5 text-white" />
            </div>
          )}
          {isError && (
            <div className="w-4 h-4 rounded-full bg-destructive flex items-center justify-center">
              <AlertCircle className="w-2.5 h-2.5 text-white" />
            </div>
          )}
        </div>
        
        {/* Task Title */}
        <div className="flex-1 min-w-0">
          <span className={cn(
            "font-medium text-sm",
            isRunning && "text-foreground",
            isSuccess && "text-muted-foreground",
            isError && "text-destructive"
          )}>
            {isRunning && `${labels.executing}：`}
            {task.title}
          </span>
          
          {/* Skill Badge */}
          {task.skillName && (
            <span className={cn(
              "ml-2 text-[10px] px-1.5 py-0.5 rounded-full",
              isRunning ? "bg-primary/10 text-primary" : "bg-muted text-muted-foreground"
            )}>
              {task.skillName}
            </span>
          )}
        </div>
        
        {/* Duration */}
        {task.durationMs > 0 && (
          <span className="text-[10px] text-muted-foreground/40 tabular-nums flex-shrink-0">
            {(task.durationMs / 1000).toFixed(1)}s
          </span>
        )}
        
        {/* Expand Button Label */}
        {hasContent && (
          <span className="text-[10px] text-muted-foreground/50 flex-shrink-0">
            {isExpanded ? labels.collapse : labels.expand}
          </span>
        )}
      </button>
      
      {/* Expandable Content */}
      <div className={cn(
        "overflow-hidden transition-all duration-300 ease-out",
        isExpanded && hasContent ? "max-h-[600px] opacity-100" : "max-h-0 opacity-0"
      )}>
        <div className="px-4 pb-3 space-y-2">
          {/* Steps (执行过程) - execution process */}
          {hasSteps && (
            <div className="ml-6 pl-3 border-l-2 border-border/30 space-y-1">
              {filteredSteps.map((step, idx) => (
                <StepItem key={step.id || idx} step={step} index={idx} />
              ))}
            </div>
          )}
          {/* Result/Summary (执行摘要) - after steps */}
          {resultText && (
            <div className="ml-6 mt-2 p-2 rounded bg-muted/30 text-sm text-muted-foreground whitespace-pre-wrap">
              {resultText}
            </div>
          )}
          
          {/* Error Message */}
          {errorText && (
            <div className="ml-6 p-2 rounded bg-destructive/10 text-xs text-destructive whitespace-pre-wrap">
              {errorText}
            </div>
          )}
        </div>
      </div>
    </div>
  );
});

// ============================================
// 3. Step item component - supports workflow_step and tool-call display
// ============================================
interface StepItemProps {
  step: TaskStep;
  index: number;
}

const StepItem = memo(function StepItem({ step, index }: StepItemProps) {
  const isRunning = step.status === 'running';
  const isSuccess = step.status === 'success';
  const isError = step.status === 'error';
  const [justCompleted, setJustCompleted] = useState(false);
  const [isExpanded, setIsExpanded] = useState(false);
  const prevStatusRef = useRef(step.status);
  const [runStartMs, setRunStartMs] = useState<number | undefined>();
  useEffect(() => {
    if (isRunning) setRunStartMs((s) => s ?? Date.now());
    else setRunStartMs(undefined);
  }, [isRunning]);
  const liveStepSec = useLiveElapsedSeconds(runStartMs, isRunning);

  const hasToolInfo = step.toolName || step.toolOutput || step.detail;
  
  // Detect completion for animation
  useEffect(() => {
    if (prevStatusRef.current === 'running' && step.status === 'success') {
      setJustCompleted(true);
      const timer = setTimeout(() => setJustCompleted(false), 400);
      return () => clearTimeout(timer);
    }
    prevStatusRef.current = step.status;
  }, [step.status]);
  
  return (
    <div 
      className={cn(
        "transition-all duration-200",
        justCompleted && "bg-emerald-500/5 rounded"
      )}
      style={{ 
        animationDelay: `${index * 30}ms`,
        animationFillMode: 'both'
      }}
    >
      {/* Main Step Row */}
      <div 
        className={cn(
          "flex items-center gap-2 py-1",
          hasToolInfo && "cursor-pointer hover:bg-muted/30 rounded px-1 -mx-1"
        )}
        onClick={() => hasToolInfo && setIsExpanded(!isExpanded)}
      >
        {/* Expand indicator for steps with details */}
        {hasToolInfo && (
          <ChevronRight className={cn(
            "w-3 h-3 text-muted-foreground/30 transition-transform duration-150",
            isExpanded && "rotate-90"
          )} />
        )}
        
        {/* Step Status — running uses muted dot; motion is on the label (shimmer). */}
        <div className="w-4 flex-shrink-0 flex items-center justify-center">
          {isRunning && (
            <Circle className="w-3 h-3 text-muted-foreground/70" aria-hidden />
          )}
          {isSuccess && (
            <Check className={cn(
              "w-3 h-3 text-emerald-500 transition-all duration-200",
              justCompleted && "scale-125"
            )} />
          )}
          {isError && (
            <AlertCircle className="w-3 h-3 text-destructive" />
          )}
          {step.status === 'pending' && (
            <Circle className="w-2 h-2 text-muted-foreground/30" />
          )}
        </div>
        
        {/* Step Label */}
        <span
          className={cn(
            'text-xs truncate flex-1',
            isRunning && REASONING_STREAM_SHIMMER_CLASS,
            isSuccess && 'text-muted-foreground/60',
            isError && 'text-destructive/80',
            step.status === 'pending' && 'text-muted-foreground/30',
          )}
        >
          {step.label}
        </span>
        {isRunning && liveStepSec != null ? (
          <span className="text-[10px] tabular-nums text-muted-foreground/80 shrink-0" lang="en">
            {formatThoughtDuration(liveStepSec)}
          </span>
        ) : null}
        
        {/* Tool Badge */}
        {step.toolName && (
          <span className={cn(
            "text-[9px] px-1.5 py-0.5 rounded-full font-mono",
            isRunning ? "bg-primary/10 text-primary" : "bg-muted/50 text-muted-foreground/50"
          )}>
            {step.toolName}
          </span>
        )}
        
        {/* Step Duration */}
        {step.durationMs && step.durationMs > 0 && (
          <span className="text-[10px] text-muted-foreground/30 tabular-nums">
            {(step.durationMs / 1000).toFixed(1)}s
          </span>
        )}
      </div>
      
      {/* Expanded Details */}
      {isExpanded && hasToolInfo && (
        <div className="ml-7 mt-1 mb-2 p-2 rounded bg-muted/20 border border-border/30 text-[11px] space-y-1">
          {step.detail && (
            <div className="text-muted-foreground/70">{step.detail}</div>
          )}
          {step.toolOutput && (
            <div className="font-mono text-[10px] text-muted-foreground/50 max-h-20 overflow-auto whitespace-pre-wrap break-all">
              {step.toolOutput.length > 200 
                ? step.toolOutput.slice(0, 200) + '...' 
                : step.toolOutput}
            </div>
          )}
        </div>
      )}
    </div>
  );
});

// ============================================
// 4. Skeleton components
// ============================================
const TaskCardSkeleton = memo(function TaskCardSkeleton({ index }: { index: number }) {
  return (
    <div 
      className="rounded-lg border border-border/30 bg-muted/10 p-3 animate-pulse"
      style={{ 
        animationDelay: `${index * 100}ms`,
        animationFillMode: 'both'
      }}
    >
      <div className="flex items-center gap-3">
        <Skeleton className="w-6 h-6 rounded-full" />
        <div className="flex-1 space-y-2">
          <Skeleton className="h-4 w-3/4" />
          <Skeleton className="h-3 w-1/2" />
        </div>
        <Skeleton className="w-4 h-4" />
      </div>
    </div>
  );
});

const TaskPlanSkeleton = memo(function TaskPlanSkeleton() {
  const { t } = useLanguage();
  
  return (
    <div className="py-2 animate-fade-in">
      <div className="flex items-center gap-2 mb-3">
        <div className="relative">
          <Sparkles className="w-4 h-4 text-primary animate-pulse" />
          <div className="absolute inset-0 bg-primary/20 rounded-full animate-ping" />
        </div>
        <span className="text-xs font-medium text-muted-foreground">
          {t.tasks.planning}
        </span>
        <div className="flex-1 h-1 bg-muted/30 rounded-full overflow-hidden">
          <div 
            className="h-full bg-primary/50 rounded-full"
            style={{ 
              width: '30%',
              background: 'linear-gradient(90deg, hsl(var(--primary)/0.3) 0%, hsl(var(--primary)/0.6) 50%, hsl(var(--primary)/0.3) 100%)',
              backgroundSize: '200% 100%',
              animation: 'shimmer 2s linear infinite',
            }}
          />
        </div>
      </div>
      <div className="space-y-2">
        <TaskCardSkeleton index={0} />
        <TaskCardSkeleton index={1} />
      </div>
    </div>
  );
});

// ============================================
// 5. TaskListPanel - task list only (status bar + X of Y Done + task rows)
// ============================================
interface TaskListPanelProps {
  plan?: TaskPlan | null;
  isLoading?: boolean;
  /** Task titles to hide */
  excludeTaskTitles?: string[];
  /** Thought duration in seconds */
  thoughtDurationSeconds?: number;
}

export const TaskListPanel = memo(function TaskListPanel({
  plan,
  isLoading,
  excludeTaskTitles,
  thoughtDurationSeconds,
}: TaskListPanelProps) {
  const { t } = useLanguage();
  const labels = useMemo<TaskLabels>(() => ({
    executing: t.tasks.executing,
    executingTask: t.tasks.executingTask,
    completed: t.tasks.completed,
    failed: t.tasks.failed,
    pending: t.tasks.pending,
    expand: t.tasks.expand,
    collapse: t.tasks.collapse,
    taskOverview: t.tasks.overview,
    taskListTitle: t.reasoning.taskList,
    progressDone: t.tasks.progressDone,
  }), [t.tasks, t.reasoning.taskList]);

  const filteredTasks = useMemo(() => {
    if (!plan?.tasks) return [];
    if (!excludeTaskTitles?.length) return plan.tasks;
    return plan.tasks.filter((task) => !excludeTaskTitles.includes(task.title));
  }, [plan?.tasks, excludeTaskTitles]);

  if (isLoading || !plan) {
    return <TaskPlanSkeleton />;
  }
  if (filteredTasks.length === 0) return null;

  return (
    <div className="animate-fade-in rounded-lg border border-border/40 p-3">
      {thoughtDurationSeconds !== undefined && thoughtDurationSeconds > 0 && (
        <div className="text-xs text-muted-foreground/70 mb-2" lang="en">
          {formatThoughtDuration(thoughtDurationSeconds)}
        </div>
      )}
      <TaskOverview tasks={filteredTasks} labels={labels} />
    </div>
  );
});

// ============================================
// 6. TaskExecutionFlow - flattened steps + result/error (Cursor-style)
// ============================================
interface TaskExecutionFlowProps {
  plan?: TaskPlan | null;
  /** Task titles to hide */
  excludeTaskTitles?: string[];
}

export const TaskExecutionFlow = memo(function TaskExecutionFlow({
  plan,
  excludeTaskTitles,
}: TaskExecutionFlowProps) {
  const { t } = useLanguage();
  const labels = useMemo<TaskLabels>(() => ({
    executing: t.tasks.executing,
    executingTask: t.tasks.executingTask,
    completed: t.tasks.completed,
    failed: t.tasks.failed,
    pending: t.tasks.pending,
    expand: t.tasks.expand,
    collapse: t.tasks.collapse,
    taskOverview: t.tasks.overview,
    taskListTitle: t.reasoning.taskList,
    progressDone: t.tasks.progressDone,
  }), [t.tasks, t.reasoning.taskList]);

  const flattenedItems = useMemo(() => {
    if (!plan?.tasks) return [];
    const tasks = excludeTaskTitles?.length
      ? plan.tasks.filter((task) => !excludeTaskTitles.includes(task.title))
      : plan.tasks;
    const items: Array<{ type: 'step'; taskTitle: string; step: TaskStep; stepIndex: number } | { type: 'result'; taskTitle: string; result: string; error?: string }> = [];
    for (const task of tasks) {
      const filteredSteps = (task.steps || []).filter((s) => !shouldFilterStep(s));
      for (let i = 0; i < filteredSteps.length; i++) {
        items.push({ type: 'step', taskTitle: task.title, step: filteredSteps[i], stepIndex: i });
      }
      const resultText = normalizeMultilineText(task.result);
      const errorText = normalizeMultilineText(task.error);
      if (resultText || errorText) {
        items.push({ type: 'result', taskTitle: task.title, result: resultText, error: errorText || undefined });
      }
    }
    return items;
  }, [plan?.tasks, excludeTaskTitles]);

  if (!plan || flattenedItems.length === 0) return null;

  return (
    <div className="animate-fade-in rounded-lg border border-border/40 p-3 space-y-2">
      {flattenedItems.map((item, idx) =>
        item.type === 'step' ? (
          <div key={`step-${item.taskTitle}-${item.step.id ?? idx}`} className="flex items-start gap-2">
            <span className="text-[10px] text-muted-foreground/60 shrink-0 mt-1.5 truncate max-w-[80px]">
              {item.taskTitle}
            </span>
            <div className="flex-1 min-w-0">
              <StepItem step={item.step} index={item.stepIndex} />
            </div>
          </div>
        ) : (
          <div key={`result-${item.taskTitle}-${idx}`} className="ml-4 space-y-1">
            <span className="text-[10px] text-muted-foreground/60">{item.taskTitle}</span>
            {item.result && (
              <div className="p-2 rounded bg-muted/30 text-sm text-muted-foreground whitespace-pre-wrap">
                {item.result}
              </div>
            )}
            {item.error && (
              <div className="p-2 rounded bg-destructive/10 text-xs text-destructive whitespace-pre-wrap">
                {item.error}
              </div>
            )}
          </div>
        )
      )}
    </div>
  );
});

