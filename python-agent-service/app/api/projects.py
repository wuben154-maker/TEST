"""Projects API routes."""

import json
from typing import Any, Dict, List, Optional
from uuid import uuid4

import structlog
from app.api.auth import get_current_user
from app.config import get_settings
from app.datetime_support import format_api_datetime
from app.db import get_pg_pool, get_supabase_client
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

logger = structlog.get_logger()
router = APIRouter(prefix="/projects", tags=["projects"])


class ProjectCreate(BaseModel):
    title: Optional[str] = "新对话"


class ProjectUpdate(BaseModel):
    """PATCH /projects/:id body.

    All fields optional so a client can send title-only, context-usage-only,
    or both in a single request. ``context_usage`` may be explicitly ``null``
    to clear the persisted ring. The sentinel below distinguishes
    "field absent" (keep existing row) from "field present & null" (clear).
    """

    title: Optional[str] = None
    # Use Pydantic's ``Field`` with a default sentinel so we can tell
    # "key not in body" apart from "key was explicitly null". FastAPI sets
    # unset fields to the default; omitted keys stay as ``_UNSET``.
    context_usage: Any = Field(default="__unset__")


class ProjectResponse(BaseModel):
    id: str
    title: str
    created_at: str
    updated_at: str
    # Realtime context-usage ring persistence (feature
    # realtime-context-usage-indicator). ``None`` until first write; the
    # payload schema is authored by the frontend (see design.md Contracts).
    context_usage: Optional[Dict[str, Any]] = None
    context_usage_updated_at: Optional[str] = None


class ProjectWithMessages(ProjectResponse):
    messages: List[dict]


# Sentinel used by ``ProjectUpdate.context_usage`` to distinguish
# "field absent" (keep existing row) from "field present and ``null``"
# (explicit clear). Keep in sync with the ``Field(default=...)`` above.
_UNSET_CONTEXT_USAGE = "__unset__"


def _serialize_context_usage(raw: Any) -> Optional[Dict[str, Any]]:
    """Normalise a DB column value to a dict or ``None`` for the API response.

    ``asyncpg`` returns jsonb as the native Python value when decoded through
    the default codec but some older paths still hand back a ``str``. Be
    defensive on both sides so an occasional string payload doesn't 500 the
    whole ``GET /projects/:id`` call.
    """
    if raw is None:
        return None
    if isinstance(raw, dict):
        return raw
    if isinstance(raw, str):
        try:
            parsed = json.loads(raw)
            return parsed if isinstance(parsed, dict) else None
        except (json.JSONDecodeError, TypeError):
            return None
    return None


@router.get("", response_model=List[ProjectResponse])
async def list_projects(current_user: dict = Depends(get_current_user)):
    """List all projects for current user."""
    settings = get_settings()
    
    # Local database-backed projects
    if settings.database_mode == "local":
        pool = await get_pg_pool()
        async with pool.acquire() as conn:
            rows = await conn.fetch(
                """
                SELECT id, title, created_at, updated_at
                FROM projects
                WHERE user_id = $1
                ORDER BY updated_at DESC
                """,
                current_user["id"]
            )
            
            return [
                {
                    "id": str(row["id"]),
                    "title": row["title"],
                    "created_at": format_api_datetime(row["created_at"]),
                    "updated_at": format_api_datetime(row["updated_at"]),
                }
                for row in rows
            ]
    
    # Supabase-backed projects
    if settings.database_mode == "supabase":
        try:
            client = get_supabase_client()
            result = client.table("projects").select("*").eq("user_id", current_user["id"]).order("updated_at", desc=True).execute()
            
            return [
                {
                    "id": str(row["id"]),
                    "title": row["title"],
                    "created_at": format_api_datetime(row["created_at"]),
                    "updated_at": format_api_datetime(row["updated_at"]),
                }
                for row in result.data
            ]
        except Exception as e:
            logger.error("Failed to list projects", error=str(e))
            raise HTTPException(status_code=500, detail="Failed to list projects")
    
    # Unsupported mode
    raise HTTPException(status_code=500, detail="Unsupported database_mode for listing projects")


