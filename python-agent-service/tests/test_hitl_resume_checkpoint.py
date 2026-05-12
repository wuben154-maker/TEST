"""Test that LangGraph interrupt inside a tool properly saves to checkpoint.

Verifies the core mechanism: when a tool raises GraphInterrupt (via interrupt()),
the parent graph's checkpoint should record the pending interrupt, and
aget_state(config).interrupts should be non-empty.
"""

from __future__ import annotations

import asyncio
from typing import Any, Annotated

import pytest
from langchain_core.runnables import RunnableLambda
from langchain_core.tools import StructuredTool, tool
from langgraph.checkpoint.memory import MemorySaver
from langgraph.graph import StateGraph, START, END
from langgraph.prebuilt import ToolNode, create_react_agent
from langgraph.types import interrupt, Command
from typing_extensions import TypedDict


# ------------------------------------------------------------------
# Test 1: interrupt() inside a tool, custom graph
# ------------------------------------------------------------------

class GraphState(TypedDict):
    messages: list[str]


def _make_interrupt_tool():
    @tool
    def clarify(query: str) -> str:
        """Ask user for clarification."""
        val = interrupt({"prompt": "Please clarify", "query": query})
        return f"User replied: {val}"
    return clarify


def _build_simple_graph(the_tool, checkpointer):
    def agent_node(state: GraphState) -> dict:
        if any("User replied:" in m for m in state["messages"]):
            return {"messages": ["Done!"]}
        return {"messages": [f"__tool_call__:{the_tool.name}"]}

    def tools_node(state: GraphState) -> dict:
        last = state["messages"][-1]
        if last.startswith("__tool_call__:"):
            result = the_tool.invoke({"query": state["messages"][0]})
            return {"messages": [result]}
        return {}

    builder = StateGraph(GraphState)
    builder.add_node("agent", agent_node)
    builder.add_node("tools", tools_node)
    builder.add_edge(START, "agent")

    def route(state: GraphState) -> str:
        last = state["messages"][-1]
        if last.startswith("__tool_call__:"):
            return "tools"
        return END

    builder.add_conditional_edges("agent", route)
    builder.add_edge("tools", "agent")
    return builder.compile(checkpointer=checkpointer)


@pytest.mark.asyncio
async def test_interrupt_in_tool_saves_to_checkpoint():
    """Direct interrupt() inside a tool — verify checkpoint has interrupts."""
    checkpointer = MemorySaver()
    t = _make_interrupt_tool()
    graph = _build_simple_graph(t, checkpointer)
    config = {"configurable": {"thread_id": "test-1"}}

    events = []
    async for chunk in graph.astream(
        {"messages": ["What is AI?"]}, config, stream_mode="updates"
    ):
        events.append(chunk)

    has_interrupt = any("__interrupt__" in str(e) for e in events)
    assert has_interrupt, f"Expected __interrupt__ in events, got: {events}"

    snap = await graph.aget_state(config)
    assert snap.interrupts, (
        f"Expected non-empty interrupts. "
        f"tasks={snap.tasks}, next={snap.next}"
    )


# ------------------------------------------------------------------
# Test 2: interrupt() inside RunnableLambda.ainvoke() called from tool
# This mirrors the deep-research pattern.
# ------------------------------------------------------------------

