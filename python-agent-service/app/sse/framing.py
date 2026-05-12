"""SSE line framing: one JSON object per ``data:`` line."""

from __future__ import annotations

import json
from typing import Any

from app.parsers.events import mark_event_internal


def create_sse_message(event: dict[str, Any]) -> str:
    """Format one SSE message: ``data: <json>\\n\\n``.

    Applies visibility rules via ``mark_event_internal`` before serialization.
    """
    event = mark_event_internal(dict(event))
    return f"data: {json.dumps(event, ensure_ascii=False)}\n\n"
