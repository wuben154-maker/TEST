"""Splunk Search API read-only tools for SOC adaptor backend mapping."""

from __future__ import annotations

import base64
import re
from contextlib import contextmanager
from contextvars import ContextVar
from dataclasses import dataclass
from typing import Any
from urllib.parse import quote

import structlog
from langchain_core.tools import StructuredTool
from pydantic import BaseModel, Field

from ..api_service_config import load_api_service_config
from ..http_executor import execute_http_request

_SPLUNK_RUNTIME_OVERRIDE: ContextVar[dict[str, Any] | None] = ContextVar(
    "_SPLUNK_RUNTIME_OVERRIDE",
    default=None,
)
logger = structlog.get_logger()
_SPL_SAFE_UNQUOTED_RE = re.compile(r"^[A-Za-z0-9._*:-]+$")


def _simulated_payload(detail: dict[str, Any]) -> dict[str, Any]:
    return {"simulated": True, "provider": "splunk", **detail}


def _request_payload_dict(request: SplunkHttpRequest, timeout: float, verify: bool) -> dict[str, Any]:
    return {
        "method": request.method,
        "url": request.url,
        "path": request.path,
        "headers": dict(request.headers),
        "params": dict(request.params or {}),
        "data": dict(request.data or {}),
        "timeout": timeout,
        "verify": verify,
    }


def _splunk_headers(api_key: str, creds: dict[str, Any] | None = None) -> dict[str, str]:
    headers = {"Accept": "application/json"}
    if isinstance(creds, dict):
        username = str(creds.get("username", "")).strip()
        password = str(creds.get("password", "")).strip()
        if username and password:
            token = base64.b64encode(f"{username}:{password}".encode("utf-8")).decode("ascii")
            headers["Authorization"] = f"Basic {token}"
            return headers
    token = api_key.strip()
    if token:
        headers["Authorization"] = token if " " in token else f"Bearer {token}"
    return headers


def _coerce_bool(value: Any, default: bool) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return bool(value)
    if isinstance(value, str):
        normalized = value.strip().lower()
        if normalized in {"1", "true", "yes", "y", "on"}:
            return True
        if normalized in {"0", "false", "no", "n", "off"}:
            return False
    return default


@dataclass(frozen=True)
class SplunkHttpRequest:
    """Canonical HTTP request payload for Splunk API calls."""

    method: str
    url: str
    headers: dict[str, str]
    params: dict[str, Any] | None
    data: dict[str, Any] | None
    path: str


def _build_splunk_http_request(
    *,
    method: str,
    path: str,
    base_url: str,
    api_key: str,
    creds: dict[str, Any] | None = None,
    params: dict[str, Any] | None = None,
    body: dict[str, Any] | None = None,
) -> SplunkHttpRequest:
    """Build a normalized Splunk HTTP request from runtime/config context."""
    headers = _splunk_headers(api_key, creds)
    data = body if body is not None else None
    if data is not None:
        headers["Content-Type"] = "application/x-www-form-urlencoded"
    normalized_base = base_url.rstrip("/")
    url = f"{normalized_base}{path}"
    return SplunkHttpRequest(
        method=method.upper(),
        url=url,
        headers=headers,
        params=params,
        data=data,
        path=path,
    )


@contextmanager
def splunk_runtime_override(override: dict[str, Any] | None):
    """Set per-call runtime override for credentials/config."""
    token = _SPLUNK_RUNTIME_OVERRIDE.set(override or None)
    try:
        yield
    finally:
        _SPLUNK_RUNTIME_OVERRIDE.reset(token)


