"""Phase 2 tools: email header analysis.

All parsing logic is self-contained — no external PhishGuard dependency.
"""

from __future__ import annotations

import re
from datetime import datetime
from email.parser import HeaderParser
from email.utils import getaddresses, parsedate_to_datetime
from typing import Any

from langchain_core.tools import tool

from ._helpers import _BRAND_KEYWORDS, _decode_header_value, logger
from .policy import domain_from_url, normalize_domain  # noqa: PLC0415

_RECEIVED_TIME_DELTA_THRESHOLD_MINUTES = 10


def _extract_domain(header_value: str) -> str:
    """Extract domain from From or Return-Path using ``email.utils.getaddresses``."""
    if not header_value:
        return ""
    addrs = getaddresses([header_value])
    if not addrs:
        return ""
    _, addr = addrs[0]
    if not addr or "@" not in addr:
        return ""
    return addr.split("@")[-1].strip().lower()


def _extract_sender_info(from_header: str) -> dict[str, str]:
    """Extract display name and email from From header."""
    if not from_header:
        return {"display_name": "", "email": ""}
    addrs = getaddresses([from_header])
    if not addrs:
        return {"display_name": "", "email": from_header}
    display_name, email = addrs[0]
    return {
        "display_name": (display_name or "").strip(),
        "email": (email or "").strip(),
    }


def _add_received_proofs(result: dict[str, Any]) -> None:
    """Append Received-related technical_proofs (time delta >10 min, private IP)."""
    received_list = result.get("received") or []
    ip_pattern = re.compile(r"\[(\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3})\]")
    private_pattern = re.compile(r"^(10\.|172\.(1[6-9]|2\d|3[01])\.|192\.168\.)")
    threshold_min = _RECEIVED_TIME_DELTA_THRESHOLD_MINUTES

    for raw in received_list:
        ips = ip_pattern.findall(raw)
        for ip in ips:
            if private_pattern.match(ip):
                result.setdefault("technical_proofs", []).append(
                    {
                        "component": "RECEIVED",
                        "status": "ANOMALY",
                        "detail": f"Private IP in Received: {ip}",
                    }
                )
                break

    dates: list[datetime] = []
    for raw in received_list:
        parts = raw.split(";", 1)
        date_part = parts[-1].strip() if len(parts) > 1 else raw
        try:
            dt = parsedate_to_datetime(date_part)
            dates.append(dt)
        except (TypeError, ValueError):
            pass
    if len(dates) >= 2:
        for i in range(1, len(dates)):
            delta = abs((dates[i] - dates[i - 1]).total_seconds()) / 60
            if delta > threshold_min:
                result.setdefault("technical_proofs", []).append(
                    {
                        "component": "RECEIVED",
                        "status": "ANOMALY",
                        "detail": (
                            f"Received time delta {delta:.0f} min > "
                            f"{threshold_min} min threshold."
                        ),
                    }
                )