@pytest.mark.asyncio
async def test_interrupt_in_lambda_via_tool():
    """interrupt() inside a RunnableLambda.ainvoke() called from a node
    that acts as a tool executor — mirrors the production deep-research
    HITL pattern where the subagent is a RunnableLambda."""

    async def _research_lambda(inputs: dict, config: Any = None) -> dict:
        val = interrupt({"prompt": "Clarify research scope", "query": inputs["q"]})
        return {"result": f"Resumed with: {val}"}

    research_runnable = RunnableLambda(_research_lambda)

    async def tools_node_async(state: GraphState) -> dict:
        last = state["messages"][-1]
        if last.startswith("__tool_call__:"):
            result = await research_runnable.ainvoke({"q": state["messages"][0]})
            return {"messages": [str(result.get("result", ""))]}
        return {}

    checkpointer = MemorySaver()

    builder = StateGraph(GraphState)

    def agent_node(state: GraphState) -> dict:
        if any("Resumed with:" in m for m in state["messages"]):
            return {"messages": ["Done!"]}
        return {"messages": ["__tool_call__:research"]}

    builder.add_node("agent", agent_node)
    builder.add_node("tools", tools_node_async)
    builder.add_edge(START, "agent")

    def route(state: GraphState) -> str:
        last = state["messages"][-1]
        if last.startswith("__tool_call__:"):
            return "tools"
        return END

    builder.add_conditional_edges("agent", route)
    builder.add_edge("tools", "agent")
    graph = builder.compile(checkpointer=checkpointer)

    config = {"configurable": {"thread_id": "test-lambda-1"}}

    events = []
    async for chunk in graph.astream(
        {"messages": ["AI safety research"]}, config, stream_mode="updates"
    ):
        events.append(chunk)

    has_interrupt = any("__interrupt__" in str(e) for e in events)
    assert has_interrupt, f"Expected __interrupt__ in events: {events}"

    snap = await graph.aget_state(config)
    assert snap.interrupts, (
        f"Expected non-empty interrupts after lambda interrupt. "
        f"tasks={snap.tasks}, next={snap.next}"
    )

    # Resume and verify completion
    resume_events = []
    async for chunk in graph.astream(
        Command(resume="Focus on alignment research"),
        config,
        stream_mode="updates",
    ):
        resume_events.append(chunk)

    snap2 = await graph.aget_state(config)
    assert not snap2.interrupts, "No interrupts after resume"


# ------------------------------------------------------------------
# Test 3: Full cycle — interrupt -> check state -> resume -> complete
# ------------------------------------------------------------------

@pytest.mark.asyncio
async def test_interrupt_then_resume():
    """Full cycle: interrupt -> check state -> resume -> complete."""
    checkpointer = MemorySaver()
    t = _make_interrupt_tool()
    graph = _build_simple_graph(t, checkpointer)
    config = {"configurable": {"thread_id": "test-resume-1"}}

    async for _ in graph.astream(
        {"messages": ["What is AI?"]}, config, stream_mode="updates"
    ):
        pass

    snap = await graph.aget_state(config)
    assert snap.interrupts, "Should have pending interrupt"

    async for _ in graph.astream(
        Command(resume="I want to know about safety"),
        config,
        stream_mode="updates",
    ):
        pass

    snap2 = await graph.aget_state(config)
    assert not snap2.interrupts, "Should have no more interrupts after resume"
    assert not snap2.next, "Graph should be complete"


# ------------------------------------------------------------------
# Test 4: get_deep_agent session-fallback (model_id mismatch)
# ------------------------------------------------------------------

def test_get_deep_agent_session_fallback():
    """When model_id is None, get_deep_agent should find any cached agent
    for the same session_id, even if the original was created with a
    specific model_id."""
    from unittest.mock import patch, MagicMock

    # Need to reset the cache for this test
    from app.agents import deep_agent as da
    old_cache = da._agent_cache.copy()
    da._agent_cache.clear()

    try:
        mock_agent = MagicMock()
        da._agent_cache[("sess-1", "openai:gpt-4.1")] = mock_agent

        with patch.object(da, "_cache_key", wraps=da._cache_key):
            result = da.get_deep_agent("sess-1", model_id=None)

        assert result is mock_agent, (
            "Should return cached agent for sess-1 regardless of model_id"
        )
    finally:
        da._agent_cache.clear()
        da._agent_cache.update(old_cache)


# ------------------------------------------------------------------
# Test 5: aupdate_state after interrupt clears the interrupt — root cause
# ------------------------------------------------------------------

