/**
 * L1: decode fetch ReadableStream chunks into JSON objects from SSE `data:` lines.
 */

import { logger } from "@/lib/logger";

export type ReadSseJsonLinesOptions = {
  /** Return true to stop reading before the next `reader.read()` (e.g. request superseded). */
  shouldAbort?: () => boolean;
  /** Invoked after each `reader.read()` completes, including when data is only a partial line. */
  onRawChunk?: () => void;
};

/**
 * Yields one parsed JSON value per complete `data: ` line (same semantics as legacy hooks).
 */
export async function* readSseJsonLines(
  reader: ReadableStreamDefaultReader<Uint8Array>,
  decoder: TextDecoder,
  options?: ReadSseJsonLinesOptions,
): AsyncGenerator<unknown, void, undefined> {
  let buffer = '';
  while (true) {
    if (options?.shouldAbort?.()) {
      // Superseded request or component teardown: release the HTTP/SSE reader so the
      // browser tears down the old Response.body promptly instead of leaving a stray
      // readable alive alongside the next request's stream (same tab).
      try {
        await reader.cancel();
      } catch {
        /* ignore cancel failures */
      }
      break;
    }
    const { done, value } = await reader.read();
    options?.onRawChunk?.();
    if (done) {
      break;
    }
    buffer += decoder.decode(value, { stream: true });
    const lines = buffer.split('\n');
    buffer = lines.pop() || '';
    for (const line of lines) {
      if (!line.startsWith('data: ')) {
        continue;
      }
      try {
        yield JSON.parse(line.slice(6)) as unknown;
      } catch {
        logger.warn("sse_json_parse_error", { line: line.slice(0, 200) });
      }
    }
  }
}
