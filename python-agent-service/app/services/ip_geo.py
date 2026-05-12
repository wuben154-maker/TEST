"""Resolve public client IPs to a country/region label for login audit rows."""

from __future__ import annotations

import ipaddress
from typing import Optional

import httpx
import structlog
from app.config import get_settings

logger = structlog.get_logger()

# ip-api.com free HTTP API (non-commercial; rate-limited).
# Docs: https://ip-api.com/docs
_IP_API_FIELDS = "status,message,country,countryCode"


async def resolve_ip_country_label(ip: Optional[str]) -> Optional[str]:
    """Country label for login audit: e.g. ``China (CN)``, or ``Local`` for private IPs.

    Returns None if lookup is off, IP is invalid, or the external service fails.
    """
    if not ip or not (ip := ip.strip()):
        return None
    try:
        addr = ipaddress.ip_address(ip)
    except ValueError:
        return None
    if (
        addr.is_private
        or addr.is_loopback
        or addr.is_link_local
        or addr.is_reserved
        or addr.is_multicast
    ):
        return "Local"

    settings = get_settings()
    if not settings.login_ip_geo_lookup_enabled:
        return None

    url = f"http://ip-api.com/json/{ip}?fields={_IP_API_FIELDS}"
    try:
        timeout = settings.login_ip_geo_timeout_seconds
        async with httpx.AsyncClient(timeout=timeout) as client:
            response = await client.get(url)
            response.raise_for_status()
            data = response.json()
    except Exception as e:
        logger.warning("ip_geo_lookup_failed", ip=ip, error=str(e))
        return None

    if data.get("status") != "success":
        return None
    country = (data.get("country") or "").strip()
    code = (data.get("countryCode") or "").strip()
    if country and code:
        return f"{country} ({code})"
    if country:
        return country
    if code:
        return code
    return None
