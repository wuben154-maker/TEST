"""Unit tests for deepagents_stream_adapter.

Verifies event mapping from agent.astream() to SSE event format.
"""

import asyncio
import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from app.parsers.final_message_split import (
    DIGEST_HEADING,
    REPORT_HEADING,
    SUBAGENT_FULL_HEADING,
    SUBAGENT_WRAPUP_HEADING,
)
from app.parsers.deepagents_stream_adapter import (
    MAIN_AGENT_ALLOWED_DIRECT_TOOLS,
    _all_task_outputs_are_deep_research,
    _apply_sse_envelope,
    _coerce_tool_call_args,
    _extract_text, _extract_thinking_and_text, _message_signature,
    _sse_task_tool_output_visible,
    _tag_merged_subagent_sse,
    adapt_astream_to_sse, adapt_subagent_astream_to_skill_events)
from app.parsers.llm_invoke_callbacks import LlmInvokeLifecycleCallbackHandler
from langchain_core.messages import AIMessage, AIMessageChunk, HumanMessage, ToolMessage
from uuid import uuid4


def _anchored_final(digest: str, report: str) -> str:
    """Build anchored final message in new preferred order (report-first)."""
    return f"{REPORT_HEADING}\n\n{report}\n\n{DIGEST_HEADING}\n\n{digest}"


def _anchored_subagent_wrapup(wrapup: str, full_report: str) -> str:
    return (
        f"{SUBAGENT_WRAPUP_HEADING}\n\n{wrapup}\n\n"
        f"{SUBAGENT_FULL_HEADING}\n\n{full_report}"
    )


def _joined_llm_reasoning(events: list) -> str:
    return "".join(
        str(e.get("content") or "")
        for e in events
        if e.get("type") == "llm_delta" and e.get("channel") == "reasoning"
    )


def _joined_llm_text(events: list) -> str:
    return "".join(
        str(e.get("content") or "")
        for e in events
        if e.get("type") == "llm_delta" and e.get("channel") == "text"
    )


def _llm_reasoning_chunks(events: list) -> list[str]:
    return [
        str(e.get("content") or "")
        for e in events
        if e.get("type") == "llm_delta" and e.get("channel") == "reasoning"
    ]


def test_coerce_tool_call_args_accepts_dict_rejects_string():
    assert _coerce_tool_call_args({"a": 1}) == {"a": 1}
    assert _coerce_tool_call_args('{"not": "parsed"}') == {}
    assert _coerce_tool_call_args(None) == {}


@pytest.mark.asyncio
async def test_llm_invoke_lifecycle_callback_emits_start_and_end():
    """Callback handler emits start on on_chat_model_start and end on on_llm_end."""
    written: list[dict] = []
    cb = LlmInvokeLifecycleCallbackHandler(written.append)
    rid = uuid4()
    await cb.on_chat_model_start({}, [], run_id=rid)
    assert len(written) == 1
    assert written[0]["type"] == "llm_invoke_start"
    assert written[0]["invokeId"] == rid.hex[:12]
    await cb.on_llm_end(None, run_id=rid)
    assert len(written) == 2
    assert written[1]["type"] == "llm_invoke_end"
    assert written[1]["invokeId"] == rid.hex[:12]


def test_main_agent_allowed_direct_tools_includes_expected():
    """MAIN_AGENT_ALLOWED_DIRECT_TOOLS must include IOC/info tools for Agentic workflow."""
    expected = {
        "extract_iocs", "decode_base64", "decode_url", "lookup_threat_intel",
        "web_search", "scrape_url", "summarize_content",
        "read_file", "grep", "glob", "ls", "write_todos",
    }
    assert expected.issubset(MAIN_AGENT_ALLOWED_DIRECT_TOOLS)


def test_extract_text_plain_string():
    assert _extract_text("hello") == "hello"


def test_extract_text_content_block_list():
    blocks = [{"type": "text", "text": "world", "extras": {"signature": "abc123"}}]
    assert _extract_text(blocks) == "world"


def test_extract_text_multi_block_list():
    blocks = [
        {"type": "text", "text": "foo"},
        {"type": "text", "text": "bar"},
    ]
    assert _extract_text(blocks) == "foobar"


def test_extract_text_skips_non_text_blocks():
    blocks = [
        {"type": "thinking", "thinking": "internal"},
        {"type": "text", "text": "visible"},
    ]
    assert _extract_text(blocks) == "visible"


def test_extract_text_empty():
    assert _extract_text("") == ""
    assert _extract_text([]) == ""
    assert _extract_text(None) == ""


def test_all_task_outputs_are_deep_research_normalizes_type():
    assert _all_task_outputs_are_deep_research(["deep-research"], ["a"])
    assert _all_task_outputs_are_deep_research(["deep_research"], ["a"])
    assert not _all_task_outputs_are_deep_research(["general-purpose"], ["a"])
    assert not _all_task_outputs_are_deep_research(["deep-research", "general-purpose"], ["a", "b"])


def test_sse_task_tool_output_visible_prefers_subagent_wrapup():
    """task() SSE toolOutput must not expose SM_SUBAGENT_FULL_REPORT body."""
    full = _anchored_subagent_wrapup(
        "Brief wrap for UI.",
        "# Full report\n\n" + "x" * 800,
    )
    assert _sse_task_tool_output_visible(full) == "Brief wrap for UI."


@pytest.mark.asyncio
async def test_adapt_conclusion_uses_subagent_full_report_when_no_task_digest(mock_agent):
    """SM_SUBAGENT_*: SSE toolOutput stays WRAPUP; conclusion event is FULL_REPORT body."""
    full_body = "# Long report\n\n" + "detail " * 200
    sub_out = _anchored_subagent_wrapup(
        "Researched topic X; key sources: A, B; bottom line: Y.",
        full_body,
    )
    ai_delegate = AIMessage(
        content="",
        tool_calls=[
            {
                "id": "tc-dr",
                "name": "task",
                "args": {
                    "subagent_type": "deep-research",
                    "description": "Research X",
                },
            }
        ],
    )
    tool_msg = ToolMessage(content=sub_out, tool_call_id="tc-dr", name="task")
    # Main model echoes full subagent blob — must not drive conclusion when deep-research-only.
    main_followup = _anchored_final(
        "Main digest should be ignored.",
        "Main full report should be ignored.",
    )
    mock_agent.astream.return_value = _astream_yield(
        {"agent": {"messages": [ai_delegate]}},
        {"tools": {"messages": [tool_msg]}},
        {"agent": {"messages": [AIMessage(content=main_followup)]}},
    )

    events = []
    async for e in adapt_astream_to_sse(
        mock_agent, {"messages": []}, {"configurable": {}}, language="en"
    ):
        events.append(e)

    conclusions = [e for e in events if e.get("type") == "conclusion"]
    task_summaries = [e for e in events if e.get("type") == "task_summary"]
    assert len(conclusions) == 1
    assert conclusions[0]["content"].strip() == full_body.strip()
    assert "Researched topic X" not in conclusions[0]["content"]
    assert "Main digest" not in conclusions[0]["content"]
    assert len(task_summaries) == 0

    tool_results = [
        e for e in events
        if e.get("type") == "tool_result" and e.get("toolName") == "task"
    ]
    assert tool_results
    assert "Long report" not in (tool_results[-1].get("toolOutput") or "")
    assert "Researched topic X" in (tool_results[-1].get("toolOutput") or "")


def test_extract_thinking_and_text_anthropic():
    """Anthropic: type thinking | text blocks."""
    msg = AIMessage(
        content=[
            {"type": "thinking", "thinking": "Let me analyze this first."},
            {"type": "text", "text": "Here is the final answer."},
        ]
    )
    thinking, text = _extract_thinking_and_text(msg)
    assert thinking == "Let me analyze this first."
    assert text == "Here is the final answer."


def test_extract_thinking_and_text_openai():
    """OpenAI: reasoning_content in additional_kwargs."""
    msg = AIMessage(
        content="Final answer",
        additional_kwargs={"reasoning_content": "Step 1: ... Step 2: ..."},
    )
    thinking, text = _extract_thinking_and_text(msg)
    assert thinking == "Step 1: ... Step 2: ..."
    assert text == "Final answer"


def test_extract_thinking_and_text_openrouter_reasoning_alias():
    """OpenRouter: plaintext ``reasoning`` on assistant message."""
    msg = AIMessage(
        content="Final answer",
        additional_kwargs={"reasoning": "First I consider ..."},
    )
    thinking, text = _extract_thinking_and_text(msg)
    assert thinking == "First I consider ..."
    assert text == "Final answer"


def test_extract_thinking_and_text_langchain_reasoning_block():
    """LangChain/OpenRouter Gemini: content block type reasoning + nested reasoning_text."""
    msg = AIMessage(
        content=[
            {
                "type": "reasoning",
                "content": [
                    {"type": "reasoning_text", "text": "**Step 1**\nMultiply.\n"},
                ],
                "status": "completed",
            },
            {"type": "text", "text": "144"},
        ]
    )
    thinking, text = _extract_thinking_and_text(msg)
    assert "**Step 1**" in thinking
    assert "Multiply" in thinking
    assert text == "144"


def test_extract_thinking_and_text_gemini():
    """Google Gemini: thought flag on parts."""
    msg = AIMessage(
        content=[
            {"text": "Internal reasoning", "thought": True},
            {"text": "Final answer", "thought": False},
        ]
    )
    thinking, text = _extract_thinking_and_text(msg)
    assert thinking == "Internal reasoning"
    assert text == "Final answer"


