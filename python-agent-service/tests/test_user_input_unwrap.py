"""Tests for structured user prompt unwrapping (e.g. research_brief JSON envelope)."""

import json

from app.middleware.user_input_unwrap import unwrap_structured_user_prompt


def test_plain_text_unchanged():
    s = "Hello, analyze this alert."
    assert unwrap_structured_user_prompt(s) == s


def test_strips_outer_whitespace_only():
    s = "  brief text  "
    assert unwrap_structured_user_prompt(s) == "brief text"


def test_research_brief_single_key_json():
    inner = "Study AI security vendors from 2025 to 2026."
    raw = json.dumps({"research_brief": inner}, ensure_ascii=False)
    assert unwrap_structured_user_prompt(raw) == inner


def test_research_brief_with_unicode():
    inner = "需要中文报告与英文来源链接。"
    raw = json.dumps({"research_brief": inner}, ensure_ascii=False)
    assert unwrap_structured_user_prompt(raw) == inner


def test_research_brief_sse_chunks_join_before_unwrap():
    """Simulates token/chunk streaming: only full JSON after join should unwrap to inner text."""
    inner = "Study AI security vendors from 2025 to 2026."
    full = json.dumps({"research_brief": inner}, ensure_ascii=False)
    i1 = max(1, len(full) // 3)
    i2 = max(i1 + 1, (2 * len(full)) // 3)
    parts = [full[:i1], full[i1:i2], full[i2:]]
    assert "".join(parts) == full
    assert unwrap_structured_user_prompt("".join(parts)) == inner


def test_multiple_keys_not_unwrapped():
    raw = json.dumps(
        {"research_brief": "a", "extra": "b"}, ensure_ascii=False
    )
    assert unwrap_structured_user_prompt(raw) == raw.strip()


def test_unknown_single_key_not_unwrapped():
    raw = json.dumps({"unknown_key": "value"}, ensure_ascii=False)
    assert unwrap_structured_user_prompt(raw) == raw.strip()


def test_invalid_json_unchanged():
    raw = '{"research_brief": "unclosed'
    assert unwrap_structured_user_prompt(raw) == raw.strip()


def test_not_json_object_unchanged():
    raw = '["a", "b"]'
    assert unwrap_structured_user_prompt(raw) == raw


def test_empty_inner_string_keeps_outer():
    raw = json.dumps({"research_brief": "   "}, ensure_ascii=False)
    assert unwrap_structured_user_prompt(raw) == raw.strip()


def test_fenced_json_block():
    inner = "Fenced brief body."
    body = json.dumps({"research_brief": inner}, ensure_ascii=False)
    raw = f"```json\n{body}\n```"
    assert unwrap_structured_user_prompt(raw) == inner


def test_prompt_alias_single_key():
    inner = "Use prompt key."
    raw = json.dumps({"prompt": inner}, ensure_ascii=False)
    assert unwrap_structured_user_prompt(raw) == inner


def test_none_and_empty():
    assert unwrap_structured_user_prompt("") == ""
    assert unwrap_structured_user_prompt(None) == ""


def test_non_string_passthrough_or_empty():
    assert unwrap_structured_user_prompt(123) == ""  # type: ignore[arg-type]
