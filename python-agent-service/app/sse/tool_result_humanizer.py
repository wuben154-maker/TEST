"""Humanize tool-result JSON payloads for the SSE ``toolOutput`` field.

Converts structured JSON produced by business tools (e.g. ``sandbox_run``,
``web_search``, ``extract_iocs``) into a plain-text rendering suitable for
displaying in the UI's ``<pre>`` block without any per-tool styling.

Design goals (see ``docs/Process/tool-result-humanization/design.md``):

- **Idempotent** — non-JSON input is returned unchanged; parse failures never
  raise.
- **Generic** — one set of rules covers all tools. No per-tool registry.
- **Lossless** — ``ToolMessage.content`` held in graph state (consumed by the
  LLM) is untouched; this layer transforms only the SSE event payload.

Truncation limits for content blocks and inline scalars are configurable via
``sse_tool_result_max_block_chars`` / ``sse_tool_result_max_scalar_chars`` in
:class:`app.config.settings.Settings` (defaults 2000 each).

Rules in short:

- Top-level must be ``dict`` or ``list``; otherwise return raw.
- In dicts, a truthy ``error`` field surfaces as the first line with an
  ``error:`` prefix.
- Keys listed in :data:`_CONTENT_KEYS` (``stdout``/``stderr``/``output``/...)
  whose values are non-empty strings render as trailing ``--- <key> ---``
  blocks, preserving newlines.
- All remaining non-empty scalar fields render as one ``key: value`` per line.
- Empty fields (``None`` / ``""`` / ``[]`` / ``{}``) are dropped.
- Nested dicts indent 2 spaces per level; object arrays render as numbered
  lists indented 2 spaces.
- Long scalar strings and content blocks are truncated with
  ``... [truncated]`` to avoid context-window style bloat in the UI.
"""

from __future__ import annotations

import json
from typing import Any, NamedTuple

_CONTENT_KEYS: tuple[str, ...] = (
    "stdout",
    "stderr",
    "output",
    "text",
    "content",
    "message",
    "body",
)

_MAX_DEPTH = 5
_TRUNCATED_SUFFIX = "\n... [truncated]"


class _Limits(NamedTuple):
    block: int
    scalar: int


def _resolve_limits() -> _Limits:
    try:
        from app.config.settings import get_settings

        s = get_settings()
        return _Limits(
            block=max(1, int(s.sse_tool_result_max_block_chars)),
            scalar=max(1, int(s.sse_tool_result_max_scalar_chars)),
        )
    except Exception:
        return _Limits(block=2000, scalar=2000)


def humanize_tool_output(raw: str) -> str:
    """Return a human-readable rendering of a tool-result payload.

    Non-JSON, JSON scalars, and top-level non-container JSON values are
    returned verbatim. Dict/list payloads are rendered per the rules in the
    module docstring.

    This function must never raise; on any unexpected error it returns
    ``raw`` unchanged so the UI still sees *some* content.
    """
    if not raw or not isinstance(raw, str):
        return raw

    stripped = raw.strip()
    if not stripped:
        return raw

    # Fast path: only attempt JSON parse if it looks like JSON.
    if stripped[0] not in "[{":
        return raw

    try:
        parsed = json.loads(stripped)
    except (ValueError, TypeError):
        return raw

    limits = _resolve_limits()
    try:
        if isinstance(parsed, dict):
            return _render_dict(parsed, depth=0, limits=limits)
        if isinstance(parsed, list):
            return _render_top_list(parsed, depth=0, limits=limits)
        # Top-level JSON scalar — unreachable via fast path but stay safe.
        return raw
    except Exception:  # noqa: BLE001 — never break the SSE stream
        return raw


