"""E2B remote-VM sandbox backend (ADR-05 / ADR-16 / ADR-17).

This module is the C16 implementation of the :class:`SandboxClient`
protocol frozen by C4.  It wraps :class:`e2b.AsyncSandbox` so the rest of
the system can be backend-agnostic:

- Tool code depends only on :class:`~sandbox.client.SandboxClient`.
- Swapping E2B ↔ subprocess fallback flips one environment variable
  (``BINARY_ANALYSIS_USE_E2B``) without touching any caller.

Security invariants (DESIGN.md §3.1 trust boundary):

- ``allow_internet_access=False`` on every sandbox we create → samples that
  attempt to beacon C2 are hard-blocked at the VM interface (NFR-03).
- ``secure=True`` to opt into E2B's stronger isolation profile.
- Every filesystem operation is funnelled through
  :func:`~sandbox.client.validate_sandbox_path` so even a
  buggy caller cannot escape ``/workspace/<analysis_id>/`` (defence-in-depth).
- The E2B SDK is imported lazily so the offline / subprocess-fallback path
  does not require ``pip install e2b``.

Failure handling (DESIGN.md §5.1):

- ``SandboxCreateTimeout`` / ``SandboxNetworkError`` / ``SandboxUnavailable``
  are mapped from E2B-SDK exceptions so upstream retry / fallback logic
  (ADR-16 §5) sees a stable error taxonomy.
- ``CommandResult`` with non-zero ``exit_code`` is returned as-is rather than
  raised — analysis tools routinely return non-zero for "nothing matched" and
  callers need to record an evidence gap, not an exception.
"""

from __future__ import annotations

import asyncio
import shlex
import time
from typing import TYPE_CHECKING, Any

from audit import current_analysis_id, log_sandbox_lifecycle
from config import settings
from errors import (
    SandboxCreateTimeout,
    SandboxNetworkError,
    SandboxUnavailable,
)
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

if TYPE_CHECKING:  # pragma: no cover — import for type checkers only.
    from e2b import AsyncSandbox


# Grace window added to per-command timeouts so the outer ``asyncio.wait_for``
# fires *after* the E2B-side timeout when both are configured — the SDK's own
# timeout gives a cleaner error class, so we prefer to let it win in normal
# operation and use ``wait_for`` only as a belt-and-braces guard.
#
# The effective grace is ``max(_EXEC_TIMEOUT_GRACE_SECONDS, 0.25 * timeout)``
# rather than a flat 5 s: on long-running commands (e.g. ``analyzeHeadless``
# bursts at ~120 s) the control-plane round-trip jitter alone can eat more
# than 5 s, causing the outer ``wait_for`` to fire *before* the SDK's own
# timeout — which in turn raised :class:`asyncio.TimeoutError` while the
# E2B server was still attempting to cancel the command, producing hard-to-
# debug phantom failures upstream (seen in terminals/39.txt).
_EXEC_TIMEOUT_GRACE_SECONDS = 5.0
_EXEC_TIMEOUT_GRACE_RATIO = 0.25


def _effective_grace_seconds(timeout: float) -> float:
    """Return the grace window to add on top of ``timeout`` for the outer guard.

    Scales with the command timeout so long-running commands still have
    sensible slack; floors at :data:`_EXEC_TIMEOUT_GRACE_SECONDS` so short
    commands keep a non-trivial margin.

    Args:
        timeout: Per-command wall-clock timeout in seconds (as passed to
            :meth:`E2BBackend.exec`).

    Returns:
        Grace in seconds; always ``>= _EXEC_TIMEOUT_GRACE_SECONDS``.
    """
    return max(_EXEC_TIMEOUT_GRACE_SECONDS, _EXEC_TIMEOUT_GRACE_RATIO * timeout)


_SANDBOX_WORKSPACE_SETUP_ATTEMPTS = 3
_SANDBOX_WORKSPACE_SETUP_BACKOFF_BASE = 0.75

_SANDBOX_ENVD_CONNECT_HINT = (
    "The control plane (api.<domain>) succeeded, but the per-sandbox VM "
    "endpoint (envd) did not accept a TLS connection. Allow outbound HTTPS "
    "to the sandbox host pattern (default `*.e2b.app` on port 443), set "
    "E2B_PROXY if you use a corporate HTTP proxy, and ensure TLS inspection "
    "does not replace the envd certificate chain."
)


