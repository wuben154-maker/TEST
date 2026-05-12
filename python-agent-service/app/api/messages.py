"""Messages API routes."""

import json
from typing import Any, List, Optional, Union
from uuid import uuid4

import structlog
from app.api.auth import get_current_user
from app.config import get_settings
from app.datetime_support import format_api_datetime, now_app
from app.db import get_pg_pool, get_supabase_client
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

logger = structlog.get_logger()
router = APIRouter(prefix="/messages", tags=["messages"])


class MessageCreate(BaseModel):
    project_id: str
    type: str  # 'user' or 'assistant'
    content: str
    request_id: Optional[str] = None
    reasoning: Optional[str] = None
    # Frontend may send list or {steps: [...], __extended: {...}} for round-trip
    thinking_steps: Optional[Union[List[dict], dict]] = None
    blocks: Optional[List[dict]] = None
    # Canonical SSE timeline (schemaVersion 1); default [] when column exists
    timeline: Optional[List[dict]] = None
    stats: Optional[dict] = None
    workspace_tabs: Optional[List[dict]] = None


class MessageResponse(BaseModel):
    id: str
    project_id: str
    type: str
    content: str
    request_id: Optional[str] = None
    reasoning: Optional[str]
    thinking_steps: Optional[Any] = None  # list or {steps, __extended}
    blocks: Optional[Any] = None
    timeline: Optional[Any] = None
    stats: Optional[Any] = None
    workspace_tabs: Optional[Any] = None
    workspace_title: Optional[str] = None
    knowledge_archive: Optional[Any] = None
    created_at: str


class MessageTitleUpdate(BaseModel):
    title: str


class KnowledgeArchivePatch(BaseModel):
    """Persist knowledge-base deeplink on the assistant row for ``request_id`` (analysis run id)."""

    project_id: str
    request_id: str
    knowledge_archive: dict


