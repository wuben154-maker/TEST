"""FileReadTool — sandbox-side structured file reader (C7 / FR-04~07).

The third of the three DESIGN.md §2.3.2 primitive tools.  Skill workflows
use this Tool to pull structured analysis artefacts (JSON, Ghidra exports,
FLOSS output text) back from the sandbox into the Agent prompt.

Hard invariants (C7-AC4):

1. **Workspace-only paths** — the logical path must be absolute and live
   under ``/workspace/<analysis_id>/``.  :func:`validate_sandbox_path`
   collapses ``..``/``.`` segments first, so escape attempts such as
   ``/workspace/<aid>/../../etc/passwd`` are rejected.

2. **No raw sample bytes** — the basename is matched against a deny-list
   (``sample.bin`` plus binary file extensions).  Attempts to read the
   sample itself raise :class:`~errors.ToolSchemaInvalid`
   with ``reason='raw_binary_forbidden'`` so NFR-03 is preserved even if
   the LLM tries to cheat the trust boundary.

Audit logging (C7-AC5 / NFR-06) is performed via
:func:`~audit.log_tool_call` on every invocation, including
validation failures and recoverable ``FILE_NOT_FOUND`` downloads.

Async-only; invoke via :meth:`~langchain_core.tools.BaseTool.ainvoke`.
"""

from __future__ import annotations

import posixpath
import time
from typing import Any

from langchain_core.tools import BaseTool
from pydantic import BaseModel, ConfigDict, Field

from audit import log_tool_call
from errors import ToolSchemaInvalid
from sandbox.client import SandboxClient, validate_sandbox_path
from sandbox.registry import get_session


def _file_missing_exception_types() -> tuple[type[BaseException], ...]:
    """Exception types that mean ``download`` hit a missing sandbox path.

    E2B raises :class:`e2b.exceptions.FileNotFoundException`; the subprocess
    backend raises :class:`FileNotFoundError`.  Both are normalised here so
    :class:`FileReadTool` can return a recoverable tool payload instead of
    aborting the LangGraph run (IR-11 parity with :class:`BashTool`).
    """

    types: tuple[type[BaseException], ...] = (FileNotFoundError,)
    try:
        from e2b.exceptions import FileNotFoundException as E2BFileNotFound
    except ImportError:
        return types
    return types + (E2BFileNotFound,)


_FILE_MISSING_EXC: tuple[type[BaseException], ...] = _file_missing_exception_types()

#: Default cap on the bytes returned to the Agent.  Matches the
#: DESIGN.md §2.3.2 "stdout truncation" budget (64 KiB) so a single
#: FileRead cannot blow past the Bash streaming cap.
DEFAULT_MAX_BYTES: int = 64 * 1024

#: Basenames that must never be read back to the Agent.  ``sample.bin`` is
#: the canonical upload target (FR-01 AC-7); other entries belong to
#: future batches that might stash packed payloads in the workspace.
_FORBIDDEN_BASENAMES: frozenset[str] = frozenset(
    {
        "sample.bin",
    }
)

#: Lower-cased extensions (including leading dot) that signal a binary
#: blob.  Any match raises ``raw_binary_forbidden``.
_FORBIDDEN_EXTENSIONS: frozenset[str] = frozenset(
    {
        ".bin",
        ".exe",
        ".dll",
        ".so",
        ".dylib",
        ".sys",
        ".o",
        ".a",
        ".ko",
        ".img",
        ".raw",
        ".macho",
    }
)


class FileReadInput(BaseModel):
    """Input schema for :class:`FileReadTool`."""

    model_config = ConfigDict(extra="forbid")

    path: str = Field(
        description="Absolute sandbox path under /workspace/<analysis_id>/.",
    )
    analysis_id: str = Field(
        description="UUID identifying the analysis whose sandbox owns the file.",
    )
    max_bytes: int | None = Field(
        default=None,
        description="Optional override for the byte cap; defaults to DEFAULT_MAX_BYTES.",
    )


def _reject_binary_payload(path: str) -> None:
    """Raise if ``path``'s basename / extension is on the deny-list."""
    basename = posixpath.basename(path)
    lowered = basename.lower()
    if lowered in _FORBIDDEN_BASENAMES:
        msg = (
            f"path {path!r} points at the raw sample blob ({basename!r}); "
            "LLM-facing reads must be restricted to structured analysis "
            "artefacts (NFR-03)."
        )
        raise ToolSchemaInvalid(
            msg,
            details={
                "reason": "raw_binary_forbidden",
                "path": path,
                "basename": basename,
            },
        )
    ext = posixpath.splitext(lowered)[1]
    if ext in _FORBIDDEN_EXTENSIONS:
        msg = (
            f"path {path!r} has a forbidden binary extension ({ext!r}); "
            "only structured text artefacts may be read back (NFR-03)."
        )
        raise ToolSchemaInvalid(
            msg,
            details={
                "reason": "raw_binary_forbidden",
                "path": path,
                "extension": ext,
            },
        )