@router.post("", response_model=ProjectResponse)
async def create_project(
    request: ProjectCreate,
    current_user: dict = Depends(get_current_user)
):
    """Create a new project."""
    settings = get_settings()
    
    # Local database-backed projects
    if settings.database_mode == "local":
        project_id = str(uuid4())
        pool = await get_pg_pool()
        
        async with pool.acquire() as conn:
            row = await conn.fetchrow(
                """
                INSERT INTO projects (id, user_id, title)
                VALUES ($1, $2, $3)
                RETURNING id, title, created_at, updated_at
                """,
                project_id, current_user["id"], request.title
            )
            
            return {
                "id": str(row["id"]),
                "title": row["title"],
                "created_at": format_api_datetime(row["created_at"]),
                "updated_at": format_api_datetime(row["updated_at"]),
            }
    
    # Supabase-backed projects
    if settings.database_mode == "supabase":
        try:
            client = get_supabase_client()
            result = client.table("projects").insert({
                "user_id": current_user["id"],
                "title": request.title,
            }).execute()
            
            if not result.data:
                raise HTTPException(status_code=500, detail="Failed to create project")
            
            row = result.data[0]
            return {
                "id": str(row["id"]),
                "title": row["title"],
                "created_at": format_api_datetime(row["created_at"]),
                "updated_at": format_api_datetime(row["updated_at"]),
            }
        except HTTPException:
            raise
        except Exception as e:
            logger.error("Failed to create project", error=str(e))
            err_lower = str(e).lower()
            if "row-level security" in err_lower or ("violates" in err_lower and "policy" in err_lower):
                raise HTTPException(
                    status_code=500,
                    detail="Database permission denied. Ensure SUPABASE_SERVICE_ROLE_KEY is set in python-agent-service/.env (Supabase Dashboard > Settings > API).",
                )
            raise HTTPException(status_code=500, detail=f"Failed to create project: {str(e)}")
    
    # Unsupported mode
    raise HTTPException(status_code=500, detail="Unsupported database_mode for creating project")


@router.post("/{project_id}/analysis-progress/cancel")
async def cancel_analysis_progress(
    project_id: str,
    current_user: dict = Depends(get_current_user),
):
    """Cancel/dismiss in-progress analysis (clears progress so UI stops showing running state).
    Use when user clicks Stop on a restored session or to clear stale progress."""
    settings = get_settings()
    if settings.database_mode == "memory":
        return {"message": "cancelled"}

    if settings.database_mode == "local":
        pool = await get_pg_pool()
        async with pool.acquire() as conn:
            project = await conn.fetchrow(
                "SELECT id FROM projects WHERE id = $1 AND user_id = $2",
                project_id, current_user["id"],
            )
            if not project:
                raise HTTPException(status_code=404, detail="Project not found")
            await conn.execute(
                "DELETE FROM project_analysis_progress WHERE project_id = $1",
                project_id,
            )
        return {"message": "cancelled"}

    if settings.database_mode == "supabase":
        client = get_supabase_client()
        project_result = client.table("projects").select("id").eq("id", project_id).eq("user_id", current_user["id"]).execute()
        if not project_result.data:
            raise HTTPException(status_code=404, detail="Project not found")
        client.table("project_analysis_progress").delete().eq("project_id", project_id).execute()
        return {"message": "cancelled"}

    return {"message": "cancelled"}