def _render_dict(d: dict[str, Any], *, depth: int, limits: _Limits) -> str:
    """Render a dict as multi-line text.

    Returns ``""`` when no field survives the empty-value filter.
    """
    if depth >= _MAX_DEPTH:
        return "{...}"

    lines: list[str] = []
    content_blocks: list[str] = []

    err = d.get("error")
    if _is_non_empty_scalar(err):
        lines.append(f"error: {_render_scalar(err, limits)}")

    for key, value in d.items():
        if key == "error":
            continue

        if key in _CONTENT_KEYS and isinstance(value, str) and value:
            block_body = _truncate(value.rstrip("\n"), limits.block)
            content_blocks.append(f"--- {key} ---\n{block_body}")
            continue

        if _is_empty(value):
            continue

        rendered = _render_field(key, value, depth=depth, limits=limits)
        if rendered:
            lines.append(rendered)

    meta = "\n".join(lines)
    blocks = "\n\n".join(content_blocks)

    if meta and blocks:
        return f"{meta}\n\n{blocks}"
    return meta or blocks


def _render_top_list(items: list[Any], *, depth: int, limits: _Limits) -> str:
    """Render a top-level list.

    Scalar-only lists become a comma-joined line; dict lists get a numbered
    ``(N items):`` header followed by indented entries.
    """
    if not items:
        return ""

    if all(_is_scalar(v) for v in items):
        return _join_scalars(items, limits)

    lines: list[str] = [f"({len(items)} items):"]
    lines.extend(
        _render_numbered_items(
            items, depth=depth, indent="  ", limits=limits
        )
    )
    return "\n".join(lines)


def _render_field(key: str, value: Any, *, depth: int, limits: _Limits) -> str:
    """Render a single ``key: value`` (or block header + indented children)."""
    if isinstance(value, dict):
        inner = _render_dict(value, depth=depth + 1, limits=limits)
        if not inner:
            return ""
        return f"{key}:\n{_indent(inner, '  ')}"

    if isinstance(value, list):
        if all(_is_scalar(v) for v in value):
            return f"{key}: {_join_scalars(value, limits)}"
        header = f"{key} ({len(value)}):"
        items = _render_numbered_items(
            value, depth=depth + 1, indent="  ", limits=limits
        )
        return "\n".join([header, *items])

    return f"{key}: {_render_scalar(value, limits)}"


def _render_numbered_items(
    items: list[Any],
    *,
    depth: int,
    indent: str,
    limits: _Limits,
) -> list[str]:
    """Render a list as numbered entries starting at ``<indent>1.``.

    Each dict item's fields render one-per-line aligned under the number.
    """
    out: list[str] = []
    for i, item in enumerate(items, start=1):
        prefix = f"{indent}{i}. "
        cont_indent = " " * len(prefix)
        if isinstance(item, dict):
            rendered = _render_dict(item, depth=depth + 1, limits=limits)
            if not rendered:
                out.append(f"{prefix}(empty)")
                continue
            lines = rendered.split("\n")
            out.append(f"{prefix}{lines[0]}")
            for ln in lines[1:]:
                out.append(f"{cont_indent}{ln}")
        elif isinstance(item, list):
            out.append(f"{prefix}{_join_scalars(item, limits)}")
        else:
            out.append(f"{prefix}{_render_scalar(item, limits)}")
    return out


def _render_scalar(value: Any, limits: _Limits) -> str:
    """Stringify a scalar (bool → ``true``/``false``; others → ``str``)."""
    if isinstance(value, bool):
        return "true" if value else "false"
    if value is None:
        return "null"
    text = str(value)
    return _truncate(text, limits.scalar)


def _join_scalars(items: list[Any], limits: _Limits) -> str:
    parts = [_render_scalar(v, limits) for v in items if not _is_empty(v)]
    rendered = ", ".join(parts)
    return _truncate(rendered, limits.scalar)


def _is_scalar(v: Any) -> bool:
    return v is None or isinstance(v, (str, int, float, bool))


def _is_empty(v: Any) -> bool:
    if v is None:
        return True
    if isinstance(v, str):
        return v == ""
    if isinstance(v, (list, dict)):
        return len(v) == 0
    return False


def _is_non_empty_scalar(v: Any) -> bool:
    return _is_scalar(v) and not _is_empty(v)


def _truncate(text: str, limit: int) -> str:
    if len(text) <= limit:
        return text
    return text[:limit] + _TRUNCATED_SUFFIX


def _indent(text: str, pad: str) -> str:
    return "\n".join(
        f"{pad}{line}" if line else line for line in text.split("\n")
    )