@router.post("", response_model=MessageResponse)
async def create_message(
    request: MessageCreate,
    current_user: dict = Depends(get_current_user)
):
    """Create a new message."""
    settings = get_settings()
    
    # Local database-backed messages
    if settings.database_mode == "local":
        try:
            pool = await get_pg_pool()
        except Exception as e:
            logger.error("Failed to get PostgreSQL pool", error=str(e))
            raise HTTPException(status_code=503, detail=f"Database unavailable: {e}")
        message_id = str(uuid4())
        # Pass Python objects for JSONB; asyncpg serializes automatically
        thinking_val = request.thinking_steps
        blocks_val = request.blocks
        timeline_val = request.timeline if request.timeline is not None else []
        stats_val = request.stats
        wtabs_val = request.workspace_tabs

        async with pool.acquire() as conn:
            # Verify project belongs to user
            project = await conn.fetchrow(
                "SELECT id FROM projects WHERE id = $1 AND user_id = $2",
                request.project_id, current_user["id"]
            )

            if not project:
                raise HTTPException(status_code=404, detail="Project not found")

            # Insert message
            try:
                row = await conn.fetchrow(
                    """
                    INSERT INTO messages (id, project_id, user_id, type, content, request_id, reasoning, thinking_steps, blocks, timeline, stats, workspace_tabs, knowledge_archive)
                    VALUES ($1, $2, $3, $4, $5, $6, $7, $8::jsonb, $9::jsonb, $10::jsonb, $11::jsonb, $12::jsonb, NULL::jsonb)
                    ON CONFLICT (project_id, request_id, type)
                    DO UPDATE SET
                        content = EXCLUDED.content,
                        reasoning = EXCLUDED.reasoning,
                        thinking_steps = EXCLUDED.thinking_steps,
                        blocks = EXCLUDED.blocks,
                        timeline = EXCLUDED.timeline,
                        stats = EXCLUDED.stats,
                        workspace_tabs = EXCLUDED.workspace_tabs,
                        knowledge_archive = COALESCE(messages.knowledge_archive, EXCLUDED.knowledge_archive)
                    RETURNING id, project_id, type, content, request_id, reasoning, thinking_steps, blocks, timeline, stats, workspace_tabs, knowledge_archive, created_at
                    """,
                    message_id,
                    request.project_id,
                    current_user["id"],
                    request.type,
                    request.content,
                    request.request_id,
                    request.reasoning,
                    json.dumps(thinking_val) if thinking_val is not None else None,
                    json.dumps(blocks_val) if blocks_val is not None else None,
                    json.dumps(timeline_val),
                    json.dumps(stats_val) if stats_val is not None else None,
                    json.dumps(wtabs_val) if wtabs_val is not None else None,
                )
            except Exception as e:
                logger.error("Failed to insert message", error=str(e), project_id=request.project_id)
                raise HTTPException(status_code=500, detail=str(e))
            
            # Update project timestamp
            await conn.execute(
                "UPDATE projects SET updated_at = now() WHERE id = $1",
                request.project_id
            )
            
            # Auto-update title from first user message
            if request.type == "user":
                msg_count = await conn.fetchval(
                    "SELECT COUNT(*) FROM messages WHERE project_id = $1",
                    request.project_id
                )
                if msg_count == 1:  # First message
                    new_title = request.content[:30] + ("..." if len(request.content) > 30 else "")
                    await conn.execute(
                        "UPDATE projects SET title = $1 WHERE id = $2",
                        new_title, request.project_id
                    )
            
            def _ensure_list(val):
                if val is None:
                    return None
                if isinstance(val, (list, dict)):
                    return val
                try:
                    return json.loads(val) if isinstance(val, str) else None
                except Exception:
                    return None

            return {
                "id": str(row["id"]),
                "project_id": str(row["project_id"]),
                "type": row["type"],
                "content": row["content"],
                "request_id": row["request_id"],
                "reasoning": row["reasoning"],
                "thinking_steps": _ensure_list(row["thinking_steps"]),
                "blocks": _ensure_list(row["blocks"]),
                "timeline": _ensure_list(row.get("timeline")) or [],
                "stats": _ensure_list(row.get("stats")),
                "workspace_tabs": _ensure_list(row.get("workspace_tabs")),
                "knowledge_archive": _ensure_list(row.get("knowledge_archive")),
                "created_at": format_api_datetime(row["created_at"]),
            }
    
    # Supabase-backed messages
    if settings.database_mode == "supabase":
        try:
            client = get_supabase_client()
            
            # Verify project belongs to user
            project_result = client.table("projects").select("id").eq("id", request.project_id).eq("user_id", current_user["id"]).execute()
            
            if not project_result.data:
                raise HTTPException(status_code=404, detail="Project not found")
            
            # Insert message (Supabase handles JSONB directly as dict)
            result = client.table("messages").upsert({
                "project_id": request.project_id,
                "user_id": current_user["id"],
                "type": request.type,
                "content": request.content,
                "request_id": request.request_id,
                "reasoning": request.reasoning,
                "thinking_steps": request.thinking_steps,
                "blocks": request.blocks,
                "timeline": request.timeline if request.timeline is not None else [],
                "stats": request.stats,
                "workspace_tabs": request.workspace_tabs,
            }, on_conflict="project_id,request_id,type").execute()
            
            if not result.data:
                raise HTTPException(status_code=500, detail="Failed to create message")
            
            row = result.data[0]
            
            # Update project timestamp (Supabase will handle updated_at via trigger)
            # We can trigger an update by updating a field, but since we don't want to change anything,
            # we'll let the database trigger handle it automatically
            # Alternatively, we can update updated_at explicitly if needed
            client.table("projects").update({
                "updated_at": format_api_datetime(now_app())
            }).eq("id", request.project_id).execute()
            
            # Auto-update title from first user message
            if request.type == "user":
                messages_result = client.table("messages").select("id").eq("project_id", request.project_id).execute()
                if len(messages_result.data) == 1:  # First message
                    new_title = request.content[:30] + ("..." if len(request.content) > 30 else "")
                    client.table("projects").update({
                        "title": new_title
                    }).eq("id", request.project_id).execute()
            
            return {
                "id": str(row["id"]),
                "project_id": str(row["project_id"]),
                "type": row["type"],
                "content": row["content"],
                "request_id": row.get("request_id"),
                "reasoning": row["reasoning"],
                "thinking_steps": row["thinking_steps"],
                "blocks": row["blocks"],
                "timeline": row.get("timeline") or [],
                "stats": row.get("stats"),
                "workspace_tabs": row.get("workspace_tabs"),
                "knowledge_archive": row.get("knowledge_archive"),
                "created_at": format_api_datetime(row["created_at"]),
            }
        except HTTPException:
            raise
        except Exception as e:
            logger.error("Failed to create message", error=str(e))
            err_lower = str(e).lower()
            if "row-level security" in err_lower or ("violates" in err_lower and "policy" in err_lower):
                raise HTTPException(
                    status_code=500,
                    detail="Database permission denied. Ensure SUPABASE_SERVICE_ROLE_KEY is set in .env (Supabase Dashboard > Settings > API).",
                )
            raise HTTPException(status_code=500, detail="Failed to create message")
    
    # Unsupported mode
    raise HTTPException(status_code=500, detail="Unsupported database_mode for creating message")


