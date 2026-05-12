"""Sandbox client protocol + feature-flag factory (ADR-05 / ADR-16).

This module defines the stable schema that every sandbox backend must satisfy:

- :class:`SandboxSession` — an opaque per-analysis handle.
- :class:`ExecResult`     — the normalised result of a `commands.run` call.
- :class:`SandboxClient`  — the :class:`typing.Protocol` every backend implements.

The :func:`SandboxClient` protocol is implemented by
:class:`~sandbox.subprocess_backend.SubprocessBackend` and
:class:`~sandbox.e2b_backend.E2BBackend`.  Backend selection happens in
:mod:`sandbox.factory`; :func:`get_sandbox_client` is a convenience alias.


Path-validation is centralised here so both backends reject paths outside
``/workspace/<analysis_id>/`` uniformly (NFR-03 defence-in-depth).

The :func:`get_sandbox_client` facade delegates to
:func:`sandbox.factory.build_binary_sandbox_client` alongside the standalone
runner and LangGraph entrypoint.
"""

from __future__ import annotations

import posixpath
from dataclasses import dataclass, field
from pathlib import Path, PurePosixPath
from typing import Any, Literal, Protocol, runtime_checkable

SANDBOX_WORKSPACE_ROOT = "/workspace"


@dataclass
class SandboxSession:
    """Opaque handle for a per-analysis sandbox session (ADR-16).

    The ``workdir`` field carries the *logical* sandbox path
    ``/workspace/<analysis_id>/`` regardless of backend.  The subprocess
    fallback additionally maintains ``host_workdir`` — the physical host
    directory that the logical path is transparently remapped to.  Keeping
    the logical path stable lets us swap backends (C16 E2B) without changing
    any Tool-facing API.

    Attributes:
        analysis_id: UUID string identifying the analysis session.
        sandbox_id: Backend-assigned sandbox identifier (E2B VM ID for the
            remote backend; ``subprocess-<hex>`` for the fallback).
        backend: Literal tag identifying which backend produced the handle.
        workdir: Logical sandbox workspace path, always
            ``/workspace/<analysis_id>/``.
        created_at: Wall-clock epoch timestamp when the session was created.
        host_workdir: Host-side physical directory; set only for the
            subprocess backend.
        raw: Backend-specific opaque object (e.g. the ``AsyncSandbox``
            instance for the E2B backend).  Populated by C16.
    """

    analysis_id: str
    sandbox_id: str
    backend: Literal["subprocess", "e2b"]
    workdir: str
    created_at: float
    host_workdir: Path | None = None
    raw: Any = field(default=None, repr=False)


@dataclass
class ExecResult:
    """Normalised result of a sandbox command execution.

    The field set is intentionally minimal: every backend must be able to
    populate all five fields.  Callers that need backend-specific extras
    should read :class:`SandboxSession.raw` directly.

    Attributes:
        stdout: Captured standard output, decoded as UTF-8 (errors replaced).
        stderr: Captured standard error, decoded as UTF-8 (errors replaced).
        exit_code: Process exit code.  ``-1`` when the process was killed
            without producing an exit status (e.g. timeout).
        duration_ms: Wall-clock duration of the call in milliseconds.
        timed_out: ``True`` iff the call was killed by the timeout guard.
    """

    stdout: str
    stderr: str
    exit_code: int
    duration_ms: float
    timed_out: bool


@runtime_checkable
class SandboxClient(Protocol):
    """Protocol every sandbox backend must satisfy (ADR-05 / ADR-16).

    Both the C4 :class:`~sandbox.subprocess_backend.SubprocessBackend`
    and the C16 E2B backend implement this structural interface; Tools depend
    only on this Protocol so backend swaps are invisible to the Agent layer.
    """

    async def create(self, analysis_id: str) -> SandboxSession:
        """Provision a new sandbox and return an opaque session handle."""
        ...

    async def exec(
        self,
        session: SandboxSession,
        cmd: str | list[str],
        *,
        timeout: float,
        user: str = "user",
        cwd: str | None = None,
    ) -> ExecResult:
        """Execute ``cmd`` inside ``session`` and return the normalised result.

        Args:
            session: Session handle previously returned by :meth:`create`.
            cmd: Command as a list of argv tokens or a shell string
                (the string form is tokenised via :mod:`shlex`).
            timeout: Hard wall-clock timeout in seconds; the backend MUST
                kill the process and report ``timed_out=True`` when hit
                (IR-10).
            user: POSIX user under which the command runs inside the
                sandbox (ignored by the subprocess fallback).
            cwd: Optional sandbox-side working directory; must live under
                ``session.workdir``.
        """
        ...

    async def upload(self, session: SandboxSession, path: str, data: bytes) -> None:
        """Write ``data`` to ``path`` inside the sandbox workspace.

        The implementation MUST reject ``path`` values outside
        ``session.workdir``.
        """
        ...

    async def download(self, session: SandboxSession, path: str) -> bytes:
        """Read ``path`` from the sandbox workspace and return its bytes."""
        ...

    async def kill(self, session: SandboxSession) -> None:
        """Destroy the sandbox and release all associated resources.

        MUST be idempotent: repeated ``kill`` calls on the same session (or
        on a session that was never created) must not raise.
        """
        ...