async def _splunk_request(
    *,
    method: str,
    path: str,
    params: dict[str, Any] | None = None,
    body: dict[str, Any] | None = None,
) -> dict[str, Any]:
    logger.info(
        "soc_splunk_request_start",
        method=method.upper(),
        path=path,
        has_params=bool(params),
        has_body=bool(body),
    )
    runtime = _SPLUNK_RUNTIME_OVERRIDE.get() or {}
    runtime_creds = runtime.get("credentials") if isinstance(runtime, dict) else {}
    runtime_base_url = str((runtime or {}).get("base_url", "")).strip()
    runtime_timeout = (runtime or {}).get("timeout")
    runtime_verify = (runtime or {}).get("verify")
    svc = load_api_service_config("splunk_api")
    base_url = runtime_base_url or svc.base_url
    timeout = float(runtime_timeout) if runtime_timeout not in (None, "") else float(svc.timeout)
    verify = _coerce_bool(runtime_verify, bool(svc.verify))
    has_runtime_auth = isinstance(runtime_creds, dict) and bool(runtime_creds)
    logger.info(
        "soc_splunk_runtime_resolved",
        method=method.upper(),
        path=path,
        has_runtime_auth=has_runtime_auth,
        has_runtime_base_url=bool(runtime_base_url),
        service_enabled=bool(svc.enabled),
        has_service_base_url=bool(svc.base_url),
    )
    if (not svc.enabled and not has_runtime_auth) or not base_url:
        logger.info(
            "soc_splunk_request_simulated",
            method=method.upper(),
            path=path,
            reason="service_disabled_or_base_url_missing",
        )
        simulated_request = _build_splunk_http_request(
            method=method,
            path=path,
            base_url=base_url or "http://splunk-not-configured.local",
            api_key=svc.api_key,
            creds=runtime_creds,
            params=params,
            body=body,
        )
        return _simulated_payload(
            {
                "method": method,
                "path": path,
                "params": params or {},
                "body": body or {},
                "request": _request_payload_dict(simulated_request, timeout, verify),
                "note": "splunk_api not configured/enabled.",
            }
        )

    request_payload = _build_splunk_http_request(
        method=method,
        path=path,
        base_url=base_url,
        api_key=svc.api_key,
        creds=runtime_creds,
        params=params,
        body=body,
    )
    logger.info(
        "soc_splunk_request_built",
        method=request_payload.method,
        path=request_payload.path,
        url=request_payload.url,
        header_keys=sorted(request_payload.headers.keys()),
        has_basic_auth=request_payload.headers.get("Authorization", "").startswith("Basic "),
    )
    result = await execute_http_request(
        method=request_payload.method,
        url=request_payload.url,
        headers=request_payload.headers,
        params=request_payload.params,
        data=request_payload.data,
        timeout=timeout,
        verify=verify,
    )
    if result.ok:
        logger.info(
            "soc_splunk_request_success",
            method=request_payload.method,
            path=request_payload.path,
            http_status=result.http_status,
            payload_kind="json" if result.data is not None else "text",
        )
        parsed_data = result.data if result.data is not None else {"raw": result.raw_text or ""}
        return {
            "provider": "splunk",
            "method": request_payload.method,
            "path": request_payload.path,
            "request": _request_payload_dict(request_payload, timeout, verify),
            "data": parsed_data,
        }
    payload = {
        "provider": "splunk",
        "method": request_payload.method,
        "path": request_payload.path,
        "request": _request_payload_dict(request_payload, timeout, verify),
        "error": result.error or "unknown error",
        "error_kind": result.error_kind or "request_error",
    }
    if result.http_status is not None:
        payload["http_status"] = result.http_status
    logger.warning(
        "soc_splunk_request_failed",
        method=request_payload.method,
        path=request_payload.path,
        error_kind=payload["error_kind"],
        http_status=payload.get("http_status"),
    )
    return payload


async def soc_splunk_search_export(
    search: str = "search index=*",
    earliest_time: str = "-24h",
    latest_time: str = "now",
    output_mode: str = "json",
) -> dict[str, Any]:
    """Run one-shot export search for alert-style querying."""
    return await _splunk_request(
        method="POST",
        path="/services/search/v2/jobs/export",
        body={
            "search": search,
            "earliest_time": earliest_time,
            "latest_time": latest_time,
            "output_mode": output_mode,
        },
    )


