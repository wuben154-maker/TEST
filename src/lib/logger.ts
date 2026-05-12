/**
 * Lightweight structured logger facade — zero dependencies.
 *
 * Production: only warn + error are emitted.
 * Development: all levels (debug/info/warn/error).
 *
 * Event naming follows the same snake_case convention as the Python backend
 * (see AGENT.md §7).
 */

export type LogLevel = "debug" | "info" | "warn" | "error";

export interface LogEntry {
  timestamp: string;
  level: LogLevel;
  event: string;
  [key: string]: unknown;
}

export type LogSink = (entry: LogEntry) => void;

const LEVEL_ORDER: Record<LogLevel, number> = {
  debug: 0,
  info: 1,
  warn: 2,
  error: 3,
};

const CONSOLE_METHOD: Record<LogLevel, "debug" | "info" | "warn" | "error"> = {
  debug: "debug",
  info: "info",
  warn: "warn",
  error: "error",
};

function safeStringify(value: unknown): string {
  const seen = new WeakSet();
  return JSON.stringify(value, (_key, val) => {
    if (typeof val === "object" && val !== null) {
      if (seen.has(val)) return "[Circular]";
      seen.add(val);
    }
    if (val instanceof Error) {
      return { message: val.message, stack: val.stack };
    }
    return val;
  });
}

class LoggerImpl {
  private threshold: number;
  private sinks: LogSink[] = [];

  constructor(level: LogLevel) {
    this.threshold = LEVEL_ORDER[level];
  }

  setLevel(level: LogLevel): void {
    this.threshold = LEVEL_ORDER[level];
  }

  addSink(sink: LogSink): void {
    this.sinks.push(sink);
  }

  debug(event: string, fields?: Record<string, unknown>): void {
    this.emit("debug", event, fields);
  }

  info(event: string, fields?: Record<string, unknown>): void {
    this.emit("info", event, fields);
  }

  warn(event: string, fields?: Record<string, unknown>): void {
    this.emit("warn", event, fields);
  }

  error(event: string, fields?: Record<string, unknown>): void {
    this.emit("error", event, fields);
  }

  private emit(level: LogLevel, event: string, fields?: Record<string, unknown>): void {
    if (LEVEL_ORDER[level] < this.threshold) return;

    const entry: LogEntry = {
      timestamp: new Date().toISOString(),
      level,
      event,
      ...fields,
    };

    // eslint-disable-next-line no-console
    console[CONSOLE_METHOD[level]](safeStringify(entry));

    for (const sink of this.sinks) {
      try {
        sink(entry);
      } catch {
        // never let a broken sink crash the app
      }
    }
  }
}

const defaultLevel: LogLevel =
  typeof import.meta !== "undefined" && import.meta.env?.DEV ? "debug" : "warn";

export const logger = new LoggerImpl(defaultLevel);
