/**
 * Shared write_todos tool_call -> TaskPlan payload (single vs multi-project id schemes).
 */
import { scrubVirtualPathsForDisplay } from '@/lib/scrubVirtualPathsForDisplay';
import type { PlannedTask, ThinkingEvent, TaskPlan } from '@/types/analysis';

const STATUS_MAP: Record<string, 'pending' | 'running' | 'success'> = {
  pending: 'pending',
  in_progress: 'running',
  completed: 'success',
};

type RawTodo = {
  id?: string | number;
  content?: string;
  task?: string;
  title?: string;
  status?: string;
};

export function buildPlannedTasksFromWriteTodosInput(
  toolInput: Record<string, unknown>,
  idForIndex: (idx: number) => string,
): PlannedTask[] | null {
  const rawTodos = (toolInput.todos ?? toolInput.tasks) as RawTodo[] | undefined;
  if (!Array.isArray(rawTodos) || rawTodos.length === 0) {
    return null;
  }
  return rawTodos.map((todo, idx) => {
    const taskText = scrubVirtualPathsForDisplay(
      String(todo.content ?? todo.task ?? todo.title ?? ''),
    );
    const rawStatus = todo.status ?? 'pending';
    const feStatus = STATUS_MAP[rawStatus] ?? 'pending';
    const stableId =
      todo.id !== undefined && todo.id !== null && String(todo.id).trim() !== ''
        ? String(todo.id)
        : idForIndex(idx);
    return {
      id: stableId,
      title: taskText,
      description: taskText,
      taskType: 'security' as const,
      priority: idx + 1,
      status: feStatus,
      durationMs: 0,
      steps: [],
    };
  });
}

export function buildTaskPlanFromWriteTodosToolCall(
  event: ThinkingEvent,
  idForIndex: (idx: number) => string,
): TaskPlan | null {
  if (event.type !== 'tool_call' || event.toolName !== 'write_todos' || !event.toolInput) {
    return null;
  }
  const planned = buildPlannedTasksFromWriteTodosInput(
    event.toolInput as Record<string, unknown>,
    idForIndex,
  );
  if (!planned) {
    return null;
  }
  const wsTitle = planned[0]?.title ?? '';
  return {
    id: 'task-plan',
    tasks: planned,
    isSingleTask: planned.length === 1,
    totalDurationMs: 0,
    status: planned.some((t) => t.status === 'running')
      ? 'running'
      : planned.every((t) => t.status === 'success')
        ? 'success'
        : 'pending',
    createdAt: '',
    ...(wsTitle ? { workspaceTitle: wsTitle } : {}),
  };
}