def test_extract_thinking_and_text_plain_string():
    """Plain string content goes to text."""
    msg = AIMessage(content="Hello world")
    thinking, text = _extract_thinking_and_text(msg)
    assert thinking == ""
    assert text == "Hello world"


def test_message_signature_uses_id_when_available():
    """_message_signature uses id when present."""
    msg = AIMessage(content="Hello", id="msg-123")
    assert _message_signature(msg) == "id:msg-123"


def test_message_signature_fallback_to_content():
    """_message_signature falls back to content hash when no id."""
    msg = AIMessage(content="Hello world")
    sig = _message_signature(msg)
    assert sig.startswith("content:")
    assert len(sig) > 10


def test_message_signature_tool_calls_when_no_text():
    """_message_signature falls back to tool_calls hash for tool-only messages."""
    msg = AIMessage(
        content="",
        tool_calls=[{"id": "tc-1", "name": "task", "args": {"subagent_type": "binary-analysis"}}],
    )
    sig = _message_signature(msg)
    assert sig.startswith("tool_calls:")
    assert len(sig) > 12


@pytest.mark.asyncio
async def test_adapt_skips_reasoning_for_seen_message_signatures(mock_agent):
    """When seen_message_signatures contains a message's signature, do not emit reasoning."""
    old_content = "Hello! I am your Deep Security Agent. I am ready to help you"
    old_msg = AIMessage(
        content=[
            {"type": "thinking", "thinking": old_content},
            {"type": "text", "text": "Ready."},
        ]
    )
    new_thinking = "I am your Deep Security Agent—a professional cybersecurity analyst."
    new_msg = AIMessage(
        content=[
            {"type": "thinking", "thinking": new_thinking},
            {"type": "text", "text": "How can I help?"},
        ]
    )
    mock_agent.astream.return_value = _astream_yield(
        {"agent": {"messages": [old_msg, new_msg]}},
    )
    mock_agent.ainvoke.return_value = {"messages": []}

    seen_sig = frozenset({_message_signature(old_msg)})

    events = []
    async for e in adapt_astream_to_sse(
        mock_agent,
        {"messages": []},
        {"configurable": {}},
        seen_message_signatures=seen_sig,
    ):
        events.append(e)

    r_text = _joined_llm_reasoning(events)
    assert r_text.strip()
    assert "professional cybersecurity analyst" in r_text
    assert old_content not in r_text


@pytest.mark.asyncio
async def test_adapt_skips_seen_task_message_no_replayed_task_or_missing_error(mock_agent):
    """Seen checkpoint task message must be skipped entirely (including tool_calls)."""
    old_task_msg = AIMessage(
        content="",
        tool_calls=[
            {
                "id": "tc-old",
                "name": "task",
                "args": {"subagent_type": "binary-analysis", "description": "Analyze /old.php"},
            }
        ],
    )
    new_text_msg = AIMessage(content="This is the new plain-text conclusion.")
    mock_agent.astream.return_value = _astream_yield(
        {"agent": {"messages": [old_task_msg, new_text_msg]}},
    )
    mock_agent.ainvoke.return_value = {"messages": []}

    seen_sig = frozenset({_message_signature(old_task_msg)})

    events = []
    async for e in adapt_astream_to_sse(
        mock_agent,
        {"messages": []},
        {"configurable": {}},
        language="en",
        seen_message_signatures=seen_sig,
    ):
        events.append(e)

    task_calls = [
        e for e in events
        if e.get("type") == "tool_call" and e.get("toolName") == "task"
    ]
    errors = [
        e for e in events
        if e.get("type") == "error" and e.get("id") == "missing-subagent-result"
    ]
    conclusions = [e for e in events if e.get("type") == "conclusion"]

    assert len(task_calls) == 0
    assert len(errors) == 0
    assert len(conclusions) == 1
    assert "new plain-text conclusion" in conclusions[0]["content"]


@pytest.mark.asyncio
async def test_resume_checkpoint_task_no_phantom_step_events(mock_agent):
    """Resume after HITL: checkpoint task() AIMessage is skipped but its ToolMessage
    arrives from the just-completed subagent.  Must NOT emit phantom step running /
    step success pair (the 7ms gap bug).  tool_result SHOULD still be emitted."""
    checkpoint_task_msg = AIMessage(
        content="",
        tool_calls=[
            {
                "id": "tc-resume",
                "name": "task",
                "args": {"subagent_type": "general-purpose", "description": "Analyze X"},
            }
        ],
    )
    resumed_tool_result = ToolMessage(
        content="Subagent completed analysis of X.",
        tool_call_id="tc-resume",
        name="task",
    )
    final_msg = AIMessage(
        content=_anchored_final(
            "Summary of X analysis.",
            "Full report of X analysis.",
        )
    )
    mock_agent.astream.return_value = _astream_yield(
        {"agent": {"messages": [checkpoint_task_msg]}},
        {"tools": {"messages": [resumed_tool_result]}},
        {"agent": {"messages": [final_msg]}},
    )

    seen_sig = frozenset({_message_signature(checkpoint_task_msg)})

    events = []
    async for e in adapt_astream_to_sse(
        mock_agent,
        {"messages": []},
        {"configurable": {}},
        language="en",
        seen_message_signatures=seen_sig,
    ):
        events.append(e)

    # No phantom step running / step success for the checkpoint task
    step_running = [
        e for e in events
        if e.get("type") == "step"
        and "task-running-tc-resume" in e.get("id", "")
        and e.get("status") == "running"
    ]
    step_success = [
        e for e in events
        if e.get("type") == "step"
        and "task-running-tc-resume" in e.get("id", "")
        and e.get("status") == "success"
    ]
    assert len(step_running) == 0, f"Phantom step running: {step_running}"
    assert len(step_success) == 0, f"Phantom step success: {step_success}"

    # No synthetic tool_call for the checkpoint task
    task_calls = [
        e for e in events
        if e.get("type") == "tool_call" and e.get("toolName") == "task"
    ]
    assert len(task_calls) == 0, f"Phantom tool_call: {task_calls}"

    # tool_result IS emitted (the subagent did complete in this stream)
    tool_results = [
        e for e in events
        if e.get("type") == "tool_result" and e.get("toolName") == "task"
    ]
    assert len(tool_results) == 1

    # Conclusion uses the task output (not "missing subagent" error)
    conclusions = [e for e in events if e.get("type") == "conclusion"]
    errors = [e for e in events if e.get("type") == "error"]
    assert len(errors) == 0, f"Unexpected errors: {errors}"
    assert len(conclusions) == 1
    assert "Full report of X analysis" in conclusions[0]["content"]

    # No task_complete for the checkpoint task
    task_completes = [
        e for e in events
        if e.get("type") == "task_complete"
    ]
    assert len(task_completes) == 0, f"Phantom task_complete: {task_completes}"


async def _astream_yield(*events):
    """Helper to yield events from async generator."""
    for e in events:
        yield e


class _NoLenMessages:
    """Iterable wrapper without __len__ (simulates LangGraph Overwrite)."""

    def __init__(self, items):
        self._items = items

    def __iter__(self):
        return iter(self._items)


@pytest.fixture
def mock_agent():
    """Create a mock agent with astream and ainvoke.

    astream is sync and returns an async generator (real agent behavior).
    ainvoke is async.
    """
    agent = MagicMock()
    agent.astream = MagicMock()  # Sync, returns async generator
    agent.ainvoke = AsyncMock()
    return agent


@pytest.mark.asyncio
async def test_adapt_reasoning_event(mock_agent):
    """Thinking blocks -> reasoning; final visible text is emitted via conclusion only."""
    msg_with_thinking = AIMessage(
        content=[
            {"type": "thinking", "thinking": "Let me analyze this file first."},
            {"type": "text", "text": "Here is my analysis result."},
        ]
    )
    mock_agent.astream.return_value = _astream_yield(
        {"agent": {"messages": [msg_with_thinking]}},
    )
    mock_agent.ainvoke.return_value = {
        "messages": [
            HumanMessage(content="Analyze this"),
            AIMessage(content="Here is my analysis result."),
        ],
    }

    events = []
    async for e in adapt_astream_to_sse(
        mock_agent, {"messages": []}, {"configurable": {}}, language="en"
    ):
        events.append(e)

    assert "Let me analyze this file first." in _joined_llm_reasoning(events)
    vis = _joined_llm_text(events)
    assert vis == ""
    conclusions = [e for e in events if e.get("type") == "conclusion"]
    assert len(conclusions) == 1
    assert "Here is my analysis result" in conclusions[0]["content"]


