"""BashTool — whitelisted CLI execution inside the sandbox (C7 / FR-04~07).

This Tool is one of the three "primitive" tools described in DESIGN.md
§2.3.2: skill workflows drive it to invoke specific CLIs (``analyzeHeadless``,
``upx``, ``yara``, ``floss``, ``diec``, ``strings``, ``ssdeep``, ``tlsh`` and
the ``python3`` interpreter) inside the per-analysis E2B sandbox (or the
subprocess fallback when :func:`binary_analysis.config.settings` has
``use_e2b=False``).

Hard invariants enforced here:

1. **Command whitelist (C7-AC1 / IR-10)** — :func:`load_bash_whitelist`
   parses ``config/bash_whitelist.yaml`` on first use; any command whose
   ``posixpath.basename(argv[0])`` is not in the whitelist raises
   :class:`~errors.ToolSchemaInvalid` with
   ``reason='command_not_whitelisted'`` **before** touching the sandbox.
2. **Timeout + stdout/stderr truncation (C7-AC2 / IR-10)** — execution is
   delegated to :meth:`~binary_analysis.sandbox.client.SandboxClient.exec`
   which kills the process on timeout; we then cap stdout and stderr at
   64 KiB (64 * 1024 bytes) so Agent prompts never balloon.
3. **Audit logging (C7-AC5 / NFR-06)** — every call, whether successful,
   timed out, rejected, or crashed, is recorded via
   :func:`~audit.log_tool_call`.

The Tool is **async-only**: the underlying :class:`SandboxClient` Protocol
is async.  Invoke via :meth:`~langchain_core.tools.BaseTool.ainvoke`.
"""

from __future__ import annotations

import posixpath
import re
import shlex
import time
from functools import lru_cache
from pathlib import Path
from typing import Any

import yaml
from langchain_core.tools import BaseTool
from pydantic import BaseModel, ConfigDict, Field

from audit import log_tool_call
from errors import ToolSchemaInvalid
from sandbox.client import ExecResult, SandboxClient
from sandbox.registry import get_session

# ---------------------------------------------------------------------------
# Whitelist loader
# ---------------------------------------------------------------------------

_DEFAULT_WHITELIST_PATH: Path = (
    Path(__file__).resolve().parents[1] / "config" / "bash_whitelist.yaml"
)

#: Hard ceiling on the byte count returned to the Agent for each stream.
#: 64 KiB matches the DESIGN.md §2.3.2 "stdout/stderr truncation" note.
DEFAULT_STREAM_LIMIT_BYTES: int = 64 * 1024

#: Secondary cap applied *after* :data:`DEFAULT_STREAM_LIMIT_BYTES` when a
#: stream was truncated at the sandbox boundary.  The truncated 64 KiB
#: payload is compressed into a head/tail preview before being handed to
#: the Agent so a single ``bash`` ToolMessage never exceeds
#: ~``DEFAULT_LLM_PREVIEW_HEAD_BYTES`` + ``DEFAULT_LLM_PREVIEW_TAIL_BYTES``
#: + a small marker (~100 bytes) per stream.  The goal is to stay *well
#: below* :class:`~deepagents.middleware.filesystem.FilesystemMiddleware`'s
#: default ``tool_token_limit_before_evict * NUM_CHARS_PER_TOKEN`` ≈
#: 80 000 chars eviction threshold so the middleware never has to spill
#: oversized tool payloads onto the filesystem (which, in the absence of
#: a correctly-routed ``/large_tool_results/`` backend, would pollute the
#: curated ``skills/`` tree).
#:
#: This does **not** weaken the SPEC C7-AC2 contract ("stdout/stderr
#: truncated to ≤ 64 KiB") — the 64 KiB cap is still enforced at the
#: sandbox boundary; this is an additional, tighter LLM-view summary that
#: kicks in only when the first cap actually fired.
DEFAULT_LLM_PREVIEW_HEAD_BYTES: int = 4 * 1024
DEFAULT_LLM_PREVIEW_TAIL_BYTES: int = 2 * 1024

