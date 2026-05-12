"""Regression guard: HITL pause tail must be representable in progress snapshot state."""

from app.services.progress_service import _state_from_events


def test_state_from_events_keeps_parameter_request_before_awaiting_done() -> None:
    """merge_resume_progress reads project_analysis_progress.timeline; it must include the ask."""
    events = [
        {"type": "step", "id": "thinking", "label": "Think", "status": "running"},
        {
            "type": "parameter_request",
            "id": "pr1",
            "detail": "Upload path?",
            "parameterRequests": [
                {
                    "id": "reply",
                    "name": "reply",
                    "paramType": "text",
                    "required": True,
                    "encrypted": False,
                }
            ],
        },
        {"type": "done", "awaitingHuman": True},
    ]
    st = _state_from_events(events)
    tl = st.get("timeline") or []
    types = [e.get("type") for e in tl if isinstance(e, dict)]
    assert "parameter_request" in types
    assert any(
        isinstance(e, dict)
        and e.get("type") == "done"
        and e.get("awaitingHuman") is True
        for e in tl
    )
