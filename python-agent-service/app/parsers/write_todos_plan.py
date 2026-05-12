"""Build frontend task plan dict from write_todos tool arguments (no SSE task_plan emission)."""

from __future__ import annotations

from typing import Any

from app.parsers.path_display_redact import redact_host_paths_in_text


def build_task_plan_dict_from_write_todos_args(tc_args: dict[str, Any]) -> dict[str, Any] | None:
    """Mirror deepagents_stream_adapter write_todos mapping for persistence / progress.

    Returns the inner ``plan`` object shape (``tasks``, ``workspaceTitle``, …), or None
    when there is no usable todo list.
    """
    raw_todos = tc_args.get("todos", []) or tc_args.get("tasks", []) or []
    if not isinstance(raw_todos, list) or not raw_todos:
        return None

    status_map = {
        "pending": "pending",
        "in_progress": "running",
        "completed": "success",
    }
    planned_tasks: list[dict[str, Any]] = []
    for idx, todo in enumerate(raw_todos):
        if not isinstance(todo, dict):
            continue
        todo_id = str(idx)
        task_text = redact_host_paths_in_text(
            str(todo.get("content") or todo.get("task") or todo.get("title") or "")
        )
        raw_status = todo.get("status", "pending")
        fe_status = status_map.get(str(raw_status), "pending")
        planned_tasks.append(
            {
                "id": todo_id,
                "title": task_text,
                "description": task_text,
                "taskType": "security",
                "priority": idx + 1,
                "status": fe_status,
                "durationMs": 0,
                "steps": [],
            }
        )

    if not planned_tasks:
        return None

    ws_title = planned_tasks[0]["title"] if planned_tasks else ""
    plan: dict[str, Any] = {
        "id": "task-plan",
        "tasks": planned_tasks,
        "isSingleTask": len(planned_tasks) == 1,
        "totalDurationMs": 0,
        "status": (
            "running"
            if any(t["status"] == "running" for t in planned_tasks)
            else (
                "success"
                if all(t["status"] == "success" for t in planned_tasks)
                else "pending"
            )
        ),
        "createdAt": "",
    }
    if ws_title:
        plan["workspaceTitle"] = ws_title
    return plan
