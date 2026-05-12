"""Billing summary, usage APIs, Stripe checkout/portal/webhook."""

from __future__ import annotations

import asyncio
from datetime import datetime, timezone
from decimal import Decimal
from typing import Any, Literal
from uuid import UUID

import structlog
from app.api.auth import get_current_user
from app.billing.credits_display import credits_per_usd_int, usd_to_display_credits_str
from app.billing.gate import (
    ACTIVE_SUB_STATUSES,
    _parse_timestamptz,
    _utc_calendar_month_bounds,
)
from app.config import get_settings
from app.datetime_support import format_api_datetime, now_app
from app.billing.usage_record import (
    enrich_llm_usage_api_item_local,
    enrich_llm_usage_api_item_supabase,
)
from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field

logger = structlog.get_logger()

router = APIRouter(tags=["billing"])


def _append_summary_credits_fields(d: dict[str, Any]) -> None:
    """Attach display Credits (100 Credits == USD 1); pricing/gate unchanged in USD."""
    spent = Decimal(str(d.get("spent_usd_period") or "0"))
    cap = Decimal(str(d.get("monthly_spend_cap_usd") or "0"))
    inc = Decimal(str(d.get("included_credits_usd") or "0"))
    d["credits_per_usd"] = credits_per_usd_int()
    d["spent_credits_period"] = usd_to_display_credits_str(spent)
    d["monthly_spend_cap_credits"] = usd_to_display_credits_str(cap)
    d["included_plan_credits"] = usd_to_display_credits_str(inc)


def _attach_usage_row_credits(it: dict[str, Any]) -> None:
    """Set ``cost_credits`` from normalized ``cost_usd`` string."""
    try:
        cu = Decimal(str(it.get("cost_usd") or "0"))
    except Exception:
        cu = Decimal("0")
    it["cost_credits"] = usd_to_display_credits_str(cu)


def _http_billing_error(status: int, code: str, message: str) -> HTTPException:
    return HTTPException(
        status_code=status,
        detail={
            "detail": message,
            "error_code": code,
            "timestamp": format_api_datetime(now_app()),
        },
    )


def _resolve_period_bounds_supabase_sync(user_id: str) -> tuple[datetime, datetime]:
    """Billing period for summary (Supabase thread only)."""
    period_start, period_end = _utc_calendar_month_bounds()
    from app.db import get_supabase_client

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
    if active:
        sub = active[0]
        ps = _parse_timestamptz(sub.get("current_period_start"))
        pe = _parse_timestamptz(sub.get("current_period_end"))
        if ps is not None and pe is not None and pe > ps:
            period_start, period_end = ps, pe
    return period_start, period_end


async def _resolve_period_bounds(user_id: str) -> tuple[datetime, datetime]:
    settings = get_settings()
    period_start, period_end = _utc_calendar_month_bounds()
    if settings.database_mode == "supabase":
        return await asyncio.to_thread(_resolve_period_bounds_supabase_sync, user_id)
    if settings.database_mode == "local":
        from app.db import get_pg_pool

        pool = await get_pg_pool()
        async with pool.acquire() as conn:
            rows = await conn.fetch(
                """
                SELECT status, current_period_start, current_period_end
                FROM user_subscriptions
                WHERE user_id = $1::uuid
                ORDER BY updated_at DESC
                """,
                user_id,
            )
        active = [
            r
            for r in rows
            if str(r["status"] or "").lower() in ACTIVE_SUB_STATUSES
        ]
        if active:
            sub = active[0]
            ps, pe = sub["current_period_start"], sub["current_period_end"]
            if ps is not None and pe is not None and pe > ps:
                period_start = (
                    ps if ps.tzinfo else ps.replace(tzinfo=timezone.utc)
                ).astimezone(timezone.utc)
                period_end = (
                    pe if pe.tzinfo else pe.replace(tzinfo=timezone.utc)
                ).astimezone(timezone.utc)
    return period_start, period_end


