"""Audit logging for the binary analysis system.

This module implements NFR-06 (audit-chain completeness) by providing:

1. A ``contextvars.ContextVar``-based ``analysis_id`` that propagates
   correctly across concurrent asyncio tasks, threads, and ``asyncio.gather``
   fan-outs — each analysis task sees its own UUID.

2. Five structured-logging helpers that append a single JSON line to
   ``<log_dir>/<analysis_id>.audit.jsonl`` on every call.

**Red line (§6.2):** raw sample bytes MUST NOT appear in any log entry.
All helpers accept only structured / textual arguments.
"""

from __future__ import annotations

import json
import os
from collections.abc import Generator
from contextlib import contextmanager
from contextvars import ContextVar
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

# Module-level ContextVar — each concurrent task gets its own copy.
_analysis_id_var: ContextVar[str] = ContextVar("analysis_id", default="")

# Default audit log directory (overridden by Settings.log_dir at runtime).
_DEFAULT_LOG_DIR = Path(os.environ.get("BINARY_ANALYSIS_LOG_DIR", "logs"))


def current_analysis_id() -> str:
    """Return the ``analysis_id`` bound to the current execution context.

    Returns:
        The UUID string set by the nearest enclosing :func:`analysis_context`
        block, or an empty string when called outside any context.
    """
    return _analysis_id_var.get()


@contextmanager
def analysis_context(
    analysis_id: str, *, log_dir: Path | None = None
) -> Generator[str, None, None]:
    """Bind ``analysis_id`` to the current task context for the duration of the block.

    The binding is scoped to the current asyncio task / thread via
    ``contextvars.ContextVar``, so concurrent analyses do not interfere with
    each other.

    Args:
        analysis_id: UUID string identifying the analysis session.
        log_dir: Directory where audit JSONL files are written.  Defaults to
            ``Settings.log_dir`` when ``None``.

    Yields:
        The same ``analysis_id`` for convenience.
    """
    token = _analysis_id_var.set(analysis_id)
    try:
        yield analysis_id
    finally:
        _analysis_id_var.reset(token)


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _resolve_log_dir(log_dir: Path | None) -> Path:
    """Return the effective audit log directory, creating it if necessary."""
    effective = log_dir if log_dir is not None else _DEFAULT_LOG_DIR
    effective.mkdir(parents=True, exist_ok=True)
    return effective


def _audit_path(log_dir: Path) -> Path:
    """Return the JSONL file path for the current analysis."""
    aid = current_analysis_id()
    return log_dir / f"{aid}.audit.jsonl"


def _write_entry(
    event_type: str, payload: dict[str, Any], *, log_dir: Path | None = None
) -> None:
    """Append one JSON line to the current analysis's audit file.

    Args:
        event_type: Discriminator string (e.g. ``"tool_call"``).
        payload: Additional fields to merge into the log entry.
        log_dir: Override for the audit directory; falls back to the env-var
            default when ``None``.
    """
    entry: dict[str, Any] = {
        "analysis_id": current_analysis_id(),
        "timestamp_iso": datetime.now(UTC).isoformat(),
        "event_type": event_type,
        **payload,
    }
    resolved = _resolve_log_dir(log_dir)
    with _audit_path(resolved).open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(entry, ensure_ascii=False) + "\n")


# ---------------------------------------------------------------------------
# Public logging functions  (NFR-06 / §6.2)
# ---------------------------------------------------------------------------


def log_tool_call(
    tool_name: str,
    args: dict[str, Any],
    result: Any,
    duration_ms: float,
    *,
    success: bool = True,
    error_code: str | None = None,
    log_dir: Path | None = None,
) -> None:
    """Record a single tool invocation to the audit log.

    Callers must ensure that ``args`` and ``result`` contain NO sample bytes —
    only structured / textual data derived from the sample (§6.2 red line).

    Args:
        tool_name: Canonical name of the tool (e.g. ``"FileIdentifyTool"``).
        args: Tool input arguments (structured, no raw bytes).
        result: Tool output (structured summary, no raw bytes).
        duration_ms: Wall-clock duration of the call in milliseconds.
        success: Whether the call completed without error.
        error_code: If ``success`` is ``False``, the domain error code
            (e.g. ``"TOOL_TIMEOUT"``).
        log_dir: Override for the audit directory.
    """
    _write_entry(
        "tool_call",
        {
            "tool_name": tool_name,
            "args": args,
            "result": result,
            "duration_ms": duration_ms,
            "success": success,
            "error_code": error_code,
        },
        log_dir=log_dir,
    )


