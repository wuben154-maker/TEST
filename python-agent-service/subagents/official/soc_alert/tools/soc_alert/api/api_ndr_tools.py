"""NDR API tools for SOC alert profile."""

from __future__ import annotations

import hashlib
import hmac
import json
import time
from base64 import urlsafe_b64encode
from typing import Any

import httpx
from langchain_core.tools import StructuredTool
from pydantic import BaseModel, Field

from .api_service_config import load_api_service_config


class SocNdrLogSearchInput(BaseModel):
    """Input schema for NDR log search."""

    action: str = Field(default="search", description="search or terms.")
    sql: str = Field(default="threat.level = 'attack'", description="NDR SQL filter expression.")
    time_from: int | None = Field(default=None, description="Unix seconds start timestamp (optional).")
    time_to: int | None = Field(default=None, description="Unix seconds end timestamp (optional).")
    size: int = Field(default=10, description="Result size or bucket size.")
    term: str | None = Field(default=None, description="Terms aggregation field.")


class SocNdrMdrAlertListInput(BaseModel):
    """Input schema for querying NDR MDR alert list."""

    cur_page: int = Field(default=1, description="Page number.")
    page_size: int = Field(default=20, description="Page size.")
    time_from: int | None = Field(default=None, description="Unix start timestamp.")
    time_to: int | None = Field(default=None, description="Unix end timestamp.")


class SocNdrDashboardStatusInput(BaseModel):
    """Input schema for querying NDR dashboard status widgets."""

    action: str = Field(default="status", description="Dashboard action, e.g. status/security/threat_event/alert_sum.")
    time_from: int | None = Field(default=None, description="Unix start timestamp.")
    time_to: int | None = Field(default=None, description="Unix end timestamp.")
    assets_group: list[int] | None = Field(default=None, description="Optional asset groups.")


class SocNdrIncidentListInput(BaseModel):
    """Input schema for querying NDR incident investigation list."""

    action: str = Field(default="search", description="Incident action, e.g. search/top_attacked_entity/result/timeline.")
    incident_id: str = Field(default="", description="Incident id for detail actions.")
    time_from: int | None = Field(default=None, description="Unix start timestamp.")
    time_to: int | None = Field(default=None, description="Unix end timestamp.")
    cur_page: int = Field(default=1, description="Page number for search action.")
    page_size: int = Field(default=20, description="Page size for search action.")


class SocNdrHostThreatListInput(BaseModel):
    """Input schema for querying NDR host threat list."""

    action: str = Field(default="summary", description="Host threat action: summary or events.")
    asset_machine: str = Field(default="", description="Asset machine id/name for events.")
    time_from: int | None = Field(default=None, description="Unix start timestamp.")
    time_to: int | None = Field(default=None, description="Unix end timestamp.")
    cur_page: int = Field(default=1, description="Page number for events.")
    page_size: int = Field(default=20, description="Page size for events.")


class SocNdrVulnerabilityListInput(BaseModel):
    """Input schema for querying NDR vulnerability list."""

    time_from: int | None = Field(default=None, description="Unix start timestamp.")
    time_to: int | None = Field(default=None, description="Unix end timestamp.")
    cur_page: int = Field(default=1, description="Page number.")
    page_size: int = Field(default=20, description="Page size.")


class SocNdrSystemStatusInput(BaseModel):
    """Input schema for querying NDR system status."""

    action: str = Field(default="all", description="System status action: all/core/ioc_update/hardware/input/database/timezone/service/cloud_connectivity.")


class SocNdrMachineAssetListInput(BaseModel):
    """Input schema for querying NDR machine/service asset list."""

    action: str = Field(default="service_list", description="Asset action: service_list/host_asset_list/web_app_framework_list.")
    cur_page: int = Field(default=1, description="Page number.")
    page_size: int = Field(default=20, description="Page size.")


class SocNdrAssetsDomainListInput(BaseModel):
    """Input schema for querying NDR domain asset list."""

    time_from: int | None = Field(default=None, description="Unix start timestamp.")
    time_to: int | None = Field(default=None, description="Unix end timestamp.")
    cur_page: int = Field(default=1, description="Page number.")
    page_size: int = Field(default=20, description="Page size.")