def _summary_supabase_sync(user_id: str) -> dict[str, Any]:
    UUID(user_id)
    period_start, period_end = _resolve_period_bounds_supabase_sync(user_id)
    from app.db import get_supabase_client

    client = get_supabase_client()

    sub = (
        client.table("user_subscriptions")
        .select("plan_slug,status,current_period_start,current_period_end")
        .eq("user_id", user_id)
        .in_("status", list(ACTIVE_SUB_STATUSES))
        .order("updated_at", desc=True)
        .limit(1)
        .execute()
    )
    plan_slug = "free"
    sub_status = "inactive"
    if sub.data:
        plan_slug = str(sub.data[0].get("plan_slug") or "free")
        sub_status = str(sub.data[0].get("status") or "inactive")

    plan_row = (
        client.table("billing_plans")
        .select("display_name,included_credits_usd,credits_label")
        .eq("slug", plan_slug)
        .limit(1)
        .execute()
    )
    included_credits_usd = 0.0
    credits_label = "credits"
    if plan_row.data:
        row = plan_row.data[0]
        included_credits_usd = float(row.get("included_credits_usd") or 0)
        credits_label = str(row.get("credits_label") or "credits")

    settings_row = (
        client.table("user_billing_settings")
        .select("monthly_spend_cap_usd,arrears_allowance_usd")
        .eq("user_id", user_id)
        .limit(1)
        .execute()
    )
    cap = float(get_settings().billing_default_monthly_spend_cap_usd)
    arr = float(get_settings().billing_default_arrears_usd)
    if settings_row.data:
        cap = float(settings_row.data[0].get("monthly_spend_cap_usd", cap))
        arr = float(settings_row.data[0].get("arrears_allowance_usd", arr))

    usage = (
        client.table("llm_usage_events")
        .select("prompt_tokens,completion_tokens,cost_usd")
        .eq("user_id", user_id)
        .gte("created_at", period_start.isoformat())
        .lt("created_at", period_end.isoformat())
        .execute()
    )
    tokens_used_estimate = 0
    billable = Decimal("0")
    for row in usage.data or []:
        tokens_used_estimate += int(row.get("prompt_tokens") or 0) + int(
            row.get("completion_tokens") or 0
        )
        billable += Decimal(str(row.get("cost_usd") or 0))

    prof = (
        client.table("user_billing_profile")
        .select("stripe_customer_id")
        .eq("user_id", user_id)
        .limit(1)
        .execute()
    )
    has_stripe_customer = bool(
        prof.data and prof.data[0].get("stripe_customer_id")
    )

    out: dict[str, Any] = {
        "plan_slug": plan_slug,
        "subscription_status": sub_status,
        "period_start": format_api_datetime(period_start),
        "period_end": format_api_datetime(period_end),
        "spent_usd_period": str(billable.quantize(Decimal("0.000001"))),
        "monthly_spend_cap_usd": cap,
        "arrears_allowance_usd": arr,
        "included_credits_usd": included_credits_usd,
        "credits_label": credits_label,
        "tokens_used_period_estimate": tokens_used_estimate,
        "has_stripe_customer": has_stripe_customer,
    }
    _append_summary_credits_fields(out)
    return out


