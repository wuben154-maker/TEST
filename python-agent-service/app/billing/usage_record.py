"""Persist rows to ``llm_usage_events`` (service / backend paths)."""

from __future__ import annotations

import asyncio
import structlog
from decimal import Decimal
from typing import Any
from uuid import UUID

from app.billing.pricing import compute_cost_usd
from app.config import get_settings

logger = structlog.get_logger()

_LLM_USAGE_MEMORY_MODE_WARNED = False


def _optional_project_uuid(project_id: str | None) -> str | None:
    if not project_id:
        return None
    try:
        UUID(project_id)
        return project_id
    except ValueError:
        return None


def _load_pricing_sync(model_id: str) -> tuple[Decimal, Decimal]:
    """Latest effective row per model; zeros if table missing or no row."""
    from app.config import get_settings

    settings = get_settings()
    default = (Decimal("0"), Decimal("0"))
    if settings.database_mode == "supabase":
        return _load_pricing_supabase_sync(model_id)
    if settings.database_mode == "local":
        return default  # async path used instead
    return default


def _load_pricing_supabase_sync(model_id: str) -> tuple[Decimal, Decimal]:
    from app.db import get_supabase_client

    try:
        client = get_supabase_client()
        r = (
            client.table("model_pricing")
            .select("usd_per_million_input,usd_per_million_output,effective_from")
            .eq("model_id", model_id)
            .order("effective_from", desc=True)
            .limit(1)
            .execute()
        )
        if not r.data:
            logger.warning("model_pricing_missing", model_id=model_id)
            return Decimal("0"), Decimal("0")
        row = r.data[0]
        return Decimal(str(row["usd_per_million_input"])), Decimal(
            str(row["usd_per_million_output"])
        )
    except Exception as e:
        logger.warning("model_pricing_load_failed", model_id=model_id, error=str(e))
        return Decimal("0"), Decimal("0")


async def _load_pricing_local_async(model_id: str) -> tuple[Decimal, Decimal]:
    import asyncpg

    from app.db import get_pg_pool

    try:
        pool = await get_pg_pool()
    except Exception:
        return Decimal("0"), Decimal("0")
    try:
        async with pool.acquire() as conn:
            row = await conn.fetchrow(
                """
                SELECT usd_per_million_input, usd_per_million_output
                FROM model_pricing
                WHERE model_id = $1
                ORDER BY effective_from DESC
                LIMIT 1
                """,
                model_id,
            )
        if not row:
            logger.warning("model_pricing_missing", model_id=model_id)
            return Decimal("0"), Decimal("0")
        return Decimal(str(row["usd_per_million_input"])), Decimal(
            str(row["usd_per_million_output"])
        )
    except asyncpg.exceptions.UndefinedTableError:
        return Decimal("0"), Decimal("0")
    except Exception as e:
        logger.warning("model_pricing_load_failed", model_id=model_id, error=str(e))
        return Decimal("0"), Decimal("0")


def _insert_supabase_sync(
    *,
    user_id: str,
    project_id: str | None,
    request_id: str,
    model_id: str,
    prompt_tokens: int,
    completion_tokens: int,
    cost_usd: Decimal,
) -> None:
    from app.db import get_supabase_client

    client = get_supabase_client()
    payload = {
        "user_id": user_id,
        "project_id": project_id,
        "request_id": request_id or "",
        "model_id": model_id,
        "prompt_tokens": prompt_tokens,
        "completion_tokens": completion_tokens,
        "cost_usd": float(cost_usd),
    }
    client.table("llm_usage_events").insert(payload).execute()


async def _insert_local_async(
    *,
    user_id: str,
    project_id: str | None,
    request_id: str,
    model_id: str,
    prompt_tokens: int,
    completion_tokens: int,
    cost_usd: Decimal,
) -> None:
    import asyncpg

    from app.db import get_pg_pool

    pool = await get_pg_pool()
    async with pool.acquire() as conn:
        await conn.execute(
            """
            INSERT INTO llm_usage_events
              (user_id, project_id, request_id, model_id,
               prompt_tokens, completion_tokens, cost_usd)
            VALUES ($1::uuid, $2::uuid, $3, $4, $5, $6, $7)
            """,
            user_id,
            project_id,
            request_id or "",
            model_id,
            prompt_tokens,
            completion_tokens,
            cost_usd,
        )