@router.get("/{project_id}/analysis-progress")
async def get_analysis_progress(
    project_id: str,
    current_user: dict = Depends(get_current_user),
):
    """Get current analysis progress for a project (for refresh recovery).
    Returns null when no running analysis.
    """
    settings = get_settings()
    if settings.database_mode == "memory":
        return None

    if settings.database_mode == "local":
        pool = await get_pg_pool()
        async with pool.acquire() as conn:
            project = await conn.fetchrow(
                "SELECT id FROM projects WHERE id = $1 AND user_id = $2",
                project_id, current_user["id"],
            )
            if not project:
                raise HTTPException(status_code=404, detail="Project not found")
            row = await conn.fetchrow(
                """
                SELECT id, project_id, request_id, status, user_input,
                       thinking_steps, task_plan, understanding, task_summary,
                       conclusion, blocks, error_detail, timeline, ui_language, updated_at
                FROM project_analysis_progress
                WHERE project_id = $1 AND status = 'running'
                """,
                project_id,
            )
            if not row:
                return None
            raw_timeline = row["timeline"]
            if raw_timeline is None:
                timeline_parsed = []
            elif isinstance(raw_timeline, str):
                timeline_parsed = json.loads(raw_timeline) if raw_timeline.strip() else []
            else:
                timeline_parsed = raw_timeline if isinstance(raw_timeline, list) else []
            return {
                "is_analyzing": True,
                "request_id": row["request_id"],
                "ui_language": row.get("ui_language"),
                "user_input": row["user_input"],
                "thinking_steps": json.loads(row["thinking_steps"]) if isinstance(row["thinking_steps"], str) else (row["thinking_steps"] or []),
                "task_plan": json.loads(row["task_plan"]) if isinstance(row["task_plan"], str) else row["task_plan"],
                "understanding": json.loads(row["understanding"]) if isinstance(row["understanding"], str) else row["understanding"],
                "task_summary": row["task_summary"] or "",
                "conclusion": row["conclusion"] or "",
                "blocks": json.loads(row["blocks"]) if isinstance(row["blocks"], str) else (row["blocks"] or []),
                "timeline": timeline_parsed,
                "updated_at": format_api_datetime(row["updated_at"]),
            }

    if settings.database_mode == "supabase":
        client = get_supabase_client()
        project_result = client.table("projects").select("id").eq("id", project_id).eq("user_id", current_user["id"]).execute()
        if not project_result.data:
            raise HTTPException(status_code=404, detail="Project not found")
        result = client.table("project_analysis_progress").select("*").eq("project_id", project_id).eq("status", "running").execute()
        if not result.data:
            return None
        row = result.data[0]
        tl = row.get("timeline")
        if not isinstance(tl, list):
            tl = []
        return {
            "is_analyzing": True,
            "request_id": row.get("request_id"),
            "ui_language": row.get("ui_language"),
            "user_input": row["user_input"],
            "thinking_steps": row["thinking_steps"] or [],
            "task_plan": row["task_plan"],
            "understanding": row["understanding"],
            "task_summary": row["task_summary"] or "",
            "conclusion": row["conclusion"] or "",
            "blocks": row["blocks"] or [],
            "timeline": tl,
            "updated_at": format_api_datetime(row["updated_at"]),
        }

    return None