async def _summary_local_async(user_id: str) -> dict[str, Any]:
    from app.db import get_pg_pool

    period_start, period_end = await _resolve_period_bounds(user_id)
    pool = await get_pg_pool()
    async with pool.acquire() as conn:
        sub = await conn.fetchrow(
            """
            SELECT plan_slug, status FROM user_subscriptions
            WHERE user_id = $1::uuid AND status = ANY($2::text[])
            ORDER BY updated_at DESC LIMIT 1
            """,
            user_id,
            list(ACTIVE_SUB_STATUSES),
        )
    plan_slug = "free"
    sub_status = "inactive"
    if sub:
        plan_slug = str(sub["plan_slug"])
        sub_status = str(sub["status"])

    async with pool.acquire() as conn:
        prow = await conn.fetchrow(
            "SELECT included_credits_usd, credits_label FROM billing_plans WHERE slug = $1",
            plan_slug,
        )
        included_credits_usd = float(prow["included_credits_usd"]) if prow else 0.0
        credits_label = str(prow["credits_label"]) if prow else "credits"
        srow = await conn.fetchrow(
            """
            SELECT monthly_spend_cap_usd, arrears_allowance_usd
            FROM user_billing_settings WHERE user_id = $1::uuid
            """,
            user_id,
        )
    s = get_settings()
    cap = float(s.billing_default_monthly_spend_cap_usd)
    arr = float(s.billing_default_arrears_usd)
    if srow:
        cap = float(srow["monthly_spend_cap_usd"])
        arr = float(srow["arrears_allowance_usd"])

    async with pool.acquire() as conn:
        rows = await conn.fetch(
            """
            SELECT prompt_tokens, completion_tokens, cost_usd
            FROM llm_usage_events
            WHERE user_id = $1::uuid
              AND created_at >= $2 AND created_at < $3
            """,
            user_id,
            period_start,
            period_end,
        )
        stripe_cust = await conn.fetchval(
            """
            SELECT stripe_customer_id FROM user_billing_profile
            WHERE user_id = $1::uuid
            """,
            user_id,
        )
    tokens_used_estimate = 0
    billable = Decimal("0")
    for r in rows:
        tokens_used_estimate += int(r["prompt_tokens"]) + int(r["completion_tokens"])
        billable += Decimal(str(r["cost_usd"]))

    out: dict[str, Any] = {
        "plan_slug": plan_slug,
        "subscription_status": sub_status,
        "period_start": format_api_datetime(period_start),
        "period_end": format_api_datetime(period_end),
        "spent_usd_period": str(billable.quantize(Decimal("0.000001"))),
        "monthly_spend_cap_usd": cap,
        "arrears_allowance_usd": arr,
        "included_credits_usd": included_credits_usd,
        "credits_label": credits_label,
        "tokens_used_period_estimate": tokens_used_estimate,
        "has_stripe_customer": bool(stripe_cust),
    }
    _append_summary_credits_fields(out)
    return out


def _coerce_jsonb(raw: Any, default: Any) -> Any:
    """Tolerate JSONB returned as str / dict / list across drivers."""
    if raw is None or raw == "":
        return default
    if isinstance(raw, (dict, list)):
        return raw
    if isinstance(raw, (bytes, bytearray)):
        try:
            raw = raw.decode("utf-8")
        except Exception:
            return default
    if isinstance(raw, str):
        import json

        try:
            return json.loads(raw)
        except Exception:
            return default
    return default


def _list_plans_supabase_sync() -> list[dict[str, Any]]:
    from app.db import get_supabase_client

    r = (
        get_supabase_client()
        .table("billing_plans")
        .select(
            "slug,display_name,monthly_price_usd,sort_order,"
            "included_credits_usd,credits_label,tagline_json,features_json,quota_hints"
        )
        .order("sort_order")
        .execute()
    )
    out: list[dict[str, Any]] = []
    for row in r.data or []:
        out.append(
            {
                "slug": str(row.get("slug") or ""),
                "display_name": str(row.get("display_name") or ""),
                "monthly_price_usd": float(row.get("monthly_price_usd") or 0),
                "sort_order": int(row.get("sort_order") or 0),
                "included_credits_usd": float(row.get("included_credits_usd") or 0),
                "credits_label": str(row.get("credits_label") or "credits"),
                "tagline_json": _coerce_jsonb(row.get("tagline_json"), {}),
                "features_json": _coerce_jsonb(row.get("features_json"), []),
                "quota_hints": _coerce_jsonb(row.get("quota_hints"), []),
            }
        )
    return out


