"""VirusTotal API tools for SOC alert profile."""

from __future__ import annotations

from base64 import urlsafe_b64encode
from pathlib import Path
from typing import Any

import httpx
from langchain_core.tools import StructuredTool
from pydantic import BaseModel, Field

from ..api_service_config import load_api_service_config


class SocVtFileQueryInput(BaseModel):
    """Input schema for querying VirusTotal file report by hash."""

    file_hash: str = Field(description="MD5/SHA1/SHA256 hash value to query.")


class SocVtIpQueryInput(BaseModel):
    """Input schema for querying VirusTotal IP report."""

    ip: str = Field(description="IP address value.")


class SocVtDomainQueryInput(BaseModel):
    """Input schema for querying VirusTotal domain report."""

    domain: str = Field(description="Domain value.")


class SocVtUrlQueryInput(BaseModel):
    """Input schema for querying VirusTotal URL report."""

    url: str = Field(description="Raw URL string.")


class SocVtUrlScanInput(BaseModel):
    """Input schema for submitting URL to VirusTotal scan."""

    url: str = Field(description="Raw URL string to submit.")


class SocVtFileScanInput(BaseModel):
    """Input schema for submitting local file to VirusTotal scan."""

    file_path: str = Field(description="Absolute or relative local file path.")


class SocVtAnalysisStatusInput(BaseModel):
    """Input schema for querying VirusTotal analysis task status."""

    analysis_id: str = Field(description="VirusTotal analysis id.")


def _simulated_payload(provider: str, detail: dict[str, Any]) -> dict[str, Any]:
    return {"simulated": True, "provider": provider, **detail}


def _vt_url_to_id(url: str) -> str:
    return urlsafe_b64encode(url.encode("utf-8")).decode("utf-8").strip("=")


async def _vt_query(path: str, indicator: str, category: str) -> dict[str, Any]:
    svc = load_api_service_config("virustotal")
    if not svc.enabled or not svc.base_url or not svc.api_key:
        return _simulated_payload(
            "virustotal",
            {
                category: indicator,
                "note": "Missing or disabled virustotal service in .flocks/flocks.json.",
            },
        )
    headers = {"x-apikey": svc.api_key, "Accept": "application/json"}
    url = f"{svc.base_url}{path}"
    async with httpx.AsyncClient(timeout=float(svc.timeout)) as client:
        try:
            resp = await client.get(url, headers=headers)
            if resp.status_code == 404:
                return {category: indicator, "found": False, "provider": "virustotal"}
            resp.raise_for_status()
            data = resp.json()
            return {
                category: indicator,
                "found": True,
                "provider": "virustotal",
                "data": data.get("data"),
            }
        except Exception as exc:
            return {"error": str(exc), "provider": "virustotal", category: indicator}


async def soc_vt_file_query(file_hash: str) -> dict[str, Any]:
    """Query VirusTotal file report by hash."""
    return await _vt_query(f"/files/{file_hash}", file_hash, "file_hash")


async def soc_vt_ip_query(ip: str) -> dict[str, Any]:
    """Query VirusTotal IP report."""
    return await _vt_query(f"/ip_addresses/{ip}", ip, "ip")


async def soc_vt_domain_query(domain: str) -> dict[str, Any]:
    """Query VirusTotal domain report."""
    return await _vt_query(f"/domains/{domain}", domain, "domain")


async def soc_vt_url_query(url: str) -> dict[str, Any]:
    """Query VirusTotal URL report."""
    url_id = _vt_url_to_id(url)
    return await _vt_query(f"/urls/{url_id}", url, "url")


async def soc_vt_url_scan(url: str) -> dict[str, Any]:
    """Submit URL to VirusTotal scan API."""
    svc = load_api_service_config("virustotal")
    if not svc.enabled or not svc.base_url or not svc.api_key:
        return _simulated_payload(
            "virustotal",
            {
                "url": url,
                "note": "Missing or disabled virustotal service in .flocks/flocks.json.",
            },
        )
    headers = {"x-apikey": svc.api_key, "Accept": "application/json"}
    async with httpx.AsyncClient(timeout=float(svc.timeout)) as client:
        try:
            resp = await client.post(f"{svc.base_url}/urls", headers=headers, data={"url": url})
            resp.raise_for_status()
            return {"provider": "virustotal", "url": url, "data": resp.json()}
        except Exception as exc:
            return {"error": str(exc), "provider": "virustotal", "url": url}


