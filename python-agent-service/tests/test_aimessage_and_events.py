"""Diagnostic test: verify AIMessage structure and event flow.

Run with: pytest tests/test_aimessage_and_events.py -v -s
Requires: GOOGLE_API_KEY or ANTHROPIC_API_KEY in env.
"""

import asyncio
import json
import os


def test_aimessage_content_structure():
    """1) Verify why AIMessage may not contain thinking/text - LLM type and API."""
    from app.agents.deep_agent import get_model
    from app.parsers.deepagents_stream_adapter import \
        _extract_thinking_and_text
    from langchain_core.messages import HumanMessage

    model = get_model()
    model_name = getattr(model, "model_name", str(model))

    # Simple prompt that might trigger tool use
    msg = HumanMessage(content="Analyze this IP: 8.8.8.8")

    async def invoke_and_inspect():
        response = await model.ainvoke([msg])
        content = getattr(response, "content", None)
        additional = getattr(response, "additional_kwargs", None) or {}

        print("\n=== AIMessage Structure ===")
        print(f"Model: {model_name}")
        print(f"content type: {type(content)}")
        if isinstance(content, list):
            for i, block in enumerate(content):
                print(f"  block[{i}]: {json.dumps(block, default=str, ensure_ascii=False)[:200]}")
        else:
            print(f"  content: {str(content)[:300]}")
        print(f"additional_kwargs keys: {list(additional.keys())}")
        if "reasoning_content" in additional:
            print(f"  reasoning_content (first 200 chars): {str(additional['reasoning_content'])[:200]}")

        thinking, text = _extract_thinking_and_text(response)
        print(f"\n_extract_thinking_and_text result:")
        print(f"  thinking: {repr(thinking[:200]) if thinking else '(empty)'}")
        print(f"  text: {repr(text[:200]) if text else '(empty)'}")

        return thinking, text

    thinking, text = asyncio.run(invoke_and_inspect())

    # Conclusion: if thinking is empty, it's because the model/API doesn't return thinking blocks
    # or the format doesn't match our extractor
    if not thinking and not text:
        print("\n[CONCLUSION] Both thinking and text are empty - model may return only tool_calls")
    elif not thinking:
        print("\n[CONCLUSION] No thinking - model may not have thinking enabled (Gemini needs include_thoughts)")
    else:
        print("\n[CONCLUSION] Thinking content found - extractor works for this model")


def test_write_todos_to_task_plan_mapping():
    """2) Verify write_todos yields tool_call (no duplicate task_plan SSE)."""
    from unittest.mock import MagicMock

    from app.parsers.deepagents_stream_adapter import adapt_astream_to_sse
    from langchain_core.messages import AIMessage, HumanMessage

    # Simulate agent output: AIMessage with write_todos
    async def mock_astream(state, config, stream_mode="updates"):
        yield {
            "agent": {
                "messages": [
                    AIMessage(
                        content="",  # No thinking/text
                        tool_calls=[
                            {
                                "id": "wt-1",
                                "name": "write_todos",
                                "args": {
                                    "todos": [
                                        {"content": "Analyze IP 8.8.8.8", "status": "pending"},
                                        {"content": "Lookup threat intel", "status": "pending"},
                                    ]
                                },
                            },
                        ],
                    )
                ]
            }
        }
        # Tools node
        yield {
            "tools": {
                "messages": []  # Simplified
            }
        }

    agent = MagicMock()
    agent.astream = mock_astream
    agent.aget_state = MagicMock(return_value=None)

    events = []
    async def collect():
        async for e in adapt_astream_to_sse(agent, {"messages": []}, {}):
            events.append(e)

    asyncio.run(collect())

    task_plan_events = [e for e in events if e.get("type") == "task_plan"]
    tool_call_events = [e for e in events if e.get("type") == "tool_call" and e.get("toolName") == "write_todos"]

    print("\n=== write_todos -> task_plan mapping ===")
    print(f"Total events: {len(events)}")
    print(f"task_plan events: {len(task_plan_events)}")
    print(f"tool_call write_todos events: {len(tool_call_events)}")

    assert len(task_plan_events) == 0, "adapter should not emit task_plan; use write_todos tool_call"
    assert len(tool_call_events) >= 1
    if tool_call_events:
        plan = tool_call_events[0].get("toolInput", {})
        todos = plan.get("todos") or []
        print(f"write_todos todos count: {len(todos)}")

    if tool_call_events:
        print(f"tool_call write_todos toolInput: {str(tool_call_events[0].get('toolInput', {}))[:200]}")


def test_task_summary_source():
    """3) Document task_summary vs conclusion source (final_message_split path)."""
    print("\n=== task_summary vs conclusion source ===")
    print("Both from the same final main-agent AIMessage (one LLM completion).")
    print("task_summary: ## SM_TASK_DIGEST section (or heuristic first block).")
    print("conclusion:   ## SM_FULL_REPORT section (report-first preferred; or heuristic remainder / full text).")
    print("No separate task_multi_summary LLM call.")