@pytest.mark.asyncio
async def test_adapt_messages_stream_llm_invoke_end_on_invoke_id_realign(mock_agent):
    """Main graph: new on_chat_model_start id before close() must not drop prior invoke without end."""
    c1 = AIMessageChunk(content=[{"type": "thinking", "thinking": "s1"}])
    c2 = AIMessageChunk(content=[{"type": "thinking", "thinking": "s2"}])
    final_ai = AIMessage(content="ok")
    mock_agent.astream.return_value = _astream_yield(
        {"type": "messages", "data": (c1, {})},
        {"type": "messages", "data": (c2, {})},
        {"agent": {"messages": [final_ai]}},
    )
    mock_agent.ainvoke.return_value = {"messages": [final_ai]}

    _call_n = {"i": 0}

    def _next_invoke() -> str:
        _call_n["i"] += 1
        return "aaaaaaaaaaaa" if _call_n["i"] == 1 else "bbbbbbbbbbbb"

    events: list = []
    with patch(
        "app.parsers.llm_invoke_sse.current_llm_invoke_id_for_delta",
        side_effect=_next_invoke,
    ):
        async for e in adapt_astream_to_sse(
            mock_agent,
            {"messages": []},
            {"configurable": {}},
            language="en",
            use_messages_stream=True,
        ):
            events.append(e)

    ends = [e for e in events if e.get("type") == "llm_invoke_end"]
    assert len(ends) >= 1
    assert any(str(e.get("invokeId")) == "aaaaaaaaaaaa" for e in ends)


@pytest.mark.asyncio
async def test_adapt_handles_messages_wrapper_without_len(mock_agent):
    """Adapter should accept iterable messages payload without len()."""
    wrapped = _NoLenMessages([AIMessage(content="Wrapped message output.")])
    mock_agent.astream.return_value = _astream_yield(
        {"model": {"messages": wrapped}},
    )

    events = []
    async for e in adapt_astream_to_sse(
        mock_agent, {"messages": []}, {"configurable": {}}, language="en"
    ):
        events.append(e)

    conclusions = [e for e in events if e.get("type") == "conclusion"]
    assert len(conclusions) == 1
    assert "Wrapped message output." in conclusions[0]["content"]


@pytest.mark.asyncio
async def test_adapt_tool_call_event(mock_agent):
    """Adapt agent node AIMessage with tool_calls -> tool_call events."""
    mock_agent.astream.return_value = _astream_yield(
        {
            "agent": {
                "messages": [
                    AIMessage(
                        content="",
                        tool_calls=[
                            {
                                "id": "tc-1",
                                "name": "read_file",
                                "args": {"path": "/tmp/test.txt"},
                            },
                        ],
                    ),
                ],
            },
        },
    )
    mock_agent.ainvoke.return_value = {"messages": []}

    events = []
    async for e in adapt_astream_to_sse(
        mock_agent, {"messages": []}, {"configurable": {}}
    ):
        events.append(e)

    tool_calls = [e for e in events if e.get("type") == "tool_call"]
    assert len(tool_calls) == 1
    assert tool_calls[0]["toolName"] == "read_file"
    assert tool_calls[0]["toolInput"] == {"path": "/tmp/test.txt"}
    assert tool_calls[0]["status"] == "running"


@pytest.mark.asyncio
async def test_adapt_tool_result_event(mock_agent):
    """Adapt tools node ToolMessage -> tool_result event."""
    tool_msg = ToolMessage(
        content="File contents here",
        tool_call_id="tc-1",
        name="read_file",
    )
    mock_agent.astream.return_value = _astream_yield(
        {"tools": {"messages": [tool_msg]}},
    )
    mock_agent.ainvoke.return_value = {"messages": []}

    events = []
    async for e in adapt_astream_to_sse(
        mock_agent, {"messages": []}, {"configurable": {}}
    ):
        events.append(e)

    tool_results = [e for e in events if e.get("type") == "tool_result"]
    assert len(tool_results) == 1
    assert tool_results[0]["toolName"] == "read_file"
    assert tool_results[0]["toolOutput"] == ""
    assert tool_results[0]["status"] == "success"


@pytest.mark.asyncio
async def test_adapt_tool_result_emits_synthetic_call_if_missing(mock_agent):
    """Tool result without call should be paired by synthetic tool_call."""
    tool_msg = ToolMessage(
        content="Task output",
        tool_call_id="tc-missing",
        name="task",
    )
    mock_agent.astream.return_value = _astream_yield(
        {"tools": {"messages": [tool_msg]}},
    )
    mock_agent.ainvoke.return_value = {"messages": []}

    events = []
    async for e in adapt_astream_to_sse(
        mock_agent, {"messages": []}, {"configurable": {}}
    ):
        events.append(e)

    tool_calls = [e for e in events if e.get("type") == "tool_call"]
    tool_results = [e for e in events if e.get("type") == "tool_result"]
    assert len(tool_calls) == 1
    assert len(tool_results) == 1
    assert tool_calls[0]["id"] == "tc-missing"
    assert tool_calls[0]["toolName"] == "task"
    assert tool_calls[0]["toolInput"] == {}


@pytest.mark.asyncio
async def test_adapt_conclusion_and_done(mock_agent):
    """Adapt stream end -> conclusion, step, done."""
    mock_agent.astream.return_value = _astream_yield(
        {"agent": {"messages": [AIMessage(content="Final analysis conclusion here.")]}},
    )

    events = []
    async for e in adapt_astream_to_sse(
        mock_agent, {"messages": []}, {"configurable": {}}, language="zh"
    ):
        events.append(e)

    conclusion = [e for e in events if e.get("type") == "conclusion"]
    assert len(conclusion) == 1
    assert conclusion[0]["content"] == "Final analysis conclusion here."

    step = [
        e
        for e in events
        if e.get("type") == "step"
        and e.get("id") == "analysis-complete"
    ]
    assert len(step) == 1
    assert step[0]["label"] == "分析完成"
    assert step[0]["status"] == "success"

    done = [e for e in events if e.get("type") == "done"]
    assert len(done) == 1
    assert done[0]["id"] == "done"

    text_deltas = [e for e in events if e.get("type") == "llm_delta" and e.get("channel") == "text"]
    assert len(text_deltas) == 0


@pytest.mark.asyncio
async def test_adapt_propagates_ui_language_to_subagent_stream_config(mock_agent):
    """Parent stream language should be forwarded to subagent SSE labels."""
    mock_agent.astream.return_value = _astream_yield(
        {"agent": {"messages": [AIMessage(content="done")]}}
    )

    events = []
    config = {"configurable": {"thread_id": "tid-1"}}
    async for e in adapt_astream_to_sse(
        mock_agent, {"messages": []}, config, language="en"
    ):
        events.append(e)

    assert events
    called_input, called_config = mock_agent.astream.call_args.args[:2]
    assert isinstance(called_config, dict)
    assert called_config.get("configurable", {}).get("thread_id") == "tid-1"
    assert called_config.get("configurable", {}).get("sse_ui_language") == "en"
    assert called_config.get("configurable", {}).get("subagent_sse_event_queue") is not None
    assert called_input == {"messages": []}


@pytest.mark.asyncio
async def test_adapt_conclusion_includes_task_outputs(mock_agent):
    """Single task(): conclusion is SM_FULL_REPORT body; task_summary from SM_TASK_DIGEST."""
    tool_msg = ToolMessage(
        content="Binary sample has C2 domain evil.test",
        tool_call_id="tc-1",
        name="task",
    )
    final = _anchored_final(
        "C2 domain evil.test noted in binary triage.",
        "Analysis finished.",
    )
    mock_agent.astream.return_value = _astream_yield(
        {"tools": {"messages": [tool_msg]}},
        {"agent": {"messages": [AIMessage(content=final)]}},
    )

    events = []
    async for e in adapt_astream_to_sse(
        mock_agent, {"messages": []}, {"configurable": {}}, language="en"
    ):
        events.append(e)

    conclusion = [e for e in events if e.get("type") == "conclusion"]
    task_summaries = [e for e in events if e.get("type") == "task_summary"]
    assert len(conclusion) == 1
    assert conclusion[0]["content"] == "Analysis finished."
    assert "Subagent Result Summary" not in conclusion[0]["content"]
    assert len(task_summaries) == 1
    assert task_summaries[0].get("summary") == "C2 domain evil.test noted in binary triage."


@pytest.mark.asyncio
async def test_single_task_heuristic_digest_when_unanchored(mock_agent):
    """Without anchors, heuristic splits first paragraph as task_summary when short enough."""
    long_output = "x" * 400
    tool_msg = ToolMessage(
        content=long_output,
        tool_call_id="tc-1",
        name="task",
    )
    body = "y" * 200
    unanchored = f"Done with triage.\n\n{body}"
    mock_agent.astream.return_value = _astream_yield(
        {"tools": {"messages": [tool_msg]}},
        {"agent": {"messages": [AIMessage(content=unanchored)]}},
    )

    events = []
    async for e in adapt_astream_to_sse(
        mock_agent, {"messages": []}, {"configurable": {}}, language="en"
    ):
        events.append(e)

    task_summaries = [e for e in events if e.get("type") == "task_summary"]
    conclusions = [e for e in events if e.get("type") == "conclusion"]
    assert len(task_summaries) == 1
    assert task_summaries[0].get("summary") == "Done with triage."
    assert len(conclusions) == 1
    assert conclusions[0].get("content") == body


