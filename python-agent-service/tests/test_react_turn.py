"""Tests for ReAct ``turn`` envelope (``ReactTurnTracker``)."""

import pytest

from app.parsers.react_turn import ReactTurnTracker, attach_turn_to_event


def test_reasoning_chunks_same_turn_then_tool_then_next_turn():
    tr = ReactTurnTracker()
    assert tr.on_reasoning() == 1
    assert tr.on_reasoning() == 1
    assert tr.on_tool_call() == 1
    assert tr.on_tool_result() == 1
    assert tr.on_reasoning() == 2
    assert tr.on_reasoning() == 2


def test_parallel_tool_results_single_pending_next():
    tr = ReactTurnTracker()
    tr.on_reasoning()
    tr.on_tool_result()
    tr.on_tool_result()
    assert tr.on_reasoning() == 2


def test_attach_turn_to_event_idempotent():
    tr = ReactTurnTracker()
    ev = {"type": "reasoning", "id": "r1", "content": "a"}
    attach_turn_to_event(ev, tr)
    assert ev["turn"] == 1
    attach_turn_to_event(ev, tr)
    assert ev["turn"] == 1


def test_attach_turn_to_event_preserves_existing():
    tr = ReactTurnTracker()
    ev = {"type": "reasoning", "id": "r1", "content": "a", "turn": 99}
    attach_turn_to_event(ev, tr)
    assert ev["turn"] == 99


def test_conclusion_turn_after_tool_result():
    tr = ReactTurnTracker()
    tr.on_reasoning()
    tr.on_tool_result()
    ev = {"type": "conclusion", "id": "c", "content": "x"}
    attach_turn_to_event(ev, tr)
    assert ev["turn"] == 2


@pytest.mark.parametrize(
    "typ,expected",
    [
        ("step", 1),
        ("task_plan", 1),
    ],
)
def test_non_tool_events_use_peek(typ: str, expected: int):
    tr = ReactTurnTracker()
    ev = {"type": typ, "id": "x"}
    attach_turn_to_event(ev, tr)
    assert ev["turn"] == expected


def test_llm_delta_reasoning_uses_on_reasoning():
    tr = ReactTurnTracker()
    tr.on_reasoning()
    ev = {"type": "llm_delta", "channel": "reasoning", "content": "x"}
    attach_turn_to_event(ev, tr)
    assert ev["turn"] == 1


def test_llm_delta_text_uses_peek_cycle_turn():
    tr = ReactTurnTracker()
    tr.on_reasoning()
    ev = {"type": "llm_delta", "channel": "text", "content": "y"}
    attach_turn_to_event(ev, tr)
    assert ev["turn"] == 1


def test_llm_invoke_events_use_peek():
    tr = ReactTurnTracker()
    tr.on_tool_call()
    for typ in ("llm_invoke_start", "llm_invoke_end"):
        ev = {"type": typ, "invokeId": "i1"}
        attach_turn_to_event(ev, tr)
        assert ev["turn"] == 1
