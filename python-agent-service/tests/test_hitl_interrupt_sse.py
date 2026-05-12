"""Unit tests for LangGraph interrupt → SSE mapping."""

from __future__ import annotations

from langgraph.types import Interrupt

from app.parsers.hitl_interrupt_sse import interrupts_to_sse_events


def test_hitl_request_emits_decision_request() -> None:
    hitl = {
        "action_requests": [
            {
                "name": "execute",
                "args": {"cmd": "ls"},
                "description": "Run shell command",
            }
        ],
        "review_configs": [
            {"action_name": "execute", "allowed_decisions": ["approve", "reject"]}
        ],
    }
    intr = Interrupt(value=hitl, id="abc123")
    seq = [0]

    def emit(ev: dict) -> dict:
        seq[0] += 1
        return {**ev, "seq": seq[0]}

    events, meta = interrupts_to_sse_events(
        (intr,),
        emit,
        stream_request_id="stream-rid-1",
    )
    assert len(events) == 1
    assert events[0]["type"] == "decision_request"
    assert events[0]["requestId"] == "stream-rid-1"
    assert events[0]["interruptRequestId"] == "abc123"
    assert events[0]["interruptKind"] == "langchain_hitl_v1"
    assert events[0]["interruptId"] == "abc123"
    assert "hitlRequest" in events[0]
    assert meta["interruptIds"] == ["abc123"]


def test_user_input_choice_emits_decision_request() -> None:
    payload = {
        "interruptKind": "user_input_v1",
        "requestId": "r1",
        "kind": "choice",
        "prompt": "Pick one",
        "options": ["A", "B"],
    }
    intr = Interrupt(value=payload, id="xyz")
    events, meta = interrupts_to_sse_events(
        (intr,),
        lambda x: x,
        stream_request_id="stream-rid-2",
    )
    assert len(events) == 1
    assert events[0]["type"] == "decision_request"
    assert events[0]["requestId"] == "stream-rid-2"
    assert events[0]["interruptRequestId"] == "r1"
    assert events[0]["userInputKind"] == "choice"
    assert meta["interruptIds"] == ["xyz"]


def test_user_input_text_emits_parameter_request() -> None:
    payload = {
        "interruptKind": "user_input_v1",
        "requestId": "r2",
        "kind": "text",
        "prompt": "Your name?",
    }
    intr = Interrupt(value=payload, id="t1")
    events, _ = interrupts_to_sse_events(
        (intr,),
        lambda x: x,
        stream_request_id="stream-rid-3",
    )
    assert len(events) == 1
    assert events[0]["type"] == "parameter_request"
    assert events[0]["requestId"] == "stream-rid-3"
    assert events[0]["interruptRequestId"] == "r2"
    assert events[0]["parameterRequests"]
