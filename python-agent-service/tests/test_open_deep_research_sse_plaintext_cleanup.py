"""Tests for deep-research compiled SSE plaintext cleanup (OpenSpec deep-research-sse-plaintext-cleanup)."""

from __future__ import annotations

from langchain_core.messages import AIMessage, HumanMessage, SystemMessage, ToolMessage

from app.agents.research.open_deep_research_compiled import (
    _clarify_user_visible_text,
    _extract_stream_events,
)
from app.agents.research.open_deep_research_original_adapter import (
    DeepResearchStreamExtractContext,
    format_research_tool_output_for_sse,
    normalize_research_brief_key,
    split_aimessage_thinking_and_visible,
)


def test_normalize_research_brief_key_collapses_whitespace():
    a = "Hello   World\n"
    b = "  hello world  "
    assert normalize_research_brief_key(a) == normalize_research_brief_key(b)


def test_split_aimessage_thinking_and_visible_blocks():
    msg = AIMessage(
        content=[
            {"type": "thinking", "thinking": "plan step"},
            {"type": "text", "text": "visible answer"},
        ]
    )
    th, vis = split_aimessage_thinking_and_visible(msg)
    assert "plan" in th
    assert "visible" in vis


def test_format_conductresearch_list_never_raw_repr():
    blocks = [
        {"type": "thinking", "thinking": "internal only"},
        {"type": "text", "text": "Finding one"},
    ]
    out = format_research_tool_output_for_sse(blocks, tool_name="ConductResearch", ui_language="en")
    assert "[{" not in out
    assert "Finding one" in out


def test_format_conductresearch_string_prefers_wrapup_for_sse():
    """ConductResearch tool output string: SSE shows SM_SUBAGENT_WRAPUP body only."""
    from app.parsers.final_message_split import SUBAGENT_FULL_HEADING, SUBAGENT_WRAPUP_HEADING

    blob = (
        f"{SUBAGENT_WRAPUP_HEADING}\n\nUI summary only.\n\n"
        f"{SUBAGENT_FULL_HEADING}\n\n# Long\n\n" + "x" * 500
    )
    out = format_research_tool_output_for_sse(blob, tool_name="ConductResearch", ui_language="en")
    assert "UI summary only" in out
    assert "xxx" not in out


def test_extract_stream_events_omits_system_message():
    ctx = DeepResearchStreamExtractContext(ui_language="zh")
    update = {
        "write_research_brief": {
            "supervisor_messages": {
                "type": "override",
                "value": [
                    SystemMessage(content="<Task>\nDo research\n</Task>"),
                    HumanMessage(content="Brief body"),
                ],
            }
        }
    }
    events = _extract_stream_events(update, ctx)
    labels_and_details = [(e.get("label"), e.get("detail")) for e in events]
    assert not any(d and "<Task>" in str(d) for _, d in labels_and_details)
    assert not any("<Task>" in str(e.get("content", "")) for e in events)


def test_extract_stream_events_dedupes_supervisor_human_same_as_brief():
    ctx = DeepResearchStreamExtractContext(ui_language="zh")
    brief = "Same research brief text"
    ctx.brief_norm_from_write = normalize_research_brief_key(brief)

    update = {
        "research_supervisor": {
            "supervisor_messages": [
                HumanMessage(content=brief),
            ]
        }
    }
    events = _extract_stream_events(update, ctx)
    human_steps = [e for e in events if e.get("type") == "step" and e.get("detail")]
    assert len(human_steps) == 0


def test_extract_stream_events_phase_labels_not_raw_node_ids():
    ctx = DeepResearchStreamExtractContext(ui_language="zh")
    update = {"final_report_generation": {}}
    events = _extract_stream_events(update, ctx)
    report_step = next(e for e in events if e.get("phaseId") == "deep_research_report")
    assert report_step.get("status") == "success"
    assert report_step.get("label") != "final_report_generation"
    assert "整理" in report_step.get("label", "") or "report" in report_step.get("label", "").lower()
    # Phase-edge nodes no longer emit a redundant debug-node step
    debug_nodes = [e for e in events if e.get("id") == "debug-node-final_report_generation"]
    assert len(debug_nodes) == 0


def test_extract_stream_events_no_debug_step_for_phase_edge_nodes():
    """Phase-edge nodes (clarify, write_brief, supervisor, final_report) must NOT emit
    a debug-node step because the milestone events already carry the same label text."""
    ctx = DeepResearchStreamExtractContext(ui_language="zh")
    ctx.research_phase_markers_done.add("deep_research_clarify:running")
    ctx.emitted_research_phase_ids.add("deep_research_clarify")
    update = {
        "clarify_with_user": {"messages": []},
        "write_research_brief": {"supervisor_messages": []},
    }
    events = _extract_stream_events(update, ctx)
    debug_ids = [e.get("id") for e in events if str(e.get("id", "")).startswith("debug-node-")]
    assert "debug-node-clarify_with_user" not in debug_ids
    assert "debug-node-write_research_brief" not in debug_ids


