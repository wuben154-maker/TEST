"""OneSec EDR API tools for SOC alert profile."""

from __future__ import annotations

from typing import Any

import httpx
from langchain_core.tools import StructuredTool
from pydantic import BaseModel, Field

from ..api_service_config import load_api_service_config


class SocEdrEndpointAlertsInput(BaseModel):
    """Input schema for querying EDR endpoint alerts."""

    sql: str = Field(
        default="",
        description="Optional EDR query expression. Empty means provider default.",
    )
    time_from: int | None = Field(default=None, description="Unix seconds start timestamp (optional).")
    time_to: int | None = Field(default=None, description="Unix seconds end timestamp (optional).")
    cur_page: int = Field(default=1, description="Page number.")
    page_size: int = Field(default=20, description="Page size.")


class SocEdrIncidentsInput(BaseModel):
    """Input schema for querying EDR incidents (read-only)."""

    cur_page: int = Field(default=1, description="Page number.")
    page_size: int = Field(default=20, description="Page size.")
    time_from: int | None = Field(default=None, description="Unix start timestamp.")
    time_to: int | None = Field(default=None, description="Unix end timestamp.")


class SocEdrThreatFilesInput(BaseModel):
    """Input schema for querying EDR threat files (read-only)."""

    sql: str = Field(
        default="",
        description="Optional EDR query expression. Empty means provider default.",
    )
    cur_page: int = Field(default=1, description="Page number.")
    page_size: int = Field(default=20, description="Page size.")
    time_from: int | None = Field(default=None, description="Unix start timestamp.")
    time_to: int | None = Field(default=None, description="Unix end timestamp.")


class SocEdrRecentEndpointAlertsInput(BaseModel):
    """Input schema for querying recent EDR endpoint alerts (24h window)."""

    sql: str = Field(default="", description="Optional EDR query expression.")
    search_fields: list[str] | None = Field(default=None, description="Optional list of fields to search.")
    time_from: int | None = Field(default=None, description="Unix start timestamp.")
    time_to: int | None = Field(default=None, description="Unix end timestamp.")


class SocEdrThreatActivitiesInput(BaseModel):
    """Input schema for querying EDR threat activities (read-only)."""

    cur_page: int = Field(default=1, description="Page number.")
    page_size: int = Field(default=20, description="Page size.")
    time_from: int | None = Field(default=None, description="Unix start timestamp.")
    time_to: int | None = Field(default=None, description="Unix end timestamp.")
    group_list: list[int] | None = Field(default=None, description="Optional group ids.")
    threat_phase_list: list[dict[str, Any]] | None = Field(default=None, description="Optional threat phase filter list.")


class SocEdrRecentThreatActivitiesInput(BaseModel):
    """Input schema for querying recent EDR threat activities (24h window)."""

    time_from: int | None = Field(default=None, description="Unix start timestamp.")
    time_to: int | None = Field(default=None, description="Unix end timestamp.")
    group_list: list[int] | None = Field(default=None, description="Optional group ids.")
    threat_phase_list: list[dict[str, Any]] | None = Field(default=None, description="Optional threat phase filter list.")


class SocEdrRecentIncidentsInput(BaseModel):
    """Input schema for querying recent EDR incidents (24h window)."""

    time_from: int | None = Field(default=None, description="Unix start timestamp.")
    time_to: int | None = Field(default=None, description="Unix end timestamp.")
    params: list[dict[str, Any]] | None = Field(default=None, description="Optional advanced incident filter params.")


class SocEdrRecentThreatFilesInput(BaseModel):
    """Input schema for querying recent EDR threat files (24h window)."""

    time_from: int | None = Field(default=None, description="Unix start timestamp.")
    time_to: int | None = Field(default=None, description="Unix end timestamp.")
    group_list: list[int] | None = Field(default=None, description="Optional group ids.")
    threat_severity: list[int] | None = Field(default=None, description="Optional threat severity filter list.")