async def _list_plans_local_async() -> list[dict[str, Any]]:
    from app.db import get_pg_pool

    pool = await get_pg_pool()
    async with pool.acquire() as conn:
        rows = await conn.fetch(
            """
            SELECT slug, display_name, monthly_price_usd, sort_order,
                   included_credits_usd, credits_label,
                   tagline_json, features_json, quota_hints
            FROM billing_plans
            ORDER BY sort_order ASC
            """
        )
    return [
        {
            "slug": str(r["slug"]),
            "display_name": str(r["display_name"]),
            "monthly_price_usd": float(r["monthly_price_usd"]),
            "sort_order": int(r["sort_order"]),
            "included_credits_usd": float(r["included_credits_usd"]),
            "credits_label": str(r["credits_label"] or "credits"),
            "tagline_json": _coerce_jsonb(r["tagline_json"], {}),
            "features_json": _coerce_jsonb(r["features_json"], []),
            "quota_hints": _coerce_jsonb(r["quota_hints"], []),
        }
        for r in rows
    ]


@router.get("/billing/plans")
async def list_billing_plans():
    """Public plan catalog for marketing pricing + authenticated billing UI (no Stripe price ids)."""
    s = get_settings()
    try:
        if s.database_mode == "supabase":
            plans = await asyncio.to_thread(_list_plans_supabase_sync)
        elif s.database_mode == "local":
            plans = await _list_plans_local_async()
        else:
            plans = []
        return {"plans": plans, "credits_per_usd": credits_per_usd_int()}
    except Exception as e:
        logger.error("billing_plans_list_failed", error=str(e))
        raise _http_billing_error(
            503, "BILLING_PLANS_UNAVAILABLE", "Could not load billing plans."
        ) from e


@router.get("/billing/summary")
async def billing_summary(current_user: dict = Depends(get_current_user)):
    """Current plan, period, token usage, USD spend, caps."""
    uid = str(current_user["id"])
    settings = get_settings()
    try:
        if settings.database_mode == "supabase":
            return await asyncio.to_thread(_summary_supabase_sync, uid)
        if settings.database_mode == "local":
            return await _summary_local_async(uid)
    except Exception as e:
        logger.error("billing_summary_failed", user_id=uid, error=str(e))
        raise _http_billing_error(
            503, "BILLING_SUMMARY_UNAVAILABLE", "Could not load billing summary."
        ) from e
    raise _http_billing_error(
        503, "BILLING_UNSUPPORTED_MODE", "Billing summary not available in this mode."
    )


class BillingSettingsPatch(BaseModel):
    monthly_spend_cap_usd: float | None = Field(default=None, gt=0)


@router.patch("/billing/settings")
async def patch_billing_settings(
    body: BillingSettingsPatch,
    current_user: dict = Depends(get_current_user),
):
    s = get_settings()
    if body.monthly_spend_cap_usd is None:
        raise HTTPException(status_code=400, detail="No fields to update")
    mx = float(s.billing_max_monthly_spend_cap_usd)
    if body.monthly_spend_cap_usd > mx:
        raise HTTPException(
            status_code=400,
            detail=f"monthly_spend_cap_usd must be <= {mx}",
        )
    uid = str(current_user["id"])
    if s.database_mode == "supabase":

        def _patch():
            from app.db import get_supabase_client

            get_supabase_client().table("user_billing_settings").upsert(
                {
                    "user_id": uid,
                    "monthly_spend_cap_usd": body.monthly_spend_cap_usd,
                },
                on_conflict="user_id",
            ).execute()

        await asyncio.to_thread(_patch)
        return {"ok": True, "monthly_spend_cap_usd": body.monthly_spend_cap_usd}
    if s.database_mode == "local":
        from app.db import get_pg_pool

        pool = await get_pg_pool()
        async with pool.acquire() as conn:
            await conn.execute(
                """
                INSERT INTO user_billing_settings (user_id, monthly_spend_cap_usd)
                VALUES ($1::uuid, $2)
                ON CONFLICT (user_id) DO UPDATE
                SET monthly_spend_cap_usd = EXCLUDED.monthly_spend_cap_usd
                """,
                uid,
                Decimal(str(body.monthly_spend_cap_usd)),
            )
        return {"ok": True, "monthly_spend_cap_usd": body.monthly_spend_cap_usd}
    raise HTTPException(status_code=503, detail="Unsupported database mode")