#: Default per-call timeout (seconds).  Callers may override via the Tool
#: input.  IR-10 requires a bound; the spec does not pin a number, so we
#: pick a conservative 60 s that stays well under ``NFR-02`` five-minute
#: total budget.
DEFAULT_TIMEOUT_SECONDS: float = 60.0


def _validate_whitelist_entries(entries: list[str], *, source: Path | str) -> None:
    """Reject empty or shell-metachar-bearing whitelist entries.

    Every entry must be a bare executable basename (no ``/``, no spaces,
    no shell metacharacters).  Any deviation is a configuration bug that
    must fail loud at startup rather than silently widen the allow-list.

    Args:
        entries: The raw string list parsed from YAML.
        source: Path or identifier used in the error message.

    Raises:
        ToolSchemaInvalid: If any entry violates the shape rules.
    """
    forbidden_chars = set("/ \t\n\"'\\;&|<>`$()*?[]{}")
    for entry in entries:
        if not entry or not isinstance(entry, str):
            msg = (
                f"bash_whitelist entry is empty or not a string: {entry!r} "
                f"(source={source!s})"
            )
            raise ToolSchemaInvalid(
                msg, details={"reason": "whitelist_entry_invalid", "entry": entry}
            )
        if any(ch in forbidden_chars for ch in entry):
            msg = (
                f"bash_whitelist entry contains forbidden characters: {entry!r} "
                f"(source={source!s}); only bare executable basenames are allowed"
            )
            raise ToolSchemaInvalid(
                msg, details={"reason": "whitelist_entry_invalid", "entry": entry}
            )


def load_bash_whitelist(path: Path | None = None) -> frozenset[str]:
    """Parse the YAML command whitelist and return the frozen set of entries.

    The first successful load of the default path is cached via
    :func:`_cached_default_whitelist`; passing an explicit ``path`` bypasses
    the cache so tests can point at a fixture file.

    Args:
        path: Override for the YAML location.  ``None`` → default shipped
            at ``examples/binary_analysis/config/bash_whitelist.yaml``.

    Returns:
        A :class:`frozenset` of allowed executable basenames.

    Raises:
        ToolSchemaInvalid: If the file is missing, malformed, lacks a
            top-level ``commands`` list, or contains invalid entries.
    """
    if path is None:
        return _cached_default_whitelist()
    return _load_whitelist_from_path(path)


@lru_cache(maxsize=1)
def _cached_default_whitelist() -> frozenset[str]:
    """Cached loader for the shipped whitelist YAML."""
    return _load_whitelist_from_path(_DEFAULT_WHITELIST_PATH)


def _load_whitelist_from_path(path: Path) -> frozenset[str]:
    """Uncached YAML parse + schema validation used by both loaders."""
    if not path.is_file():
        msg = f"bash_whitelist.yaml not found at {path!s}"
        raise ToolSchemaInvalid(
            msg, details={"reason": "whitelist_missing", "path": str(path)}
        )
    with path.open("r", encoding="utf-8") as fh:
        parsed = yaml.safe_load(fh)
    if not isinstance(parsed, dict) or "commands" not in parsed:
        msg = f"bash_whitelist.yaml must contain a top-level 'commands' list: {path!s}"
        raise ToolSchemaInvalid(
            msg, details={"reason": "whitelist_schema_invalid", "path": str(path)}
        )
    entries = parsed["commands"]
    if not isinstance(entries, list) or not entries:
        msg = f"bash_whitelist.yaml 'commands' must be a non-empty list: {path!s}"
        raise ToolSchemaInvalid(
            msg, details={"reason": "whitelist_schema_invalid", "path": str(path)}
        )
    _validate_whitelist_entries(entries, source=path)
    return frozenset(entries)


# ---------------------------------------------------------------------------
# Command parsing + whitelist check
# ---------------------------------------------------------------------------


