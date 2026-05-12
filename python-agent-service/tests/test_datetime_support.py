"""Tests for request-scoped client timezone and fallback."""

from datetime import datetime, timezone
from zoneinfo import ZoneInfo

from app.config.settings import clear_settings_cache
from app.datetime_support import (
    app_calendar_month_bounds_utc,
    clear_request_timezone,
    format_api_datetime,
    get_fallback_tz,
    get_effective_tz,
    now_app,
    parse_timestamp_flexible,
    set_request_timezone,
    to_app_local,
)


def test_format_api_datetime_utc_fallback_without_client_header():
    clear_settings_cache()
    dt = datetime(2026, 4, 8, 12, 0, 0, tzinfo=timezone.utc)
    s = format_api_datetime(dt)
    assert "12:00:00" in s
    assert "T" not in s
    assert "+" not in s and "-" not in s[10:]  # no timezone suffix on the string
    assert ".664226" not in s


def test_format_api_datetime_respects_client_zone_header():
    clear_settings_cache()
    dt = datetime(2026, 4, 8, 12, 0, 0, tzinfo=timezone.utc)
    token = set_request_timezone("America/New_York")
    try:
        s = format_api_datetime(dt)
        assert "+" not in s and s.count("-") == 2  # date hyphens only, no offset
        assert "08:00:00" in s or "07:00:00" in s
    finally:
        clear_request_timezone(token)


def test_now_app_matches_effective_zone():
    clear_settings_cache()
    token = set_request_timezone("Europe/Berlin")
    try:
        n = now_app()
        assert n.tzinfo == get_effective_tz()
        assert n.tzinfo == ZoneInfo("Europe/Berlin")
    finally:
        clear_request_timezone(token)


def test_app_calendar_month_bounds_utc_ordering():
    clear_settings_cache()
    start, end = app_calendar_month_bounds_utc()
    assert start.tzinfo == timezone.utc
    assert end.tzinfo == timezone.utc
    assert start < end


def test_parse_timestamp_flexible_accepts_iso_t_and_space_form():
    a = parse_timestamp_flexible("2026-04-10T14:43:05.664226+08:00")
    b = parse_timestamp_flexible("2026-04-10 14:43:05+08:00")
    assert a.replace(microsecond=0) == b
    assert a.microsecond == 664226


def test_parse_timestamp_flexible_naive_wall_time_uses_effective_zone():
    clear_settings_cache()
    token = set_request_timezone("Asia/Shanghai")
    try:
        p = parse_timestamp_flexible("2026-04-10 14:43:05")
        assert p.tzinfo == ZoneInfo("Asia/Shanghai")
        assert format_api_datetime(p) == "2026-04-10 14:43:05"
    finally:
        clear_request_timezone(token)


def test_to_app_local_naive_treated_as_utc():
    clear_settings_cache()
    naive = datetime(2026, 1, 1, 0, 0, 0)
    loc = to_app_local(naive)
    assert loc.tzinfo == get_fallback_tz()
