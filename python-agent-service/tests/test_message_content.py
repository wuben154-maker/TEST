"""Tests for message_content handoff and LLM visible content normalization."""

import json

import pytest
from langchain_core.messages import AIMessage

from app.parsers.message_content import (
    additional_kwargs_reasoning_text,
    aimessage_to_handoff_plain_text,
    normalize_llm_visible_content,
)


# ---------- handoff (existing) ----------

def test_handoff_merges_reasoning_content_and_text_blocks():
    msg = AIMessage(
        content=[
            {"type": "thinking", "thinking": "## SM_SUBAGENT_WRAPUP\ns\n\n## SM_SUBAGENT_FULL_REPORT\nLONG"},
            {"type": "text", "text": "short visible only"},
        ],
        additional_kwargs={"reasoning_content": ""},
    )
    out = aimessage_to_handoff_plain_text(msg)
    assert "LONG" in out
    assert "short visible only" in out


def test_handoff_includes_openai_style_reasoning_content_kwarg():
    msg = AIMessage(
        content=[{"type": "text", "text": "wrapup line"}],
        additional_kwargs={"reasoning_content": "full report body here"},
    )
    out = aimessage_to_handoff_plain_text(msg)
    assert "full report body here" in out
    assert "wrapup line" in out


def test_handoff_includes_openrouter_reasoning_alias():
    """OpenRouter documents ``reasoning`` as alias of ``reasoning_content`` on messages."""
    msg = AIMessage(
        content=[{"type": "text", "text": "visible"}],
        additional_kwargs={"reasoning": "internal chain of thought"},
    )
    out = aimessage_to_handoff_plain_text(msg)
    assert "internal chain of thought" in out
    assert "visible" in out


def test_additional_kwargs_reasoning_prefers_reasoning_content_over_alias():
    assert (
        additional_kwargs_reasoning_text(
            {"reasoning_content": "primary", "reasoning": "alias"}
        )
        == "primary"
    )


def test_additional_kwargs_reasoning_details_reasoning_text():
    txt = additional_kwargs_reasoning_text(
        {
            "reasoning_details": [
                {"type": "reasoning.text", "text": "First line."},
                {"type": "reasoning.encrypted", "data": "xxx"},
                {"type": "reasoning.text", "text": "Second line."},
            ]
        }
    )
    assert "First line." in txt and "Second line." in txt


class TestNormalizeClarificationEnvelope:
    """need_clarification JSON -> user-visible text."""

    def test_need_clarification_true_returns_question(self):
        raw = json.dumps({
            "need_clarification": True,
            "question": "Can you clarify the scope?",
            "verification": "",
        })
        assert normalize_llm_visible_content(raw) == "Can you clarify the scope?"

    def test_need_clarification_false_returns_verification(self):
        raw = json.dumps({
            "need_clarification": False,
            "question": "",
            "verification": "I understand your request fully.",
        })
        assert normalize_llm_visible_content(raw) == "I understand your request fully."

    def test_clarification_json_with_leading_prose(self):
        raw = 'Here is my response: {"need_clarification": false, "question": "", "verification": "Got it."}'
        assert normalize_llm_visible_content(raw) == "Got it."

    def test_clarification_json_with_trailing_text(self):
        """The exact pattern the user reported: {JSON}extracted_text concatenated."""
        verification = "我已收到您的请求，将展开深度研究。"
        raw = json.dumps({
            "need_clarification": False,
            "question": "",
            "verification": verification,
        }) + verification
        assert normalize_llm_visible_content(raw) == verification

    def test_clarification_json_with_chinese(self):
        raw = json.dumps({
            "need_clarification": False,
            "question": "",
            "verification": "我已经充分理解了您的需求。",
        })
        assert normalize_llm_visible_content(raw) == "我已经充分理解了您的需求。"

    def test_empty_question_and_verification_returns_empty(self):
        raw = json.dumps({
            "need_clarification": True,
            "question": "",
            "verification": "",
        })
        assert normalize_llm_visible_content(raw) == ""


class TestNormalizeIntentEnvelope:
    """Intent understanding JSON -> empty string."""

    def test_task_category_json_returns_empty(self):
        raw = json.dumps({"task_category": "research", "input_type": "text"})
        assert normalize_llm_visible_content(raw) == ""

    def test_context_reasoning_json_returns_empty(self):
        raw = json.dumps({
            "input_type": "file",
            "context_reasoning": "User uploaded a PDF.",
        })
        assert normalize_llm_visible_content(raw) == ""


class TestNormalizePlainText:
    """Plain text passes through unchanged."""

    def test_plain_text_unchanged(self):
        assert normalize_llm_visible_content("Hello world") == "Hello world"

    def test_markdown_unchanged(self):
        md = "## Analysis\n\n- Point 1\n- Point 2"
        assert normalize_llm_visible_content(md) == md

    def test_empty_string(self):
        assert normalize_llm_visible_content("") == ""

    def test_none_returns_empty(self):
        assert normalize_llm_visible_content(None) == ""  # type: ignore[arg-type]

    def test_whitespace_only(self):
        assert normalize_llm_visible_content("   \n  ") == ""


class TestNormalizeUnknownJson:
    """Unknown JSON objects pass through as-is."""

    def test_unknown_json_object_passthrough(self):
        raw = json.dumps({"foo": "bar", "baz": 42})
        assert normalize_llm_visible_content(raw) == raw.strip()

    def test_json_array_passthrough(self):
        raw = json.dumps([1, 2, 3])
        assert normalize_llm_visible_content(raw) == raw.strip()


class TestNormalizeIdempotent:
    """Calling twice gives the same result."""

    @pytest.mark.parametrize("text", [
        "plain text",
        json.dumps({"need_clarification": False, "question": "", "verification": "OK"}),
        json.dumps({"task_category": "x", "input_type": "y"}),
    ])
    def test_idempotent(self, text):
        first = normalize_llm_visible_content(text)
        second = normalize_llm_visible_content(first)
        assert first == second