def test_extract_stream_events_leading_phases_per_main_node_completion():
    """Each main-graph completion emits success for the finished slot then running for the next."""
    lang = "en"

    ctx0 = DeepResearchStreamExtractContext(ui_language=lang)
    ctx0.research_phase_markers_done.add("deep_research_clarify:running")
    ctx0.emitted_research_phase_ids.add("deep_research_clarify")
    ev_c = _extract_stream_events({"clarify_with_user": {"messages": []}}, ctx0)
    ms_c = [e for e in ev_c if e.get("phaseId")]
    assert [e.get("phaseId") for e in ms_c] == ["deep_research_clarify", "deep_research_plan"]
    assert [e.get("status") for e in ms_c] == ["success", "running"]

    ctx1 = DeepResearchStreamExtractContext(ui_language=lang)
    ctx1.research_phase_markers_done.update(
        {
            "deep_research_clarify:running",
            "main_graph_done:clarify_with_user",
            "deep_research_clarify:success",
            "deep_research_plan:running",
        }
    )
    ctx1.emitted_research_phase_ids.update({"deep_research_clarify", "deep_research_plan"})
    ev_b = _extract_stream_events({"write_research_brief": {"supervisor_messages": []}}, ctx1)
    ms_b = [e for e in ev_b if e.get("phaseId")]
    assert [e.get("phaseId") for e in ms_b] == ["deep_research_plan", "deep_research_collect"]
    assert [e.get("status") for e in ms_b] == ["success", "running"]

    ctx2 = DeepResearchStreamExtractContext(ui_language=lang)
    ctx2.research_phase_markers_done.update(
        {
            "deep_research_clarify:running",
            "main_graph_done:clarify_with_user",
            "deep_research_clarify:success",
            "deep_research_plan:running",
            "main_graph_done:write_research_brief",
            "deep_research_plan:success",
            "deep_research_collect:running",
        }
    )
    ctx2.emitted_research_phase_ids.update(
        {"deep_research_clarify", "deep_research_plan", "deep_research_collect"}
    )
    ev_s = _extract_stream_events({"research_supervisor": {}}, ctx2)
    ms_s = [e for e in ev_s if e.get("phaseId")]
    assert [e.get("phaseId") for e in ms_s] == ["deep_research_collect", "deep_research_report"]
    assert [e.get("status") for e in ms_s] == ["success", "running"]

    ctx3 = DeepResearchStreamExtractContext(ui_language=lang)
    ctx3.research_phase_markers_done.update(
        {
            "deep_research_clarify:running",
            "main_graph_done:clarify_with_user",
            "deep_research_clarify:success",
            "deep_research_plan:running",
            "main_graph_done:write_research_brief",
            "deep_research_plan:success",
            "deep_research_collect:running",
            "main_graph_done:research_supervisor",
            "deep_research_collect:success",
            "deep_research_report:running",
        }
    )
    ctx3.emitted_research_phase_ids.update(
        {"deep_research_clarify", "deep_research_plan", "deep_research_collect", "deep_research_report"}
    )
    ev_f = _extract_stream_events({"final_report_generation": {}}, ctx3)
    ms_f = [e for e in ev_f if e.get("phaseId")]
    assert [e.get("phaseId") for e in ms_f] == ["deep_research_report"]
    assert [e.get("status") for e in ms_f] == ["success"]

    for group in (ms_c, ms_b, ms_s, ms_f):
        assert all(e.get("subagentName") == "deep-research" for e in group)
        assert all(e.get("researchSubgraph") is True for e in group)


def test_extract_stream_events_human_input_step_is_debug():
    ctx = DeepResearchStreamExtractContext(ui_language="en")
    update = {
        "clarify_with_user": {
            "messages": [HumanMessage(content="User asks something")],
        }
    }
    events = _extract_stream_events(update, ctx)
    human_debug = next(
        e
        for e in events
        if e.get("type") == "step" and str(e.get("id", "")).startswith("debug-input-")
    )
    assert human_debug.get("internal") is True
    assert human_debug.get("visibility") == "debug"


def test_extract_stream_events_reasoning_prefixes_for_draft_node():
    """Non-silent draft-phase nodes still emit reasoning with draft prefix."""
    ctx = DeepResearchStreamExtractContext(ui_language="zh")
    # write_research_brief is in _DRAFT_PHASE_NODES but NOT in _SUPERVISOR_SILENT_NODES
    update = {
        "write_research_brief": {
            "messages": [
                AIMessage(content="Draft findings paragraph"),
            ]
        }
    }
    events = _extract_stream_events(update, ctx)
    deltas = [
        e.get("content") or ""
        for e in events
        if e.get("type") == "llm_delta" and e.get("channel") in ("reasoning", "text")
    ]
    joined = "".join(deltas)
    assert joined
    assert "草稿" in joined or "draft" in joined.lower()


def test_extract_stream_events_supervisor_silent_suppresses_all_but_conduct_research():
    """supervisor node is in _SUPERVISOR_SILENT_NODES — only ConductResearch tool_call passes."""
    ctx = DeepResearchStreamExtractContext(ui_language="en")
    update = {
        "supervisor": {
            "supervisor_messages": [
                HumanMessage(content="Brief text input"),
                AIMessage(
                    content="I will delegate research",
                    tool_calls=[
                        {"id": "tc-cr", "name": "ConductResearch", "args": {"topic": "X"}},
                        {"id": "tc-think", "name": "think_tool", "args": {"thought": "hmm"}},
                    ],
                ),
            ]
        }
    }
    events = _extract_stream_events(update, ctx)
    types = [e.get("type") for e in events]
    assert "tool_call" in types
    cr = [e for e in events if e.get("type") == "tool_call"]
    assert len(cr) == 1
    assert cr[0]["toolName"] == "ConductResearch"
    assert cr[0]["id"] == "tc-cr"
    assert "step" not in [e.get("type") for e in events if "debug-node" in str(e.get("id", ""))]
    assert not any(e.get("type") == "llm_delta" for e in events)
    assert not any(
        e.get("type") == "step" and "debug-input" in str(e.get("id", ""))
        for e in events
    )


def test_extract_stream_events_supervisor_tools_passes_conduct_research_tool_result():
    """supervisor_tools passes ConductResearch tool_result so the UI can update status."""
    ctx = DeepResearchStreamExtractContext(ui_language="en")
    update = {
        "supervisor_tools": {
            "supervisor_messages": [
                ToolMessage(
                    content=[{"type": "text", "text": "Research findings"}],
                    name="ConductResearch",
                    tool_call_id="tc-cr-done",
                )
            ]
        }
    }
    events = _extract_stream_events(update, ctx)
    tr = [e for e in events if e.get("type") == "tool_result"]
    assert len(tr) == 1
    assert tr[0]["toolName"] == "ConductResearch"
    assert tr[0]["id"] == "tc-cr-done"
    assert tr[0]["status"] == "success"
    assert not any(e.get("id", "").startswith("debug-node") for e in events)


