"""E2B sandbox backend — synchronous implementation of BaseSandbox.

Wraps the e2b.Sandbox (synchronous client) so it can be passed as the
``backend=`` parameter to create_deep_agent() or as a SubAgent backend.

For the primary tool-based path, use app/tools/sandbox_tools.py instead.
"""

from __future__ import annotations

import os

import structlog

from app._vendor.deepagents.backends.protocol import (
    ExecuteResponse,
    FileDownloadResponse,
    FileUploadResponse,
)
from app._vendor.deepagents.backends.sandbox import BaseSandbox
from app.tools.sandbox_tools import _load_sandbox_config, _resolve_template

logger = structlog.get_logger(__name__)


class E2BSandboxBackend(BaseSandbox):
    """Synchronous E2B sandbox backend.

    Satisfies BaseSandbox / SandboxBackendProtocol.

    Usage::

        backend = E2BSandboxBackend(template="binary-analysis")
        agent = create_deep_agent(..., backend=backend)

    The sandbox is created lazily on first ``execute()`` call and reused for the
    session lifetime.  Call ``close()`` to destroy it explicitly.
    """

    def __init__(
        self,
        *,
        template: str | None = None,
        api_key: str | None = None,
        timeout: int | None = None,
    ) -> None:
        self._template = template
        self._api_key = api_key or os.environ.get("E2B_API_KEY")
        self._timeout = timeout
        self._sandbox: object | None = None

    # ------------------------------------------------------------------
    # BaseSandbox abstract interface
    # ------------------------------------------------------------------

    @property
    def id(self) -> str:
        """Unique identifier for this backend instance."""
        if self._sandbox is None:
            return "<not_started>"
        return getattr(self._sandbox, "sandbox_id", "<unknown>")

    def execute(
        self,
        command: str,
        *,
        timeout: int | None = None,
    ) -> ExecuteResponse:
        """Execute a shell command synchronously and return ExecuteResponse."""
        sandbox = self._get_or_create_sandbox()
        cfg_timeout = _load_sandbox_config().defaults.timeout_seconds
        used_timeout = timeout or self._timeout or cfg_timeout
        try:
            result = sandbox.commands.run(command, timeout=used_timeout)
            combined = (result.stdout or "") + (result.stderr or "")
            return ExecuteResponse(
                output=combined,
                exit_code=result.exit_code,
                truncated=False,
            )
        except Exception as exc:  # noqa: BLE001
            logger.error("e2b_backend_execute_failed", error=str(exc))
            return ExecuteResponse(output=str(exc), exit_code=1, truncated=False)

    def upload_files(self, files: list[tuple[str, bytes]]) -> list[FileUploadResponse]:
        """Upload multiple files; partial failures are captured per-file."""
        sandbox = self._get_or_create_sandbox()
        results: list[FileUploadResponse] = []
        for path, content in files:
            try:
                sandbox.files.write(path, content)
                results.append(FileUploadResponse(path=path, error=None))
            except Exception as exc:  # noqa: BLE001
                logger.warning("e2b_upload_failed", path=path, error=str(exc))
                results.append(FileUploadResponse(path=path, error=str(exc)))
        return results

    def download_files(self, paths: list[str]) -> list[FileDownloadResponse]:
        """Download multiple files; partial failures are captured per-file."""
        sandbox = self._get_or_create_sandbox()
        results: list[FileDownloadResponse] = []
        for path in paths:
            try:
                raw: bytes = sandbox.files.read(path, format="bytes")
                results.append(FileDownloadResponse(path=path, content=raw, error=None))
            except Exception as exc:  # noqa: BLE001
                logger.warning("e2b_download_failed", path=path, error=str(exc))
                results.append(
                    FileDownloadResponse(path=path, content=b"", error=str(exc))
                )
        return results

    # ------------------------------------------------------------------
    # Lifecycle helpers
    # ------------------------------------------------------------------

    def close(self) -> None:
        """Destroy the underlying E2B sandbox."""
        if self._sandbox is not None:
            try:
                self._sandbox.kill()
            except Exception:  # noqa: BLE001
                logger.warning("e2b_backend_close_failed", sandbox_id=self.id)
            finally:
                self._sandbox = None

    def _get_or_create_sandbox(self) -> object:
        """Return the existing sandbox or create a new one (lazy init)."""
        if self._sandbox is not None:
            return self._sandbox

        if not self._api_key:
            raise RuntimeError(
                "E2B_API_KEY is not configured. "
                "Set it in .env to use E2BSandboxBackend."
            )

        try:
            tpl, _ = _resolve_template(self._template)
        except ValueError as exc:
            raise RuntimeError(str(exc)) from exc

        try:
            from e2b import Sandbox  # synchronous client

            self._sandbox = Sandbox(
                template=tpl.template_id,
                api_key=self._api_key,
                timeout=self._timeout or tpl.timeout_seconds,
            )
            logger.info(
                "e2b_backend_sandbox_created",
                sandbox_id=self._sandbox.sandbox_id,
                template=self._template,
            )
            return self._sandbox
        except Exception as exc:
            raise RuntimeError(f"Failed to create E2B sandbox: {exc}") from exc
