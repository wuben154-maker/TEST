"""Parity and smoke tests for ``common_tool_registry``."""

from app.sse.tool_presentation import COMMON_SECURITY_TOOL_ORDER, RESEARCH_TOOL_ORDER
from app.tools.common_tool_registry import (
    SANDBOX_TOOL_NAMES,
    registered_common_tool_names,
    try_mount_common_tool,
)


def test_registered_names_cover_security_history_research() -> None:
    expected = (
        frozenset(COMMON_SECURITY_TOOL_ORDER)
        | frozenset(RESEARCH_TOOL_ORDER)
        | frozenset({"search_history"})
        | frozenset(SANDBOX_TOOL_NAMES)
        | frozenset({"SReadFile"})
    )
    assert registered_common_tool_names() == expected


def test_try_mount_unknown_returns_false() -> None:
    assert try_mount_common_tool("not_a_real_tool_ever", []) is False