async def soc_splunk_list_jobs(
    count: int = 20,
    offset: int = 0,
    output_mode: str = "json",
) -> dict[str, Any]:
    """List search jobs (used as case list abstraction)."""
    return await _splunk_request(
        method="GET",
        path="/services/search/jobs",
        params={"count": count, "offset": offset, "output_mode": output_mode},
    )


async def soc_splunk_get_job(
    sid: str,
    output_mode: str = "json",
) -> dict[str, Any]:
    """Get one search job detail (used as case detail abstraction)."""
    return await _splunk_request(
        method="GET",
        path=f"/services/search/jobs/{quote(sid, safe='')}",
        params={"output_mode": output_mode},
    )


async def soc_splunk_get_job_events(
    sid: str,
    count: int = 100,
    offset: int = 0,
    output_mode: str = "json",
) -> dict[str, Any]:
    """Get job events as case alerts abstraction."""
    return await _splunk_request(
        method="GET",
        path=f"/services/search/jobs/{quote(sid, safe='')}/events",
        params={
            "count": count,
            "offset": offset,
            "output_mode": output_mode,
        },
    )


async def soc_splunk_get_job_timeline(
    sid: str,
    output_mode: str = "json",
) -> dict[str, Any]:
    """Get job timeline as case activity abstraction."""
    return await _splunk_request(
        method="GET",
        path=f"/services/search/jobs/{quote(sid, safe='')}/timeline",
        params={"output_mode": output_mode},
    )


async def soc_splunk_get_job_search_log(
    sid: str,
    output_mode: str = "json",
) -> dict[str, Any]:
    """Get job search log as case comments abstraction."""
    return await _splunk_request(
        method="GET",
        path=f"/services/search/jobs/{quote(sid, safe='')}/search.log",
        params={"output_mode": output_mode},
    )


async def soc_splunk_list_saved_searches(
    count: int = 20,
    offset: int = 0,
    output_mode: str = "json",
) -> dict[str, Any]:
    """List saved searches as rule list abstraction."""
    return await _splunk_request(
        method="GET",
        path="/services/saved/searches",
        params={"count": count, "offset": offset, "output_mode": output_mode},
    )


async def soc_splunk_get_saved_search(
    search_name: str,
    output_mode: str = "json",
) -> dict[str, Any]:
    """Get one saved search as rule detail abstraction."""
    return await _splunk_request(
        method="GET",
        path=f"/services/saved/searches/{quote(search_name, safe='')}",
        params={"output_mode": output_mode},
    )


class SplunkSearchExportInput(BaseModel):
    search: str = Field(default="search index=*", description="SPL query string.")
    earliest_time: str = Field(default="-24h", description="Earliest time bound.")
    latest_time: str = Field(default="now", description="Latest time bound.")
    output_mode: str = Field(default="json", description="Response format.")


class SplunkListJobsInput(BaseModel):
    count: int = Field(default=20, description="Page size.")
    offset: int = Field(default=0, description="Offset.")
    output_mode: str = Field(default="json", description="Response format.")


class SplunkJobInput(BaseModel):
    sid: str = Field(description="Search job sid.")
    output_mode: str = Field(default="json", description="Response format.")


class SplunkJobEventsInput(BaseModel):
    sid: str = Field(description="Search job sid.")
    count: int = Field(default=100, description="Page size.")
    offset: int = Field(default=0, description="Offset.")
    output_mode: str = Field(default="json", description="Response format.")


class SplunkSavedSearchInput(BaseModel):
    search_name: str = Field(description="Saved search name.")
    output_mode: str = Field(default="json", description="Response format.")


class SplunkHuntCommonInput(BaseModel):
    index: str = Field(default="*", description="Splunk index name (optional, default '*').")
    earliest: str = Field(default="-15m", description="Earliest time bound.")
    latest: str = Field(default="now", description="Latest time bound.")