def test_extract_stream_events_supervisor_tools_suppresses_non_conduct_research_tool_result():
    """supervisor_tools suppresses tool_result for tools other than ConductResearch."""
    ctx = DeepResearchStreamExtractContext(ui_language="en")
    update = {
        "supervisor_tools": {
            "supervisor_messages": [
                ToolMessage(
                    content="thought result",
                    name="think_tool",
                    tool_call_id="tc-think-1",
                )
            ]
        }
    }
    events = _extract_stream_events(update, ctx)
    assert not any(e.get("type") == "tool_result" for e in events)


def test_extract_stream_events_researcher_silent_suppresses_web_search():
    """researcher and researcher_tools are silent — web_search tool_call/result suppressed."""
    ctx = DeepResearchStreamExtractContext(ui_language="en")
    # researcher node: LLM delta + web_search tool_call → suppressed
    update_researcher = {
        "researcher": {
            "researcher_messages": [
                AIMessage(
                    content="I will search for info",
                    tool_calls=[{"id": "tc-ws", "name": "web_search", "args": {"query": "test"}}],
                ),
            ]
        }
    }
    events_r = _extract_stream_events(update_researcher, ctx)
    assert not any(e.get("type") == "tool_call" for e in events_r)
    assert not any(e.get("type") == "llm_delta" for e in events_r)
    assert not any(e.get("id", "").startswith("debug-node") for e in events_r)

    # researcher_tools node: web_search tool_result → suppressed
    ctx2 = DeepResearchStreamExtractContext(ui_language="en")
    update_tools = {
        "researcher_tools": {
            "researcher_messages": [
                ToolMessage(content="search results", name="web_search", tool_call_id="tc-ws"),
            ]
        }
    }
    events_t = _extract_stream_events(update_tools, ctx2)
    assert not any(e.get("type") == "tool_result" for e in events_t)

    # compress_research node: LLM content → suppressed
    ctx3 = DeepResearchStreamExtractContext(ui_language="en")
    update_compress = {
        "compress_research": {
            "researcher_messages": [AIMessage(content="Compressed findings")]
        }
    }
    events_c = _extract_stream_events(update_compress, ctx3)
    assert not any(e.get("type") == "llm_delta" for e in events_c)


def test_extract_stream_events_non_silent_node_still_emits_tool_result():
    """Nodes NOT in _SUPERVISOR_SILENT_NODES continue to emit tool_result events."""
    ctx = DeepResearchStreamExtractContext(ui_language="en")
    # clarify_with_user is NOT in _SUPERVISOR_SILENT_NODES
    update = {
        "clarify_with_user": {
            "messages": [
                ToolMessage(
                    content="Some result",
                    name="some_tool",
                    tool_call_id="tc-some",
                )
            ]
        }
    }
    events = _extract_stream_events(update, ctx)
    tr = next(e for e in events if e.get("type") == "tool_result")
    assert tr.get("toolName") == "some_tool"


def test_clarify_user_visible_text_prefers_verification_when_no_clarification():
    raw = (
        '{"need_clarification": false, "question": "", '
        '"verification": "We have enough information and will start research now."}'
    )
    out = _clarify_user_visible_text(raw)
    assert out == "We have enough information and will start research now."


def test_clarify_user_visible_text_prefers_question_when_clarification_needed():
    raw = (
        '{"need_clarification": true, "question": "Which region should I focus on?", '
        '"verification": ""}'
    )
    out = _clarify_user_visible_text(raw)
    assert out == "Which region should I focus on?"


# ---------------------------------------------------------------------------
# Regression: LangGraph 1.0.8 tuple v1 event format is not silently dropped
# ---------------------------------------------------------------------------

import asyncio
from unittest.mock import AsyncMock, patch

from langchain_core.messages import AIMessage

from app.agents.research.open_deep_research_compiled import (
    _run_open_deep_research_subagent,
)
from app.parsers.final_message_split import SUBAGENT_FULL_HEADING, SUBAGENT_WRAPUP_HEADING


def _make_astream_returning_tuples():
    """Async generator simulating LangGraph stream_mode=list + subgraphs=True (ns, mode, data)."""

    async def _gen(*_args, **_kwargs):
        long_body = "LONGREPORT" * 120
        content = (
            f"{SUBAGENT_WRAPUP_HEADING}\n\nBrief wrap for SSE.\n\n"
            f"{SUBAGENT_FULL_HEADING}\n\n{long_body}"
        )
        # Root namespace () — same shape as LangGraph StreamChunk when subgraphs=True.
        yield (
            (),
            "messages",
            (
                AIMessage(content=content),
                {"langgraph_node": "final_report_generation"},
            ),
        )
        yield (
            (),
            "updates",
            {
                "final_report_generation": {
                    "final_report": content,
                    "messages": [AIMessage(content=content)],
                }
            },
        )

    return _gen


def test_run_subagent_handles_two_tuple_stream_format():
    """Backward compat: (mode, data) without namespace still works if caller omits subgraphs."""

    async def _gen_two_tuple(*_args, **_kwargs):
        long_body = "LONGREPORT" * 120
        content = (
            f"{SUBAGENT_WRAPUP_HEADING}\n\nBrief wrap for SSE.\n\n"
            f"{SUBAGENT_FULL_HEADING}\n\n{long_body}"
        )
        yield (
            "messages",
            (
                AIMessage(content=content),
                {"langgraph_node": "final_report_generation"},
            ),
        )
        yield (
            "updates",
            {
                "final_report_generation": {
                    "final_report": content,
                    "messages": [AIMessage(content=content)],
                }
            },
        )

    pushed: list[dict] = []
    state = {"messages": [HumanMessage(content="What is LangGraph?")]}
    config = {
        "configurable": {
            "subagent_stream_writer": pushed.append,
            "thread_id": "test-session",
        }
    }
    with patch(
        "app.agents.research.open_deep_research_compiled.original_research_graph.astream",
        side_effect=_gen_two_tuple(),
    ):
        result = asyncio.run(_run_open_deep_research_subagent(state, config))
    assert result.get("messages")
    assert any(e.get("type") == "step" for e in pushed)


