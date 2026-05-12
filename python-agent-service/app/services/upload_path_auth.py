"""Virtual upload path ownership, sanitization, and disk resolution."""

from __future__ import annotations

import hashlib
from pathlib import Path
from typing import Any

from app.backends.constants import (
    ANON_OWNER_PREFIX,
    DEFAULT_PROJECT_SEGMENT,
    PROJECT_OWNER_PREFIX,
    USER_OWNER_PREFIX,
    WORKSPACE_VIRTUAL_ROOT,
)
from app.backends.path_aliases import fold_workspace_ui_spelling

# Historical /uploads/ prefix is still used by legacy helpers (authorize_virtual_path,
# resolve_upload_disk_path) for the pre-request /analyze file manifest resolution.
# Agent-facing tooling and user-visible paths are served under WORKSPACE_VIRTUAL_ROOT.
_UPLOADS_PREFIX = "/uploads/"


def sanitize_path_segment(raw: str, *, max_len: int = 128) -> str:
    """Allow only safe single path segment characters."""
    s = (raw or "").strip()
    if not s:
        return "unknown"
    out = []
    for c in s:
        if c.isalnum() or c in ("-", "_", "."):
            out.append(c)
        else:
            out.append("_")
    seg = "".join(out)[:max_len].strip("._") or "unknown"
    return seg


def owner_segment(
    *,
    user_id: str | None,
    session_id: str,
    project_id: str | None = None,
) -> str:
    """On-disk + virtual-scope owner segment for the per-request workspace.

    Shapes:
        logged-in + project   -> ``u_<uid>/p_<pid>``
        logged-in, no project -> ``u_<uid>/default``
        anonymous             -> ``s_<sid>``

    The project_id argument is accepted but silently ignored for anonymous sessions
    so that owner isolation still holds when ``user_id`` is missing.
    """
    if user_id:
        u = f"{USER_OWNER_PREFIX}{sanitize_path_segment(user_id)}"
        if project_id:
            p = f"{PROJECT_OWNER_PREFIX}{sanitize_path_segment(project_id)}"
        else:
            p = DEFAULT_PROJECT_SEGMENT
        return f"{u}/{p}"
    return f"{ANON_OWNER_PREFIX}{sanitize_path_segment(session_id or 'default')}"


def virtual_path_prefix_for_owner(owner: str) -> str:
    """Normalized prefix with trailing slash, e.g. /uploads/u_abc/p_xyz/ (disk-side)."""
    o = owner.strip("/")
    return f"{_UPLOADS_PREFIX}{o}/"


def strip_uploads_virtual_path(virtual_path: str) -> str:
    """Return path relative to upload_dir from a legacy /uploads/ virtual path.

    The new /workspace/ virtual root is also accepted: ``/workspace/<rest>`` becomes
    ``<rest>`` so that pre-request file manifest resolution can consume paths from
    either namespace transparently.

    UI copy may use historic PascalCase ``/Workspace/...``; that is folded here without
    stripping owner segments (unlike :func:`~app.backends.path_aliases.canonicalize_agent_path`).
    """
    v = fold_workspace_ui_spelling((virtual_path or "").strip())
    if not v.startswith("/"):
        v = f"/{v}"
    if v.startswith(WORKSPACE_VIRTUAL_ROOT):
        rest = v[len(WORKSPACE_VIRTUAL_ROOT) :].lstrip("/")
        return rest
    if not v.startswith(_UPLOADS_PREFIX):
        raise ValueError("not_under_uploads")
    rest = v[len(_UPLOADS_PREFIX) :].lstrip("/")
    return rest


def resolve_upload_disk_path(upload_dir: Path, virtual_path: str) -> Path:
    """Map virtual /uploads/... to absolute disk path under upload_dir."""
    rest = strip_uploads_virtual_path(virtual_path)
    if not rest or ".." in Path(rest).parts:
        raise ValueError("invalid_path")
    rel = Path(rest)
    actual = (upload_dir / rel).resolve()
    upload_resolved = upload_dir.resolve()
    try:
        actual.relative_to(upload_resolved)
    except ValueError as e:
        raise ValueError("outside_upload_dir") from e
    return actual


