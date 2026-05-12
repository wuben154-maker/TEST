"""Structured multi-format file read for security analysis (SReadFile common tool).

Reads user artifacts via the agent backend (virtual paths like /workspace/..., /uploads/...)
with encoding fallbacks, binary sniffing, and basic .eml parsing — without replacing read_file
for normal repo / skill file browsing.
"""

from __future__ import annotations

import base64
import binascii
import mimetypes
from email import policy
from email.parser import BytesParser
from pathlib import PurePosixPath
from typing import Any, Literal

from langchain.tools import ToolRuntime
from langchain_core.tools import StructuredTool
from pydantic import BaseModel, Field

from app._vendor.deepagents.backends.utils import _get_file_type

ContentKind = Literal["text", "binary", "email", "empty", "error"]
TextViewMode = Literal["window", "head_tail"]

# Extensions treated as binary regardless of UTF-8 decodability (mirrors common CLI expectations).
_BINARY_SUFFIXES: frozenset[str] = frozenset(
    {
        ".exe",
        ".dll",
        ".so",
        ".dylib",
        ".bin",
        ".dat",
        ".msi",
        ".scr",
        ".elf",
        ".zip",
        ".gz",
        ".7z",
        ".rar",
        ".tar",
        ".bz2",
        ".xz",
        ".wasm",
        ".class",
    }
)

_DEFAULT_MAX_BYTES = 2 * 1024 * 1024
_MAX_EMAIL_BODY_CHARS = 48_000
_MAX_LINE_CHARS = 8_000


class SReadFileInput(BaseModel):
    """Arguments exposed to the model (no runtime — injected separately)."""

    file_path: str = Field(
        description=(
            "Absolute virtual path to the artifact (e.g. /workspace/shell.php, /uploads/session/file.dat). "
            "Must start with / or use workspace/... or uploads/... prefix."
        ),
    )
    offset: int = Field(
        default=0,
        ge=0,
        description=(
            "0-based line offset into decoded text (window mode only; ignored for binary, .eml, and head_tail)."
        ),
    )
    limit: int = Field(
        default=500,
        ge=1,
        le=50_000,
        description=(
            "Text mode: when view_mode=window, max lines starting at offset. "
            "When view_mode=head_tail, max lines taken from the start AND from the end "
            "(each side gets up to `limit` lines; small files return the full text once)."
        ),
    )
    view_mode: TextViewMode = Field(
        default="window",
        description=(
            "Text decode only. `window`: contiguous slice [offset : offset+limit] (default). "
            "`head_tail`: security-oriented snapshot — first `limit` lines plus last `limit` lines "
            "in one response, with an omission marker if the middle was skipped; `offset` is ignored. "
            "Use for webshells / drops where payloads often sit at the end of a long file."
        ),
    )
    max_bytes: int = Field(
        default=_DEFAULT_MAX_BYTES,
        ge=1,
        le=16 * 1024 * 1024,
        description="Max raw bytes to load from storage for this call (cap before decode).",
    )
    hex_preview_bytes: int = Field(
        default=64,
        ge=0,
        le=512,
        description="If content is binary, include this many leading bytes as hex (0 to disable).",
    )


def _canonical_virtual_path(file_path: str) -> str | None:
    """Normalize UI/virtual spellings to backend routes.

    Stream scrub and copy-paste may show ``workspace/<file>`` (relative); the
    composite backend mounts lowercase ``/workspace/``. Reuse
    :func:`~app.backends.path_aliases.canonicalize_agent_path` for parity with
    :class:`~app.backends.path_aliases.PathAliasBackend`.
    """
    from app.backends.path_aliases import canonicalize_agent_path

    cleaned = (file_path or "").strip().replace("\\", "/")
    if not cleaned:
        return None

    low = cleaned.lower()

    if low.startswith("uploads/"):
        return "/uploads/" + cleaned.split("/", 1)[1]
    if low.startswith("/uploads/"):
        return "/uploads/" + cleaned.split("/", 2)[2]
    if low == "/uploads":
        return "/uploads"

    if (
        low.startswith("workspace/")
        or low == "workspace"
        or low.startswith("/workspace")
    ):
        out = canonicalize_agent_path(cleaned)
        return out if out.startswith("/workspace") else None

    if cleaned.startswith("/"):
        return cleaned

    return None


