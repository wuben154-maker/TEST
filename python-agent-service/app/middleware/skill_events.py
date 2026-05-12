"""Skill execution events for subagent streaming.

adapt_subagent_astream_to_skill_events now yields dict (ThinkingEvent-compatible)
directly. SkillEvent kept for backward compatibility; use .to_dict() to convert.
"""

import time
from typing import Any


class SkillEvent:
    """Event emitted during skill execution (subagent stream adapter)."""

    def __init__(
        self,
        event_type: str,
        *,
        step_id: str = "",
        label: str = "",
        status: str = "running",
        detail: str = "",
        tool_name: str = "",
        tool_input: dict | None = None,
        tool_output: str = "",
        timestamp: int = 0,
    ):
        self.type = event_type
        self.step_id = step_id or f"step-{int(time.time() * 1000)}"
        self.label = label
        self.status = status
        self.detail = detail
        self.tool_name = tool_name
        self.tool_input = tool_input or {}
        self.tool_output = tool_output
        self.timestamp = timestamp or int(time.time() * 1000)

    def to_dict(self) -> dict[str, Any]:
        return {
            "type": self.type,
            "id": self.step_id,
            "label": self.label,
            "status": self.status,
            "detail": self.detail,
            "toolName": self.tool_name,
            "toolInput": self.tool_input,
            "toolOutput": self.tool_output,
            "timestamp": self.timestamp,
        }