def _tokenise_cmd(cmd: str | list[str]) -> list[str]:
    """Tokenise ``cmd`` the same way :class:`SubprocessBackend` does.

    Args:
        cmd: Either a shell string (tokenised by :mod:`shlex`) or an
            explicit argv list.

    Returns:
        A non-empty list of argv tokens.

    Raises:
        ToolSchemaInvalid: If ``cmd`` is empty or tokenisation fails.
    """
    if isinstance(cmd, str):
        stripped = cmd.strip()
        if not stripped:
            msg = "bash command is empty"
            raise ToolSchemaInvalid(
                msg, details={"reason": "empty_command", "cmd": cmd}
            )
        try:
            tokens = shlex.split(stripped)
        except ValueError as exc:
            msg = f"bash command failed shell-tokenisation: {exc}"
            raise ToolSchemaInvalid(
                msg, details={"reason": "tokenise_failed", "cmd": cmd}
            ) from exc
    else:
        tokens = list(cmd)
    if not tokens:
        msg = "bash command argv is empty"
        raise ToolSchemaInvalid(msg, details={"reason": "empty_command", "cmd": cmd})
    return tokens


#: Standalone tokens produced by :func:`shlex.split` when the user wrote
#: shell syntax (pipes, lists, redirections) without realising ``bash`` is
#: argv-only.  Catching these avoids bogus errors like ``strings: '|': No
#: such file`` where ``|`` was passed as a path argument.
_FORBIDDEN_SHELL_OPERATOR_TOKENS: frozenset[str] = frozenset(
    {
        "|",
        "&&",
        "||",
        ";",
        "&",
        ">",
        "<",
        ">>",
        "<<",
        ">&",
        "<&",
        "|&",
        "2>&1",
        "1>&2",
        "2>&2",
        "0<&1",
        "&>",
        "&>>",
    }
)

#: File-descriptor redirects that appear as a single argv token, e.g.
#: ``2>out``, ``1>>log``, ``2>&1`` (last also listed explicitly above).
_FD_REDIRECT_TOKEN: re.Pattern[str] = re.compile(
    r"^(?:\d+>>?|\d+<<?|\d*>&\d+|\d*<&\d+|>&\d+|<&\d+)$"
)


def _first_unsupported_shell_token(tokens: list[str]) -> str | None:
    """Return the first argv token that implies unsupported shell syntax.

    ``BashTool`` executes ``tokens`` via ``exec``-style APIs — there is no
    ``/bin/sh``.  Operators such as ``|`` therefore become literal arguments
    unless we reject them up front.

    Args:
        tokens: Tokenised argv (from :func:`_tokenise_cmd`).

    Returns:
        The first offending token, or ``None`` when the argv looks argv-safe.
    """
    for tok in tokens:
        if tok in _FORBIDDEN_SHELL_OPERATOR_TOKENS:
            return tok
        if _FD_REDIRECT_TOKEN.fullmatch(tok):
            return tok
        # e.g. ``2>err`` / ``1>>log`` — one token, not matched by the fd-only pattern.
        if re.match(r"^\d+[<>]{1,2}\S", tok):
            return tok
    return None


def _ensure_whitelisted(tokens: list[str], whitelist: frozenset[str]) -> str:
    """Verify the first argv token's basename is in ``whitelist``.

    Args:
        tokens: Tokenised argv list.
        whitelist: Allowed executable basenames.

    Returns:
        The matched basename (used for audit-log labelling).

    Raises:
        ToolSchemaInvalid: When the basename is not in ``whitelist``.
    """
    binary = posixpath.basename(tokens[0])
    if binary not in whitelist:
        msg = (
            f"command {tokens[0]!r} is not in bash whitelist; "
            f"allowed binaries: {sorted(whitelist)!r}. "
            "For sample keyword searches, use `strings`/`floss` for bounded "
            "string extraction or `python_exec` for structured, sanitized "
            "byte scans; shell filters such as `grep` are intentionally "
            "unavailable."
        )
        raise ToolSchemaInvalid(
            msg,
            details={
                "reason": "command_not_whitelisted",
                "command": tokens[0],
                "binary": binary,
            },
        )
    return binary


