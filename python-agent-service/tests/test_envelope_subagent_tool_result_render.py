"""Tests for envelope humanizing subagent tool_result events.

The subagent → main SSE bridge in deepagents vendor middleware emits
``tool_result`` events whose ``toolOutput`` is the raw ToolMessage content
(JSON for many tools). ``tag_merged_subagent_sse`` is the centralized filter
*we* control; it is the right place to route ``toolOutput`` through
:func:`app.sse.tool_result_renderers.render_tool_result` so subagent-internal
tools (e.g. ``detect_web_attack`` running inside the ``web_security``
subagent) reach the UI as humanized text — without touching vendored
deepagents source.

Sibling concerns already handled in the same function (toolOutput
suppression, plain ``Error: ...`` bypass) must keep working after the
humanization step.
"""

from __future__ import annotations

import json

import pytest

from app.sse import tool_result_renderers as _renderers
from app.sse.envelope import tag_merged_subagent_sse


@pytest.fixture(autouse=True)
def _reset_renderer_registry():
    """Snapshot/restore the global renderer registry around each test."""
    snapshot = dict(_renderers._RENDERERS)
    try:
        yield
    finally:
        _renderers._RENDERERS.clear()
        _renderers._RENDERERS.update(snapshot)


def test_subagent_tool_result_json_is_humanized():
    """Without a registered renderer, JSON output is converted to k:v lines."""
    raw_json = json.dumps({"status": "ok", "matches": 3})
    evt = {
        "type": "tool_result",
        "id": "tc-1",
        "toolName": "grep",
        "toolOutput": raw_json,
        "status": "success",
    }

    out = tag_merged_subagent_sse(evt)

    assert "{" not in out["toolOutput"], (
        f"raw JSON leaked: {out['toolOutput']!r}"
    )
    assert "status: ok" in out["toolOutput"]
    assert "matches: 3" in out["toolOutput"]


def test_registered_renderer_takes_precedence_in_envelope():
    """Per-tool renderer wins over generic humanizer in envelope path."""

    @_renderers.register_renderer("fake_subagent_tool")
    def _render(data):
        return f"summary: {data.get('artifact_type', 'unknown')}"

    raw_json = json.dumps(
        {"artifact_type": "webshell_or_code", "noise": "x"}
    )
    evt = {
        "type": "tool_result",
        "id": "tc-1",
        "toolName": "fake_subagent_tool",
        "toolOutput": raw_json,
        "status": "success",
    }

    out = tag_merged_subagent_sse(evt)

    assert out["toolOutput"] == "summary: webshell_or_code"


def test_non_json_tool_output_is_passed_through():
    """Plain text tool output stays untouched by humanizer fallback."""
    evt = {
        "type": "tool_result",
        "id": "tc-1",
        "toolName": "grep",
        "toolOutput": "match found at line 42",
        "status": "success",
    }

    out = tag_merged_subagent_sse(evt)

    assert out["toolOutput"] == "match found at line 42"


def test_empty_tool_output_unchanged():
    """Empty toolOutput must not crash and must stay empty."""
    evt = {
        "type": "tool_result",
        "id": "tc-1",
        "toolName": "grep",
        "toolOutput": "",
        "status": "success",
    }

    out = tag_merged_subagent_sse(evt)

    assert out["toolOutput"] == ""


def test_humanization_preserves_existing_suppression_for_read_file():
    """read_file has emit_output=False; suppression clears post-humanize."""
    evt = {
        "type": "tool_result",
        "id": "tc-1",
        "toolName": "read_file",
        "toolOutput": json.dumps({"content": "secret payload"}),
        "status": "success",
    }

    out = tag_merged_subagent_sse(evt)

    assert out["toolOutput"] == ""


def test_json_error_payload_keeps_error_bypass_after_humanization():
    """JSON {"error": "..."} becomes "error: ..." and bypasses suppression."""
    evt = {
        "type": "tool_result",
        "id": "tc-1",
        "toolName": "read_file",
        "toolOutput": json.dumps({"error": "permission denied"}),
        "status": "success",
    }

    out = tag_merged_subagent_sse(evt)

    assert out["toolOutput"]
    assert out["toolOutput"].lower().startswith("error:")
    assert "permission denied" in out["toolOutput"].lower()


def test_plain_error_string_still_bypasses_suppression():
    """Plain ``Error: ...`` strings continue to bypass suppression."""
    evt = {
        "type": "tool_result",
        "id": "tc-1",
        "toolName": "read_file",
        "toolOutput": "Error: file not found",
        "status": "success",
    }

    out = tag_merged_subagent_sse(evt)

    assert out["toolOutput"] == "Error: file not found"


def test_renderer_failure_falls_back_to_generic_or_raw():
    """If a renderer raises, envelope must still produce a usable string."""

    @_renderers.register_renderer("broken_tool")
    def _render(_data):
        raise RuntimeError("renderer blew up")

    evt = {
        "type": "tool_result",
        "id": "tc-1",
        "toolName": "broken_tool",
        "toolOutput": json.dumps({"k": "v"}),
        "status": "success",
    }

    out = tag_merged_subagent_sse(evt)

    assert isinstance(out["toolOutput"], str)
    assert out["toolOutput"]


def test_non_tool_result_events_unaffected():
    """Humanization only applies to type=='tool_result'."""
    evt = {
        "type": "tool_call",
        "id": "tc-1",
        "toolName": "grep",
        "toolInput": {"pattern": "x"},
    }

    out = tag_merged_subagent_sse(evt)

    assert "toolOutput" not in out
    assert out["type"] == "tool_call"
