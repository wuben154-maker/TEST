"""Record and list user login events (local PostgreSQL and Supabase)."""

from __future__ import annotations

import asyncio
import uuid
from typing import Any, Optional

import structlog
from app.config import get_settings
from app.datetime_support import format_api_datetime
from app.db import get_pg_pool, get_supabase_client
from app.services.ip_geo import resolve_ip_country_label

logger = structlog.get_logger()


async def record_login_event_async(
    user_id: str,
    ip_address: Optional[str],
    user_agent: Optional[str],
) -> None:
    """Best-effort insert; logs warning on failure (e.g. missing migration)."""
    settings = get_settings()
    ip_country = await resolve_ip_country_label(ip_address)
    try:
        if settings.database_mode == "local":
            pool = await get_pg_pool()
            async with pool.acquire() as conn:
                await conn.execute(
                    """
                    INSERT INTO user_login_events (
                        id, user_id, ip_address, user_agent, ip_country
                    )
                    VALUES ($1, $2, $3, $4, $5)
                    """,
                    str(uuid.uuid4()),
                    user_id,
                    ip_address,
                    user_agent,
                    ip_country,
                )
        elif settings.database_mode == "supabase":

            def _insert() -> None:
                client = get_supabase_client()
                client.table("user_login_events").insert(
                    {
                        "user_id": user_id,
                        "ip_address": ip_address,
                        "user_agent": user_agent,
                        "ip_country": ip_country,
                    }
                ).execute()

            await asyncio.to_thread(_insert)
    except Exception as e:
        logger.warning("login_event_record_failed", user_id=user_id, error=str(e))


async def list_recent_logins_async(user_id: str, limit: int = 10) -> list[dict[str, Any]]:
    settings = get_settings()
    if settings.database_mode == "local":
        pool = await get_pg_pool()
        async with pool.acquire() as conn:
            try:
                rows = await conn.fetch(
                    """
                    SELECT id::text, logged_in_at, ip_address, user_agent, ip_country
                    FROM user_login_events
                    WHERE user_id = $1
                    ORDER BY logged_in_at DESC
                    LIMIT $2
                    """,
                    user_id,
                    limit,
                )
            except Exception:
                return []
            return [
                {
                    "id": str(r["id"]),
                    "logged_in_at": format_api_datetime(r["logged_in_at"])
                    if r["logged_in_at"]
                    else "",
                    "ip_address": r["ip_address"],
                    "user_agent": r["user_agent"],
                    "ip_country": r["ip_country"],
                }
                for r in rows
            ]

    if settings.database_mode == "supabase":

        def _select() -> list[dict[str, Any]]:
            client = get_supabase_client()
            resp = (
                client.table("user_login_events")
                .select("id,logged_in_at,ip_address,user_agent,ip_country")
                .eq("user_id", user_id)
                .order("logged_in_at", desc=True)
                .limit(limit)
                .execute()
            )
            out: list[dict[str, Any]] = []
            for r in resp.data or []:
                ts = r.get("logged_in_at")
                out.append(
                    {
                        "id": str(r.get("id", "")),
                        "logged_in_at": format_api_datetime(ts) if ts is not None else "",
                        "ip_address": r.get("ip_address"),
                        "user_agent": r.get("user_agent"),
                        "ip_country": r.get("ip_country"),
                    }
                )
            return out

        try:
            return await asyncio.to_thread(_select)
        except Exception:
            return []

    return []
