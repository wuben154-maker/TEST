"""E2B on-demand sandbox tools.

Four StructuredTools for isolated command execution:
  - sandbox_create  : create a named session-level sandbox
  - sandbox_destroy : kill a session-level sandbox
  - sandbox_run     : execute a shell command (per-call or session-reuse, optional streaming)
  - sandbox_pty_run : PTY interactive session (list of commands sent sequentially, streaming)

All tools are conditionally mounted: if E2B_API_KEY is not configured, the agent
will not receive these tools and behaviour is unchanged.

Template configuration lives entirely in config/sandbox.yaml.
"""

from __future__ import annotations

import asyncio
import base64
import json
import os
from functools import lru_cache
from pathlib import Path
from typing import Any

import structlog
import yaml
from langchain_core.tools import StructuredTool
from pydantic import BaseModel, Field

from app.tools.sandbox_sse import emit_sandbox_output
from app.tools.sandbox_workspace_stage import strip_workspace_staging_for_guard

# Module-level reference so tests can patch `app.tools.sandbox_tools.AsyncSandbox`.
# Falls back to None when e2b is not installed (tools return an error at call time).
try:
    from e2b import AsyncSandbox  # type: ignore[import-untyped]
except ImportError:
    AsyncSandbox = None  # type: ignore[assignment,misc]

logger = structlog.get_logger(__name__)

# ---------------------------------------------------------------------------
# Host-virtual-path guard
# ---------------------------------------------------------------------------
# Sandbox filesystems are isolated VMs; SecManus host virtual paths
# (``/workspace/...``, ``/uploads/...``, ``workspace/...``) do not exist inside
# them. When the agent copies a UI-rendered path into a ``sandbox_run``
# ``command`` or a ``sandbox_path`` the command fails with a confusing ``cat:
# No such file or directory``. We catch that at the tool boundary and return a
# structured error so the LLM corrects course in one step instead of retrying.

import re as _re

_HOST_VIRTUAL_PATTERNS = (
    _re.compile(r"(?<![\w/])(?:/workspace|workspace)(?=/|\b)", _re.IGNORECASE),
    _re.compile(r"(?<![\w/])/uploads(?=/|\b)"),
)


def _contains_host_virtual_path(text: str) -> str | None:
    """Return the first offending substring, or ``None``.

    Only absolute variants and the UI-rendered ``workspace/…`` shape are
    flagged. A bare ``workspace`` word in a comment or sandbox-local path
    like ``/home/user/workspace`` passes through.
    """
    if not text:
        return None
    for pat in _HOST_VIRTUAL_PATTERNS:
        m = pat.search(text)
        if m:
            return m.group(0)
    return None


def _reject_host_virtual_paths_after_staging(
    command: str,
    cwd: str | None,
    upload_files: list[UploadFileSpec] | None,
    *,
    sandbox_id: str | None,
) -> str | None:
    """Return a JSON error string if strings still reference host virtual paths."""
    cmd = strip_workspace_staging_for_guard(command)
    cw = strip_workspace_staging_for_guard(cwd) if cwd else None

    offender = _contains_host_virtual_path(cmd)
    source = "command"
    if offender is None and upload_files:
        for spec in upload_files:
            sp = strip_workspace_staging_for_guard(spec.sandbox_path or "")
            offender = _contains_host_virtual_path(sp)
            if offender:
                source = "upload_files[].sandbox_path"
                break
    if offender is None and cw:
        offender = _contains_host_virtual_path(cw)
        if offender:
            source = "cwd"
    if offender is None:
        return None
    return json.dumps(
        {
            "error": (
                f"Invalid {source}: references host virtual path '{offender}'. "
                "Sandboxes do not mount the SecManus host filesystem. "
                "Pass workspace_stage_paths / enable auto staging from command, "
                "or read the file with read_file and use upload_files with "
                "sandbox_path under /tmp/secmanus/work/in/."
            ),
            "sandbox_id": None,
            "mode": "per_call" if not sandbox_id else "session",
            "exit_code": -1,
        }
    )


# ---------------------------------------------------------------------------
# Config loader
# ---------------------------------------------------------------------------

