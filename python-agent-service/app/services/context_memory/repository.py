"""Postgres / Supabase persistence with application-level tenant checks."""

from __future__ import annotations

from typing import Any

import structlog
from app.config import get_settings
from app.datetime_support import format_api_datetime, now_app
from app.db import get_pg_pool, get_supabase_client

logger = structlog.get_logger()


async def verify_project_owner(project_id: str, user_id: str) -> bool:
    settings = get_settings()
    if settings.database_mode == "memory":
        return False
    if settings.database_mode == "local":
        pool = await get_pg_pool()
        async with pool.acquire() as conn:
            row = await conn.fetchrow(
                "SELECT 1 FROM projects WHERE id = $1::uuid AND user_id = $2::uuid",
                project_id,
                user_id,
            )
            return row is not None
    client = get_supabase_client()
    r = (
        client.table("projects")
        .select("id")
        .eq("id", project_id)
        .eq("user_id", user_id)
        .execute()
    )
    return bool(r.data)


async def merge_already_processed(project_id: str, request_id: str) -> bool:
    settings = get_settings()
    if settings.database_mode == "local":
        pool = await get_pg_pool()
        async with pool.acquire() as conn:
            row = await conn.fetchrow(
                """
                SELECT 1 FROM context_memory_merge_log
                WHERE project_id = $1::uuid AND request_id = $2
                """,
                project_id,
                request_id,
            )
            return row is not None
    client = get_supabase_client()
    r = (
        client.table("context_memory_merge_log")
        .select("project_id")
        .eq("project_id", project_id)
        .eq("request_id", request_id)
        .execute()
    )
    return bool(r.data)


async def record_merge_processed(project_id: str, request_id: str) -> None:
    """Mark request_id merged (idempotency). Duplicate inserts are ignored."""
    settings = get_settings()
    if settings.database_mode == "local":
        pool = await get_pg_pool()
        async with pool.acquire() as conn:
            try:
                await conn.execute(
                    """
                    INSERT INTO context_memory_merge_log (project_id, request_id)
                    VALUES ($1::uuid, $2)
                    ON CONFLICT (project_id, request_id) DO NOTHING
                    """,
                    project_id,
                    request_id,
                )
            except Exception as e:
                logger.warning("merge_log insert failed", error=str(e))
        return
    client = get_supabase_client()
    try:
        client.table("context_memory_merge_log").insert(
            {
                "project_id": project_id,
                "request_id": request_id,
                "merged_at": format_api_datetime(now_app()),
            }
        ).execute()
    except Exception as e:
        logger.debug("merge_log insert skipped or duplicate", error=str(e))


async def fetch_project_title(project_id: str, user_id: str) -> str:
    settings = get_settings()
    if settings.database_mode == "local":
        pool = await get_pg_pool()
        async with pool.acquire() as conn:
            row = await conn.fetchrow(
                "SELECT title FROM projects WHERE id = $1::uuid AND user_id = $2::uuid",
                project_id,
                user_id,
            )
            return str(row["title"]) if row and row.get("title") else ""
    client = get_supabase_client()
    r = (
        client.table("projects")
        .select("title")
        .eq("id", project_id)
        .eq("user_id", user_id)
        .execute()
    )
    if r.data:
        return str(r.data[0].get("title") or "")
    return ""


async def load_project_derived(project_id: str, user_id: str) -> dict[str, Any] | None:
    if not await verify_project_owner(project_id, user_id):
        return None
    settings = get_settings()
    if settings.database_mode == "local":
        pool = await get_pg_pool()
        async with pool.acquire() as conn:
            row = await conn.fetchrow(
                """
                SELECT payload FROM project_derived_memory
                WHERE project_id = $1::uuid AND user_id = $2::uuid
                """,
                project_id,
                user_id,
            )
            if not row:
                return None
            return dict(row["payload"]) if row.get("payload") else {}
    client = get_supabase_client()
    r = (
        client.table("project_derived_memory")
        .select("payload")
        .eq("project_id", project_id)
        .eq("user_id", user_id)
        .execute()
    )
    if not r.data:
        return None
    return dict(r.data[0].get("payload") or {})