class SplunkPowerShellBypassInput(SplunkHuntCommonInput):
    host: str | None = Field(default=None, description="Optional host filter.")
    user: str | None = Field(default=None, description="Optional user filter.")


class SplunkHostTimelineInput(SplunkHuntCommonInput):
    host: str = Field(description="Target host name.")


class SplunkUserActivityInput(SplunkHuntCommonInput):
    user: str = Field(description="Target username.")


class SplunkNetworkConnectionsInput(SplunkHuntCommonInput):
    host: str | None = Field(default=None, description="Optional host filter.")
    dest_ip: str | None = Field(default=None, description="Optional destination IP filter.")


class SplunkLdapActivityInput(SplunkHuntCommonInput):
    host: str | None = Field(default=None, description="Optional host filter.")


class SplunkDomainAdminEnumInput(SplunkHuntCommonInput):
    pass


class SplunkLateralMovementInput(SplunkHuntCommonInput):
    indicator: str = Field(description="Keyword or artifact indicating lateral movement.")
    earliest: str = Field(default="-30m", description="Earliest time bound.")


class SplunkProcessTreeInput(SplunkHuntCommonInput):
    process_name: str = Field(description="Process name to trace.")


class SplunkFileActivityInput(SplunkHuntCommonInput):
    file_path: str | None = Field(default=None, description="Optional file path filter.")


class SplunkIndicatorSearchInput(SplunkHuntCommonInput):
    indicator: str = Field(description="IOC value (ip/domain/hash/url/text).")
    earliest: str = Field(default="-24h", description="Earliest time bound.")


def _build_search_spl(base: str, clauses: list[tuple[str, str | None]]) -> str:
    def _format_clause_value(raw: str) -> str:
        value = raw.strip()
        if _SPL_SAFE_UNQUOTED_RE.fullmatch(value):
            return value
        escaped = value.replace("\\", "\\\\").replace('"', '\\"')
        return f'"{escaped}"'

    parts = [base]
    for key, value in clauses:
        if isinstance(value, str) and value.strip():
            parts.append(f"{key}={_format_clause_value(value)}")
    return " ".join(parts)


async def soc_splunk_query_powershell_bypass(
    index: str = "*",
    host: str | None = None,
    user: str | None = None,
    earliest: str = "-15m",
    latest: str = "now",
) -> dict[str, Any]:
    spl = _build_search_spl(
        f'index={index} process_name=powershell.exe command_line="*ExecutionPolicy Bypass*"',
        [("host", host), ("user", user)],
    )
    return await soc_splunk_search_export(
        search=f"search {spl}",
        earliest_time=earliest,
        latest_time=latest,
    )


async def soc_splunk_query_host_timeline(
    host: str,
    index: str = "*",
    earliest: str = "-15m",
    latest: str = "now",
) -> dict[str, Any]:
    spl = f"index={index} host={host} | sort _time"
    return await soc_splunk_search_export(
        search=f"search {spl}",
        earliest_time=earliest,
        latest_time=latest,
    )


async def soc_splunk_query_user_activity(
    user: str,
    index: str = "*",
    earliest: str = "-15m",
    latest: str = "now",
) -> dict[str, Any]:
    spl = f"index={index} user={user} | stats count by process_name"
    return await soc_splunk_search_export(
        search=f"search {spl}",
        earliest_time=earliest,
        latest_time=latest,
    )


async def soc_splunk_query_network_connections(
    index: str = "*",
    host: str | None = None,
    dest_ip: str | None = None,
    earliest: str = "-15m",
    latest: str = "now",
) -> dict[str, Any]:
    spl = _build_search_spl(
        f"index={index} event_type=network",
        [("host", host), ("dest_ip", dest_ip)],
    )
    return await soc_splunk_search_export(
        search=f"search {spl}",
        earliest_time=earliest,
        latest_time=latest,
    )


