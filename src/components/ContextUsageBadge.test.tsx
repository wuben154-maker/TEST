import type { ReactElement } from 'react';
import { render, screen } from '@testing-library/react';
import { describe, it, expect } from 'vitest';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { LanguageProvider } from '@/contexts/LanguageContext';
import { ContextUsageBadge } from '@/components/ContextUsageBadge';
import type { ContextUsageState } from '@/types/analysis';
import { MAIN_SUBAGENT_KEY } from '@/lib/contextUsage';

const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } });

function renderWithLang(ui: ReactElement) {
  return render(
    <QueryClientProvider client={queryClient}>
      <LanguageProvider>{ui}</LanguageProvider>
    </QueryClientProvider>,
  );
}

function state(overrides?: Partial<ContextUsageState>): ContextUsageState {
  return {
    latest: undefined,
    latestMain: undefined,
    latestSubagentByName: {},
    cumulative: { inputTokens: 0, outputTokens: 0, invocations: 0 },
    bySubagent: [],
    lastSummarizedAt: undefined,
    ...overrides,
  };
}

describe('ContextUsageBadge', () => {
  it('shows compact idle icon after context_summarized until next main invoke (Option A)', () => {
    renderWithLang(
      <ContextUsageBadge
        state={state({
          lastSummarizedAt: Date.now(),
          cumulative: { inputTokens: 50_000, outputTokens: 100, invocations: 1 },
          bySubagent: [
            {
              subagentName: MAIN_SUBAGENT_KEY,
              invocations: 1,
              inputTokens: 50_000,
              outputTokens: 100,
            },
          ],
        })}
        contextWindow={200_000}
      />,
    );
    const btn = screen.getByTestId('context-usage-badge');
    expect(btn.getAttribute('data-awaiting-measure')).toBe('true');
    expect(btn.getAttribute('data-severity')).toBe('idle');
    // Awaiting state uses icon SVG, not the dual-circle progress ring.
    expect(btn.querySelector('circle')).toBeNull();
  });

  it('renders nothing when no invocation has completed', () => {
    const { container } = renderWithLang(
      <ContextUsageBadge state={state()} contextWindow={200_000} />,
    );
    // Idle state hides the badge entirely (no data → no UI).
    expect(container.firstChild).toBeNull();
    expect(screen.queryByTestId('context-usage-badge')).toBeNull();
  });

  it('shows safe severity with a rounded percentage when usage is < 70%', () => {
    renderWithLang(
      <ContextUsageBadge
        state={state({
          latest: {
            invokeId: 'r1',
            modelId: 'anthropic/claude-sonnet-4',
            inputTokens: 100_000,
            outputTokens: 0,
            endedAt: Date.now(),
          },
          cumulative: { inputTokens: 100_000, outputTokens: 0, invocations: 1 },
          bySubagent: [
            {
              subagentName: MAIN_SUBAGENT_KEY,
              invocations: 1,
              inputTokens: 100_000,
              outputTokens: 0,
            },
          ],
        })}
        contextWindow={200_000}
      />,
    );
    const btn = screen.getByTestId('context-usage-badge');
    expect(btn.getAttribute('data-severity')).toBe('safe');
    expect(btn.getAttribute('data-pct')).toBe('50');
    // Minimal UI: trigger shows only the ring, no inline text. Percent lives
    // in aria-label / title for accessibility + tooltip.
    expect(btn.textContent).toBe('');
    expect(btn.getAttribute('aria-label') ?? '').toContain('50');
    expect(btn.getAttribute('title') ?? '').toContain('50');
  });

  it('shows warn severity at >=70%', () => {
    renderWithLang(
      <ContextUsageBadge
        state={state({
          latest: { invokeId: 'r1', inputTokens: 150_000, outputTokens: 0, endedAt: Date.now() },
          cumulative: { inputTokens: 150_000, outputTokens: 0, invocations: 1 },
          bySubagent: [],
        })}
        contextWindow={200_000}
      />,
    );
    expect(screen.getByTestId('context-usage-badge').getAttribute('data-severity')).toBe(
      'warn',
    );
  });

  it('shows critical severity at >=95% and pulses', () => {
    renderWithLang(
      <ContextUsageBadge
        state={state({
          latest: { invokeId: 'r1', inputTokens: 195_000, outputTokens: 0, endedAt: Date.now() },
          cumulative: { inputTokens: 195_000, outputTokens: 0, invocations: 1 },
          bySubagent: [],
        })}
        contextWindow={200_000}
      />,
    );
    const btn = screen.getByTestId('context-usage-badge');
    expect(btn.getAttribute('data-severity')).toBe('critical');
    expect(btn.className).toContain('animate-pulse');
  });

  it('renders the progress ring SVG with dashoffset proportional to usage', () => {
    renderWithLang(
      <ContextUsageBadge
        state={state({
          latest: { invokeId: 'r1', inputTokens: 50_000, outputTokens: 0, endedAt: Date.now() },
          cumulative: { inputTokens: 50_000, outputTokens: 0, invocations: 1 },
          bySubagent: [],
        })}
        contextWindow={200_000}
      />,
    );
    const btn = screen.getByTestId('context-usage-badge');
    const svg = btn.querySelector('svg');
    expect(svg).not.toBeNull();
    // Two circles: the track and the progress arc.
    const circles = svg!.querySelectorAll('circle');
    expect(circles.length).toBe(2);
    // 25% usage → dashoffset should equal 75% of the circumference.
    // Ring radius is 8 in the minimal-ring layout (see ContextUsageBadge).
    const circumference = 2 * Math.PI * 8;
    const expected = circumference * 0.75;
    const actual = parseFloat(
      circles[1].getAttribute('stroke-dashoffset') ?? '0',
    );
    expect(Math.abs(actual - expected)).toBeLessThan(0.01);
  });
});
