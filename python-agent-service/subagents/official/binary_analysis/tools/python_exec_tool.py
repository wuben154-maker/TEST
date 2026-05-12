"""PythonExecTool — whitelisted Python snippet execution (C7 / FR-04~06).

Drives the second of the three DESIGN.md §2.3.2 primitive tools: skill
workflows use this Tool to run short Python snippets against the libraries
pre-installed in the E2B template (``pefile``, ``lief``, ``capstone``,
``yara-python``, ``ssdeep``, ``tlsh``, ...).  Execution happens via the
``python3`` entry point already permitted by :data:`bash_whitelist.yaml`.

Invariants (shared with :class:`~tools.bash_tool.BashTool`):

1. **No package installation (C7-AC3)** — any snippet that contains a
   ``pip install`` / ``pip3 install`` / ``python -m pip install`` token is
   rejected **before** reaching the sandbox; packages must come from the
   template image (ADR-17).  The sandbox additionally runs with
   ``allow_internet_access=False`` which blocks networked imports like
   ``import requests`` — this Tool does not re-validate that at the
   Python level; the sandbox is the enforcement point.

2. **Timeout + stdout/stderr truncation (C7-AC2 / IR-10)** — same contract
   as :class:`BashTool` (delegated to :meth:`SandboxClient.exec`).

3. **Audit logging (C7-AC5 / NFR-06)** — every call is recorded via
   :func:`~audit.log_tool_call` with ``tool_name='python_exec'``.

Async-only; invoke via :meth:`~langchain_core.tools.BaseTool.ainvoke`.
"""

from __future__ import annotations

import re
import time
from typing import Any

from langchain_core.tools import BaseTool
from pydantic import BaseModel, ConfigDict, Field

from audit import log_tool_call
from errors import ToolSchemaInvalid
from sandbox.client import ExecResult, SandboxClient
from sandbox.registry import get_session
from tools.bash_tool import (
    DEFAULT_LLM_PREVIEW_HEAD_BYTES,
    DEFAULT_LLM_PREVIEW_TAIL_BYTES,
    DEFAULT_STREAM_LIMIT_BYTES,
    DEFAULT_TIMEOUT_SECONDS,
    _preview,
    _truncate,
)

# Matches any form of ``pip install`` that can mutate the template, including
# both direct shell forms and list / tuple literal forms used with
# ``subprocess``:
#   - ``pip install foo``
#   - ``pip3 install foo``
#   - ``python -m pip install foo`` (the ``-m pip`` prefix is absorbed by
#     the ``pip`` token; we only need to see ``pip`` → ``install`` close by)
#   - ``['pip', 'install', 'foo']``
#   - ``subprocess.run(['pip', 'install', ...])``
# ``\W+`` covers the whitespace, commas, and quotes that appear between the
# two tokens across these forms.  Invoked via :func:`re.search` on the *raw
# code string* (not after tokenisation) so obfuscations via
# ``"pi" "p install"`` still fall back to the sandbox's
# ``allow_internet_access=False`` defence in depth.
_PIP_INSTALL_PATTERN = re.compile(r"\bpip3?\b\W+install\b", re.IGNORECASE)

# LLMs often confuse "run this .py file" with ``python3 -c <snippet>`` and pass
# a bare path like ``suicide.py`` as ``code``, which provokes
# :exc:`SyntaxError` / :exc:`IndentationError` instead of running the file.
# Reject a single line that is only a path-like ``*.py`` string (no spaces or
# ``= ( ) ' "`` etc.) and point callers at :class:`BashTool` for ``python3
# /path`` instead.
_SCRIPT_PATH_NOT_CODE = re.compile(r"^[A-Za-z0-9_./-]+\.py$")


def _reject_script_path_mistake(code: str) -> None:
    """Raise if ``code`` looks like a .py *path* instead of a snippet (FR C7)."""
    stripped = code.strip()
    if not stripped or "\n" in stripped or " " in stripped:
        return
    if not _SCRIPT_PATH_NOT_CODE.fullmatch(stripped):
        return
    msg = (
        "python_exec receives Python *source* for `python3 -c`, not a script "
        "file path. To run a .py file, use the `bash` tool with a full path, "
        "e.g. `python3 /workspace/<analysis_id>/script.py` (and keep paths "
        "under that analysis workspace)."
    )
    raise ToolSchemaInvalid(msg, details={"reason": "script_path_not_code"})


class PythonExecInput(BaseModel):
    """Input schema for :class:`PythonExecTool`."""

    model_config = ConfigDict(extra="forbid")

    code: str = Field(
        description=(
            "Python *source* passed to `python3 -c` (a snippet, not a filename). "
            "To execute a .py *file*, use the `bash` tool: "
            "`python3 /workspace/<analysis_id>/path/to/script.py`."
        ),
    )
    analysis_id: str = Field(
        description="UUID identifying the analysis whose sandbox should run the code.",
    )
    timeout_seconds: float | None = Field(
        default=None,
        description="Optional per-call timeout override; defaults to DEFAULT_TIMEOUT_SECONDS.",
    )
    cwd: str | None = Field(
        default=None,
        description="Optional sandbox-side cwd; must live under /workspace/<analysis_id>/.",
    )


