"""Shared helpers used across the tools package."""

from __future__ import annotations

import functools
import logging
import re
import unicodedata
from collections.abc import Callable
from pathlib import Path
from typing import Any

from email.header import decode_header

from langchain.tools import ToolRuntime
from langchain_core.tools import StructuredTool
from pydantic import Field, create_model

logger = logging.getLogger("email_security_agent")

# NOTE: The main service mounts user-scoped uploads under /uploads/.
# The original upstream agent used /uploaded/; we treat it as a legacy alias.
UPLOADED_PREFIX = "/uploads"


def _safe_storage_basename(filename: str, *, max_total_len: int = 200) -> str:
    """Sanitize attachment basename for virtual-path segments (portable, LLM-copy stable).

    MIME filenames may contain ©, U+FFFD, or mixed Unicode that models re-type
    inconsistently; extracted files are stored under this name so ``file_path``
    from ``parse_eml`` matches the backend.
    """
    raw = Path(str(filename).replace("\\", "/")).name.strip() or "attachment"
    stem, suffix = Path(raw).stem, Path(raw).suffix
    stem = unicodedata.normalize("NFKC", stem)
    stem = stem.replace("\ufffd", "_").replace("\u00a9", "").replace("\u00ae", "")
    stem = re.sub(r"[^A-Za-z0-9._-]+", "_", stem)
    stem = re.sub(r"_+", "_", stem).strip("._-") or "file"
    suf = suffix.lower() if suffix else ""
    suf = re.sub(r"[^.a-zA-Z0-9]+", "", suf) or ".bin"
    if not suf.startswith("."):
        suf = "." + suf.lstrip(".")
    suf = suf[:20]
    budget = max(max_total_len - len(suf), 8)
    stem = stem[:budget]
    return f"{stem}{suf}"


def _normalize_path(path: str) -> str:
    """Normalize path for backend lookup.

    Aligns UI / model spellings (``workspace/...``) with :func:`canonicalize_agent_path`
    so paths match :class:`PathAliasBackend` routing. Whitelist: ``/uploads/`` (legacy
    ``/uploaded/`` folded here) and ``/workspace/`` (same disk scope as uploads in the
    layered backend).
    """
    from app.backends.path_aliases import canonicalize_agent_path

    if "\x00" in path:
        msg = f"Null byte in path: {path!r}"
        raise ValueError(msg)
    p = path.replace("\\", "/").strip()
    if ".." in p.split("/") or p.startswith("~"):
        msg = f"Path traversal not allowed: {path}"
        raise ValueError(msg)
    normalized = canonicalize_agent_path(p)
    if not normalized.startswith("/"):
        normalized = f"/{normalized}" if normalized else "/"
    # Legacy alias: accept /uploaded/... but route to /uploads/... (backend mount).
    if normalized.startswith("/uploaded/"):
        normalized = "/uploads/" + normalized[len("/uploaded/") :].lstrip("/")

    workspace_root = "/workspace"
    under_uploads = normalized.startswith(UPLOADED_PREFIX + "/") or normalized == UPLOADED_PREFIX
    under_workspace = normalized.startswith(workspace_root + "/") or normalized == workspace_root
    if not under_uploads and not under_workspace:
        msg = f"Path must be under {UPLOADED_PREFIX}/ or {workspace_root}/: {path}"
        raise ValueError(msg)
    return normalized


def _decode_header_value(val: str | None) -> str:
    """Decode RFC 2047 encoded header value to Unicode."""
    if not val or "=?" not in val:
        return val or ""
    parts = decode_header(val)
    result: list[str] = []
    for decoded, charset in parts:
        if isinstance(decoded, bytes):
            result.append(decoded.decode(charset or "utf-8", errors="replace"))
        else:
            result.append(decoded)
    return "".join(result)


def _error_result(error: str) -> dict[str, Any]:
    """Return a standard ``parse_eml`` error response."""
    return {
        "ok": False,
        "metadata": None,
        "headers_raw": "",
        "body_text": None,
        "body_html": None,
        "attachments": [],
        "error": error,
    }


