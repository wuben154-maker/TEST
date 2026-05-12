"""Unwrap structured user envelopes (JSON) into plain prompt text.

Some clients or copy-paste workflows send a single-field JSON object such as
``{"research_brief": "..."}``. The agent should receive the inner string, not
raw JSON, so intent and research subgraphs behave as with normal chat input.
"""

from __future__ import annotations

import json
import re
from typing import Any

# Keys that indicate the entire body is a wrapper around the real user prompt.
_UNWRAP_KEYS = frozenset(
    {
        "research_brief",
        "brief",
        "query",
        "prompt",
        "message",
        "user_message",
        "instruction",
    }
)

_FENCE_RE = re.compile(
    r"^```(?:json)?\s*\r?\n([\s\S]*?)\r?\n```\s*$",
    re.IGNORECASE,
)


def unwrap_structured_user_prompt(text: Any) -> str:
    """Return inner prompt if ``text`` is a one-key JSON envelope.

    Otherwise return stripped ``text`` (or empty string for non-strings).

    Rules:
    - Strip optional fenced `` ```json `` block first.
    - Unwrap only a JSON object with exactly one allowed key (see module).
    - Inner value must be a non-empty string after strip.
    """
    if text is None:
        return ""
    if not isinstance(text, str):
        return ""

    original = text
    s = text.strip()
    if not s:
        return ""

    m = _FENCE_RE.match(s)
    if m:
        s = m.group(1).strip()
        if not s:
            return original.strip()

    if not (s.startswith("{") and s.endswith("}")):
        return original.strip()

    try:
        data = json.loads(s)
    except json.JSONDecodeError:
        return original.strip()

    if not isinstance(data, dict) or len(data) != 1:
        return original.strip()

    key, val = next(iter(data.items()))
    if key not in _UNWRAP_KEYS:
        return original.strip()
    if not isinstance(val, str):
        return original.strip()
    inner = val.strip()
    if not inner:
        return original.strip()
    return inner
