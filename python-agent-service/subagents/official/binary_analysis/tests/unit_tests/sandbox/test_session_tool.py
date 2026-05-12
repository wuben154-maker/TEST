"""Unit tests for `SandboxSessionTool` (C4-AC5)."""

from __future__ import annotations

from typing import Any

import pytest

from errors import SandboxUnavailable
from sandbox.client import ExecResult, SandboxSession, sandbox_workspace
from sandbox.registry import _SESSION_REGISTRY
from sandbox.session_tool import SandboxSessionInput, SandboxSessionTool
from sandbox.subprocess_backend import SubprocessBackend


@pytest.fixture(autouse=True)
def _clean_registry():
    _SESSION_REGISTRY.clear()
    yield
    _SESSION_REGISTRY.clear()


@pytest.fixture()
def tool() -> SandboxSessionTool:
    return SandboxSessionTool(client=SubprocessBackend())


class _CreateFailingClient:
    async def create(self, analysis_id: str) -> SandboxSession:
        raise SandboxUnavailable(
            "sandbox template unavailable",
            details={"reason": "template_missing", "analysis_id": analysis_id},
        )

    async def exec(
        self,
        session: SandboxSession,
        cmd: str | list[str],
        *,
        timeout: float,
        user: str = "user",
        cwd: str | None = None,
    ) -> ExecResult:  # pragma: no cover
        raise NotImplementedError

    async def upload(self, *args: Any, **kwargs: Any) -> None:  # pragma: no cover
        raise NotImplementedError

    async def download(self, *args: Any, **kwargs: Any) -> bytes:  # pragma: no cover
        raise NotImplementedError

    async def kill(self, session: SandboxSession) -> None:  # pragma: no cover
        _SESSION_REGISTRY.pop(session.analysis_id, None)


class _KillFailingClient(_CreateFailingClient):
    async def create(self, analysis_id: str) -> SandboxSession:
        session = SandboxSession(
            analysis_id=analysis_id,
            sandbox_id=f"fake-{analysis_id}",
            backend="subprocess",
            workdir=sandbox_workspace(analysis_id),
            created_at=0.0,
        )
        _SESSION_REGISTRY[analysis_id] = session
        return session

    async def kill(self, session: SandboxSession) -> None:
        raise RuntimeError("backend kill failed")


class TestSchema:
    def test_tool_name(self, tool):
        assert tool.name == "sandbox_session"

    def test_args_schema_is_sandbox_session_input(self, tool):
        assert tool.args_schema is SandboxSessionInput

    def test_schema_requires_action(self):
        with pytest.raises(Exception):
            SandboxSessionInput(analysis_id="x")  # type: ignore[call-arg]

    def test_schema_requires_analysis_id(self):
        with pytest.raises(Exception):
            SandboxSessionInput(action="create")  # type: ignore[call-arg]

    def test_schema_rejects_unknown_action(self):
        with pytest.raises(Exception):
            SandboxSessionInput(action="frobnicate", analysis_id="x")  # type: ignore[arg-type]


class TestCreateAction:
    async def test_create_returns_session_handle(self, tool):
        result = await tool.ainvoke({"action": "create", "analysis_id": "aid-create"})
        try:
            assert result["ok"] is True
            assert result["analysis_id"] == "aid-create"
            assert result["backend"] == "subprocess"
            assert result["workdir"] == "/workspace/aid-create/"
            assert result["sandbox_id"].startswith("subprocess-")
        finally:
            await tool.ainvoke({"action": "kill", "analysis_id": "aid-create"})

    async def test_create_failure_returns_structured_error(self):
        tool = SandboxSessionTool(client=_CreateFailingClient())

        result = await tool.ainvoke({"action": "create", "analysis_id": "aid-create"})

        assert result["ok"] is False
        assert result["error_code"] == "SANDBOX_UNAVAILABLE"
        assert result["reason"] == "template_missing"
        assert result["details"]["error_type"] == "SandboxUnavailable"

    async def test_create_registers_in_registry(self, tool):
        await tool.ainvoke({"action": "create", "analysis_id": "aid-reg"})
        try:
            assert "aid-reg" in _SESSION_REGISTRY
        finally:
            await tool.ainvoke({"action": "kill", "analysis_id": "aid-reg"})


class TestInfoAction:
    async def test_info_before_create_returns_none(self, tool):
        result = await tool.ainvoke({"action": "info", "analysis_id": "missing"})
        assert result == {"ok": True, "session": None}

    async def test_info_after_create_returns_handle(self, tool):
        await tool.ainvoke({"action": "create", "analysis_id": "aid-info"})
        try:
            result = await tool.ainvoke({"action": "info", "analysis_id": "aid-info"})
            assert result["analysis_id"] == "aid-info"
            assert result["backend"] == "subprocess"
        finally:
            await tool.ainvoke({"action": "kill", "analysis_id": "aid-info"})


class TestKillAction:
    async def test_kill_after_create(self, tool):
        await tool.ainvoke({"action": "create", "analysis_id": "aid-k"})
        result = await tool.ainvoke({"action": "kill", "analysis_id": "aid-k"})
        assert result == {"ok": True, "killed": True, "analysis_id": "aid-k"}
        assert "aid-k" not in _SESSION_REGISTRY

    async def test_kill_unknown_is_idempotent(self, tool):
        """C4-AC5: kill on a never-created session must succeed with killed=False."""
        result = await tool.ainvoke({"action": "kill", "analysis_id": "never-created"})
        assert result == {
            "ok": True,
            "killed": False,
            "analysis_id": "never-created",
        }

    async def test_kill_failure_returns_structured_error(self):
        client = _KillFailingClient()
        session = await client.create("aid-kill")
        tool = SandboxSessionTool(client=client)

        result = await tool.ainvoke(
            {"action": "kill", "analysis_id": session.analysis_id}
        )

        assert result["ok"] is False
        assert result["error_code"] == "TOOL_CRASH"
        assert result["reason"] == "sandbox_kill_failed"
        assert result["details"]["error_type"] == "RuntimeError"

    async def test_kill_twice_is_idempotent(self, tool):
        await tool.ainvoke({"action": "create", "analysis_id": "aid-twice"})
        first = await tool.ainvoke({"action": "kill", "analysis_id": "aid-twice"})
        second = await tool.ainvoke({"action": "kill", "analysis_id": "aid-twice"})
        assert first["killed"] is True
        assert second["killed"] is False
