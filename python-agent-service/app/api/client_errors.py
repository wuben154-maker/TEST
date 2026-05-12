"""Receive frontend error reports and pipe them into the backend log pipeline."""

from __future__ import annotations

import time
from collections import defaultdict
from typing import Any

import structlog
from fastapi import APIRouter, HTTPException, Request, Response
from pydantic import BaseModel, Field, field_validator

router = APIRouter(tags=["client-errors"])
logger = structlog.get_logger()

# ---------------------------------------------------------------------------
# Simple in-memory rate limiter: max RATE_LIMIT_MAX requests per
# RATE_LIMIT_WINDOW_SECONDS per client IP.
# ---------------------------------------------------------------------------
RATE_LIMIT_MAX = 10
RATE_LIMIT_WINDOW_SECONDS = 60
_rate_buckets: dict[str, list[float]] = defaultdict(list)

MAX_ENTRIES_PER_REQUEST = 50
MAX_STRING_FIELD_LENGTH = 2000


class ClientErrorEntry(BaseModel):
    timestamp: str
    level: str
    event: str = Field(max_length=200)
    extra: dict[str, Any] = Field(default_factory=dict)

    @field_validator("extra", mode="before")
    @classmethod
    def _cap_extra_values(cls, v: Any) -> dict[str, Any]:
        if not isinstance(v, dict):
            return {}
        capped: dict[str, Any] = {}
        for key, val in list(v.items())[:30]:
            if isinstance(val, str) and len(val) > MAX_STRING_FIELD_LENGTH:
                val = val[:MAX_STRING_FIELD_LENGTH] + "…[truncated]"
            capped[str(key)[:100]] = val
        return capped


class ClientErrorsPayload(BaseModel):
    errors: list[ClientErrorEntry] = Field(max_length=MAX_ENTRIES_PER_REQUEST)


def _check_rate_limit(client_ip: str) -> None:
    now = time.monotonic()
    bucket = _rate_buckets[client_ip]
    # Evict expired entries
    cutoff = now - RATE_LIMIT_WINDOW_SECONDS
    _rate_buckets[client_ip] = bucket = [t for t in bucket if t > cutoff]
    if len(bucket) >= RATE_LIMIT_MAX:
        raise HTTPException(status_code=429, detail="rate_limit_exceeded")
    bucket.append(now)


@router.post("/api/client-errors", status_code=204)
async def receive_client_errors(
    payload: ClientErrorsPayload,
    request: Request,
) -> Response:
    client_ip = request.client.host if request.client else "unknown"
    _check_rate_limit(client_ip)

    for entry in payload.errors:
        log_fn = logger.warning if entry.level == "warn" else logger.error
        log_fn(
            "client_error",
            client_event=entry.event,
            client_level=entry.level,
            client_timestamp=entry.timestamp,
            client_ip=client_ip,
            **entry.extra,
        )

    return Response(status_code=204)