class SocEdrThreatDisposalsInput(BaseModel):
    """Input schema for querying EDR threat disposals."""

    incident_id: str = Field(description="Incident id.")
    umid: str = Field(description="Endpoint umid.")
    cur_page: int = Field(default=1, description="Page number.")
    page_size: int = Field(default=20, description="Page size.")
    sort_by: str | None = Field(default=None, description="Optional sort field.")
    sort_order: str | None = Field(default=None, description="Optional sort order.")


class SocEdrRecentThreatDisposalsInput(BaseModel):
    """Input schema for querying recent EDR threat disposals."""

    incident_id: str = Field(description="Incident id.")
    umid: str = Field(description="Endpoint umid.")
    sort_by: str | None = Field(default=None, description="Optional sort field.")
    sort_order: str | None = Field(default=None, description="Optional sort order.")


class SocEdrThreatTimelineInput(BaseModel):
    """Input schema for querying EDR threat timeline."""

    cur_page: int = Field(default=1, description="Page number.")
    page_size: int = Field(default=20, description="Page size.")
    time_from: int | None = Field(default=None, description="Unix start timestamp.")
    time_to: int | None = Field(default=None, description="Unix end timestamp.")


class SocEdrRecentThreatTimelineInput(BaseModel):
    """Input schema for querying recent EDR threat timeline (24h window)."""

    time_from: int | None = Field(default=None, description="Unix start timestamp.")
    time_to: int | None = Field(default=None, description="Unix end timestamp.")


class SocEdrIocListInput(BaseModel):
    """Input schema for querying EDR IOC list."""

    cur_page: int = Field(default=1, description="Page number.")
    page_size: int = Field(default=20, description="Page size.")
    fuzzy: str = Field(default="", description="Optional fuzzy query keyword.")
    ioc_severity_list: list[int] | None = Field(default=None, description="Optional IOC severity filter list.")
    sort_by: str | None = Field(default=None, description="Optional sort field.")
    sort_order: str | None = Field(default=None, description="Optional sort order.")


class SocEdrActionStatusInput(BaseModel):
    """Input schema for querying EDR action task status."""

    task_id: int = Field(description="Action task id.")
    cur_page: int = Field(default=1, description="Page number.")
    page_size: int = Field(default=20, description="Page size.")
    time_sort: int | None = Field(default=None, description="Optional task sort type.")


def _simulated_payload(provider: str, detail: dict[str, Any]) -> dict[str, Any]:
    return {"simulated": True, "provider": provider, **detail}


async def _edr_action(action: str, payload: dict[str, Any]) -> dict[str, Any]:
    svc = load_api_service_config("onesec_api")
    if not svc.enabled or not svc.base_url:
        return _simulated_payload(
            "edr",
            {"action": action, **payload, "note": "onesec_api not configured/enabled."},
        )
    req = {"action": action, **payload}
    headers: dict[str, str] = {"Content-Type": "application/json"}
    if svc.api_key:
        headers["Authorization"] = f"Bearer {svc.api_key}"
    async with httpx.AsyncClient(timeout=float(svc.timeout)) as client:
        try:
            resp = await client.post(f"{svc.base_url}/edr", headers=headers, json=req)
            resp.raise_for_status()
            return {"provider": "edr", "action": action, "data": resp.json()}
        except Exception as exc:
            return {"provider": "edr", "action": action, "error": str(exc)}


def _edr_payload(**kwargs: Any) -> dict[str, Any]:
    payload: dict[str, Any] = {}
    for key, value in kwargs.items():
        if value is None:
            continue
        if isinstance(value, str) and not value.strip():
            continue
        payload[key] = value
    return payload


async def soc_edr_endpoint_alerts(sql: str = "", time_from: int | None = None, time_to: int | None = None, cur_page: int = 1, page_size: int = 20) -> dict[str, Any]:
    payload = _edr_payload(sql=sql, cur_page=cur_page, page_size=page_size, time_from=time_from, time_to=time_to)
    return await _edr_action("edr_get_endpoint_alerts", payload)


async def soc_edr_incidents(cur_page: int = 1, page_size: int = 20, time_from: int | None = None, time_to: int | None = None) -> dict[str, Any]:
    payload = _edr_payload(cur_page=cur_page, page_size=page_size, time_from=time_from, time_to=time_to)
    return await _edr_action("edr_get_incidents", payload)


