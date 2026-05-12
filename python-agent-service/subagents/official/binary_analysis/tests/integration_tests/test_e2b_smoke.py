"""End-to-end smoke tests for the C16 E2B sandbox backend (ADR-05 / ADR-16).

These tests require a live ``E2B_API_KEY`` and the E2B SDK; they are skipped
automatically when either is absent so they can coexist with the offline unit
test suite.

Scope (C16-AC3):

- ``E2BBackend.create`` provisions a sandbox with
  ``allow_internet_access=False`` and the ADR-17 template.
- The resulting session satisfies the stable :class:`SandboxClient` protocol
  (same contract as :class:`SubprocessBackend` from C4).
- :meth:`upload` / :meth:`download` round-trip bytes inside
  ``/workspace/<analysis_id>/`` without ever touching the host filesystem.
- :meth:`exec` executes a trivial tool (``sha256sum``) and returns a normalised
  :class:`ExecResult`.
- :meth:`kill` is idempotent.
- Path-validation rejects escapes outside the per-analysis workspace.
"""

from __future__ import annotations

import hashlib
import os
import uuid
from typing import TYPE_CHECKING

import pytest

if TYPE_CHECKING:
    from sandbox.client import SandboxClient, SandboxSession

pytestmark = pytest.mark.integration


def _load_env() -> None:
    """Populate ``E2B_API_KEY`` from a local ``.env`` when python-dotenv is available.

    Mirrors the convention used by ``sandbox_browser`` so developers can keep
    credentials in a file rather than exporting them each shell invocation.
    """
    try:
        from dotenv import load_dotenv  # noqa: PLC0415
    except ImportError:
        return
    from pathlib import Path  # noqa: PLC0415

    repo_root = Path(__file__).resolve().parents[2]
    load_dotenv(dotenv_path=repo_root / ".env", override=False)


_load_env()
E2B_API_KEY_MISSING = not os.environ.get("E2B_API_KEY")

try:  # pragma: no cover - environment-dependent
    import e2b as _e2b_module  # noqa: F401

    _E2B_SDK_MISSING = False
except ImportError:  # pragma: no cover - environment-dependent
    _E2B_SDK_MISSING = True

SKIP_INTEGRATION = E2B_API_KEY_MISSING or _E2B_SDK_MISSING
if _E2B_SDK_MISSING:
    E2B_SKIP_REASON = (
        "the 'e2b' SDK is not installed in this environment; "
        "install it with `pip install e2b` to enable the C16 smoke tests."
    )
else:
    E2B_SKIP_REASON = (
        "E2B_API_KEY is not set; skipping the C16 smoke test per ADR-16 "
        "(the subprocess fallback branch is covered by the C4 unit tests)."
    )


# Minimal valid MZ/PE header (DOS stub + PE signature) - 68 bytes is plenty
# for `sha256sum` to succeed and for downstream file-type detection tests.
_MINIMAL_PE_BYTES = (
    b"MZ"
    + b"\x00" * 58
    + b"\x40\x00\x00\x00"  # e_lfanew = 0x40
    + b"PE\x00\x00"
)


async def _create_or_skip(backend: SandboxClient, analysis_id: str) -> SandboxSession:
    """Attempt ``backend.create``, skipping the test when the env is unready.

    Per AC-3 the test is a ``skipif`` rather than a hard failure when the
    deployment environment is incomplete (no API key, template not yet
    published, quota exhausted, ...).  This helper centralises that policy.
    """
    from errors import (  # noqa: PLC0415
        SandboxCreateTimeout,
        SandboxNetworkError,
        SandboxUnavailable,
    )

    try:
        return await backend.create(analysis_id)
    except (SandboxUnavailable, SandboxCreateTimeout, SandboxNetworkError) as exc:
        pytest.skip(
            f"E2B sandbox provisioning unavailable ({type(exc).__name__}: "
            f"{exc.message}); build the ADR-17 template and retry."
        )


