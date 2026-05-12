"""Deterministic investigation policy (onion-style) for email security."""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Literal
from urllib.parse import urlparse

ActionType = Literal[
    "ti_urlhaus",
    "ti_malwarebazaar",
    "ti_threatfox",
    "ti_otx",
    "rdap_lookup",
    "fetch_url_metadata",
    "render_url_fingerprint",
    "binary_analyzer_second_pass",
]


@dataclass(frozen=True, slots=True)
class Budget:
    tool_calls_left: int
    max_parallel: int = 5


@dataclass(frozen=True, slots=True)
class Action:
    type: ActionType
    tool_name: str
    params: dict[str, Any]
    priority: int
    estimated_cost: int
    reason: str


def _registrable_domain(domain: str) -> str:
    d = (domain or "").lower().strip()
    parts = [p for p in d.split(".") if p]
    if len(parts) >= 2:
        return ".".join(parts[-2:])
    return d


def _domain_from_url(url: str) -> str:
    try:
        return (urlparse(url).hostname or "").lower()
    except Exception:
        return ""


def _tier_for_attachment(filename: str, content_type: str) -> int:
    name = (filename or "").lower()
    ct = (content_type or "").lower()
    suffix = Path(name).suffix.lower()

    tier1 = {".exe", ".dll", ".bat", ".cmd", ".ps1", ".vbs", ".js", ".jar", ".com", ".lnk"}
    tier2 = {".doc", ".docx", ".docm", ".xls", ".xlsx", ".xlsm", ".ppt", ".pptx", ".pptm", ".pdf", ".zip", ".rar", ".7z", ".iso"}
    tier3 = {".jpg", ".jpeg", ".png", ".gif", ".bmp", ".webp", ".txt", ".html", ".htm", ".svg", ".eml"}

    if suffix in tier1:
        return 1
    if suffix in tier2:
        return 2
    if suffix in tier3:
        return 3
    if ct.startswith("image/"):
        return 3
    if "pdf" in ct or "officedocument" in ct or "msword" in ct:
        return 2
    return 2


def prioritize_attachments_for_second_pass(
    attachments: list[dict[str, Any]],
    *,
    budget: Budget,
    already_second_pass: set[str] | None = None,
) -> list[Action]:
    already = already_second_pass or set()
    candidates: list[tuple[int, int, dict[str, Any]]] = []
    for i, att in enumerate(attachments or []):
        file_path = str(att.get("file_path") or "")
        sha256 = str(att.get("sha256") or "")
        if sha256 and sha256 in already:
            continue
        if not file_path:
            continue
        tier = _tier_for_attachment(str(att.get("filename") or ""), str(att.get("content_type") or ""))
        candidates.append((tier, i, att))

    actions: list[Action] = []
    remaining = max(0, budget.tool_calls_left)
    for tier, _, att in sorted(candidates, key=lambda t: (t[0], t[1])):
        if remaining <= 0:
            break
        actions.append(
            Action(
                type="binary_analyzer_second_pass",
                tool_name="scan_attachment_second_pass",
                params={
                    "file_path": att.get("file_path"),
                    "filename": att.get("filename"),
                    "content_type": att.get("content_type"),
                    "tier": tier,
                    "sha256": att.get("sha256"),
                },
                priority=10 + tier,
                estimated_cost=1,
                reason=f"Second-pass scan prioritized by Tier{tier}.",
            )
        )
        remaining -= 1
    return actions


