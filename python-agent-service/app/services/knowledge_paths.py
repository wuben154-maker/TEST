"""Disk layout and path safety for per-user knowledge (.docx) under ``knowledge/<user_id>/``."""

from __future__ import annotations

import re
from pathlib import Path

from app.config import Settings
from app.services.upload_path_auth import sanitize_path_segment


def knowledge_filesystem_root(settings: Settings) -> Path:
    """Root directory that contains the top-level ``knowledge/`` folder."""
    raw = (settings.knowledge_storage_root or "").strip()
    if raw:
        return Path(raw).expanduser().resolve()
    return Path(settings.upload_dir).expanduser().resolve()


def user_knowledge_dir(settings: Settings, user_id: str) -> Path:
    """``{root}/knowledge/<sanitized_user_id>/`` — created if missing."""
    uid = sanitize_path_segment(user_id)
    d = knowledge_filesystem_root(settings) / "knowledge" / uid
    d.mkdir(parents=True, exist_ok=True)
    return d


def knowledge_title_segment(raw: str | None, *, max_len: int = 48) -> str:
    """Single path segment from a human title (letters, digits, CJK; unsafe chars → _)."""
    if not raw or not str(raw).strip():
        return ""
    s = str(raw).strip()
    out: list[str] = []
    for c in s:
        if c.isalnum() or "\u4e00" <= c <= "\u9fff":
            out.append(c)
        elif c in (" ", "-", "_", "."):
            out.append("_")
        else:
            out.append("_")
    seg = "".join(out)
    seg = re.sub(r"_+", "_", seg).strip("._")
    if not seg:
        return ""
    seg = seg[:max_len].rstrip("._")
    return seg or ""


def knowledge_stored_filename(message_id: str, report_title: str | None = None) -> str:
    """Idempotent name keyed by ``message_id``; optional ``report_title`` prefix for readability."""
    mid = sanitize_path_segment(message_id)
    title_seg = knowledge_title_segment(report_title)
    if title_seg:
        return f"{title_seg}-{mid}.docx"
    return f"report-{mid}.docx"


def resolve_knowledge_file(settings: Settings, user_id: str, filename: str) -> Path | None:
    """Map a basename into the caller's knowledge dir; reject path traversal."""
    base = (filename or "").strip()
    if not base or base != Path(base).name or ".." in base:
        return None
    if not base.lower().endswith(".docx"):
        return None
    user_dir = user_knowledge_dir(settings, user_id)
    target = (user_dir / base).resolve()
    try:
        target.relative_to(user_dir.resolve())
    except ValueError:
        return None
    return target


__all__ = [
    "knowledge_filesystem_root",
    "knowledge_title_segment",
    "knowledge_stored_filename",
    "resolve_knowledge_file",
    "user_knowledge_dir",
]