_CONFIG_PATH = Path(__file__).resolve().parents[2] / "config" / "sandbox.yaml"


class _TemplateConfig(BaseModel):
    """Single sandbox template definition."""

    template_id: str
    description: str = ""
    allow_internet: bool = False
    timeout_seconds: int = 60
    env: dict[str, str] = Field(default_factory=dict)


class _DefaultsConfig(BaseModel):
    template: str = "base"
    timeout_seconds: int = 60
    max_sandbox_lifetime: int = 300
    allow_internet: bool = False


class SandboxConfig(BaseModel):
    defaults: _DefaultsConfig = Field(default_factory=_DefaultsConfig)
    templates: dict[str, _TemplateConfig] = Field(default_factory=dict)


@lru_cache(maxsize=1)
def _load_sandbox_config() -> SandboxConfig:
    """Load and cache config/sandbox.yaml.  Restart to pick up changes."""
    try:
        with open(_CONFIG_PATH, encoding="utf-8") as fh:
            raw = yaml.safe_load(fh) or {}
        return SandboxConfig(**raw)
    except Exception as exc:  # noqa: BLE001
        logger.error("sandbox_config_load_failed", path=str(_CONFIG_PATH), error=str(exc))
        return SandboxConfig()


def _resolve_template(name: str | None) -> tuple[_TemplateConfig, str]:
    """Return (template_cfg, resolved_name).  Raises ValueError on unknown name."""
    cfg = _load_sandbox_config()
    # Allow env override of default template
    default_name = (
        os.environ.get("E2B_DEFAULT_TEMPLATE")
        or cfg.defaults.template
    )
    resolved = name or default_name
    tpl = cfg.templates.get(resolved)
    if tpl is None:
        available = list(cfg.templates.keys())
        raise ValueError(
            f"Template '{resolved}' not found in config/sandbox.yaml. "
            f"Available: {available}"
        )
    return tpl, resolved


# ---------------------------------------------------------------------------
# Input schemas
# ---------------------------------------------------------------------------


class UploadFileSpec(BaseModel):
    """A file to upload into the sandbox before executing a command."""

    sandbox_path: str = Field(
        description=(
            "Destination path inside the E2B sandbox only. Convention: inputs under "
            "/tmp/secmanus/work/in/<filename> (e.g. /tmp/secmanus/work/in/sample.php). "
            "Never use host paths like /uploads/... — they are not mounted unless "
            "materialized via upload_files."
        ),
    )
    content_b64: str | None = Field(
        default=None,
        description="Base64-encoded file content (binary or text). "
        "Supply either content_b64 or content_text, not both.",
    )
    content_text: str | None = Field(
        default=None,
        description="Plain-text file content. "
        "Supply either content_b64 or content_text, not both.",
    )


class SandboxCreateInput(BaseModel):
    """Input for sandbox_create tool."""

    template: str | None = Field(
        default=None,
        description=(
            "Sandbox template name defined in config/sandbox.yaml "
            "(e.g. 'base', 'binary-analysis', 'web-simulation'). "
            "Defaults to the value in config/sandbox.yaml defaults.template."
        ),
    )
    env_vars: dict[str, str] | None = Field(
        default=None,
        description="Extra environment variables to inject on top of the template defaults.",
    )
    metadata: str | None = Field(
        default=None,
        description="Free-form label for logging / tracing (not sent to E2B).",
    )


class SandboxDestroyInput(BaseModel):
    """Input for sandbox_destroy tool."""

    sandbox_id: str = Field(description="ID of the sandbox to destroy.")


