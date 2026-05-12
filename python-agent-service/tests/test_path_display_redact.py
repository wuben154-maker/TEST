"""Tests for host-path redaction in user-visible strings."""

from app.parsers.path_display_redact import (
    redact_host_paths_in_text,
    sanitize_task_tool_input_for_display,
    sanitize_write_todos_tool_input_for_display,
)


def test_redact_windows_absolute_to_workspace_basename():
    raw = (
        r"Analyze binary file located at D:\code\cursor\demo\sec-manus\secmanus-workspace\python-agent-service\uploads\u_a0e19924\p_33cceb8d\5cb9c8c118fb_abcd.exe"
    )
    out = redact_host_paths_in_text(raw)
    assert r"D:\code" not in out
    assert "uploads" not in out
    assert "/workspace/5cb9c8c118fb_abcd.exe" in out


def test_redact_win_forward_slashes():
    out = redact_host_paths_in_text("Run D:/a/b/c.bin please")
    assert "/workspace/c.bin" in out
    assert "D:/" not in out


def test_redact_unc_path():
    out = redact_host_paths_in_text(r"Copy from \\nas\share\folder\doc.dll")
    assert r"\\nas" not in out
    assert "/workspace/doc.dll" in out


def test_redact_unix_uploads_layout():
    out = redact_host_paths_in_text("file is /var/app/python-agent-service/uploads/u_99/p_1/x.sh")
    assert "/var/app" not in out
    assert "/workspace/x.sh" in out


def test_preserves_existing_workspace_path():
    s = "Use /workspace/parent/sample.bin only"
    assert redact_host_paths_in_text(s) == s


def test_sanitize_write_todos_copies_and_redacts():
    inp = {
        "todos": [
            {
                "content": r"Task D:\secret\evil.exe",
                "title": r"D:\secret\evil.exe",
                "status": "pending",
            }
        ]
    }
    clean = sanitize_write_todos_tool_input_for_display(inp)
    assert inp["todos"][0]["content"] == r"Task D:\secret\evil.exe"
    assert clean["todos"][0]["content"] == "Task /workspace/evil.exe"
    assert clean["todos"][0]["title"] == "/workspace/evil.exe"


def test_sanitize_task_description():
    desc = r'{"taskObjective": "x", "files": []}'  # no path
    assert sanitize_task_tool_input_for_display({"description": desc})["description"] == desc
    leak = r"Delegate with D:\a\b\c.bin"
    out = sanitize_task_tool_input_for_display({"description": leak})["description"]
    assert r"D:\a" not in out
    assert "/workspace/c.bin" in out
