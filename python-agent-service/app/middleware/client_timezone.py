"""Resolve per-request IANA timezone from X-Client-Timezone header."""

from __future__ import annotations

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response

from app.datetime_support import clear_request_timezone, set_request_timezone


class ClientTimezoneMiddleware(BaseHTTPMiddleware):
    """Bind client IANA timezone for the request scope (ContextVar).

    Frontend should send: X-Client-Timezone: e.g. America/New_York
    Invalid or missing values fall back to APP_TIMEZONE in settings.
    """

    async def dispatch(self, request: Request, call_next) -> Response:
        raw = request.headers.get("x-client-timezone")
        token = set_request_timezone(raw)
        try:
            return await call_next(request)
        finally:
            clear_request_timezone(token)
