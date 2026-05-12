"""Start-of-request billing gate for POST /analyze (no mid-stream enforcement)."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from datetime import datetime, timezone
from decimal import Decimal
from typing import Any
from uuid import UUID

import structlog
from fastapi import HTTPException

from app.config import get_settings
from app.datetime_support import app_calendar_month_bounds_utc, format_api_datetime, now_app

logger = structlog.get_logger()

# Match migration defaults on public.user_billing_settings
DEFAULT_MONTHLY_SPEND_CAP_USD = Decimal("100.00")
DEFAULT_ARREARS_ALLOWANCE_USD = Decimal("5.00")

ACTIVE_SUB_STATUSES = frozenset({"active", "trialing"})


@dataclass(frozen=True)
class BillingGateInputs:
    """Values needed for policy checks (already scoped to one billing period)."""

    billable_usd: Decimal
    monthly_spend_cap_usd: Decimal
    arrears_allowance_usd: Decimal
    only_inactive_subscriptions: bool


def _utc_calendar_month_bounds(now: datetime | None = None) -> tuple[datetime, datetime]:
    """Return [start, end) for the current calendar month in app timezone (bounds as UTC instants)."""
    return app_calendar_month_bounds_utc(now)


def _parse_timestamptz(value: Any) -> datetime | None:
    if value is None:
        return None
    if isinstance(value, datetime):
        dt = value
    else:
        text = str(value).strip()
        if not text:
            return None
        raw = text.replace("Z", "+00:00")
        dt = datetime.fromisoformat(raw)
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def apply_billing_gate_policy(inputs: BillingGateInputs) -> None:
    """Raise HTTPException when this user must not start a new analysis."""
    if inputs.only_inactive_subscriptions:
        raise _billing_http_exception(
            403,
            "BILLING_PLAN_INACTIVE",
            "No active subscription; start of analysis is blocked.",
        )

    ceiling = inputs.monthly_spend_cap_usd + inputs.arrears_allowance_usd
    # Deny when spend has reached the cap plus arrears headroom (see design.md).
    if inputs.billable_usd >= ceiling:
        raise _billing_http_exception(
            402,
            "BILLING_CAP_EXCEEDED",
            "Billing spend limit reached for the current period.",
        )


def _billing_http_exception(status: int, code: str, message: str) -> HTTPException:
    return HTTPException(
        status_code=status,
        detail={
            "detail": message,
            "error_code": code,
            "timestamp": format_api_datetime(now_app()),
        },
    )


def _sync_load_inputs_supabase(user_id: str) -> BillingGateInputs:
    from app.db import get_supabase_client

    UUID(user_id)
    client = get_supabase_client()

    sub_resp = (
        client.table("user_subscriptions")
        .select("status,current_period_start,current_period_end,updated_at")
        .eq("user_id", user_id)
        .order("updated_at", desc=True)
        .execute()
    )
    rows = sub_resp.data or []
    active = [
        r
        for r in rows
        if str(r.get("status") or "").lower() in ACTIVE_SUB_STATUSES
    ]
    only_inactive = bool(rows) and not active

    period_start, period_end = _utc_calendar_month_bounds()
    if active:
        sub = active[0]
        ps = _parse_timestamptz(sub.get("current_period_start"))
        pe = _parse_timestamptz(sub.get("current_period_end"))
        if ps is not None and pe is not None and pe > ps:
            period_start, period_end = ps, pe

    settings_resp = (
        client.table("user_billing_settings")
        .select("monthly_spend_cap_usd,arrears_allowance_usd")
        .eq("user_id", user_id)
        .limit(1)
        .execute()
    )
    cap = DEFAULT_MONTHLY_SPEND_CAP_USD
    arrears = DEFAULT_ARREARS_ALLOWANCE_USD
    if settings_resp.data:
        row = settings_resp.data[0]
        cap = Decimal(str(row.get("monthly_spend_cap_usd", cap)))
        arrears = Decimal(str(row.get("arrears_allowance_usd", arrears)))

    usage_resp = (
        client.table("llm_usage_events")
        .select("cost_usd")
        .eq("user_id", user_id)
        .gte("created_at", period_start.isoformat())
        .lt("created_at", period_end.isoformat())
        .execute()
    )
    billable = Decimal("0")
    for row in usage_resp.data or []:
        billable += Decimal(str(row.get("cost_usd") or 0))

    return BillingGateInputs(
        billable_usd=billable,
        monthly_spend_cap_usd=cap,
        arrears_allowance_usd=arrears,
        only_inactive_subscriptions=only_inactive,
    )


async def _async_load_inputs_local(user_id: str) -> BillingGateInputs:
    import asyncpg

    from app.db import get_pg_pool

    UUID(user_id)
    pool = await get_pg_pool()
    try:
        async with pool.acquire() as conn:
            rows = await conn.fetch(
                """
                SELECT status, current_period_start, current_period_end, updated_at
                FROM user_subscriptions
                WHERE user_id = $1::uuid
                ORDER BY updated_at DESC
                """,
                user_id,
            )
    except asyncpg.exceptions.UndefinedTableError:
        logger.error(
            "billing_gate_missing_tables",
            user_id=user_id,
            hint="Apply billing migration or set BILLING_ENFORCE=false",
        )
        raise _billing_http_exception(
            503,
            "BILLING_SCHEMA_MISSING",
            "Billing tables are not available on this database.",
        ) from None

    active = [
        r
        for r in rows
        if str(r["status"] or "").lower() in ACTIVE_SUB_STATUSES
    ]
    only_inactive = bool(rows) and not active

    period_start, period_end = _utc_calendar_month_bounds()
    if active:
        sub = active[0]
        ps = sub["current_period_start"]
        pe = sub["current_period_end"]
        if ps is not None and pe is not None and pe > ps:
            period_start = (
                ps if ps.tzinfo else ps.replace(tzinfo=timezone.utc)
            ).astimezone(timezone.utc)
            period_end = (
                pe if pe.tzinfo else pe.replace(tzinfo=timezone.utc)
            ).astimezone(timezone.utc)

    async with pool.acquire() as conn:
        srow = await conn.fetchrow(
            """
            SELECT monthly_spend_cap_usd, arrears_allowance_usd
            FROM user_billing_settings
            WHERE user_id = $1::uuid
            LIMIT 1
            """,
            user_id,
        )
    cap = DEFAULT_MONTHLY_SPEND_CAP_USD
    arrears = DEFAULT_ARREARS_ALLOWANCE_USD
    if srow:
        cap = Decimal(str(srow["monthly_spend_cap_usd"]))
        arrears = Decimal(str(srow["arrears_allowance_usd"]))

    async with pool.acquire() as conn:
        usage_rows = await conn.fetch(
            """
            SELECT cost_usd
            FROM llm_usage_events
            WHERE user_id = $1::uuid
              AND created_at >= $2
              AND created_at < $3
            """,
            user_id,
            period_start,
            period_end,
        )
    billable = sum(
        (Decimal(str(r["cost_usd"])) for r in usage_rows),
        Decimal("0"),
    )

    return BillingGateInputs(
        billable_usd=billable,
        monthly_spend_cap_usd=cap,
        arrears_allowance_usd=arrears,
        only_inactive_subscriptions=only_inactive,
    )


async def assert_analyze_billing_allowed(user_id: str) -> None:
    """Raise HTTPException if this user may not start a new analysis."""
    settings = get_settings()
    if not settings.billing_enforce:
        return

    try:
        UUID(user_id)
    except ValueError:
        raise _billing_http_exception(
            400,
            "BILLING_INVALID_USER",
            "Invalid user id in token.",
        ) from None

    try:
        if settings.database_mode == "supabase":
            inputs = await asyncio.to_thread(_sync_load_inputs_supabase, user_id)
        elif settings.database_mode == "local":
            inputs = await _async_load_inputs_local(user_id)
        else:
            logger.warning(
                "billing_enforce_unsupported_database_mode",
                mode=settings.database_mode,
            )
            return
    except HTTPException:
        raise
    except Exception as e:
        logger.error("billing_gate_load_failed", user_id=user_id, error=str(e))
        raise _billing_http_exception(
            503,
            "BILLING_GATE_UNAVAILABLE",
            "Could not evaluate billing gate; try again later.",
        ) from e

    apply_billing_gate_policy(inputs)