class SandboxRunInput(BaseModel):
    """Input for sandbox_run tool."""

    command: str = Field(
        description=(
            "Shell command inside the sandbox. Reference paths that exist there: VM-local "
            "/workspace/<project_id>/<filename> after staging, manual upload_files "
            "(e.g. under /tmp/secmanus/work/in/), or standard OS paths. "
            "Never pass raw SecManus host-only paths such as /uploads/u_.../file."
        ),
    )
    sandbox_id: str | None = Field(
        default=None,
        description=(
            "Leave empty for per-call mode (sandbox is created, command runs, sandbox "
            "is destroyed automatically). Provide a sandbox_id returned by sandbox_create "
            "to reuse an existing session-level sandbox."
        ),
    )
    template: str | None = Field(
        default=None,
        description="Template to use in per-call mode. Ignored in session mode.",
    )
    upload_files: list[UploadFileSpec] | None = Field(
        default=None,
        description=(
            "Write payloads into the VM before the command runs. If content lives on the "
            "SecManus host, read it in the agent context then pass content_b64 or content_text "
            "with sandbox_path under /tmp/secmanus/work/in/. Prefer omitting sandbox_id "
            "(per-call mode) with upload_files for one-shot analysis."
        ),
    )
    download_paths: list[str] | None = Field(
        default=None,
        description=(
            "Sandbox-local paths to read back as base64 after the command (e.g. artifacts "
            "under /tmp/secmanus/work/out/). Must not be host paths."
        ),
    )
    cwd: str | None = Field(
        default=None,
        description="Working directory for command execution (default: /home/user).",
    )
    env_vars: dict[str, str] | None = Field(
        default=None,
        description="Environment variables to add/override for this execution.",
    )
    timeout: int | None = Field(
        default=None,
        description="Execution timeout in seconds (overrides template default).",
    )
    background: bool = Field(
        default=False,
        description="Start command in background (returns immediately without waiting).",
    )
    stream_to_sse: bool = Field(
        default=False,
        description=(
            "When true, each stdout/stderr line is pushed as a sandbox_output SSE event "
            "in real time. The tool still returns the complete output at the end."
        ),
    )
    workspace_stage_paths: list[str] | None = Field(
        default=None,
        description=(
            "SecManus virtual paths (/workspace/… or /uploads/…) to read on the host and "
            "upload into the sandbox before command execution. Combined with "
            "auto_stage_workspace_paths_from_command."
        ),
    )
    auto_stage_workspace_paths_from_command: bool = Field(
        default=True,
        description=(
            "When true, scan ``command`` for /workspace/, /uploads/, or workspace/… tokens "
            "and stage those files automatically (same tenant scope as read_file)."
        ),
    )
    rewrite_workspace_paths_in_command: bool = Field(
        default=True,
        description=(
            "After staging, rewrite virtual path literals in ``command`` to sandbox-local "
            "/workspace/<project_id>/<basename> paths before execution."
        ),
    )


class SandboxPtyInput(BaseModel):
    """Input for sandbox_pty_run tool."""

    commands: list[str] = Field(
        description=(
            "Commands to send sequentially to the PTY (each appended with newline). "
            "Reference only sandbox paths (e.g. files under /tmp/secmanus/work/in/ after a "
            "prior sandbox_run with upload_files in the same session)."
        ),
    )
    sandbox_id: str | None = Field(
        default=None,
        description="Leave empty for per-call mode; provide for session reuse.",
    )
    template: str | None = Field(
        default=None,
        description="Template to use in per-call mode.",
    )
    initial_wait_ms: int = Field(
        default=500,
        description="Milliseconds to wait after PTY creation before sending first command.",
    )
    between_cmd_ms: int = Field(
        default=300,
        description="Milliseconds to wait between consecutive commands.",
    )
    cols: int = Field(default=220, description="PTY terminal columns.")
    rows: int = Field(default=50, description="PTY terminal rows.")
    timeout: int = Field(
        default=60,
        description="Total PTY session timeout in seconds.",
    )
    stream_to_sse: bool = Field(
        default=True,
        description="Push each PTY output chunk as a sandbox_output SSE event.",
    )


# ---------------------------------------------------------------------------
# Core implementation helpers
# ---------------------------------------------------------------------------


def _e2b_api_key() -> str | None:
    return os.environ.get("E2B_API_KEY")


_E2B_ASYNC_SDK_UNAVAILABLE_MSG = (
    "E2B AsyncSandbox is unavailable: the `e2b` package failed to import. "
    "Install or repair the e2b dependency in the agent service (see requirements.txt)."
)