@router.get("/usage/events")
async def usage_events(
    limit: int = 50,
    offset: int = 0,
    current_user: dict = Depends(get_current_user),
):
    uid = str(current_user["id"])
    limit = max(1, min(limit, 200))
    offset = max(0, offset)
    # Fetch one extra row to know if another page exists (avoids a separate COUNT).
    fetch_n = min(limit + 1, 201)
    s = get_settings()
    if s.database_mode == "supabase":

        def _count() -> int:
            from app.db import get_supabase_client

            r = (
                get_supabase_client()
                .table("llm_usage_events")
                .select("id", count="exact", head=True)
                .eq("user_id", uid)
                .execute()
            )
            c = getattr(r, "count", None)
            return int(c) if c is not None else 0

        def _q():
            from app.db import get_supabase_client

            r = (
                get_supabase_client()
                .table("llm_usage_events")
                .select(
                    "id,created_at,model_id,prompt_tokens,completion_tokens,cost_usd,project_id,request_id"
                )
                .eq("user_id", uid)
                .order("created_at", desc=True)
                .range(offset, offset + fetch_n - 1)
                .execute()
            )
            return r.data or []

        total = await asyncio.to_thread(_count)
        rows = await asyncio.to_thread(_q)
        has_more = len(rows) > limit
        page_rows = rows[:limit]
        items: list[dict[str, Any]] = []
        for row in page_rows:
            it = dict(row)
            if it.get("created_at"):
                it["created_at"] = format_api_datetime(it["created_at"])
            enrich_llm_usage_api_item_supabase(it)
            _attach_usage_row_credits(it)
            items.append(it)
        return {
            "items": items,
            "limit": limit,
            "offset": offset,
            "has_more": has_more,
            "total": total,
            "credits_per_usd": credits_per_usd_int(),
        }
    if s.database_mode == "local":
        from app.db import get_pg_pool

        pool = await get_pg_pool()
        async with pool.acquire() as conn:
            total = int(
                await conn.fetchval(
                    """
                    SELECT COUNT(*)::bigint
                    FROM llm_usage_events
                    WHERE user_id = $1::uuid
                    """,
                    uid,
                )
                or 0
            )
            rows = await conn.fetch(
                """
                SELECT id, created_at, model_id, prompt_tokens, completion_tokens,
                       cost_usd, project_id, request_id
                FROM llm_usage_events
                WHERE user_id = $1::uuid
                ORDER BY created_at DESC
                LIMIT $2 OFFSET $3
                """,
                uid,
                fetch_n,
                offset,
            )
        has_more = len(rows) > limit
        page_rows = rows[:limit]
        items = [dict(r) for r in page_rows]
        for it in items:
            if it.get("created_at"):
                it["created_at"] = format_api_datetime(it["created_at"])
            await enrich_llm_usage_api_item_local(it)
            _attach_usage_row_credits(it)
        return {
            "items": items,
            "limit": limit,
            "offset": offset,
            "has_more": has_more,
            "total": total,
            "credits_per_usd": credits_per_usd_int(),
        }
    if s.database_mode == "memory":
        return {
            "items": [],
            "limit": limit,
            "offset": offset,
            "has_more": False,
            "total": 0,
            "usage_persistence": "disabled",
            "reason": "DATABASE_MODE=memory does not persist llm_usage_events; use local or supabase.",
            "credits_per_usd": credits_per_usd_int(),
        }
    return {
        "items": [],
        "limit": limit,
        "offset": offset,
        "has_more": False,
        "total": 0,
        "credits_per_usd": credits_per_usd_int(),
    }


