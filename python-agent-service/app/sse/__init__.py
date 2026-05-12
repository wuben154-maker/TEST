"""SSE wire format, envelopes, and tool presentation metadata.

Eager-importing ``envelope`` here caused a circular import
(envelope → parsers → … → envelope). Lazy-export those symbols so
``from app.sse.tool_presentation import …`` stays safe.
"""

from __future__ import annotations

from app.sse.framing import create_sse_message
from app.sse.tool_presentation import attach_tool_presentation

__all__ = [
    "apply_sse_envelope",
    "attach_tool_presentation",
    "create_sse_message",
    "tag_merged_subagent_sse",
]


def __getattr__(name: str):
    if name == "apply_sse_envelope":
        from app.sse.envelope import apply_sse_envelope

        return apply_sse_envelope
    if name == "tag_merged_subagent_sse":
        from app.sse.envelope import tag_merged_subagent_sse

        return tag_merged_subagent_sse
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