def _ghidra_priority_list_path(tokens: list[str]) -> str | None:
    """Return the priority-list path from a sanctioned Ghidra invocation.

    The FR-07 contract routes `analyzeHeadless` through `DecompileByList.py`;
    its first script argument is the machine-readable priority file that must
    already exist before Ghidra starts.
    """
    if posixpath.basename(tokens[0]) != "analyzeHeadless":
        return None
    try:
        post_idx = tokens.index("-postScript")
    except ValueError:
        return None
    if len(tokens) <= post_idx + 2:
        return None
    script_name = posixpath.basename(tokens[post_idx + 1])
    if script_name != "DecompileByList.py":
        return None
    return tokens[post_idx + 2]


# ---------------------------------------------------------------------------
# Output truncation
# ---------------------------------------------------------------------------


def _truncate(text: str, limit: int) -> tuple[str, bool]:
    """Return ``text`` clipped to ``limit`` bytes (UTF-8) plus a truncation flag.

    The cap is applied on the encoded byte length because DESIGN.md §2.3.2
    expresses the limit in bytes, not code points.  When the cap is hit we
    trim the tail until the remaining bytes form a valid UTF-8 sequence so
    the returned string never ends mid-multibyte-codepoint.

    Args:
        text: The raw captured stream.
        limit: Byte-count ceiling (``<= 0`` disables truncation).

    Returns:
        Tuple of ``(truncated_text, truncated_flag)``.
    """
    if limit <= 0:
        return text, False
    encoded = text.encode("utf-8")
    if len(encoded) <= limit:
        return text, False
    cut = encoded[:limit]
    return cut.decode("utf-8", errors="ignore"), True


def _preview(
    text: str,
    *,
    head_bytes: int = DEFAULT_LLM_PREVIEW_HEAD_BYTES,
    tail_bytes: int = DEFAULT_LLM_PREVIEW_TAIL_BYTES,
    original_bytes: int | None = None,
    stream_name: str = "stdout",
) -> str:
    """Compress an already-truncated stream into a head+tail preview.

    Called *after* :func:`_truncate` has clipped ``text`` to
    :data:`DEFAULT_STREAM_LIMIT_BYTES`, this trims it further so the
    Agent-visible payload stays well below
    :class:`~deepagents.middleware.filesystem.FilesystemMiddleware`'s
    default 80 000-char eviction threshold.  Without this compression a
    single ``strings <binary>`` call routinely fills both stdout (64 KiB)
    and stderr (64 KiB) to the cap, producing a ~130 KiB ToolMessage that
    *always* trips eviction — which, if ``/large_tool_results/`` is
    mis-routed (regression of ``analyst_graph.py`` / ``langgraph_entry.py``),
    pollutes the curated skills tree on disk.

    An elision marker is emitted in the middle so the Agent can tell
    roughly how much data it is missing and decide whether to re-run the
    command with a narrower scope (``strings -n 8``) or redirect to a
    file and read it with :class:`FileReadTool`.

    Args:
        text: Stream content already trimmed to the sandbox byte cap.
        head_bytes: UTF-8 byte budget for the head slice.
        tail_bytes: UTF-8 byte budget for the tail slice.
        original_bytes: Byte count of the *pre-sandbox-truncation* stream,
            used to annotate how much data was dropped overall.  When
            ``None`` the marker only mentions the preview-vs-truncated
            delta.
        stream_name: Label used in the marker (``"stdout"`` / ``"stderr"``).

    Returns:
        Either ``text`` unchanged (when it already fits in
        ``head_bytes + tail_bytes``) or a ``"<head>\\n... <marker>
        ...\\n<tail>"`` summary.  Head/tail slices are re-decoded with
        ``errors='ignore'`` so multibyte sequences never appear mid-codepoint.
    """
    encoded = text.encode("utf-8")
    visible_budget = head_bytes + tail_bytes
    if len(encoded) <= visible_budget:
        return text

    head = encoded[:head_bytes].decode("utf-8", errors="ignore")
    tail = encoded[-tail_bytes:].decode("utf-8", errors="ignore")
    elided_bytes = len(encoded) - head_bytes - tail_bytes
    if original_bytes is not None and original_bytes > len(encoded):
        extra = (
            f"; sandbox already dropped "
            f"{original_bytes - len(encoded)} bytes before this preview"
        )
    else:
        extra = ""
    marker = (
        f"\n... [{stream_name} preview: "
        f"head={head_bytes}B + tail={tail_bytes}B, "
        f"elided={elided_bytes}B{extra}] ...\n"
    )
    return f"{head}{marker}{tail}"


