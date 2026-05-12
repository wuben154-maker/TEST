/**
 * React Query hook that fetches /api/models and exposes per-model context
 * window + max output tokens for the realtime context-usage indicator.
 *
 * The gateway model id (e.g. ``anthropic/claude-sonnet-4``) is the key that
 * matches ``llm_invoke_start.modelId`` emitted by the backend callback handler,
 * so callers should look up by the same id.
 */
import { useCallback } from 'react';
import { useQuery } from '@tanstack/react-query';
import { analysisEndpoints } from '@/lib/config';
import { getAuthToken, getClientTimezoneHeaders } from '@/lib/api-client';

export interface ModelLimit {
  id: string;
  name: string;
  provider: string;
  contextWindow: number;
  maxOutputTokens: number;
}

interface ApiModel {
  id: string;
  name: string;
  provider: string;
  context_window?: number;
  max_output_tokens?: number;
}

interface ApiResponse {
  models?: ApiModel[];
}

/** Fallback when the backend omits context_window (legacy config or error). */
export const DEFAULT_CONTEXT_WINDOW = 200_000;
export const DEFAULT_MAX_OUTPUT_TOKENS = 4096;

async function fetchModelLimits(signal?: AbortSignal): Promise<ModelLimit[]> {
  const headers: Record<string, string> = {
    ...getClientTimezoneHeaders(),
    'Content-Type': 'application/json',
  };
  const token = getAuthToken();
  if (token) headers['Authorization'] = `Bearer ${token}`;
  const res = await fetch(analysisEndpoints.models, { headers, signal });
  if (!res.ok) {
    throw new Error(`Failed to fetch /api/models: ${res.status}`);
  }
  const data = (await res.json()) as ApiResponse;
  const raw = Array.isArray(data.models) ? data.models : [];
  return raw.map((m) => ({
    id: m.id,
    name: m.name,
    provider: m.provider,
    contextWindow:
      typeof m.context_window === 'number' && m.context_window > 0
        ? m.context_window
        : DEFAULT_CONTEXT_WINDOW,
    maxOutputTokens:
      typeof m.max_output_tokens === 'number' && m.max_output_tokens > 0
        ? m.max_output_tokens
        : DEFAULT_MAX_OUTPUT_TOKENS,
  }));
}

/**
 * Fetch model limits with a 30-minute cache. Returns helpers for looking up a
 * model by its gateway id.
 *
 * Model catalog changes only when ``llm_gateway.yaml`` is redeployed, so a long
 * ``staleTime`` is fine and avoids refetching while the user chats.
 */
export function useModelLimits() {
  const query = useQuery({
    queryKey: ['llm-gateway', 'models'],
    queryFn: ({ signal }) => fetchModelLimits(signal),
    staleTime: 30 * 60 * 1000,
    gcTime: 60 * 60 * 1000,
    retry: 1,
  });

  const getLimit = useCallback(
    (modelId: string | undefined | null): ModelLimit | undefined => {
      if (!modelId) return undefined;
      return query.data?.find((m) => m.id === modelId);
    },
    [query.data],
  );

  const getContextWindow = useCallback(
    (modelId: string | undefined | null): number => {
      const lim = getLimit(modelId);
      return lim?.contextWindow ?? DEFAULT_CONTEXT_WINDOW;
    },
    [getLimit],
  );

  return {
    models: query.data ?? [],
    isLoading: query.isLoading,
    error: query.error,
    getLimit,
    getContextWindow,
  };
}