def _is_sandbox_transport_error(exc: BaseException) -> bool:
    """Return True when ``exc`` is a low-level connect/TLS failure to envd."""
    try:
        import httpcore
    except ImportError:
        pass
    else:
        if isinstance(exc, httpcore.ConnectError):
            return True
    try:
        import httpx
    except ImportError:
        pass
    else:
        if isinstance(exc, httpx.ConnectError):
            return True
    cause = exc.__cause__
    if cause is not None and cause is not exc:
        return _is_sandbox_transport_error(cause)
    return False


async def _best_effort_kill_sandbox(sandbox: Any) -> None:
    """Destroy a sandbox without raising (cleanup after a failed ``create``)."""
    try:
        await sandbox.kill()
    except Exception:  # noqa: BLE001 — best-effort only
        pass


async def _ensure_analysis_workspace(sandbox: Any, workdir: str) -> None:
    """Create ``/workspace/<analysis_id>/`` inside a freshly provisioned VM.

    Prefer :meth:`e2b.AsyncSandbox.files.make_dir`, which issues a unary
    Connect-RPC over the shared httpcore pool.  ``commands.run`` uses a
    **server-streaming** RPC; on some networks the stream handshake fails with
    :class:`httpcore.ConnectError` during ``start_tls`` even though
    :meth:`e2b.AsyncSandbox.create` (plain HTTPS to ``api.*``) succeeds
    (seen in local dev logs).  We fall back to ``commands.run`` when
    ``make_dir`` is not enough, and retry both paths a few times on transport
    errors only.

    Args:
        sandbox: Live :class:`e2b.AsyncSandbox` instance.
        workdir: Canonical workspace path (trailing slash allowed).

    Raises:
        SandboxNetworkError: If only transport-level failures occur after
            retries.
        Exception: The last non-transport error from ``make_dir`` or
            ``commands.run`` (wrapped by :meth:`E2BBackend.create` when
            appropriate).
    """
    path = workdir.rstrip("/")
    mkdir_chown = (
        f"mkdir -p {shlex.quote(path)} && chown -R user:user {shlex.quote(path)}"
    )
    last_exc: BaseException | None = None

    for attempt in range(_SANDBOX_WORKSPACE_SETUP_ATTEMPTS):
        if attempt:
            await asyncio.sleep(
                _SANDBOX_WORKSPACE_SETUP_BACKOFF_BASE * (2 ** (attempt - 1))
            )
        try:
            await sandbox.files.make_dir(
                path,
                user="user",
                request_timeout=15.0,
            )
            return
        except Exception as exc_md:
            last_exc = exc_md
            try:
                await sandbox.commands.run(
                    mkdir_chown,
                    user="root",
                    timeout=15,
                )
                return
            except Exception as exc_sh:
                last_exc = exc_sh
                transport = _is_sandbox_transport_error(
                    exc_md
                ) or _is_sandbox_transport_error(exc_sh)
                if transport and attempt + 1 < _SANDBOX_WORKSPACE_SETUP_ATTEMPTS:
                    continue
                if transport:
                    raise SandboxNetworkError(_SANDBOX_ENVD_CONNECT_HINT) from exc_sh
                raise exc_sh from exc_md

    if last_exc is not None:
        raise SandboxNetworkError(_SANDBOX_ENVD_CONNECT_HINT) from last_exc


