"""HTTP access logging middleware — structured JSON per request."""

from __future__ import annotations

import time
from uuid import uuid4

import structlog
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response

logger = structlog.get_logger()


def _get_client_ip(request: Request) -> str:
    """Extract client IP, respecting X-Forwarded-For behind a trusted proxy."""
    forwarded = request.headers.get("x-forwarded-for")
    if forwarded:
        return forwarded.split(",")[0].strip()
    return request.client.host if request.client else "unknown"


class RequestLoggingMiddleware(BaseHTTPMiddleware):
    """Emit one ``http_request`` log line per HTTP request with timing and status."""

    async def dispatch(self, request: Request, call_next) -> Response:
        request_id = (
            request.headers.get("x-request-id")
            or request.query_params.get("requestId")
            or uuid4().hex[:16]
        )

        structlog.contextvars.bind_contextvars(
            request_id=request_id,
            client_ip=_get_client_ip(request),
            http_method=request.method,
            http_path=request.url.path,
        )

        start = time.perf_counter()
        try:
            response = await call_next(request)
        except Exception:
            logger.error(
                "http_request_unhandled",
                status_code=500,
                latency_ms=int((time.perf_counter() - start) * 1000),
            )
            raise

        latency_ms = int((time.perf_counter() - start) * 1000)

        log_fn = logger.info if response.status_code < 400 else logger.warning
        log_fn(
            "http_request",
            status_code=response.status_code,
            latency_ms=latency_ms,
        )

        structlog.contextvars.unbind_contextvars(
            "request_id", "client_ip", "http_method", "http_path",
        )
        return response