def test_run_subagent_handles_langgraph_tuple_format():
    """Events from LangGraph (namespace, mode, data) with subgraphs=True must be handled.

    Regression guard for the `if not isinstance(raw_event, dict): continue` bug
    that caused all intermediate SSE events to be discarded.
    """
    pushed: list[dict] = []

    state = {"messages": [HumanMessage(content="What is LangGraph?")]}
    config = {
        "configurable": {
            "subagent_stream_writer": pushed.append,
            "thread_id": "test-session",
        }
    }

    with patch(
        "app.agents.research.open_deep_research_compiled.original_research_graph.astream",
        side_effect=_make_astream_returning_tuples(),
    ):
        result = asyncio.run(_run_open_deep_research_subagent(state, config))

    # The subagent must return a non-empty final message.
    assert result.get("messages"), "Expected messages in result"
    content = result["messages"][-1].content
    assert content and len(content) > 0, "Final message content must be non-empty"

    # At least the four phase milestone events should have been pushed.
    types = [e.get("type") for e in pushed]
    assert "step" in types, f"Expected 'step' events in pushed events, got: {types}"
    assert pushed[0].get("id") == "dr-pre-clarify"
    assert pushed[0].get("phaseId") == "deep_research_clarify"

    text_joined = "".join(
        str(e.get("content") or "")
        for e in pushed
        if e.get("type") == "llm_delta" and e.get("channel") == "text"
    )
    assert "Brief wrap for SSE." in text_joined
    assert "LONGREPORT" not in text_joined


def test_subagent_three_tuple_supervisor_stream_emits_conduct_research_tool_call():
    """With subgraph namespaces, supervisor AIMessage+tool_calls must _push before final_report."""

    def _make_supervisor_astream():
        async def _gen(*_args, **_kwargs):
            ns_sup = (
                "research_supervisor:00000000-0000-0000-0000-000000000001",
                "supervisor:00000000-0000-0000-0000-000000000002",
            )
            yield (
                ns_sup,
                "messages",
                (
                    AIMessage(
                        content="",
                        tool_calls=[
                            {
                                "id": "tc-cr-supervisor",
                                "name": "ConductResearch",
                                "args": {"research_topic": "Topic from supervisor"},
                            }
                        ],
                    ),
                    {"langgraph_node": "supervisor"},
                ),
            )
            long_body = "LONGREPORT" * 120
            content = (
                f"{SUBAGENT_WRAPUP_HEADING}\n\nBrief wrap for SSE.\n\n"
                f"{SUBAGENT_FULL_HEADING}\n\n{long_body}"
            )
            yield (
                (),
                "messages",
                (
                    AIMessage(content=content),
                    {"langgraph_node": "final_report_generation"},
                ),
            )
            yield (
                (),
                "updates",
                {
                    "final_report_generation": {
                        "final_report": content,
                        "messages": [AIMessage(content=content)],
                    }
                },
            )

        return _gen

    pushed: list[dict] = []
    state = {"messages": [HumanMessage(content="Research question")]}
    config = {
        "configurable": {
            "subagent_stream_writer": pushed.append,
            "thread_id": "test-session",
        }
    }
    with patch(
        "app.agents.research.open_deep_research_compiled.original_research_graph.astream",
        side_effect=_make_supervisor_astream(),
    ):
        asyncio.run(_run_open_deep_research_subagent(state, config))

    cr_events = [
        e
        for e in pushed
        if e.get("type") == "tool_call" and e.get("toolName") == "ConductResearch"
    ]
    assert cr_events, "Expected ConductResearch tool_call from nested supervisor messages"
    assert cr_events[0].get("node") == "supervisor"
    assert cr_events[0].get("id") == "tc-cr-supervisor"


# ---------------------------------------------------------------------------
# Anchor wrapping: return value carries SM_SUBAGENT_WRAPUP / SM_SUBAGENT_FULL_REPORT
# ---------------------------------------------------------------------------

from app.agents.research.open_deep_research_compiled import _extract_research_wrapup
from app.parsers.final_message_split import SUBAGENT_FULL_HEADING, split_subagent_wrapup_and_full


def test_extract_research_wrapup_short_text_returned_as_is():
    short = "Single paragraph finding."
    assert _extract_research_wrapup(short) == short


def test_extract_research_wrapup_breaks_at_paragraph():
    p1 = "A" * 300
    p2 = "B" * 300
    p3 = "C" * 900
    report = f"{p1}\n\n{p2}\n\n{p3}"
    result = _extract_research_wrapup(report)
    assert p1 in result
    assert "CCC" not in result


def test_extract_research_wrapup_empty():
    assert _extract_research_wrapup("") == ""
    assert _extract_research_wrapup("   ") == ""


def test_subagent_return_wraps_plain_text_with_anchors():
    """When LLM output has no anchors, _run_open_deep_research_subagent adds them."""
    plain_report = "# Research Title\n\nIntro paragraph.\n\nDetail paragraph " + "x" * 900

    async def _gen(*_args, **_kwargs):
        yield (
            (),
            "updates",
            {
                "final_report_generation": {
                    "final_report": plain_report,
                    "messages": [AIMessage(content=plain_report)],
                }
            },
        )

    pushed: list[dict] = []
    state = {"messages": [HumanMessage(content="Test query")]}
    config = {
        "configurable": {
            "subagent_stream_writer": pushed.append,
            "thread_id": "test-anchors",
        }
    }
    with patch(
        "app.agents.research.open_deep_research_compiled.original_research_graph.astream",
        side_effect=_gen,
    ):
        result = asyncio.run(_run_open_deep_research_subagent(state, config))

    content = result["messages"][-1].content
    assert SUBAGENT_FULL_HEADING not in content, "Body-first wrap must not duplicate FULL_REPORT heading"
    wrapup, full = split_subagent_wrapup_and_full(content)
    assert wrapup is not None, "Expected WRAPUP anchor in return value"
    assert full is not None, "Expected parseable full report body"
    assert "Research Title" in full
    assert "Detail paragraph" in full
    assert len(wrapup) < len(full), "WRAPUP should be shorter than full report"


