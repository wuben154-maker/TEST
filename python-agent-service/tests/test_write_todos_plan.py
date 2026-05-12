"""Unit tests for write_todos → frontend task plan dict helper."""

from app.parsers.write_todos_plan import build_task_plan_dict_from_write_todos_args


def test_build_plan_from_todos_content_field():
    plan = build_task_plan_dict_from_write_todos_args(
        {
            "todos": [
                {"content": "First", "status": "pending"},
                {"content": "Second", "status": "in_progress"},
            ],
        }
    )
    assert plan is not None
    assert plan["workspaceTitle"] == "First"
    assert plan["tasks"][0]["status"] == "pending"
    assert plan["tasks"][1]["status"] == "running"


def test_empty_todos_returns_none():
    assert build_task_plan_dict_from_write_todos_args({"todos": []}) is None


def test_build_plan_redacts_host_path_in_titles():
    plan = build_task_plan_dict_from_write_todos_args(
        {
            "todos": [
                {
                    "content": r"Analyze D:\uploads\u_x\malware.bin",
                    "status": "pending",
                },
            ],
        }
    )
    assert plan is not None
    assert r"D:\uploads" not in plan["tasks"][0]["title"]
    assert plan["tasks"][0]["title"] == "Analyze /workspace/malware.bin"
    assert plan["workspaceTitle"] == "Analyze /workspace/malware.bin"
