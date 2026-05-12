"""Tests for layered deep-research task description parsing.

The main agent formats its ``task(deep-research)`` description with a
``ORIGINAL_QUERY:`` prefix and ``---CONTEXT---`` separator so the research
graph can distinguish the user's verbatim question from preliminary explore
findings that may be inaccurate.
"""

from langchain_core.messages import HumanMessage, SystemMessage

from app.agents.research.open_deep_research_compiled import (
    _build_layered_research_messages,
    parse_layered_task_description,
)


# ---------------------------------------------------------------------------
# parse_layered_task_description
# ---------------------------------------------------------------------------

class TestParseLayeredTaskDescription:
    def test_full_layered_format(self):
        raw = (
            "ORIGINAL_QUERY: 深度分析多Agent系统的安全威胁\n"
            "---CONTEXT---\n"
            "Preliminary search found references to prompt injection and MCP attack vectors."
        )
        original, context = parse_layered_task_description(raw)
        assert original == "深度分析多Agent系统的安全威胁"
        assert "prompt injection" in context
        assert "MCP attack" in context

    def test_original_query_prefix_stripped(self):
        raw = "ORIGINAL_QUERY: What are the latest CVEs for Log4j?"
        original, context = parse_layered_task_description(raw)
        assert original == "What are the latest CVEs for Log4j?"
        assert context == ""

    def test_backward_compatible_no_markers(self):
        raw = "Comprehensive research on OpenClaw: CVEs, threat landscape, mitigation."
        original, context = parse_layered_task_description(raw)
        assert original == raw
        assert context == ""

    def test_empty_context_after_separator(self):
        raw = "ORIGINAL_QUERY: test question\n---CONTEXT---\n"
        original, context = parse_layered_task_description(raw)
        assert original == "test question"
        assert context == ""

    def test_multiline_context(self):
        raw = (
            "ORIGINAL_QUERY: research topic\n"
            "---CONTEXT---\n"
            "Line 1 of context.\n"
            "Line 2 with CVE-2025-12345 (unconfirmed).\n"
            "Line 3."
        )
        original, context = parse_layered_task_description(raw)
        assert original == "research topic"
        assert "Line 1" in context
        assert "CVE-2025-12345" in context
        assert "Line 3" in context

    def test_case_insensitive_prefix(self):
        raw = "original_query: some question"
        original, context = parse_layered_task_description(raw)
        assert original == "some question"

    def test_only_separator_no_prefix(self):
        raw = "Some question text\n---CONTEXT---\nSome context"
        original, context = parse_layered_task_description(raw)
        assert original == "Some question text"
        assert context == "Some context"


# ---------------------------------------------------------------------------
# _build_layered_research_messages
# ---------------------------------------------------------------------------

class TestBuildLayeredResearchMessages:
    def test_layered_produces_human_and_system(self):
        raw = (
            "ORIGINAL_QUERY: 分析Claude Code的安全漏洞\n"
            "---CONTEXT---\n"
            "Found CVE-2025-59536 (unconfirmed) related to sandbox escape."
        )
        msgs = _build_layered_research_messages(raw)
        assert len(msgs) == 2
        assert isinstance(msgs[0], HumanMessage)
        assert isinstance(msgs[1], SystemMessage)
        assert msgs[0].content == "分析Claude Code的安全漏洞"
        assert "Preliminary context from routing agent" in msgs[1].content
        assert "CVE-2025-59536" in msgs[1].content

    def test_plain_query_produces_single_human(self):
        raw = "What is Log4Shell?"
        msgs = _build_layered_research_messages(raw)
        assert len(msgs) == 1
        assert isinstance(msgs[0], HumanMessage)
        assert msgs[0].content == "What is Log4Shell?"

    def test_original_query_only_no_context(self):
        raw = "ORIGINAL_QUERY: Research OpenClaw vulnerabilities"
        msgs = _build_layered_research_messages(raw)
        assert len(msgs) == 1
        assert isinstance(msgs[0], HumanMessage)
        assert msgs[0].content == "Research OpenClaw vulnerabilities"

    def test_empty_string_fallback(self):
        msgs = _build_layered_research_messages("")
        assert len(msgs) == 1
        assert isinstance(msgs[0], HumanMessage)

    def test_context_message_warns_about_inaccuracy(self):
        raw = "ORIGINAL_QUERY: test\n---CONTEXT---\nSome finding."
        msgs = _build_layered_research_messages(raw)
        sys_msg = msgs[1]
        assert "may contain inaccuracies" in sys_msg.content
        assert "Verify independently" in sys_msg.content
