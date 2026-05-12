"""Unit tests for :mod:`tools.python_exec_tool` (C7-AC3/AC5)."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

import audit as audit_module
from audit import analysis_context
from sandbox.client import ExecResult, SandboxSession, sandbox_workspace
from sandbox.registry import _SESSION_REGISTRY
from tools.bash_tool import (
    DEFAULT_LLM_PREVIEW_HEAD_BYTES,
    DEFAULT_LLM_PREVIEW_TAIL_BYTES,
    DEFAULT_STREAM_LIMIT_BYTES,
)
from tools.python_exec_tool import PythonExecTool


class _FakeSandboxClient:
    """SandboxClient stub whose ``exec`` output is a function of the payload.

    Simulates the sandbox network-block invariant: any ``import requests``
    snippet is treated as a runtime failure, mirroring the real E2B VM with
    ``allow_internet_access=False``.
    """

    def __init__(self) -> None:
        self.exec_calls: list[dict[str, Any]] = []

    async def create(self, analysis_id: str) -> SandboxSession:  # pragma: no cover
        raise NotImplementedError

    async def exec(
        self,
        session: SandboxSession,
        cmd: str | list[str],
        *,
        timeout: float,
        user: str = "user",
        cwd: str | None = None,
    ) -> ExecResult:
        self.exec_calls.append(
            {"session": session, "cmd": cmd, "timeout": timeout, "cwd": cwd}
        )
        assert isinstance(cmd, list)
        assert cmd[:2] == ["python3", "-c"]
        code = cmd[2]
        if "import requests" in code or "urllib" in code:
            return ExecResult(
                stdout="",
                stderr=(
                    "Traceback (most recent call last):\n"
                    '  File "<string>", line 1, in <module>\n'
                    "ConnectionError: outbound network blocked by sandbox\n"
                ),
                exit_code=1,
                duration_ms=8.0,
                timed_out=False,
            )
        if "import pefile" in code:
            return ExecResult(
                stdout="{'sections': 4}\n",
                stderr="",
                exit_code=0,
                duration_ms=18.0,
                timed_out=False,
            )
        return ExecResult(
            stdout="",
            stderr="",
            exit_code=0,
            duration_ms=5.0,
            timed_out=False,
        )

    async def upload(self, *args: Any, **kwargs: Any) -> None:  # pragma: no cover
        raise NotImplementedError

    async def download(self, *args: Any, **kwargs: Any) -> bytes:  # pragma: no cover
        raise NotImplementedError

    async def kill(self, session: SandboxSession) -> None:
        _SESSION_REGISTRY.pop(session.analysis_id, None)


class _ExecFailingSandboxClient(_FakeSandboxClient):
    async def exec(
        self,
        session: SandboxSession,
        cmd: str | list[str],
        *,
        timeout: float,
        user: str = "user",
        cwd: str | None = None,
    ) -> ExecResult:
        self.exec_calls.append(
            {"session": session, "cmd": cmd, "timeout": timeout, "cwd": cwd}
        )
        raise RuntimeError("backend unavailable")


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
# C7-AC3: import pefile succeeds; import requests blocked by sandbox
# ---------------------------------------------------------------------------


class TestAC3WhitelistedPackages:
    async def test_import_pefile_runs_successfully(self):
        _make_session("aid-pe")
        client = _FakeSandboxClient()
        tool = PythonExecTool(sandbox_client=client)
        result = await tool.ainvoke(
            {
                "code": "import pefile; print({'sections': 4})",
                "analysis_id": "aid-pe",
            }
        )
        assert result["ok"] is True
        assert result["exit_code"] == 0
        assert "sections" in result["stdout"]
        cmd = client.exec_calls[0]["cmd"]
        assert cmd[0] == "python3"
        assert cmd[1] == "-c"

    async def test_import_requests_blocked_by_sandbox_mock(self):
        """Fallback mock simulates ``allow_internet_access=False``."""
        _make_session("aid-net")
        client = _FakeSandboxClient()
        tool = PythonExecTool(sandbox_client=client)
        result = await tool.ainvoke(
            {
                "code": "import requests; requests.get('http://example.com')",
                "analysis_id": "aid-net",
            }
        )
        assert result["ok"] is False
        assert result["exit_code"] == 1
        assert "blocked" in result["stderr"].lower()

    async def test_pip_install_rejected_without_reaching_sandbox(self):
        _make_session("aid-pip")
        client = _FakeSandboxClient()
        tool = PythonExecTool(sandbox_client=client)
        result = await tool.ainvoke(
            {
                "code": "import subprocess; subprocess.run(['pip', 'install', 'requests'])",
                "analysis_id": "aid-pip",
            }
        )
        assert result["ok"] is False
        assert result["error_code"] == "TOOL_SCHEMA_INVALID"
        assert result["reason"] == "pip_install_forbidden"
        assert client.exec_calls == []

    async def test_bare_script_path_rejected(self):
        """Regression: ``python3 -c suicide.py`` is wrong; use bash with python3 path."""
        for snippet in (
            "suicide.py",
            "    suicide.py",  # leading space → IndentationError in Python
            "/workspace/aid-1/suicide.py",
            "./tools/run.py",
        ):
            _make_session("aid-path-mistake")
            client = _FakeSandboxClient()
            tool = PythonExecTool(sandbox_client=client)
            result = await tool.ainvoke(
                {"code": snippet, "analysis_id": "aid-path-mistake"}
            )
            assert result["ok"] is False
            assert result["error_code"] == "TOOL_SCHEMA_INVALID"
            assert result["reason"] == "script_path_not_code"
            assert client.exec_calls == []
            _SESSION_REGISTRY.clear()

    async def test_python_dash_m_pip_install_also_rejected(self):
        _make_session("aid-pip2")
        client = _FakeSandboxClient()
        tool = PythonExecTool(sandbox_client=client)
        result = await tool.ainvoke(
            {
                "code": 'import os; os.system("python3 -m pip install foo")',
                "analysis_id": "aid-pip2",
            }
        )
        assert result["ok"] is False
        assert result["error_code"] == "TOOL_SCHEMA_INVALID"
        assert result["reason"] == "pip_install_forbidden"


# ---------------------------------------------------------------------------
# Timeout + session guards (shared contract with Bash)
# ---------------------------------------------------------------------------


class _BulkOutputClient(_FakeSandboxClient):
    """Fake client returning caller-controlled stdout/stderr sizes.

    Used to exercise the two-stage (sandbox-cap + LLM-view preview)
    truncation contract without depending on the code-sniffing branches
    in :class:`_FakeSandboxClient`.
    """

    def __init__(
        self,
        *,
        stdout: str = "",
        stderr: str = "",
        exit_code: int = 0,
    ) -> None:
        super().__init__()
        self._bulk_stdout = stdout
        self._bulk_stderr = stderr
        self._bulk_exit_code = exit_code

    async def exec(
        self,
        session: SandboxSession,
        cmd: str | list[str],
        *,
        timeout: float,
        user: str = "user",
        cwd: str | None = None,
    ) -> ExecResult:
        self.exec_calls.append(
            {"session": session, "cmd": cmd, "timeout": timeout, "cwd": cwd}
        )
        return ExecResult(
            stdout=self._bulk_stdout,
            stderr=self._bulk_stderr,
            exit_code=self._bulk_exit_code,
            duration_ms=9.0,
            timed_out=False,
        )


class TestTruncationAndPreview:
    """Symmetric contract with :class:`BashTool` — see bash tool tests."""

    async def test_stdout_truncated_triggers_head_tail_preview(self):
        _make_session("aid-py-big")
        huge = "O" * (DEFAULT_STREAM_LIMIT_BYTES + 5_000)
        tool = PythonExecTool(sandbox_client=_BulkOutputClient(stdout=huge))
        result = await tool.ainvoke(
            {"code": "print('x' * 80000)", "analysis_id": "aid-py-big"}
        )
        assert result["stdout_truncated"] is True
        assert result["stdout_preview_only"] is True
        stdout_bytes = len(result["stdout"].encode("utf-8"))
        preview_budget = DEFAULT_LLM_PREVIEW_HEAD_BYTES + DEFAULT_LLM_PREVIEW_TAIL_BYTES
        assert preview_budget <= stdout_bytes < DEFAULT_STREAM_LIMIT_BYTES

    async def test_short_output_not_truncated(self):
        _make_session("aid-py-short")
        tool = PythonExecTool(sandbox_client=_BulkOutputClient(stdout="ok"))
        result = await tool.ainvoke(
            {"code": "print('ok')", "analysis_id": "aid-py-short"}
        )
        assert result["stdout_truncated"] is False
        assert result["stdout_preview_only"] is False
        assert result["stdout"] == "ok"


class TestTimeoutAndGuards:
    async def test_timeout_forwarded_to_sandbox(self):
        _make_session("aid-to")
        client = _FakeSandboxClient()
        tool = PythonExecTool(sandbox_client=client)
        await tool.ainvoke(
            {
                "code": "import pefile; print('ok')",
                "analysis_id": "aid-to",
                "timeout_seconds": 7.5,
            }
        )
        assert client.exec_calls[0]["timeout"] == 7.5  # noqa: PLR2004

    async def test_missing_session_returns_schema_error(self):
        tool = PythonExecTool(sandbox_client=_FakeSandboxClient())
        result = await tool.ainvoke({"code": "print(1)", "analysis_id": "aid-missing"})
        assert result["ok"] is False
        assert result["error_code"] == "TOOL_SCHEMA_INVALID"
        assert result["reason"] == "sandbox_session_missing"

    async def test_backend_exec_exception_returns_tool_crash(
        self, _clean_registry_and_logdir
    ):
        log_dir: Path = _clean_registry_and_logdir
        aid = "aid-backend-error"
        _make_session(aid)
        tool = PythonExecTool(sandbox_client=_ExecFailingSandboxClient())

        with analysis_context(aid):
            result = await tool.ainvoke({"code": "print(1)", "analysis_id": aid})

        assert result["ok"] is False
        assert result["error_code"] == "TOOL_CRASH"
        assert result["reason"] == "sandbox_exec_exception"
        assert result["details"]["error_type"] == "RuntimeError"
        entries = _read_audit(aid, log_dir)
        assert entries[-1]["error_code"] == "TOOL_CRASH"


# ---------------------------------------------------------------------------
# C7-AC5: audit log
# ---------------------------------------------------------------------------


class TestAC5Audit:
    async def test_successful_call_writes_tool_call_event(
        self, _clean_registry_and_logdir
    ):
        log_dir: Path = _clean_registry_and_logdir
        aid = "aid-audit-py"
        _make_session(aid)
        tool = PythonExecTool(sandbox_client=_FakeSandboxClient())
        with analysis_context(aid):
            await tool.ainvoke({"code": "import pefile; print(1)", "analysis_id": aid})
        entries = _read_audit(aid, log_dir)
        assert len(entries) == 1
        assert entries[0]["event_type"] == "tool_call"
        assert entries[0]["tool_name"] == "python_exec"
        assert entries[0]["success"] is True
        assert entries[0]["args"]["code_bytes"] > 0
        assert "code" not in entries[0]["args"], "raw code must not leak into audit"

    async def test_network_blocked_call_logs_tool_crash(
        self, _clean_registry_and_logdir
    ):
        log_dir: Path = _clean_registry_and_logdir
        aid = "aid-audit-net"
        _make_session(aid)
        tool = PythonExecTool(sandbox_client=_FakeSandboxClient())
        with analysis_context(aid):
            await tool.ainvoke({"code": "import requests", "analysis_id": aid})
        entries = _read_audit(aid, log_dir)
        assert len(entries) == 1
        assert entries[0]["success"] is False
        assert entries[0]["error_code"] == "TOOL_CRASH"

    async def test_backend_exception_logs_tool_crash_and_returns_error(
        self, _clean_registry_and_logdir
    ):
        """Regression for terminals/39.txt: when the sandbox backend raises
        unexpectedly (e.g. an SDK bug or a ``TimeoutException`` that somehow
        escaped the backend), the tool must still emit an audit entry with
        ``error_code='TOOL_CRASH'`` and return a structured ToolMessage.
        """
        log_dir: Path = _clean_registry_and_logdir
        aid = "aid-audit-crash-py"
        _make_session(aid)

        class _ExplodingClient(_FakeSandboxClient):
            async def exec(self, *args: Any, **kwargs: Any) -> ExecResult:
                raise RuntimeError("sandbox vanished")

        tool = PythonExecTool(sandbox_client=_ExplodingClient())
        with analysis_context(aid):
            result = await tool.ainvoke({"code": "import pefile", "analysis_id": aid})

        assert result["ok"] is False
        assert result["error_code"] == "TOOL_CRASH"
        assert result["reason"] == "sandbox_exec_exception"

        entries = _read_audit(aid, log_dir)
        assert len(entries) == 1
        assert entries[0]["success"] is False
        assert entries[0]["error_code"] == "TOOL_CRASH"
        assert entries[0]["result"]["error_type"] == "RuntimeError"