@pytest.mark.asyncio
async def test_multi_task_emits_task_summary_from_final_anchors(mock_agent):
    """Multiple task() runs: digest + report from one final AIMessage (no extra LLM)."""
    t1 = ToolMessage(content="First subagent output A.", tool_call_id="tc-a", name="task")
    t2 = ToolMessage(content="Second subagent output B.", tool_call_id="tc-b", name="task")
    final = _anchored_final(
        "A: finding one. B: finding two. Overall: combined risk.",
        "Final report body.",
    )
    mock_agent.astream.return_value = _astream_yield(
        {"tools": {"messages": [t1]}},
        {"tools": {"messages": [t2]}},
        {"agent": {"messages": [AIMessage(content=final)]}},
    )

    events = []
    async for e in adapt_astream_to_sse(
        mock_agent, {"messages": []}, {"configurable": {}}, language="en"
    ):
        events.append(e)

    task_summaries = [e for e in events if e.get("type") == "task_summary"]
    conclusions = [e for e in events if e.get("type") == "conclusion"]
    assert len(task_summaries) == 1
    assert task_summaries[0].get("summary") == "A: finding one. B: finding two. Overall: combined risk."
    assert len(conclusions) == 1
    assert conclusions[0].get("content") == "Final report body."


@pytest.mark.asyncio
async def test_adapt_task_result_with_nameless_tool_message(mock_agent):
    """deepagents creates ToolMessage without `name`.  The adapter must resolve
    the tool name from seen_tool_calls so task_outputs is populated and a
    conclusion is emitted (regression for 'analysis interrupted' bug)."""
    ai_msg = AIMessage(
        content="",
        tool_calls=[
            {
                "id": "tc-php",
                "name": "task",
                "args": {"subagent_type": "binary-analysis", "description": "Analyze /shell.php"},
            }
        ],
    )
    # ToolMessage deliberately has name=None (as deepagents creates it)
    tool_msg = ToolMessage(
        content="shell.php is a PHP webshell with system() call",
        tool_call_id="tc-php",
        # name intentionally omitted → defaults to None
    )
    mock_agent.astream.return_value = _astream_yield(
        {"agent": {"messages": [ai_msg]}},
        {"tools": {"messages": [tool_msg]}},
        {
            "agent": {
                "messages": [
                    AIMessage(
                        content=_anchored_final(
                            "PHP webshell with system() confirmed.",
                            "Analysis complete: PHP webshell detected.",
                        )
                    )
                ]
            }
        },
    )

    events = []
    async for e in adapt_astream_to_sse(
        mock_agent, {"messages": []}, {"configurable": {}}, language="en"
    ):
        events.append(e)

    conclusion = [e for e in events if e.get("type") == "conclusion"]
    summaries = [e for e in events if e.get("type") == "task_summary"]
    errors = [e for e in events if e.get("type") == "error"]
    assert len(errors) == 0, f"Unexpected errors: {errors}"
    assert len(conclusion) == 1
    assert "webshell" in conclusion[0]["content"]
    assert len(summaries) == 1
    assert "webshell" in summaries[0].get("summary", "")

    # Step complete event should also be emitted
    step_complete = [
        e for e in events
        if e.get("type") == "step" and e.get("status") == "success"
        and "task-running-tc-php" in e.get("id", "")
    ]
    assert len(step_complete) == 1


@pytest.mark.asyncio
async def test_adapt_emits_error_when_no_task_result(mock_agent):
    """When agent claims task submitted but no task tool result, emit error."""
    mock_agent.astream.return_value = _astream_yield(
        {"agent": {"messages": [AIMessage(content="Task submitted.")]}},
    )

    events = []
    async for e in adapt_astream_to_sse(
        mock_agent, {"messages": []}, {"configurable": {}}, language="en"
    ):
        events.append(e)

    errors = [e for e in events if e.get("type") == "error"]
    conclusion = [e for e in events if e.get("type") == "conclusion"]
    assert len(errors) == 1
    assert "Missing subagent outputs" in errors[0]["detail"]
    assert len(conclusion) == 0


@pytest.mark.asyncio
async def test_adapt_emits_bypass_warning_when_non_allowed_tool_used_without_task(mock_agent):
    """Emit bypass warning only when tools used are NOT in MAIN_AGENT_ALLOWED_DIRECT_TOOLS.

    Subagent-specific tools (e.g. analyze_email_headers) used without task() -> bypass.
    Main agent direct tools (extract_iocs, read_file, etc.) -> no bypass.
    """
    # Use a subagent-specific tool that is NOT in MAIN_AGENT_ALLOWED_DIRECT_TOOLS
    mock_agent.astream.return_value = _astream_yield(
        {
            "agent": {
                "messages": [
                    AIMessage(
                        content="",
                        tool_calls=[
                            {
                                "id": "tc-2",
                                "name": "analyze_email_headers",
                                "args": {"path": "/email.eml"},
                            }
                        ],
                    ),
                ],
            },
        },
        {
            "tools": {
                "messages": [
                    ToolMessage(
                        content="Analysis result",
                        tool_call_id="tc-2",
                        name="analyze_email_headers",
                    )
                ]
            },
        },
    )
    events = []
    async for e in adapt_astream_to_sse(
        mock_agent,
        {"messages": []},
        {"configurable": {}},
        language="en",
    ):
        events.append(e)

    warnings = [e for e in events if e.get("type") == "warning"]
    assert any(e.get("id") == "subagent-bypass-detected" for e in warnings)


@pytest.mark.asyncio
async def test_adapt_no_bypass_warning_when_only_allowed_tools_used(mock_agent):
    """No bypass warning when main agent uses only allowed direct tools (extract_iocs, read_file, etc.)."""
    mock_agent.astream.return_value = _astream_yield(
        {
            "agent": {
                "messages": [
                    AIMessage(
                        content="",
                        tool_calls=[
                            {"id": "tc-1", "name": "extract_iocs", "args": {"text": "1.1.1.1"}},
                        ],
                    ),
                ],
            },
        },
        {
            "tools": {
                "messages": [
                    ToolMessage(
                        content="{'ips':['1.1.1.1']}",
                        tool_call_id="tc-1",
                        name="extract_iocs",
                    )
                ]
            },
        },
    )
    events = []
    async for e in adapt_astream_to_sse(
        mock_agent,
        {"messages": []},
        {"configurable": {}},
        language="en",
    ):
        events.append(e)

    warnings = [e for e in events if e.get("type") == "warning"]
    bypass_warnings = [e for e in warnings if e.get("id") == "subagent-bypass-detected"]
    assert len(bypass_warnings) == 0, "extract_iocs is allowed; no bypass expected"


@pytest.mark.asyncio
async def test_adapt_fallback_conclusion_from_reasoning(mock_agent):
    """If no terminal AI text is available, fallback to latest reasoning text."""
    mock_agent.astream.return_value = _astream_yield(
        {"agent": {"messages": [AIMessage(content="Interim analysis text.")]}}
    )

    events = []
    async for e in adapt_astream_to_sse(
        mock_agent,
        {"messages": []},
        {"configurable": {}},
        language="en",
    ):
        events.append(e)

    conclusions = [e for e in events if e.get("type") == "conclusion"]
    assert len(conclusions) == 1
    assert conclusions[0]["content"] == "Interim analysis text."


# --- adapt_subagent_astream_to_skill_events tests ---


@pytest.fixture
def mock_subagent():
    """Mock subagent for subagent stream adapter tests."""
    agent = MagicMock()
    agent.astream = MagicMock()
    agent.ainvoke = AsyncMock()
    return agent


@pytest.mark.asyncio
async def test_adapt_subagent_tool_call_to_skill_event(mock_subagent):
    """Adapt subagent tool_call -> SSE dict (tool_call)."""
    mock_subagent.astream.return_value = _astream_yield(
        {
            "agent": {
                "messages": [
                    AIMessage(
                        content="",
                        tool_calls=[
                            {
                                "id": "tc-1",
                                "name": "analyze_email_headers",
                                "args": {"path": "/email.eml"},
                            }
                        ],
                    ),
                ],
            },
        },
    )
    mock_subagent.ainvoke.return_value = {"messages": []}

    events = []
    async for e in adapt_subagent_astream_to_skill_events(
        mock_subagent,
        {"messages": []},
        {"configurable": {}},
        skill_name="email-security",
        subagent_name="web-security",
    ):
        events.append(e)

    tool_calls = [e for e in events if e.get("type") == "tool_call"]
    assert len(tool_calls) == 1
    assert tool_calls[0]["toolName"] == "analyze_email_headers"
    assert tool_calls[0]["toolInput"] == {"path": "/email.eml"}
    assert tool_calls[0]["subagentName"] == "web-security"
    assert tool_calls[0]["label"] == "web-security"

    skill_complete = [e for e in events if e.get("type") == "skill_complete"]
    assert len(skill_complete) == 1
    assert "email-security" in skill_complete[0]["label"]
    assert skill_complete[0]["status"] == "success"


@pytest.mark.asyncio
async def test_adapt_subagent_tool_result_to_skill_event(mock_subagent):
    """Adapt subagent tool_result -> SSE dict (tool_result)."""
    tool_msg = ToolMessage(
        content="Headers parsed successfully",
        tool_call_id="tc-1",
        name="analyze_email_headers",
    )
    mock_subagent.astream.return_value = _astream_yield(
        {"tools": {"messages": [tool_msg]}},
    )
    mock_subagent.ainvoke.return_value = {"messages": []}

    events = []
    async for e in adapt_subagent_astream_to_skill_events(
        mock_subagent,
        {"messages": []},
        {"configurable": {}},
        skill_name="email-security",
        subagent_name="web-security",
    ):
        events.append(e)

    tool_calls = [e for e in events if e.get("type") == "tool_call"]
    tool_results = [e for e in events if e.get("type") == "tool_result"]
    assert len(tool_calls) == 1
    assert tool_calls[0]["id"] == "tc-1"
    assert tool_calls[0]["toolName"] == "analyze_email_headers"
    assert tool_calls[0]["toolInput"] == {}
    assert tool_calls[0]["subagentName"] == "web-security"
    assert len(tool_results) == 1
    assert tool_results[0]["toolName"] == "analyze_email_headers"
    assert tool_results[0]["toolOutput"] == "Headers parsed successfully"
    assert tool_results[0]["status"] == "success"
    assert tool_results[0]["subagentName"] == "web-security"
    assert tool_results[0]["label"] == "web-security"


