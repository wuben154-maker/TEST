#!/usr/bin/env python3
"""Probe event order for ConductResearch tool_call vs tool_result on the compiled deep-research path.

Uses the same entrypoint as production: _run_open_deep_research_subagent + subagent_stream_writer.
Patches original_research_graph.astream to emit a minimal LangGraph v1 tuple stream:

1) ``messages``: AIMessage with ConductResearch tool_calls (supervise节点), emulating
   "model decided to delegate" **before** tool execution.
2) ``updates``: node output containing ToolMessage for the same tool_call_id (tool finished).

Run from repo:
  cd python-agent-service && python scripts/probe_conduct_research_tool_sse_order.py

Exit 0 if every ConductResearch tool_result appears after its tool_call in the pushed list.
"""

from __future__ import annotations

import asyncio
import sys

from langchain_core.messages import AIMessage, HumanMessage, ToolMessage

from app.agents.research.open_deep_research_compiled import (
    _run_open_deep_research_subagent,
    original_research_graph,
)

TC_ID = "call-conduct-abc"
TOPIC = "SSE order probe topic"


async def _fake_research_graph_astream(*_args, **_kwargs):
    """Minimal LangGraph v1 tuple stream (same shape as real ``astream``)."""
    # 1) Model output with ConductResearch — early ``messages`` branch should _push tool_call.
    yield (
        "messages",
        (
            AIMessage(
                content="",
                tool_calls=[
                    {
                        "name": "ConductResearch",
                        "id": TC_ID,
                        "args": {"research_topic": TOPIC},
                    }
                ],
            ),
            {"langgraph_node": "research_supervisor"},
        ),
    )
    # 2) Tool finished — ``updates`` emits tool_result (duplicate tool_call skipped by ctx).
    yield (
        "updates",
        {
            "supervisor_tools": {
                "supervisor_messages": [
                    ToolMessage(
                        content="compressed summary for topic",
                        name="ConductResearch",
                        tool_call_id=TC_ID,
                    )
                ]
            }
        },
    )
    # 3) Final node so the runner can finish like the integration test.
    yield (
        "updates",
        {
            "final_report_generation": {
                "final_report": "# Report\n\nDone.",
                "messages": [AIMessage(content="# Report\n\nDone.")],
            }
        },
    )


def main() -> int:
    pushed: list[dict] = []
    state = {"messages": [HumanMessage(content="Probe: one ConductResearch cycle order")]}
    config = {
        "configurable": {
            "subagent_stream_writer": pushed.append,
            "thread_id": "probe-sse-order",
            "sse_ui_language": "en",
        }
    }

    async def _run():
        prev = getattr(original_research_graph, "astream", None)
        original_research_graph.astream = _fake_research_graph_astream  # type: ignore[method-assign]
        try:
            return await _run_open_deep_research_subagent(state, config)
        finally:
            if prev is not None:
                original_research_graph.astream = prev  # type: ignore[method-assign]

    asyncio.run(_run())

    cr_calls = [
        (i, e)
        for i, e in enumerate(pushed)
        if e.get("type") == "tool_call" and e.get("toolName") == "ConductResearch"
    ]
    cr_results = [
        (i, e)
        for i, e in enumerate(pushed)
        if e.get("type") == "tool_result" and e.get("toolName") == "ConductResearch"
    ]

    print("=== pushed events (ConductResearch / tool_call / tool_result only) ===")
    for i, e in enumerate(pushed):
        t = e.get("type")
        if t not in ("tool_call", "tool_result"):
            continue
        if e.get("toolName") != "ConductResearch":
            continue
        tin = e.get("toolInput") if t == "tool_call" else None
        topic_hint = ""
        if isinstance(tin, dict) and tin.get("research_topic"):
            rt = str(tin.get("research_topic", ""))[:50]
            topic_hint = f" research_topic={rt!r}"
        print(f"  [{i:3d}] {t:<12} id={e.get('id')!r}{topic_hint}")

    print("\n=== summary ===")
    print(f"  ConductResearch tool_call count: {len(cr_calls)}")
    print(f"  ConductResearch tool_result count: {len(cr_results)}")

    if not cr_calls:
        print("ERROR: no ConductResearch tool_call in pushed stream", file=sys.stderr)
        return 2
    if not cr_results:
        print("ERROR: no ConductResearch tool_result in pushed stream", file=sys.stderr)
        return 2

    call_idx, call_ev = cr_calls[0]
    for res_idx, res_ev in cr_results:
        if res_ev.get("id") != call_ev.get("id"):
            continue
        if res_idx <= call_idx:
            print(
                f"ERROR: tool_result at {res_idx} not after tool_call at {call_idx}",
                file=sys.stderr,
            )
            return 3
        print(f"  OK: tool_call index {call_idx} < tool_result index {res_idx} (id={call_ev.get('id')!r})")
        return 0

    print("ERROR: could not pair tool_result id with tool_call", file=sys.stderr)
    return 4


if __name__ == "__main__":
    raise SystemExit(main())
