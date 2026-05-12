import { describe, expect, it } from 'vitest';
import { readSseJsonLines } from './readSseJsonLines';

function streamFromChunks(chunks: string[]): ReadableStream<Uint8Array> {
  const enc = new TextEncoder();
  return new ReadableStream({
    start(controller) {
      for (const c of chunks) {
        controller.enqueue(enc.encode(c));
      }
      controller.close();
    },
  });
}

describe('readSseJsonLines', () => {
  it('parses complete lines from split chunks', async () => {
    const reader = streamFromChunks(['data: {"type":"step","id":"a"}\n\ndata: ', '{"type":"done","id":"d"}\n\n']).getReader();
    const dec = new TextDecoder();
    const out: unknown[] = [];
    for await (const x of readSseJsonLines(reader, dec)) {
      out.push(x);
    }
    expect(out).toEqual([{ type: 'step', id: 'a' }, { type: 'done', id: 'd' }]);
  });

  it('ignores non-data lines and invalid json', async () => {
    const reader = streamFromChunks(['\n', 'data: not-json\n', 'data: {"ok":true}\n']).getReader();
    const dec = new TextDecoder();
    const out: unknown[] = [];
    for await (const x of readSseJsonLines(reader, dec)) {
      out.push(x);
    }
    expect(out).toEqual([{ ok: true }]);
  });

  it('shouldAbort stops before next read', async () => {
    const enc = new TextEncoder();
    let reads = 0;
    const stream = new ReadableStream<Uint8Array>({
      pull(controller) {
        reads += 1;
        controller.enqueue(enc.encode(`data: {"n":${reads}}\n\n`));
        if (reads >= 5) controller.close();
      },
    });
    const reader = stream.getReader();
    const dec = new TextDecoder();
    let n = 0;
    for await (const x of readSseJsonLines(reader, dec, {
      shouldAbort: () => n >= 2,
    })) {
      void x;
      n += 1;
    }
    expect(n).toBe(2);
  });

  it('invokes onRawChunk after each read (including final done)', async () => {
    const reader = streamFromChunks(['da', 'ta: {"a":1}\n\n']).getReader();
    const dec = new TextDecoder();
    let chunks = 0;
    for await (const _ of readSseJsonLines(reader, dec, { onRawChunk: () => chunks++ })) {
      /* consume */
    }
    // Two payload chunks + one read with done=true
    expect(chunks).toBe(3);
  });
});