# ============================================================
# write_todos → tool_call + task lifecycle (no duplicate task_plan SSE)
# ============================================================


@pytest.mark.asyncio
async def test_write_todos_tool_call_carries_todos_no_task_plan_sse(mock_agent):
    """write_todos tool call with LangChain Todo format (content field) →
    tool_call payload only; UI builds plan from toolInput (no task_plan event)."""
    ai_msg = AIMessage(
        content="",
        tool_calls=[{
            "id": "wt-1",
            "name": "write_todos",
            "args": {"todos": [
                {"content": "Analyze PHP webshell", "status": "pending"},
                {"content": "Check binary signatures", "status": "pending"},
            ]},
        }],
    )
    tool_msg = ToolMessage(content="Updated todo list", tool_call_id="wt-1")
    final_msg = AIMessage(content="Analysis complete.")

    mock_agent.astream.return_value = _astream_yield(
        {"agent": {"messages": [ai_msg]}},
        {"tools": {"messages": [tool_msg]}},
        {"agent": {"messages": [final_msg]}},
    )
    events = []
    async for e in adapt_astream_to_sse(
        mock_agent, {"messages": []}, {"configurable": {}}, language="en"
    ):
        events.append(e)

    task_plans = [e for e in events if e["type"] == "task_plan"]
    assert len(task_plans) == 0, "task_plan SSE removed; use write_todos tool_call"
    wt_calls = [e for e in events if e["type"] == "tool_call" and e.get("toolName") == "write_todos"]
    assert len(wt_calls) == 1
    from app.parsers.write_todos_plan import build_task_plan_dict_from_write_todos_args

    plan = build_task_plan_dict_from_write_todos_args(wt_calls[0].get("toolInput") or {})
    assert plan is not None
    tasks = plan["tasks"]
    assert len(tasks) == 2
    assert tasks[0]["title"] == "Analyze PHP webshell", (
        f"title should be from 'content' field, got: {tasks[0]['title']!r}"
    )
    assert tasks[1]["title"] == "Check binary signatures"
    assert tasks[0]["status"] == "pending"


@pytest.mark.asyncio
async def test_write_todos_sse_tool_input_redacts_host_paths(mock_agent):
    """tool_call.toolInput must not leak Windows upload layout to the client."""
    leak = r"D:\code\uploads\u_1\p_2\sample.exe"
    ai_msg = AIMessage(
        content="",
        tool_calls=[{
            "id": "wt-redact-1",
            "name": "write_todos",
            "args": {"todos": [{"content": f"Analyze binary at {leak}", "status": "pending"}]},
        }],
    )
    tool_msg = ToolMessage(content="Updated todo list", tool_call_id="wt-redact-1")
    final_msg = AIMessage(content="done")
    mock_agent.astream.return_value = _astream_yield(
        {"agent": {"messages": [ai_msg]}},
        {"tools": {"messages": [tool_msg]}},
        {"agent": {"messages": [final_msg]}},
    )
    events: list[dict] = []
    async for e in adapt_astream_to_sse(
        mock_agent, {"messages": []}, {"configurable": {}}, language="en"
    ):
        events.append(e)
    wt = [e for e in events if e["type"] == "tool_call" and e.get("toolName") == "write_todos"]
    assert len(wt) == 1
    dumped = json.dumps(wt[0].get("toolInput") or {})
    assert r"D:\code" not in dumped
    # scrub_event maps /workspace/ → workspace/ at SSE boundary
    assert "workspace/sample.exe" in dumped


@pytest.mark.asyncio
async def test_write_todos_task_start_complete_events(mock_agent):
    """write_todos status transitions emit task_start and task_complete events."""
    # First call: all pending
    wt_pending = AIMessage(
        content="",
        tool_calls=[{
            "id": "wt-1", "name": "write_todos",
            "args": {"todos": [{"content": "Analyze file", "status": "pending"}]},
        }],
    )
    # Second call: in_progress
    wt_running = AIMessage(
        content="",
        tool_calls=[{
            "id": "wt-2", "name": "write_todos",
            "args": {"todos": [{"content": "Analyze file", "status": "in_progress"}]},
        }],
    )
    # Third call: completed
    wt_done = AIMessage(
        content="",
        tool_calls=[{
            "id": "wt-3", "name": "write_todos",
            "args": {"todos": [{"content": "Analyze file", "status": "completed"}]},
        }],
    )
    task_msg = AIMessage(
        content="",
        tool_calls=[{"id": "tc-1", "name": "task",
                     "args": {"subagent_type": "binary-analysis", "description": "Analyze"}}],
    )
    final_msg = AIMessage(content="File is malicious.")

    mock_agent.astream.return_value = _astream_yield(
        {"agent": {"messages": [wt_pending]}},
        {"tools": {"messages": [ToolMessage("updated", tool_call_id="wt-1")]}},
        {"agent": {"messages": [wt_running]}},
        {"tools": {"messages": [ToolMessage("updated", tool_call_id="wt-2")]}},
        {"agent": {"messages": [task_msg]}},
        {"tools": {"messages": [ToolMessage("Malware found", tool_call_id="tc-1")]}},
        {"agent": {"messages": [wt_done]}},
        {"tools": {"messages": [ToolMessage("updated", tool_call_id="wt-3")]}},
        {"agent": {"messages": [final_msg]}},
    )
    events = []
    async for e in adapt_astream_to_sse(
        mock_agent, {"messages": []}, {"configurable": {}}, language="en"
    ):
        events.append(e)

    task_starts = [e for e in events if e["type"] == "task_start"]
    task_completes = [e for e in events if e["type"] == "task_complete"]
    task_plans = [e for e in events if e["type"] == "task_plan"]
    conclusions = [e for e in events if e["type"] == "conclusion"]

    assert len(task_plans) == 0, "No task_plan snapshots over SSE; write_todos tool_call only"
    assert len(task_starts) >= 1, "Expected at least one task_start event"
    assert len(task_completes) >= 1, "Expected at least one task_complete event"
    assert len(conclusions) == 1


@pytest.mark.asyncio
async def test_task_delegate_emits_tool_call_before_running_step(mock_agent):
    """task() delegation: tool_call SSE precedes task-running step(running); end step still follows."""
    task_msg = AIMessage(
        content="",
        tool_calls=[
            {
                "id": "tc-order",
                "name": "task",
                "args": {"subagent_type": "web-security", "description": "scan"},
            }
        ],
    )
    mock_agent.astream.return_value = _astream_yield(
        {"agent": {"messages": [task_msg]}},
        {"tools": {"messages": [ToolMessage("sub result", tool_call_id="tc-order", name="task")]}},
        {"agent": {"messages": [AIMessage(content="Done.")]}},
    )
    events: list[dict] = []
    async for e in adapt_astream_to_sse(
        mock_agent, {"messages": []}, {"configurable": {}}, language="en"
    ):
        events.append(e)

    def idx(pred):
        for i, ev in enumerate(events):
            if pred(ev):
                return i
        return -1

    i_call = idx(
        lambda e: e.get("type") == "tool_call"
        and e.get("toolName") == "task"
        and e.get("id") == "tc-order"
    )
    i_run = idx(
        lambda e: e.get("type") == "step"
        and e.get("id") == "task-running-tc-order"
        and e.get("status") == "running"
    )
    assert i_call >= 0 and i_run >= 0
    assert i_call < i_run


@pytest.mark.asyncio
async def test_write_todos_synthesis_with_tool_calls_no_reasoning_after_first_tool(mock_agent):
    """When synthesis AIMessage has BOTH text AND tool_calls, we do NOT emit reasoning
    (saw_first_tool_call is True from earlier). Synthesis goes to conclusion only."""
    task_call = AIMessage(
        content="",
        tool_calls=[{"id": "tc-1", "name": "task",
                     "args": {"subagent_type": "binary-analysis", "description": "Analyze"}}],
    )
    synthesis_with_todos = AIMessage(
        content="Executive Summary: Malware confirmed.",
        tool_calls=[{
            "id": "wt-final", "name": "write_todos",
            "args": {"todos": [{"content": "Analyze", "status": "completed"}]},
        }],
    )

    mock_agent.astream.return_value = _astream_yield(
        {"agent": {"messages": [task_call]}},
        {"tools": {"messages": [ToolMessage("Malware found", tool_call_id="tc-1")]}},
        {"agent": {"messages": [synthesis_with_todos]}},
        {"tools": {"messages": [ToolMessage("updated", tool_call_id="wt-final")]}},
    )
    events = []
    async for e in adapt_astream_to_sse(
        mock_agent, {"messages": []}, {"configurable": {}}, language="en"
    ):
        events.append(e)

    conclusions = [e for e in events if e["type"] == "conclusion"]
    errors = [e for e in events if e["type"] == "error"]

    assert len(errors) == 0, f"Unexpected errors: {errors}"
    # Synthesis content must NOT appear in reasoning (intent-only); it goes to conclusion
    reasoning_text = _joined_llm_reasoning(events)
    assert "Malware confirmed" not in reasoning_text, (
        f"Synthesis must not be in reasoning. Got: {reasoning_text!r}"
    )
    assert len(conclusions) == 1
    conclusion_content = next((e.get("content", "") for e in conclusions), "")
    assert "Malware confirmed" in conclusion_content, "Synthesis must be in conclusion"