def test_subagent_return_preserves_existing_anchors():
    """When the research output already has WRAPUP/FULL anchors, no double wrapping."""
    long_body = "LONGREPORT" * 120
    anchored_content = (
        f"{SUBAGENT_WRAPUP_HEADING}\n\nOriginal wrapup.\n\n"
        f"{SUBAGENT_FULL_HEADING}\n\n{long_body}"
    )

    async def _gen(*_args, **_kwargs):
        yield (
            (),
            "updates",
            {
                "final_report_generation": {
                    "final_report": anchored_content,
                    "messages": [AIMessage(content=anchored_content)],
                }
            },
        )

    pushed: list[dict] = []
    state = {"messages": [HumanMessage(content="Test query")]}
    config = {
        "configurable": {
            "subagent_stream_writer": pushed.append,
            "thread_id": "test-no-double-wrap",
        }
    }
    with patch(
        "app.agents.research.open_deep_research_compiled.original_research_graph.astream",
        side_effect=_gen,
    ):
        result = asyncio.run(_run_open_deep_research_subagent(state, config))

    content = result["messages"][-1].content
    wrapup, full = split_subagent_wrapup_and_full(content)
    assert wrapup is not None
    assert full is not None
    assert wrapup.strip() == "Original wrapup."
    assert content.count(SUBAGENT_WRAPUP_HEADING) == 1, "Must not double-wrap"


# ---------------------------------------------------------------------------
# Messages stream: non-AIMessage filtering
# ---------------------------------------------------------------------------


def test_messages_stream_skips_system_and_human_messages():
    """SystemMessage / HumanMessage from the messages stream must be silently discarded.

    Regression: supervisor system prompt (lead_researcher_prompt) was leaking to UI
    because it was treated as visible text when emitted as a SystemMessage chunk from
    the write_research_brief state update.
    """

    async def _gen(*_args, **_kwargs):
        ns = ("research_supervisor:a",)
        # SystemMessage from write_research_brief state update — must NOT appear
        yield (
            ns,
            "messages",
            (
                SystemMessage(content="You are a research supervisor. Do not show this."),
                {"langgraph_node": "write_research_brief"},
            ),
        )
        # HumanMessage (research brief) from state update — must NOT appear
        yield (
            ns,
            "messages",
            (
                HumanMessage(content="Research brief: topic X. Do not show this either."),
                {"langgraph_node": "write_research_brief"},
            ),
        )
        # AIMessage from final_report_generation — must appear
        content = f"{SUBAGENT_WRAPUP_HEADING}\n\nWrap.\n\n{SUBAGENT_FULL_HEADING}\n\nFull."
        yield ((), "updates", {"final_report_generation": {
            "final_report": content, "messages": [AIMessage(content=content)],
        }})

    pushed: list[dict] = []
    state = {"messages": [HumanMessage(content="Query")]}
    config = {"configurable": {"subagent_stream_writer": pushed.append, "thread_id": "t"}}
    with patch(
        "app.agents.research.open_deep_research_compiled.original_research_graph.astream",
        side_effect=_gen,
    ):
        asyncio.run(_run_open_deep_research_subagent(state, config))

    llm_deltas = [e for e in pushed if e.get("type") == "llm_delta"]
    delta_contents = [str(e.get("content", "")) for e in llm_deltas]
    joined = " ".join(delta_contents)
    assert "research supervisor" not in joined.lower(), \
        f"SystemMessage content leaked to UI: {joined[:200]}"
    assert "Do not show this" not in joined, \
        f"HumanMessage content leaked to UI: {joined[:200]}"


# ---------------------------------------------------------------------------
# Supervisor signal suppression — messages stream filtering
# ---------------------------------------------------------------------------


def test_supervisor_messages_stream_suppresses_delta_but_passes_conduct_research():
    """supervisor tokens are silent: no llm_delta, but ConductResearch tool_call passes."""

    async def _gen(*_args, **_kwargs):
        ns_sup = ("research_supervisor:a", "supervisor:b")
        yield (
            ns_sup,
            "messages",
            (
                AIMessage(
                    content=[
                        {"type": "thinking", "thinking": "I should delegate"},
                        {"type": "text", "text": "Supervisor visible reasoning"},
                    ],
                ),
                {"langgraph_node": "supervisor"},
            ),
        )
        yield (
            ns_sup,
            "messages",
            (
                AIMessage(
                    content="",
                    tool_calls=[
                        {"id": "tc-cr-1", "name": "ConductResearch", "args": {"topic": "T1"}},
                        {"id": "tc-res-complete", "name": "ResearchComplete", "args": {"result": "done"}},
                    ],
                ),
                {"langgraph_node": "supervisor"},
            ),
        )
        content = f"{SUBAGENT_WRAPUP_HEADING}\n\nWrap.\n\n{SUBAGENT_FULL_HEADING}\n\nFull."
        yield ((), "updates", {"final_report_generation": {
            "final_report": content, "messages": [AIMessage(content=content)],
        }})

    pushed: list[dict] = []
    state = {"messages": [HumanMessage(content="Query")]}
    config = {"configurable": {"subagent_stream_writer": pushed.append, "thread_id": "t"}}
    with patch(
        "app.agents.research.open_deep_research_compiled.original_research_graph.astream",
        side_effect=_gen,
    ):
        asyncio.run(_run_open_deep_research_subagent(state, config))

    llm_deltas = [e for e in pushed if e.get("type") == "llm_delta"]
    assert not llm_deltas, f"supervisor deltas should be suppressed, got: {llm_deltas}"

    invoke_starts = [e for e in pushed if e.get("type") == "llm_invoke_start"]
    invoke_ends = [e for e in pushed if e.get("type") == "llm_invoke_end"]
    assert not invoke_starts, "No llm_invoke_start from silent supervisor"
    assert not invoke_ends, "No llm_invoke_end from silent supervisor"

    tcs = [e for e in pushed if e.get("type") == "tool_call"]
    tc_names = [e.get("toolName") for e in tcs]
    assert "ConductResearch" in tc_names
    assert "ResearchComplete" not in tc_names


