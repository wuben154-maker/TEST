"""Gates for clearing project_analysis_progress when the stream pauses for HITL."""

from app.main import _stream_ended_awaiting_human


def test_stream_ended_awaiting_human_true_on_last_done() -> None:
    events = [
        {"type": "step", "id": "a"},
        {"type": "done", "awaitingHuman": False},
        {"type": "done", "awaitingHuman": True},
    ]
    assert _stream_ended_awaiting_human(events) is True


def test_stream_ended_awaiting_human_false_when_last_done_not_human() -> None:
    events = [{"type": "done", "awaitingHuman": False}]
    assert _stream_ended_awaiting_human(events) is False


def test_stream_ended_awaiting_human_false_without_done() -> None:
    assert _stream_ended_awaiting_human([{"type": "error"}]) is False
    assert _stream_ended_awaiting_human([]) is False