def _mime_from_path(path: str) -> str:
    suffix = PurePosixPath(path).suffix.lower()
    guessed, _ = mimetypes.guess_type("x" + suffix)
    return guessed or "application/octet-stream"


def _looks_binary_by_sniff(raw: bytes) -> bool:
    if not raw:
        return False
    if raw[:2] == b"MZ" or raw[:4] == b"\x7fELF" or raw[:4] == b"PK\x03\x04":
        return True
    # Heuristic: NUL in first 8 KiB or very high non-text ratio
    sample = raw[:8192]
    if b"\x00" in sample:
        return True
    textish = sum(1 for b in sample if 32 <= b <= 126 or b in (9, 10, 13))
    return len(sample) > 200 and textish / len(sample) < 0.60


def _extension_forces_binary(path: str) -> bool:
    return PurePosixPath(path).suffix.lower() in _BINARY_SUFFIXES


def _deepagents_family(path: str) -> str:
    """image | audio | video | file | text"""
    return _get_file_type(path)


def _decode_text_with_fallbacks(raw: bytes) -> tuple[str, str, list[str]]:
    warnings: list[str] = []
    for enc in ("utf-8-sig", "utf-8"):
        try:
            return raw.decode(enc), enc, warnings
        except UnicodeDecodeError:
            continue
    for enc in ("gb18030", "cp936", "big5hkscs", "cp1252"):
        try:
            return raw.decode(enc), enc, warnings
        except UnicodeDecodeError:
            continue
    try:
        from charset_normalizer import from_bytes

        match = from_bytes(raw[: min(len(raw), 2_000_000)]).best()
        if match is not None:
            enc_guess = str(match.encoding)
            text = raw.decode(enc_guess, errors="replace")
            warnings.append("charset_normalizer_best_effort")
            return text, enc_guess, warnings
    except Exception:
        pass
    warnings.append("decoded_with_replacement")
    return raw.decode("utf-8", errors="replace"), "utf-8", warnings


def _truncate_long_line(line: str) -> tuple[str, bool]:
    if len(line) > _MAX_LINE_CHARS:
        return line[:_MAX_LINE_CHARS] + "… [line truncated]", True
    return line, False


def _head_tail_text_view(
    text: str,
    per_end_limit: int,
) -> tuple[str, int, int, int, int | None, int, bool]:
    """Build head+tail line view for security triage.

    Returns:
        body, total_lines, head_lines, tail_lines, tail_line_start (0-based, or None if full file),
        omitted_lines, any_long_line_truncated
    """
    lines = text.splitlines()
    total = len(lines)
    if total == 0:
        return "", 0, 0, 0, None, 0, False
    n = max(1, min(per_end_limit, total))
    long_trunc = False

    def fmt(block: list[str]) -> str:
        nonlocal long_trunc
        parts: list[str] = []
        for ln in block:
            s, t = _truncate_long_line(ln)
            if t:
                long_trunc = True
            parts.append(s)
        return "\n".join(parts)

    if 2 * n >= total:
        body = fmt(lines)
        return body, total, total, 0, None, 0, long_trunc

    head_part = fmt(lines[:n])
    tail_part = fmt(lines[total - n :])
    omitted = total - 2 * n
    sep = f"\n\n--- [{omitted} lines omitted; middle of file not shown] ---\n\n"
    body = head_part + sep + tail_part
    tail_start = total - n
    return body, total, n, n, tail_start, omitted, long_trunc


def _line_window(text: str, offset: int, limit: int) -> tuple[str, int, int, bool]:
    lines = text.splitlines()
    total = len(lines)
    if offset >= total:
        return "", total, 0, False
    chunk = lines[offset : offset + limit]
    truncated_lines = False
    out_lines: list[str] = []
    for line in chunk:
        s, t = _truncate_long_line(line)
        if t:
            truncated_lines = True
        out_lines.append(s)
    body = "\n".join(out_lines)
    return body, total, len(chunk), truncated_lines