def test_callback_handler_stripped_from_research_config():
    """Parent LlmInvokeLifecycleCallbackHandler must not propagate into research astream."""
    from app.parsers.llm_invoke_callbacks import LlmInvokeLifecycleCallbackHandler

    captured_configs: list[dict] = []

    async def _capture_config(*args, **kwargs):
        cfg = kwargs.get("config") or (args[1] if len(args) > 1 else {})
        captured_configs.append(cfg)
        content = f"{SUBAGENT_WRAPUP_HEADING}\n\nW.\n\n{SUBAGENT_FULL_HEADING}\n\nF."
        yield ((), "updates", {"final_report_generation": {
            "final_report": content, "messages": [AIMessage(content=content)],
        }})

    handler = LlmInvokeLifecycleCallbackHandler()
    state = {"messages": [HumanMessage(content="Q")]}
    config = {
        "configurable": {"subagent_stream_writer": (lambda e: None), "thread_id": "t"},
        "callbacks": [handler],
    }
    with patch(
        "app.agents.research.open_deep_research_compiled.original_research_graph.astream",
        side_effect=_capture_config,
    ):
        asyncio.run(_run_open_deep_research_subagent(state, config))

    assert captured_configs, "astream must have been called"
    inner_cfg = captured_configs[0]
    from app.parsers.llm_invoke_callbacks import flatten_runnable_callbacks
    inner_cbs = flatten_runnable_callbacks(inner_cfg.get("callbacks"))
    assert not any(
        isinstance(cb, LlmInvokeLifecycleCallbackHandler) for cb in inner_cbs
    ), "LlmInvokeLifecycleCallbackHandler must be stripped from research config"


# ---------------------------------------------------------------------------
# Regression: chunk boundary newlines must survive buffer accumulation
# ---------------------------------------------------------------------------

from app.agents.research.open_deep_research_compiled import _extract_visible_raw


def test_extract_visible_raw_preserves_newlines_string_content():
    """String-content chunks must NOT be stripped — newlines at boundaries are meaningful."""
    chunk = AIMessage(content="\n\n## SM_SUBAGENT_FULL_REPORT\n")
    raw = _extract_visible_raw(chunk)
    assert raw.startswith("\n"), "Leading newline must be preserved"
    assert raw.endswith("\n"), "Trailing newline must be preserved"


def test_extract_visible_raw_preserves_newlines_block_content():
    """Block-content chunks skip thinking blocks and preserve text without stripping."""
    chunk = AIMessage(
        content=[
            {"type": "thinking", "thinking": "internal plan"},
            {"type": "text", "text": "\n\n## SM_SUBAGENT_FULL_REPORT\n"},
        ]
    )
    raw = _extract_visible_raw(chunk)
    assert "thinking" not in raw.lower()
    assert raw.startswith("\n"), "Leading newline must be preserved"


def test_buffer_with_chunk_boundary_newlines_parses_anchors():
    """Simulate realistic token streaming where newlines fall at chunk boundaries.

    Before the fix, split_aimessage_thinking_and_visible stripped each chunk,
    destroying newlines and merging heading lines with surrounding content.
    This caused split_subagent_wrapup_and_full to fail exact-match detection.
    """
    chunks = [
        "## SM_SUBAGENT_WRAPUP",    # heading
        "\n\n",                       # blank line (would be stripped to "" and skipped)
        "Brief summary of findings.", # wrapup body
        "\n\n",                       # blank line
        "## SM_SUBAGENT_FULL_REPORT", # heading
        "\n\n",                       # blank line
        "# Full Report Title",        # report content
        "\n\nDetailed paragraph.",     # more content
    ]

    # Simulate _extract_visible_raw for each chunk (string content, no strip).
    buf: list[str] = []
    for c in chunks:
        mock_chunk = AIMessage(content=c)
        raw_vis = _extract_visible_raw(mock_chunk)
        if raw_vis:
            buf.append(raw_vis)

    joined = "".join(buf).strip()
    wrapup, full = split_subagent_wrapup_and_full(joined)
    assert wrapup is not None, f"Anchor parsing failed on joined text: {joined[:200]}"
    assert full is not None
    assert "Brief summary" in wrapup
    assert "Full Report Title" in full
    assert "FULL_REPORT" not in wrapup, "WRAPUP must not contain FULL heading"


def test_buffer_with_stripped_chunks_fails_anchor_parsing():
    """Demonstrate the bug: stripped chunks lose newlines and anchor parsing fails."""
    chunks = [
        "Brief summary of findings.",
        "\n\n",
        "## SM_SUBAGENT_FULL_REPORT",
        "\n\n",
        "# Full Report Title",
    ]

    # Simulate the OLD behavior: strip each chunk.
    buf_old: list[str] = []
    for c in chunks:
        stripped = c.strip()
        if stripped:
            buf_old.append(stripped)

    joined_old = "".join(buf_old)
    # Without newlines, heading merges: "...findings.## SM_SUBAGENT_FULL_REPORT# Full Report..."
    assert "## SM_SUBAGENT_FULL_REPORT#" in joined_old or "\n" not in joined_old.split("FULL_REPORT")[0][-5:], \
        "Stripped chunks should merge heading with adjacent content"


def test_emit_wrapup_sse_only_with_chunked_buffer():
    """End-to-end: streaming chunks → buffer → _emit_research_wrapup_sse_only → WRAPUP only."""
    long_body = "Detailed analysis. " * 100

    async def _gen(*_args, **_kwargs):
        # Simulate realistic multi-chunk streaming for final_report_generation.
        # Each yield is a separate messages event (one chunk per token batch).
        token_chunks = [
            "## SM_SUBAGENT_WRAPUP",
            "\n\n",
            "Brief executive summary.",
            "\n\n",
            "## SM_SUBAGENT_FULL_REPORT",
            "\n\n",
            "# Report Title\n\n",
            long_body,
        ]
        for i, tc in enumerate(token_chunks):
            yield (
                (),
                "messages",
                (
                    AIMessage(content=tc, id=f"chunk-final-{i}"),
                    {"langgraph_node": "final_report_generation"},
                ),
            )
        # Node completion triggers _emit_research_wrapup_sse_only.
        full_content = "".join(token_chunks)
        yield (
            (),
            "updates",
            {
                "final_report_generation": {
                    "final_report": full_content,
                    "messages": [AIMessage(content=full_content)],
                }
            },
        )

    pushed: list[dict] = []
    state = {"messages": [HumanMessage(content="Test query")]}
    config = {
        "configurable": {
            "subagent_stream_writer": pushed.append,
            "thread_id": "test-chunked-wrapup",
        }
    }
    with patch(
        "app.agents.research.open_deep_research_compiled.original_research_graph.astream",
        side_effect=_gen,
    ):
        result = asyncio.run(_run_open_deep_research_subagent(state, config))

    text_deltas = [
        str(e.get("content", ""))
        for e in pushed
        if e.get("type") == "llm_delta" and e.get("channel") == "text"
    ]
    joined_delta = "".join(text_deltas)
    assert "Brief executive summary" in joined_delta, \
        f"WRAPUP body must appear in llm_delta, got: {joined_delta[:300]}"
    assert "FULL_REPORT" not in joined_delta, \
        f"FULL_REPORT heading must NOT appear in llm_delta, got: {joined_delta[:300]}"
    assert "Detailed analysis" not in joined_delta, \
        f"Full report body must NOT appear in llm_delta, got: {joined_delta[:300]}"


