"""Ensure default billing rows after user registration (Free plan, settings, profile)."""

from __future__ import annotations

import asyncio
import structlog
from decimal import Decimal

from app.config import get_settings

logger = structlog.get_logger()


async def ensure_default_billing_for_user(user_id: str) -> None:
    """Best-effort: create profile row, settings, and active Free subscription if missing."""
    settings = get_settings()
    if settings.database_mode == "supabase":
        await asyncio.to_thread(_bootstrap_supabase_sync, user_id)
    elif settings.database_mode == "local":
        await _bootstrap_local_async(user_id)
    # memory mode: skip


def _bootstrap_supabase_sync(user_id: str) -> None:
    from app.db import get_supabase_client

    try:
        client = get_supabase_client()
    except Exception as e:
        logger.warning("billing_bootstrap_skip_no_supabase", user_id=user_id, error=str(e))
        return

    s = get_settings()
    cap = float(s.billing_default_monthly_spend_cap_usd)
    arr = float(s.billing_default_arrears_usd)

    try:
        client.table("user_billing_profile").upsert(
            {"user_id": user_id}, on_conflict="user_id"
        ).execute()
    except Exception as e:
        logger.warning("billing_bootstrap_profile_failed", user_id=user_id, error=str(e))
        return

    try:
        client.table("user_billing_settings").upsert(
            {
                "user_id": user_id,
                "monthly_spend_cap_usd": cap,
                "arrears_allowance_usd": arr,
            },
            on_conflict="user_id",
        ).execute()
    except Exception as e:
        logger.warning("billing_bootstrap_settings_failed", user_id=user_id, error=str(e))

    try:
        active = (
            client.table("user_subscriptions")
            .select("id")
            .eq("user_id", user_id)
            .in_("status", ["active", "trialing"])
            .limit(1)
            .execute()
        )
        if active.data:
            return
        client.table("user_subscriptions").insert(
            {
                "user_id": user_id,
                "plan_slug": "free",
                "status": "active",
            }
        ).execute()
    except Exception as e:
        logger.warning("billing_bootstrap_subscription_failed", user_id=user_id, error=str(e))


async def _bootstrap_local_async(user_id: str) -> None:
    import asyncpg

    from app.db import get_pg_pool

    s = get_settings()
    cap = Decimal(str(s.billing_default_monthly_spend_cap_usd))
    arr = Decimal(str(s.billing_default_arrears_usd))

    try:
        pool = await get_pg_pool()
    except Exception as e:
        logger.warning("billing_bootstrap_local_no_pool", error=str(e))
        return

    try:
        async with pool.acquire() as conn:
            await conn.execute(
                """
                INSERT INTO user_billing_profile (user_id) VALUES ($1::uuid)
                ON CONFLICT (user_id) DO NOTHING
                """,
                user_id,
            )
            await conn.execute(
                """
                INSERT INTO user_billing_settings
                  (user_id, monthly_spend_cap_usd, arrears_allowance_usd)
                VALUES ($1::uuid, $2, $3)
                ON CONFLICT (user_id) DO NOTHING
                """,
                user_id,
                cap,
                arr,
            )
            row = await conn.fetchrow(
                """
                SELECT 1 FROM user_subscriptions
                WHERE user_id = $1::uuid AND status IN ('active', 'trialing')
                LIMIT 1
                """,
                user_id,
            )
            if row is None:
                await conn.execute(
                    """
                    INSERT INTO user_subscriptions
                      (user_id, plan_slug, status)
                    VALUES ($1::uuid, 'free', 'active')
                    """,
                    user_id,
                )
    except asyncpg.exceptions.UndefinedTableError:
        logger.info(
            "billing_bootstrap_skipped_no_tables",
            user_id=user_id,
            hint="Run scripts/db/init_local_billing.sql",
        )
    except Exception as e:
        logger.warning("billing_bootstrap_local_failed", user_id=user_id, error=str(e))
