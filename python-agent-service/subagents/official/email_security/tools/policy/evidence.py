"""Evidence model and export helpers for the email security agent."""

from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Iterable, Literal
from urllib.parse import urlparse

ArtifactType = Literal["url", "domain", "ip", "hash", "email", "file"]
Severity = Literal["CRITICAL", "HIGH", "MEDIUM", "LOW", "INFO"]
Confidence = Literal["high", "medium", "low"]

TechnicalProofComponent = Literal["AUTH", "URL", "ATTACHMENT", "BODY"]
TechnicalProofStatus = Literal["FAIL", "ANOMALY", "WARNING", "INFO"]


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def normalize_domain(domain: str) -> str:
    d = (domain or "").strip().lower()
    if ":" in d:
        d = d.split(":", 1)[0]
    return d


def normalize_sha256(value: str) -> str:
    v = (value or "").strip().lower()
    return v if re.fullmatch(r"[a-f0-9]{64}", v) else ""


def normalize_url(url: str) -> str:
    u = (url or "").strip()
    if not u:
        return ""
    try:
        parsed = urlparse(u)
    except Exception:
        return u
    scheme = (parsed.scheme or "").lower()
    netloc = (parsed.netloc or "").lower()
    if scheme and netloc:
        rest = parsed._replace(scheme=scheme, netloc=netloc)
        return rest.geturl()
    return u


def domain_from_url(url: str) -> str:
    try:
        return normalize_domain(urlparse(url).hostname or "")
    except Exception:
        return ""


@dataclass(frozen=True, slots=True)
class Artifact:
    type: ArtifactType
    value: str
    context: dict[str, Any] = field(default_factory=dict)

    def normalized_value(self) -> str:
        if self.type == "domain":
            return normalize_domain(self.value)
        if self.type == "url":
            return normalize_url(self.value)
        if self.type == "hash":
            return normalize_sha256(self.value)
        return (self.value or "").strip()

    def dedupe_key(self) -> tuple[str, str]:
        return (self.type, self.normalized_value())


@dataclass(frozen=True, slots=True)
class EvidenceItem:
    signal: str
    severity: Severity
    confidence: Confidence
    artifact: Artifact | None
    source: str
    detail: str
    details: dict[str, Any] = field(default_factory=dict)
    limitations: list[str] = field(default_factory=list)
    timestamp: str = field(default_factory=_utc_now_iso)

    def stable_id(self) -> str:
        blob = {
            "signal": self.signal,
            "severity": self.severity,
            "confidence": self.confidence,
            "artifact": self.artifact.dedupe_key() if self.artifact else None,
            "source": self.source,
            "detail": self.detail,
            "details": self.details,
            "limitations": self.limitations,
        }
        raw = json.dumps(blob, sort_keys=True, ensure_ascii=False).encode("utf-8")
        return hashlib.sha256(raw).hexdigest()[:16]


@dataclass(slots=True)
class EvidenceStore:
    _items_by_id: dict[str, EvidenceItem] = field(default_factory=dict)
    _artifacts: dict[tuple[str, str], Artifact] = field(default_factory=dict)

    def add(self, item: EvidenceItem) -> str:
        eid = item.stable_id()
        if eid not in self._items_by_id:
            self._items_by_id[eid] = item
            if item.artifact is not None:
                key = item.artifact.dedupe_key()
                if key[1]:
                    self._artifacts[key] = Artifact(
                        type=item.artifact.type,
                        value=item.artifact.normalized_value(),
                        context=item.artifact.context,
                    )
        return eid

    def extend(self, items: Iterable[EvidenceItem]) -> None:
        for item in items:
            self.add(item)

    def items(self) -> list[EvidenceItem]:
        return list(self._items_by_id.values())

    def artifacts(self) -> list[Artifact]:
        return list(self._artifacts.values())

    def export_iocs(self) -> list[dict[str, Any]]:
        out: list[dict[str, Any]] = []
        for art in sorted(self._artifacts.values(), key=lambda a: (a.type, a.value)):
            out.append({"type": art.type, "value": art.value, "context": art.context or {}})
        return out

    def export_technical_proofs(self) -> list[dict[str, Any]]:
        proofs: list[dict[str, Any]] = []
        for item in self.items():
            comp = _component_for_signal(item.signal)
            if comp is None:
                continue
            status = _status_for_evidence(item)
            proofs.append({"component": comp, "status": status, "detail": item.detail})
        return sorted(proofs, key=lambda p: (p["component"], p["status"], p["detail"]))

    def export_findings_for_scoring(
        self,
        *,
        header_analysis: dict[str, Any] | None = None,
        url_counts: dict[str, int] | None = None,
        attachment_risks: list[str] | None = None,
        social_engineering_score: int | None = None,
        prompt_injection_detected: bool | None = None,
        display_name_spoofing: bool | None = None,
        reply_to_mismatch: bool | None = None,
        mass_mailing_penalty: int | None = None,
    ) -> dict[str, Any]:
        auth = header_analysis or {}
        counts = url_counts or {}
        return {
            "auth": {"spf": auth.get("spf"), "dkim": auth.get("dkim"), "dmarc": auth.get("dmarc")},
            "url_high_risk_count": int(counts.get("high", 0)),
            "url_medium_risk_count": int(counts.get("medium", 0)),
            "attachment_risks": attachment_risks or [],
            "social_engineering_score": int(social_engineering_score or 0),
            "prompt_injection_detected": bool(prompt_injection_detected or False),
            "display_name_spoofing": bool(display_name_spoofing or False),
            "reply_to_mismatch": bool(reply_to_mismatch or False),
            "mass_mailing_penalty": int(mass_mailing_penalty or 0),
        }


def _component_for_signal(signal: str) -> TechnicalProofComponent | None:
    s = (signal or "").lower()
    if s.startswith(("auth_", "spf_", "dkim_", "dmarc_")):
        return "AUTH"
    if s.startswith(("url_", "idn_", "href_", "redirect_", "ti_url_", "ti_domain_")):
        return "URL"
    if s.startswith(("att_", "attachment_", "ti_hash_", "hash_")):
        return "ATTACHMENT"
    if s.startswith(("body_", "prompt_injection_", "social_engineering_")):
        return "BODY"
    return None


def _status_for_evidence(item: EvidenceItem) -> TechnicalProofStatus:
    sev = item.severity
    if sev == "CRITICAL":
        return "FAIL"
    if sev in ("HIGH", "MEDIUM"):
        return "ANOMALY"
    if item.limitations:
        return "WARNING"
    return "INFO"

