"""Test that multimode astream correctly surfaces __interrupt__ and saves checkpoint."""

from __future__ import annotations

from typing import Any

import pytest
from langchain_core.runnables import RunnableLambda
from langgraph.checkpoint.memory import MemorySaver
from langgraph.graph import StateGraph, START, END
from langgraph.types import interrupt, Command
from typing_extensions import TypedDict


class St(TypedDict):
    messages: list[str]


def _build_graph_with_lambda_interrupt(checkpointer):
    async def _lambda(inputs: dict, config: Any = None) -> dict:
        val = interrupt({"prompt": "Clarify", "q": inputs["q"]})
        return {"answer": f"Got: {val}"}

    research = RunnableLambda(_lambda)

    async def tools_node(state: St) -> dict:
        last = state["messages"][-1]
        if last.startswith("__call__"):
            result = await research.ainvoke({"q": state["messages"][0]})
            return {"messages": [str(result.get("answer", ""))]}
        return {}

    def agent_node(state: St) -> dict:
        if any("Got:" in m for m in state["messages"]):
            return {"messages": ["DONE"]}
        return {"messages": ["__call__"]}

    builder = StateGraph(St)
    builder.add_node("agent", agent_node)
    builder.add_node("tools", tools_node)
    builder.add_edge(START, "agent")
    builder.add_conditional_edges(
        "agent",
        lambda s: "tools" if s["messages"][-1].startswith("__call__") else END,
    )
    builder.add_edge("tools", "agent")
    return builder.compile(checkpointer=checkpointer)


@pytest.mark.asyncio
async def test_multimode_stream_interrupt_and_resume():
    """With stream_mode=['messages', 'updates', 'custom'] (production settings),
    verify __interrupt__ appears, checkpoint has interrupts, and resume works."""
    checkpointer = MemorySaver()
    graph = _build_graph_with_lambda_interrupt(checkpointer)
    config = {"configurable": {"thread_id": "multimode-1"}}

    kwargs: dict[str, Any] = {"stream_mode": ["messages", "updates", "custom"]}
    try:
        import langgraph
        if hasattr(langgraph, "__version__") and langgraph.__version__ >= "1.1":
            kwargs["version"] = "v2"
    except Exception:
        pass

    saw_interrupt = False
    async for chunk in graph.astream(
        {"messages": ["Test topic"]}, config, **kwargs
    ):
        if "__interrupt__" in str(chunk):
            saw_interrupt = True
            break

    assert saw_interrupt, "Should see __interrupt__ in multimode stream"

    snap = await graph.aget_state(config)
    assert snap.interrupts, (
        f"Checkpoint should have interrupts. "
        f"tasks={snap.tasks}, next={snap.next}"
    )

    # Resume with Command
    events = []
    async for chunk in graph.astream(
        Command(resume="Focus on safety"), config, stream_mode="updates"
    ):
        events.append(chunk)

    snap2 = await graph.aget_state(config)
    assert not snap2.interrupts, "No interrupts after resume"
    assert not snap2.next, "Graph should be complete"
