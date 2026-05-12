"""Per-parameter XSS/SQLi/SSRF feature extraction for parsed HTTP requests."""

from __future__ import annotations

from .extractors.sqli_patterns import detect_sqli
from .extractors.xss_patterns import detect_xss
from .http_parse import (
    ParsedHttpRequest,
    infer_param_context,
    iter_body_params,
    iter_cookies,
    iter_query_params,
)
from .models import Evidence, Finding, Severity, Signal


def _sev_map(s: str) -> Severity:
    m: dict[str, Severity] = {
        "critical": "critical",
        "high": "high",
        "medium": "medium",
        "low": "low",
        "none": "info",
    }
    return m.get(s, "medium")


def _ssrf_param(value: str, location: str) -> Finding | None:
    lowered = value.lower()
    if "169.254.169.254" in value or "metadata.google.internal" in lowered:
        return Finding(
            id=f"ssrf-{hash(location) & 0xFFFF:x}",
            category="ssrf",
            severity="high",
            confidence=0.8,
            evidence=Evidence(
                snippet=value[:200],
                start=0,
                end=min(80, len(value)),
                location=location,
            ),
            signals=[
                Signal(
                    type="param_context",
                    name="cloud_metadata_endpoint",
                    weight=0.85,
                ),
            ],
        )
    return None


def analyze_traffic_params(parsed: ParsedHttpRequest) -> list[Finding]:
    """Run extractors on each decoded parameter value (not the whole request)."""
    findings: list[Finding] = []
    if not parsed.ok:
        return findings

    pairs: list[tuple[str, str, str]] = []
    for name, value in iter_query_params(parsed.query_string):
        pairs.append((name, value, f"{parsed.query_location_prefix}:{name}"))
    ct = parsed.headers.get("content-type", "")
    for name, value in iter_body_params(parsed.body, ct):
        prefix = "body.json" if "application/json" in ct.lower() else "body"
        pairs.append((name, value, f"{prefix}:{name}"))
    for name, value in parsed.headers.items():
        if name in {"cookie", "host", "content-type", "content-length"}:
            continue
        pairs.append((name, value, f"header:{name}"))
    for name, value in iter_cookies(parsed.headers.get("cookie", "")):
        pairs.append((name, value, f"cookie:{name}"))

    for name, value, loc in pairs:
        ctx = infer_param_context(name, value)
        ctx_sig = Signal(type="param_context", name=f"ctx:{ctx}", weight=0.75)

        sq = detect_sqli(value)
        if sq.get("is_sqli"):
            sev = _sev_map(str(sq.get("severity", "medium")))
            findings.append(
                Finding(
                    id=f"sqli-{name}-{loc}",
                    category="sqli",
                    severity=sev,
                    confidence=0.82,
                    evidence=Evidence(
                        snippet=value[:220],
                        start=0,
                        end=min(len(value), 120),
                        location=loc,
                    ),
                    signals=[
                        ctx_sig,
                        Signal(
                            type="pattern",
                            name="sqli_signature",
                            weight=0.8,
                        ),
                    ],
                )
            )

        xs = detect_xss(value)
        if xs.get("is_xss"):
            sev = _sev_map(str(xs.get("severity", "medium")))
            findings.append(
                Finding(
                    id=f"xss-{name}-{loc}",
                    category="xss",
                    severity=sev,
                    confidence=0.8,
                    evidence=Evidence(
                        snippet=value[:220],
                        start=0,
                        end=min(len(value), 120),
                        location=loc,
                    ),
                    signals=[
                        ctx_sig,
                        Signal(
                            type="pattern",
                            name="xss_signature",
                            weight=0.78,
                        ),
                    ],
                )
            )

        ssrf_f = _ssrf_param(value, loc)
        if ssrf_f is not None:
            findings.append(ssrf_f)

    return findings