def _no_key_error() -> dict[str, Any]:
    return {"error": "E2B_API_KEY not configured. Set E2B_API_KEY in .env to use sandbox tools."}


def _async_sandbox_unavailable_json(*, sandbox_id: str | None = None) -> str:
    """JSON response when ``AsyncSandbox`` is None (import failure)."""
    payload: dict[str, Any] = {"error": _E2B_ASYNC_SDK_UNAVAILABLE_MSG}
    if sandbox_id is not None:
        payload["sandbox_id"] = sandbox_id
    else:
        payload["sandbox_id"] = None
    return json.dumps(payload)


async def _upload_files_skip_unchanged(sandbox: Any, files: list[UploadFileSpec]) -> None:
    """Write uploads; skip writes when sandbox already holds identical bytes."""
    for spec in files:
        if spec.content_b64:
            content: bytes | str = base64.b64decode(spec.content_b64)
        elif spec.content_text is not None:
            content = (
                spec.content_text.encode("utf-8")
                if isinstance(spec.content_text, str)
                else spec.content_text
            )
        else:
            continue
        if not isinstance(content, bytes):
            content = bytes(content)
        skip = False
        try:
            existing = await sandbox.files.read(spec.sandbox_path, format="bytes")
            skip = existing == content
        except Exception:  # noqa: BLE001
            skip = False
        if not skip:
            await sandbox.files.write(spec.sandbox_path, content)


async def _download_files(sandbox: Any, paths: list[str]) -> list[dict[str, Any]]:
    results: list[dict[str, Any]] = []
    for path in paths:
        try:
            raw = await sandbox.files.read(path, format="bytes")
            results.append(
                {
                    "sandbox_path": path,
                    "content_b64": base64.b64encode(raw).decode(),
                    "error": None,
                }
            )
        except Exception as exc:  # noqa: BLE001
            results.append({"sandbox_path": path, "content_b64": None, "error": str(exc)})
    return results


# ---------------------------------------------------------------------------
# Tool implementations
# ---------------------------------------------------------------------------


async def _sandbox_create(
    template: str | None,
    env_vars: dict[str, str] | None,
    metadata: str | None,
) -> str:
    if AsyncSandbox is None:
        return _async_sandbox_unavailable_json()
    if not _e2b_api_key():
        return json.dumps(_no_key_error())

    try:
        tpl, resolved_name = _resolve_template(template)
    except ValueError as exc:
        return json.dumps({"error": str(exc), "sandbox_id": None})

    try:
        merged_env = {**tpl.env, **(env_vars or {})}
        sandbox = await AsyncSandbox.create(
            template=tpl.template_id,
            api_key=_e2b_api_key(),
            timeout=tpl.timeout_seconds,
            envs=merged_env or None,
            metadata={"label": metadata} if metadata else None,
        )
        logger.info(
            "sandbox_created",
            sandbox_id=sandbox.sandbox_id,
            template=resolved_name,
            metadata=metadata,
        )
        return json.dumps(
            {
                "sandbox_id": sandbox.sandbox_id,
                "template": resolved_name,
                "status": "running",
                "error": None,
            }
        )
    except Exception as exc:  # noqa: BLE001
        logger.error("sandbox_create_failed", error=str(exc))
        return json.dumps({"error": str(exc), "sandbox_id": None})


async def _sandbox_destroy(sandbox_id: str) -> str:
    if AsyncSandbox is None:
        return _async_sandbox_unavailable_json(sandbox_id=sandbox_id)
    if not _e2b_api_key():
        return json.dumps(_no_key_error())

    try:
        sandbox = await AsyncSandbox.connect(sandbox_id, api_key=_e2b_api_key())
        await sandbox.kill()
        logger.info("sandbox_destroyed", sandbox_id=sandbox_id)
        return json.dumps(
            {
                "sandbox_id": sandbox_id,
                "status": "killed",
                "message": "Sandbox destroyed successfully.",
                "error": None,
            }
        )
    except Exception as exc:  # noqa: BLE001
        logger.warning("sandbox_destroy_failed", sandbox_id=sandbox_id, error=str(exc))
        return json.dumps({"sandbox_id": sandbox_id, "error": str(exc)})


