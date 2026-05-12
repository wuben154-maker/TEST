"""Unit tests for _apply_task_lifecycle and _state_from_events task-status tracking.

Pure-function tests – no database or network required.
"""

import pytest

from app.services.progress_service import _apply_task_lifecycle, _state_from_events


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_plan(tasks_status: list[str] | None = None) -> dict:
    """Build a minimal task_plan dict with tasks in given statuses."""
    statuses = tasks_status or ["pending", "pending"]
    return {
        "id": "plan-1",
        "tasks": [
            {"id": str(i), "title": f"Task {i}", "status": s, "steps": []}
            for i, s in enumerate(statuses)
        ],
        "isSingleTask": len(statuses) == 1,
        "totalDurationMs": 0,
        "status": "pending",
        "createdAt": "",
    }


def _ev(event_type: str, **kwargs) -> dict:
    return {"type": event_type, **kwargs}


# ---------------------------------------------------------------------------
# _apply_task_lifecycle
# ---------------------------------------------------------------------------

class TestApplyTaskLifecycle:
    def test_returns_none_when_plan_is_none(self):
        assert _apply_task_lifecycle(None, []) is None

    def test_task_start_sets_running(self):
        plan = _make_plan(["pending", "pending"])
        events = [_ev("task_start", id="0")]
        result = _apply_task_lifecycle(plan, events)

        assert result["tasks"][0]["status"] == "running"
        assert result["tasks"][1]["status"] == "pending"
        assert result["currentTaskId"] == "0"
        assert result["status"] == "running"

    def test_task_complete_sets_success(self):
        plan = _make_plan(["pending", "pending"])
        events = [
            _ev("task_start", id="0"),
            _ev("task_complete", id="0"),
        ]
        result = _apply_task_lifecycle(plan, events)

        assert result["tasks"][0]["status"] == "success"
        assert result["currentTaskId"] is None

    def test_all_tasks_complete_sets_plan_success(self):
        plan = _make_plan(["pending", "pending"])
        events = [
            _ev("task_start", id="0"),
            _ev("task_complete", id="0"),
            _ev("task_start", id="1"),
            _ev("task_complete", id="1"),
        ]
        result = _apply_task_lifecycle(plan, events)

        assert all(t["status"] == "success" for t in result["tasks"])
        assert result["status"] == "success"

    def test_task_error_sets_error_status(self):
        plan = _make_plan(["pending"])
        events = [
            _ev("task_start", id="0"),
            _ev("task_error", id="0", detail="LLM timeout"),
        ]
        result = _apply_task_lifecycle(plan, events)

        assert result["tasks"][0]["status"] == "error"
        assert result["tasks"][0]["error"] == "LLM timeout"
        assert result["currentTaskId"] is None

    def test_task_complete_with_result_and_duration(self):
        plan = _make_plan(["pending"])
        events = [
            _ev("task_start", id="0"),
            _ev("task_complete", id="0", task={"result": "clean", "durationMs": 1234}),
        ]
        result = _apply_task_lifecycle(plan, events)

        assert result["tasks"][0]["result"] == "clean"
        assert result["tasks"][0]["durationMs"] == 1234

    def test_task_step_appended(self):
        plan = _make_plan(["pending"])
        step = {"id": "step-1", "label": "Parsing", "status": "running"}
        events = [_ev("task_step", taskId="0", step=step)]
        result = _apply_task_lifecycle(plan, events)

        assert len(result["tasks"][0]["steps"]) == 1
        assert result["tasks"][0]["steps"][0]["id"] == "step-1"

    def test_task_step_updated_in_place(self):
        plan = _make_plan(["pending"])
        plan["tasks"][0]["steps"] = [{"id": "step-1", "label": "Parsing", "status": "running"}]
        step_update = {"id": "step-1", "label": "Parsing", "status": "success"}
        events = [_ev("task_step", taskId="0", step=step_update)]
        result = _apply_task_lifecycle(plan, events)

        assert len(result["tasks"][0]["steps"]) == 1
        assert result["tasks"][0]["steps"][0]["status"] == "success"

    def test_plan_complete_merges_final_snapshot(self):
        plan = _make_plan(["pending", "pending"])
        events = [
            _ev("task_start", id="0"),
            _ev("task_complete", id="0"),
            _ev("task_start", id="1"),
            _ev("task_complete", id="1"),
            _ev("plan_complete", plan={"totalDurationMs": 5000, "status": "success"}),
        ]
        result = _apply_task_lifecycle(plan, events)

        assert result["totalDurationMs"] == 5000
        assert result["status"] == "success"

    def test_ignores_unknown_task_ids(self):
        plan = _make_plan(["pending"])
        events = [_ev("task_start", id="nonexistent")]
        result = _apply_task_lifecycle(plan, events)

        assert result["tasks"][0]["status"] == "pending"
        assert result["currentTaskId"] is None

    def test_mixed_success_and_error(self):
        plan = _make_plan(["pending", "pending"])
        events = [
            _ev("task_start", id="0"),
            _ev("task_complete", id="0"),
            _ev("task_start", id="1"),
            _ev("task_error", id="1", detail="fail"),
        ]
        result = _apply_task_lifecycle(plan, events)

        assert result["tasks"][0]["status"] == "success"
        assert result["tasks"][1]["status"] == "error"
        assert result["status"] == "success"  # all_done is True (success or error)