@router.get("/usage/summary")
async def usage_summary_month(
    current_user: dict = Depends(get_current_user),
):
    """Daily USD totals per model for the current billing period (lightweight aggregate)."""
    uid = str(current_user["id"])
    period_start, period_end = await _resolve_period_bounds(uid)
    s = get_settings()
    if s.database_mode == "local":
        from app.db import get_pg_pool

        pool = await get_pg_pool()
        async with pool.acquire() as conn:
            rows = await conn.fetch(
                """
                SELECT
                  date_trunc('day', created_at AT TIME ZONE 'UTC')::date AS day,
                  model_id,
                  SUM(cost_usd)::text AS usd
                FROM llm_usage_events
                WHERE user_id = $1::uuid
                  AND created_at >= $2 AND created_at < $3
                GROUP BY 1, model_id
                ORDER BY 1 ASC, model_id
                """,
                uid,
                period_start,
                period_end,
            )
        return {
            "period_start": format_api_datetime(period_start),
            "period_end": format_api_datetime(period_end),
            "rows": [dict(r) for r in rows],
        }

    if s.database_mode == "supabase":

        def _agg():
            from app.db import get_supabase_client

            r = (
                get_supabase_client()
                .table("llm_usage_events")
                .select("created_at,model_id,cost_usd")
                .eq("user_id", uid)
                .gte("created_at", period_start.isoformat())
                .lt("created_at", period_end.isoformat())
                .execute()
            )
            by_day: dict[str, dict[str, Decimal]] = {}
            for row in r.data or []:
                ca = row.get("created_at", "")[:10]
                mid = str(row.get("model_id") or "")
                c = Decimal(str(row.get("cost_usd") or 0))
                by_day.setdefault(ca, {})
                by_day[ca][mid] = by_day[ca].get(mid, Decimal("0")) + c
            out = []
            for day in sorted(by_day.keys()):
                for mid, usd in sorted(by_day[day].items()):
                    out.append({"day": day, "model_id": mid, "usd": str(usd)})
            return out

        rows = await asyncio.to_thread(_agg)
        return {
            "period_start": format_api_datetime(period_start),
            "period_end": format_api_datetime(period_end),
            "rows": rows,
        }
    return {
        "period_start": format_api_datetime(period_start),
        "period_end": format_api_datetime(period_end),
        "rows": [],
    }


class CheckoutBody(BaseModel):
    plan_slug: Literal["pro", "ultra"] = "pro"


@router.post("/billing/checkout")
async def create_checkout_session(
    body: CheckoutBody,
    current_user: dict = Depends(get_current_user),
):
    s = get_settings()
    if not s.stripe_secret_key:
        raise HTTPException(status_code=503, detail="Stripe is not configured")
    price = (
        s.stripe_price_pro_monthly
        if body.plan_slug == "pro"
        else s.stripe_price_ultra_monthly
    )
    if not price:
        raise HTTPException(
            status_code=503,
            detail=f"stripe_price_{body.plan_slug}_monthly not configured",
        )
    if not s.billing_checkout_success_url or not s.billing_checkout_cancel_url:
        raise HTTPException(
            status_code=503,
            detail="billing_checkout_success_url / billing_checkout_cancel_url required",
        )
    import stripe

    stripe.api_key = s.stripe_secret_key
    uid = str(current_user["id"])
    email = str(current_user.get("email") or "")
    try:
        session = stripe.checkout.Session.create(
            mode="subscription",
            line_items=[{"price": price, "quantity": 1}],
            success_url=s.billing_checkout_success_url,
            cancel_url=s.billing_checkout_cancel_url,
            client_reference_id=uid,
            customer_email=email or None,
            metadata={"user_id": uid, "plan_slug": body.plan_slug},
            subscription_data={"metadata": {"user_id": uid, "plan_slug": body.plan_slug}},
        )
        return {"url": session.url, "session_id": session.id}
    except Exception as e:
        logger.error("stripe_checkout_failed", error=str(e))
        raise HTTPException(status_code=502, detail="Stripe checkout failed") from e