async def record_llm_usage_event_async(
    *,
    user_id: str,
    project_id: str | None,
    request_id: str,
    model_id: str,
    prompt_tokens: int,
    completion_tokens: int,
) -> None:
    """Compute cost from ``model_pricing`` and insert one usage row. Swallows errors."""
    settings = get_settings()
    try:
        if settings.database_mode == "supabase":
            pi, po = _load_pricing_sync(model_id)
            cost = compute_cost_usd(prompt_tokens, completion_tokens, pi, po)
            await asyncio.to_thread(
                _insert_supabase_sync,
                user_id=user_id,
                project_id=_optional_project_uuid(project_id),
                request_id=request_id,
                model_id=model_id,
                prompt_tokens=prompt_tokens,
                completion_tokens=completion_tokens,
                cost_usd=cost,
            )
        elif settings.database_mode == "local":
            pi, po = await _load_pricing_local_async(model_id)
            cost = compute_cost_usd(prompt_tokens, completion_tokens, pi, po)
            await _insert_local_async(
                user_id=user_id,
                project_id=_optional_project_uuid(project_id),
                request_id=request_id,
                model_id=model_id,
                prompt_tokens=prompt_tokens,
                completion_tokens=completion_tokens,
                cost_usd=cost,
            )
        elif settings.database_mode == "memory":
            global _LLM_USAGE_MEMORY_MODE_WARNED
            if not _LLM_USAGE_MEMORY_MODE_WARNED:
                _LLM_USAGE_MEMORY_MODE_WARNED = True
                logger.warning(
                    "llm_usage_events_skipped_database_mode_memory",
                    hint="DATABASE_MODE=memory does not persist llm_usage_events; "
                    "set DATABASE_MODE=local or supabase and apply billing migrations.",
                )
    except Exception as e:
        logger.warning(
            "llm_usage_event_insert_failed",
            user_id=user_id,
            model_id=model_id,
            error=str(e),
        )


def enrich_llm_usage_api_item_supabase(row: dict[str, Any]) -> dict[str, Any]:
    """If ``cost_usd`` is missing or zero, recompute from tokens + ``model_pricing`` (best-effort).

    Fixes rows inserted when pricing was unavailable for ``model_id`` (common in local/dev).
    """
    try:
        stored = Decimal(
            str(row.get("cost_usd") if row.get("cost_usd") is not None else "0")
        )
    except Exception:
        stored = Decimal("0")
    if stored > Decimal("0"):
        row["cost_usd"] = str(stored.quantize(Decimal("0.000001")))
        return row

    model_id = str(row.get("model_id") or "")
    try:
        pt = int(row.get("prompt_tokens") or 0)
        ct = int(row.get("completion_tokens") or 0)
    except (TypeError, ValueError):
        pt, ct = 0, 0
    if not model_id:
        row["cost_usd"] = "0"
        return row

    pi, po = _load_pricing_supabase_sync(model_id)
    cost = compute_cost_usd(pt, ct, pi, po)
    row["cost_usd"] = str(cost.quantize(Decimal("0.000001")))
    return row


async def enrich_llm_usage_api_item_local(row: dict[str, Any]) -> dict[str, Any]:
    """Same as ``enrich_llm_usage_api_item_supabase`` for local asyncpg-backed DB."""
    try:
        stored = Decimal(
            str(row.get("cost_usd") if row.get("cost_usd") is not None else "0")
        )
    except Exception:
        stored = Decimal("0")
    if stored > Decimal("0"):
        row["cost_usd"] = str(stored.quantize(Decimal("0.000001")))
        return row

    model_id = str(row.get("model_id") or "")
    try:
        pt = int(row.get("prompt_tokens") or 0)
        ct = int(row.get("completion_tokens") or 0)
    except (TypeError, ValueError):
        pt, ct = 0, 0
    if not model_id:
        row["cost_usd"] = "0"
        return row

    pi, po = await _load_pricing_local_async(model_id)
    cost = compute_cost_usd(pt, ct, pi, po)
    row["cost_usd"] = str(cost.quantize(Decimal("0.000001")))
    return row
