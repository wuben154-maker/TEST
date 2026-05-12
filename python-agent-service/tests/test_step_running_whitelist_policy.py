"""Tests for running-step whitelist policy in SSE stream."""

from app.main import _parse_running_step_whitelist, _should_emit_event


def test_parse_running_step_whitelist():
    value = "analysis-start, prefetch-step ,step-1"
    parsed = _parse_running_step_whitelist(value)
    assert parsed == {"analysis-start", "prefetch-step", "step-1"}


def test_should_emit_event_keeps_non_whitelisted_running_step_when_filter_disabled():
    event = {"type": "step", "id": "analysis-start", "status": "running"}
    should_emit = _should_emit_event(
        event, running_step_whitelist={"prefetch-step"}
    )
    assert should_emit is True


def test_should_emit_event_keeps_whitelisted_running_step():
    event = {"type": "step", "id": "analysis-start", "status": "running"}
    should_emit = _should_emit_event(
        event, running_step_whitelist={"analysis-start"}
    )
    assert should_emit is True


def test_should_emit_event_keeps_non_running_step():
    event = {"type": "step", "id": "analysis-start", "status": "success"}
    should_emit = _should_emit_event(
        event, running_step_whitelist=set()
    )
    assert should_emit is True


def test_empty_whitelist_does_not_block_running_steps():
    """Default config: subagent ``task-running-*`` and other running steps must reach the client."""
    event = {"type": "step", "id": "task-running-call_abc", "status": "running"}
    assert _should_emit_event(event, running_step_whitelist=set()) is True
    start = {"type": "step", "id": "analysis-start", "status": "running"}
    assert _should_emit_event(start, running_step_whitelist=set()) is True