async def save_project_derived(
    project_id: str, user_id: str, payload: dict[str, Any]
) -> None:
    if not await verify_project_owner(project_id, user_id):
        logger.warning("save_project_derived denied", project_id=project_id)
        return
    settings = get_settings()
    now = now_app()
    if settings.database_mode == "local":
        pool = await get_pg_pool()
        async with pool.acquire() as conn:
            await conn.execute(
                """
                INSERT INTO project_derived_memory (project_id, user_id, payload, updated_at)
                VALUES ($1::uuid, $2::uuid, $3::jsonb, $4)
                ON CONFLICT (project_id) DO UPDATE SET
                  payload = EXCLUDED.payload,
                  updated_at = EXCLUDED.updated_at,
                  user_id = EXCLUDED.user_id
                """,
                project_id,
                user_id,
                payload,
                now,
            )
        return
    client = get_supabase_client()
    client.table("project_derived_memory").upsert(
        {
            "project_id": project_id,
            "user_id": user_id,
            "payload": payload,
            "updated_at": format_api_datetime(now),
        },
        on_conflict="project_id",
    ).execute()


async def load_user_index(user_id: str) -> dict[str, Any] | None:
    settings = get_settings()
    if settings.database_mode == "local":
        pool = await get_pg_pool()
        async with pool.acquire() as conn:
            row = await conn.fetchrow(
                "SELECT payload FROM user_memory_index WHERE user_id = $1::uuid",
                user_id,
            )
            if not row:
                return None
            return dict(row["payload"]) if row.get("payload") else {}
    client = get_supabase_client()
    r = client.table("user_memory_index").select("payload").eq("user_id", user_id).execute()
    if not r.data:
        return None
    return dict(r.data[0].get("payload") or {})


async def save_user_index(user_id: str, payload: dict[str, Any]) -> None:
    settings = get_settings()
    now = now_app()
    if settings.database_mode == "local":
        pool = await get_pg_pool()
        async with pool.acquire() as conn:
            await conn.execute(
                """
                INSERT INTO user_memory_index (user_id, payload, updated_at)
                VALUES ($1::uuid, $2::jsonb, $3)
                ON CONFLICT (user_id) DO UPDATE SET
                  payload = EXCLUDED.payload,
                  updated_at = EXCLUDED.updated_at
                """,
                user_id,
                payload,
                now,
            )
        return
    client = get_supabase_client()
    client.table("user_memory_index").upsert(
        {
            "user_id": user_id,
            "payload": payload,
            "updated_at": format_api_datetime(now),
        },
        on_conflict="user_id",
    ).execute()


async def fetch_recent_messages_for_hydrate(
    project_id: str, user_id: str, max_pairs: int
) -> list[tuple[str, str]]:
    """Return (role, content) pairs: user then assistant per turn, newest last."""
    if max_pairs <= 0:
        return []
    if not await verify_project_owner(project_id, user_id):
        return []
    limit = max(1, max_pairs * 2)
    settings = get_settings()
    if settings.database_mode == "local":
        pool = await get_pg_pool()
        async with pool.acquire() as conn:
            rows = await conn.fetch(
                """
                SELECT type, content FROM (
                  SELECT type, content, created_at FROM messages
                  WHERE project_id = $1::uuid AND user_id = $2::uuid
                  ORDER BY created_at DESC
                  LIMIT $3
                ) sub ORDER BY created_at ASC
                """,
                project_id,
                user_id,
                limit,
            )
            return [(str(r["type"]), str(r["content"] or "")) for r in rows]
    client = get_supabase_client()
    r = (
        client.table("messages")
        .select("type,content,created_at")
        .eq("project_id", project_id)
        .eq("user_id", user_id)
        .order("created_at", desc=True)
        .limit(limit)
        .execute()
    )
    raw = list(r.data or [])
    raw.reverse()
    out: list[tuple[str, str]] = []
    for row in raw:
        out.append((str(row.get("type") or ""), str(row.get("content") or "")))
    return out