@router.post("/billing/portal")
async def create_portal_session(current_user: dict = Depends(get_current_user)):
    s = get_settings()
    if not s.stripe_secret_key:
        raise HTTPException(status_code=503, detail="Stripe is not configured")
    if not s.billing_portal_return_url:
        raise HTTPException(status_code=503, detail="billing_portal_return_url required")
    uid = str(current_user["id"])
    import stripe

    stripe.api_key = s.stripe_secret_key

    cust: str | None = None
    if s.database_mode == "supabase":

        def _cust_sup() -> str | None:
            from app.db import get_supabase_client

            r = (
                get_supabase_client()
                .table("user_billing_profile")
                .select("stripe_customer_id")
                .eq("user_id", uid)
                .limit(1)
                .execute()
            )
            if r.data and r.data[0].get("stripe_customer_id"):
                return str(r.data[0]["stripe_customer_id"])
            return None

        cust = await asyncio.to_thread(_cust_sup)
    elif s.database_mode == "local":
        from app.db import get_pg_pool

        pool = await get_pg_pool()
        async with pool.acquire() as conn:
            cust = await conn.fetchval(
                """
                SELECT stripe_customer_id FROM user_billing_profile
                WHERE user_id = $1::uuid
                """,
                uid,
            )
    if not cust:
        raise HTTPException(
            status_code=400,
            detail="No Stripe customer on file; complete checkout first.",
        )
    try:
        session = stripe.billing_portal.Session.create(
            customer=cust,
            return_url=s.billing_portal_return_url,
        )
        return {"url": session.url}
    except Exception as e:
        logger.error("stripe_portal_failed", error=str(e))
        raise HTTPException(status_code=502, detail="Stripe portal failed") from e


def _stripe_mark_processed_supabase_sync(
    event_id: str, event_type: str, livemode: bool
) -> bool:
    from app.db import get_supabase_client

    try:
        get_supabase_client().table("stripe_webhook_events").insert(
            {"id": event_id, "event_type": event_type, "livemode": livemode}
        ).execute()
        return True
    except Exception:
        return False


async def _stripe_mark_processed(
    event_id: str, event_type: str, livemode: bool
) -> bool:
    s = get_settings()
    if s.database_mode == "supabase":
        return await asyncio.to_thread(
            _stripe_mark_processed_supabase_sync, event_id, event_type, livemode
        )
    if s.database_mode == "local":
        from app.db import get_pg_pool

        try:
            pool = await get_pg_pool()
            async with pool.acquire() as conn:
                await conn.execute(
                    """
                    INSERT INTO stripe_webhook_events (id, event_type, livemode)
                    VALUES ($1, $2, $3)
                    """,
                    event_id,
                    event_type,
                    livemode,
                )
            return True
        except Exception:
            return False
    return True