@pytest.mark.skipif(SKIP_INTEGRATION, reason=E2B_SKIP_REASON)
async def test_e2b_backend_round_trip_smoke() -> None:
    """Full lifecycle smoke: create - upload - exec - download - kill.

    A deliberately minimal but self-contained end-to-end exercise that
    validates C16-AC1 (template built with the ADR-17 tooling) and C16-AC2
    (backend conforms to the :class:`SandboxClient` protocol) in a single
    flight.
    """
    from sandbox.client import (  # noqa: PLC0415
        upload_sample_to_sandbox,
    )
    from sandbox.e2b_backend import E2BBackend  # noqa: PLC0415

    backend: SandboxClient = E2BBackend()
    analysis_id = f"smoke-{uuid.uuid4().hex[:12]}"
    session = None
    try:
        session = await _create_or_skip(backend, analysis_id)
        assert session.backend == "e2b"
        assert session.workdir == f"/workspace/{analysis_id}/"
        assert session.sandbox_id

        sample_path = f"{session.workdir.rstrip('/')}/sample.bin"
        await backend.upload(session, sample_path, _MINIMAL_PE_BYTES)

        round_tripped = await backend.download(session, sample_path)
        assert round_tripped == _MINIMAL_PE_BYTES

        expected_digest = hashlib.sha256(_MINIMAL_PE_BYTES).hexdigest()
        result = await backend.exec(
            session,
            ["sha256sum", sample_path],
            timeout=30.0,
        )
        assert result.exit_code == 0, (
            f"sha256sum failed: stderr={result.stderr!r} stdout={result.stdout!r}"
        )
        assert not result.timed_out
        assert expected_digest in result.stdout

        # Extra sanity: upload_sample_to_sandbox helper should also survive
        # round-tripping via the real backend (the helper is the only
        # sanctioned path for sample bytes - DESIGN.md section 3.1).
        import tempfile  # noqa: PLC0415
        from pathlib import Path  # noqa: PLC0415

        with tempfile.NamedTemporaryFile(delete=False) as host_file:
            host_file.write(_MINIMAL_PE_BYTES)
            host_tmp = Path(host_file.name)
        try:
            dest = await upload_sample_to_sandbox(
                backend, session, host_tmp, filename="helper_sample.bin"
            )
            assert dest == f"{session.workdir.rstrip('/')}/helper_sample.bin"
            assert (await backend.download(session, dest)) == _MINIMAL_PE_BYTES
        finally:
            host_tmp.unlink(missing_ok=True)
    finally:
        if session is not None:
            # kill is idempotent: call it twice to exercise that contract.
            await backend.kill(session)
            await backend.kill(session)


@pytest.mark.skipif(SKIP_INTEGRATION, reason=E2B_SKIP_REASON)
async def test_e2b_backend_rejects_path_escape() -> None:
    """``upload`` / ``download`` must reject paths outside ``session.workdir``.

    Defence-in-depth for NFR-03: even a buggy caller cannot write to
    ``/etc/`` or read ``/root/`` through the backend.
    """
    from sandbox.e2b_backend import E2BBackend  # noqa: PLC0415

    backend = E2BBackend()
    analysis_id = f"smoke-{uuid.uuid4().hex[:12]}"
    session = None
    try:
        session = await _create_or_skip(backend, analysis_id)
        with pytest.raises(ValueError, match="outside session workspace"):
            await backend.upload(session, "/etc/passwd", b"nope")
        with pytest.raises(ValueError, match="outside session workspace"):
            await backend.download(session, "/etc/passwd")
    finally:
        if session is not None:
            await backend.kill(session)


@pytest.mark.skipif(SKIP_INTEGRATION, reason=E2B_SKIP_REASON)
async def test_e2b_backend_exec_captures_nonzero_exit() -> None:
    """A command that exits non-zero must return a populated :class:`ExecResult`.

    The backend MUST NOT raise ``CommandExitException`` on non-zero exit -
    analysis tools (``yara``, ``die``, ``pefile``) routinely return non-zero
    for "nothing matched" / "not a PE" and the caller needs the structured
    result to record an evidence gap.
    """
    from sandbox.e2b_backend import E2BBackend  # noqa: PLC0415

    backend = E2BBackend()
    analysis_id = f"smoke-{uuid.uuid4().hex[:12]}"
    session = None
    try:
        session = await _create_or_skip(backend, analysis_id)
        result = await backend.exec(
            session,
            ["sh", "-c", "echo hello && exit 7"],
            timeout=10.0,
        )
        assert result.exit_code == 7
        assert "hello" in result.stdout
        assert not result.timed_out
    finally:
        if session is not None:
            await backend.kill(session)