def _resolve_phase4_data(
    file_path: str | None,
    backend_factory: Callable[[Any], Any],
    runtime: ToolRuntime,
) -> tuple[bytes | None, str]:
    """Resolve bytes from ``file_path``. Returns ``(data, error)``.

    This agent intentionally avoids transporting attachment bytes as base64 in
    the LLM context. Tools should pass `file_path` and let the backend fetch
    bytes on demand.
    """
    if not file_path:
        return None, "Provide file_path"
    try:
        validated_path = _normalize_path(file_path)
    except ValueError as exc:
        return None, str(exc)
    backend = backend_factory(runtime)
    responses = backend.download_files([validated_path])
    if not responses or responses[0].error:
        return None, responses[0].error if responses else "file_not_found"
    content = responses[0].content
    return content if content else None, "" if content else "No content"


# Unified brand registry: keyword → canonical domain(s)
KNOWN_BRANDS: dict[str, str] = {
    "paypal": "paypal.com",
    "microsoft": "microsoft.com",
    "apple": "apple.com",
    "google": "google.com",
    "amazon": "amazon.com",
    "facebook": "facebook.com",
    "netflix": "netflix.com",
    "linkedin": "linkedin.com",
    "dropbox": "dropbox.com",
    "icloud": "icloud.com",
    "outlook": "outlook.com",
    "office": "office.com",
    "bank": "",
    "support": "",
}
_BRAND_KEYWORDS = list(KNOWN_BRANDS.keys())
BRAND_DOMAINS = frozenset(d for d in KNOWN_BRANDS.values() if d)

MAX_ATTACHMENT_INLINE_BYTES = 10 * 1024 * 1024  # 10 MB

URL_SHORTENERS: frozenset[str] = frozenset(
    {
        "bit.ly",
        "tinyurl.com",
        "t.co",
        "goo.gl",
        "ow.ly",
        "is.gd",
        "buff.ly",
        "j.mp",
        "su.pr",
        "tr.im",
        "cli.gs",
        "short.to",
        "budurl.com",
        "ping.fm",
        "post.ly",
        "just.as",
        "bkite.com",
        "snipr.com",
    }
)

SUSPICIOUS_TLDS: frozenset[str] = frozenset(
    {
        ".tk",
        ".ml",
        ".ga",
        ".cf",
        ".gq",
        ".top",
        ".xyz",
        ".work",
        ".click",
        ".link",
        ".download",
        ".racing",
    }
)


def bind_backend(
    tool: StructuredTool,
    backend_factory: Callable[[Any], Any],
) -> StructuredTool:
    """Return a new StructuredTool with backend_factory pre-bound via closure.

    ``BaseTool.bind()`` (inherited from ``Runnable``) returns ``RunnableBinding``,
    which is NOT a ``BaseTool`` subclass and has ``name=None``.  LangGraph's
    ``ToolNode`` requires a strict ``BaseTool`` instance, so passing a
    ``RunnableBinding`` causes the "first argument must be a string or callable
    with a name" error at graph construction time.

    This helper creates a proper ``StructuredTool`` that closes over
    ``backend_factory`` while preserving:
    - ``name`` / ``description`` / ``args_schema`` from the original tool
    - ``__annotations__`` (via ``functools.wraps``) so ``ToolNode`` still detects
      and injects ``runtime: ToolRuntime`` automatically
    """
    original_func: Callable[..., Any] = tool.func  # type: ignore[attr-defined]
    filtered_fields: dict[str, tuple[Any, Any]] = {}
    args_schema = getattr(tool, "args_schema", None)
    model_fields = getattr(args_schema, "model_fields", {})
    for field_name, model_field in model_fields.items():
        if field_name in {"backend_factory", "runtime"}:
            continue
        default_value = (
            ...
            if getattr(model_field, "is_required", lambda: False)()
            else model_field.default
        )
        if getattr(model_field, "description", None):
            default_value = Field(default_value, description=model_field.description)
        filtered_fields[field_name] = (model_field.annotation, default_value)
    bound_args_schema = create_model(
        f"{getattr(tool, 'name', 'bound_tool')}_bound_schema",
        **filtered_fields,
    )

    @functools.wraps(original_func)
    def bound(**kwargs: Any) -> Any:
        runtime = kwargs.pop("runtime", None)
        return original_func(backend_factory=backend_factory, runtime=runtime, **kwargs)

    return StructuredTool.from_function(
        func=bound,
        name=tool.name,
        description=tool.description,
        args_schema=bound_args_schema,
    )