class E2BBackend:
    """E2B-backed implementation of :class:`SandboxClient` (ADR-05 / ADR-16).

    The backend is stateless with respect to sandboxes — each session owns
    its own :class:`e2b.AsyncSandbox` instance, kept in ``session.raw`` so
    later :meth:`exec` / :meth:`kill` calls can find it again without a
    separate map.  Session bookkeeping (by ``analysis_id``) is delegated to
    :mod:`sandbox.registry`.

    Args:
        template: Override for the E2B template id.  Defaults to the value of
            ``BINARY_ANALYSIS_E2B_TEMPLATE`` via :func:`settings`, which is
            ``"binary-analysis-ubuntu-2204"`` (ADR-17) unless a caller has
            set a different id.
        sandbox_lifetime_seconds: Override for the sandbox lifetime, in
            seconds.  Defaults to :attr:`Settings.sandbox_timeout_seconds`.
    """

    backend_name = "e2b"

    def __init__(
        self,
        *,
        template: str | None = None,
        sandbox_lifetime_seconds: int | None = None,
    ) -> None:
        cfg = settings()
        self._template = template if template is not None else cfg.e2b_template
        self._sandbox_lifetime_seconds = (
            sandbox_lifetime_seconds
            if sandbox_lifetime_seconds is not None
            else cfg.sandbox_timeout_seconds
        )

    async def create(self, analysis_id: str) -> SandboxSession:
        """Provision an E2B sandbox and register it for ``analysis_id``.

        Any exception raised by :meth:`e2b.AsyncSandbox.create` is mapped
        onto the stable :mod:`errors` taxonomy so the retry /
        fallback logic in ADR-16 can react uniformly.

        Args:
            analysis_id: UUID string identifying the analysis session.

        Returns:
            A :class:`SandboxSession` whose ``raw`` field carries the
            underlying :class:`e2b.AsyncSandbox` instance.

        Raises:
            SandboxCreateTimeout: If the ``AsyncSandbox.create`` call times
                out (typically a cold-start exceeding the budget).
            SandboxNetworkError: If the TLS connection to the E2B control
                plane or to the per-sandbox envd endpoint fails.
            SandboxUnavailable: For any other provisioning failure (missing
                API key, template not found, quota exhausted, …).
        """
        async_sandbox_cls = self._resolve_async_sandbox()

        start = time.perf_counter()
        try:
            sandbox = await async_sandbox_cls.create(
                template=self._template,
                timeout=self._sandbox_lifetime_seconds,
                allow_internet_access=False,
                secure=True,
            )
        except TimeoutError as exc:
            self._audit_failure("create", None, start, "SANDBOX_CREATE_TIMEOUT")
            msg = (
                f"AsyncSandbox.create timed out after "
                f"{self._sandbox_lifetime_seconds}s for template "
                f"{self._template!r}."
            )
            raise SandboxCreateTimeout(msg) from exc
        except ConnectionError as exc:
            self._audit_failure("create", None, start, "SANDBOX_NETWORK_ERROR")
            msg = (
                "Failed to reach the E2B control plane; "
                "check network connectivity and firewall rules."
            )
            raise SandboxNetworkError(msg) from exc
        except Exception as exc:  # noqa: BLE001 — last-ditch mapping layer
            self._audit_failure("create", None, start, "SANDBOX_UNAVAILABLE")
            msg = f"AsyncSandbox.create failed for template {self._template!r}: {exc!s}"
            raise SandboxUnavailable(msg) from exc
        duration_ms = (time.perf_counter() - start) * 1000.0

        sandbox_id = self._extract_sandbox_id(sandbox)
        workdir = sandbox_workspace(analysis_id)

        try:
            await _ensure_analysis_workspace(sandbox, workdir)
        except SandboxNetworkError:
            self._audit_failure("create", None, start, "SANDBOX_NETWORK_ERROR")
            await _best_effort_kill_sandbox(sandbox)
            raise
        except Exception as exc:
            self._audit_failure("create", None, start, "SANDBOX_UNAVAILABLE")
            await _best_effort_kill_sandbox(sandbox)
            msg = f"Failed to prepare E2B workspace {workdir!r}: {exc!s}"
            raise SandboxUnavailable(msg) from exc

        session = SandboxSession(
            analysis_id=analysis_id,
            sandbox_id=sandbox_id,
            backend="e2b",
            workdir=workdir,
            created_at=time.time(),
            host_workdir=None,
            raw=sandbox,
        )
        await register_session(session)
        self._audit(
            "create",
            session,
            duration_ms=duration_ms,
            kill_status=None,
        )
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
        """Execute ``cmd`` in the sandbox and return a normalised result.

        The implementation delegates to :meth:`e2b.Commands.run` with a
        matching timeout.  An outer :func:`asyncio.wait_for` guards against
        the SDK misbehaving; either mechanism firing is normalised to
        ``timed_out=True`` with ``exit_code=-1``.

        Non-zero exit codes are returned, not raised — the E2B SDK normally
        raises :class:`CommandExitException` for non-zero exits, which we
        intercept and convert to a structured :class:`ExecResult`.

        Args:
            session: Session previously returned by :meth:`create`.
            cmd: argv list or shell string.  Lists are passed through
                :func:`shlex.join` to produce a shell-safe command line
                because :meth:`e2b.Commands.run` takes a string.
            timeout: Hard wall-clock timeout in seconds.
            user: POSIX user to run under inside the sandbox.
            cwd: Optional sandbox-side working directory; must live under
                ``session.workdir``.

        Returns:
            An :class:`ExecResult` with captured stdout/stderr, exit code,
            duration, and timeout flag.
        """
        sandbox = self._require_sandbox(session)
        cmd_str = cmd if isinstance(cmd, str) else shlex.join(cmd)
        effective_cwd = self._effective_cwd(session, cwd)

        # Normalise the timeout: E2B takes a float, asyncio.wait_for takes
        # an optional float.  We always pass both, using a small grace so
        # the SDK's own timeout wins in a race.
        # Lazy import so the e2b SDK remains an optional dependency; users
        # on `BINARY_ANALYSIS_USE_E2B=false` never need to install the group.
        from e2b import CommandExitException  # noqa: PLC0415
        from e2b.exceptions import (
            TimeoutException as _E2BTimeoutException,  # noqa: PLC0415
        )

        start = time.perf_counter()
        timed_out = False
        nonzero_exit: CommandExitException | None = None
        try:
            result = await asyncio.wait_for(
                sandbox.commands.run(
                    cmd_str,
                    user=user,
                    cwd=effective_cwd,
                    timeout=timeout,
                ),
                timeout=timeout + _effective_grace_seconds(timeout),
            )
        except (TimeoutError, _E2BTimeoutException):
            # Unify the SDK's own ``TimeoutException`` with ``asyncio.TimeoutError``
            # from the outer ``wait_for``. Both mean "command exceeded its
            # wall-clock budget"; IR-10 / ADR-16 require callers to see this
            # as a value (``timed_out=True, exit_code=-1``) rather than a
            # raise — a raise escaped the backend historically and crashed
            # the Pregel runner mid-graph (seen in terminals/39.txt).
            timed_out = True
            result = None
        except CommandExitException as exc:
            # E2B's `commands.run` raises on non-zero exit rather than
            # returning a result with a non-zero ``exit_code``. Capture the
            # exception and normalise it to a structured ExecResult so
            # callers observe the same contract as the subprocess backend
            # (IR-10 / ADR-16): ``exit_code != 0`` is a value, not a raise.
            nonzero_exit = exc
            result = None
        else:
            timed_out = self._is_timeout_result(result)
        duration_ms = (time.perf_counter() - start) * 1000.0

        if nonzero_exit is not None:
            return ExecResult(
                stdout=nonzero_exit.stdout or "",
                stderr=nonzero_exit.stderr or "",
                exit_code=nonzero_exit.exit_code,
                duration_ms=duration_ms,
                timed_out=False,
            )

        if result is None:
            return ExecResult(
                stdout="",
                stderr=f"Command exceeded wall-clock timeout of {timeout}s.",
                exit_code=-1,
                duration_ms=duration_ms,
                timed_out=True,
            )

        stdout, stderr, exit_code = self._extract_result(result)
        if timed_out and exit_code == 0:
            exit_code = -1
        return ExecResult(
            stdout=stdout,
            stderr=stderr,
            exit_code=exit_code,
            duration_ms=duration_ms,
            timed_out=timed_out,
        )

    async def upload(self, session: SandboxSession, path: str, data: bytes) -> None:
        """Write ``data`` to ``path`` inside the sandbox workspace.

        The path is validated *before* the write is scheduled so escape
        attempts never hit the SDK layer.

        Args:
            session: Active session (must have been created by this backend).
            path: Absolute sandbox path under ``session.workdir``.
            data: Bytes to write — typically sample bytes routed via
                :func:`~sandbox.client.upload_sample_to_sandbox`.

        Raises:
            ValueError: If ``path`` escapes ``session.workdir``.
        """
        validate_sandbox_path(session, path)
        sandbox = self._require_sandbox(session)
        await sandbox.files.write(path, data)

    async def download(self, session: SandboxSession, path: str) -> bytes:
        """Read ``path`` from the sandbox workspace and return its bytes.

        Args:
            session: Active session (must have been created by this backend).
            path: Absolute sandbox path under ``session.workdir``.

        Returns:
            The file contents as ``bytes``.

        Raises:
            ValueError: If ``path`` escapes ``session.workdir``.
        """
        validate_sandbox_path(session, path)
        sandbox = self._require_sandbox(session)
        content = await sandbox.files.read(path, format="bytes", user="user")
        # The SDK returns ``bytearray`` on some versions; normalise.
        return bytes(content)

    async def kill(self, session: SandboxSession) -> None:
        """Idempotently destroy the sandbox and unregister the session.

        The method is safe to call multiple times: each call tries to unwire
        the session from the registry, invoke ``AsyncSandbox.kill`` at most
        once, and swallow errors so the caller can treat kill as a "best
        effort" cleanup.
        """
        start = time.perf_counter()
        await unregister_session(session.analysis_id)
        sandbox = session.raw
        session.raw = None  # ensure subsequent calls are true no-ops
        kill_status = "ok"
        if sandbox is not None:
            try:
                await sandbox.kill()
            except Exception as exc:  # noqa: BLE001 — log and move on
                kill_status = f"error:{type(exc).__name__}"
        duration_ms = (time.perf_counter() - start) * 1000.0
        self._audit(
            "kill",
            session,
            duration_ms=duration_ms,
            kill_status=kill_status,
        )

    # ------------------------------------------------------------------
    # Internals
    # ------------------------------------------------------------------

    @staticmethod
    def _resolve_async_sandbox() -> type[AsyncSandbox]:
        """Lazy-import :class:`e2b.AsyncSandbox` with a friendly error.

        Raises:
            SandboxUnavailable: If the ``e2b`` package is not installed.
        """
        try:
            from e2b import AsyncSandbox  # noqa: PLC0415
        except ImportError as exc:  # pragma: no cover — environment-dependent
            msg = (
                "The 'e2b' package is required for the E2B backend. "
                "Install it with `pip install e2b` or set "
                "BINARY_ANALYSIS_USE_E2B=false to use the subprocess fallback."
            )
            raise SandboxUnavailable(msg) from exc
        return AsyncSandbox

    @staticmethod
    def _extract_sandbox_id(sandbox: Any) -> str:
        """Best-effort extraction of the sandbox id across SDK versions.

        The SDK has exposed the id under several attribute names (``sandbox_id``,
        ``id``, ``sandboxID``) depending on the release; we try them in turn and
        fall back to ``repr(sandbox)`` so the audit log always has a stable
        correlator, even if the SDK changes shape.
        """
        for attr in ("sandbox_id", "id", "sandboxID"):
            value = getattr(sandbox, attr, None)
            if isinstance(value, str) and value:
                return value
        return f"e2b-{id(sandbox):x}"

    @staticmethod
    def _require_sandbox(session: SandboxSession) -> Any:
        """Return the live :class:`e2b.AsyncSandbox` for ``session``.

        Raises:
            RuntimeError: If the session was not produced by this backend or
                has already been killed.
        """
        if session.backend != "e2b":
            msg = (
                f"E2BBackend received a session with backend="
                f"{session.backend!r}; refusing to operate on a foreign handle."
            )
            raise RuntimeError(msg)
        if session.raw is None:
            msg = (
                "E2B sandbox handle is missing; the session was either never "
                "created by this backend or has already been killed."
            )
            raise RuntimeError(msg)
        return session.raw

    def _effective_cwd(self, session: SandboxSession, cwd: str | None) -> str:
        """Return the validated cwd for :meth:`exec`, defaulting to ``session.workdir``."""
        if cwd is None:
            return session.workdir.rstrip("/")
        validate_sandbox_path(session, cwd)
        return cwd

    @staticmethod
    def _extract_result(result: Any) -> tuple[str, str, int]:
        """Pull (stdout, stderr, exit_code) out of an E2B ``CommandResult``.

        Tolerates the small attribute-name drift between SDK versions so the
        backend does not pin a single SDK minor release.
        """
        stdout = getattr(result, "stdout", "") or ""
        stderr = getattr(result, "stderr", "") or ""
        exit_code = getattr(result, "exit_code", None)
        if exit_code is None:
            exit_code = getattr(result, "exitCode", -1)
        return str(stdout), str(stderr), int(exit_code)

    @staticmethod
    def _is_timeout_result(result: Any) -> bool:
        """Return ``True`` when the SDK result signals a command-level timeout.

        Current SDK versions populate ``error`` with the string ``"timeout"``
        when the command hit its own timeout (as opposed to exiting naturally);
        we also fall back to probing the exception type for robustness.
        """
        error = getattr(result, "error", None)
        if isinstance(error, str) and "timeout" in error.lower():
            return True
        return False

    def _audit(
        self,
        event: str,
        session: SandboxSession,
        *,
        duration_ms: float | None,
        kill_status: str | None,
    ) -> None:
        """Emit a sandbox-lifecycle audit entry when an analysis context is bound."""
        if not current_analysis_id():
            return
        log_sandbox_lifecycle(
            event=event,
            sandbox_id=session.sandbox_id,
            template=self._template,
            duration_ms=duration_ms,
            fallback_used=False,
            kill_status=kill_status,
        )

    def _audit_failure(
        self,
        event: str,
        session: SandboxSession | None,
        start: float,
        error_code: str,
    ) -> None:
        """Record a failed lifecycle event in the audit log (NFR-06)."""
        if not current_analysis_id():
            return
        duration_ms = (time.perf_counter() - start) * 1000.0
        log_sandbox_lifecycle(
            event=event,
            sandbox_id=session.sandbox_id if session is not None else None,
            template=self._template,
            duration_ms=duration_ms,
            fallback_used=False,
            kill_status=None,
            error_code=error_code,
        )
