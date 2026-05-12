"""Per-user JSON index for knowledge .docx metadata (display name, project link)."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

INDEX_FILENAME = "knowledge_index.json"
CURRENT_VERSION = 1


def load_index(user_dir: Path) -> dict[str, Any]:
    path = user_dir / INDEX_FILENAME
    if not path.is_file():
        return {"version": CURRENT_VERSION, "files": {}}
    try:
        with path.open(encoding="utf-8") as f:
            data = json.load(f)
        if not isinstance(data, dict):
            return {"version": CURRENT_VERSION, "files": {}}
        files = data.get("files")
        if not isinstance(files, dict):
            data["files"] = {}
        data.setdefault("version", CURRENT_VERSION)
        return data
    except Exception:
        return {"version": CURRENT_VERSION, "files": {}}


def save_index_atomic(user_dir: Path, data: dict[str, Any]) -> None:
    path = user_dir / INDEX_FILENAME
    tmp = path.with_suffix(".json.tmp")
    user_dir.mkdir(parents=True, exist_ok=True)
    payload = json.dumps(data, ensure_ascii=False, indent=2) + "\n"
    with tmp.open("w", encoding="utf-8") as f:
        f.write(payload)
    tmp.replace(path)


def upsert_file_metadata(
    user_dir: Path,
    *,
    filename: str,
    message_id: str,
    report_title: str | None,
    project_id: str | None,
    task_kind: str | None,
) -> None:
    """Record metadata after a successful upload (idempotent per filename key)."""
    data = load_index(user_dir)
    files: dict[str, Any] = data.setdefault("files", {})
    mid = (message_id or "").strip()
    title = (report_title or "").strip() or None
    pid = (project_id or "").strip() or None
    tk = (task_kind or "").strip() or None
    files[filename] = {
        "message_id": mid,
        "report_title": title,
        "project_id": pid,
        "task_kind": tk,
    }
    save_index_atomic(user_dir, data)


def entry_for_file(index: dict[str, Any], filename: str) -> dict[str, Any] | None:
    raw = index.get("files")
    if not isinstance(raw, dict):
        return None
    e = raw.get(filename)
    return e if isinstance(e, dict) else None


def derive_display_name(filename: str, entry: dict[str, Any] | None) -> str:
    """Human-facing title: prefer stored report_title, else filename stem."""
    if entry:
        rt = entry.get("report_title")
        if isinstance(rt, str) and rt.strip():
            return rt.strip()
    base = filename
    if base.lower().endswith(".docx"):
        base = base[:-5]
    s = base.replace("_", " ").strip()
    s = " ".join(s.split())
    return s if s else filename


def project_id_for_file(entry: dict[str, Any] | None) -> str | None:
    if not entry:
        return None
    pid = entry.get("project_id")
    if isinstance(pid, str) and pid.strip():
        return pid.strip()
    return None


__all__ = [
    "CURRENT_VERSION",
    "INDEX_FILENAME",
    "derive_display_name",
    "entry_for_file",
    "load_index",
    "project_id_for_file",
    "save_index_atomic",
    "upsert_file_metadata",
]