async def soc_vt_file_scan(file_path: str) -> dict[str, Any]:
    """Submit local file to VirusTotal file scan API."""
    svc = load_api_service_config("virustotal")
    if not svc.enabled or not svc.base_url or not svc.api_key:
        return _simulated_payload(
            "virustotal",
            {
                "file_path": file_path,
                "note": "Missing or disabled virustotal service in .flocks/flocks.json.",
            },
        )
    path = Path(file_path)
    if not path.is_file():
        return {"provider": "virustotal", "file_path": file_path, "error": "File not found."}
    if path.stat().st_size > 32 * 1024 * 1024:
        return {
            "provider": "virustotal",
            "file_path": file_path,
            "error": "File too large. Maximum 32MB allowed.",
        }
    headers = {"x-apikey": svc.api_key, "Accept": "application/json"}
    async with httpx.AsyncClient(timeout=float(svc.timeout)) as client:
        try:
            with path.open("rb") as file_handle:
                resp = await client.post(
                    f"{svc.base_url}/files",
                    headers=headers,
                    files={"file": (path.name, file_handle)},
                )
            resp.raise_for_status()
            return {"provider": "virustotal", "file_path": str(path), "data": resp.json()}
        except Exception as exc:
            return {"error": str(exc), "provider": "virustotal", "file_path": str(path)}


async def soc_vt_analysis_status(analysis_id: str) -> dict[str, Any]:
    """Query VirusTotal analysis task status."""
    return await _vt_query(f"/analyses/{analysis_id}", analysis_id, "analysis_id")


def create_soc_alert_virustotal_tools() -> list[StructuredTool]:
    """Create VirusTotal tools for SOC alert."""
    return [
        StructuredTool.from_function(
            name="soc_vt_file_query",
            description="Query VirusTotal file hash report for SOC triage evidence.",
            func=soc_vt_file_query,
            coroutine=soc_vt_file_query,
            args_schema=SocVtFileQueryInput,
        ),
        StructuredTool.from_function(
            name="soc_vt_ip_query",
            description="Query VirusTotal IP reputation for SOC triage.",
            func=soc_vt_ip_query,
            coroutine=soc_vt_ip_query,
            args_schema=SocVtIpQueryInput,
        ),
        StructuredTool.from_function(
            name="soc_vt_domain_query",
            description="Query VirusTotal domain reputation for SOC triage.",
            func=soc_vt_domain_query,
            coroutine=soc_vt_domain_query,
            args_schema=SocVtDomainQueryInput,
        ),
        StructuredTool.from_function(
            name="soc_vt_url_query",
            description="Query VirusTotal URL reputation for SOC triage.",
            func=soc_vt_url_query,
            coroutine=soc_vt_url_query,
            args_schema=SocVtUrlQueryInput,
        ),
        StructuredTool.from_function(
            name="soc_vt_url_scan",
            description="Submit URL to VirusTotal for analysis scan.",
            func=soc_vt_url_scan,
            coroutine=soc_vt_url_scan,
            args_schema=SocVtUrlScanInput,
        ),
        StructuredTool.from_function(
            name="soc_vt_file_scan",
            description="Submit local file to VirusTotal for analysis scan.",
            func=soc_vt_file_scan,
            coroutine=soc_vt_file_scan,
            args_schema=SocVtFileScanInput,
        ),
        StructuredTool.from_function(
            name="soc_vt_analysis_status",
            description="Query VirusTotal analysis status by analysis id.",
            func=soc_vt_analysis_status,
            coroutine=soc_vt_analysis_status,
            args_schema=SocVtAnalysisStatusInput,
        ),
    ]
