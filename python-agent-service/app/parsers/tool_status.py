"""Derive SSE tool_result status from tool output content."""

import json
from typing import Any


def derive_tool_status(content: Any) -> str:
    """Infer tool_result status from output content.

    Returns ``"error"`` when:
      - the output is a JSON object with a truthy ``"error"`` key, or
      - the output is a plain string starting with ``"Error:"`` (the
        convention used by DeepAgents filesystem tools such as
        ``read_file`` / ``edit_file`` / ``write_file`` when the backend
        returns a ``ReadResult`` with an error message).

    Otherwise returns ``"success"``.
    """
    if isinstance(content, str):
        text = content
    else:
        text = str(content) if content is not None else ""
    text = text.strip()
    if not text:
        return "success"
    try:
        parsed = json.loads(text)
        if isinstance(parsed, dict) and parsed.get("error"):
            return "error"
    except (ValueError, TypeError):
        pass
    # DeepAgents filesystem tools signal failure by returning a plain string
    # prefixed with "Error:". Without this branch the SSE tool_result would
    # be tagged "success" even when read_file actually failed, which misleads
    # the UI and weakens the master-agent "read_file failure = hard stop"
    # contract. Match case-insensitively and accept "Error:" / "Error ".
    lowered = text.lower()
    if lowered.startswith("error:") or lowered.startswith("error "):
        return "error"
    return "success"
