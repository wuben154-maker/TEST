"""UI-bound path scrubbing.

Rewrites internal virtual and host paths so that the frontend never sees raw
``/workspace/u_abc/p_xyz/…``, ``/memories/…``, ``/skills-<id>/…``, absolute
Windows / POSIX host paths, or relative ``./`` prefixes. Applied at the SSE
boundary of the stream adapter — tool results flowing back to the LLM keep
their raw form so the agent can chain path-referenced calls.

The rules are deliberately ordered (first match wins); they are idempotent:
``scrub_paths_for_ui(scrub_paths_for_ui(x)) == scrub_paths_for_ui(x)``.
"""

from __future__ import annotations

import re
from typing import Any, Iterable

_TEXT_FIELDS: tuple[str, ...] = (
    "text",
    "content",
    "reasoning",
    "output",
    "message",
    "label",
    "detail",
    "description",
    "title",
    "summary",
    "markdown",
)


# A path-like token excludes whitespace, quotes, angle brackets and backticks so
# sentences like "see /workspace/a.txt." are not over-consumed.
_TOKEN_CHARS = r"[^\s'\"<>`]"


def _memory_basename(match: re.Match[str]) -> str:
    tail = match.group(1).rsplit("/", 1)[-1]
    return f"Memory: {tail}"


def _workspace_owner_tail_basename(match: re.Match[str]) -> str:
    """Collapse owner-scoped tails to ``workspace/<filename>`` only (user-facing)."""
    tail = (match.group(1) or "").strip().strip("/")
    if not tail:
        return "workspace"
    base = tail.rsplit("/", 1)[-1]
    return f"workspace/{base}"


_RULES: tuple[tuple[re.Pattern[str], Any], ...] = (
    # Multi-segment owner paths → basename only (fixes leaked
    # ``workspace/u_<id>/default/sub/file`` when single-token regex failed).
    (
        re.compile(
            r"/workspace/(?:u_[\w.-]+/(?:p_[\w.-]+|default)|s_[\w.-]+)/(.+)"
        ),
        _workspace_owner_tail_basename,
    ),
    (
        re.compile(
            r"(?i)workspace/(?:u_[\w.-]+/(?:p_[\w.-]+|default)|s_[\w.-]+)/(.+)"
        ),
        _workspace_owner_tail_basename,
    ),
    (
        re.compile(
            r"/uploads/u_[\w.-]+/(?:p_[\w.-]+|default)/(.+)"
        ),
        _workspace_owner_tail_basename,
    ),
    (re.compile(r"/uploads/s_[\w.-]+/(.+)"), _workspace_owner_tail_basename),
    (
        re.compile(
            rf"/uploads/u_[\w.-]+/({_TOKEN_CHARS}+)"
        ),
        _workspace_owner_tail_basename,
    ),
    # Strip owner-only segments (no filename) from scrubbed prose.
    (
        re.compile(
            r"/workspace/(?:u_[\w.-]+/(?:p_[\w.-]+|default)|s_[\w.-]+)(?=/|\b)"
        ),
        "workspace",
    ),
    (
        re.compile(
            r"(?i)workspace/(?:u_[\w.-]+/(?:p_[\w.-]+|default)|s_[\w.-]+)(?=/|\b)"
        ),
        "workspace",
    ),
    (re.compile(rf"/workspace/({_TOKEN_CHARS}+)"), r"workspace/\1"),
    (re.compile(r"/workspace\b"), "workspace"),
    (re.compile(rf"/skills(?:-main|-[\w-]+)?/([\w][\w-]*)/{_TOKEN_CHARS}*"), r"System Skill: \1"),
    (re.compile(r"/skills(?:-main|-[\w-]+)?/([\w][\w-]*)"), r"System Skill: \1"),
    (re.compile(rf"/memories/({_TOKEN_CHARS}+)"), _memory_basename),
    (re.compile(rf"/parameters/{_TOKEN_CHARS}*"), "Parameters"),
    (re.compile(r"/parameters\b"), "Parameters"),
    (re.compile(rf"/uploads/({_TOKEN_CHARS}+)"), r"workspace/\1"),
    (re.compile(r"/uploads\b"), "workspace"),
)


# Short-circuit strings that clearly contain no rewritable tokens. Keeps the
# hot path ~free for normal chat text (no token allocation beyond the search).
# Only matches SecManus-internal virtual roots — arbitrary host paths (/tmp,
# /var, Windows drive letters, ./relative) are intentionally *not* rewritten
# so legitimate tool arguments, sandbox paths and URLs pass through unchanged.
_FAST_PATH = re.compile(
    r"(?i)(?:/workspace\b|workspace/)|/skills(?:-main|-[\w-]+)?/|"
    r"/memories/|/parameters|/uploads",
)


def scrub_paths_for_ui(text: str | None) -> str:
    """Return a UI-safe copy of *text* with every internal path rewritten.

    Idempotent; safe on empty string, ``None`` (returns empty string) and on
    text that has already been scrubbed.
    """
    if text is None:
        return ""
    if not isinstance(text, str) or not text:
        return text or ""
    if not _FAST_PATH.search(text):
        return text
    out = text
    for pat, repl in _RULES:
        out = pat.sub(repl, out)
    return out


def _walk_scrub(value: Any, depth: int = 0) -> Any:
    """Recursively scrub every string inside a nested dict/list/tuple.

    Depth-capped so pathological structures cannot turn into a DoS vector.
    """
    if depth > 6:
        return value
    if isinstance(value, str):
        return scrub_paths_for_ui(value)
    if isinstance(value, dict):
        return {k: _walk_scrub(v, depth + 1) for k, v in value.items()}
    if isinstance(value, list):
        return [_walk_scrub(v, depth + 1) for v in value]
    if isinstance(value, tuple):
        return tuple(_walk_scrub(v, depth + 1) for v in value)
    return value


_NESTED_FIELDS: tuple[str, ...] = (
    "tool_input",
    "toolInput",
    "tool_output",
    "toolOutput",
    "payload",
    "result",
    "data",
    "meta",
    "artifact",
    "artifacts",
    "files",
    "attachments",
    "args",
    "arguments",
)


def scrub_event(event: Any) -> Any:
    """Return a UI-safe shallow copy of an SSE event dict.

    The original dict is never mutated. Non-dict events pass through unchanged.
    All known text-bearing top-level fields, common nested payloads and
    ``blocks`` are walked. Binary / base64 content blocks are preserved because
    they never contain prose that should be rewritten.
    """
    if not isinstance(event, dict):
        return event
    out = dict(event)
    for field in _TEXT_FIELDS:
        val = out.get(field)
        if isinstance(val, str):
            out[field] = scrub_paths_for_ui(val)
    for nested in _NESTED_FIELDS:
        if nested in out:
            out[nested] = _walk_scrub(out[nested])
    if isinstance(out.get("blocks"), list):
        out["blocks"] = [_walk_scrub(b) for b in out["blocks"]]
    return out


def scrub_iterable(events: Iterable[Any]) -> Iterable[Any]:
    for ev in events:
        yield scrub_event(ev)


__all__ = [
    "scrub_paths_for_ui",
    "scrub_event",
    "scrub_iterable",
]