def plan_bec_enrich_actions(
    *,
    header_analysis: dict[str, Any] | None,
    url_analyses: list[dict[str, Any]] | None,
    budget: Budget,
    top_k: int = 3,
    enable_otx: bool = False,
) -> list[Action]:
    header = header_analysis or {}
    urls = url_analyses or []

    suspicious_urls: list[dict[str, Any]] = []
    for u in urls:
        risk = str(u.get("risk_level") or "low")
        indicators = u.get("indicators") or u.get("suspicious_indicators") or []
        ind_str = " ".join([i for i in indicators if isinstance(i, str)])
        if risk in {"high", "medium"}:
            suspicious_urls.append(u)
            continue
        if any(
            k in ind_str
            for k in (
                "url_shortener",
                "mixed_unicode_scripts",
                "confusable_char",
                "possible_typosquat",
                "data_uri_detected",
            )
        ):
            suspicious_urls.append(u)

    def _score(u: dict[str, Any]) -> tuple[int, int]:
        risk = str(u.get("risk_level") or "low")
        r = 0 if risk == "high" else (1 if risk == "medium" else 2)
        inds = u.get("indicators") or u.get("suspicious_indicators") or []
        return (r, -len([i for i in inds if isinstance(i, str)]))

    picked = sorted(suspicious_urls, key=_score)[: max(0, top_k)]
    actions: list[Action] = []
    remaining = max(0, budget.tool_calls_left)

    spoofing = bool(header.get("reply_to_mismatch")) or bool(header.get("display_name_spoofing"))
    sender_domains: list[str] = []
    if spoofing:
        for key in ("from_domain", "return_path_domain"):
            d = str(header.get(key) or "").lower()
            if d and d not in sender_domains:
                sender_domains.append(d)

    domains_to_rdap: list[str] = []
    for u in picked:
        dom = _domain_from_url(str(u.get("url") or ""))
        rd = _registrable_domain(dom)
        if rd:
            domains_to_rdap.append(rd)
    domains_to_rdap.extend([_registrable_domain(d) for d in sender_domains if d])
    seen: set[str] = set()
    domains_to_rdap = [d for d in domains_to_rdap if not (d in seen or seen.add(d))]

    for d in domains_to_rdap[:top_k]:
        if remaining <= 0:
            break
        actions.append(
            Action(
                type="rdap_lookup",
                tool_name="rdap_lookup",
                params={"domain": d},
                priority=1,
                estimated_cost=1,
                reason="Check domain age/registrar (anti-typosquat/newly registered).",
            )
        )
        remaining -= 1

    for u in picked:
        if remaining <= 0:
            break
        url = str(u.get("url") or "")
        if not url:
            continue
        actions.append(
            Action(
                type="ti_urlhaus",
                tool_name="lookup_urlhaus",
                params={"url_or_domain": url},
                priority=2,
                estimated_cost=1,
                reason="Query open-source URL reputation (URLhaus).",
            )
        )
        remaining -= 1

    if enable_otx:
        for d in domains_to_rdap[:top_k]:
            if remaining <= 0:
                break
            actions.append(
                Action(
                    type="ti_otx",
                    tool_name="lookup_otx",
                    params={"ioc": d},
                    priority=3,
                    estimated_cost=1,
                    reason="Optional correlation enrichment (OTX pulses).",
                )
            )
            remaining -= 1
    return actions


def plan_attachment_ti_actions(
    attachments: list[dict[str, Any]],
    *,
    budget: Budget,
    top_k: int = 5,
) -> list[Action]:
    remaining = max(0, budget.tool_calls_left)
    scored: list[tuple[int, int, str, dict[str, Any]]] = []
    for i, att in enumerate(attachments or []):
        sha256 = str(att.get("sha256") or "")
        if not re.fullmatch(r"[a-fA-F0-9]{64}", sha256):
            continue
        tier = _tier_for_attachment(str(att.get("filename") or ""), str(att.get("content_type") or ""))
        scored.append((tier, i, sha256.lower(), att))

    actions: list[Action] = []
    for tier, _, sha256, att in sorted(scored, key=lambda t: (t[0], t[1]))[:top_k]:
        if remaining <= 0:
            break
        actions.append(
            Action(
                type="ti_malwarebazaar",
                tool_name="lookup_malwarebazaar",
                params={"sha256": sha256, "filename": att.get("filename"), "tier": tier},
                priority=5 + tier,
                estimated_cost=1,
                reason=f"Attachment hash reputation lookup (Tier{tier} prioritized).",
            )
        )
        remaining -= 1
    return actions

