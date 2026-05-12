/**
 * Remote log sink — batches warn/error entries and POSTs them
 * to the backend /api/client-errors endpoint.
 */

import type { LogEntry, LogSink } from "@/lib/logger";
import { getAuthToken } from "@/lib/api-client";
import { activeApiBaseUrl } from "@/lib/config";

export interface RemoteSinkOptions {
  endpoint: string;
  batchSize: number;
  flushIntervalMs: number;
  maxRetries: number;
}

const DEFAULTS: RemoteSinkOptions = {
  endpoint: "/api/client-errors",
  batchSize: 10,
  flushIntervalMs: 5_000,
  maxRetries: 1,
};

export function createRemoteSink(
  opts?: Partial<RemoteSinkOptions>,
): LogSink {
  const config = { ...DEFAULTS, ...opts };
  let buffer: LogEntry[] = [];
  let timer: ReturnType<typeof setInterval> | null = null;

  async function flush(): Promise<void> {
    if (buffer.length === 0) return;
    const batch = buffer.splice(0, config.batchSize);
    const url = `${activeApiBaseUrl}${config.endpoint}`;
    const headers: Record<string, string> = { "Content-Type": "application/json" };
    const token = getAuthToken();
    if (token) headers["Authorization"] = `Bearer ${token}`;

    const body = JSON.stringify({
      errors: batch.map((e) => ({
        timestamp: e.timestamp,
        level: e.level,
        event: e.event,
        extra: Object.fromEntries(
          Object.entries(e).filter(
            ([k]) => !["timestamp", "level", "event"].includes(k),
          ),
        ),
      })),
    });

    for (let attempt = 0; attempt <= config.maxRetries; attempt++) {
      try {
        const resp = await fetch(url, { method: "POST", headers, body });
        if (resp.ok || resp.status === 204) return;
        if (resp.status === 429 || resp.status >= 400) return;
      } catch {
        if (attempt === config.maxRetries) {
          // eslint-disable-next-line no-console
          console.warn("[remoteSink] flush failed, dropping batch");
        }
      }
    }
  }

  function startTimer(): void {
    if (timer) return;
    timer = setInterval(() => {
      flush();
    }, config.flushIntervalMs);
  }

  function sink(entry: LogEntry): void {
    if (entry.level !== "warn" && entry.level !== "error") return;
    if (typeof navigator !== "undefined" && !navigator.onLine) return;

    buffer.push(entry);
    startTimer();
    if (buffer.length >= config.batchSize) {
      flush();
    }
  }

  // Flush remaining on page unload
  if (typeof window !== "undefined") {
    window.addEventListener("visibilitychange", () => {
      if (document.visibilityState === "hidden") flush();
    });
    window.addEventListener("pagehide", () => flush());
  }

  return sink;
}
