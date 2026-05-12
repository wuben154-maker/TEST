"""Anthropic-style message content must not become str(dict) in research output."""

from langchain_core.messages import AIMessage, ToolMessage

from app.agents.research.open_deep_research_original_adapter import (
    _extract_content_text,
    _extract_visible_answer_text,
)
from app.agents.research.open_deep_research_compiled import _extract_final_text


def test_extract_visible_answer_prefers_text_blocks_only():
    blocks = [
        {"type": "thinking", "thinking": "internal only", "index": 0},
        {"type": "text", "text": "# Report\n\nHello world."},
    ]
    assert _extract_visible_answer_text(blocks) == "# Report\n\nHello world."
    assert "internal only" not in _extract_visible_answer_text(blocks)


def test_extract_content_text_joins_thinking_and_text():
    blocks = [
        {"type": "thinking", "thinking": "think"},
        {"type": "text", "text": "answer"},
    ]
    out = _extract_content_text(blocks)
    assert "think" in out
    assert "answer" in out


def test_extract_final_text_from_state_list_not_str_dict():
    result = {
        "final_report": [
            {"type": "thinking", "thinking": "chain", "index": 0},
            {"type": "text", "text": "## Final\nBody"},
        ]
    }
    out = _extract_final_text(result)
    assert "## Final\nBody" in out
    assert "chain" in out


def test_legacy_str_join_would_have_been_broken():
    blocks = [
        {"type": "thinking", "thinking": "x", "index": 0},
        {"type": "text", "text": "y"},
    ]
    bad = "\n".join(str(item) for item in blocks if item)
    assert bad.startswith("{")
    assert _extract_visible_answer_text(blocks) == "y"


def test_extract_final_text_prefers_final_report_over_short_tail_aimessage():
    """Regression: do not use messages[-1] when it is a short AIMessage."""
    long_body = "## SM_SUBAGENT_FULL_REPORT\n" + ("paragraph\n" * 80)
    result = {
        "final_report": long_body,
        "messages": [AIMessage(content="brief tail line")],
    }
    out = _extract_final_text(result)
    assert "SM_SUBAGENT_FULL_REPORT" in out
    assert len(out) > 200


def test_extract_final_text_reversed_skips_tool_calls_and_toolmessage_tail():
    """Newest-first: last non-tool AIMessage; ignore ToolMessage at end."""
    result = {
        "messages": [
            AIMessage(
                content="",
                tool_calls=[{"id": "a", "name": "ConductResearch", "args": {}}],
            ),
            ToolMessage(content="nested", tool_call_id="a", name="ConductResearch"),
            AIMessage(content="## SM_SUBAGENT_WRAPUP\nw\n\n## SM_SUBAGENT_FULL_REPORT\nFULL"),
        ]
    }
    assert "FULL" in _extract_final_text(result)
    assert "nested" not in _extract_final_text(result)
