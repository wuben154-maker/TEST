"""Subprocess-based sandbox fallback (ADR-16, offline / CI / air-gapped).

When ``BINARY_ANALYSIS_USE_E2B=false`` the system uses this backend in place
of the remote E2B VM.  The contract is identical to the C16 E2B backend:

- Each analysis gets its own isolated working directory.
- The logical workspace path ``/workspace/<analysis_id>/`` is preserved so
  Tools and prompts remain backend-agnostic.
- All ``exec`` calls enforce a hard wall-clock timeout (IR-10).
- ``kill`` is idempotent and cleans up the host-side tmpdir.

**Security caveat:** this backend only provides process-level isolation and
a path-validation layer — it is NOT a VM boundary.  The Agent must still
respect NFR-04 (zero execution of sample bytes) at the orchestration layer.
"""

from __future__ import annotations

import asyncio
import shlex
import shutil
import tempfile
import time
import uuid
from pathlib import Path

from audit import current_analysis_id, log_sandbox_lifecycle
from sandbox.client import (
    ExecResult,
    SandboxSession,
    sandbox_workspace,
    validate_sandbox_path,
)
from sandbox.registry import (
    register_session,
    unregister_session,
)


class SubprocessBackend:
    """Host-local subprocess backend implementing :class:`SandboxClient`.

    Each session gets a dedicated ``tempfile.mkdtemp`` directory on the host;
    logical ``/workspace/<analysis_id>/`` paths are transparently remapped
    to that host directory by :meth:`_resolve`.
    """

    backend_name = "subprocess"

    async def create(self, analysis_id: str) -> SandboxSession:
        """Create a host tmpdir and register a new session.

        Args:
            analysis_id: UUID string identifying the analysis.

        Returns:
            A fresh :class:`SandboxSession` registered in the module-level
            registry.
        """
        host_workdir = Path(
            tempfile.mkdtemp(prefix=f"deepagent-analyze-{analysis_id}-")
        )
        session = SandboxSession(
            analysis_id=analysis_id,
            sandbox_id=f"subprocess-{uuid.uuid4().hex[:12]}",
            backend="subprocess",
            workdir=sandbox_workspace(analysis_id),
            created_at=time.time(),
            host_workdir=host_workdir,
        )
        await register_session(session)
        self._audit("create", session, duration_ms=None, kill_status=None)
        return session

    async def exec(
        self,
        session: SandboxSession,
        cmd: str | list[str],
        *,
        timeout: float,
        user: str = "user",
        cwd: str | None = None,
    ) -> ExecResult:
        """Run ``cmd`` under ``session.host_workdir`` with a wall-clock timeout.

        Args:
            session: Session previously returned by :meth:`create`.
            cmd: argv list or shell string (tokenised via :mod:`shlex`).
            timeout: Hard wall-clock timeout in seconds.  On hit the process
                is killed and ``timed_out=True`` is returned (IR-10).
            user: Ignored by the subprocess backend (kept for interface
                parity with the E2B backend).
            cwd: Optional sandbox-side working directory; must be under
                ``session.workdir``.

        Returns:
            :class:`ExecResult` with captured stdout/stderr, exit code,
            duration, and timeout flag.
        """
        del user  # subprocess backend does not drop privileges
        if session.host_workdir is None:
            msg = "SubprocessBackend session is missing host_workdir; was it created by this backend?"
            raise RuntimeError(msg)

        argv = shlex.split(cmd) if isinstance(cmd, str) else list(cmd)
        effective_cwd = self._effective_cwd(session, cwd)

        start = time.perf_counter()
        try:
            proc = await asyncio.create_subprocess_exec(
                *argv,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                cwd=str(effective_cwd),
            )
        except (FileNotFoundError, NotADirectoryError, PermissionError) as exc:
            # The subprocess backend targets developer workstations where the
            # agent routinely calls Linux-first CLIs (`sha256sum`, `file`,
            # `yara`, ...). On hosts without these binaries (notably Windows)
            # `create_subprocess_exec` raises rather than returning a non-zero
            # exit code, which crashes the LangGraph tool-call boundary.
            # Soft-fail to a normal `ExecResult` so the agent sees a
            # structured tool error and can fall back to an alternative
            # skill or degrade the corresponding fact bucket to SKIPPED.
            return ExecResult(
                stdout="",
                stderr=f"{type(exc).__name__}: {exc}",
                exit_code=127,
                duration_ms=(time.perf_counter() - start) * 1000.0,
                timed_out=False,
            )
        timed_out = False
        try:
            stdout_b, stderr_b = await asyncio.wait_for(
                proc.communicate(), timeout=timeout
            )
        except TimeoutError:
            timed_out = True
            proc.kill()
            try:
                stdout_b, stderr_b = await proc.communicate()
            except (ProcessLookupError, OSError):
                stdout_b, stderr_b = b"", b""
        duration_ms = (time.perf_counter() - start) * 1000.0

        return ExecResult(
            stdout=stdout_b.decode("utf-8", errors="replace") if stdout_b else "",
            stderr=stderr_b.decode("utf-8", errors="replace") if stderr_b else "",
            exit_code=proc.returncode if proc.returncode is not None else -1,
            duration_ms=duration_ms,
            timed_out=timed_out,
        )

    async def upload(self, session: SandboxSession, path: str, data: bytes) -> None:
        """Write ``data`` to ``path`` inside the (virtual) sandbox workspace.

        The logical ``path`` is validated against ``session.workdir`` and
        then remapped to the host tmpdir before writing.
        """
        dest = self._resolve(session, path)
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_bytes(data)

    async def download(self, session: SandboxSession, path: str) -> bytes:
        """Read ``path`` from the (virtual) sandbox workspace and return its bytes."""
        src = self._resolve(session, path)
        return src.read_bytes()

    async def kill(self, session: SandboxSession) -> None:
        """Idempotently destroy ``session`` and remove its host tmpdir."""
        start = time.perf_counter()
        await unregister_session(session.analysis_id)
        if session.host_workdir is not None and session.host_workdir.exists():
            shutil.rmtree(session.host_workdir, ignore_errors=True)
        duration_ms = (time.perf_counter() - start) * 1000.0
        self._audit("kill", session, duration_ms=duration_ms, kill_status="ok")

    # ------------------------------------------------------------------
    # Internals
    # ------------------------------------------------------------------

    def _resolve(self, session: SandboxSession, path: str) -> Path:
        """Translate a logical ``/workspace/<aid>/...`` path to a host path.

        Raises:
            ValueError: If ``path`` is outside the session workspace.
            RuntimeError: If ``session`` has no ``host_workdir`` (wrong backend).
        """
        if session.host_workdir is None:
            msg = "SubprocessBackend session is missing host_workdir."
            raise RuntimeError(msg)
        pp = validate_sandbox_path(session, path)
        root = session.workdir.rstrip("/")
        relative = pp.relative_to(root)
        return session.host_workdir / str(relative)

    def _effective_cwd(self, session: SandboxSession, cwd: str | None) -> Path:
        assert session.host_workdir is not None  # noqa: S101
        if cwd is None:
            return session.host_workdir
        return self._resolve(session, cwd)

    def _audit(
        self,
        event: str,
        session: SandboxSession,
        *,
        duration_ms: float | None,
        kill_status: str | None,
    ) -> None:
        """Emit a sandbox-lifecycle audit entry when an analysis context is active.

        Skips the write when no ``analysis_id`` is bound to the current
        context (typically in unit tests) to avoid polluting the default
        ``logs/.audit.jsonl`` file.
        """
        if not current_analysis_id():
            return
        log_sandbox_lifecycle(
            event=event,
            sandbox_id=session.sandbox_id,
            template=None,
            duration_ms=duration_ms,
            fallback_used=True,
            kill_status=kill_status,
        )