def _parse_eml(raw: bytes, max_body: int = _MAX_EMAIL_BODY_CHARS) -> dict[str, Any]:
    msg = BytesParser(policy=policy.default).parsebytes(raw)
    subject = msg.get("Subject", "") or ""
    from_ = msg.get("From", "") or ""
    to = msg.get("To", "") or ""
    date = msg.get("Date", "") or ""

    attachments: list[dict[str, Any]] = []
    body_text = ""
    body_html = ""

    if msg.is_multipart():
        for part in msg.walk():
            if part.is_multipart():
                continue
            ctype = part.get_content_type()
            disp = str(part.get_content_disposition() or "")
            filename = part.get_filename()
            if disp == "attachment" or filename:
                plen = len(part.get_payload(decode=True) or b"")
                attachments.append(
                    {
                        "filename": filename or "",
                        "content_type": ctype,
                        "size_bytes": plen,
                        "skipped": True,
                    }
                )
                continue
            if ctype == "text/plain" and not body_text:
                try:
                    body_text = part.get_content().strip()[:max_body]  # type: ignore[union-attr]
                except Exception:
                    pass
            elif ctype == "text/html" and not body_html:
                try:
                    body_html = part.get_content().strip()[:max_body]  # type: ignore[union-attr]
                except Exception:
                    pass
    else:
        ctype = msg.get_content_type()
        if ctype == "text/html":
            body_html = (msg.get_content() or "")[:max_body]  # type: ignore[operator]
        else:
            body_text = (msg.get_content() or "")[:max_body]  # type: ignore[operator]

    return {
        "subject": str(subject)[:2048],
        "from": str(from_)[:2048],
        "to": str(to)[:2048],
        "date": str(date)[:256],
        "attachments": attachments,
        "body_text": body_text[:max_body],
        "body_html_preview": (body_html[:max_body] if body_html else None),
    }


def _runtime_backend(runtime: Any) -> Any:
    backend = getattr(runtime, "backend", None)
    if backend is not None:
        return backend
    from app.backends.composite import create_layered_backend

    return create_layered_backend()(runtime)


def _download_raw(backend: Any, path: str, max_bytes: int) -> tuple[bytes | None, str | None]:
    try:
        responses = backend.download_files([path])
    except Exception as exc:
        return None, f"download_failed:{exc}"
    if not responses:
        return None, "download_empty"
    response = responses[0]
    error = getattr(response, "error", None)
    if error:
        return None, str(error)
    content = getattr(response, "content", None)
    if not isinstance(content, bytes):
        return None, "not_bytes"
    if len(content) > max_bytes:
        content = content[:max_bytes]
    return content, None