class SocNdrInterfaceRiskListInput(BaseModel):
    """Input schema for querying NDR API risk list."""

    time_from: int | None = Field(default=None, description="Unix start timestamp.")
    time_to: int | None = Field(default=None, description="Unix end timestamp.")
    cur_page: int = Field(default=1, description="Page number.")
    page_size: int = Field(default=20, description="Page size.")


class SocNdrInterfaceListInput(BaseModel):
    """Input schema for querying NDR API interface list."""

    time_from: int | None = Field(default=None, description="Unix start timestamp.")
    time_to: int | None = Field(default=None, description="Unix end timestamp.")
    cur_page: int = Field(default=1, description="Page number.")
    page_size: int = Field(default=20, description="Page size.")


class SocNdrLoginApiListInput(BaseModel):
    """Input schema for querying NDR login API list."""

    action: str = Field(default="list", description="Action: list/summary/category.")
    time_from: int | None = Field(default=None, description="Unix start timestamp.")
    time_to: int | None = Field(default=None, description="Unix end timestamp.")
    cur_page: int = Field(default=1, description="Page number for list action.")
    page_size: int = Field(default=20, description="Page size for list action.")
    app_class: str = Field(default="", description="Optional app class filter.")
    category: str = Field(default="", description="Optional category filter.")


class SocNdrLoginWeakpwdListInput(BaseModel):
    """Input schema for querying NDR weak password list."""

    time_from: int | None = Field(default=None, description="Unix start timestamp.")
    time_to: int | None = Field(default=None, description="Unix end timestamp.")
    cur_page: int = Field(default=1, description="Page number.")
    page_size: int = Field(default=20, description="Page size.")


class SocNdrCloudFacilitiesInput(BaseModel):
    """Input schema for querying NDR cloud facilities statistics."""

    action: str = Field(default="access_source", description="Action: access_source/assets_info/instance_list/instance_access_list.")
    time_from: int | None = Field(default=None, description="Unix start timestamp.")
    time_to: int | None = Field(default=None, description="Unix end timestamp.")
    source_ip: str = Field(default="", description="Required for assets_info action.")
    cur_page: int = Field(default=1, description="Page number.")
    page_size: int = Field(default=20, description="Page size.")


class SocNdrPrivacyDiagramInput(BaseModel):
    """Input schema for querying NDR privacy overview diagram."""

    time_from: int | None = Field(default=None, description="Unix start timestamp.")
    time_to: int | None = Field(default=None, description="Unix end timestamp.")


class SocNdrThreatInboundAttackInput(BaseModel):
    """Input schema for querying NDR inbound attack severity distribution."""

    time_from: int | None = Field(default=None, description="Unix start timestamp.")
    time_to: int | None = Field(default=None, description="Unix end timestamp.")


def _simulated_payload(provider: str, detail: dict[str, Any]) -> dict[str, Any]:
    return {"simulated": True, "provider": provider, **detail}


def _ndr_signature(api_key: str, secret: str, timestamp: str, body: str) -> str:
    raw = f"{api_key}{timestamp}{body}".encode("utf-8")
    digest = hmac.new(secret.encode("utf-8"), raw, hashlib.sha256).digest()
    return urlsafe_b64encode(digest).decode("utf-8").rstrip("=")


async def _ndr_post(path: str, payload: dict[str, Any], action: str) -> dict[str, Any]:
    svc = load_api_service_config("tdp_api")
    if not svc.enabled or not svc.base_url:
        return _simulated_payload(
            "ndr",
            {"action": action, **payload, "note": "tdp_api not configured/enabled."},
        )
    body_text = json.dumps(payload, ensure_ascii=False, separators=(",", ":"))
    headers: dict[str, str] = {"Content-Type": "application/json"}
    if svc.api_key and svc.secret:
        ts = str(int(time.time()))
        sign = _ndr_signature(svc.api_key, svc.secret, ts, body_text)
        headers.update({"X-API-KEY": svc.api_key, "X-SIGNATURE": sign, "X-TIMESTAMP": ts})
    async with httpx.AsyncClient(timeout=float(svc.timeout)) as client:
        try:
            resp = await client.post(f"{svc.base_url}{path}", headers=headers, content=body_text)
            resp.raise_for_status()
            return {"provider": "ndr", "action": action, "data": resp.json()}
        except Exception as exc:
            return {"provider": "ndr", "action": action, "error": str(exc)}


