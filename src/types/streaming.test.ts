import { describe, expect, it } from 'vitest';
import { createEmptyStreamingState } from './streaming';

describe('streaming state', () => {
  it('createEmptyStreamingState includes timeline as empty array', () => {
    const state = createEmptyStreamingState();
    expect(state).toHaveProperty('timeline');
    expect(Array.isArray(state.timeline)).toBe(true);
    expect(state.timeline).toHaveLength(0);
  });
});