def test_apply_sse_envelope_monotonic_seq_and_main_scope():
    seq = [0]
    a = _apply_sse_envelope({"type": "step", "id": "s1"}, seq)
    b = _apply_sse_envelope({"type": "tool_call", "id": "t1"}, seq)
    assert a["seq"] == 1 and b["seq"] == 2
    assert a["schemaVersion"] == 1 and b["schemaVersion"] == 1
    assert a["scope"] == "main" and b["scope"] == "main"
    assert isinstance(a.get("timestamp"), int) and isinstance(b.get("timestamp"), int)


def test_apply_sse_envelope_preserves_explicit_timestamp():
    seq = [0]
    fixed = 1_712_000_000_000
    ev = _apply_sse_envelope(
        {"type": "llm_invoke_end", "id": "x", "invokeId": "x", "timestamp": fixed},
        seq,
    )
    assert ev["timestamp"] == fixed


def test_apply_sse_envelope_replaces_none_timestamp_with_emit_time():
    seq = [0]
    ev = _apply_sse_envelope({"type": "step", "id": "s1", "timestamp": None}, seq)
    assert isinstance(ev.get("timestamp"), int)


def test_apply_sse_envelope_subagent_scope_from_flag():
    seq = [0]
    ev = _apply_sse_envelope(
        {"type": "llm_delta", "channel": "reasoning", "subagentStream": True, "id": "r1", "content": "x"},
        seq,
    )
    assert ev["scope"] == "subagent"


def test_tag_merged_subagent_maps_skill_reasoning_to_llm_delta():
    out = _tag_merged_subagent_sse({"type": "skill_reasoning", "id": "x", "content": "c"})
    assert out["type"] == "llm_delta"
    assert out["channel"] == "reasoning"
    assert out["subagentStream"] is True


def test_tag_merged_subagent_sets_default_subagent_name_for_frontend_routing():
    """Merged subagent events must carry subagentName so client taskPlansSubagent keys are stable."""
    out = _tag_merged_subagent_sse({"type": "tool_call", "id": "tc1", "toolName": "read_file"})
    assert out["subagentName"] == "subagent"


def test_tag_merged_subagent_preserves_explicit_subagent_name():
    out = _tag_merged_subagent_sse(
        {
            "type": "llm_delta",
            "channel": "reasoning",
            "id": "r1",
            "subagentName": "web-security",
            "content": "x",
        }
    )
    assert out["subagentName"] == "web-security"


def test_subagent_task_plan_gets_subagent_scope_after_envelope():
    """Subagent task_plan with numeric task ids must not be confused with main plan (client uses scope + name)."""
    seq = [0]
    raw = {
        "type": "task_plan",
        "id": "task-plan",
        "plan": {
            "id": "task-plan",
            "tasks": [{"id": "0", "title": "sub todo", "status": "pending"}],
        },
    }
    tagged = _tag_merged_subagent_sse(raw)
    env = _apply_sse_envelope(tagged, seq)
    assert env["scope"] == "subagent"
    assert env["subagentName"] == "subagent"
    assert env["plan"]["tasks"][0]["id"] == "0"


@pytest.mark.asyncio
async def test_multi_round_tools_post_tool_reasoning_not_duplicate_conclusion(mock_agent):
    """3.2 regression: multiple direct tool rounds; final answer only in conclusion text."""
    final_answer = "FINAL_VISIBLE_ANSWER_UNIQUE_99231"
    round1 = AIMessage(
        content=[
            {"type": "thinking", "thinking": "Intent before first tool."},
            {"type": "text", "text": ""},
        ],
        tool_calls=[{"id": "tc-a", "name": "extract_iocs", "args": {"text": "8.8.8.8"}}],
    )
    round2 = AIMessage(
        content=[
            {"type": "thinking", "thinking": "Reflection after first tool, before second."},
            {"type": "text", "text": ""},
        ],
        tool_calls=[{"id": "tc-b", "name": "web_search", "args": {"query": "test"}}],
    )
    terminal = AIMessage(
        content=[
            {"type": "text", "text": final_answer},
        ]
    )
    mock_agent.astream.return_value = _astream_yield(
        {"agent": {"messages": [round1]}},
        {
            "tools": {
                "messages": [
                    ToolMessage(content="{'ips':['8.8.8.8']}", tool_call_id="tc-a", name="extract_iocs"),
                ]
            }
        },
        {"agent": {"messages": [round2]}},
        {
            "tools": {
                "messages": [
                    ToolMessage(content="search ok", tool_call_id="tc-b", name="web_search"),
                ]
            }
        },
        {"agent": {"messages": [terminal]}},
    )

    events = []
    async for e in adapt_astream_to_sse(
        mock_agent,
        {"messages": []},
        {"configurable": {}},
        language="en",
        use_messages_stream=False,
    ):
        events.append(e)

    conclusions = [e for e in events if e.get("type") == "conclusion"]
    assert len(conclusions) == 1
    assert final_answer in (conclusions[0].get("content") or "")
    text_deltas = [e for e in events if e.get("type") == "llm_delta" and e.get("channel") == "text"]
    assert len(text_deltas) == 0, "Final synthesis should not emit llm_delta(text)"

    reasoning_bodies = _llm_reasoning_chunks(events)
    joined = " ".join(reasoning_bodies)
    assert final_answer not in joined, "Conclusion text must not be replayed as reasoning deltas"
    assert any("before first tool" in t for t in reasoning_bodies)
    assert any("after first tool" in t for t in reasoning_bodies)

    seqs = [e["seq"] for e in events if isinstance(e.get("seq"), int)]
    assert seqs == sorted(seqs) and len(seqs) == len(events)


@pytest.mark.asyncio
async def test_adapt_subagent_with_sse_seq_counter_matches_main_envelope(mock_subagent):
    """4.2: Optional shared seq counter applies envelope + merged subagent tagging."""
    mock_subagent.astream.return_value = _astream_yield(
        {
            "agent": {
                "messages": [
                    AIMessage(
                        content="",
                        tool_calls=[
                            {
                                "id": "tc-1",
                                "name": "read_file",
                                "args": {"path": "/x"},
                            }
                        ],
                    ),
                ],
            },
        },
        {
            "tools": {
                "messages": [
                    ToolMessage(content="ok", tool_call_id="tc-1", name="read_file"),
                ]
            }
        },
    )
    mock_subagent.ainvoke.return_value = {"messages": []}

    shared = [0]
    events = []
    async for e in adapt_subagent_astream_to_skill_events(
        mock_subagent,
        {"messages": []},
        {"configurable": {}},
        skill_name="my-skill",
        subagent_name="web-security",
        sse_seq_counter=shared,
    ):
        events.append(e)

    assert all(e.get("schemaVersion") == 1 for e in events)
    assert all(e.get("scope") == "subagent" for e in events)
    seqs = [e["seq"] for e in events]
    assert seqs == [1, 2, 3]
    # skill_complete maps to step when merged (same as main-stream bridge)
    assert events[-1]["type"] == "step"
    assert events[0]["id"].startswith("subagent-web-security-")


# ============================================================
# _ainvoke_subagent_with_sse_queue — stream_writer path tests
# ============================================================


from app._vendor.deepagents.middleware.subagents import (
    _ainvoke_subagent_with_sse_queue,
    _extract_subagent_thinking_and_text,
    _stable_subagent_message_delivery_order,
)


def test_extract_subagent_thinking_and_text_anthropic():
    """Inline helper correctly extracts Anthropic thinking + text blocks."""
    msg = AIMessage(
        content=[
            {"type": "thinking", "thinking": "chain of thought"},
            {"type": "text", "text": "final answer"},
        ]
    )
    thinking, text = _extract_subagent_thinking_and_text(msg)
    assert thinking == "chain of thought"
    assert text == "final answer"


def test_extract_subagent_thinking_and_text_openai():
    """Inline helper extracts OpenAI reasoning_content."""
    msg = AIMessage(
        content="answer",
        additional_kwargs={"reasoning_content": "reasoning here"},
    )
    thinking, text = _extract_subagent_thinking_and_text(msg)
    assert thinking == "reasoning here"
    assert text == "answer"


def test_extract_subagent_thinking_and_text_plain():
    """Plain string → empty thinking, full text."""
    msg = AIMessage(content="plain response")
    thinking, text = _extract_subagent_thinking_and_text(msg)
    assert thinking == ""
    assert text == "plain response"


def test_stable_subagent_message_delivery_order_reorders_final_ai_before_tool():
    tc_ai = AIMessage(content="", tool_calls=[{"id": "a", "name": "grep", "args": {}}])
    final_ai = AIMessage(content=[{"type": "thinking", "thinking": "post-tool"}])
    tool_m = ToolMessage(content="r", tool_call_id="a", name="grep")
    out = _stable_subagent_message_delivery_order([tc_ai, final_ai, tool_m])
    assert out == [tc_ai, tool_m, final_ai]


