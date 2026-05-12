"""Resume progress merge: keep first-leg timeline/state when upserting during POST /analyze/resume."""

import copy

import pytest

from app.services.progress_service import (
    build_decision_response_timeline_event,
    build_parameter_response_timeline_event,
    merge_resume_progress_state,
)


class TestBuildDecisionResponseTimelineEvent:
    def test_returns_none_without_id_or_options(self):
        assert build_decision_response_timeline_event(decision_ui_id=None, selected_options=None) is None
        assert build_decision_response_timeline_event(decision_ui_id="d1", selected_options=None) is None
        assert build_decision_response_timeline_event(decision_ui_id="", selected_options=["a"]) is None

    def test_builds_decision_response_row(self):
        ev = build_decision_response_timeline_event(
            decision_ui_id="dec-1",
            selected_options=["approve", "x"],
            timestamp_ms=99,
        )
        assert ev is not None
        assert ev["type"] == "decision_response"
        assert ev["decisionUiId"] == "dec-1"
        assert ev["selectedOptions"] == ["approve", "x"]
        assert ev["timestamp"] == 99


class TestBuildParameterResponseTimelineEvent:
    def test_returns_none_for_decisions_only_resume(self):
        assert build_parameter_response_timeline_event({"decisions": [{"type": "approve"}]}) is None

    def test_returns_none_for_non_dict(self):
        assert build_parameter_response_timeline_event("text") is None

    def test_builds_event_for_form_like_resume(self):
        ev = build_parameter_response_timeline_event(
            {"reply": "hello", "requestId": "rid-1"},
            timestamp_ms=42,
        )
        assert ev is not None
        assert ev["type"] == "parameter_response"
        assert ev["id"] == "hitl-parameter-response"
        assert ev["timestamp"] == 42
        assert ev["parameters"] == {"reply": "hello", "requestId": "rid-1"}


class TestMergeResumeProgressState:
    def test_appends_tail_timeline_after_base(self):
        base = {
            "timeline": [{"type": "step", "id": "a"}],
            "thinking_steps": [{"id": "a", "label": "L", "status": "success"}],
            "task_plan": None,
            "understanding": None,
            "task_summary": "",
            "conclusion": "",
            "blocks": [],
            "error_detail": "",
        }
        tail_events = [{"type": "step", "id": "b", "label": "B", "status": "running"}]
        merged = merge_resume_progress_state(base, tail_events)
        assert len(merged["timeline"]) == 2
        assert merged["timeline"][0]["id"] == "a"
        assert merged["timeline"][1]["id"] == "b"

    def test_preserves_parameter_response_in_tail(self):
        base = {"timeline": [{"type": "done", "id": "d1", "awaitingHuman": True}]}
        tail_events = [
            {
                "type": "parameter_response",
                "id": "hitl-parameter-response",
                "timestamp": 1,
                "parameters": {"reply": "ok"},
            },
            {"type": "step", "id": "s2", "label": "x", "status": "running"},
        ]
        merged = merge_resume_progress_state(base, tail_events)
        types = [r["type"] for r in merged["timeline"]]
        assert types == ["done", "parameter_response", "step"]

    def test_applies_task_lifecycle_on_base_plan_with_resume_events(self):
        base_plan = {
            "id": "plan",
            "tasks": [{"id": "0", "title": "T", "status": "running", "steps": []}],
            "status": "running",
            "currentTaskId": "0",
        }
        base = {
            "timeline": [],
            "thinking_steps": [],
            "task_plan": copy.deepcopy(base_plan),
            "understanding": None,
            "task_summary": "",
            "conclusion": "",
            "blocks": [],
            "error_detail": "",
        }
        tail_events = [
            {"type": "task_complete", "id": "0", "task": {"result": "ok", "durationMs": 1}},
        ]
        merged = merge_resume_progress_state(base, tail_events)
        assert merged["task_plan"] is not None
        assert merged["task_plan"]["tasks"][0]["status"] == "success"
