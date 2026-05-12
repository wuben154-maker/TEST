"""E2E (no real LLM): POST /uploads x5 -> POST /analyze -> capture first model input.

Shows exactly what the main agent puts in the initial HumanMessage and state["files"]
before any LLM call. Run with -s to print the full report:

  cd python-agent-service && python -m pytest tests/test_e2e_upload_to_llm_first_message.py -v -s
"""

from __future__ import annotations

import json
from unittest.mock import patch

import pytest
from app.auth import create_access_token
from fastapi.testclient import TestClient
from langchain_core.messages import HumanMessage

_E2E_USER_AUTH = {
    "Authorization": f"Bearer {create_access_token('e2e-upload-user', 'e2e-upload@secmanus.test')}",
}
_E2E_ANALYZE_HEADERS = {**_E2E_USER_AUTH, "Accept": "text/event-stream"}


@pytest.fixture
def isolated_upload_dir(tmp_path, monkeypatch):
    """Point UPLOAD_DIR at a temp folder and clear settings cache."""
    upload_root = tmp_path / "uploads"
    upload_root.mkdir(parents=True, exist_ok=True)
    monkeypatch.setenv("UPLOAD_DIR", str(upload_root))
    from app.config.settings import get_settings

    get_settings.cache_clear()
    yield upload_root
    get_settings.cache_clear()


def _print_report(title: str, body: str) -> None:
    line = "=" * 72
    # ASCII titles avoid Windows console mojibake when piping logs
    print(f"\n{line}\n{title}\n{line}\n{body.rstrip()}\n{line}\n")


@pytest.mark.integration
def test_upload_five_files_then_first_llm_input_snapshot(isolated_upload_dir):
    """Simulate 5 file uploads via HTTP, then analyze; capture initial_state for the graph."""
    # Optional: avoid loading real gateway if env is messy (analyze still builds state before LLM)
    from app.main import app
    from app.config.settings import get_settings

    get_settings.cache_clear()

    client = TestClient(app)
    session_id = "e2e5filesess"

    # --- 1) Build 5 small text files (multipart field name must be "files" for FastAPI list) ---
    file_specs = [
        ("alpha.txt", b"# alpha\nline2\n", "text/plain"),
        ("beta.log", b"[INFO] beta\n", "text/plain"),
        ("gamma.cfg", b"key=gamma\n", "text/plain"),
        ("delta.json", b'{"k": "delta"}', "application/json"),
        ("epsilon.md", b"# epsilon\n", "text/markdown"),
    ]
    multipart = []
    for name, raw, ctype in file_specs:
        multipart.append(("files", (name, raw, ctype)))

    up = client.post(
        "/uploads",
        data={"session_id": session_id, "project_id": session_id},
        files=multipart,
        headers=_E2E_USER_AUTH,
    )
    assert up.status_code == 200, up.text
    up_body = up.json()
    assert "files" in up_body
    assert len(up_body["files"]) == 5

    attachments = []
    for row in up_body["files"]:
        attachments.append(
            {
                "filename": row["filename"],
                "content_type": row["content_type"],
                "size": row["size_bytes"],
                "file_path": row["virtual_path"],
                "sha256": row["sha256"],
            }
        )

    captured: dict = {}

    async def fake_adapt_astream(agent, initial_state, config, **kwargs):
        msgs = initial_state.get("messages") or []
        human = next((m for m in msgs if isinstance(m, HumanMessage)), None)
        content = getattr(human, "content", "") if human is not None else ""
        files_state = initial_state.get("files") or {}

        captured["human_message_text"] = content
        captured["files_state_keys"] = list(files_state.keys())
        captured["files_state_len"] = len(files_state)
        captured["upload_response"] = up_body
        captured["analyze_attachments"] = attachments

        yield {"type": "done", "id": "done", "requestId": kwargs.get("request_id", "")}

    # LangChain HumanMessage uses .type == "human"
    with patch(
        "app.parsers.deepagents_stream_adapter.adapt_astream_to_sse",
        side_effect=fake_adapt_astream,
    ):
        payload = {
            "message": "请简要说明这五个上传文件分别是什么用途（端到端测试）",
            "stream": True,
            "session_id": session_id,
            "project_id": session_id,
            "attachments": attachments,
            "ui_language": "zh",
            "input_language": "zh",
        }
        with client.stream(
            "POST",
            "/analyze",
            json=payload,
            headers=_E2E_ANALYZE_HEADERS,
        ) as resp:
            assert resp.status_code == 200
            raw = resp.read()

    assert "human_message_text" in captured
    text = captured["human_message_text"]
    assert "请简要说明这五个上传文件" in text
    assert "[Attached files" in text or "Attached files" in text
    assert "disk_path" not in text
    assert str(isolated_upload_dir) not in text
    assert "/uploads/u_" not in text
    assert "\\uploads\\u_" not in text
    stored_by_name = {
        row["filename"]: row["stored_filename"] for row in up_body["files"]
    }
    for name, _, _ in file_specs:
        assert name in text, f"manifest missing {name}"
        stored_name = stored_by_name[name]
        assert f"`/workspace/{stored_name}`" in text
        assert f"`Workspace/{name}`" not in text
        assert f"`workspace/{name}`" not in text
        assert f"`/workspace/{name}`" not in text
        row_path = f"`/uploads/u_e2e-upload-user/p_{session_id}/{stored_name}`"
        assert row_path not in text
    assert "use detect_web_attack(file_path=...) on file_path" in text.lower()
    assert "pass **`file_path`** to `file_identify`" in text

    # Path-only attachments: no FileData preloaded into state["files"]
    assert captured["files_state_len"] == 0

    # --- Console report (pytest -s) ---
    report_upload = json.dumps(captured["upload_response"], indent=2, ensure_ascii=False)
    report_attach = json.dumps(captured["analyze_attachments"], indent=2, ensure_ascii=False)
    _print_report("STEP 1: POST /uploads response (JSON)", report_upload)
    _print_report("STEP 2: POST /analyze attachments (JSON)", report_attach)
    _print_report(
        "STEP 3: First LLM turn - HumanMessage.content (full string to the agent graph)",
        captured["human_message_text"],
    )
    _print_report(
        "STEP 4: initial_state['files'] (path-only uploads = empty dict)",
        json.dumps(
            {
                "keys": captured["files_state_keys"],
                "count": captured["files_state_len"],
            },
            indent=2,
            ensure_ascii=False,
        ),
    )

    # Non-silent assertion summary for CI without -s
    assert raw  # stream body consumed