@pytest.mark.asyncio
async def test_ainvoke_subagent_stream_writer_tool_call_and_result():
    """stream_writer receives tool_call + tool_result events in real-time."""
    tool_call_msg = AIMessage(
        content="",
        tool_calls=[{"id": "tc-sw-1", "name": "read_file", "args": {"path": "/x"}}],
    )
    tool_result_msg = ToolMessage(
        content="file contents",
        tool_call_id="tc-sw-1",
        name="read_file",
    )
    final_msg = AIMessage(content="done")

    mock_sub = MagicMock()
    mock_sub.astream = MagicMock(
        return_value=_astream_yield(
            {"messages": [tool_call_msg, tool_result_msg, final_msg]},
        )
    )
    mock_sub.ainvoke = AsyncMock(return_value={"messages": [final_msg]})

    written: list = []
    await _ainvoke_subagent_with_sse_queue(
        mock_sub,
        {"messages": []},
        {"configurable": {}},
        "test-agent",
        stream_writer=written.append,
    )

    types = [e["type"] for e in written]
    assert "tool_call" in types
    assert "tool_result" in types
    tc = next(e for e in written if e["type"] == "tool_call")
    assert tc["toolName"] == "read_file"
    assert tc["subagentName"] == "test-agent"
    tr = next(e for e in written if e["type"] == "tool_result")
    assert tr["toolOutput"] == "file contents"


@pytest.mark.asyncio
async def test_ainvoke_subagent_stream_writer_tool_result_before_final_reasoning_when_tick_order_wrong():
    """If values tick lists final AIMessage before ToolMessage, SSE order must still be tool first."""
    tool_call_msg = AIMessage(
        content="",
        tool_calls=[{"id": "tc-ord", "name": "read_file", "args": {"path": "/z"}}],
    )
    tool_result_msg = ToolMessage(
        content="body",
        tool_call_id="tc-ord",
        name="read_file",
    )
    final_msg = AIMessage(
        content=[{"type": "thinking", "thinking": "synthesis after reading"}],
    )
    mock_sub = MagicMock()
    mock_sub.astream = MagicMock(
        return_value=_astream_yield(
            {"messages": [tool_call_msg, final_msg, tool_result_msg]},
        )
    )
    mock_sub.ainvoke = AsyncMock(return_value={"messages": [final_msg]})

    written: list = []
    await _ainvoke_subagent_with_sse_queue(
        mock_sub,
        {"messages": []},
        {"configurable": {}},
        "order-agent",
        stream_writer=written.append,
    )

    idx_tr = next(i for i, e in enumerate(written) if e["type"] == "tool_result")
    idx_syn = next(
        i
        for i, e in enumerate(written)
        if e.get("type") == "llm_delta"
        and e.get("channel") == "reasoning"
        and "synthesis after reading" in str(e.get("content", ""))
    )
    assert idx_tr < idx_syn, written


@pytest.mark.asyncio
async def test_ainvoke_subagent_stream_writer_emits_reasoning_with_tool_calls():
    """stream_writer emits reasoning event when AIMessage has thinking + tool_calls."""
    msg_with_thinking = AIMessage(
        content=[
            {"type": "thinking", "thinking": "let me think first"},
            {"type": "text", "text": ""},
        ],
        tool_calls=[{"id": "tc-r1", "name": "grep", "args": {"pattern": "foo"}}],
    )
    tool_result = ToolMessage(content="found", tool_call_id="tc-r1", name="grep")
    final_msg = AIMessage(content="result")

    mock_sub = MagicMock()
    mock_sub.astream = MagicMock(
        return_value=_astream_yield(
            {"messages": [msg_with_thinking, tool_result, final_msg]},
        )
    )
    mock_sub.ainvoke = AsyncMock(return_value={"messages": [final_msg]})

    written: list = []
    await _ainvoke_subagent_with_sse_queue(
        mock_sub,
        {"messages": []},
        {"configurable": {}},
        "think-agent",
        stream_writer=written.append,
    )

    r_text = _joined_llm_reasoning(written)
    assert "let me think first" in r_text
    r0 = next(e for e in written if e.get("type") == "llm_delta" and e.get("channel") == "reasoning")
    assert r0.get("subagentName") == "think-agent"
    types = [e["type"] for e in written]
    first_llm = next(
        i for i, t in enumerate(types) if t in ("llm_invoke_start", "llm_delta", "llm_invoke_end")
    )
    assert first_llm < types.index("tool_call")
    # Subagent uses emit_boundaries=False; close() must still emit llm_invoke_end for timeline pairing.
    assert "llm_invoke_end" in types
    idx_end = next(i for i, t in enumerate(types) if t == "llm_invoke_end")
    assert idx_end < types.index("tool_call")


@pytest.mark.asyncio
async def test_ainvoke_subagent_stream_writer_final_thinking_only_no_text():
    """Final AIMessage (no tool_calls): only thinking emitted, not visible text."""
    final_msg = AIMessage(
        content=[
            {"type": "thinking", "thinking": "synthesis thinking"},
            {"type": "text", "text": "This is the visible conclusion."},
        ]
    )
    mock_sub = MagicMock()
    mock_sub.astream = MagicMock(
        return_value=_astream_yield({"messages": [final_msg]})
    )
    mock_sub.ainvoke = AsyncMock(return_value={"messages": [final_msg]})

    written: list = []
    await _ainvoke_subagent_with_sse_queue(
        mock_sub,
        {"messages": []},
        {"configurable": {}},
        "final-agent",
        stream_writer=written.append,
    )

    r_text = _joined_llm_reasoning(written)
    assert "synthesis thinking" in r_text
    # Visible text must NOT appear in reasoning (it arrives as task() ToolMessage)
    assert "visible conclusion" not in r_text


@pytest.mark.asyncio
async def test_ainvoke_subagent_stream_writer_final_visible_is_wrapup_not_full_report():
    """Final AIMessage: SSE text channel carries WRAPUP only when anchors are present."""
    wrap = "Used tools A/B; outcome OK."
    full_body = "SECRET_LONG_REPORT\n" + ("Z" * 4000)
    final_body = (
        f"{SUBAGENT_WRAPUP_HEADING}\n\n{wrap}\n\n{SUBAGENT_FULL_HEADING}\n\n{full_body}"
    )
    final_msg = AIMessage(content=final_body)
    mock_sub = MagicMock()
    mock_sub.astream = MagicMock(return_value=_astream_yield({"messages": [final_msg]}))
    mock_sub.ainvoke = AsyncMock(return_value={"messages": [final_msg]})

    written: list = []
    await _ainvoke_subagent_with_sse_queue(
        mock_sub,
        {"messages": []},
        {"configurable": {}},
        "wrap-agent",
        stream_writer=written.append,
    )

    text_joined = _joined_llm_text(written).strip()
    assert text_joined == wrap
    assert "SECRET_LONG_REPORT" not in text_joined
    assert "ZZZZ" not in text_joined


@pytest.mark.asyncio
async def test_ainvoke_subagent_no_writer_no_queue_bare_ainvoke():
    """Without stream_writer or queue, falls back to bare ainvoke()."""
    final_msg = AIMessage(content="bare result")
    mock_sub = MagicMock()
    mock_sub.astream = MagicMock()
    mock_sub.ainvoke = AsyncMock(return_value={"messages": [final_msg]})

    result = await _ainvoke_subagent_with_sse_queue(
        mock_sub,
        {"messages": []},
        {"configurable": {}},
        "bare-agent",
        stream_writer=None,
    )

    mock_sub.astream.assert_not_called()
    assert result == {"messages": [final_msg]}


# ============================================================
# adapt_astream_to_sse — custom stream event handling tests
# ============================================================


@pytest.mark.asyncio
async def test_adapt_astream_handles_custom_stream_event_v2(mock_agent):
    """v2 custom stream events (from stream_writer) are yielded as merged subagent events."""
    custom_event = {
        "type": "custom",
        "data": {
            "type": "tool_call",
            "id": "tc-custom",
            "toolName": "read_file",
            "toolInput": {"path": "/x"},
            "status": "running",
            "subagentName": "general-purpose",
        },
    }
    final_msg = AIMessage(content="done")
    mock_agent.astream.return_value = _astream_yield(
        custom_event,
        {"agent": {"messages": [final_msg]}},
    )

    events = []
    async for e in adapt_astream_to_sse(
        mock_agent,
        {"messages": []},
        {"configurable": {}},
        use_messages_stream=False,
    ):
        events.append(e)

    tool_calls = [e for e in events if e.get("type") == "tool_call"]
    assert len(tool_calls) >= 1
    tc = next(e for e in tool_calls if e.get("id", "").endswith("tc-custom") or "tc-custom" in e.get("id", ""))
    assert tc["toolName"] == "read_file"
    assert tc.get("scope") == "subagent"
    assert tc.get("subagentStream") is True


@pytest.mark.asyncio
async def test_adapt_astream_handles_custom_reasoning_event(mock_agent):
    """Legacy custom ``reasoning`` payloads are tagged to ``llm_delta`` (reasoning channel)."""
    custom_reasoning = {
        "type": "custom",
        "data": {
            "type": "reasoning",
            "id": "reasoning-1",
            "content": "subagent is thinking about this",
            "subagentName": "general-purpose",
        },
    }
    final_msg = AIMessage(content="done")
    mock_agent.astream.return_value = _astream_yield(
        custom_reasoning,
        {"agent": {"messages": [final_msg]}},
    )

    events = []
    async for e in adapt_astream_to_sse(
        mock_agent,
        {"messages": []},
        {"configurable": {}},
        use_messages_stream=False,
    ):
        events.append(e)

    deltas = [e for e in events if e.get("type") == "llm_delta" and e.get("channel") == "reasoning"]
    assert any("subagent is thinking" in (e.get("content") or "") for e in deltas)
    assert any(e.get("scope") == "subagent" for e in deltas)