@router.get("/project/{project_id}", response_model=List[MessageResponse])
async def get_project_messages(
    project_id: str,
    limit: int = 100,
    current_user: dict = Depends(get_current_user)
):
    """Get messages for a project."""
    settings = get_settings()
    
    # Local database-backed messages
    if settings.database_mode == "local":
        try:
            pool = await get_pg_pool()
        except Exception as e:
            logger.error("Failed to get PostgreSQL pool", error=str(e))
            raise HTTPException(status_code=503, detail=f"Database unavailable: {e}")
        try:
            async with pool.acquire() as conn:
                # Verify project belongs to user
                project = await conn.fetchrow(
                    "SELECT id FROM projects WHERE id = $1 AND user_id = $2",
                    project_id, current_user["id"]
                )

                if not project:
                    raise HTTPException(status_code=404, detail="Project not found")

                # Get messages
                rows = await conn.fetch(
                    """
                    SELECT id, project_id, type, content, request_id, reasoning, thinking_steps, blocks, workspace_title, timeline, stats, workspace_tabs, knowledge_archive, created_at
                    FROM (
                        SELECT id, project_id, type, content, request_id, reasoning, thinking_steps, blocks, workspace_title, timeline, stats, workspace_tabs, knowledge_archive, created_at
                        FROM messages
                        WHERE project_id = $1
                        ORDER BY created_at DESC
                        LIMIT $2
                    ) recent
                    ORDER BY created_at ASC
                    """,
                    project_id, limit
                )

                def _ensure_serializable(val):
                    if val is None:
                        return None
                    if isinstance(val, (list, dict)):
                        return val
                    try:
                        return json.loads(val) if isinstance(val, str) else None
                    except Exception:
                        return None

                return [
                    {
                        "id": str(row["id"]),
                        "project_id": str(row["project_id"]),
                        "type": row["type"],
                        "content": row["content"],
                        "request_id": row["request_id"],
                        "reasoning": row["reasoning"],
                        "thinking_steps": _ensure_serializable(row["thinking_steps"]),
                        "blocks": _ensure_serializable(row["blocks"]),
                        "timeline": _ensure_serializable(row.get("timeline")) or [],
                        "stats": _ensure_serializable(row.get("stats")),
                        "workspace_tabs": _ensure_serializable(row.get("workspace_tabs")),
                        "workspace_title": row.get("workspace_title"),
                        "knowledge_archive": _ensure_serializable(row.get("knowledge_archive")),
                        "created_at": format_api_datetime(row["created_at"]),
                    }
                    for row in rows
                ]
        except HTTPException:
            raise
        except Exception as e:
            logger.error("Failed to get project messages", error=str(e), project_id=project_id)
            raise HTTPException(status_code=500, detail=str(e))
    
    # Supabase-backed messages
    if settings.database_mode == "supabase":
        try:
            client = get_supabase_client()
            
            # Verify project belongs to user
            project_result = client.table("projects").select("id").eq("id", project_id).eq("user_id", current_user["id"]).execute()
            
            if not project_result.data:
                raise HTTPException(status_code=404, detail="Project not found")
            
            # Get messages
            # Keep API behavior consistent with local mode:
            # fetch latest N first, then return in ascending order for frontend timeline rendering.
            result = (
                client.table("messages")
                .select("*")
                .eq("project_id", project_id)
                .order("created_at", desc=True)
                .limit(limit)
                .execute()
            )
            rows = list(reversed(result.data or []))
            
            return [
                {
                    "id": str(row["id"]),
                    "project_id": str(row["project_id"]),
                    "type": row["type"],
                    "content": row["content"],
                    "request_id": row.get("request_id"),
                    "reasoning": row["reasoning"],
                    "thinking_steps": row["thinking_steps"],
                    "blocks": row["blocks"],
                    "timeline": row.get("timeline") or [],
                    "stats": row.get("stats"),
                    "workspace_tabs": row.get("workspace_tabs"),
                    "workspace_title": row.get("workspace_title"),
                    "knowledge_archive": row.get("knowledge_archive"),
                    "created_at": format_api_datetime(row["created_at"]),
                }
                for row in rows
            ]
        except HTTPException:
            raise
        except Exception as e:
            logger.error("Failed to get project messages", error=str(e))
            raise HTTPException(status_code=500, detail="Failed to get project messages")
    
    # Unsupported mode
    raise HTTPException(status_code=500, detail="Unsupported database_mode for getting project messages")


