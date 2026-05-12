"""Shared HTTP executor for SOC provider API clients."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import httpx
import structlog


@dataclass(frozen=True)
class HttpExecutionResult:
    """Normalized HTTP execution result for provider clients."""

    ok: bool
    data: Any | None = None
    raw_text: str | None = None
    error: str | None = None
    error_kind: str | None = None
    http_status: int | None = None


logger = structlog.get_logger()


_SENSITIVE_KEYWORDS = (
    "authorization",
    "password",
    "passwd",
    "secret",
    "token",
    "api_key",
    "apikey",
    "credential",
)


def _is_sensitive_key(key: str) -> bool:
    k = key.strip().lower()
    return any(word in k for word in _SENSITIVE_KEYWORDS)


def _sanitize_value(value: Any) -> Any:
    if isinstance(value, dict):
        out: dict[str, Any] = {}
        for k, v in value.items():
            sk = str(k)
            if _is_sensitive_key(sk):
                out[sk] = "***"
            else:
                out[sk] = _sanitize_value(v)
        return out
    if isinstance(value, list):
        return [_sanitize_value(v) for v in value]
    return value


async def execute_http_request(
    *,
    method: str,
    url: str,
    headers: dict[str, str] | None = None,
    params: dict[str, Any] | None = None,
    data: dict[str, Any] | None = None,
    timeout: float = 30.0,
    verify: bool = True,
) -> HttpExecutionResult:
    """Execute one HTTP request and normalize success/error payload."""
    request_payload = {
        "method": method.upper(),
        "url": url,
        "headers": _sanitize_value(headers or {}),
        "params": _sanitize_value(params or {}),
        "data": _sanitize_value(data or {}),
        "timeout": timeout,
        "verify": verify,
    }
    logger.info(
        "soc_http_execute_start",
        method=request_payload["method"],
        url=request_payload["url"],
        has_headers=bool(headers),
        has_params=bool(params),
        has_data=bool(data),
        timeout=timeout,
        verify=verify,
        request=request_payload,
    )
    async with httpx.AsyncClient(timeout=timeout, verify=verify) as client:
        try:
            resp = await client.request(
                method=method.upper(),
                url=url,
                headers=headers,
                params=params,
                data=data,
            )
            resp.raise_for_status()
            try:
                parsed = resp.json()
                logger.info(
                    "soc_http_execute_success",
                    method=request_payload["method"],
                    url=request_payload["url"],
                    http_status=int(resp.status_code),
                    payload_type="json",
                )
                return HttpExecutionResult(
                    ok=True,
                    data=parsed,
                    http_status=int(resp.status_code),
                )
            except Exception:
                logger.info(
                    "soc_http_execute_success",
                    method=request_payload["method"],
                    url=request_payload["url"],
                    http_status=int(resp.status_code),
                    payload_type="text",
                )
                return HttpExecutionResult(
                    ok=True,
                    raw_text=resp.text,
                    http_status=int(resp.status_code),
                )
        except httpx.HTTPStatusError as exc:
            status_code = None
            if exc.response is not None:
                status_code = int(exc.response.status_code)
            logger.warning(
                "soc_http_execute_http_error",
                method=request_payload["method"],
                url=request_payload["url"],
                http_status=status_code,
                error=str(exc),
                request=request_payload,
            )
            return HttpExecutionResult(
                ok=False,
                error=str(exc),
                error_kind="http_status_error",
                http_status=status_code,
            )
        except Exception as exc:
            logger.error(
                "soc_http_execute_request_error",
                method=request_payload["method"],
                url=request_payload["url"],
                error=str(exc),
                request=request_payload,
            )
            return HttpExecutionResult(
                ok=False,
                error=str(exc),
                error_kind="request_error",
            )