# ---------------------------------------------------------------------------
# _state_from_events (integration with _apply_task_lifecycle)
# ---------------------------------------------------------------------------

class TestStateFromEvents:
    def test_basic_fields_extracted(self):
        events = [
            _ev("step", id="s1", label="Init", status="running"),
            _ev("understanding", summary="Understood input"),
            _ev("task_plan", plan=_make_plan(["pending"])),
            _ev("task_summary", summary="All done"),
            _ev("conclusion", content="Report content"),
        ]
        state = _state_from_events(events)

        assert len(state["thinking_steps"]) == 1
        assert state["thinking_steps"][0]["label"] == "Init"
        assert state["task_summary"] == "All done"
        assert state["conclusion"] == "Report content"
        assert state["task_plan"] is not None

    def test_task_lifecycle_applied_to_plan(self):
        events = [
            _ev("task_plan", plan=_make_plan(["pending", "pending"])),
            _ev("task_start", id="0"),
            _ev("task_complete", id="0"),
            _ev("task_start", id="1"),
        ]
        state = _state_from_events(events)
        plan = state["task_plan"]

        assert plan["tasks"][0]["status"] == "success"
        assert plan["tasks"][1]["status"] == "running"
        assert plan["currentTaskId"] == "1"

    def test_no_plan_returns_none(self):
        events = [_ev("step", id="s1", label="Init", status="running")]
        state = _state_from_events(events)
        assert state["task_plan"] is None

    def test_write_todos_tool_call_builds_plan_then_lifecycle(self):
        events = [
            {
                "type": "tool_call",
                "toolName": "write_todos",
                "toolInput": {
                    "todos": [
                        {"content": "A", "status": "pending"},
                        {"content": "B", "status": "pending"},
                    ],
                },
            },
            _ev("task_start", id="0"),
        ]
        state = _state_from_events(events)
        plan = state["task_plan"]
        assert plan is not None
        assert plan["tasks"][0]["status"] == "running"
        assert plan["tasks"][1]["status"] == "pending"

    def test_error_event_adds_to_thinking_steps(self):
        events = [_ev("error", label="Analysis Error", detail="timeout")]
        state = _state_from_events(events)

        assert len(state["thinking_steps"]) == 1
        assert state["thinking_steps"][0]["status"] == "error"
        assert state["error_detail"] == "timeout"

    def test_timeline_matches_message_persistence_filter(self):
        events = [
            _ev("step", id="s1", label="Init", status="running"),
            {"type": "tool_call", "toolName": "search", "id": "tc1", "timestamp": 1},
            {"type": "debug", "detail": "hidden"},
        ]
        state = _state_from_events(events)
        assert "timeline" in state
        assert len(state["timeline"]) == 2
        assert state["timeline"][0]["type"] == "step"
        assert state["timeline"][1]["type"] == "tool_call"