async def _sandbox_run(inp: SandboxRunInput) -> str:  # noqa: PLR0912, PLR0915
    from app.config.settings import get_settings

    settings = get_settings()
    upload_dir = Path(settings.upload_dir)

    staging_pairs: list[tuple[str, bytes]] = []
    replacements: list[tuple[str, str]] = []
    want_stage = bool(inp.workspace_stage_paths) or inp.auto_stage_workspace_paths_from_command
    if want_stage:
        from app.tools.sandbox_workspace_stage import prepare_workspace_staging

        staging_pairs, replacements, staging_err = prepare_workspace_staging(
            workspace_stage_paths=inp.workspace_stage_paths,
            command=inp.command,
            auto_extract_from_command=inp.auto_stage_workspace_paths_from_command,
            upload_dir=upload_dir,
            max_bytes_per_file=settings.max_upload_bytes_per_file,
        )
        if staging_err:
            return json.dumps(
                {
                    "error": f"workspace staging failed: {staging_err}",
                    "sandbox_id": None,
                    "mode": "per_call" if not inp.sandbox_id else "session",
                    "exit_code": -1,
                }
            )

    effective_command = inp.command
    if replacements and inp.rewrite_workspace_paths_in_command:
        from app.tools.sandbox_workspace_stage import rewrite_command_workspace_paths

        effective_command = rewrite_command_workspace_paths(inp.command, replacements)

    staged_specs = [
        UploadFileSpec(
            sandbox_path=p,
            content_b64=base64.b64encode(raw).decode("ascii"),
        )
        for p, raw in staging_pairs
    ]
    merged_uploads: dict[str, UploadFileSpec] = {s.sandbox_path: s for s in staged_specs}
    for spec in inp.upload_files or []:
        merged_uploads[spec.sandbox_path] = spec
    merged_list = list(merged_uploads.values())

    guard = _reject_host_virtual_paths_after_staging(
        effective_command,
        inp.cwd,
        merged_list,
        sandbox_id=inp.sandbox_id,
    )
    if guard is not None:
        return guard
    if AsyncSandbox is None:
        return json.dumps({"error": _E2B_ASYNC_SDK_UNAVAILABLE_MSG})
    if not _e2b_api_key():
        return json.dumps(_no_key_error())

    cfg = _load_sandbox_config()
    mode: str
    sandbox: Any
    tpl: _TemplateConfig

    if inp.sandbox_id:
        mode = "session"
        try:
            sandbox = await AsyncSandbox.connect(
                inp.sandbox_id, api_key=_e2b_api_key()
            )
        except Exception as exc:  # noqa: BLE001
            return json.dumps(
                {"error": f"Sandbox '{inp.sandbox_id}' not found or expired: {exc}"}
            )
        tpl = _TemplateConfig(template_id="<session>")  # env not re-applied in session mode
    else:
        mode = "per_call"
        try:
            tpl, resolved_name = _resolve_template(inp.template)
        except ValueError as exc:
            return json.dumps({"error": str(exc)})
        try:
            sandbox = await AsyncSandbox.create(
                template=tpl.template_id,
                api_key=_e2b_api_key(),
                timeout=inp.timeout or tpl.timeout_seconds,
            )
        except Exception as exc:  # noqa: BLE001
            return json.dumps({"error": f"Failed to create sandbox: {exc}"})

    seq_counter = 0
    sid = sandbox.sandbox_id

    async def on_stdout(data: Any) -> None:
        nonlocal seq_counter
        if inp.stream_to_sse:
            await emit_sandbox_output(sid, "sandbox_run", "stdout", data.line, seq_counter)
        seq_counter += 1

    async def on_stderr(data: Any) -> None:
        nonlocal seq_counter
        if inp.stream_to_sse:
            await emit_sandbox_output(sid, "sandbox_run", "stderr", data.line, seq_counter)
        seq_counter += 1

    try:
        if merged_list:
            await _upload_files_skip_unchanged(sandbox, merged_list)

        env_merge: dict[str, str] = {}
        if mode == "per_call":
            env_merge.update(tpl.env)
        env_merge.update(inp.env_vars or {})

        timeout = inp.timeout or (tpl.timeout_seconds if mode == "per_call" else cfg.defaults.timeout_seconds)

        result = await sandbox.commands.run(
            effective_command,
            cwd=inp.cwd or "/home/user",
            envs=env_merge or None,
            timeout=timeout,
            on_stdout=on_stdout,
            on_stderr=on_stderr,
            background=inp.background,
        )

        downloaded: list[dict[str, Any]] = []
        if inp.download_paths:
            downloaded = await _download_files(sandbox, inp.download_paths)

        return json.dumps(
            {
                "exit_code": result.exit_code if not inp.background else None,
                "stdout": result.stdout if not inp.background else None,
                "stderr": result.stderr if not inp.background else None,
                "sandbox_id": sid,
                "mode": mode,
                "downloaded_files": downloaded,
                "streamed_lines": seq_counter if inp.stream_to_sse else None,
                "error": None,
            }
        )
    except asyncio.TimeoutError:
        return json.dumps({"exit_code": -1, "sandbox_id": sid, "mode": mode,
                           "error": "Command timed out"})
    except Exception as exc:  # noqa: BLE001
        logger.error("sandbox_run_failed", sandbox_id=sid, error=str(exc))
        return json.dumps({"exit_code": -1, "sandbox_id": sid, "mode": mode,
                           "error": str(exc)})
    finally:
        if mode == "per_call":
            try:
                await sandbox.kill()
            except Exception:  # noqa: BLE001
                logger.warning("sandbox_kill_failed_in_finally", sandbox_id=sid)