@router.get("/{project_id}", response_model=ProjectWithMessages)
async def get_project(
    project_id: str,
    current_user: dict = Depends(get_current_user)
):
    """Get a project with its messages."""
    settings = get_settings()
    
    # Local database-backed projects
    if settings.database_mode == "local":
        pool = await get_pg_pool()
        
        async with pool.acquire() as conn:
            # Get project
            project = await conn.fetchrow(
                """
                SELECT id, title, created_at, updated_at,
                       context_usage, context_usage_updated_at
                FROM projects
                WHERE id = $1 AND user_id = $2
                """,
                project_id, current_user["id"]
            )
            
            if not project:
                raise HTTPException(status_code=404, detail="Project not found")
            
            # Get messages
            messages = await conn.fetch(
                """
                SELECT id, content, type, reasoning, thinking_steps, blocks, timeline, created_at
                FROM messages
                WHERE project_id = $1
                ORDER BY created_at ASC
                """,
                project_id
            )
            
            return {
                "id": str(project["id"]),
                "title": project["title"],
                "created_at": format_api_datetime(project["created_at"]),
                "updated_at": format_api_datetime(project["updated_at"]),
                "context_usage": _serialize_context_usage(project.get("context_usage")),
                "context_usage_updated_at": (
                    format_api_datetime(project["context_usage_updated_at"])
                    if project.get("context_usage_updated_at") is not None
                    else None
                ),
                "messages": [
                    {
                        "id": str(msg["id"]),
                        "content": msg["content"],
                        "type": msg["type"],
                        "reasoning": msg["reasoning"],
                        "thinking_steps": json.loads(msg["thinking_steps"]) if msg["thinking_steps"] else None,
                        "blocks": json.loads(msg["blocks"]) if msg["blocks"] else None,
                        "timeline": (
                            msg["timeline"]
                            if isinstance(msg.get("timeline"), list)
                            else (json.loads(msg["timeline"]) if msg.get("timeline") else [])
                        ),
                        "created_at": format_api_datetime(msg["created_at"]),
                    }
                    for msg in messages
                ],
            }
    
    # Supabase-backed projects
    if settings.database_mode == "supabase":
        try:
            client = get_supabase_client()
            
            # Get project
            project_result = client.table("projects").select("*").eq("id", project_id).eq("user_id", current_user["id"]).execute()
            
            if not project_result.data:
                raise HTTPException(status_code=404, detail="Project not found")
            
            project = project_result.data[0]
            
            # Get messages
            messages_result = client.table("messages").select("*").eq("project_id", project_id).order("created_at", desc=False).execute()
            
            return {
                "id": str(project["id"]),
                "title": project["title"],
                "created_at": format_api_datetime(project["created_at"]),
                "updated_at": format_api_datetime(project["updated_at"]),
                "context_usage": _serialize_context_usage(project.get("context_usage")),
                "context_usage_updated_at": (
                    format_api_datetime(project["context_usage_updated_at"])
                    if project.get("context_usage_updated_at") is not None
                    else None
                ),
                "messages": [
                    {
                        "id": str(msg["id"]),
                        "content": msg["content"],
                        "type": msg["type"],
                        "reasoning": msg["reasoning"],
                        "thinking_steps": msg["thinking_steps"],
                        "blocks": msg["blocks"],
                        "timeline": msg.get("timeline") or [],
                        "created_at": format_api_datetime(msg["created_at"]),
                    }
                    for msg in messages_result.data
                ],
            }
        except HTTPException:
            raise
        except Exception as e:
            logger.error("Failed to get project", error=str(e))
            raise HTTPException(status_code=500, detail="Failed to get project")
    
    # Unsupported mode
    raise HTTPException(status_code=500, detail="Unsupported database_mode for getting project")