class FileReadTool(BaseTool):
    """Read a structured artefact back from the sandbox workspace.

    Args:
        sandbox_client: Any concrete backend implementing
            :class:`~sandbox.client.SandboxClient`.
        default_max_bytes: Fallback byte cap when the Tool input omits
            ``max_bytes`` (DESIGN.md §2.3.2 budget parity with Bash).
    """

    name: str = "file_read"
    description: str = (
        "Read a structured artefact (JSON / text / export) from the "
        "per-analysis sandbox workspace. "
        "Only paths under /workspace/<analysis_id>/ are allowed; raw sample "
        "blobs (sample.bin, *.exe, *.dll, *.so, *.bin, etc.) are rejected "
        "before the read happens. Returns UTF-8-decoded content truncated "
        "to 64 KiB. If the path does not exist, returns ok=false with "
        "error_code=FILE_NOT_FOUND (the bash tool is not a shell — `>` never "
        "creates files; create artefacts with python_exec or CLI -o flags first)."
    )
    args_schema: type[BaseModel] = FileReadInput

    sandbox_client: Any
    default_max_bytes: int = DEFAULT_MAX_BYTES

    model_config = {"arbitrary_types_allowed": True}

    def _run(self, **kwargs: Any) -> Any:  # type: ignore[override]  # pragma: no cover
        msg = (
            "FileReadTool is async-only; invoke via .ainvoke(...) rather "
            "than .invoke(...)."
        )
        raise NotImplementedError(msg)

    def _schema_error_result(
        self,
        exc: ToolSchemaInvalid,
        *,
        start: float,
        path: str,
        analysis_id: str,
        max_bytes: int,
    ) -> dict[str, Any]:
        """Return a recoverable ToolMessage payload for path-policy failures."""
        wall_ms = (time.perf_counter() - start) * 1000.0
        log_tool_call(
            tool_name=self.name,
            args={
                "path": path,
                "analysis_id": analysis_id,
                "max_bytes": max_bytes,
            },
            result={
                "bytes_returned": 0,
                "truncated": False,
                "error_code": "TOOL_SCHEMA_INVALID",
                "reason": exc.details.get("reason"),
            },
            duration_ms=wall_ms,
            success=False,
            error_code="TOOL_SCHEMA_INVALID",
        )
        return {
            "ok": False,
            "error_code": "TOOL_SCHEMA_INVALID",
            "reason": exc.details.get("reason"),
            "path": path,
            "message": exc.message,
            "details": exc.details,
        }

    async def _arun(self, **kwargs: Any) -> dict[str, Any]:  # type: ignore[override]
        inp = FileReadInput(**kwargs)
        max_bytes = (
            inp.max_bytes if inp.max_bytes is not None else self.default_max_bytes
        )

        start = time.perf_counter()
        session = await get_session(inp.analysis_id)
        if session is None:
            msg = (
                f"no sandbox session registered for analysis_id={inp.analysis_id!r}; "
                "call SandboxSessionTool(action='create', ...) first."
            )
            exc = ToolSchemaInvalid(
                msg,
                details={
                    "reason": "sandbox_session_missing",
                    "analysis_id": inp.analysis_id,
                },
            )
            return self._schema_error_result(
                exc,
                start=start,
                path=inp.path,
                analysis_id=inp.analysis_id,
                max_bytes=max_bytes,
            )

        try:
            validate_sandbox_path(session, inp.path)
        except ValueError as exc:
            schema_exc = ToolSchemaInvalid(
                str(exc),
                details={"reason": "path_outside_workspace", "path": inp.path},
            )
            return self._schema_error_result(
                schema_exc,
                start=start,
                path=inp.path,
                analysis_id=inp.analysis_id,
                max_bytes=max_bytes,
            )

        try:
            _reject_binary_payload(inp.path)
        except ToolSchemaInvalid as exc:
            return self._schema_error_result(
                exc,
                start=start,
                path=inp.path,
                analysis_id=inp.analysis_id,
                max_bytes=max_bytes,
            )

        client: SandboxClient = self.sandbox_client
        try:
            data: bytes = await client.download(session, inp.path)
        except _FILE_MISSING_EXC:
            wall_ms = (time.perf_counter() - start) * 1000.0
            log_tool_call(
                tool_name=self.name,
                args={
                    "path": inp.path,
                    "analysis_id": inp.analysis_id,
                    "max_bytes": max_bytes,
                },
                result={
                    "bytes_returned": 0,
                    "truncated": False,
                    "error_code": "FILE_NOT_FOUND",
                },
                duration_ms=wall_ms,
                success=False,
                error_code="FILE_NOT_FOUND",
            )
            message = (
                f"no file at {inp.path!r} in the sandbox workspace. "
                "The path must already exist: the bash tool is not a shell, "
                "so shell redirection (`>`) does not create files. Use "
                "stdout from bash/python_exec, write files via python_exec, "
                "or a whitelisted CLI output flag (e.g. yara -o) before "
                "calling file_read."
            )
            return {
                "ok": False,
                "error_code": "FILE_NOT_FOUND",
                "reason": "file_not_found",
                "path": inp.path,
                "message": message,
                "details": {
                    "reason": "file_not_found",
                    "path": inp.path,
                    "analysis_id": inp.analysis_id,
                },
            }

        truncated = False
        if max_bytes >= 0 and len(data) > max_bytes:
            data = data[:max_bytes]
            truncated = True

        content = data.decode("utf-8", errors="replace")
        wall_ms = (time.perf_counter() - start) * 1000.0

        result: dict[str, Any] = {
            "ok": True,
            "path": inp.path,
            "content": content,
            "bytes_returned": len(data),
            "truncated": truncated,
        }

        log_tool_call(
            tool_name=self.name,
            args={
                "path": inp.path,
                "analysis_id": inp.analysis_id,
                "max_bytes": max_bytes,
            },
            result={
                "bytes_returned": len(data),
                "truncated": truncated,
            },
            duration_ms=wall_ms,
            success=True,
            error_code=None,
        )
        return result


__all__ = ["DEFAULT_MAX_BYTES", "FileReadInput", "FileReadTool"]