async def soc_edr_threat_files(sql: str = "", cur_page: int = 1, page_size: int = 20, time_from: int | None = None, time_to: int | None = None) -> dict[str, Any]:
    payload = _edr_payload(sql=sql, cur_page=cur_page, page_size=page_size, time_from=time_from, time_to=time_to)
    return await _edr_action("edr_get_threat_files", payload)


async def soc_edr_recent_endpoint_alerts(sql: str = "", search_fields: list[str] | None = None, time_from: int | None = None, time_to: int | None = None) -> dict[str, Any]:
    payload = _edr_payload(sql=sql, search_fields=search_fields, time_from=time_from, time_to=time_to)
    return await _edr_action("edr_get_recent_endpoint_alerts", payload)


async def soc_edr_threat_activities(cur_page: int = 1, page_size: int = 20, time_from: int | None = None, time_to: int | None = None, group_list: list[int] | None = None, threat_phase_list: list[dict[str, Any]] | None = None) -> dict[str, Any]:
    payload = _edr_payload(cur_page=cur_page, page_size=page_size, time_from=time_from, time_to=time_to, group_list=group_list, threat_phase_list=threat_phase_list)
    return await _edr_action("edr_get_threat_activities", payload)


async def soc_edr_recent_threat_activities(time_from: int | None = None, time_to: int | None = None, group_list: list[int] | None = None, threat_phase_list: list[dict[str, Any]] | None = None) -> dict[str, Any]:
    payload = _edr_payload(time_from=time_from, time_to=time_to, group_list=group_list, threat_phase_list=threat_phase_list)
    return await _edr_action("edr_get_recent_threat_activities", payload)


async def soc_edr_recent_incidents(time_from: int | None = None, time_to: int | None = None, params: list[dict[str, Any]] | None = None) -> dict[str, Any]:
    payload = _edr_payload(time_from=time_from, time_to=time_to, params=params)
    return await _edr_action("edr_get_recent_incidents", payload)


async def soc_edr_recent_threat_files(time_from: int | None = None, time_to: int | None = None, group_list: list[int] | None = None, threat_severity: list[int] | None = None) -> dict[str, Any]:
    payload = _edr_payload(time_from=time_from, time_to=time_to, group_list=group_list, threat_severity=threat_severity)
    return await _edr_action("edr_get_recent_threat_files", payload)


async def soc_edr_threat_disposals(incident_id: str, umid: str, cur_page: int = 1, page_size: int = 20, sort_by: str | None = None, sort_order: str | None = None) -> dict[str, Any]:
    payload = _edr_payload(incident_id=incident_id, umid=umid, cur_page=cur_page, page_size=page_size, sort_by=sort_by, sort_order=sort_order)
    return await _edr_action("edr_get_threat_disposals", payload)


async def soc_edr_recent_threat_disposals(incident_id: str, umid: str, sort_by: str | None = None, sort_order: str | None = None) -> dict[str, Any]:
    payload = _edr_payload(incident_id=incident_id, umid=umid, sort_by=sort_by, sort_order=sort_order)
    return await _edr_action("edr_get_recent_threat_disposals", payload)


async def soc_edr_threat_timeline(cur_page: int = 1, page_size: int = 20, time_from: int | None = None, time_to: int | None = None) -> dict[str, Any]:
    payload = _edr_payload(cur_page=cur_page, page_size=page_size, time_from=time_from, time_to=time_to)
    return await _edr_action("edr_get_threat_timeline", payload)


async def soc_edr_recent_threat_timeline(time_from: int | None = None, time_to: int | None = None) -> dict[str, Any]:
    payload = _edr_payload(time_from=time_from, time_to=time_to)
    return await _edr_action("edr_get_recent_threat_timeline", payload)


async def soc_edr_ioc_list(cur_page: int = 1, page_size: int = 20, fuzzy: str = "", ioc_severity_list: list[int] | None = None, sort_by: str | None = None, sort_order: str | None = None) -> dict[str, Any]:
    payload = _edr_payload(cur_page=cur_page, page_size=page_size, fuzzy=fuzzy, ioc_severity_list=ioc_severity_list, sort_by=sort_by, sort_order=sort_order)
    return await _edr_action("edr_get_ioc_list", payload)


