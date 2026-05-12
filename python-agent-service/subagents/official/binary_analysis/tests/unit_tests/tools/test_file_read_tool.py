"""Unit tests for :mod:`tools.file_read_tool` (C7-AC4/AC5)."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

import audit as audit_module
from audit import analysis_context
from sandbox.client import SandboxSession, sandbox_workspace
from sandbox.registry import _SESSION_REGISTRY
from tools.file_read_tool import DEFAULT_MAX_BYTES, FileReadTool


class _FakeSandboxClient:
    """SandboxClient with an in-memory filesystem for workspace downloads."""

    def __init__(self, files: dict[str, bytes]) -> None:
        self.files = dict(files)
        self.download_calls: list[str] = []

    async def create(self, analysis_id: str) -> SandboxSession:  # pragma: no cover
        raise NotImplementedError

    async def exec(self, *args: Any, **kwargs: Any) -> Any:  # pragma: no cover
        raise NotImplementedError

    async def upload(self, session: SandboxSession, path: str, data: bytes) -> None:
        self.files[path] = data

    async def download(self, session: SandboxSession, path: str) -> bytes:
        self.download_calls.append(path)
        if path not in self.files:
            msg = f"file not found in fake sandbox: {path!r}"
            raise FileNotFoundError(msg)
        return self.files[path]

    async def kill(self, session: SandboxSession) -> None:
        _SESSION_REGISTRY.pop(session.analysis_id, None)


def _make_session(analysis_id: str) -> SandboxSession:
    session = SandboxSession(
        analysis_id=analysis_id,
        sandbox_id=f"fake-{analysis_id}",
        backend="subprocess",
        workdir=sandbox_workspace(analysis_id),
        created_at=0.0,
    )
    _SESSION_REGISTRY[analysis_id] = session
    return session


@pytest.fixture(autouse=True)
def _clean_registry_and_logdir(monkeypatch, tmp_path: Path):
    _SESSION_REGISTRY.clear()
    monkeypatch.setattr(audit_module, "_DEFAULT_LOG_DIR", tmp_path)
    yield tmp_path
    _SESSION_REGISTRY.clear()


def _read_audit(aid: str, log_dir: Path) -> list[dict[str, Any]]:
    path = log_dir / f"{aid}.audit.jsonl"
    if not path.is_file():
        return []
    return [
        json.loads(line)
        for line in path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]


# ---------------------------------------------------------------------------
# C7-AC4: path constraints + raw-binary denial
# ---------------------------------------------------------------------------


class TestAC4PathConstraints:
    async def test_json_artefact_read_succeeds(self):
        aid = "aid-json"
        _make_session(aid)
        payload = b'{"sections": [{"name": ".text"}]}'
        client = _FakeSandboxClient({f"/workspace/{aid}/pe_info.json": payload})
        tool = FileReadTool(sandbox_client=client)
        result = await tool.ainvoke(
            {"path": f"/workspace/{aid}/pe_info.json", "analysis_id": aid}
        )
        assert result["ok"] is True
        assert result["content"] == payload.decode("utf-8")
        assert result["bytes_returned"] == len(payload)
        assert result["truncated"] is False

    async def test_sample_bin_read_rejected_with_raw_binary_forbidden(self):
        aid = "aid-sample"
        _make_session(aid)
        client = _FakeSandboxClient(
            {f"/workspace/{aid}/sample.bin": b"\x4d\x5a\x90\x00"}
        )
        tool = FileReadTool(sandbox_client=client)
        result = await tool.ainvoke(
            {"path": f"/workspace/{aid}/sample.bin", "analysis_id": aid}
        )
        assert result["ok"] is False
        assert result["error_code"] == "TOOL_SCHEMA_INVALID"
        assert result["reason"] == "raw_binary_forbidden"
        assert client.download_calls == []

    @pytest.mark.parametrize(
        "name", ["packed.exe", "module.DLL", "payload.so", "lib.dylib", "blob.bin"]
    )
    async def test_binary_extensions_rejected(self, name: str):
        aid = "aid-bin"
        _make_session(aid)
        client = _FakeSandboxClient({f"/workspace/{aid}/{name}": b"\x00\x01"})
        tool = FileReadTool(sandbox_client=client)
        result = await tool.ainvoke(
            {"path": f"/workspace/{aid}/{name}", "analysis_id": aid}
        )
        assert result["ok"] is False
        assert result["error_code"] == "TOOL_SCHEMA_INVALID"
        assert result["reason"] == "raw_binary_forbidden"

    async def test_path_outside_workspace_rejected(self):
        aid = "aid-out"
        _make_session(aid)
        client = _FakeSandboxClient({})
        tool = FileReadTool(sandbox_client=client)
        result = await tool.ainvoke({"path": "/etc/passwd", "analysis_id": aid})
        assert result["ok"] is False
        assert result["error_code"] == "TOOL_SCHEMA_INVALID"
        assert result["reason"] == "path_outside_workspace"

    async def test_path_traversal_rejected(self):
        aid = "aid-trav"
        _make_session(aid)
        client = _FakeSandboxClient({})
        tool = FileReadTool(sandbox_client=client)
        result = await tool.ainvoke(
            {
                "path": f"/workspace/{aid}/../../etc/passwd",
                "analysis_id": aid,
            }
        )
        assert result["ok"] is False
        assert result["error_code"] == "TOOL_SCHEMA_INVALID"
        assert result["reason"] == "path_outside_workspace"

    async def test_relative_path_rejected(self):
        aid = "aid-rel"
        _make_session(aid)
        client = _FakeSandboxClient({})
        tool = FileReadTool(sandbox_client=client)
        result = await tool.ainvoke({"path": "pe_info.json", "analysis_id": aid})
        assert result["ok"] is False
        assert result["error_code"] == "TOOL_SCHEMA_INVALID"
        assert result["reason"] == "path_outside_workspace"

    async def test_oversized_file_truncated(self):
        aid = "aid-trunc"
        _make_session(aid)
        big = b"X" * (DEFAULT_MAX_BYTES + 100)
        client = _FakeSandboxClient({f"/workspace/{aid}/big.txt": big})
        tool = FileReadTool(sandbox_client=client)
        result = await tool.ainvoke(
            {"path": f"/workspace/{aid}/big.txt", "analysis_id": aid}
        )
        assert result["truncated"] is True
        assert result["bytes_returned"] == DEFAULT_MAX_BYTES


# ---------------------------------------------------------------------------
# Session missing guard
# ---------------------------------------------------------------------------


class TestSessionGuard:
    async def test_missing_session_returns_schema_error(self):
        tool = FileReadTool(sandbox_client=_FakeSandboxClient({}))
        result = await tool.ainvoke(
            {"path": "/workspace/aid-missing/x.json", "analysis_id": "aid-missing"}
        )
        assert result["ok"] is False
        assert result["error_code"] == "TOOL_SCHEMA_INVALID"
        assert result["reason"] == "sandbox_session_missing"


# ---------------------------------------------------------------------------
# Missing sandbox file → recoverable tool error (IR-11)
# ---------------------------------------------------------------------------


class TestMissingFile:
    async def test_missing_path_returns_file_not_found(
        self, _clean_registry_and_logdir
    ):
        log_dir: Path = _clean_registry_and_logdir
        aid = "aid-missing-file"
        _make_session(aid)
        path = f"/workspace/{aid}/strings.txt"
        client = _FakeSandboxClient({})
        tool = FileReadTool(sandbox_client=client)
        with analysis_context(aid):
            result = await tool.ainvoke({"path": path, "analysis_id": aid})
        assert result["ok"] is False
        assert result["error_code"] == "FILE_NOT_FOUND"
        assert result["reason"] == "file_not_found"
        assert result["path"] == path
        assert "bash tool is not a shell" in result["message"]
        assert result["details"]["path"] == path
        assert result["details"]["analysis_id"] == aid
        entries = _read_audit(aid, log_dir)
        assert len(entries) == 1
        assert entries[0]["success"] is False
        assert entries[0]["error_code"] == "FILE_NOT_FOUND"


# ---------------------------------------------------------------------------
# C7-AC5: audit log
# ---------------------------------------------------------------------------


class TestAC5Audit:
    async def test_successful_read_writes_tool_call_event(
        self, _clean_registry_and_logdir
    ):
        log_dir: Path = _clean_registry_and_logdir
        aid = "aid-audit-fr"
        _make_session(aid)
        payload = b'{"ok": true}'
        client = _FakeSandboxClient({f"/workspace/{aid}/result.json": payload})
        tool = FileReadTool(sandbox_client=client)
        with analysis_context(aid):
            await tool.ainvoke(
                {"path": f"/workspace/{aid}/result.json", "analysis_id": aid}
            )
        entries = _read_audit(aid, log_dir)
        assert len(entries) == 1
        entry = entries[0]
        assert entry["event_type"] == "tool_call"
        assert entry["tool_name"] == "file_read"
        assert entry["success"] is True
        assert entry["args"]["path"] == f"/workspace/{aid}/result.json"
        assert entry["result"]["bytes_returned"] == len(payload)