def _preview_content(text: str | None, max_chars: int) -> tuple[str, bool]:
    s = (text or "").strip()
    if len(s) <= max_chars:
        return s, False
    return s[:max_chars] + "…", True


async def search_project_messages(
    project_id: str,
    user_id: str,
    *,
    query: str | None,
    limit: int,
    request_id_filter: str | None,
    content_preview_max: int = 800,
) -> dict[str, Any]:
    """Read-only search over persisted ``messages`` for a project (tenant-scoped).

    Returns ``{"ok": bool, "matches": [...], "error"?: str, "note"?: str}``.
    """
    if limit < 1:
        limit = 1
    if limit > 50:
        limit = 50

    settings = get_settings()
    if settings.database_mode == "memory":
        return {
            "ok": True,
            "matches": [],
            "note": "database_mode=memory: no persisted messages to search",
        }

    if not await verify_project_owner(project_id, user_id):
        return {"ok": False, "error": "access_denied", "matches": []}

    q = (query or "").strip() or None
    rid = (request_id_filter or "").strip() or None

    if settings.database_mode == "local":
        pool = await get_pg_pool()
        async with pool.acquire() as conn:
            rows = await conn.fetch(
                """
                SELECT id, type, request_id, created_at, content
                FROM messages
                WHERE project_id = $1::uuid AND user_id = $2::uuid
                  AND ($3::text IS NULL OR $3 = '' OR position(lower($3) IN lower(coalesce(content, ''))) > 0)
                  AND ($4::text IS NULL OR request_id = $4)
                ORDER BY created_at DESC
                LIMIT $5
                """,
                project_id,
                user_id,
                q,
                rid,
                limit,
            )
            matches: list[dict[str, Any]] = []
            for r in rows:
                raw_content = r.get("content")
                preview, truncated = _preview_content(
                    str(raw_content) if raw_content is not None else None,
                    content_preview_max,
                )
                ca = r.get("created_at")
                matches.append(
                    {
                        "id": str(r["id"]),
                        "type": str(r["type"] or ""),
                        "request_id": str(r["request_id"] or ""),
                        "created_at": format_api_datetime(ca)
                        if ca is not None
                        else "",
                        "content_preview": preview,
                        "truncated": truncated,
                    }
                )
            return {"ok": True, "matches": matches}

    client = get_supabase_client()
    sel = (
        client.table("messages")
        .select("id,type,request_id,created_at,content")
        .eq("project_id", project_id)
        .eq("user_id", user_id)
    )
    if rid:
        sel = sel.eq("request_id", rid)
    fetch_limit = limit if not q else min(max(limit * 15, limit), 400)
    r = sel.order("created_at", desc=True).limit(fetch_limit).execute()
    raw_rows = list(r.data or [])
    if q:
        q_lower = q.lower()
        raw_rows = [
            row
            for row in raw_rows
            if q_lower in (str(row.get("content") or "").lower())
        ][:limit]
    else:
        raw_rows = raw_rows[:limit]

    matches = []
    for row in raw_rows:
        preview, truncated = _preview_content(
            str(row.get("content") or ""),
            content_preview_max,
        )
        ca = row.get("created_at")
        matches.append(
            {
                "id": str(row.get("id") or ""),
                "type": str(row.get("type") or ""),
                "request_id": str(row.get("request_id") or ""),
                "created_at": format_api_datetime(ca) if ca is not None else "",
                "content_preview": preview,
                "truncated": truncated,
            }
        )
    return {"ok": True, "matches": matches}