async def _sandbox_pty_run(inp: SandboxPtyInput) -> str:  # noqa: PLR0912, PLR0915
    for cmd in inp.commands or ():
        offender = _contains_host_virtual_path(cmd)
        if offender:
            return json.dumps(
                {
                    "error": (
                        f"Invalid pty command: references host virtual path '{offender}'. "
                        "Sandboxes do not mount the SecManus host filesystem. "
                        "Stage files first via sandbox_run upload_files."
                    ),
                    "sandbox_id": None,
                    "mode": "per_call" if not inp.sandbox_id else "session",
                }
            )
    if AsyncSandbox is None:
        return json.dumps(
            {"error": _E2B_ASYNC_SDK_UNAVAILABLE_MSG, "sandbox_id": None, "mode": None}
        )
    if not _e2b_api_key():
        return json.dumps(_no_key_error())

    mode: str
    sandbox: Any

    if inp.sandbox_id:
        mode = "session"
        try:
            sandbox = await AsyncSandbox.connect(
                inp.sandbox_id, api_key=_e2b_api_key()
            )
        except Exception as exc:  # noqa: BLE001
            return json.dumps(
                {"error": f"Sandbox '{inp.sandbox_id}' not found or expired: {exc}"}
            )
    else:
        mode = "per_call"
        try:
            tpl, _ = _resolve_template(inp.template)
        except ValueError as exc:
            return json.dumps({"error": str(exc)})
        try:
            sandbox = await AsyncSandbox.create(
                template=tpl.template_id,
                api_key=_e2b_api_key(),
                timeout=inp.timeout,
            )
        except Exception as exc:  # noqa: BLE001
            return json.dumps({"error": f"Failed to create sandbox: {exc}"})

    sid = sandbox.sandbox_id
    full_output: list[str] = []
    chunk_counter = 0

    async def _collect_output() -> None:
        nonlocal chunk_counter
        async for chunk in sandbox.pty.subscribe(handle.pid):
            text = chunk.decode("utf-8", errors="replace") if isinstance(chunk, bytes) else str(chunk)
            full_output.append(text)
            if inp.stream_to_sse:
                await emit_sandbox_output(
                    sid, "sandbox_pty_run", "pty",
                    text.rstrip("\r\n"), chunk_counter,
                )
            chunk_counter += 1

    try:
        handle = await sandbox.pty.create(cols=inp.cols, rows=inp.rows)
        await asyncio.sleep(inp.initial_wait_ms / 1000)

        output_task = asyncio.create_task(_collect_output())
        for cmd in inp.commands:
            await sandbox.pty.send_stdin(handle.pid, (cmd + "\n").encode())
            await asyncio.sleep(inp.between_cmd_ms / 1000)

        try:
            await asyncio.wait_for(output_task, timeout=inp.timeout)
        except asyncio.TimeoutError:
            output_task.cancel()
            return json.dumps(
                {
                    "output": "".join(full_output),
                    "sandbox_id": sid,
                    "mode": mode,
                    "commands_sent": len(inp.commands),
                    "streamed_chunks": chunk_counter,
                    "error": "PTY session timed out",
                }
            )

        return json.dumps(
            {
                "output": "".join(full_output),
                "sandbox_id": sid,
                "mode": mode,
                "commands_sent": len(inp.commands),
                "streamed_chunks": chunk_counter,
                "error": None,
            }
        )
    except Exception as exc:  # noqa: BLE001
        logger.error("sandbox_pty_run_failed", sandbox_id=sid, error=str(exc))
        return json.dumps({"error": str(exc), "sandbox_id": sid, "mode": mode})
    finally:
        if mode == "per_call":
            try:
                await sandbox.kill()
            except Exception:  # noqa: BLE001
                logger.warning("sandbox_pty_kill_failed_in_finally", sandbox_id=sid)