def _reject_package_installation(code: str) -> None:
    """Raise :class:`ToolSchemaInvalid` if ``code`` appears to run ``pip install``.

    This is a best-effort guard; the authoritative enforcement is the
    sandbox's blocked network.  Keeping the check at the Tool boundary lets
    us fail loud with a structured error code instead of waiting for a
    cryptic network timeout from the E2B VM.
    """
    if _PIP_INSTALL_PATTERN.search(code):
        msg = (
            "python_exec code contains a 'pip install' invocation; "
            "the sandbox template (ADR-17) ships every allowed package "
            "pre-installed and forbids runtime installation."
        )
        raise ToolSchemaInvalid(msg, details={"reason": "pip_install_forbidden"})


class PythonExecTool(BaseTool):
    """Execute a short Python snippet via ``python3 -c`` inside the sandbox.

    Args:
        sandbox_client: Any concrete backend implementing
            :class:`~sandbox.client.SandboxClient`.
        default_timeout_seconds: Fallback timeout when input omits one.
        stdout_limit_bytes: stdout byte cap for the Agent-visible payload.
        stderr_limit_bytes: stderr byte cap for the Agent-visible payload.
    """

    name: str = "python_exec"
    description: str = (
        "Execute a short Python snippet via `python3 -c` inside the sandbox. "
        "Only packages pre-installed in the E2B template are importable; "
        "`pip install` is rejected and the sandbox blocks outbound network "
        "(so `import requests` will fail at runtime).\n"
        "\n"
        "Output handling: stdout and stderr are capped at 64 KiB each at the "
        "sandbox boundary (IR-10 / SPEC C7-AC2). If that cap fires, the tool "
        "ALSO returns only a head+tail preview (~6 KiB) in `stdout` / "
        "`stderr` and sets `stdout_preview_only` / `stderr_preview_only` to "
        "true; the full 64 KiB payload is NOT preserved in the tool result. "
        "If you expect a large structured output, write it to a file inside "
        "/workspace/<aid>/ (e.g. `json.dump(data, open('/workspace/<aid>/"
        "pe.json', 'w'))`) and read it back in pages with the `file_read` "
        "tool — shell redirection is unavailable because this tool is not a "
        "shell.\n"
        "\n"
        "Do not pass a script *filename* in `code` (e.g. `script.py`); that "
        "is not valid Python and becomes `python3 -c 'script.py'`, which "
        "fails. To run a file, use the `bash` tool with `python3 /path/to/"
        "script.py`."
    )
    args_schema: type[BaseModel] = PythonExecInput

    sandbox_client: Any
    default_timeout_seconds: float = DEFAULT_TIMEOUT_SECONDS
    stdout_limit_bytes: int = DEFAULT_STREAM_LIMIT_BYTES
    stderr_limit_bytes: int = DEFAULT_STREAM_LIMIT_BYTES
    stdout_preview_head_bytes: int = DEFAULT_LLM_PREVIEW_HEAD_BYTES
    stdout_preview_tail_bytes: int = DEFAULT_LLM_PREVIEW_TAIL_BYTES
    stderr_preview_head_bytes: int = DEFAULT_LLM_PREVIEW_HEAD_BYTES
    stderr_preview_tail_bytes: int = 1024

    model_config = {"arbitrary_types_allowed": True}

    def _run(self, **kwargs: Any) -> Any:  # type: ignore[override]  # pragma: no cover
        msg = (
            "PythonExecTool is async-only; invoke via .ainvoke(...) rather "
            "than .invoke(...)."
        )
        raise NotImplementedError(msg)

    def _schema_error_result(
        self,
        exc: ToolSchemaInvalid,
        *,
        start: float,
        code: str,
        timeout: float,
        cwd: str | None,
        analysis_id: str,
    ) -> dict[str, Any]:
        """Return a recoverable ToolMessage payload without leaking source code."""
        wall_ms = (time.perf_counter() - start) * 1000.0
        log_tool_call(
            tool_name=self.name,
            args={
                "code_bytes": len(code.encode("utf-8")),
                "code_sha256_prefix": _sha256_prefix(code),
                "timeout_seconds": timeout,
                "cwd": cwd,
                "analysis_id": analysis_id,
            },
            result={
                "exit_code": None,
                "timed_out": False,
                "duration_ms": 0.0,
                "stdout_truncated": False,
                "stderr_truncated": False,
                "stdout_bytes": 0,
                "stderr_bytes": 0,
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
            "message": exc.message,
            "details": exc.details,
        }

    async def _arun(self, **kwargs: Any) -> dict[str, Any]:  # type: ignore[override]
        inp = PythonExecInput(**kwargs)
        timeout = inp.timeout_seconds or self.default_timeout_seconds

        start = time.perf_counter()
        try:
            _reject_package_installation(inp.code)
            _reject_script_path_mistake(inp.code)
        except ToolSchemaInvalid as exc:
            return self._schema_error_result(
                exc,
                start=start,
                code=inp.code,
                timeout=timeout,
                cwd=inp.cwd,
                analysis_id=inp.analysis_id,
            )
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
                code=inp.code,
                timeout=timeout,
                cwd=inp.cwd,
                analysis_id=inp.analysis_id,
            )

        client: SandboxClient = self.sandbox_client
        try:
            exec_result: ExecResult = await client.exec(
                session,
                ["python3", "-c", inp.code],
                timeout=timeout,
                cwd=inp.cwd,
            )
        except Exception as exc:
            # Unexpected backend failure — a well-behaved backend returns an
            # ``ExecResult`` for every exit-code / timeout / OOM case (ADR-16
            # IR-10). Preserve the audit trail, but return a ToolMessage so
            # one leaked SDK exception does not abort the whole agent run.
            wall_ms = (time.perf_counter() - start) * 1000.0
            log_tool_call(
                tool_name=self.name,
                args={
                    "code_bytes": len(inp.code.encode("utf-8")),
                    "code_sha256_prefix": _sha256_prefix(inp.code),
                    "timeout_seconds": timeout,
                    "cwd": inp.cwd,
                    "analysis_id": inp.analysis_id,
                },
                result={
                    "exit_code": None,
                    "timed_out": False,
                    "duration_ms": wall_ms,
                    "stdout_truncated": False,
                    "stderr_truncated": False,
                    "stdout_bytes": 0,
                    "stderr_bytes": 0,
                    "error_type": type(exc).__name__,
                },
                duration_ms=wall_ms,
                success=False,
                error_code="TOOL_CRASH",
            )
            return {
                "ok": False,
                "error_code": "TOOL_CRASH",
                "reason": "sandbox_exec_exception",
                "message": (
                    "sandbox exec backend raised an exception instead of "
                    f"returning ExecResult: {type(exc).__name__}"
                ),
                "details": {
                    "reason": "sandbox_exec_exception",
                    "error_type": type(exc).__name__,
                    "analysis_id": inp.analysis_id,
                },
            }

        stdout_sandbox, stdout_truncated = _truncate(
            exec_result.stdout, self.stdout_limit_bytes
        )
        stderr_sandbox, stderr_truncated = _truncate(
            exec_result.stderr, self.stderr_limit_bytes
        )
        # Stage-2 preview — mirrors :class:`~tools.bash_tool.BashTool`.
        # See that tool for the rationale; identical contract so skills that
        # consume the two tool results can branch on the same flag name.
        if stdout_truncated:
            stdout = _preview(
                stdout_sandbox,
                head_bytes=self.stdout_preview_head_bytes,
                tail_bytes=self.stdout_preview_tail_bytes,
                original_bytes=len(exec_result.stdout.encode("utf-8")),
                stream_name="stdout",
            )
            stdout_preview_only = True
        else:
            stdout = stdout_sandbox
            stdout_preview_only = False
        if stderr_truncated:
            stderr = _preview(
                stderr_sandbox,
                head_bytes=self.stderr_preview_head_bytes,
                tail_bytes=self.stderr_preview_tail_bytes,
                original_bytes=len(exec_result.stderr.encode("utf-8")),
                stream_name="stderr",
            )
            stderr_preview_only = True
        else:
            stderr = stderr_sandbox
            stderr_preview_only = False

        ok = exec_result.exit_code == 0 and not exec_result.timed_out
        wall_ms = (time.perf_counter() - start) * 1000.0

        result: dict[str, Any] = {
            "ok": ok,
            "exit_code": exec_result.exit_code,
            "stdout": stdout,
            "stderr": stderr,
            "duration_ms": exec_result.duration_ms,
            "timed_out": exec_result.timed_out,
            "stdout_truncated": stdout_truncated,
            "stderr_truncated": stderr_truncated,
            "stdout_preview_only": stdout_preview_only,
            "stderr_preview_only": stderr_preview_only,
        }

        log_tool_call(
            tool_name=self.name,
            args={
                "code_bytes": len(inp.code.encode("utf-8")),
                "code_sha256_prefix": _sha256_prefix(inp.code),
                "timeout_seconds": timeout,
                "cwd": inp.cwd,
                "analysis_id": inp.analysis_id,
            },
            result={
                "exit_code": exec_result.exit_code,
                "timed_out": exec_result.timed_out,
                "duration_ms": exec_result.duration_ms,
                "stdout_truncated": stdout_truncated,
                "stderr_truncated": stderr_truncated,
                "stdout_preview_only": stdout_preview_only,
                "stderr_preview_only": stderr_preview_only,
                "stdout_bytes": len(stdout.encode("utf-8")),
                "stderr_bytes": len(stderr.encode("utf-8")),
            },
            duration_ms=wall_ms,
            success=ok,
            error_code=None
            if ok
            else ("TOOL_TIMEOUT" if exec_result.timed_out else "TOOL_CRASH"),
        )
        return result


def _sha256_prefix(text: str) -> str:
    """Return the first 12 hex chars of SHA-256(text).

    Keeps the audit log compact while still letting forensic review
    de-duplicate identical snippets across a session.
    """
    import hashlib

    return hashlib.sha256(text.encode("utf-8")).hexdigest()[:12]


__all__ = ["PythonExecInput", "PythonExecTool"]
