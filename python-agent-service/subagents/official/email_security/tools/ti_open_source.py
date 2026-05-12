"""Open-source threat intelligence tools (networked, best-effort).

These tools are intended for optional enrich steps under a strict budget.
They must:
- be safe by default (timeouts, size limits),
- never treat unavailability as benign,
- return structured outputs suitable for Evidence conversion.
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass
from typing import Annotated, Any
from urllib.error import HTTPError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

from langchain_core.tools import tool

_DEFAULT_TIMEOUT_S = 10
_MAX_RESPONSE_BYTES = 1_000_000


def _http_post_form(
    url: str,
    form: dict[str, str],
    *,
    timeout_s: int = _DEFAULT_TIMEOUT_S,
    extra_headers: dict[str, str] | None = None,
) -> tuple[int, dict[str, Any] | None, str | None]:
    data = urlencode(form).encode("utf-8")
    headers: dict[str, str] = {"Content-Type": "application/x-www-form-urlencoded"}
    if extra_headers:
        headers.update(extra_headers)

    req = Request(url, data=data, headers=headers)
    try:
        with urlopen(req, timeout=timeout_s) as resp:  # noqa: S310
            status = int(getattr(resp, "status", 200))
            raw = resp.read(_MAX_RESPONSE_BYTES + 1)
        if len(raw) > _MAX_RESPONSE_BYTES:
            return status, None, "response_too_large"
        try:
            return status, json.loads(raw.decode("utf-8", errors="replace")), None
        except json.JSONDecodeError:
            return status, None, "invalid_json"
    except HTTPError as exc:
        status = int(getattr(exc, "code", 0) or 0)
        reason = getattr(exc, "reason", "") or ""
        msg = f"HTTPError {status}: {reason}".strip()
        return status, None, msg or "httperror"
    except Exception as exc:  # noqa: BLE001
        return 0, None, str(exc)


@tool
def lookup_urlhaus(
    url_or_domain: Annotated[str, "URL (preferred) or domain/host to look up in URLhaus."],
    timeout_s: Annotated[int, "HTTP timeout seconds."] = _DEFAULT_TIMEOUT_S,
) -> dict[str, Any]:
    """Look up a URL or host in URLhaus (abuse.ch)."""
    target = (url_or_domain or "").strip()
    if not target:
        return {"ok": False, "analysis_unavailable": True, "detail": "Empty target"}

    if target.startswith(("http://", "https://")):
        endpoint = "https://urlhaus-api.abuse.ch/v1/url/"
        form = {"url": target}
        kind = "url"
    else:
        endpoint = "https://urlhaus-api.abuse.ch/v1/host/"
        form = {"host": target}
        kind = "host"

    status, payload, err = _http_post_form(endpoint, form, timeout_s=int(timeout_s))
    if err or not isinstance(payload, dict):
        return {
            "ok": False,
            "analysis_unavailable": True,
            "detail": f"URLhaus lookup failed: {err or 'no_payload'}",
            "target": target,
            "kind": kind,
            "http_status": status or None,
        }

    qstatus = str(payload.get("query_status") or "").lower()
    malicious = qstatus == "ok"
    return {
        "ok": True,
        "target": target,
        "kind": kind,
        "query_status": qstatus,
        "malicious": bool(malicious),
        "confidence": "high" if malicious else "low",
        "payload": payload,
    }


@tool
def lookup_malwarebazaar(
    sha256: Annotated[str, "SHA256 hash to look up in MalwareBazaar."],
    timeout_s: Annotated[int, "HTTP timeout seconds."] = _DEFAULT_TIMEOUT_S,
) -> dict[str, Any]:
    """Look up a sha256 in MalwareBazaar (abuse.ch)."""
    h = (sha256 or "").strip().lower()
    if len(h) != 64:
        return {"ok": False, "analysis_unavailable": True, "detail": "Invalid sha256"}

    endpoint = "https://mb-api.abuse.ch/api/v1/"
    form: dict[str, str] = {"query": "get_info", "hash": h}
    api_key = os.getenv("ABUSE_API_KEY", "").strip()
    headers = {"Auth-Key": api_key} if api_key else None

    status, payload, err = _http_post_form(
        endpoint, form, timeout_s=int(timeout_s), extra_headers=headers
    )
    if err or not isinstance(payload, dict):
        return {
            "ok": False,
            "analysis_unavailable": True,
            "detail": f"MalwareBazaar lookup failed: {err or 'no_payload'}",
            "sha256": h,
            "http_status": status or None,
        }

    qstatus = str(payload.get("query_status") or "").lower()
    malicious = qstatus == "ok"
    return {
        "ok": True,
        "sha256": h,
        "query_status": qstatus,
        "malicious": bool(malicious),
        "confidence": "high" if malicious else "low",
        "payload": payload,
    }


@tool
def lookup_threatfox(
    ioc: Annotated[str, "IOC (domain, ip, url, hash) to look up in ThreatFox."],
    timeout_s: Annotated[int, "HTTP timeout seconds."] = _DEFAULT_TIMEOUT_S,
) -> dict[str, Any]:
    """Look up an IOC in ThreatFox (abuse.ch)."""
    target = (ioc or "").strip()
    if not target:
        return {"ok": False, "analysis_unavailable": True, "detail": "Empty IOC"}
    endpoint = "https://threatfox-api.abuse.ch/api/v1/"
    form: dict[str, str] = {"query": "search_ioc", "search_term": target}
    api_key = os.getenv("ABUSE_API_KEY", "").strip()
    headers = {"Auth-Key": api_key} if api_key else None
    status, payload, err = _http_post_form(
        endpoint, form, timeout_s=int(timeout_s), extra_headers=headers
    )
    if err or not isinstance(payload, dict):
        return {
            "ok": False,
            "analysis_unavailable": True,
            "detail": f"ThreatFox lookup failed: {err or 'no_payload'}",
            "ioc": target,
            "http_status": status or None,
        }
    qstatus = str(payload.get("query_status") or "").lower()
    malicious = qstatus == "ok"
    return {
        "ok": True,
        "ioc": target,
        "query_status": qstatus,
        "malicious": bool(malicious),
        "confidence": "high" if malicious else "low",
        "payload": payload,
    }


@tool
def lookup_otx(
    ioc: Annotated[
        str,
        "IOC to look up in AlienVault OTX (requires OTX API key if rate-limited).",
    ],
    timeout_s: Annotated[int, "HTTP timeout seconds."] = _DEFAULT_TIMEOUT_S,
) -> dict[str, Any]:
    """Placeholder: OTX lookup is optional and may require an API key."""
    target = (ioc or "").strip()
    if not target:
        return {"ok": False, "analysis_unavailable": True, "detail": "Empty IOC"}
    return {
        "ok": False,
        "analysis_unavailable": True,
        "detail": "OTX lookup not configured in this example (API key/endpoints vary).",
        "ioc": target,
    }

