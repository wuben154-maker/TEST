"""Unit tests for `SubprocessBackend` (C4-AC1/AC2/AC4, IR-10, ADR-16)."""

from __future__ import annotations

import sys

import pytest

from sandbox.client import (
    ExecResult,
    SandboxSession,
    get_sandbox_client,
    sandbox_workspace,
    validate_sandbox_path,
)
from sandbox.registry import _SESSION_REGISTRY
from sandbox.subprocess_backend import SubprocessBackend


@pytest.fixture(autouse=True)
def _clean_registry():
    _SESSION_REGISTRY.clear()
    yield
    _SESSION_REGISTRY.clear()


@pytest.fixture()
def backend() -> SubprocessBackend:
    return SubprocessBackend()


# ---------------------------------------------------------------------------
# C4-AC1: SandboxClient abstract interface
# ---------------------------------------------------------------------------


class TestProtocolConformance:
    def test_subprocess_backend_exposes_all_protocol_methods(self, backend):
        for name in ("create", "exec", "upload", "download", "kill"):
            assert callable(getattr(backend, name))

    def test_workspace_helper(self):
        assert sandbox_workspace("aid") == "/workspace/aid/"


class TestPathValidation:
    def _session(self):
        return SandboxSession(
            analysis_id="x",
            sandbox_id="s",
            backend="subprocess",
            workdir="/workspace/x/",
            created_at=0.0,
        )

    def test_validate_accepts_workspace_root(self):
        validate_sandbox_path(self._session(), "/workspace/x")

    def test_validate_accepts_subpath(self):
        validate_sandbox_path(self._session(), "/workspace/x/sample.bin")

    def test_validate_rejects_outside_path(self):
        with pytest.raises(ValueError):
            validate_sandbox_path(self._session(), "/etc/passwd")

    def test_validate_rejects_sibling_workspace(self):
        with pytest.raises(ValueError):
            validate_sandbox_path(self._session(), "/workspace/y/file")

    def test_validate_rejects_dotdot_escape(self):
        """Hardens against `/workspace/x/../../../etc/passwd` bypass."""
        with pytest.raises(ValueError):
            validate_sandbox_path(self._session(), "/workspace/x/../../etc/passwd")

    def test_validate_rejects_relative_path(self):
        with pytest.raises(ValueError):
            validate_sandbox_path(self._session(), "sample.bin")


# ---------------------------------------------------------------------------
# C4-AC2: subprocess fallback backend
# ---------------------------------------------------------------------------


class TestCreate:
    async def test_create_returns_well_formed_session(self, backend):
        session = await backend.create("aid-create")
        try:
            assert session.analysis_id == "aid-create"
            assert session.backend == "subprocess"
            assert session.workdir == "/workspace/aid-create/"
            assert session.sandbox_id.startswith("subprocess-")
            assert session.host_workdir is not None
            assert session.host_workdir.exists()
            assert session.host_workdir.is_dir()
        finally:
            await backend.kill(session)

    async def test_create_registers_session(self, backend):
        session = await backend.create("aid-reg")
        try:
            assert _SESSION_REGISTRY["aid-reg"] is session
        finally:
            await backend.kill(session)

    async def test_two_creates_produce_distinct_host_workdirs(self, backend):
        s1 = await backend.create("aid-a")
        s2 = await backend.create("aid-b")
        try:
            assert s1.host_workdir != s2.host_workdir
        finally:
            await backend.kill(s1)
            await backend.kill(s2)


class TestExec:
    async def test_exec_returns_exec_result(self, backend):
        session = await backend.create("aid-exec")
        try:
            result = await backend.exec(
                session,
                [sys.executable, "-c", "print('hello')"],
                timeout=10,
            )
            assert isinstance(result, ExecResult)
            assert result.exit_code == 0
            assert "hello" in result.stdout
            assert result.timed_out is False
        finally:
            await backend.kill(session)

    async def test_exec_captures_stderr(self, backend):
        session = await backend.create("aid-err")
        try:
            result = await backend.exec(
                session,
                [sys.executable, "-c", "import sys; sys.stderr.write('boom')"],
                timeout=10,
            )
            assert "boom" in result.stderr
        finally:
            await backend.kill(session)

    async def test_exec_timeout_kills_process(self, backend):
        """C4-AC2 / IR-10: timeout must kill the subprocess and flag `timed_out`."""
        session = await backend.create("aid-timeout")
        try:
            result = await backend.exec(
                session,
                [sys.executable, "-c", "import time; time.sleep(5)"],
                timeout=0.5,
            )
            assert result.timed_out is True
        finally:
            await backend.kill(session)

    async def test_exec_cwd_defaults_to_host_workdir(self, backend):
        session = await backend.create("aid-cwd")
        try:
            result = await backend.exec(
                session,
                [sys.executable, "-c", "import os; print(os.getcwd())"],
                timeout=10,
            )
            assert str(session.host_workdir) in result.stdout
        finally:
            await backend.kill(session)

    async def test_exec_nonzero_exit_propagates(self, backend):
        session = await backend.create("aid-nonzero")
        try:
            result = await backend.exec(
                session,
                [sys.executable, "-c", "import sys; sys.exit(7)"],
                timeout=10,
            )
            assert result.exit_code == 7
            assert result.timed_out is False
        finally:
            await backend.kill(session)