def test_emit_wrapup_sse_only_strips_sm_stats_payload_from_wrapup():
    """Regression: deep-research buffers WRAPUP for llm_delta; strip machine stats tail."""
    long_body = "Detailed analysis. " * 100
    stats_tail = (
        "### SM_STATS_PAYLOAD\n\n"
        '```json\n'
        '{"research_stats": {"keyFindings": 6, "recommendations": 3, "gaps": 4}}\n'
        "```\n"
    )

    async def _gen(*_args, **_kwargs):
        token_chunks = [
            "## SM_SUBAGENT_WRAPUP",
            "\n\n",
            "Brief executive summary.\n\n",
            stats_tail,
            "## SM_SUBAGENT_FULL_REPORT",
            "\n\n",
            "# Report Title\n\n",
            long_body,
        ]
        for i, tc in enumerate(token_chunks):
            yield (
                (),
                "messages",
                (
                    AIMessage(content=tc, id=f"chunk-stats-{i}"),
                    {"langgraph_node": "final_report_generation"},
                ),
            )
        full_content = "".join(token_chunks)
        yield (
            (),
            "updates",
            {
                "final_report_generation": {
                    "final_report": full_content,
                    "messages": [AIMessage(content=full_content)],
                }
            },
        )

    pushed: list[dict] = []
    state = {"messages": [HumanMessage(content="Test query")]}
    config = {
        "configurable": {
            "subagent_stream_writer": pushed.append,
            "thread_id": "test-chunked-wrapup-stats",
        }
    }
    with patch(
        "app.agents.research.open_deep_research_compiled.original_research_graph.astream",
        side_effect=_gen,
    ):
        asyncio.run(_run_open_deep_research_subagent(state, config))

    text_deltas = [
        str(e.get("content", ""))
        for e in pushed
        if e.get("type") == "llm_delta" and e.get("channel") == "text"
    ]
    joined_delta = "".join(text_deltas)
    assert "Brief executive summary" in joined_delta
    assert "SM_STATS_PAYLOAD" not in joined_delta
    assert "research_stats" not in joined_delta
    assert "```json" not in joined_delta


# ---------------------------------------------------------------------------
# write_research_brief fallback: structured output via function_calling
# ---------------------------------------------------------------------------


def test_write_research_brief_fallback_emits_brief_from_update():
    """When write_research_brief uses function_calling structured output,
    the LLM response goes into tool_calls (not content), leaving the
    streaming buffer empty.  The fallback must extract research_brief
    from the node update and emit it as visible llm_delta text.
    """
    brief_text = "Analyze Claude Code security architecture for AI agent sandboxing."
    final_content = (
        f"{SUBAGENT_WRAPUP_HEADING}\n\nSummary.\n\n"
        f"{SUBAGENT_FULL_HEADING}\n\nFull body " + "x" * 500
    )

    async def _gen(*_args, **_kwargs):
        # write_research_brief completes (no messages stream — simulates
        # function_calling structured output where content is empty).
        yield (
            (),
            "updates",
            {
                "write_research_brief": {
                    "research_brief": brief_text,
                    "supervisor_messages": {
                        "type": "override",
                        "value": [
                            SystemMessage(content="You are a supervisor."),
                            HumanMessage(content=brief_text),
                        ],
                    },
                }
            },
        )
        # final_report_generation to produce a valid return value.
        yield (
            (),
            "updates",
            {
                "final_report_generation": {
                    "final_report": final_content,
                    "messages": [AIMessage(content=final_content)],
                }
            },
        )

    pushed: list[dict] = []
    state = {"messages": [HumanMessage(content="Test query")]}
    config = {
        "configurable": {
            "subagent_stream_writer": pushed.append,
            "thread_id": "test-brief-fallback",
        }
    }
    with patch(
        "app.agents.research.open_deep_research_compiled.original_research_graph.astream",
        side_effect=_gen,
    ):
        asyncio.run(_run_open_deep_research_subagent(state, config))

    text_deltas = [
        str(e.get("content", ""))
        for e in pushed
        if e.get("type") == "llm_delta" and e.get("channel") == "text"
    ]
    joined_delta = "".join(text_deltas)
    assert "Claude Code" in joined_delta, (
        f"research_brief must appear in llm_delta when streaming buffer is empty, "
        f"got: {joined_delta[:300]}"
    )