@router.patch("/{project_id}", response_model=ProjectResponse)
async def update_project(
    project_id: str,
    request: ProjectUpdate,
    current_user: dict = Depends(get_current_user)
):
    """Update project fields.

    Supports two independent, optional fields:

    - ``title``: classic rename (back-compat with pre-2026-04 callers).
    - ``context_usage``: realtime context-usage ring snapshot. The sentinel
      ``_UNSET_CONTEXT_USAGE`` means "field absent — do not touch the
      column". An explicit ``null`` clears the column AND bumps
      ``context_usage_updated_at``. Any dict is stored verbatim (we treat
      it as an opaque jsonb payload; validation lives on the frontend).

    At least one of the two fields must be present; otherwise we 400 so
    clients don't silently no-op.
    """
    settings = get_settings()

    title_present = request.title is not None
    usage_present = request.context_usage != _UNSET_CONTEXT_USAGE
    if not title_present and not usage_present:
        raise HTTPException(status_code=400, detail="No updatable fields provided")

    # Validate the context_usage payload shape minimally. A full-featured
    # schema check would belong in the frontend persistence layer; here we
    # just reject obvious non-object shapes so the jsonb column stays sane.
    usage_value: Optional[Dict[str, Any]] = None
    if usage_present and request.context_usage is not None:
        if not isinstance(request.context_usage, dict):
            raise HTTPException(
                status_code=400,
                detail="context_usage must be a JSON object or null",
            )
        usage_value = request.context_usage

    # Local database-backed projects
    if settings.database_mode == "local":
        pool = await get_pg_pool()

        # Build a parameterised UPDATE that only touches the requested
        # columns. ``updated_at`` is bumped on every PATCH (handled by the
        # existing trigger); ``context_usage_updated_at`` is bumped only
        # when context_usage is present (including null).
        set_clauses: List[str] = []
        params: List[Any] = []

        if title_present:
            params.append(request.title)
            set_clauses.append(f"title = ${len(params)}")

        if usage_present:
            # jsonb column: asyncpg accepts dicts via native codec; for
            # explicit null we pass Python None which becomes SQL NULL.
            params.append(json.dumps(usage_value) if usage_value is not None else None)
            set_clauses.append(f"context_usage = ${len(params)}::jsonb")
            set_clauses.append("context_usage_updated_at = now()")

        # Always bump ``updated_at`` so the row appears fresh in the
        # sidebar even if only context_usage changed. (Matches previous
        # title-only behaviour.)
        set_clauses.append("updated_at = now()")

        params.append(project_id)
        project_id_pos = len(params)
        params.append(current_user["id"])
        user_id_pos = len(params)

        query = f"""
            UPDATE projects
            SET {", ".join(set_clauses)}
            WHERE id = ${project_id_pos} AND user_id = ${user_id_pos}
            RETURNING id, title, created_at, updated_at,
                      context_usage, context_usage_updated_at
            """

        async with pool.acquire() as conn:
            row = await conn.fetchrow(query, *params)

            if not row:
                raise HTTPException(status_code=404, detail="Project not found")

            return {
                "id": str(row["id"]),
                "title": row["title"],
                "created_at": format_api_datetime(row["created_at"]),
                "updated_at": format_api_datetime(row["updated_at"]),
                "context_usage": _serialize_context_usage(row.get("context_usage")),
                "context_usage_updated_at": (
                    format_api_datetime(row["context_usage_updated_at"])
                    if row.get("context_usage_updated_at") is not None
                    else None
                ),
            }

    # Supabase-backed projects
    if settings.database_mode == "supabase":
        try:
            client = get_supabase_client()
            updates: Dict[str, Any] = {}
            if title_present:
                updates["title"] = request.title
            if usage_present:
                # Supabase client accepts ``None`` as SQL NULL. We pass the
                # stamped timestamp as an ISO string so it matches asyncpg
                # semantics. NOTE: Postgres' ``now()`` would be preferable
                # but supabase-py doesn't allow raw SQL expressions in
                # ``update()``; ISO-now is close enough and still monotonic.
                from datetime import datetime, timezone

                updates["context_usage"] = usage_value
                updates["context_usage_updated_at"] = (
                    datetime.now(tz=timezone.utc).isoformat()
                )

            result = client.table("projects").update(updates).eq(
                "id", project_id
            ).eq("user_id", current_user["id"]).execute()

            if not result.data:
                raise HTTPException(status_code=404, detail="Project not found")

            row = result.data[0]
            return {
                "id": str(row["id"]),
                "title": row["title"],
                "created_at": format_api_datetime(row["created_at"]),
                "updated_at": format_api_datetime(row["updated_at"]),
                "context_usage": _serialize_context_usage(row.get("context_usage")),
                "context_usage_updated_at": (
                    format_api_datetime(row["context_usage_updated_at"])
                    if row.get("context_usage_updated_at") is not None
                    else None
                ),
            }
        except HTTPException:
            raise
        except Exception as e:
            logger.error("Failed to update project", error=str(e))
            raise HTTPException(status_code=500, detail="Failed to update project")

    # Unsupported mode
    raise HTTPException(status_code=500, detail="Unsupported database_mode for updating project")


@router.delete("/{project_id}")
async def delete_project(
    project_id: str,
    current_user: dict = Depends(get_current_user)
):
    """Delete a project."""
    settings = get_settings()
    
    # Local database-backed projects
    if settings.database_mode == "local":
        pool = await get_pg_pool()
        
        async with pool.acquire() as conn:
            result = await conn.execute(
                """
                DELETE FROM projects
                WHERE id = $1 AND user_id = $2
                """,
                project_id, current_user["id"]
            )
            
            if result == "DELETE 0":
                raise HTTPException(status_code=404, detail="Project not found")
            
            return {"message": "Project deleted"}
    
    # Supabase-backed projects
    if settings.database_mode == "supabase":
        try:
            client = get_supabase_client()
            result = client.table("projects").delete().eq("id", project_id).eq("user_id", current_user["id"]).execute()
            
            if not result.data:
                raise HTTPException(status_code=404, detail="Project not found")
            
            return {"message": "Project deleted"}
        except HTTPException:
            raise
        except Exception as e:
            logger.error("Failed to delete project", error=str(e))
            raise HTTPException(status_code=500, detail="Failed to delete project")
    
    # Unsupported mode
    raise HTTPException(status_code=500, detail="Unsupported database_mode for deleting project")
