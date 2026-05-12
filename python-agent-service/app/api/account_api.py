"""Account overview aggregates (projects, analyses, lifetime tokens)."""

from __future__ import annotations

import asyncio
from typing import Any

import structlog
from app.api.auth import get_current_user
from app.config import get_settings
from app.db import get_pg_pool, get_supabase_client
from fastapi import APIRouter, Depends

logger = structlog.get_logger()

router = APIRouter(prefix="/account", tags=["account"])


async def _overview_local_async(user_id: str) -> dict[str, Any]:
    pool = await get_pg_pool()
    async with pool.acquire() as conn:
        project_count = int(
            await conn.fetchval(
                "SELECT COUNT(*)::int FROM projects WHERE user_id = $1",
                user_id,
            )
            or 0
        )
        try:
            analysis_count = int(
                await conn.fetchval(
                    """
                    SELECT COUNT(*)::int FROM messages m
                    INNER JOIN projects p ON p.id = m.project_id
                    WHERE p.user_id = $1::uuid AND m.type = 'assistant'
                    AND (
                      COALESCE(jsonb_array_length(m.timeline), 0) > 0
                      OR (
                        m.blocks IS NOT NULL
                        AND m.blocks != '[]'::jsonb
                        AND m.blocks != 'null'::jsonb
                      )
                    )
                    """,
                    user_id,
                )
                or 0
            )
        except Exception as e:
            logger.warning("overview_analysis_count_failed", error=str(e))
            analysis_count = 0

        total_tokens = 0
        try:
            row = await conn.fetchrow(
                """
                SELECT COALESCE(
                    SUM(prompt_tokens + completion_tokens), 0
                )::bigint AS t
                FROM llm_usage_events
                WHERE user_id = $1::uuid
                """,
                user_id,
            )
            if row and row["t"] is not None:
                total_tokens = int(row["t"])
        except Exception:
            pass

    return {
        "project_count": project_count,
        "analysis_sessions_count": analysis_count,
        "total_llm_tokens_lifetime": total_tokens,
    }


def _overview_supabase_sync(user_id: str) -> dict[str, Any]:
    client = get_supabase_client()
    projs = (
        client.table("projects").select("id").eq("user_id", user_id).execute()
    )
    ids = [str(r["id"]) for r in (projs.data or [])]
    project_count = len(ids)
    analysis_count = 0
    chunk_size = 80
    for i in range(0, len(ids), chunk_size):
        chunk = ids[i:i + chunk_size]
        msg = (
            client.table("messages")
            .select("timeline,blocks")
            .in_("project_id", chunk)
            .eq("type", "assistant")
            .execute()
        )
        for r in msg.data or []:
            tl = r.get("timeline")
            has_tl = isinstance(tl, list) and len(tl) > 0
            bl = r.get("blocks")
            has_bl = bl is not None and bl != [] and bl != {}
            if has_tl or has_bl:
                analysis_count += 1

    total_tokens = 0
    try:
        rpc = client.rpc(
            "sum_llm_tokens_for_user", {"p_user_id": user_id}
        ).execute()
        if rpc.data is not None:
            total_tokens = int(rpc.data)
    except Exception as e:
        logger.warning("overview_token_sum_rpc_failed", error=str(e))
        try:
            usage = (
                client.table("llm_usage_events")
                .select("prompt_tokens,completion_tokens")
                .eq("user_id", user_id)
                .limit(50_000)
                .execute()
            )
            for r in usage.data or []:
                total_tokens += int(r.get("prompt_tokens") or 0) + int(
                    r.get("completion_tokens") or 0
                )
        except Exception as e2:
            logger.warning("overview_token_sum_fallback_failed", error=str(e2))

    return {
        "project_count": project_count,
        "analysis_sessions_count": analysis_count,
        "total_llm_tokens_lifetime": total_tokens,
    }


@router.get("/overview")
async def get_account_overview(current_user: dict = Depends(get_current_user)):
    """Aggregates for the account overview page."""
    settings = get_settings()
    uid = current_user["id"]
    if settings.database_mode == "local":
        return await _overview_local_async(uid)
    if settings.database_mode == "supabase":
        return await asyncio.to_thread(_overview_supabase_sync, uid)
    return {
        "project_count": 0,
        "analysis_sessions_count": 0,
        "total_llm_tokens_lifetime": 0,
    }