def authorize_virtual_path(
    virtual_path: str,
    *,
    upload_dir: Path,
    user_id: str | None,
    session_id: str,
    project_id: str | None = None,
    allow_legacy_flat: bool = True,
) -> tuple[bool, Path | None, str]:
    """
    Return (ok, resolved_disk_path, error_message).

    ``virtual_path`` must be under /uploads/ or /workspace/ and owned by the caller:
    - logged-in: ``u_<uid>/p_<pid>``, or ``u_<uid>/default`` (including default-bucket
      files attached to a project-scoped request for the same user)
    - anonymous: ``s_<sid>`` (flat single-level tree)
    """
    try:
        disk = resolve_upload_disk_path(upload_dir, virtual_path)
    except ValueError:
        return False, None, "Invalid upload path"

    try:
        rest = strip_uploads_virtual_path(virtual_path)
    except ValueError:
        return False, None, "Invalid upload path"

    parts = [p for p in rest.split("/") if p]
    if not parts:
        return False, None, "Empty upload path"

    expected = owner_segment(
        user_id=user_id, session_id=session_id, project_id=project_id
    )
    expected_parts = [p for p in expected.split("/") if p]
    # Prefix-match: owner segment may span 1 (anonymous) or 2 (user+project) path parts.
    if len(parts) >= len(expected_parts) and parts[: len(expected_parts)] == expected_parts:
        return True, disk, ""

    # Pre-project uploads: when the client had no project_id (e.g. transition composer
    # with uploadSessionId=null), POST /uploads stores under u_<uid>/default/. The first
    # POST /analyze for a new project then uses project_id=<new id>; allow the same
    # user to attach those default-bucket paths to any of their project-scoped runs.
    if user_id:
        u_seg = f"{USER_OWNER_PREFIX}{sanitize_path_segment(user_id)}"
        default_prefix = [u_seg, DEFAULT_PROJECT_SEGMENT]
        if (
            len(parts) >= len(default_prefix)
            and parts[: len(default_prefix)] == default_prefix
        ):
            return True, disk, ""

    first = parts[0]
    if user_id and first.startswith("s_"):
        return False, None, "Upload path not owned by current user"

    if not user_id and first.startswith("u_"):
        return False, None, "Upload path requires authentication"

    if allow_legacy_flat and not user_id:
        legacy_seg = sanitize_path_segment(session_id)
        if first == legacy_seg:
            return True, disk, ""

    return False, None, "Upload path not authorized for this session"


def attachment_virtual_path(file_dict: dict[str, Any]) -> str | None:
    """Extract virtual path from analyze attachment dict."""
    v = file_dict.get("file_path") or file_dict.get("filePath") or file_dict.get("virtual_path")
    if v is None:
        return None
    s = str(v).strip()
    return s if s else None


def total_inline_attachment_bytes(files: list[dict[str, Any]] | None) -> int:
    """Sum decoded byte length of inline content fields for legacy JSON uploads."""
    total = 0
    for f in files or []:
        raw = f.get("content") or f.get("fullContent")
        if raw is None:
            continue
        if isinstance(raw, bytes):
            total += len(raw)
        else:
            total += len(str(raw).encode("utf-8", errors="replace"))
    return total


def sha256_hex(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def safe_unique_filename(original: str) -> str:
    """Preserve extension; add random prefix to avoid collisions."""
    from secrets import token_hex

    name = sanitize_path_segment(original.replace("\\", "/").split("/")[-1], max_len=200)
    if not name or name == "unknown":
        name = "upload.bin"
    stem = name
    suffix = ""
    if "." in name:
        stem, _, ext = name.rpartition(".")
        suffix = f".{ext}" if ext else ""
    return f"{token_hex(6)}_{stem}{suffix}"


def is_probably_text_bytes(sample: bytes) -> bool:
    if not sample:
        return True
    if b"\x00" in sample[:8192]:
        return False
    try:
        sample.decode("utf-8")
        return True
    except UnicodeDecodeError:
        return False


def sniff_preview(disk_path: Path, *, per_file_cap: int) -> str:
    """Small UTF-8 safe preview for manifest (binary -> short hex note)."""
    try:
        data = disk_path.read_bytes()[:per_file_cap]
    except OSError:
        return "(unreadable)"
    if not data:
        return "(empty file)"
    if is_probably_text_bytes(data):
        return data.decode("utf-8", errors="replace")
    h = data[:16].hex()
    return f"[binary, first {len(data)} bytes as hex: {h}...]"