async def soc_ndr_log_search(action: str = "search", sql: str = "threat.level = 'attack'", time_from: int | None = None, time_to: int | None = None, size: int = 10, term: str | None = None) -> dict[str, Any]:
    endpoint = "/api/v1/log/search" if action == "search" else "/api/v1/log/terms"
    body_payload: dict[str, Any] = {"sql": sql, "size": size}
    if time_from is not None:
        body_payload["time_from"] = time_from
    if time_to is not None:
        body_payload["time_to"] = time_to
    if term:
        body_payload["term"] = term
    return await _ndr_post(endpoint, body_payload, action)


async def soc_ndr_mdr_alert_list(cur_page: int = 1, page_size: int = 20, time_from: int | None = None, time_to: int | None = None) -> dict[str, Any]:
    payload: dict[str, Any] = {"cur_page": cur_page, "page_size": page_size}
    if time_from is not None:
        payload["time_from"] = time_from
    if time_to is not None:
        payload["time_to"] = time_to
    return await _ndr_post("/api/v1/mdr/alerts", payload, "ndr_mdr_alert_list")


async def soc_ndr_dashboard_status(action: str = "status", time_from: int | None = None, time_to: int | None = None, assets_group: list[int] | None = None) -> dict[str, Any]:
    endpoint_map = {
        "status": "/api/v1/dashboard/status",
        "security": "/api/v1/dashboard/security",
        "threat_event": "/api/v1/dashboard/threaten_event",
        "alert_sum": "/api/v1/alert/getSumList",
    }
    endpoint = endpoint_map.get(action, endpoint_map["status"])
    payload: dict[str, Any] = {}
    if action == "alert_sum":
        condition: dict[str, Any] = {}
        if time_from is not None:
            condition["time_from"] = time_from
        if time_to is not None:
            condition["time_to"] = time_to
        if assets_group:
            condition["assets_group"] = assets_group
        if condition:
            payload["condition"] = condition
    else:
        if time_from is not None:
            payload["time_from"] = time_from
        if time_to is not None:
            payload["time_to"] = time_to
        if assets_group:
            payload["assets_group"] = assets_group
    return await _ndr_post(endpoint, payload, f"ndr_dashboard_status:{action}")


async def soc_ndr_incident_list(action: str = "search", incident_id: str = "", time_from: int | None = None, time_to: int | None = None, cur_page: int = 1, page_size: int = 20) -> dict[str, Any]:
    endpoint_map = {
        "search": "/api/v1/incident/search",
        "top_attacked_entity": "/api/v1/incident/topAttackedEntity",
        "result": "/api/v1/incident/result",
        "timeline": "/api/v1/incident/timeline",
    }
    endpoint = endpoint_map.get(action, endpoint_map["search"])
    payload: dict[str, Any] = {}
    if action == "search":
        condition: dict[str, Any] = {}
        if time_from is not None:
            condition["time_from"] = time_from
        if time_to is not None:
            condition["time_to"] = time_to
        payload["condition"] = condition
        payload["page"] = {"cur_page": cur_page, "page_size": page_size}
    else:
        if incident_id.strip():
            payload["incident_id"] = incident_id
        if time_from is not None:
            payload["time_from"] = time_from
        if time_to is not None:
            payload["time_to"] = time_to
    return await _ndr_post(endpoint, payload, f"ndr_incident_list:{action}")