def log_llm_request(
    model: str,
    stage: str,
    prompt_tokens: int,
    completion_tokens: int,
    duration_ms: float,
    *,
    success: bool = True,
    error_code: str | None = None,
    log_dir: Path | None = None,
) -> None:
    """Record an LLM request/response pair to the audit log.

    Args:
        model: LLM model identifier (e.g. ``"claude-opus-4-5"``).
        stage: Analysis stage label (e.g. ``"quick_scan"``, ``"deep_analysis"``).
        prompt_tokens: Number of tokens in the prompt.
        completion_tokens: Number of tokens in the completion.
        duration_ms: Wall-clock duration of the LLM call in milliseconds.
        success: Whether the call completed without error.
        error_code: Domain error code when ``success`` is ``False``.
        log_dir: Override for the audit directory.
    """
    _write_entry(
        "llm_request",
        {
            "model": model,
            "stage": stage,
            "prompt_tokens": prompt_tokens,
            "completion_tokens": completion_tokens,
            "duration_ms": duration_ms,
            "success": success,
            "error_code": error_code,
        },
        log_dir=log_dir,
    )


def log_sandbox_lifecycle(
    event: str,
    sandbox_id: str | None,
    template: str | None,
    *,
    duration_ms: float | None = None,
    fallback_used: bool = False,
    kill_status: str | None = None,
    error_code: str | None = None,
    log_dir: Path | None = None,
) -> None:
    """Record a sandbox lifecycle event (create / kill / fallback) to the audit log.

    Args:
        event: Lifecycle event name (``"create"``, ``"kill"``, ``"fallback"``).
        sandbox_id: E2B sandbox identifier; ``None`` when using the local
            subprocess fallback.
        template: E2B template identifier (e.g. ``"binary-analysis-ubuntu-2204"``).
        duration_ms: Duration of the create/kill operation in milliseconds.
        fallback_used: ``True`` when the local subprocess fallback was activated
            instead of the remote sandbox (ADR-16).
        kill_status: Result of the kill operation (``"ok"`` / ``"timeout"`` /
            ``"error"``).
        error_code: Domain error code when the operation failed.
        log_dir: Override for the audit directory.
    """
    _write_entry(
        "sandbox_lifecycle",
        {
            "event": event,
            "sandbox_id": sandbox_id,
            "template": template,
            "duration_ms": duration_ms,
            "fallback_used": fallback_used,
            "kill_status": kill_status,
            "error_code": error_code,
        },
        log_dir=log_dir,
    )


def log_indicator_write(
    indicator_id: str,
    bucket: str,
    kind: str,
    severity: str,
    source_fr: str,
    *,
    log_dir: Path | None = None,
) -> None:
    """Record an Indicator being written to the evidence chain.

    Args:
        indicator_id: Globally unique Indicator ID (IR-12).
        bucket: Target evidence-chain bucket (e.g. ``"file_meta"``,
            ``"strings_iocs"``).
        kind: ``"fact"`` for tool-derived data; ``"inference"`` for LLM
            inferences (ADR-03).
        severity: Severity level (``"INFO"`` / ``"WARNING"`` / ``"CRITICAL"``).
        source_fr: Originating functional requirement (e.g. ``"FR-01"``).
        log_dir: Override for the audit directory.
    """
    _write_entry(
        "indicator_write",
        {
            "indicator_id": indicator_id,
            "bucket": bucket,
            "kind": kind,
            "severity": severity,
            "source_fr": source_fr,
        },
        log_dir=log_dir,
    )


def log_skill_read(
    skill_name: str,
    skill_path: str,
    *,
    log_dir: Path | None = None,
) -> None:
    """Record a LLM ``Read(skill_path)`` invocation to the audit log.

    This event is required by NFR-06 / §9.4 to enable post-hoc reconstruction
    of which skills were consulted during an analysis session.

    Args:
        skill_name: Canonical skill name as declared in ``SKILL.md``
            frontmatter (e.g. ``"reverse-engineering-malware-with-ghidra"``).
        skill_path: Relative path to the ``SKILL.md`` file.
        log_dir: Override for the audit directory.
    """
    _write_entry(
        "skill_read",
        {
            "skill_name": skill_name,
            "skill_path": skill_path,
        },
        log_dir=log_dir,
    )
