import { describe, expect, it } from 'vitest';
import type { TaskPlan } from '@/types/analysis';
import { scrubTaskPlanPathsForDisplay, scrubVirtualPathsForDisplay } from './scrubVirtualPathsForDisplay';

describe('scrubVirtualPathsForDisplay', () => {
  it('folds Pascal Workspace in absolute-style segments', () => {
    expect(scrubVirtualPathsForDisplay('/Workspace/a/b')).toBe('/workspace/a/b');
  });

  it('folds Workspace after word boundary (e.g. Chinese task prefix)', () => {
    expect(scrubVirtualPathsForDisplay('分析 Workspace/a558969bbd4f_indrajith-2.0.txt.php')).toBe(
      '分析 workspace/a558969bbd4f_indrajith-2.0.txt.php',
    );
  });

  it('does not mangle MyWorkspace/', () => {
    expect(scrubVirtualPathsForDisplay('dir/MyWorkspace/file')).toBe('dir/MyWorkspace/file');
  });

  it('redacts Windows host paths to workspace basename', () => {
    const raw =
      'Analyze binary at D:\\code\\cursor\\demo\\python-agent-service\\uploads\\u_1\\p_2\\sample.exe';
    const out = scrubVirtualPathsForDisplay(raw);
    expect(out).toContain('/workspace/sample.exe');
    expect(out).not.toContain('D:');
    expect(out).not.toContain('uploads\\u_');
  });

describe('scrubTaskPlanPathsForDisplay', () => {
  it('normalizes titles, workspaceTitle, description, result, error', () => {
    const plan: TaskPlan = {
      id: 'p',
      isSingleTask: false,
      totalDurationMs: 0,
      status: 'pending',
      createdAt: '',
      workspaceTitle: 'Scope /Workspace/x',
      tasks: [
        {
          id: '1',
          title: '分析 Workspace/a.php',
          description: 'Workspace/b',
          taskType: 'security',
          priority: 1,
          status: 'pending',
          durationMs: 0,
          steps: [],
          result: 'read /Workspace/c',
          error: 'Workspace/d',
        },
      ],
    };
    const s = scrubTaskPlanPathsForDisplay(plan);
    expect(s.workspaceTitle).toBe('Scope /workspace/x');
    expect(s.tasks[0].title).toBe('分析 workspace/a.php');
    expect(s.tasks[0].description).toBe('workspace/b');
    expect(s.tasks[0].result).toBe('read /workspace/c');
    expect(s.tasks[0].error).toBe('workspace/d');
  });
});