# ---------------------------------------------------------------------------
# Tool implementation
# ---------------------------------------------------------------------------


class BashInput(BaseModel):
    """Input schema for :class:`BashTool`."""

    model_config = ConfigDict(extra="forbid")

    cmd: str | list[str] = Field(
        description="Command line to execute; either a shell string or an argv list.",
    )
    analysis_id: str = Field(
        description="UUID identifying the analysis whose sandbox should run the command.",
    )
    timeout_seconds: float | None = Field(
        default=None,
        description="Optional per-call timeout override; defaults to DEFAULT_TIMEOUT_SECONDS.",
    )
    cwd: str | None = Field(
        default=None,
        description="Optional sandbox-side cwd; must live under /workspace/<analysis_id>/.",
    )


class BashTool(BaseTool):
    """Whitelisted CLI execution inside the per-analysis sandbox.

    Args:
        sandbox_client: Any concrete backend implementing
            :class:`~sandbox.client.SandboxClient`.
        whitelist: Override for the YAML-derived command whitelist.
            Useful for tests; production callers should leave this ``None``
            so the shipped ``config/bash_whitelist.yaml`` is used.
        default_timeout_seconds: Fallback timeout when the Tool input omits
            ``timeout_seconds`` (IR-10 enforcement).
        stdout_limit_bytes: stdout byte cap for the Agent-visible payload.
        stderr_limit_bytes: stderr byte cap for the Agent-visible payload.
    """

    name: str = "bash"
    description: str = (
        "Execute a whitelisted CLI inside the per-analysis sandbox. "
        "Allowed binaries: analyzeHeadless, upx, floss, diec, yara, strings, "
        "sha256sum, file, ssdeep, tlsh, python3, ls, pwd. "
        "Commands not in the whitelist are rejected before reaching the sandbox.\n"
        "\n"
        "IMPORTANT — this is NOT a shell; `cmd` is parsed with `shlex.split` "
        "and executed as argv via SandboxClient.exec. Shell metacharacters such "
        "as `|`, `&&`, `;`, `>`, `<`, `$(...)`, backticks, globs, and "
        "redirections DO NOT work: known shell operators are rejected before "
        "exec with `reason=shell_operators_not_supported`; other metacharacters "
        "may still be passed literally and confuse the target binary.\n"
        "\n"
        "Do NOT call non-whitelisted readers or filters such as `grep`, `find`, "
        "`head`, `tail`, `cat`, `xxd`, `hexdump`, or `od` on `sample.bin`. "
        "To look for strings such as `powershell`, first use `strings -a -n 6` "
        "or `floss` with bounded output, then classify and sanitize matches via "
        "`python_exec`. For precise keyword searches, use `python_exec` to scan "
        "bytes and return only structured, bounded, sanitized snippets or counts "
        "(for example: offsets, match counts, and printable context limits), "
        "never raw binary context.\n"
        "\n"
        "Output handling: stdout and stderr are first truncated at the sandbox "
        "boundary to 64 KiB each (IR-10 / SPEC C7-AC2). If that cap fires, the "
        "tool ALSO returns only a head+tail preview (~6 KiB) in `stdout`/"
        "`stderr` and sets `stdout_preview_only=True` / `stderr_preview_only="
        "True`; the full 64 KiB payload is NOT preserved in the tool result. "
        "For commands that are expected to emit lots of output (e.g. `strings`, "
        "`floss`, `analyzeHeadless`), the recommended pattern is:\n"
        "  1. Call the binary with a flag that narrows the result "
        "(e.g. `strings -n 8 /workspace/<aid>/sample`, `floss --no-static-strings`).\n"
        "  2. If you still need the complete stream, write the output to a file "
        "first via a binary that accepts `-o`/`--output` "
        "(e.g. `yara -f rules.yar sample -o /workspace/<aid>/yara.out`), then "
        "read the file in pages with the `file_read` tool (offset + limit). "
        "Shell redirection with `>` is NOT supported.\n"
        "  3. Treat the `preview_only` flag as authoritative: if it is true, "
        "do not assume the middle of the output is empty — rerun with a "
        "narrower scope or paginate via `file_read` instead.\n"
        "\n"
        "SPECIAL CASE — upx (FR-05): only use `upx` through the "
        "`analyzing-packed-malware-with-upx-unpacker` skill. The sanctioned "
        "commands are `upx -t /workspace/<aid>/sample.bin` and, only after "
        "the skill's evidence gates pass, `upx -d /workspace/<aid>/sample.bin "
        "-o /workspace/<aid>/unpacked/<name>.bin`. Do not try UPX on "
        "commercial or non-UPX packers; write an `unpack_result` fact instead.\n"
        "\n"
        "SPECIAL CASE — analyzeHeadless (Ghidra, FR-07): do NOT rely on "
        "stdout for decompilation output. `analyzeHeadless` in its default "
        "whole-binary mode floods stdout well past the 64 KiB cap and "
        "violates FR-07 AC-7 (no per-function timeout) + IR-05 (priority "
        "BEFORE decompile). The ONLY sanctioned invocation is via the "
        "`ghidra-priority-queue-workflow` skill: before calling `bash`, "
        "use `python_exec` to create a non-empty `decompile_priority.txt` "
        "file and write a matching `decompile_priority` fact into the "
        "`disassembly` bucket. Do not create the priority file with `bash`, "
        "`printf`, `echo`, `tee`, or shell redirection; this tool rejects "
        "`DecompileByList.py` invocations when `<priority_list_path>` is "
        "missing or empty. Then call `analyzeHeadless <proj> <name> "
        "-import <sample> -scriptPath /opt/ghidra/scripts "
        "-postScript DecompileByList.py "
        "<priority_list_path> <output_dir> <per_fn_timeout_s> "
        "-deleteProject -readOnly`. Per-function `.c` files and "
        "`manifest.json` land under `<output_dir>`; read them via "
        "`file_read` (offset/limit). stdout from this command is a "
        "single summary line by design — if you see a truncation flag "
        "there, the command was wrong (likely missing the postScript)."
    )
    args_schema: type[BaseModel] = BashInput

    # Structural Protocol — store as ``Any`` so Pydantic does not try to
    # build a schema for it (same pattern as FileIdentifyTool).
    sandbox_client: Any
    whitelist: frozenset[str] | None = None
    default_timeout_seconds: float = DEFAULT_TIMEOUT_SECONDS
    stdout_limit_bytes: int = DEFAULT_STREAM_LIMIT_BYTES
    stderr_limit_bytes: int = DEFAULT_STREAM_LIMIT_BYTES
    stdout_preview_head_bytes: int = DEFAULT_LLM_PREVIEW_HEAD_BYTES
    stdout_preview_tail_bytes: int = DEFAULT_LLM_PREVIEW_TAIL_BYTES
    stderr_preview_head_bytes: int = DEFAULT_LLM_PREVIEW_HEAD_BYTES
    # stderr usually carries less actionable content; keep the tail short.
    stderr_preview_tail_bytes: int = 1024

    model_config = {"arbitrary_types_allowed": True}

    def _run(self, **kwargs: Any) -> Any:  # type: ignore[override]  # pragma: no cover
        msg = (
            "BashTool is async-only; invoke via .ainvoke(...) rather than .invoke(...)."
        )
        raise NotImplementedError(msg)

    def _schema_error_result(
        self,
        exc: ToolSchemaInvalid,
        *,
        start: float,
        tokens: list[str],
        timeout: float,
        cwd: str | None,
        analysis_id: str,
    ) -> dict[str, Any]:
        """Return a recoverable ToolMessage payload for LLM-correctable errors."""
        wall_ms = (time.perf_counter() - start) * 1000.0
        log_tool_call(
            tool_name=self.name,
            args={
                "cmd": tokens,
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
                "binary": exc.details.get("binary"),
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
        inp = BashInput(**kwargs)
        whitelist = (
            self.whitelist if self.whitelist is not None else load_bash_whitelist()
        )
        timeout = inp.timeout_seconds or self.default_timeout_seconds

        start = time.perf_counter()
        try:
            tokens = _tokenise_cmd(inp.cmd)
        except ToolSchemaInvalid as exc:
            return self._schema_error_result(
                exc,
                start=start,
                tokens=[],
                timeout=timeout,
                cwd=inp.cwd,
                analysis_id=inp.analysis_id,
            )
        bad_shell = _first_unsupported_shell_token(tokens)
        if bad_shell is not None:
            wall_ms = (time.perf_counter() - start) * 1000.0
            log_tool_call(
                tool_name=self.name,
                args={
                    "cmd": tokens,
                    "timeout_seconds": timeout,
                    "cwd": inp.cwd,
                    "analysis_id": inp.analysis_id,
                },
                result={
                    "exit_code": None,
                    "timed_out": False,
                    "duration_ms": 0.0,
                    "stdout_truncated": False,
                    "stderr_truncated": False,
                    "stdout_bytes": 0,
                    "stderr_bytes": 0,
                    "reason": "shell_operators_not_supported",
                    "token": bad_shell,
                },
                duration_ms=wall_ms,
                success=False,
                error_code="TOOL_SCHEMA_INVALID",
            )
            return {
                "ok": False,
                "error_code": "TOOL_SCHEMA_INVALID",
                "reason": "shell_operators_not_supported",
                "message": (
                    "bash is not a shell: pipes, redirections, and command "
                    "lists are not executed. Remove shell operators from `cmd` "
                    "and invoke one whitelisted binary per call, or use "
                    "`python_exec` to compose logic (e.g. subprocess.run of a "
                    "single whitelisted CLI and truncate output in Python)."
                ),
                "details": {
                    "reason": "shell_operators_not_supported",
                    "token": bad_shell,
                    "cmd": tokens,
                },
            }
        try:
            binary = _ensure_whitelisted(tokens, whitelist)
        except ToolSchemaInvalid as exc:
            # Surface whitelist violations as a structured tool result rather
            # than propagating the exception. A raise would escape the
            # LangGraph ToolNode and kill the agent loop (historically triggered
            # the api.py facts-only fallback, wasting the whole analysis on a
            # single LLM slip such as calling `find` or `grep`). Returning an
            # error dict lets the LLM observe the allowed list via ToolMessage
            # and retry with a whitelisted binary on the next step. The
            # underlying safety invariant is unchanged — no sandbox.exec() is
            # reached — and the audit log preserves the rejection with
            # `error_code="TOOL_SCHEMA_INVALID"`.
            return self._schema_error_result(
                exc,
                start=start,
                tokens=tokens,
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
                tokens=tokens,
                timeout=timeout,
                cwd=inp.cwd,
                analysis_id=inp.analysis_id,
            )

        client: SandboxClient = self.sandbox_client
        priority_path = _ghidra_priority_list_path(tokens)
        if priority_path is not None:
            try:
                priority_bytes = await client.download(session, priority_path)
            except Exception as exc:  # noqa: BLE001 - backend path/missing-file details vary
                msg = (
                    "`analyzeHeadless` with `DecompileByList.py` requires a "
                    "pre-existing non-empty decompile priority file. Run "
                    "`ghidra-priority-queue-workflow` Step 0 with `python_exec` "
                    "to write `decompile_priority.txt`; do not use `bash`, "
                    "`printf`, or shell redirection."
                )
                return self._schema_error_result(
                    ToolSchemaInvalid(
                        msg,
                        details={
                            "reason": "decompile_priority_file_missing",
                            "priority_list_path": priority_path,
                            "error_type": type(exc).__name__,
                        },
                    ),
                    start=start,
                    tokens=tokens,
                    timeout=timeout,
                    cwd=inp.cwd,
                    analysis_id=inp.analysis_id,
                )
            if not priority_bytes.strip():
                msg = (
                    "`analyzeHeadless` with `DecompileByList.py` requires a "
                    "non-empty decompile priority file. Re-run "
                    "`ghidra-priority-queue-workflow` Step 0 with `python_exec` "
                    "before invoking Ghidra."
                )
                return self._schema_error_result(
                    ToolSchemaInvalid(
                        msg,
                        details={
                            "reason": "decompile_priority_file_empty",
                            "priority_list_path": priority_path,
                        },
                    ),
                    start=start,
                    tokens=tokens,
                    timeout=timeout,
                    cwd=inp.cwd,
                    analysis_id=inp.analysis_id,
                )
        try:
            exec_result: ExecResult = await client.exec(
                session, tokens, timeout=timeout, cwd=inp.cwd
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
                    "cmd": tokens,
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
                    "binary": binary,
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
                    "binary": binary,
                    "analysis_id": inp.analysis_id,
                },
            }

        stdout_sandbox, stdout_truncated = _truncate(
            exec_result.stdout, self.stdout_limit_bytes
        )
        stderr_sandbox, stderr_truncated = _truncate(
            exec_result.stderr, self.stderr_limit_bytes
        )

        # Two-stage compression. Stage 1 (`_truncate`) is the C7-AC2 /
        # IR-10 sandbox cap on stream size. Stage 2 (`_preview`) is a
        # tighter LLM-view summary that only kicks in when stage 1 actually
        # truncated — otherwise small outputs like `sha256sum` / short
        # `file` runs pass through unchanged. The stage-2 step exists to
        # keep the total ToolMessage payload well below the 80 000-char
        # FilesystemMiddleware eviction threshold so oversized tool results
        # never spill onto disk (see ``/large_tool_results/`` routing in
        # ``analyst_graph.py`` and ``langgraph_entry.py``).
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
            "binary": binary,
        }

        log_tool_call(
            tool_name=self.name,
            args={
                "cmd": tokens,
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
                # Byte counts reflect the *Agent-visible* payload (post-preview),
                # not the sandbox-level 64 KiB cap; the latter can still be
                # inferred from ``stdout_truncated`` / ``stderr_truncated``.
                "stdout_bytes": len(stdout.encode("utf-8")),
                "stderr_bytes": len(stderr.encode("utf-8")),
                "binary": binary,
            },
            duration_ms=wall_ms,
            success=ok,
            error_code=None
            if ok
            else ("TOOL_TIMEOUT" if exec_result.timed_out else "TOOL_CRASH"),
        )
        return result


__all__ = [
    "DEFAULT_LLM_PREVIEW_HEAD_BYTES",
    "DEFAULT_LLM_PREVIEW_TAIL_BYTES",
    "DEFAULT_STREAM_LIMIT_BYTES",
    "DEFAULT_TIMEOUT_SECONDS",
    "BashInput",
    "BashTool",
    "load_bash_whitelist",
]