def test_write_research_brief_no_double_emit_when_streaming_has_content():
    """When the streaming messages DO produce visible content for
    write_research_brief, the fallback must NOT emit a second copy.
    """
    brief_text = "Study AI agent sandboxing patterns."
    final_content = (
        f"{SUBAGENT_WRAPUP_HEADING}\n\nSummary.\n\n"
        f"{SUBAGENT_FULL_HEADING}\n\nFull body " + "x" * 500
    )

    async def _gen(*_args, **_kwargs):
        # Streaming produces visible content (e.g. json_mode structured output
        # where LLM writes content into the content field).
        yield (
            ("research_supervisor:a",),
            "messages",
            (
                AIMessage(content=f'{{"research_brief": "{brief_text}"}}'),
                {"langgraph_node": "write_research_brief"},
            ),
        )
        # Node completes with the same brief in the update.
        yield (
            (),
            "updates",
            {
                "write_research_brief": {
                    "research_brief": brief_text,
                    "supervisor_messages": {
                        "type": "override",
                        "value": [
                            SystemMessage(content="Supervisor prompt."),
                            HumanMessage(content=brief_text),
                        ],
                    },
                }
            },
        )
        yield (
            (),
            "updates",
            {
                "final_report_generation": {
                    "final_report": final_content,
                    "messages": [AIMessage(content=final_content)],
                }
            },
        )

    pushed: list[dict] = []
    state = {"messages": [HumanMessage(content="Test query")]}
    config = {
        "configurable": {
            "subagent_stream_writer": pushed.append,
            "thread_id": "test-brief-no-double",
        }
    }
    with patch(
        "app.agents.research.open_deep_research_compiled.original_research_graph.astream",
        side_effect=_gen,
    ):
        asyncio.run(_run_open_deep_research_subagent(state, config))

    text_deltas = [
        str(e.get("content", ""))
        for e in pushed
        if e.get("type") == "llm_delta" and e.get("channel") == "text"
    ]
    brief_occurrences = sum(
        1 for d in text_deltas if brief_text in d
    )
    assert brief_occurrences == 1, (
        f"Brief should appear exactly once in llm_delta (streaming OR fallback, not both), "
        f"found {brief_occurrences} in: {text_deltas}"
    )


# ---------------------------------------------------------------------------
# ConductResearch tool_call: empty args from streaming must not block updates
# ---------------------------------------------------------------------------


def test_conduct_research_empty_args_streaming_skipped_updates_emit_complete():
    """LangChain treats tool_call_chunks with args="" as args={} on the
    first streaming chunk.  The messages stream must skip empty-args
    ConductResearch so the updates stream emits the complete version.

    Regression: dedup (emitted_tool_call_sse_ids) prevented the updates
    stream from correcting the empty toolInput emitted by the messages stream.
    """
    final_content = (
        f"{SUBAGENT_WRAPUP_HEADING}\n\nSummary.\n\n"
        f"{SUBAGENT_FULL_HEADING}\n\nFull body " + "x" * 500
    )

    async def _gen(*_args, **_kwargs):
        ns_sup = ("research_supervisor:a", "supervisor:b")
        # Messages stream: first chunk has ConductResearch with empty args
        # (simulates LangChain parsing tool_call_chunks with args="")
        yield (
            ns_sup,
            "messages",
            (
                AIMessage(
                    content="",
                    tool_calls=[
                        {"id": "tc-cr-empty", "name": "ConductResearch", "args": {}},
                    ],
                ),
                {"langgraph_node": "supervisor"},
            ),
        )
        # Updates stream: supervisor completes with full tool_calls
        yield (
            (),
            "updates",
            {
                "supervisor": {
                    "supervisor_messages": [
                        AIMessage(
                            content="",
                            tool_calls=[
                                {
                                    "id": "tc-cr-empty",
                                    "name": "ConductResearch",
                                    "args": {"research_topic": "AI agent sandboxing"},
                                },
                            ],
                        ),
                    ],
                }
            },
        )
        yield (
            (),
            "updates",
            {
                "final_report_generation": {
                    "final_report": final_content,
                    "messages": [AIMessage(content=final_content)],
                }
            },
        )

    pushed: list[dict] = []
    state = {"messages": [HumanMessage(content="Test query")]}
    config = {
        "configurable": {
            "subagent_stream_writer": pushed.append,
            "thread_id": "test-cr-empty-args",
        }
    }
    with patch(
        "app.agents.research.open_deep_research_compiled.original_research_graph.astream",
        side_effect=_gen,
    ):
        asyncio.run(_run_open_deep_research_subagent(state, config))

    cr_events = [
        e for e in pushed
        if e.get("type") == "tool_call" and e.get("toolName") == "ConductResearch"
    ]
    assert cr_events, "ConductResearch tool_call must be emitted (from updates stream)"
    assert cr_events[0].get("toolInput", {}).get("research_topic") == "AI agent sandboxing", (
        f"toolInput must have complete args from updates stream, got: {cr_events[0].get('toolInput')}"
    )


def test_conduct_research_non_empty_args_still_emitted_eagerly():
    """When the messages stream has complete args, the tool_call should
    still be emitted eagerly (not delayed to updates).  This preserves
    real-time UI feedback when the model sends args in one chunk.
    """
    final_content = (
        f"{SUBAGENT_WRAPUP_HEADING}\n\nSummary.\n\n"
        f"{SUBAGENT_FULL_HEADING}\n\nFull body " + "x" * 500
    )

    async def _gen(*_args, **_kwargs):
        ns_sup = ("research_supervisor:a", "supervisor:b")
        # Messages stream: complete args in one chunk
        yield (
            ns_sup,
            "messages",
            (
                AIMessage(
                    content="",
                    tool_calls=[
                        {
                            "id": "tc-cr-full",
                            "name": "ConductResearch",
                            "args": {"research_topic": "Zero-trust architecture"},
                        },
                    ],
                ),
                {"langgraph_node": "supervisor"},
            ),
        )
        yield (
            (),
            "updates",
            {
                "final_report_generation": {
                    "final_report": final_content,
                    "messages": [AIMessage(content=final_content)],
                }
            },
        )

    pushed: list[dict] = []
    state = {"messages": [HumanMessage(content="Test query")]}
    config = {
        "configurable": {
            "subagent_stream_writer": pushed.append,
            "thread_id": "test-cr-eager",
        }
    }
    with patch(
        "app.agents.research.open_deep_research_compiled.original_research_graph.astream",
        side_effect=_gen,
    ):
        asyncio.run(_run_open_deep_research_subagent(state, config))

    cr_events = [
        e for e in pushed
        if e.get("type") == "tool_call" and e.get("toolName") == "ConductResearch"
    ]
    assert cr_events, "ConductResearch must be emitted eagerly when args are complete"
    assert cr_events[0].get("toolInput", {}).get("research_topic") == "Zero-trust architecture"