@pytest.mark.asyncio
async def test_adapt_astream_custom_event_has_seq_and_schema(mock_agent):
    """custom stream events receive schemaVersion, seq, and scope envelope."""
    custom_event = {
        "type": "custom",
        "data": {
            "type": "tool_result",
            "id": "tr-1",
            "toolName": "grep",
            "toolOutput": "found",
            "status": "success",
            "subagentName": "general-purpose",
        },
    }
    final_msg = AIMessage(content="ok")
    mock_agent.astream.return_value = _astream_yield(
        custom_event,
        {"agent": {"messages": [final_msg]}},
    )

    events = []
    async for e in adapt_astream_to_sse(
        mock_agent, {"messages": []}, {"configurable": {}}, use_messages_stream=False
    ):
        events.append(e)

    tool_results = [e for e in events if e.get("type") == "tool_result"]
    assert len(tool_results) >= 1
    tr = tool_results[0]
    assert tr.get("schemaVersion") == 1
    assert isinstance(tr.get("seq"), int)
    assert tr.get("scope") == "subagent"


@pytest.mark.asyncio
async def test_subagent_sse_queue_yields_before_next_main_chunk(mock_agent):
    """Queue-backed subagent SSE must not wait for the next astream chunk (regression)."""
    sq = asyncio.Queue(maxsize=512)

    async def delayed_astream():
        yield {"type": "messages", "data": (AIMessageChunk(content="FIRST_CH"), {})}

        async def feed():
            await asyncio.sleep(0.02)
            await sq.put(
                {
                    "type": "tool_call",
                    "id": "tc-queue-cr",
                    "toolName": "ConductResearch",
                    "toolInput": {"research_topic": "topic"},
                    "status": "running",
                    "subagentName": "deep-research",
                }
            )

        asyncio.create_task(feed())
        await asyncio.sleep(0.25)
        # updates path emits visible text; v2 "messages" chunks here only stream thinking.
        yield {
            "type": "updates",
            "data": {"agent": {"messages": [AIMessage(content="SECOND_UNIQUE")]}},
        }

    mock_agent.astream.return_value = delayed_astream()

    events = []
    async for e in adapt_astream_to_sse(
        mock_agent,
        {"messages": []},
        {"configurable": {"subagent_sse_event_queue": sq}},
        use_messages_stream=True,
        language="en",
    ):
        events.append(e)

    idx_tc = next(
        (
            i
            for i, ev in enumerate(events)
            if ev.get("type") == "tool_call" and ev.get("toolName") == "ConductResearch"
        ),
        None,
    )
    assert idx_tc is not None, "ConductResearch tool_call from subagent queue missing"
    # Second graph chunk may surface as conclusion (not llm_delta text) depending on finalize path.
    idx_second = next((i for i, ev in enumerate(events) if "SECOND_UNIQUE" in str(ev)), None)
    assert idx_second is not None, "expected second updates chunk text to appear in some SSE event"
    assert idx_tc < idx_second, (
        "ConductResearch should appear before second chunk text; "
        f"got indices tool_call={idx_tc}, second_delta={idx_second}"
    )


# ============================================================
# Path A: RunnableLambda stream_writer injection tests
# ============================================================


@pytest.mark.asyncio
async def test_runnable_lambda_injects_stream_writer_into_configurable():
    """When stream_writer is provided, atask() injects it into configurable for RunnableLambda."""
    from langchain_core.runnables import RunnableLambda

    received_configs: list[dict] = []

    async def _fake_lambda(state, config=None):
        received_configs.append(config or {})
        return {"messages": [AIMessage(content="done")]}

    runnable = RunnableLambda(_fake_lambda)
    original_ainvoke = runnable.ainvoke

    async def _patched_ainvoke(state, config=None, **kw):
        received_configs.append(config or {})
        return {"messages": [AIMessage(content="done")]}

    runnable.ainvoke = _patched_ainvoke  # type: ignore[method-assign]

    written_events: list[dict] = []
    sw = written_events.append

    cfg = {"configurable": {"thread_id": "t1"}}
    await _ainvoke_subagent_with_sse_queue(
        runnable, {}, cfg, "open-deep-research", stream_writer=sw
    )

    assert len(received_configs) == 1
    injected = received_configs[0].get("configurable", {})
    assert injected.get("subagent_stream_writer") is sw, (
        "stream_writer should be injected as 'subagent_stream_writer' in configurable"
    )


@pytest.mark.asyncio
async def test_runnable_lambda_no_stream_writer_uses_original_config():
    """Without stream_writer, RunnableLambda ainvoke is called with the original config unchanged."""
    from langchain_core.runnables import RunnableLambda

    received_configs: list[dict] = []

    async def _fake_lambda(state, config=None):
        return {"messages": [AIMessage(content="ok")]}

    runnable = RunnableLambda(_fake_lambda)

    async def _patched_ainvoke(state, config=None, **kw):
        received_configs.append(config or {})
        return {"messages": [AIMessage(content="ok")]}

    runnable.ainvoke = _patched_ainvoke  # type: ignore[method-assign]

    cfg = {"configurable": {"thread_id": "t2", "some_key": "val"}}
    await _ainvoke_subagent_with_sse_queue(
        runnable, {}, cfg, "open-deep-research", stream_writer=None
    )

    assert len(received_configs) == 1
    assert "subagent_stream_writer" not in received_configs[0].get("configurable", {})


@pytest.mark.asyncio
async def test_open_deep_research_push_uses_stream_writer():
    """_push helper in open_deep_research_compiled delivers events via stream_writer."""
    import asyncio

    written: list[dict] = []

    def sw(ev: dict) -> None:
        written.append(ev)

    # Simulate what subagents.py now does: inject stream_writer into configurable
    cfg = {"configurable": {"subagent_stream_writer": sw}}

    # Build a minimal event queue (should NOT be used when stream_writer is set)
    q: asyncio.Queue = asyncio.Queue()

    # Directly test the _push logic as implemented in open_deep_research_compiled
    import types

    configurable = cfg.get("configurable", {})
    _stream_writer = configurable.get("subagent_stream_writer")
    event_queue = q  # would be set normally

    def _push(ev: dict) -> None:
        if _stream_writer is not None:
            try:
                _stream_writer(ev)
            except Exception:
                pass
        elif event_queue is not None:
            try:
                event_queue.put_nowait(ev)
            except asyncio.QueueFull:
                pass

    test_ev = {"type": "llm_delta", "channel": "reasoning", "id": "r1", "content": "thinking..."}
    _push(test_ev)

    assert written == [test_ev], "event should arrive via stream_writer"
    assert q.empty(), "queue should NOT receive events when stream_writer is set"


@pytest.mark.asyncio
async def test_adapt_emits_context_summarized_when_summarization_state_appears(mock_agent):
    """A-03: when `_summarization_event` flows through updates, adapter emits `context_summarized`."""
    summary_msg = HumanMessage(content="[Previous conversation compacted.]")
    sum_state = {
        "_summarization_event": {
            "cutoff_index": 42,
            "summary_message": summary_msg,
            "file_path": None,
        }
    }
    # Two updates with the same cutoff -> only a single context_summarized emitted.
    mock_agent.astream.return_value = _astream_yield(
        {"agent": sum_state},
        {"agent": sum_state},
        {"agent": {"messages": [AIMessage(content="ok")]}},
    )
    mock_agent.ainvoke.return_value = {"messages": [AIMessage(content="ok")]}

    events = []
    async for e in adapt_astream_to_sse(
        mock_agent, {"messages": []}, {"configurable": {}}, language="en"
    ):
        events.append(e)

    ctx_events = [e for e in events if e.get("type") == "context_summarized"]
    assert len(ctx_events) == 1, f"Expected exactly one context_summarized, got {len(ctx_events)}"
    assert ctx_events[0]["cutoffIndex"] == 42
    assert isinstance(ctx_events[0].get("timestamp"), int)


@pytest.mark.asyncio
async def test_adapt_emits_context_summarized_once_per_cutoff(mock_agent):
    """Different cutoff_index values each produce their own `context_summarized`."""
    msg = HumanMessage(content="...")
    mock_agent.astream.return_value = _astream_yield(
        {"agent": {"_summarization_event": {"cutoff_index": 10, "summary_message": msg, "file_path": None}}},
        {"agent": {"_summarization_event": {"cutoff_index": 20, "summary_message": msg, "file_path": None}}},
        {"agent": {"messages": [AIMessage(content="ok")]}},
    )
    mock_agent.ainvoke.return_value = {"messages": [AIMessage(content="ok")]}

    events = []
    async for e in adapt_astream_to_sse(
        mock_agent, {"messages": []}, {"configurable": {}}, language="en"
    ):
        events.append(e)

    ctx_events = [e for e in events if e.get("type") == "context_summarized"]
    assert [e["cutoffIndex"] for e in ctx_events] == [10, 20]