async def soc_ndr_host_threat_list(action: str = "summary", asset_machine: str = "", time_from: int | None = None, time_to: int | None = None, cur_page: int = 1, page_size: int = 20) -> dict[str, Any]:
    endpoint = "/api/v1/host/getFallHostSumList" if action == "summary" else "/api/v1/host/threat/list"
    condition: dict[str, Any] = {}
    if time_from is not None:
        condition["time_from"] = time_from
    if time_to is not None:
        condition["time_to"] = time_to
    if asset_machine.strip():
        condition["asset_machine"] = asset_machine
    payload: dict[str, Any] = {"condition": condition}
    if action != "summary":
        payload["page"] = {"cur_page": cur_page, "page_size": page_size}
    return await _ndr_post(endpoint, payload, f"ndr_host_threat_list:{action}")


async def soc_ndr_vulnerability_list(time_from: int | None = None, time_to: int | None = None, cur_page: int = 1, page_size: int = 20) -> dict[str, Any]:
    condition: dict[str, Any] = {}
    if time_from is not None:
        condition["time_from"] = time_from
    if time_to is not None:
        condition["time_to"] = time_to
    payload: dict[str, Any] = {"condition": condition, "page": {"cur_page": cur_page, "page_size": page_size}}
    return await _ndr_post("/api/v1/vulnerability/vulnerabilityList", payload, "ndr_vulnerability_list")


async def soc_ndr_system_status(action: str = "all") -> dict[str, Any]:
    endpoint_map = {
        "core": "/api/v1/core-status",
        "ioc_update": "/api/v1/ioc-update-status",
        "hardware": "/api/v1/hardware-status",
        "input": "/api/v1/input-status",
        "database": "/api/v1/db-status",
        "timezone": "/api/v1/timezone-status",
        "service": "/api/v1/service-status",
        "cloud_connectivity": "/api/v1/cloud-connectivity-status",
    }
    if action == "all":
        data: dict[str, Any] = {}
        for item_action, endpoint in endpoint_map.items():
            result = await _ndr_post(endpoint, {}, f"ndr_system_status:{item_action}")
            data[item_action] = result.get("data") if isinstance(result, dict) else result
        return {"provider": "ndr", "action": "ndr_system_status:all", "data": data}
    endpoint = endpoint_map.get(action, endpoint_map["core"])
    return await _ndr_post(endpoint, {}, f"ndr_system_status:{action}")


async def soc_ndr_machine_asset_list(action: str = "service_list", cur_page: int = 1, page_size: int = 20) -> dict[str, Any]:
    endpoint_map = {
        "service_list": "/api/v1/machine/list",
        "host_asset_list": "/api/v1/machine/list",
        "web_app_framework_list": "/api/v1/machine/appFrame/detailList",
    }
    endpoint = endpoint_map.get(action, endpoint_map["service_list"])
    payload = {"condition": {}, "page": {"cur_page": cur_page, "page_size": page_size}}
    return await _ndr_post(endpoint, payload, f"ndr_machine_asset_list:{action}")


async def soc_ndr_assets_domain_list(time_from: int | None = None, time_to: int | None = None, cur_page: int = 1, page_size: int = 20) -> dict[str, Any]:
    condition: dict[str, Any] = {}
    if time_from is not None:
        condition["time_from"] = time_from
    if time_to is not None:
        condition["time_to"] = time_to
    payload: dict[str, Any] = {"condition": condition, "page": {"cur_page": cur_page, "page_size": page_size}}
    return await _ndr_post("/api/v1/assets/domainName/search", payload, "ndr_assets_domain_list")


async def soc_ndr_interface_risk_list(time_from: int | None = None, time_to: int | None = None, cur_page: int = 1, page_size: int = 20) -> dict[str, Any]:
    condition: dict[str, Any] = {}
    if time_from is not None:
        condition["time_from"] = time_from
    if time_to is not None:
        condition["time_to"] = time_to
    payload: dict[str, Any] = {"condition": condition, "page": {"cur_page": cur_page, "page_size": page_size}}
    return await _ndr_post("/api/v1/interface/risk/getApiList", payload, "ndr_interface_risk_list")


async def soc_ndr_interface_list(time_from: int | None = None, time_to: int | None = None, cur_page: int = 1, page_size: int = 20) -> dict[str, Any]:
    condition: dict[str, Any] = {}
    if time_from is not None:
        condition["time_from"] = time_from
    if time_to is not None:
        condition["time_to"] = time_to
    payload: dict[str, Any] = {"condition": condition, "page": {"cur_page": cur_page, "page_size": page_size}}
    return await _ndr_post("/api/v1/interface/list", payload, "ndr_interface_list")


