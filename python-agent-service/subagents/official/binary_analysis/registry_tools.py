"""Deprecated: use :mod:`subagents.official.binary_analysis.registry` instead."""

from __future__ import annotations

from subagents.official.binary_analysis.registry import (
    REGISTRY_TOOL_ORDER,
    build_subagent_tool_map,
    create_binary_analysis_tools,
)

build_binary_analysis_tool_map = build_subagent_tool_map

__all__ = [
    "REGISTRY_TOOL_ORDER",
    "build_binary_analysis_tool_map",
    "build_subagent_tool_map",
    "create_binary_analysis_tools",
]
