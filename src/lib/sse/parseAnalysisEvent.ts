/**
 * L2: narrow SSE JSON payload to ThinkingEvent (trust backend + envelope).
 */
import type { ThinkingEvent } from '@/types/analysis';

export function parseAnalysisEvent(raw: unknown): ThinkingEvent {
  return raw as ThinkingEvent;
}
