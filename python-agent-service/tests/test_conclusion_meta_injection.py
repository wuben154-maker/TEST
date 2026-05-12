"""Adapter-level tests for the `conclusion.meta` injection.

Covers acceptance A-01, A-02, A-03 from
`docs/Process/stats-bar-value-redesign/acceptance.md`.

We feed ``adapt_astream_to_sse`` a minimal mock ``agent`` whose ``astream``
returns a hand-crafted sequence of updates, and verify that the emitted
``conclusion`` event either carries a properly shaped ``meta`` key or omits
it entirely.
"""

from __future__ import annotations

from typing import Any
from unittest.mock import AsyncMock, MagicMock

import pytest

from app.parsers.deepagents_stream_adapter import adapt_astream_to_sse
from langchain_core.messages import AIMessage, ToolMessage


async def _astream_yield(*events: dict[str, Any]):
    for ev in events:
        yield ev


def _mock_agent(*events: dict[str, Any]):
    agent = MagicMock()
    agent.astream = MagicMock(return_value=_astream_yield(*events))
    agent.ainvoke = AsyncMock(return_value={"messages": []})
    return agent


# ---------------------------------------------------------------------------
# A-01 — security conclusion → meta.taskKind=="security"
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_conclusion_meta_injection_security() -> None:
    """A-01: web-security subagent + detect_web_attack findings → meta.security."""
    task_call = AIMessage(
        content="",
        tool_calls=[
            {
                "id": "tc-task-1",
                "name": "task",
                "args": {
                    "subagent_type": "web-security",
                    "description": "Scan PHP.",
                },
            }
        ],
    )
    task_result = ToolMessage(
        content="## WRAPUP\nWeb shell located.",
        tool_call_id="tc-task-1",
        name="task",
    )
    detect_result = ToolMessage(
        content=(
            '{"findings": [{"type": "web_shell", '
            '"severity": "high", "risk": 82}]}'
        ),
        tool_call_id="tc-detect-1",
        name="detect_web_attack",
    )
    final = AIMessage(content="Final conclusion body.")

    agent = _mock_agent(
        {"agent": {"messages": [task_call]}},
        {"tools": {"messages": [task_result]}},
        {"tools": {"messages": [detect_result]}},
        {"agent": {"messages": [final]}},
    )

    events: list[dict[str, Any]] = []
    async for ev in adapt_astream_to_sse(agent, {"messages": []}, {"configurable": {}}):
        events.append(ev)

    conclusions = [e for e in events if e.get("type") == "conclusion"]
    assert len(conclusions) == 1
    meta = conclusions[0].get("meta")
    assert meta is not None, f"meta missing from conclusion: {conclusions[0]}"
    assert meta["taskKind"] == "security"
    sec = meta["security"]
    assert sec["severity"] == "high"
    assert sec["riskScore"] == 82
    # detect_web_attack → validation includes "static".
    assert "static" in sec.get("validation", [])
    assert sec.get("threatClasses") == ["web-shell"]


# ---------------------------------------------------------------------------
# A-02 — research conclusion → meta.taskKind=="research"
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_conclusion_meta_injection_research() -> None:
    """A-02: deep-research subagent → meta.taskKind=="research"."""
    task_call = AIMessage(
        content="",
        tool_calls=[
            {
                "id": "tc-task-r1",
                "name": "task",
                "args": {
                    "subagent_type": "deep-research",
                    "description": "Brief on QKD 2025",
                },
            }
        ],
    )
    task_result = ToolMessage(
        content=(
            "## SM_SUBAGENT_WRAPUP\n\nConcise wrapup.\n\n"
            "## SM_SUBAGENT_FULL_REPORT\n\n"
            "## Executive Summary\n- Finding A.\n- Finding B.\n\n"
            "## Recommendations\n- Do X.\n\n"
            "## Sources\n- https://alpha.example.com/p1\n"
        ),
        tool_call_id="tc-task-r1",
        name="task",
    )

    agent = _mock_agent(
        {"agent": {"messages": [task_call]}},
        {"tools": {"messages": [task_result]}},
    )

    events: list[dict[str, Any]] = []
    async for ev in adapt_astream_to_sse(agent, {"messages": []}, {"configurable": {}}):
        events.append(ev)

    conclusions = [e for e in events if e.get("type") == "conclusion"]
    assert len(conclusions) == 1, f"expected 1 conclusion, got {len(conclusions)}"
    meta = conclusions[0].get("meta")
    assert meta is not None
    assert meta["taskKind"] == "research"
    research = meta.get("research") or {}
    # Sources chip driven by URL count; keyFindings by Executive Summary bullets.
    assert research.get("keyFindings") == 2
    assert research.get("recommendations") == 1
    assert research.get("sources") == 1


# ---------------------------------------------------------------------------
# A-03 — generic conclusion → no meta key
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_conclusion_meta_absent_generic() -> None:
    """A-03: trivial chat → conclusion emitted without a `meta` key."""
    agent = _mock_agent(
        {"agent": {"messages": [AIMessage(content="Sure, happy to help!")]}},
    )

    events: list[dict[str, Any]] = []
    async for ev in adapt_astream_to_sse(agent, {"messages": []}, {"configurable": {}}):
        events.append(ev)

    conclusions = [e for e in events if e.get("type") == "conclusion"]
    assert len(conclusions) == 1
    # Must be absent — not null — so downstream type guards treat it as "no profile".
    assert "meta" not in conclusions[0], (
        f"unexpected meta on generic conclusion: {conclusions[0].get('meta')}"
    )