async def soc_ndr_login_api_list(action: str = "list", time_from: int | None = None, time_to: int | None = None, cur_page: int = 1, page_size: int = 20, app_class: str = "", category: str = "") -> dict[str, Any]:
    endpoint_map = {
        "list": "/api/v1/loginApi/list",
        "summary": "/api/v1/loginApi/countOfAppClass",
        "category": "/api/v1/loginApi/rightTopScreen",
    }
    endpoint = endpoint_map.get(action, endpoint_map["list"])
    payload: dict[str, Any] = {}
    if action == "list":
        condition: dict[str, Any] = {}
        if time_from is not None:
            condition["time_from"] = time_from
        if time_to is not None:
            condition["time_to"] = time_to
        if app_class.strip():
            condition["app_class"] = app_class
        if category.strip():
            condition["category"] = category
        payload["condition"] = condition
        payload["page"] = {"cur_page": cur_page, "page_size": page_size}
    else:
        if time_from is not None:
            payload["time_from"] = time_from
        if time_to is not None:
            payload["time_to"] = time_to
        if app_class.strip():
            payload["app_class"] = app_class
        if category.strip():
            payload["category"] = category
    return await _ndr_post(endpoint, payload, f"ndr_login_api_list:{action}")


async def soc_ndr_login_weakpwd_list(time_from: int | None = None, time_to: int | None = None, cur_page: int = 1, page_size: int = 20) -> dict[str, Any]:
    condition: dict[str, Any] = {}
    if time_from is not None:
        condition["time_from"] = time_from
    if time_to is not None:
        condition["time_to"] = time_to
    payload: dict[str, Any] = {"condition": condition, "page": {"cur_page": cur_page, "page_size": page_size}}
    return await _ndr_post("/api/v1/login/weakpwd/list", payload, "ndr_login_weakpwd_list")


async def soc_ndr_cloud_facilities(action: str = "access_source", time_from: int | None = None, time_to: int | None = None, source_ip: str = "", cur_page: int = 1, page_size: int = 20) -> dict[str, Any]:
    endpoint_map = {
        "access_source": "/api/v1/cloud-facilities/access-source",
        "assets_info": "/api/v1/cloud-facilities/assets-info",
        "instance_list": "/api/v1/cloud-facilities/instance-info-list",
        "instance_access_list": "/api/v1/cloud-facilities/instance-access-list",
    }
    endpoint = endpoint_map.get(action, endpoint_map["access_source"])
    condition: dict[str, Any] = {}
    if time_from is not None:
        condition["time_from"] = time_from
    if time_to is not None:
        condition["time_to"] = time_to
    if source_ip.strip():
        condition["source_ip"] = source_ip
    payload: dict[str, Any] = {"condition": condition, "page": {"cur_page": cur_page, "page_size": page_size}}
    return await _ndr_post(endpoint, payload, f"ndr_cloud_facilities:{action}")


async def soc_ndr_privacy_diagram(time_from: int | None = None, time_to: int | None = None) -> dict[str, Any]:
    condition: dict[str, Any] = {}
    if time_from is not None:
        condition["time_from"] = time_from
    if time_to is not None:
        condition["time_to"] = time_to
    payload: dict[str, Any] = {"condition": condition}
    return await _ndr_post("/api/v1/privacy/diagram", payload, "ndr_privacy_diagram")


async def soc_ndr_threat_inbound_attack(time_from: int | None = None, time_to: int | None = None) -> dict[str, Any]:
    condition: dict[str, Any] = {}
    if time_from is not None:
        condition["time_from"] = time_from
    if time_to is not None:
        condition["time_to"] = time_to
    payload: dict[str, Any] = {"condition": condition}
    return await _ndr_post("/api/v1/threat/inbound-attack/severity-distribution", payload, "ndr_threat_inbound_attack")


