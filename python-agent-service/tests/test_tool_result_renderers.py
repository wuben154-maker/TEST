"""Tests for the per-tool SSE result renderer dispatcher.

The dispatcher must:

- Fall back to :func:`humanize_tool_output` when no renderer is registered.
- Fall back when the payload is not a JSON object.
- Fall back when the registered renderer raises or returns an empty string.
- Return the renderer's output verbatim on success.
- Never raise.
"""

from __future__ import annotations

import json
from typing import Any

import pytest

from app.sse import tool_result_renderers as dispatcher
from app.sse.tool_result_renderers import (
    register_renderer,
    render_tool_result,
)


@pytest.fixture(autouse=True)
def _isolate_registry(monkeypatch: pytest.MonkeyPatch) -> None:
    """Snapshot-and-restore the module-level renderer registry per test."""
    original = dict(dispatcher._RENDERERS)
    yield
    dispatcher._RENDERERS.clear()
    dispatcher._RENDERERS.update(original)


def test_dispatcher_falls_back_to_generic_when_unregistered() -> None:
    raw = json.dumps({"exit_code": 0, "mode": "run"})
    out = render_tool_result("unknown_tool", raw)
    assert out == "exit_code: 0\nmode: run"


def test_dispatcher_uses_registered_renderer_for_object_payload() -> None:
    @register_renderer("fake_tool")
    def _render(data: dict[str, Any]) -> str:
        return f"CUSTOM:{data.get('k')}"

    out = render_tool_result("fake_tool", json.dumps({"k": 7}))
    assert out == "CUSTOM:7"


def test_dispatcher_falls_back_when_renderer_returns_empty() -> None:
    @register_renderer("fake_tool")
    def _render(_data: dict[str, Any]) -> str:
        return ""

    raw = json.dumps({"exit_code": 0})
    assert render_tool_result("fake_tool", raw) == "exit_code: 0"


def test_dispatcher_falls_back_when_renderer_raises() -> None:
    @register_renderer("fake_tool")
    def _render(_data: dict[str, Any]) -> str:
        raise RuntimeError("boom")

    raw = json.dumps({"exit_code": 0})
    assert render_tool_result("fake_tool", raw) == "exit_code: 0"


def test_dispatcher_ignores_non_object_payloads() -> None:
    @register_renderer("fake_tool")
    def _render(_data: dict[str, Any]) -> str:
        return "SHOULD_NOT_RUN"

    assert render_tool_result("fake_tool", "hello world") == "hello world"
    assert render_tool_result("fake_tool", "[1,2,3]") == "1, 2, 3"
    assert render_tool_result("fake_tool", "") == ""


def test_dispatcher_handles_malformed_json_via_fallback() -> None:
    @register_renderer("fake_tool")
    def _render(_data: dict[str, Any]) -> str:
        return "SHOULD_NOT_RUN"

    raw = '{"broken": '
    assert render_tool_result("fake_tool", raw) == raw


def test_register_last_wins() -> None:
    @register_renderer("fake_tool")
    def _a(_data: dict[str, Any]) -> str:
        return "A"

    @register_renderer("fake_tool")
    def _b(_data: dict[str, Any]) -> str:
        return "B"

    assert render_tool_result("fake_tool", json.dumps({})) == "B"
