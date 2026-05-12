"""Tests for ConductResearch per-topic researcher subgraph execution."""

from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock

import pytest
from langchain_core.runnables import RunnableConfig

from app.agents.research.open_deep_research_compiled import stream_researcher_subgraph_with_sse


@pytest.mark.asyncio
async def test_stream_researcher_subgraph_uses_ainvoke():
    """Always ainvoke; return shape is normalized compressed_research + raw_notes."""
    graph = AsyncMock()
    graph.ainvoke = AsyncMock(
        return_value={"compressed_research": "ok", "raw_notes": ["a"]}
    )
    cfg: RunnableConfig = {"configurable": {}}
    out = await stream_researcher_subgraph_with_sse(
        graph, {"research_topic": "t"}, cfg, research_unit_topic="topic a"
    )
    assert out["compressed_research"] == "ok"
    assert out["raw_notes"] == ["a"]
    graph.ainvoke.assert_awaited_once()
    graph.astream.assert_not_called()


@pytest.mark.asyncio
async def test_stream_researcher_subgraph_ignores_sse_sink_uses_ainvoke_only():
    """subagent_sse_event_queue no longer enables nested streaming."""
    graph = AsyncMock()
    graph.ainvoke = AsyncMock(
        return_value={
            "compressed_research": "compressed body",
            "raw_notes": ["note1"],
        }
    )

    q: asyncio.Queue = asyncio.Queue()
    cfg: RunnableConfig = {
        "configurable": {"subagent_sse_event_queue": q, "sse_ui_language": "en"}
    }
    out = await stream_researcher_subgraph_with_sse(
        graph,
        {"research_topic": "my topic", "researcher_messages": []},
        cfg,
        research_unit_topic="my topic",
    )

    assert out["compressed_research"] == "compressed body"
    assert out["raw_notes"] == ["note1"]
    graph.ainvoke.assert_awaited_once()
    graph.astream.assert_not_called()
    assert q.empty()


@pytest.mark.asyncio
async def test_stream_researcher_subgraph_normalizes_raw_notes_scalar():
    graph = AsyncMock()
    graph.ainvoke = AsyncMock(
        return_value={"compressed_research": "ok", "raw_notes": "single"}
    )
    cfg: RunnableConfig = {"configurable": {}}
    out = await stream_researcher_subgraph_with_sse(
        graph, {"research_topic": "t", "researcher_messages": []}, cfg
    )
    assert out["compressed_research"] == "ok"
    assert out["raw_notes"] == ["single"]
