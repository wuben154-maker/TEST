"""RDAP domain lookup tool (best-effort, networked).

Uses rdap.org as a public RDAP aggregator. RDAP provides structured domain
registration information which is useful for detecting newly registered
typosquat/phishing domains.
"""

from __future__ import annotations

import json
from typing import Annotated, Any
from urllib.parse import quote
from urllib.request import Request, urlopen

from langchain_core.tools import tool

from .policy import normalize_domain

_DEFAULT_TIMEOUT_S = 10
_MAX_RESPONSE_BYTES = 1_000_000


@tool
def rdap_lookup(
    domain: Annotated[str, "Domain to look up via RDAP (registrable domain recommended)."],
    timeout_s: Annotated[int, "HTTP timeout seconds."] = _DEFAULT_TIMEOUT_S,
) -> dict[str, Any]:
    """Look up domain registration details via RDAP."""
    d = normalize_domain(domain)
    if not d or "." not in d:
        return {
            "ok": False,
            "analysis_unavailable": True,
            "detail": "Invalid domain",
            "domain": d,
        }

    url = f"https://rdap.org/domain/{quote(d)}"
    req = Request(url, headers={"Accept": "application/rdap+json, application/json"})
    try:
        with urlopen(req, timeout=int(timeout_s)) as resp:  # noqa: S310
            status = int(getattr(resp, "status", 200))
            raw = resp.read(_MAX_RESPONSE_BYTES + 1)
        if len(raw) > _MAX_RESPONSE_BYTES:
            return {
                "ok": False,
                "analysis_unavailable": True,
                "detail": "response_too_large",
                "domain": d,
                "http_status": status,
            }
        payload = json.loads(raw.decode("utf-8", errors="replace"))
    except Exception as exc:  # noqa: BLE001
        return {
            "ok": False,
            "analysis_unavailable": True,
            "detail": f"RDAP lookup failed: {exc}",
            "domain": d,
        }

    return {"ok": True, "domain": d, "payload": payload}

