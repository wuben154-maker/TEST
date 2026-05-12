"""Multipart file upload API — scoped disk layout and virtual paths."""

from __future__ import annotations

import hashlib
from pathlib import Path

import structlog
from app.api.auth import get_optional_user
from app.config import get_settings
from app.services.upload_path_auth import (
    owner_segment,
    safe_unique_filename,
    virtual_path_prefix_for_owner,
)
from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile

logger = structlog.get_logger()

router = APIRouter(prefix="/uploads", tags=["uploads"])


@router.post("")
async def upload_files(
    files: list[UploadFile] = File(default_factory=list),
    session_id: str = Form(""),
    project_id: str = Form(""),
    current_user: dict | None = Depends(get_optional_user),
):
    """Accept multipart files; persist under owner-scoped dir; return virtual paths.

    ``project_id`` binds uploads to ``u_<uid>/p_<pid>/`` so the agent
    ContextVar scope (also keyed on project_id) resolves the file on read.
    Omitted ⇒ ``u_<uid>/default/``.
    """
    settings = get_settings()
    max_n = settings.max_upload_files_per_batch
    max_b = settings.max_upload_bytes_per_file

    if not files:
        raise HTTPException(status_code=400, detail="No files provided")

    if len(files) > max_n:
        raise HTTPException(
            status_code=400,
            detail=f"Too many files (max {max_n} per request)",
        )

    uid = (current_user or {}).get("id") if current_user else None
    sid = (session_id or "").strip()
    pid = (project_id or "").strip() or None
    if not uid and not sid:
        raise HTTPException(
            status_code=400,
            detail="session_id is required for uploads when not authenticated",
        )

    eff_session = sid or "default"
    seg = owner_segment(user_id=uid, session_id=eff_session, project_id=pid)
    base_dir = Path(settings.upload_dir) / seg
    base_dir.mkdir(parents=True, exist_ok=True)
    prefix = virtual_path_prefix_for_owner(seg)

    results: list[dict] = []
    for uf in files:
        raw_name = uf.filename or "upload.bin"
        disk_name = safe_unique_filename(raw_name)
        dest = base_dir / disk_name
        h = hashlib.sha256()
        size = 0
        try:
            with dest.open("wb") as out:
                while True:
                    chunk = await uf.read(1024 * 1024)
                    if not chunk:
                        break
                    size += len(chunk)
                    if size > max_b:
                        dest.unlink(missing_ok=True)
                        raise HTTPException(
                            status_code=413,
                            detail=f"File exceeds max size ({max_b} bytes)",
                        )
                    h.update(chunk)
                    out.write(chunk)
        except HTTPException:
            raise
        except Exception as e:
            dest.unlink(missing_ok=True)
            logger.error("upload_failed", error=str(e), filename=raw_name)
            raise HTTPException(status_code=500, detail="Upload failed") from e

        ct = uf.content_type or "application/octet-stream"
        vpath = f"{prefix}{disk_name}"
        workspace_path = f"/workspace/{disk_name}"
        results.append(
            {
                "filename": raw_name,
                "stored_filename": disk_name,
                "content_type": ct,
                "size_bytes": size,
                "virtual_path": vpath,
                "workspace_path": workspace_path,
                "display_path": workspace_path,
                "sha256": h.hexdigest(),
            }
        )

    return {"files": results}
