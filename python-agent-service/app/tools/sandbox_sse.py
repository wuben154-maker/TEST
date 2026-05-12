"""Sandbox SSE emitter — ContextVar-based mechanism for pushing real-time
sandbox output into the current request's SSE stream.

Usage (request layer, e.g. stream_deep_analysis in main.py):
    async def _emitter(event: dict) -> None:
        await queue.put(event)
    set_sse_emitter(_emitter)
    task = asyncio.create_task(producer())   # task inherits the context

Usage (tool layer, e.g. sandbox_tools.py):
    await emit_sandbox_output(sandbox_id, "sandbox_run", "stdout", line, seq)
"""

from __future__ import annotations

import structlog
from contextvars import ContextVar
from typing import Awaitable, Callable

logger = structlog.get_logger(__name__)

# Callable registered per-request by stream_deep_analysis.
# None when the tool is not running inside a streaming request context.
_SseEmitterType = Callable[[dict], Awaitable[None]] | None

_sse_emitter: ContextVar[_SseEmitterType] = ContextVar(
    "sandbox_sse_emitter", default=None
)


def set_sse_emitter(
    fn: Callable[[dict], Awaitable[None]],
) -> None:
    """Register the SSE send function for the current async context.

    Must be called before asyncio.create_task() so the producer task
    inherits the updated context.
    """
    _sse_emitter.set(fn)


def clear_sse_emitter() -> None:
    """Remove the SSE emitter from the current context (e.g. after request ends)."""
    _sse_emitter.set(None)


async def emit_sandbox_output(
    sandbox_id: str,
    tool_name: str,
    stream: str,
    line: str,
    seq: int,
) -> None:
    """Push a sandbox_output SSE event if an emitter is registered.

    Silently skips when no emitter is set (non-streaming context or missing
    E2B key). Captures and logs emit failures so sandbox execution continues.
    """
    emitter = _sse_emitter.get()
    if emitter is None:
        return
    try:
        await emitter(
            {
                "type": "sandbox_output",
                "data": {
                    "sandbox_id": sandbox_id,
                    "tool_name": tool_name,
                    "stream": stream,
                    "line": line,
                    "seq": seq,
                },
            }
        )
    except Exception:
        logger.warning(
            "sandbox_output_emit_failed",
            sandbox_id=sandbox_id,
            tool_name=tool_name,
            seq=seq,
        )
