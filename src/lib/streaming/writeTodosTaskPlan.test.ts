import { describe, expect, it } from 'vitest';
import type { ThinkingEvent } from '@/types/analysis';
import { buildTaskPlanFromWriteTodosToolCall } from './writeTodosTaskPlan';

describe('buildTaskPlanFromWriteTodosToolCall', () => {
  it('returns null for non write_todos', () => {
    const ev = { type: 'tool_call', id: 'x', toolName: 'read_file', toolInput: {} } as ThinkingEvent;
    expect(buildTaskPlanFromWriteTodosToolCall(ev, (i) => String(i))).toBeNull();
  });

  it('builds plan with namespaced ids', () => {
    const ev = {
      type: 'tool_call',
      id: 'wt',
      toolName: 'write_todos',
      toolInput: {
        todos: [
          { content: 'A', status: 'pending' },
          { content: 'B', status: 'in_progress' },
          { content: 'C', status: 'completed' },
        ],
      },
    } as ThinkingEvent;
    const plan = buildTaskPlanFromWriteTodosToolCall(ev, (i) => `main:todo:ns:${i}`);
    expect(plan).not.toBeNull();
    expect(plan!.tasks.map((t) => t.id)).toEqual(['main:todo:ns:0', 'main:todo:ns:1', 'main:todo:ns:2']);
    expect(plan!.tasks[0].status).toBe('pending');
    expect(plan!.tasks[1].status).toBe('running');
    expect(plan!.tasks[2].status).toBe('success');
    expect(plan!.workspaceTitle).toBe('A');
  });

  it('folds Workspace in todo content for task titles', () => {
    const ev = {
      type: 'tool_call',
      id: 'wt',
      toolName: 'write_todos',
      toolInput: {
        todos: [{ content: '分析 Workspace/shell.php', status: 'pending' }],
      },
    } as ThinkingEvent;
    const plan = buildTaskPlanFromWriteTodosToolCall(ev, (i) => String(i));
    expect(plan!.tasks[0].title).toBe('分析 workspace/shell.php');
    expect(plan!.workspaceTitle).toBe('分析 workspace/shell.php');
  });
});
