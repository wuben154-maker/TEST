import { describe, expect, it } from 'vitest';
import { resolveStreamDisplayProjectId } from './resolveStreamDisplayProjectId';

describe('resolveStreamDisplayProjectId', () => {
  it('prefers current when it has a local abort', () => {
    expect(
      resolveStreamDisplayProjectId('a', ['a', 'b'], []),
    ).toBe('a');
  });

  it('when current is stale, uses sole abort owner', () => {
    expect(
      resolveStreamDisplayProjectId('a', ['b'], []),
    ).toBe('b');
  });

  it('when current matches analyzing, uses it', () => {
    expect(
      resolveStreamDisplayProjectId('a', [], ['a']),
    ).toBe('a');
  });

  it('when no abort and only analyzing ids, uses first', () => {
    expect(
      resolveStreamDisplayProjectId(null, [], ['x']),
    ).toBe('x');
  });
});