def _parse_email_headers_impl(
    raw_headers: str,
    trusted_authserv_domains: list[str] | None = None,
) -> dict[str, Any]:
    """Parse raw email headers (Phase 2 rules: top-most Auth, authserv-id, Received)."""
    parser = HeaderParser()
    msg = parser.parsestr(raw_headers)
    trusted = trusted_authserv_domains or []

    result: dict[str, Any] = {
        "from": _decode_header_value(msg.get("From", "")),
        "to": _decode_header_value(msg.get("To", "")),
        "subject": _decode_header_value(msg.get("Subject", "")),
        "date": msg.get("Date", ""),
        "message_id": msg.get("Message-ID", ""),
        "reply_to": msg.get("Reply-To", ""),
        "return_path": _decode_header_value(msg.get("Return-Path", "")),
        "received": list(msg.get_all("Received") or []),
        "authentication": {
            "spf": None,
            "dkim": None,
            "dmarc": None,
            "authserv_id": None,
            "trusted": None,
        },
        "domains": {"from_domain": "", "return_path_domain": ""},
        "technical_proofs": [],
        "gateway": {"scl": None, "scl_source": None},
    }

    auth_headers = msg.get_all("Authentication-Results") or []
    auth_raw = auth_headers[-1] if auth_headers else ""

    if auth_raw:
        parts = [p.strip() for p in auth_raw.split(";", 1)]
        authserv_id = (parts[0] or "").strip().lower()
        rest = (parts[1] or "") if len(parts) > 1 else ""

        result["authentication"]["authserv_id"] = authserv_id

        if trusted:
            domain_trusted = any(
                authserv_id == d or authserv_id.endswith("." + d) for d in trusted
            )
        else:
            domain_trusted = True
        result["authentication"]["trusted"] = domain_trusted

        if domain_trusted:
            for pattern, key in [
                (r"spf=(\w+)", "spf"),
                (r"dkim=(\w+)", "dkim"),
                (r"dmarc=(\w+)", "dmarc"),
            ]:
                m = re.search(pattern, rest, re.IGNORECASE)
                if m:
                    result["authentication"][key] = m.group(1).lower()
            auth = result["authentication"]
            if auth.get("spf") in ("fail", "softfail"):
                result["technical_proofs"].append(
                    {
                        "component": "AUTH",
                        "status": "FAIL",
                        "detail": (
                            f"SPF {auth.get('spf', 'unknown')}: sender IP not in "
                            "allowed list."
                        ),
                    }
                )
            if auth.get("dkim") == "fail":
                result["technical_proofs"].append(
                    {
                        "component": "AUTH",
                        "status": "FAIL",
                        "detail": "DKIM signature verification failed.",
                    }
                )
            if auth.get("dmarc") == "fail":
                result["technical_proofs"].append(
                    {
                        "component": "AUTH",
                        "status": "FAIL",
                        "detail": "DMARC policy check failed.",
                    }
                )
        else:
            result["technical_proofs"].append(
                {
                    "component": "AUTH",
                    "status": "UNTRUSTED",
                    "detail": (
                        "Authentication-Results from non-trusted authserv-id "
                        f"'{authserv_id}'; not used."
                    ),
                }
            )

    scl_headers = msg.get_all("X-Forefront-Antispam-Report") or []
    scl_value: int | None = None
    if scl_headers:
        raw_scl = scl_headers[-1]
        match = re.search(r"SCL:\s*(-?\d+)", raw_scl, re.IGNORECASE)
        if match:
            try:
                scl_int = int(match.group(1))
            except ValueError:
                scl_int = None
            else:
                if -1 <= scl_int <= 9:
                    scl_value = scl_int

    if scl_value is not None:
        result["gateway"]["scl"] = scl_value
        result["gateway"]["scl_source"] = "X-Forefront-Antispam-Report"
        status = "INFO"
        if scl_value >= 5:
            status = "WARNING"
        result["technical_proofs"].append(
            {
                "component": "AUTH",
                "status": status,
                "detail": (
                    "Exchange Online Protection "
                    f"SCL={scl_value} from X-Forefront-Antispam-Report."
                ),
            }
        )

    from_val = result["from"] or ""
    rp_val = result["return_path"] or ""
    result["domains"]["from_domain"] = _extract_domain(from_val)
    result["domains"]["return_path_domain"] = _extract_domain(rp_val)

    _add_received_proofs(result)
    return result