class TestUploadDownload:
    async def test_upload_then_download_roundtrip(self, backend):
        session = await backend.create("aid-io")
        try:
            payload = b"MZ\x90\x00sample-bytes"
            await backend.upload(session, "/workspace/aid-io/sample.bin", payload)
            data = await backend.download(session, "/workspace/aid-io/sample.bin")
            assert data == payload
        finally:
            await backend.kill(session)

    async def test_upload_creates_nested_dirs(self, backend):
        session = await backend.create("aid-nested")
        try:
            await backend.upload(
                session, "/workspace/aid-nested/ghidra/export.c", b"int main(){}"
            )
            assert (
                await backend.download(session, "/workspace/aid-nested/ghidra/export.c")
                == b"int main(){}"
            )
        finally:
            await backend.kill(session)

    async def test_upload_outside_workspace_raises(self, backend):
        """Hard path-validation: cannot write outside `/workspace/<aid>/`."""
        session = await backend.create("aid-oob")
        try:
            with pytest.raises(ValueError):
                await backend.upload(session, "/etc/passwd", b"x")
        finally:
            await backend.kill(session)

    async def test_upload_to_other_workspace_raises(self, backend):
        session = await backend.create("aid-a")
        try:
            with pytest.raises(ValueError):
                await backend.upload(session, "/workspace/aid-b/x", b"x")
        finally:
            await backend.kill(session)


class TestKill:
    async def test_kill_removes_session_from_registry(self, backend):
        session = await backend.create("aid-kill-reg")
        await backend.kill(session)
        assert "aid-kill-reg" not in _SESSION_REGISTRY

    async def test_kill_removes_host_workdir(self, backend):
        session = await backend.create("aid-kill-wd")
        host_workdir = session.host_workdir
        assert host_workdir is not None
        await backend.kill(session)
        assert not host_workdir.exists()

    async def test_kill_is_idempotent(self, backend):
        """C4-AC5: kill must not raise when called twice."""
        session = await backend.create("aid-idem")
        await backend.kill(session)
        await backend.kill(session)  # must not raise


# ---------------------------------------------------------------------------
# C4-AC4: Feature-flag factory
# ---------------------------------------------------------------------------


class TestFactory:
    def test_factory_returns_subprocess_backend_when_e2b_disabled(self, monkeypatch):
        from config import settings

        monkeypatch.setenv("BINARY_ANALYSIS_USE_E2B", "false")
        monkeypatch.delenv("E2B_API_KEY", raising=False)
        settings.cache_clear()
        try:
            client = get_sandbox_client()
            assert isinstance(client, SubprocessBackend)
        finally:
            settings.cache_clear()

    def test_factory_raises_sandbox_unavailable_when_e2b_enabled_without_key(
        self, monkeypatch
    ):
        from config import settings
        from errors import SandboxUnavailable

        monkeypatch.setenv("BINARY_ANALYSIS_USE_E2B", "true")
        monkeypatch.delenv("E2B_API_KEY", raising=False)
        settings.cache_clear()
        try:
            with pytest.raises(SandboxUnavailable):
                get_sandbox_client()
        finally:
            settings.cache_clear()

    def test_factory_returns_e2b_backend_when_e2b_enabled_with_key(
        self, monkeypatch
    ):
        from config import settings
        from sandbox.e2b_backend import E2BBackend

        monkeypatch.setenv("BINARY_ANALYSIS_USE_E2B", "true")
        monkeypatch.setenv("E2B_API_KEY", "dummy-key")
        settings.cache_clear()
        try:
            client = get_sandbox_client()
            assert isinstance(client, E2BBackend)
        finally:
            settings.cache_clear()

    def test_build_binary_sandbox_client_force_subprocess_overrides_settings(
        self, monkeypatch
    ):
        from config import settings
        from sandbox.factory import build_binary_sandbox_client

        monkeypatch.setenv("BINARY_ANALYSIS_USE_E2B", "true")
        monkeypatch.setenv("E2B_API_KEY", "dummy-key")
        settings.cache_clear()
        try:
            client = build_binary_sandbox_client(use_e2b=False)
            assert isinstance(client, SubprocessBackend)
        finally:
            settings.cache_clear()
