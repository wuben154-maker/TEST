"""Knowledge base API — .docx under knowledge/<user_id>/."""

from __future__ import annotations

from datetime import datetime, timezone

import structlog
from app.api.auth import get_current_user
from app.config import get_settings
from app.services.knowledge_index import (
    derive_display_name,
    entry_for_file,
    load_index,
    project_id_for_file,
    upsert_file_metadata,
)
from app.services.knowledge_paths import (
    knowledge_stored_filename,
    resolve_knowledge_file,
    user_knowledge_dir,
)
from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from fastapi.responses import FileResponse
from pydantic import BaseModel

logger = structlog.get_logger()
router = APIRouter(prefix="/knowledge", tags=["knowledge"])


def _message_id_for_file(entry: dict | None) -> str | None:
    if not entry:
        return None
    mid = entry.get("message_id")
    if isinstance(mid, str) and mid.strip():
        return mid.strip()
    return None


def _max_bytes() -> int:
    s = get_settings()
    return s.knowledge_max_bytes_per_file or s.max_upload_bytes_per_file


class KnowledgeItem(BaseModel):
    filename: str
    display_name: str
    project_id: str | None = None
    """Correlates archived .docx with ``messages.request_id`` when index was written."""
    message_id: str | None = None
    size_bytes: int
    updated_at: str
    display_path: str


class KnowledgeListResponse(BaseModel):
    items: list[KnowledgeItem]


def _iso_mtime(st: float | int) -> str:
    dt = datetime.fromtimestamp(float(st), tz=timezone.utc)
    return dt.isoformat().replace("+00:00", "Z")


@router.get("", response_model=KnowledgeListResponse)
async def list_knowledge(
    current_user: dict = Depends(get_current_user),
) -> KnowledgeListResponse:
    settings = get_settings()
    uid = str(current_user["id"])
    user_dir = user_knowledge_dir(settings, uid)
    index = load_index(user_dir)
    items: list[KnowledgeItem] = []
    try:
        names = sorted(user_dir.iterdir())
    except FileNotFoundError:
        return KnowledgeListResponse(items=[])
    for p in names:
        if not p.is_file():
            continue
        name = p.name
        if not name.lower().endswith(".docx"):
            continue
        entry = entry_for_file(index, name)
        st = p.stat()
        items.append(
            KnowledgeItem(
                filename=name,
                display_name=derive_display_name(name, entry),
                project_id=project_id_for_file(entry),
                message_id=_message_id_for_file(entry),
                size_bytes=st.st_size,
                updated_at=_iso_mtime(st.st_mtime),
                display_path=f"Workspace/knowledge/{name}",
            )
        )
    items.sort(key=lambda x: x.updated_at, reverse=True)
    return KnowledgeListResponse(items=items)


@router.post("/reports", status_code=201)
async def store_knowledge_report(
    file: UploadFile = File(...),
    message_id: str = Form(""),
    project_id: str = Form(""),
    task_kind: str = Form(""),
    report_title: str = Form(""),
    current_user: dict = Depends(get_current_user),
):
    """Store a .docx; same ``message_id`` overwrites the file."""
    mid = (message_id or "").strip()
    if not mid:
        raise HTTPException(status_code=400, detail="message_id is required")

    raw_name = file.filename or ""
    if not raw_name.lower().endswith(".docx"):
        raise HTTPException(status_code=400, detail="Expected a .docx file")

    settings = get_settings()
    max_b = _max_bytes()
    uid = str(current_user["id"])
    title = (report_title or "").strip() or None
    disk_name = knowledge_stored_filename(mid, title)
    dest = user_knowledge_dir(settings, uid) / disk_name

    size = 0
    try:
        with dest.open("wb") as out:
            while True:
                chunk = await file.read(1024 * 1024)
                if not chunk:
                    break
                size += len(chunk)
                if size > max_b:
                    dest.unlink(missing_ok=True)
                    raise HTTPException(
                        status_code=413,
                        detail=f"File exceeds max size ({max_b} bytes)",
                    )
                out.write(chunk)
    except HTTPException:
        raise
    except Exception as e:
        dest.unlink(missing_ok=True)
        logger.error("knowledge_store_failed", error=str(e))
        raise HTTPException(status_code=500, detail="Failed to store report") from e

    try:
        upsert_file_metadata(
            dest.parent,
            filename=disk_name,
            message_id=mid,
            report_title=title,
            project_id=(project_id or "").strip() or None,
            task_kind=(task_kind or "").strip() or None,
        )
    except Exception as e:
        logger.warning("knowledge_index_write_failed", filename=disk_name, error=str(e))

    return {
        "filename": disk_name,
        "display_path": f"Workspace/knowledge/{disk_name}",
        "size_bytes": size,
        "project_id": (project_id or "").strip(),
        "task_kind": (task_kind or "").strip(),
    }


@router.get("/download")
async def download_knowledge(
    filename: str,
    current_user: dict = Depends(get_current_user),
):
    settings = get_settings()
    uid = str(current_user["id"])
    path = resolve_knowledge_file(settings, uid, filename)
    if path is None or not path.is_file():
        raise HTTPException(status_code=404, detail="Not found")
    return FileResponse(
        path=path,
        filename=path.name,
        media_type=(
            "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
        ),
    )


__all__ = ["router"]