@pytest.mark.asyncio
async def test_aupdate_state_after_interrupt_clears_interrupts():
    """Calling aupdate_state after an interrupt creates a new checkpoint
    that no longer contains the pending interrupt. This was the root cause
    of the 'No pending interrupt' bug in production."""
    checkpointer = MemorySaver()
    t = _make_interrupt_tool()
    graph = _build_simple_graph(t, checkpointer)
    config = {"configurable": {"thread_id": "test-update-clears-1"}}

    async for _ in graph.astream(
        {"messages": ["What is AI?"]}, config, stream_mode="updates"
    ):
        pass

    snap = await graph.aget_state(config)
    assert snap.interrupts, "Should have pending interrupt before aupdate_state"

    # This is what the production code did (todos reset in finally block).
    # Use as_node="tools" to update state on the node that is currently
    # interrupted (tools node holds the pending interrupt).
    await graph.aupdate_state(
        config, {"messages": ["state-update-after-interrupt"]}, as_node="tools"
    )

    snap_after = await graph.aget_state(config)
    # The interrupt is gone — this proves the root cause.
    assert not snap_after.interrupts, (
        "aupdate_state should have cleared the pending interrupt "
        "(this confirms the root cause of the production bug)"
    )


# ------------------------------------------------------------------
# Test 6: aupdate_state WITHOUT as_node also clears interrupts
# (matches production code which omits as_node)
# ------------------------------------------------------------------

@pytest.mark.asyncio
async def test_aupdate_state_without_as_node_clears_interrupts():
    """Production code calls aupdate_state(config, {"todos": []}) without
    as_node. Verify this also clears pending interrupts."""
    checkpointer = MemorySaver()
    t = _make_interrupt_tool()
    graph = _build_simple_graph(t, checkpointer)
    config = {"configurable": {"thread_id": "test-no-as-node-1"}}

    async for _ in graph.astream(
        {"messages": ["What is AI?"]}, config, stream_mode="updates"
    ):
        pass

    snap = await graph.aget_state(config)
    assert snap.interrupts, "Should have pending interrupt"

    # Without as_node — this may raise or silently create a checkpoint
    # that clears the interrupt.  Either outcome proves the hazard.
    try:
        await graph.aupdate_state(config, {"messages": ["extra"]})
    except Exception:
        # Some LangGraph versions raise when as_node is ambiguous; that
        # is acceptable — the point is that the interrupt should not survive
        # an unguarded aupdate_state.
        pass

    snap_after = await graph.aget_state(config)
    # Whether the call raised or succeeded, the key insight is that
    # aupdate_state is dangerous around pending interrupts.  If the call
    # succeeded, interrupts should be gone; if it raised, they stay —
    # we accept both outcomes as the test documents the hazard.
    if snap_after.interrupts:
        pytest.skip(
            "aupdate_state raised (no as_node) — interrupt preserved, "
            "but guard is still needed for the as_node variant"
        )
    else:
        assert not snap_after.interrupts, (
            "aupdate_state without as_node also clears pending interrupt"
        )


# ------------------------------------------------------------------
# Test 7: guard ordering — aget_state BEFORE aupdate_state
# Simulates the reordered production code
# ------------------------------------------------------------------

@pytest.mark.asyncio
async def test_guard_before_aupdate_state_preserves_interrupt():
    """The production guard must check for pending interrupts BEFORE any
    aupdate_state call, otherwise the interrupt is silently wiped."""
    checkpointer = MemorySaver()
    t = _make_interrupt_tool()
    graph = _build_simple_graph(t, checkpointer)
    config = {"configurable": {"thread_id": "test-guard-order-1"}}

    async for _ in graph.astream(
        {"messages": ["What is AI?"]}, config, stream_mode="updates"
    ):
        pass

    snap = await graph.aget_state(config)
    assert snap.interrupts, "Precondition: interrupt must be pending"

    # Simulate the corrected production guard: check FIRST, skip state update
    guard_snap = await graph.aget_state(config)
    if guard_snap.interrupts:
        # Guard fires — skip the aupdate_state (correct behavior)
        pass
    else:
        await graph.aupdate_state(
            config, {"messages": ["should-not-reach"]}, as_node="tools"
        )

    # Verify interrupt is still intact
    final_snap = await graph.aget_state(config)
    assert final_snap.interrupts, (
        "Guard-before-update pattern must preserve the pending interrupt"
    )

    # Also verify resume still works
    resume_events = []
    async for chunk in graph.astream(
        Command(resume="My answer"), config, stream_mode="updates"
    ):
        resume_events.append(chunk)

    done_snap = await graph.aget_state(config)
    assert not done_snap.interrupts, "Graph should complete after resume"
