import { describe, it, expect } from 'vitest';
import { render, screen } from '@testing-library/react';
import { LanguageProvider } from '@/contexts/LanguageContext';
import type { AnalysisResultStats } from '@/types/project';
import { TaskStatsBar } from './TaskStatsBar';

function renderWithZh(ui: React.ReactElement) {
  return render(<LanguageProvider initialLanguage="zh">{ui}</LanguageProvider>);
}

describe('TaskStatsBar', () => {
  describe('visibility (U-05)', () => {
    it('renders null when stats is undefined and status is done', () => {
      const { container } = renderWithZh(<TaskStatsBar status="done" />);
      expect(container.firstChild).toBeNull();
    });

    it('renders null when stats.taskKind is undefined', () => {
      const { container } = renderWithZh(
        <TaskStatsBar stats={{ durationMs: 1234 }} status="done" />,
      );
      expect(container.firstChild).toBeNull();
    });

    it('renders null for security taskKind without security payload', () => {
      const { container } = renderWithZh(
        <TaskStatsBar stats={{ taskKind: 'security' }} status="done" />,
      );
      expect(container.firstChild).toBeNull();
    });
  });

  describe('running state (U-06)', () => {
    it('renders analyzing chip with sourceLabel', () => {
      renderWithZh(
        <TaskStatsBar status="running" sourceLabel="上传" />,
      );
      expect(screen.getByTestId('task-stats-bar')).toBeTruthy();
      expect(screen.getByText('分析中')).toBeTruthy();
      expect(screen.getByText('上传')).toBeTruthy();
    });

    it('renders analyzing chip without sourceLabel when absent', () => {
      renderWithZh(<TaskStatsBar status="running" />);
      expect(screen.getByText('分析中')).toBeTruthy();
    });
  });

  describe('security profile (U-01, U-02, U-04)', () => {
    const fullSecurity: AnalysisResultStats = {
      taskKind: 'security',
      security: {
        severity: 'high',
        riskScore: 82,
        actionable: { total: 3, critical: 0, high: 2, medium: 1 },
        threatClasses: ['web_shell', 'sqli', 'xss'],
        validation: ['static', 'yara', 'sandbox'],
      },
    };

    it('renders 5 chips in order for a full security payload', () => {
      renderWithZh(<TaskStatsBar stats={fullSecurity} status="done" />);
      const bar = screen.getByTestId('task-stats-bar');
      expect(bar).toBeTruthy();
      // severity
      expect(screen.getByText('高危')).toBeTruthy();
      // risk score (zh label = 风险)
      expect(screen.getByText('82')).toBeTruthy();
      // actionable breakdown
      expect(screen.getByText('3·2H/1M')).toBeTruthy();
      // threat classes: top 2 joined by ' · ' + "+1" suffix, underscores → space
      expect(screen.getByText('web shell · sqli +1')).toBeTruthy();
      // validation trail (zh labels)
      expect(screen.getByText('静态 · YARA · 沙箱')).toBeTruthy();
    });

    it('applies destructive colouring for critical severity chip', () => {
      renderWithZh(
        <TaskStatsBar
          stats={{ taskKind: 'security', security: { severity: 'critical' } }}
          status="done"
        />,
      );
      const sevText = screen.getByText('严重');
      // Chip outer wrapper is the grandparent (value span → outer chip span).
      const chip = sevText.parentElement;
      expect(chip?.className).toMatch(/border-destructive/);
    });

    it('applies risk variant only when score >= 70', () => {
      const { rerender } = renderWithZh(
        <TaskStatsBar
          stats={{
            taskKind: 'security',
            security: { severity: 'info', riskScore: 40 },
          }}
          status="done"
        />,
      );
      const low = screen.getByText('40').parentElement;
      expect(low?.className).not.toMatch(/red-/);

      rerender(
        <LanguageProvider initialLanguage="zh">
          <TaskStatsBar
            stats={{
              taskKind: 'security',
              security: { severity: 'info', riskScore: 90 },
            }}
            status="done"
          />
        </LanguageProvider>,
      );
      const high = screen.getByText('90').parentElement;
      expect(high?.className).toMatch(/red-/);
    });

    it('renders only 2 chips when only severity and riskScore are available', () => {
      renderWithZh(
        <TaskStatsBar
          stats={{
            taskKind: 'security',
            security: { severity: 'info', riskScore: 10 },
          }}
          status="done"
        />,
      );
      expect(screen.getByText('信息')).toBeTruthy();
      expect(screen.getByText('10')).toBeTruthy();
      // No actionable / threat / validation chip
      expect(screen.queryByText('待处置')).toBeNull();
      expect(screen.queryByText('威胁类型')).toBeNull();
      expect(screen.queryByText('验证')).toBeNull();
    });
  });

  describe('research profile (U-03)', () => {
    it('renders 5 chips in order for a full research payload', () => {
      renderWithZh(
        <TaskStatsBar
          stats={{
            taskKind: 'research',
            research: {
              keyFindings: 5,
              recommendations: 3,
              sources: 12,
              freshness: '<=30d',
              gaps: 2,
            },
          }}
          status="done"
        />,
      );
      expect(screen.getByTestId('task-stats-bar')).toBeTruthy();
      expect(screen.getByText('5')).toBeTruthy();
      expect(screen.getByText('3')).toBeTruthy();
      expect(screen.getByText('12')).toBeTruthy();
      expect(screen.getByText('≤30天')).toBeTruthy();
      expect(screen.getByText('2')).toBeTruthy();
    });

    it('hides individual chips for missing sub-fields', () => {
      renderWithZh(
        <TaskStatsBar
          stats={{
            taskKind: 'research',
            research: { keyFindings: 4, sources: 8 },
          }}
          status="done"
        />,
      );
      expect(screen.getByTestId('task-stats-bar')).toBeTruthy();
      expect(screen.getByText('4')).toBeTruthy();
      expect(screen.getByText('8')).toBeTruthy();
      expect(screen.queryByText('建议')).toBeNull();
      expect(screen.queryByText('新鲜度')).toBeNull();
      expect(screen.queryByText('知识缺口')).toBeNull();
    });
  });

  describe('no process-counter leakage (U-08)', () => {
    it('does not render technical row, session id, duration, tool calls, or blocks', () => {
      renderWithZh(
        <TaskStatsBar
          stats={{
            taskKind: 'security',
            security: { severity: 'high', riskScore: 50 },
            durationMs: 60000,
            toolCallCount: 10,
            sandboxRunCount: 3,
          }}
          status="done"
        />,
      );
      expect(screen.queryByTestId('task-stats-bar-technical')).toBeNull();
      // Duration, tool call, sandbox signals must NOT appear in the bar.
      const bar = screen.getByTestId('task-stats-bar');
      expect(bar.textContent).not.toContain('1m 0s');
      expect(bar.textContent).not.toContain('10');
      expect(bar.textContent).not.toContain('沙箱 3');
    });
  });

  describe('accessibility (U-A11y-03)', () => {
    it('sets aria-label on the stats bar container', () => {
      renderWithZh(
        <TaskStatsBar
          stats={{ taskKind: 'research', research: { keyFindings: 1 } }}
          status="done"
        />,
      );
      const bar = screen.getByTestId('task-stats-bar');
      expect(bar.getAttribute('aria-label')).toBe('任务统计摘要');
    });
  });
});
