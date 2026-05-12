import { describe, expect, it } from 'vitest';
import type { ProductTimelineRowKind } from './timelineProductRows';

describe('timelineProductRows model', () => {
  it('exports row kinds used by timeline reducers', () => {
    const kinds: ProductTimelineRowKind[] = [
      'text',
      'tool_line',
      'task_block',
      'user_input',
      'delegation_line',
    ];
    expect(kinds).toHaveLength(5);
  });
});
