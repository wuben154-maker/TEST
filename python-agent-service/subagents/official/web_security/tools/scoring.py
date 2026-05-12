"""Severity gates and legacy flat-field builder."""

from __future__ import annotations

from .constants import PATTERN_CORROBORATION_WEIGHT
from .models import Finding, LegacyReport, Severity


_SEVERITY_ORDER: dict[str, int] = {
    "critical": 4,
    "high": 3,
    "medium": 2,
    "low": 1,
    "info": 0,
}


def _max_severity(a: Severity, b: Severity) -> Severity:
    return a if _SEVERITY_ORDER[a] >= _SEVERITY_ORDER[b] else b


def cap_high_critical(findings: list[Finding]) -> list[Finding]:
    """
    Enforce design rule: high/critical needs ast_sink, param_context,
    or multiple strong pattern signals (not a lone full-blob regex).
    """
    out: list[Finding] = []
    for f in findings:
        nf = f.model_copy(deep=True)
        if nf.severity not in ("high", "critical"):
            out.append(nf)
            continue

        sigs = nf.signals
        has_struct = any(
            s.type in ("ast_sink", "param_context", "yara_rule", "sandbox_trace") for s in sigs
        )
        if has_struct:
            out.append(nf)
            continue

        pattern_sigs = [s for s in sigs if s.type == "pattern"]
        pattern_weight = sum(s.weight for s in pattern_sigs)
        full_blob = nf.evidence.location.startswith("full_blob")

        if len(pattern_sigs) >= 2 and pattern_weight >= PATTERN_CORROBORATION_WEIGHT:
            out.append(nf)
            continue

        if full_blob or len(pattern_sigs) < 2:
            if nf.severity == "critical":
                nf.severity = "medium"
            else:
                nf.severity = "medium"
        out.append(nf)
    return out


def build_legacy(findings: list[Finding]) -> LegacyReport:
    """Map structured findings to v1-style flat fields."""
    attacks: list[str] = []
    max_sev: Severity = "info"
    for f in findings:
        if f.category == "sqli":
            attacks.append(f"SQL Injection — {f.evidence.location}")
        elif f.category == "xss":
            attacks.append(f"XSS — {f.evidence.location}")
        elif f.category == "ssrf":
            attacks.append(f"SSRF — {f.evidence.location}")
        elif f.category == "webshell":
            attacks.append(f"Webshell / sink — {f.evidence.location}")
        elif f.category == "rce":
            attacks.append(f"RCE — {f.evidence.location}")
        elif f.category == "traversal":
            attacks.append(f"Path Traversal — {f.evidence.location}")
        else:
            attacks.append(f"{f.category} — {f.id}")
        max_sev = _max_severity(max_sev, f.severity)

    immediate = max_sev in ("critical", "high")
    return LegacyReport(
        attacks_detected=attacks,
        severity=max_sev if findings else "info",
        attack_count=len(findings),
        requires_immediate_action=immediate,
    )


def add_risk_scores(findings: list[Finding]) -> list[Finding]:
    """Attach deterministic 0-100 risk scores to findings."""
    out: list[Finding] = []
    for f in findings:
        base = {
            "critical": 90,
            "high": 75,
            "medium": 50,
            "low": 25,
            "info": 5,
        }.get(f.severity, 5)
        signal_bonus = min(10, int(sum(s.weight for s in f.signals) * 5))
        confidence_adj = int((f.confidence - 0.5) * 20)
        score = max(0, min(100, base + signal_bonus + confidence_adj))
        out.append(f.model_copy(update={"risk_score": score}))
    return out
