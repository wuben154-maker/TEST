"""Unit tests for :mod:`sandbox.e2b_backend`.

These tests mock the ``e2b.AsyncSandbox`` boundary so they run offline; the
live end-to-end checks live in ``tests/integration_tests/test_e2b_smoke.py``.

Scope: narrow regressions that surfaced in production log
``terminals/39.txt`` where a per-command timeout inside an E2B sandbox raised
:class:`e2b.exceptions.TimeoutException` and propagated all the way up to
the Pregel runner — violating the ADR-16 / IR-10 contract that
``ExecResult`` normalises every failure mode into a *value*, not a raise.
"""

from __future__ import annotations

import asyncio

import pytest

e2b = pytest.importorskip("e2b")

# Imports below the ``importorskip`` gate deliberately skip ruff E402; they
# must run only after we've confirmed the optional ``e2b`` SDK is installed
# so the file stays collectable on offline CI.
import config as _config  # noqa: E402
from errors import SandboxNetworkError  # noqa: E402
from sandbox.client import ExecResult, SandboxSession  # noqa: E402
from sandbox.e2b_backend import (  # noqa: E402
    _EXEC_TIMEOUT_GRACE_SECONDS,
    _SANDBOX_WORKSPACE_SETUP_ATTEMPTS,
    E2BBackend,
    _effective_grace_seconds,
    _ensure_analysis_workspace,
)


@pytest.fixture(autouse=True)
def _e2b_credentials(monkeypatch: pytest.MonkeyPatch) -> None:
    """Pretend credentials are present so ``E2BBackend()`` can construct.

    The tests never call out to the real control plane — they mock the
    ``AsyncSandbox`` at the ``commands.run`` seam — so a stub key suffices.
    """
    monkeypatch.setenv("E2B_API_KEY", "test-key-unused")
    _config.settings.cache_clear()
    yield
    _config.settings.cache_clear()


class _StubCommands:
    """Stub for ``AsyncSandbox.commands`` that raises a configured exception."""

    def __init__(self, exc: BaseException | None, *, delay: float = 0.0) -> None:
        self._exc = exc
        self._delay = delay
        self.run_calls: list[dict[str, object]] = []

    async def run(self, cmd: str, **kwargs: object) -> object:
        self.run_calls.append({"cmd": cmd, **kwargs})
        if self._delay:
            await asyncio.sleep(self._delay)
        if self._exc is not None:
            raise self._exc
        return _CommandResultStub(stdout="ok\n", stderr="", exit_code=0)


class _CommandResultStub:
    """Shape-compatible stand-in for ``e2b.CommandResult``."""

    def __init__(
        self, *, stdout: str, stderr: str, exit_code: int, error: str | None = None
    ) -> None:
        self.stdout = stdout
        self.stderr = stderr
        self.exit_code = exit_code
        self.error = error


class _StubAsyncSandbox:
    """Minimal stand-in for :class:`e2b.AsyncSandbox` exposing ``commands``."""

    def __init__(self, commands: _StubCommands) -> None:
        self.commands = commands
        self.sandbox_id = "stub-sandbox"


def _session_with_raw(raw: object) -> SandboxSession:
    return SandboxSession(
        analysis_id="aid-test",
        sandbox_id="stub-sandbox",
        backend="e2b",
        workdir="/workspace/aid-test/",
        created_at=0.0,
        raw=raw,
    )


# ---------------------------------------------------------------------------
# P0: TimeoutException from the SDK must be normalised to an ExecResult.
# ---------------------------------------------------------------------------


class TestTimeoutNormalisation:
    async def test_e2b_timeout_exception_normalises_to_exec_result(self):
        """Regression for terminals/39.txt: the SDK's TimeoutException was
        leaking past the backend and crashing the graph. It must become a
        structured ExecResult with ``timed_out=True, exit_code=-1``.
        """
        exc = e2b.exceptions.TimeoutException("context deadline exceeded")
        commands = _StubCommands(exc)
        session = _session_with_raw(_StubAsyncSandbox(commands))
        backend = E2BBackend()

        result = await backend.exec(session, ["echo", "hi"], timeout=5.0)

        assert isinstance(result, ExecResult)
        assert result.timed_out is True
        assert result.exit_code == -1
        assert "timeout" in result.stderr.lower()

    async def test_asyncio_timeout_still_normalises(self):
        """Pre-existing invariant: asyncio.TimeoutError from the outer
        ``wait_for`` also yields ``timed_out=True`` (belt-and-braces guard).
        """
        # Delay longer than (timeout + grace) so the outer wait_for fires.
        # timeout=0.1, grace=max(5, 0.025)=5 ⇒ total budget ~5.1s, too long to
        # wait for in a unit test. Instead, directly raise asyncio.TimeoutError
        # from the stub.
        commands = _StubCommands(TimeoutError("outer"))
        session = _session_with_raw(_StubAsyncSandbox(commands))
        backend = E2BBackend()

        result = await backend.exec(session, ["sleep", "999"], timeout=0.1)

        assert result.timed_out is True
        assert result.exit_code == -1


