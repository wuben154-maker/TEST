"""Per-tool SSE result renderer dispatch.

This module keeps :mod:`app.sse.tool_result_humanizer` free of any tool- or
subagent-specific knowledge. Subagents that want a custom rendering for their
tool outputs register a renderer here at import time; all other tools fall
back to the generic humanizer.

Usage from a subagent tool package::

    # subagents/official/web_security/tools/result_renderer.py
    from app.sse.tool_result_renderers import register_renderer

    @register_renderer("detect_web_attack")
    def render_detect_web_attack(data: dict) -> str:
        ...

The subagent's ``tools/__init__.py`` (or any module imported during tool
assembly) should import ``result_renderer`` for its side effects so the
registration happens before the first SSE event is emitted.

Invariants:

- Never raises. Any renderer exception or malformed payload falls through to
  :func:`humanize_tool_output`.
- Renderers receive **already-parsed** dicts; string handling / JSON parsing
  lives in one place (this module).
- The dispatcher does not mutate state; it is safe to call concurrently.
"""

from __future__ import annotations

import json
from typing import Any, Callable

from app.sse.tool_result_humanizer import humanize_tool_output

Renderer = Callable[[dict[str, Any]], str]

_RENDERERS: dict[str, Renderer] = {}


def register_renderer(tool_name: str) -> Callable[[Renderer], Renderer]:
    """Register ``fn`` as the renderer for ``tool_name`` (decorator form).

    Last registration wins, which makes tests easy to isolate with
    monkeypatching.
    """

    def _decorator(fn: Renderer) -> Renderer:
        _RENDERERS[tool_name] = fn
        return fn

    return _decorator


def get_renderer(tool_name: str) -> Renderer | None:
    """Return the renderer registered for ``tool_name`` (or ``None``)."""
    return _RENDERERS.get(tool_name)


def render_tool_result(tool_name: str, raw: str) -> str:
    """Render ``raw`` for SSE ``toolOutput`` emission.

    Dispatch order:

    1. If ``tool_name`` has a registered renderer AND ``raw`` is a JSON
       object literal, parse it and invoke the renderer. On success return
       its output.
    2. Otherwise — or on any failure — return
       :func:`humanize_tool_output(raw) <humanize_tool_output>`.
    """
    fn = _RENDERERS.get(tool_name)
    if fn and isinstance(raw, str) and raw:
        stripped = raw.strip()
        if stripped.startswith("{"):
            try:
                parsed = json.loads(stripped)
            except (ValueError, TypeError):
                parsed = None
            if isinstance(parsed, dict):
                try:
                    rendered = fn(parsed)
                except Exception:  # noqa: BLE001 — never break the stream
                    rendered = ""
                if rendered:
                    return rendered
    return humanize_tool_output(raw)