@tool
def analyze_email_headers(raw_headers: str) -> dict[str, Any]:
    """Analyze raw email headers for auth results, anomalies, and domain mismatches."""
    raw_result = _parse_email_headers_impl(raw_headers, trusted_authserv_domains=None)
    auth = raw_result.get("authentication", {})
    domains = raw_result.get("domains", {})
    gateway = raw_result.get("gateway", {})

    result: dict[str, Any] = {
        "spf": auth.get("spf"),
        "dkim": auth.get("dkim"),
        "dmarc": auth.get("dmarc"),
        "from_domain": domains.get("from_domain", ""),
        "return_path_domain": domains.get("return_path_domain", ""),
        "display_name_spoofing": False,
        "reply_to_mismatch": False,
        "scl": gateway.get("scl"),
        "scl_source": gateway.get("scl_source"),
        "technical_proofs": list(raw_result.get("technical_proofs", [])),
    }

    reply_to = raw_result.get("reply_to", "")
    if reply_to:
        from_email = _extract_sender_info(raw_result.get("from", "") or "")["email"]
        reply_email = _extract_sender_info(reply_to)["email"]
        if from_email and reply_email:
            from_domain = from_email.split("@")[-1] if "@" in from_email else ""
            reply_domain = reply_email.split("@")[-1] if "@" in reply_email else ""
            if from_domain and reply_domain and from_domain != reply_domain:
                result["reply_to_mismatch"] = True
                result["technical_proofs"].append(
                    {
                        "component": "HEADER",
                        "status": "ANOMALY",
                        "detail": (
                            f"Reply-To domain ({reply_domain}) differs from "
                            f"From domain ({from_domain})"
                        ),
                    }
                )

    from_header = raw_result.get("from", "")
    spoofed, proofs = _check_display_name_spoofing(from_header)
    if spoofed:
        result["display_name_spoofing"] = True
    result["technical_proofs"].extend(proofs)

    evidence: list[dict[str, Any]] = []
    from_domain = normalize_domain(result.get("from_domain") or "")
    rp_domain = normalize_domain(result.get("return_path_domain") or "")
    if from_domain:
        evidence.append(
            {
                "signal": "auth_from_domain_observed",
                "severity": "INFO",
                "confidence": "high",
                "artifact": {
                    "type": "domain",
                    "value": from_domain,
                    "context": {"source": "From"},
                },
                "source": "analyze_email_headers",
                "detail": f"From domain observed: {from_domain}",
            }
        )
    if rp_domain:
        evidence.append(
            {
                "signal": "auth_return_path_domain_observed",
                "severity": "INFO",
                "confidence": "high",
                "artifact": {
                    "type": "domain",
                    "value": rp_domain,
                    "context": {"source": "Return-Path"},
                },
                "source": "analyze_email_headers",
                "detail": f"Return-Path domain observed: {rp_domain}",
            }
        )

    for key in ("spf", "dkim", "dmarc"):
        val = result.get(key)
        if isinstance(val, str) and val.lower() in {"fail", "softfail"}:
            evidence.append(
                {
                    "signal": f"auth_{key}_{val.lower()}",
                    "severity": "HIGH" if val.lower() == "fail" else "MEDIUM",
                    "confidence": "high",
                    "artifact": {
                        "type": "domain",
                        "value": from_domain or rp_domain or "",
                        "context": {"auth": key},
                    },
                    "source": "analyze_email_headers",
                    "detail": f"{key.upper()} {val.lower()} reported in Authentication-Results.",
                }
            )

    if result.get("reply_to_mismatch"):
        evidence.append(
            {
                "signal": "auth_reply_to_mismatch",
                "severity": "MEDIUM",
                "confidence": "high",
                "artifact": {
                    "type": "domain",
                    "value": from_domain or "",
                    "context": {"kind": "reply_to_mismatch"},
                },
                "source": "analyze_email_headers",
                "detail": "Reply-To domain differs from From domain.",
            }
        )
    if result.get("display_name_spoofing"):
        evidence.append(
            {
                "signal": "auth_display_name_spoofing",
                "severity": "MEDIUM",
                "confidence": "medium",
                "artifact": {
                    "type": "domain",
                    "value": from_domain or "",
                    "context": {"kind": "display_name"},
                },
                "source": "analyze_email_headers",
                "detail": "Display name suggests a different brand/domain than sender domain.",
            }
        )

    scl = result.get("scl")
    if isinstance(scl, int) and scl >= 5:
        evidence.append(
            {
                "signal": "auth_gateway_scl_high",
                "severity": "LOW",
                "confidence": "high",
                "artifact": {"type": "domain", "value": from_domain or "", "context": {"scl": scl}},
                "source": "analyze_email_headers",
                "detail": f"Gateway SCL indicates spam likelihood (SCL={scl}).",
            }
        )
    result["evidence"] = evidence

    logger.debug(
        "Header analysis: spf=%s dkim=%s dmarc=%s spoofing=%s reply_mismatch=%s",
        result["spf"],
        result["dkim"],
        result["dmarc"],
        result["display_name_spoofing"],
        result["reply_to_mismatch"],
    )
    return result


def _check_display_name_spoofing(from_header: str) -> tuple[bool, list[dict[str, Any]]]:
    """Detect display name that mimics a different domain or brand."""
    proofs: list[dict[str, Any]] = []
    if not from_header:
        return False, proofs

    addr_match = re.search(r"<([^>]+)>", from_header)
    email_addr = addr_match.group(1) if addr_match else from_header
    if "@" not in email_addr:
        return False, proofs

    actual_domain = email_addr.split("@")[-1].lower()
    display = (
        from_header.split("<")[0].strip().strip('"').lower()
        if "<" in from_header
        else ""
    )

    spoofed = False

    email_in_display = re.search(r"[\w.+-]+@([\w.-]+\.\w+)", display)
    if email_in_display:
        spoofed_domain = email_in_display.group(1)
        if spoofed_domain != actual_domain:
            spoofed = True
            proofs.append(
                {
                    "component": "HEADER",
                    "status": "ANOMALY",
                    "detail": (
                        f"Display name contains email from '{spoofed_domain}' "
                        f"but actual sender is '{actual_domain}'."
                    ),
                }
            )

    for brand in _BRAND_KEYWORDS:
        if brand in display and brand not in actual_domain:
            spoofed = True
            proofs.append(
                {
                    "component": "HEADER",
                    "status": "WARNING",
                    "detail": (
                        f"Display name contains brand '{brand}' but sender domain "
                        f"is '{actual_domain}'."
                    ),
                }
            )
            break

    return spoofed, proofs