async def soc_splunk_query_ldap_activity(
    index: str = "*",
    host: str | None = None,
    earliest: str = "-15m",
    latest: str = "now",
) -> dict[str, Any]:
    spl = _build_search_spl(f"index={index} event_type=ldap", [("host", host)])
    return await soc_splunk_search_export(
        search=f"search {spl}",
        earliest_time=earliest,
        latest_time=latest,
    )


async def soc_splunk_query_domain_admin_enum(
    index: str = "*",
    earliest: str = "-15m",
    latest: str = "now",
) -> dict[str, Any]:
    spl = f'index={index} command_line="*Domain Admins*"'
    return await soc_splunk_search_export(
        search=f"search {spl}",
        earliest_time=earliest,
        latest_time=latest,
    )


async def soc_splunk_query_lateral_movement(
    indicator: str,
    index: str = "*",
    earliest: str = "-30m",
    latest: str = "now",
) -> dict[str, Any]:
    spl = f'index={index} command_line="*{indicator}*" | stats dc(host) as host_count values(host)'
    return await soc_splunk_search_export(
        search=f"search {spl}",
        earliest_time=earliest,
        latest_time=latest,
    )


async def soc_splunk_query_process_tree(
    process_name: str,
    index: str = "*",
    earliest: str = "-15m",
    latest: str = "now",
) -> dict[str, Any]:
    spl = (
        f"index={index} process_name={process_name} "
        "| table _time host parent_process process_name command_line"
    )
    return await soc_splunk_search_export(
        search=f"search {spl}",
        earliest_time=earliest,
        latest_time=latest,
    )


async def soc_splunk_query_file_activity(
    index: str = "*",
    file_path: str | None = None,
    earliest: str = "-15m",
    latest: str = "now",
) -> dict[str, Any]:
    spl = _build_search_spl(
        f"index={index} event_type=file",
        [("file_path", file_path)],
    )
    return await soc_splunk_search_export(
        search=f"search {spl}",
        earliest_time=earliest,
        latest_time=latest,
    )


async def soc_splunk_query_indicator_search(
    indicator: str,
    index: str = "*",
    earliest: str = "-24h",
    latest: str = "now",
) -> dict[str, Any]:
    spl = f'index={index} "{indicator}"'
    return await soc_splunk_search_export(
        search=f"search {spl}",
        earliest_time=earliest,
        latest_time=latest,
    )