# ---------------------------------------------------------------------------
# StructuredTool factory
# ---------------------------------------------------------------------------


def create_sandbox_tools() -> list[StructuredTool]:
    """Return the four sandbox StructuredTools.

    Call only when E2B_API_KEY is configured.
    """
    from app.sse.tool_presentation import get_tool_rule

    def _desc(name: str, fallback: str) -> str:
        rule = get_tool_rule(name)
        return str(rule.description).strip() if rule and rule.description else fallback

    async def _run_create(
        template: str | None = None,
        env_vars: dict[str, str] | None = None,
        metadata: str | None = None,
    ) -> str:
        return await _sandbox_create(template, env_vars, metadata)

    async def _run_destroy(sandbox_id: str) -> str:
        return await _sandbox_destroy(sandbox_id)

    async def _run_sandbox_run(**kwargs: Any) -> str:
        return await _sandbox_run(SandboxRunInput(**kwargs))

    async def _run_pty(**kwargs: Any) -> str:
        return await _sandbox_pty_run(SandboxPtyInput(**kwargs))

    return [
        StructuredTool.from_function(
            coroutine=_run_create,
            name="sandbox_create",
            description=_desc(
                "sandbox_create",
                "Create an isolated E2B sandbox for dynamic malware/script analysis. "
                "Returns sandbox_id for session-level reuse.",
            ),
            args_schema=SandboxCreateInput,
        ),
        StructuredTool.from_function(
            coroutine=_run_destroy,
            name="sandbox_destroy",
            description=_desc(
                "sandbox_destroy",
                "Destroy an E2B sandbox created by sandbox_create. "
                "Always call this when a session-level sandbox is no longer needed.",
            ),
            args_schema=SandboxDestroyInput,
        ),
        StructuredTool.from_function(
            coroutine=_run_sandbox_run,
            name="sandbox_run",
            description=_desc(
                "sandbox_run",
                "Execute a shell command inside an isolated E2B sandbox. "
                "Omit sandbox_id for one-shot per-call mode (safest). "
                "Provide sandbox_id for session reuse. "
                "Set stream_to_sse=true to get real-time stdout/stderr in the UI.",
            ),
            args_schema=SandboxRunInput,
        ),
        StructuredTool.from_function(
            coroutine=_run_pty,
            name="sandbox_pty_run",
            description=_desc(
                "sandbox_pty_run",
                "Run an interactive PTY session inside a sandbox, sending a list of commands "
                "sequentially and collecting all output. Streams output to SSE by default. "
                "Use for interactive programs (REPLs, programs that require a tty).",
            ),
            args_schema=SandboxPtyInput,
        ),
    ]