def sandbox_workspace(analysis_id: str) -> str:
    """Return the canonical ``/workspace/<analysis_id>/`` path for an analysis.

    Args:
        analysis_id: UUID string identifying the analysis session.

    Returns:
        Logical workspace path with a trailing slash.
    """
    return f"{SANDBOX_WORKSPACE_ROOT}/{analysis_id}/"


def validate_sandbox_path(session: SandboxSession, path: str) -> PurePosixPath:
    """Reject any ``path`` that escapes ``session.workdir``.

    Uses :func:`posixpath.normpath` to collapse ``..`` / ``.`` segments
    before the prefix check, so attempts like
    ``/workspace/<aid>/../../etc/passwd`` are caught.

    Args:
        session: Session whose workspace is the allowed root.
        path: Candidate path, expected to be absolute and within
            ``session.workdir``.

    Returns:
        The normalised path as a :class:`PurePosixPath`.

    Raises:
        ValueError: If ``path`` is relative or escapes the workspace.
    """
    if not posixpath.isabs(path):
        msg = (
            f"Sandbox path must be absolute, got: {path!r}. "
            f"Only paths under {session.workdir!r} are allowed."
        )
        raise ValueError(msg)
    normalized = posixpath.normpath(path)
    root = session.workdir.rstrip("/")
    if normalized != root and not normalized.startswith(root + "/"):
        msg = (
            f"Path {path!r} is outside session workspace {session.workdir!r}; "
            f"only paths under /workspace/{session.analysis_id}/ are allowed."
        )
        raise ValueError(msg)
    return PurePosixPath(normalized)


async def upload_sample_to_sandbox(
    client: SandboxClient,
    session: SandboxSession,
    host_path: Path,
    *,
    filename: str = "sample.bin",
) -> str:
    """Upload the bytes of a host file to the sandbox workspace (ADR-10 / NFR-03).

    This is the *only* sanctioned path for sample bytes to cross the host ↔
    sandbox trust boundary described in DESIGN.md §3.1:

    - Bytes are read from ``host_path`` inside this function.
    - They are handed to :meth:`SandboxClient.upload` unchanged.
    - They are NEVER returned to the caller; only the destination sandbox
      path string is surfaced.

    Callers (notably :class:`~tools.file_identify.FileIdentifyTool`)
    therefore rely on this helper to guarantee FR-01 AC-7 zero-byte leakage
    at the Tool boundary.

    Args:
        client: Any backend implementing :class:`SandboxClient`.
        session: Active session whose workspace will receive the bytes.
        host_path: Absolute host path to read the sample bytes from.
        filename: Destination file name inside ``session.workdir``.
            Defaults to ``"sample.bin"`` per the DESIGN.md §3.1 convention.

    Returns:
        The absolute sandbox path where the bytes now live (e.g.
        ``"/workspace/<aid>/sample.bin"``).

    Raises:
        ValueError: If ``filename`` resolves outside ``session.workdir``
            (defence-in-depth, delegated to :func:`validate_sandbox_path`).
        FileNotFoundError: If ``host_path`` does not exist on the host.
    """
    dest = f"{session.workdir.rstrip('/')}/{filename}"
    validate_sandbox_path(session, dest)
    data = host_path.read_bytes()
    await client.upload(session, dest, data)
    return dest


def get_sandbox_client() -> SandboxClient:
    """Return the sandbox backend selected by the current configuration.

    Delegates to :func:`~sandbox.factory.build_binary_sandbox_client` — same
    selection as :mod:`~binary_analysis.api` and Deep Agent registry wiring.

    Returns:
        A concrete implementation of :class:`SandboxClient` (subprocess or E2B).

    Raises:
        SandboxUnavailable: If E2B is enabled but ``E2B_API_KEY`` is absent,
            propagated from :func:`config.settings` validation.

    pydantic.ValidationError:
        Raised on invalid numeric configuration parsed by settings.
    """
    from sandbox.factory import build_binary_sandbox_client  # noqa: PLC0415

    return build_binary_sandbox_client()