def create_soc_alert_splunk_tools() -> list[StructuredTool]:
    """Create Splunk read-only tools (backend mapping layer)."""
    return [
        StructuredTool.from_function(
            name="soc_splunk_search_export",
            description="Run Splunk export search.",
            func=soc_splunk_search_export,
            coroutine=soc_splunk_search_export,
            args_schema=SplunkSearchExportInput,
        ),
        StructuredTool.from_function(
            name="soc_splunk_list_jobs",
            description="List Splunk search jobs.",
            func=soc_splunk_list_jobs,
            coroutine=soc_splunk_list_jobs,
            args_schema=SplunkListJobsInput,
        ),
        StructuredTool.from_function(
            name="soc_splunk_get_job",
            description="Get one Splunk search job detail by sid.",
            func=soc_splunk_get_job,
            coroutine=soc_splunk_get_job,
            args_schema=SplunkJobInput,
        ),
        StructuredTool.from_function(
            name="soc_splunk_get_job_events",
            description="Get events for one Splunk search job.",
            func=soc_splunk_get_job_events,
            coroutine=soc_splunk_get_job_events,
            args_schema=SplunkJobEventsInput,
        ),
        StructuredTool.from_function(
            name="soc_splunk_get_job_timeline",
            description="Get timeline for one Splunk search job.",
            func=soc_splunk_get_job_timeline,
            coroutine=soc_splunk_get_job_timeline,
            args_schema=SplunkJobInput,
        ),
        StructuredTool.from_function(
            name="soc_splunk_get_job_search_log",
            description="Get search log for one Splunk search job.",
            func=soc_splunk_get_job_search_log,
            coroutine=soc_splunk_get_job_search_log,
            args_schema=SplunkJobInput,
        ),
        StructuredTool.from_function(
            name="soc_splunk_list_saved_searches",
            description="List Splunk saved searches.",
            func=soc_splunk_list_saved_searches,
            coroutine=soc_splunk_list_saved_searches,
            args_schema=SplunkListJobsInput,
        ),
        StructuredTool.from_function(
            name="soc_splunk_get_saved_search",
            description="Get one Splunk saved search by name.",
            func=soc_splunk_get_saved_search,
            coroutine=soc_splunk_get_saved_search,
            args_schema=SplunkSavedSearchInput,
        ),
        StructuredTool.from_function(
            name="soc_splunk_query_powershell_bypass",
            description="Hunt PowerShell ExecutionPolicy Bypass executions.",
            func=soc_splunk_query_powershell_bypass,
            coroutine=soc_splunk_query_powershell_bypass,
            args_schema=SplunkPowerShellBypassInput,
        ),
        StructuredTool.from_function(
            name="soc_splunk_query_host_timeline",
            description="Build host timeline sorted by event time.",
            func=soc_splunk_query_host_timeline,
            coroutine=soc_splunk_query_host_timeline,
            args_schema=SplunkHostTimelineInput,
        ),
        StructuredTool.from_function(
            name="soc_splunk_query_user_activity",
            description="Aggregate one user's process activity.",
            func=soc_splunk_query_user_activity,
            coroutine=soc_splunk_query_user_activity,
            args_schema=SplunkUserActivityInput,
        ),
        StructuredTool.from_function(
            name="soc_splunk_query_network_connections",
            description="Query network events by host or destination IP.",
            func=soc_splunk_query_network_connections,
            coroutine=soc_splunk_query_network_connections,
            args_schema=SplunkNetworkConnectionsInput,
        ),
        StructuredTool.from_function(
            name="soc_splunk_query_ldap_activity",
            description="Query LDAP-related activity events.",
            func=soc_splunk_query_ldap_activity,
            coroutine=soc_splunk_query_ldap_activity,
            args_schema=SplunkLdapActivityInput,
        ),
        StructuredTool.from_function(
            name="soc_splunk_query_domain_admin_enum",
            description="Hunt Domain Admins enumeration commands.",
            func=soc_splunk_query_domain_admin_enum,
            coroutine=soc_splunk_query_domain_admin_enum,
            args_schema=SplunkDomainAdminEnumInput,
        ),
        StructuredTool.from_function(
            name="soc_splunk_query_lateral_movement",
            description="Detect lateral movement by indicator spread across hosts.",
            func=soc_splunk_query_lateral_movement,
            coroutine=soc_splunk_query_lateral_movement,
            args_schema=SplunkLateralMovementInput,
        ),
        StructuredTool.from_function(
            name="soc_splunk_query_process_tree",
            description="Trace process tree information for one process name.",
            func=soc_splunk_query_process_tree,
            coroutine=soc_splunk_query_process_tree,
            args_schema=SplunkProcessTreeInput,
        ),
        StructuredTool.from_function(
            name="soc_splunk_query_file_activity",
            description="Query file operation events with optional file path.",
            func=soc_splunk_query_file_activity,
            coroutine=soc_splunk_query_file_activity,
            args_schema=SplunkFileActivityInput,
        ),
        StructuredTool.from_function(
            name="soc_splunk_query_indicator_search",
            description="Search one IOC indicator in Splunk events.",
            func=soc_splunk_query_indicator_search,
            coroutine=soc_splunk_query_indicator_search,
            args_schema=SplunkIndicatorSearchInput,
        ),
    ]