async def _apply_stripe_event_async(event: Any) -> None:
    et = event.get("type")
    obj = (event.get("data") or {}).get("object") or {}
    s = get_settings()
    if et == "checkout.session.completed":
        uid = (obj.get("metadata") or {}).get("user_id") or obj.get("client_reference_id")
        cust = obj.get("customer")
        if uid and cust:
            if s.database_mode == "supabase":
                from app.db import get_supabase_client

                get_supabase_client().table("user_billing_profile").upsert(
                    {"user_id": str(uid), "stripe_customer_id": str(cust)},
                    on_conflict="user_id",
                ).execute()
            elif s.database_mode == "local":
                from app.db import get_pg_pool

                pool = await get_pg_pool()
                async with pool.acquire() as conn:
                    await conn.execute(
                        """
                        INSERT INTO user_billing_profile (user_id, stripe_customer_id)
                        VALUES ($1::uuid, $2)
                        ON CONFLICT (user_id) DO UPDATE
                        SET stripe_customer_id = EXCLUDED.stripe_customer_id
                        """,
                        str(uid),
                        str(cust),
                    )
        return
    if et and et.startswith("customer.subscription."):
        cust = obj.get("customer")
        if not cust:
            return
        status = str(obj.get("status") or "inactive")
        sub_id = str(obj.get("id") or "")
        meta = obj.get("metadata") or {}
        uid = meta.get("user_id")
        plan_slug = meta.get("plan_slug") or "pro"
        cps = obj.get("current_period_start")
        cpe = obj.get("current_period_end")
        if not uid:
            return
        from datetime import datetime as dt

        def _ts(v: Any):
            if v is None:
                return None
            if isinstance(v, (int, float)):
                return dt.fromtimestamp(int(v), tz=timezone.utc)
            raw = str(v).replace("Z", "+00:00")
            parsed = dt.fromisoformat(raw)
            if parsed.tzinfo is None:
                parsed = parsed.replace(tzinfo=timezone.utc)
            return parsed.astimezone(timezone.utc)

        ps, pe = _ts(cps), _ts(cpe)
        if s.database_mode == "supabase":
            from app.db import get_supabase_client

            client = get_supabase_client()
            client.table("user_subscriptions").upsert(
                {
                    "user_id": str(uid),
                    "plan_slug": str(plan_slug),
                    "stripe_subscription_id": sub_id,
                    "status": status,
                    "current_period_start": format_api_datetime(ps) if ps else None,
                    "current_period_end": format_api_datetime(pe) if pe else None,
                },
                on_conflict="stripe_subscription_id",
            ).execute()
        elif s.database_mode == "local":
            from app.db import get_pg_pool

            pool = await get_pg_pool()
            async with pool.acquire() as conn:
                await conn.execute(
                    """
                    INSERT INTO user_subscriptions
                      (user_id, plan_slug, stripe_subscription_id, status,
                       current_period_start, current_period_end)
                    VALUES ($1::uuid, $2, $3, $4, $5, $6)
                    ON CONFLICT (stripe_subscription_id) DO UPDATE SET
                      status = EXCLUDED.status,
                      plan_slug = EXCLUDED.plan_slug,
                      current_period_start = EXCLUDED.current_period_start,
                      current_period_end = EXCLUDED.current_period_end
                    """,
                    str(uid),
                    str(plan_slug),
                    sub_id,
                    status,
                    ps,
                    pe,
                )


@router.post("/webhooks/stripe")
async def stripe_webhook(request: Request):
    s = get_settings()
    if not s.stripe_webhook_secret:
        raise HTTPException(status_code=503, detail="Stripe webhook not configured")
    payload = await request.body()
    sig = request.headers.get("stripe-signature") or ""
    import stripe

    stripe.api_key = s.stripe_secret_key or ""
    try:
        event = stripe.Webhook.construct_event(
            payload, sig, s.stripe_webhook_secret
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail="Invalid payload") from e
    except Exception as e:
        err_name = type(e).__name__
        if "SignatureVerification" in err_name or "signature" in str(e).lower():
            raise HTTPException(status_code=400, detail="Invalid signature") from e
        raise

    eid = str(event.get("id") or "")
    etype = str(event.get("type") or "")
    live = bool(event.get("livemode"))
    if not eid:
        raise HTTPException(status_code=400, detail="Missing event id")

    is_new = await _stripe_mark_processed(eid, etype, live)
    if not is_new:
        return {"received": True, "duplicate": True}

    try:
        await _apply_stripe_event_async(event)
    except Exception as e:
        logger.error("stripe_webhook_apply_failed", error=str(e), event_type=etype)
    return {"received": True}