@router.patch("/knowledge-archive")
async def patch_message_knowledge_archive(
    body: KnowledgeArchivePatch,
    current_user: dict = Depends(get_current_user),
):
    """Set ``knowledge_archive`` JSON so the chat survives page refresh."""
    settings = get_settings()
    payload_json = json.dumps(body.knowledge_archive)

    if settings.database_mode == "local":
        try:
            pool = await get_pg_pool()
        except Exception as e:
            logger.error("Failed to get PostgreSQL pool", error=str(e))
            raise HTTPException(status_code=503, detail=f"Database unavailable: {e}")
        async with pool.acquire() as conn:
            r = await conn.execute(
                """
                UPDATE messages SET knowledge_archive = $1::jsonb
                WHERE project_id = $2 AND user_id = $3 AND request_id = $4 AND type = 'assistant'
                """,
                payload_json,
                body.project_id,
                current_user["id"],
                body.request_id,
            )
            if r == "UPDATE 0":
                raise HTTPException(status_code=404, detail="Assistant message not found for this request")
        return {"message": "Knowledge archive updated"}

    if settings.database_mode == "supabase":
        try:
            client = get_supabase_client()
            result = (
                client.table("messages")
                .update({"knowledge_archive": body.knowledge_archive})
                .eq("project_id", body.project_id)
                .eq("user_id", current_user["id"])
                .eq("request_id", body.request_id)
                .eq("type", "assistant")
                .execute()
            )
            if not result.data:
                raise HTTPException(status_code=404, detail="Assistant message not found for this request")
            return {"message": "Knowledge archive updated"}
        except HTTPException:
            raise
        except Exception as e:
            logger.error("Failed to patch knowledge archive", error=str(e))
            raise HTTPException(status_code=500, detail="Failed to update knowledge archive")

    raise HTTPException(status_code=500, detail="Unsupported database_mode")


@router.patch("/{message_id}/title")
async def update_message_title(
    message_id: str,
    body: MessageTitleUpdate,
    current_user: dict = Depends(get_current_user),
):
    """Update the workspace tab title of a message."""
    settings = get_settings()

    if settings.database_mode == "local":
        pool = await get_pg_pool()
        async with pool.acquire() as conn:
            result = await conn.execute(
                "UPDATE messages SET workspace_title = $1 WHERE id = $2 AND user_id = $3",
                body.title,
                message_id,
                current_user["id"],
            )
            if result == "UPDATE 0":
                raise HTTPException(status_code=404, detail="Message not found")
            return {"message": "Title updated"}

    if settings.database_mode == "supabase":
        try:
            client = get_supabase_client()
            result = (
                client.table("messages")
                .update({"workspace_title": body.title})
                .eq("id", message_id)
                .eq("user_id", current_user["id"])
                .execute()
            )
            if not result.data:
                raise HTTPException(status_code=404, detail="Message not found")
            return {"message": "Title updated"}
        except HTTPException:
            raise
        except Exception as e:
            logger.error("Failed to update message title", error=str(e))
            raise HTTPException(status_code=500, detail="Failed to update message title")

    raise HTTPException(status_code=500, detail="Unsupported database_mode")


@router.delete("/{message_id}")
async def delete_message(
    message_id: str,
    current_user: dict = Depends(get_current_user)
):
    """Delete a message."""
    settings = get_settings()
    
    # Local database-backed messages
    if settings.database_mode == "local":
        pool = await get_pg_pool()
        
        async with pool.acquire() as conn:
            result = await conn.execute(
                """
                DELETE FROM messages
                WHERE id = $1 AND user_id = $2
                """,
                message_id, current_user["id"]
            )
            
            if result == "DELETE 0":
                raise HTTPException(status_code=404, detail="Message not found")
            
            return {"message": "Message deleted"}
    
    # Supabase-backed messages
    if settings.database_mode == "supabase":
        try:
            client = get_supabase_client()
            result = client.table("messages").delete().eq("id", message_id).eq("user_id", current_user["id"]).execute()
            
            if not result.data:
                raise HTTPException(status_code=404, detail="Message not found")
            
            return {"message": "Message deleted"}
        except HTTPException:
            raise
        except Exception as e:
            logger.error("Failed to delete message", error=str(e))
            raise HTTPException(status_code=500, detail="Failed to delete message")
    
    # Unsupported mode
    raise HTTPException(status_code=500, detail="Unsupported database_mode for deleting message")