def create_soc_alert_ndr_tools() -> list[StructuredTool]:
    """Create NDR tools for SOC alert."""
    return [
        StructuredTool.from_function(name="soc_ndr_log_search", description="Query NDR log search / terms aggregation for SOC triage.", func=soc_ndr_log_search, coroutine=soc_ndr_log_search, args_schema=SocNdrLogSearchInput),
        StructuredTool.from_function(name="soc_ndr_mdr_alert_list", description="Query NDR MDR alert list (read-only).", func=soc_ndr_mdr_alert_list, coroutine=soc_ndr_mdr_alert_list, args_schema=SocNdrMdrAlertListInput),
        StructuredTool.from_function(name="soc_ndr_dashboard_status", description="Query NDR dashboard status and threat overview widgets.", func=soc_ndr_dashboard_status, coroutine=soc_ndr_dashboard_status, args_schema=SocNdrDashboardStatusInput),
        StructuredTool.from_function(name="soc_ndr_incident_list", description="Query NDR incident investigation list/details.", func=soc_ndr_incident_list, coroutine=soc_ndr_incident_list, args_schema=SocNdrIncidentListInput),
        StructuredTool.from_function(name="soc_ndr_host_threat_list", description="Query NDR host threat summary/events.", func=soc_ndr_host_threat_list, coroutine=soc_ndr_host_threat_list, args_schema=SocNdrHostThreatListInput),
        StructuredTool.from_function(name="soc_ndr_vulnerability_list", description="Query NDR vulnerability list (read-only).", func=soc_ndr_vulnerability_list, coroutine=soc_ndr_vulnerability_list, args_schema=SocNdrVulnerabilityListInput),
        StructuredTool.from_function(name="soc_ndr_system_status", description="Query NDR system status health checks.", func=soc_ndr_system_status, coroutine=soc_ndr_system_status, args_schema=SocNdrSystemStatusInput),
        StructuredTool.from_function(name="soc_ndr_machine_asset_list", description="Query NDR machine/service asset list.", func=soc_ndr_machine_asset_list, coroutine=soc_ndr_machine_asset_list, args_schema=SocNdrMachineAssetListInput),
        StructuredTool.from_function(name="soc_ndr_assets_domain_list", description="Query NDR domain asset list.", func=soc_ndr_assets_domain_list, coroutine=soc_ndr_assets_domain_list, args_schema=SocNdrAssetsDomainListInput),
        StructuredTool.from_function(name="soc_ndr_interface_risk_list", description="Query NDR API risk list (read-only).", func=soc_ndr_interface_risk_list, coroutine=soc_ndr_interface_risk_list, args_schema=SocNdrInterfaceRiskListInput),
        StructuredTool.from_function(name="soc_ndr_interface_list", description="Query NDR API interface list (read-only).", func=soc_ndr_interface_list, coroutine=soc_ndr_interface_list, args_schema=SocNdrInterfaceListInput),
        StructuredTool.from_function(name="soc_ndr_login_api_list", description="Query NDR login API list and summaries.", func=soc_ndr_login_api_list, coroutine=soc_ndr_login_api_list, args_schema=SocNdrLoginApiListInput),
        StructuredTool.from_function(name="soc_ndr_login_weakpwd_list", description="Query NDR login weak-password list.", func=soc_ndr_login_weakpwd_list, coroutine=soc_ndr_login_weakpwd_list, args_schema=SocNdrLoginWeakpwdListInput),
        StructuredTool.from_function(name="soc_ndr_cloud_facilities", description="Query NDR cloud facilities views.", func=soc_ndr_cloud_facilities, coroutine=soc_ndr_cloud_facilities, args_schema=SocNdrCloudFacilitiesInput),
        StructuredTool.from_function(name="soc_ndr_privacy_diagram", description="Query NDR privacy overview diagram.", func=soc_ndr_privacy_diagram, coroutine=soc_ndr_privacy_diagram, args_schema=SocNdrPrivacyDiagramInput),
        StructuredTool.from_function(name="soc_ndr_threat_inbound_attack", description="Query NDR inbound attack severity distribution.", func=soc_ndr_threat_inbound_attack, coroutine=soc_ndr_threat_inbound_attack, args_schema=SocNdrThreatInboundAttackInput),
    ]