# ---------------------------------------------------------------------------
# P1a: grace is max(constant, 0.25 * timeout).
# ---------------------------------------------------------------------------


class TestGraceFormula:
    @pytest.mark.parametrize(
        ("timeout", "expected"),
        [
            (1.0, _EXEC_TIMEOUT_GRACE_SECONDS),  # 0.25 * 1 < 5 → floor wins
            (10.0, _EXEC_TIMEOUT_GRACE_SECONDS),  # 0.25 * 10 = 2.5 < 5
            (60.0, 15.0),  # 0.25 * 60 = 15
            (120.0, 30.0),  # 0.25 * 120 = 30
        ],
    )
    def test_effective_grace_scales_with_timeout(self, timeout: float, expected: float):
        assert _effective_grace_seconds(timeout) == expected


# ---------------------------------------------------------------------------
# Existing happy-path still works with the refactor.
# ---------------------------------------------------------------------------


class TestHappyPath:
    async def test_successful_run_returns_exec_result(self):
        commands = _StubCommands(None)
        session = _session_with_raw(_StubAsyncSandbox(commands))
        backend = E2BBackend()

        result = await backend.exec(session, ["echo", "hi"], timeout=5.0)

        assert result.exit_code == 0
        assert result.timed_out is False
        assert result.stdout == "ok\n"
        assert commands.run_calls[0]["cmd"] == "echo hi"
        assert commands.run_calls[0]["timeout"] == 5.0  # noqa: PLR2004


class _StubFilesMakeDir:
    def __init__(self) -> None:
        self.paths: list[str] = []

    async def make_dir(self, path: str, **kwargs: object) -> bool:
        self.paths.append(path)
        return True


class _StubAsyncSandboxWithFiles:
    """Stub exposing ``files.make_dir`` + ``commands`` like :class:`e2b.AsyncSandbox`."""

    def __init__(self, files: _StubFilesMakeDir, commands: _StubCommands) -> None:
        self.files = files
        self.commands = commands
        self.sandbox_id = "stub-sandbox"


class TestWorkspaceProvisioning:
    async def test_ensure_workspace_uses_make_dir_without_shell_when_possible(self):
        """Regression: avoid ``commands.run`` for mkdir when unary FS RPC works."""
        files = _StubFilesMakeDir()
        commands = _StubCommands(None)
        sandbox = _StubAsyncSandboxWithFiles(files, commands)
        await _ensure_analysis_workspace(sandbox, "/workspace/aid-test/")
        assert files.paths == ["/workspace/aid-test"]
        assert commands.run_calls == []

    async def test_ensure_workspace_falls_back_to_shell_when_make_dir_fails(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """When ``make_dir`` raises, ``commands.run`` must still provision."""

        class _FlakyFiles:
            async def make_dir(self, path: str, **kwargs: object) -> bool:
                raise RuntimeError("make_dir unsupported in stub")

        async def _no_sleep(_delay: float) -> None:
            return None

        monkeypatch.setattr(asyncio, "sleep", _no_sleep)
        commands = _StubCommands(None)
        sandbox = _StubAsyncSandboxWithFiles(_FlakyFiles(), commands)
        await _ensure_analysis_workspace(sandbox, "/workspace/aid-test/")
        assert len(commands.run_calls) == 1
        assert "mkdir -p" in commands.run_calls[0]["cmd"]
        assert "chown" in commands.run_calls[0]["cmd"]

    async def test_ensure_workspace_raises_network_error_after_transport_failures(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        httpcore = pytest.importorskip("httpcore")

        class _ConnectFiles:
            async def make_dir(self, path: str, **kwargs: object) -> bool:
                raise httpcore.ConnectError()

        async def _no_sleep(_delay: float) -> None:
            return None

        monkeypatch.setattr(asyncio, "sleep", _no_sleep)
        commands = _StubCommands(httpcore.ConnectError())
        sandbox = _StubAsyncSandboxWithFiles(_ConnectFiles(), commands)
        with pytest.raises(SandboxNetworkError, match="control plane"):
            await _ensure_analysis_workspace(sandbox, "/workspace/aid/")
        assert len(commands.run_calls) == _SANDBOX_WORKSPACE_SETUP_ATTEMPTS
