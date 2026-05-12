import { useEffect, useState } from 'react';

/** Elapsed seconds from `startMs` while `active`, updated on a short interval for UI. */
export function useLiveElapsedSeconds(startMs: number | undefined, active: boolean): number | undefined {
  const [tick, setTick] = useState(0);
  useEffect(() => {
    if (!active || startMs == null) return;
    const id = window.setInterval(() => setTick((n) => n + 1), 250);
    return () => window.clearInterval(id);
  }, [active, startMs]);
  if (!active || startMs == null) return undefined;
  void tick;
  return Math.max(0, (Date.now() - startMs) / 1000);
}
