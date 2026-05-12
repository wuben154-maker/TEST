"""Timezone helpers: per-request client zone (header) + fallback from settings."""

from __future__ import annotations

from contextvars import ContextVar, Token
from datetime import datetime, timezone
from functools import lru_cache
from typing import Union
from zoneinfo import ZoneInfo

from app.config import get_settings

DatetimeLike = Union[datetime, str, None]

# Set by ClientTimezoneMiddleware from X-Client-Timezone (IANA). None = use fallback.
_request_client_zone: ContextVar[ZoneInfo | None] = ContextVar(
    "request_client_zone", default=None
)


def _parse_iana_zone(raw: str | None) -> ZoneInfo | None:
    if raw is None:
        return None
    name = str(raw).strip()
    if not name or name.lower() in ("undefined", "null", "invalid"):
        return None
    try:
        return ZoneInfo(name)
    except Exception:
        return None


def set_request_timezone(header_value: str | None) -> Token:
    """Bind client zone for this request; returns token for reset."""
    z = _parse_iana_zone(header_value)
    return _request_client_zone.set(z)


def clear_request_timezone(token: Token) -> None:
    _request_client_zone.reset(token)


@lru_cache
def get_fallback_tz() -> ZoneInfo:
    """Default zone when no X-Client-Timezone (webhooks, CLI, tests)."""
    name = (get_settings().app_timezone or "UTC").strip()
    try:
        return ZoneInfo(name)
    except Exception:
        return ZoneInfo("UTC")


def get_effective_tz() -> ZoneInfo:
    """Client zone from request header if valid; else APP_TIMEZONE."""
    z = _request_client_zone.get()
    if z is not None:
        return z
    return get_fallback_tz()


# Backwards compatibility: "app" tz now means effective (client or fallback).
def get_app_tz() -> ZoneInfo:
    return get_effective_tz()


def now_app() -> datetime:
    """Current time in the effective timezone for this request."""
    return datetime.now(get_effective_tz())


def to_app_local(dt: datetime) -> datetime:
    """Convert an instant to the effective timezone (naive treated as UTC)."""
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(get_effective_tz())


def parse_timestamp_flexible(raw: str) -> datetime:
    """Parse API or ISO timestamps, including legacy ``±HH:MM`` and offset-free wall times."""
    s = raw.strip().replace("Z", "+00:00")
    if len(s) >= 11 and s[10] == " ":
        s = s[:10] + "T" + s[11:]
    dt = datetime.fromisoformat(s)
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=get_effective_tz())
    return dt


def format_api_datetime(value: DatetimeLike) -> str | None:
    """Serialize instants for JSON APIs: local wall time in the effective zone, seconds only.

    Example: ``2026-04-10 14:43:05`` — no ``T``, no fractional seconds, no ``±HH:MM`` suffix
    (offset is implied by ``X-Client-Timezone`` / ``APP_TIMEZONE`` for the request).
    """
    if value is None:
        return None
    if isinstance(value, str):
        raw = value.strip().replace("Z", "+00:00")
        if not raw:
            return None
        dt = datetime.fromisoformat(raw)
    else:
        dt = value
    loc = to_app_local(dt)
    loc = loc.replace(microsecond=0)
    return loc.strftime("%Y-%m-%d %H:%M:%S")


def app_calendar_month_bounds_utc(
    now: datetime | None = None,
) -> tuple[datetime, datetime]:
    """Calendar month [start, end) in effective TZ, returned as UTC for DB/queries."""
    tz = get_effective_tz()
    n = now or datetime.now(tz)
    if n.tzinfo is None:
        n = n.replace(tzinfo=tz)
    else:
        n = n.astimezone(tz)
    start = n.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    if start.month == 12:
        end = start.replace(year=start.year + 1, month=1)
    else:
        end = start.replace(month=start.month + 1)
    return start.astimezone(timezone.utc), end.astimezone(timezone.utc)


def clear_app_tz_cache() -> None:
    """Invalidate fallback zone cache when settings/env change (e.g. tests)."""
    get_fallback_tz.cache_clear()
