/**
 * @vitest-environment jsdom
 *
 * Verifies that useModelLimits normalizes the /api/models payload (snake_case
 * → camelCase) and falls back to sensible defaults for malformed entries.
 */
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { renderHook, waitFor } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import React from 'react';
import {
  useModelLimits,
  DEFAULT_CONTEXT_WINDOW,
  DEFAULT_MAX_OUTPUT_TOKENS,
} from './useModelLimits';

function wrapper(client: QueryClient) {
  return ({ children }: { children: React.ReactNode }) =>
    React.createElement(QueryClientProvider, { client }, children);
}

describe('useModelLimits', () => {
  let originalFetch: typeof fetch;
  beforeEach(() => {
    originalFetch = globalThis.fetch;
  });
  afterEach(() => {
    globalThis.fetch = originalFetch;
    vi.restoreAllMocks();
  });

  it('maps snake_case fields to camelCase', async () => {
    globalThis.fetch = vi.fn(async () =>
      new Response(
        JSON.stringify({
          models: [
            {
              id: 'anthropic/claude-sonnet-4',
              name: 'Claude Sonnet 4',
              provider: 'anthropic',
              context_window: 200000,
              max_output_tokens: 8192,
            },
          ],
        }),
        { status: 200, headers: { 'Content-Type': 'application/json' } },
      ),
    ) as unknown as typeof fetch;
    const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
    const { result } = renderHook(() => useModelLimits(), { wrapper: wrapper(client) });
    await waitFor(() => expect(result.current.isLoading).toBe(false));
    expect(result.current.models).toHaveLength(1);
    expect(result.current.models[0]).toEqual({
      id: 'anthropic/claude-sonnet-4',
      name: 'Claude Sonnet 4',
      provider: 'anthropic',
      contextWindow: 200000,
      maxOutputTokens: 8192,
    });
    expect(result.current.getContextWindow('anthropic/claude-sonnet-4')).toBe(200000);
  });

  it('falls back to defaults when fields are missing or invalid', async () => {
    globalThis.fetch = vi.fn(async () =>
      new Response(
        JSON.stringify({
          models: [
            { id: 'x/y', name: 'y', provider: 'x' },
            { id: 'a/b', name: 'b', provider: 'a', context_window: 0, max_output_tokens: -1 },
          ],
        }),
        { status: 200, headers: { 'Content-Type': 'application/json' } },
      ),
    ) as unknown as typeof fetch;
    const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
    const { result } = renderHook(() => useModelLimits(), { wrapper: wrapper(client) });
    await waitFor(() => expect(result.current.isLoading).toBe(false));
    expect(result.current.models[0].contextWindow).toBe(DEFAULT_CONTEXT_WINDOW);
    expect(result.current.models[0].maxOutputTokens).toBe(DEFAULT_MAX_OUTPUT_TOKENS);
    expect(result.current.models[1].contextWindow).toBe(DEFAULT_CONTEXT_WINDOW);
    expect(result.current.models[1].maxOutputTokens).toBe(DEFAULT_MAX_OUTPUT_TOKENS);
    expect(result.current.getContextWindow('unknown/model')).toBe(DEFAULT_CONTEXT_WINDOW);
    expect(result.current.getContextWindow(null)).toBe(DEFAULT_CONTEXT_WINDOW);
  });
});