async def soc_edr_action_status(task_id: int, cur_page: int = 1, page_size: int = 20, time_sort: int | None = None) -> dict[str, Any]:
    payload = _edr_payload(task_id=task_id, cur_page=cur_page, page_size=page_size, time_sort=time_sort)
    return await _edr_action("edr_get_action_status", payload)


def create_soc_alert_onesec_tools() -> list[StructuredTool]:
    """Create OneSec EDR tools for SOC alert."""
    return [
        StructuredTool.from_function(name="soc_edr_endpoint_alerts", description="Query EDR endpoint alert logs for SOC triage.", func=soc_edr_endpoint_alerts, coroutine=soc_edr_endpoint_alerts, args_schema=SocEdrEndpointAlertsInput),
        StructuredTool.from_function(name="soc_edr_incidents", description="Query EDR incident list (read-only).", func=soc_edr_incidents, coroutine=soc_edr_incidents, args_schema=SocEdrIncidentsInput),
        StructuredTool.from_function(name="soc_edr_threat_files", description="Query EDR threat files list (read-only).", func=soc_edr_threat_files, coroutine=soc_edr_threat_files, args_schema=SocEdrThreatFilesInput),
        StructuredTool.from_function(name="soc_edr_recent_endpoint_alerts", description="Query recent EDR endpoint alert logs (24h window).", func=soc_edr_recent_endpoint_alerts, coroutine=soc_edr_recent_endpoint_alerts, args_schema=SocEdrRecentEndpointAlertsInput),
        StructuredTool.from_function(name="soc_edr_threat_activities", description="Query EDR threat activities list (read-only).", func=soc_edr_threat_activities, coroutine=soc_edr_threat_activities, args_schema=SocEdrThreatActivitiesInput),
        StructuredTool.from_function(name="soc_edr_recent_threat_activities", description="Query recent EDR threat activities (24h window).", func=soc_edr_recent_threat_activities, coroutine=soc_edr_recent_threat_activities, args_schema=SocEdrRecentThreatActivitiesInput),
        StructuredTool.from_function(name="soc_edr_recent_incidents", description="Query recent EDR incidents (24h window).", func=soc_edr_recent_incidents, coroutine=soc_edr_recent_incidents, args_schema=SocEdrRecentIncidentsInput),
        StructuredTool.from_function(name="soc_edr_recent_threat_files", description="Query recent EDR threat files (24h window).", func=soc_edr_recent_threat_files, coroutine=soc_edr_recent_threat_files, args_schema=SocEdrRecentThreatFilesInput),
        StructuredTool.from_function(name="soc_edr_threat_disposals", description="Query EDR threat disposal list (read-only).", func=soc_edr_threat_disposals, coroutine=soc_edr_threat_disposals, args_schema=SocEdrThreatDisposalsInput),
        StructuredTool.from_function(name="soc_edr_recent_threat_disposals", description="Query recent EDR threat disposal list (read-only).", func=soc_edr_recent_threat_disposals, coroutine=soc_edr_recent_threat_disposals, args_schema=SocEdrRecentThreatDisposalsInput),
        StructuredTool.from_function(name="soc_edr_threat_timeline", description="Query EDR threat timeline list (read-only).", func=soc_edr_threat_timeline, coroutine=soc_edr_threat_timeline, args_schema=SocEdrThreatTimelineInput),
        StructuredTool.from_function(name="soc_edr_recent_threat_timeline", description="Query recent EDR threat timeline (24h window).", func=soc_edr_recent_threat_timeline, coroutine=soc_edr_recent_threat_timeline, args_schema=SocEdrRecentThreatTimelineInput),
        StructuredTool.from_function(name="soc_edr_ioc_list", description="Query EDR IOC list (read-only).", func=soc_edr_ioc_list, coroutine=soc_edr_ioc_list, args_schema=SocEdrIocListInput),
        StructuredTool.from_function(name="soc_edr_action_status", description="Query EDR action task status (read-only).", func=soc_edr_action_status, coroutine=soc_edr_action_status, args_schema=SocEdrActionStatusInput),
    ]
