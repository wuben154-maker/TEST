import { describe, expect, it, vi, beforeEach, afterEach } from 'vitest';
import { renderHook, act } from '@testing-library/react';
import { useLiveElapsedSeconds } from '@/lib/liveElapsedSeconds';

describe('useLiveElapsedSeconds', () => {
  beforeEach(() => {
    vi.useFakeTimers();
  });
  afterEach(() => {
    vi.useRealTimers();
  });

  it('returns undefined when inactive', () => {
    const { result } = renderHook(() => useLiveElapsedSeconds(1000, false));
    expect(result.current).toBeUndefined();
  });

  it('returns elapsed seconds while active', () => {
    const start = 10_000;
    vi.setSystemTime(start);
    const { result } = renderHook(() => useLiveElapsedSeconds(start, true));
    expect(result.current).toBe(0);
    vi.setSystemTime(start + 1000);
    act(() => {
      vi.advanceTimersByTime(300);
    });
    expect((result.current ?? 0) >= 0.9).toBe(true);
  });
});