def sread_file(
    file_path: str,
    offset: int = 0,
    limit: int = 500,
    view_mode: TextViewMode = "window",
    max_bytes: int = _DEFAULT_MAX_BYTES,
    hex_preview_bytes: int = 64,
    runtime: ToolRuntime | None = None,
) -> dict[str, Any]:
    """Read a user/security artifact with encoding and format awareness."""
    canon = _canonical_virtual_path(file_path)
    if canon is None:
        return {
            "ok": False,
            "content_kind": "error",
            "error_code": "INVALID_PATH",
            "error_message": (
                "file_path must be an absolute virtual path (e.g. /workspace/...) "
                "or start with workspace/ or uploads/."
            ),
        }

    raw, err = _download_raw(_runtime_backend(runtime), canon, max_bytes)
    if err:
        return {
            "ok": False,
            "content_kind": "error",
            "error_code": "READ_FAILED",
            "error_message": err,
            "path": canon,
        }
    assert raw is not None
    truncated_raw = len(raw) >= max_bytes

    if not raw:
        return {
            "ok": True,
            "content_kind": "empty",
            "path": canon,
            "message": "File is empty.",
            "truncated": truncated_raw,
        }

    suffix = PurePosixPath(canon).suffix.lower()
    if suffix == ".eml":
        try:
            parsed = _parse_eml(raw)
            return {
                "ok": True,
                "content_kind": "email",
                "path": canon,
                "mime_guess": "message/rfc822",
                "email": parsed,
                "truncated": truncated_raw,
                "truncation_reason": "max_bytes" if truncated_raw else None,
            }
        except Exception:
            pass

    fam = _deepagents_family(canon)
    if fam != "text":
        b64 = base64.standard_b64encode(raw).decode("ascii")
        out: dict[str, Any] = {
            "ok": True,
            "content_kind": "binary",
            "path": canon,
            "mime_guess": _mime_from_path(canon),
            "deepagents_family": fam,
            "size_bytes": len(raw),
            "truncated": truncated_raw,
            "truncation_reason": "max_bytes" if truncated_raw else None,
            "base64": b64,
        }
        if hex_preview_bytes > 0:
            head = raw[:hex_preview_bytes]
            out["hex_head"] = binascii.hexlify(head).decode("ascii")
        return out

    force_bin = _extension_forces_binary(canon) or _looks_binary_by_sniff(raw)
    if force_bin:
        b64 = base64.standard_b64encode(raw).decode("ascii")
        out = {
            "ok": True,
            "content_kind": "binary",
            "path": canon,
            "mime_guess": _mime_from_path(canon),
            "size_bytes": len(raw),
            "truncated": truncated_raw,
            "truncation_reason": "max_bytes" if truncated_raw else None,
            "base64": b64,
            "note": "Classified as binary by extension or content sniff (not UTF‑8 source text).",
        }
        if hex_preview_bytes > 0:
            head = raw[:hex_preview_bytes]
            out["hex_head"] = binascii.hexlify(head).decode("ascii")
        return out

    text, enc_used, enc_warnings = _decode_text_with_fallbacks(raw)
    warn = list(enc_warnings)
    if view_mode == "head_tail":
        if offset != 0:
            warn.append("offset_ignored_for_head_tail")
        (
            body,
            total_lines,
            head_n,
            tail_n,
            tail_line_start,
            omitted_lines,
            line_truncated,
        ) = _head_tail_text_view(text, limit)
        if line_truncated:
            warn.append("long_lines_truncated")
        trunc_reason: str | None = None
        if truncated_raw:
            trunc_reason = "max_bytes"
        elif omitted_lines > 0:
            trunc_reason = "head_tail_omit_middle"
        return {
            "ok": True,
            "content_kind": "text",
            "path": canon,
            "encoding": enc_used,
            "warnings": warn,
            "view_mode": "head_tail",
            "text": body,
            "line_start": 0,
            "lines_returned": head_n + tail_n,
            "total_lines": total_lines,
            "head_lines_returned": head_n,
            "tail_lines_returned": tail_n,
            "tail_line_start": tail_line_start,
            "omitted_lines": omitted_lines,
            "truncated": truncated_raw or omitted_lines > 0,
            "truncation_reason": trunc_reason,
        }

    body, total_lines, lines_out, line_truncated = _line_window(text, offset, limit)
    if line_truncated:
        warn.append("long_lines_truncated")
    if offset >= total_lines:
        return {
            "ok": True,
            "content_kind": "text",
            "path": canon,
            "encoding": enc_used,
            "warnings": warn,
            "view_mode": "window",
            "text": "",
            "line_start": offset,
            "lines_returned": 0,
            "total_lines": total_lines,
            "truncated": truncated_raw,
            "truncation_reason": "offset_beyond_eof" if offset else None,
            "message": f"offset {offset} is beyond file ({total_lines} lines).",
        }

    trunc_reason = None
    if truncated_raw:
        trunc_reason = "max_bytes"
    elif offset + lines_out < total_lines:
        trunc_reason = "line_window"

    return {
        "ok": True,
        "content_kind": "text",
        "path": canon,
        "encoding": enc_used,
        "warnings": warn,
        "view_mode": "window",
        "text": body,
        "line_start": offset,
        "lines_returned": lines_out,
        "total_lines": total_lines,
        "truncated": truncated_raw or (offset + lines_out < total_lines),
        "truncation_reason": trunc_reason,
    }


def create_sread_file_tool() -> StructuredTool:
    from app.tools.common.tools import _structured_tool_description_from_registry

    desc = _structured_tool_description_from_registry("SReadFile")
    return StructuredTool.from_function(
        func=sread_file,
        name="SReadFile",
        description=desc,
        args_schema=SReadFileInput,
        infer_schema=False,
    )
