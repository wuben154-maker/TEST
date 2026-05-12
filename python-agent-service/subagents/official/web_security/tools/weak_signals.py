"""Full-blob pattern signals (Log4j, traversal) — capped without corroboration."""

from __future__ import annotations

import re

from .models import Evidence, Finding, Signal

_JNDI = re.compile(r"\$\{\s*jndi\s*:", re.IGNORECASE)
_TRAVERSAL = re.compile(r"\.\./|\.\.\\")
_UNION = re.compile(r"union\s+(all\s+)?select", re.IGNORECASE)
_SCRIPT = re.compile(r"<script[^>]*>", re.IGNORECASE)


def weak_signals_full_blob(text: str) -> list[Finding]:
    """Low-cost patterns on entire input; always `pattern` signals (full_blob location)."""
    findings: list[Finding] = []
    if _JNDI.search(text):
        m = _JNDI.search(text)
        assert m is not None
        findings.append(
            Finding(
                id="weak-jndi-pattern",
                category="rce",
                severity="medium",
                confidence=0.65,
                evidence=Evidence(
                    snippet=text[m.start() : min(m.start() + 80, len(text))],
                    start=m.start(),
                    end=m.end(),
                    location="full_blob:jndi",
                ),
                signals=[Signal(type="pattern", name="log4shell_jndi", weight=0.7)],
            )
        )
    if _TRAVERSAL.search(text):
        m = _TRAVERSAL.search(text)
        assert m is not None
        findings.append(
            Finding(
                id="weak-path-traversal",
                category="traversal",
                severity="medium",
                confidence=0.55,
                evidence=Evidence(
                    snippet=text[m.start() : min(m.start() + 40, len(text))],
                    start=m.start(),
                    end=m.end(),
                    location="full_blob:path",
                ),
                signals=[Signal(type="pattern", name="path_traversal", weight=0.55)],
            )
        )
    return findings


def fallback_content_signals(text: str) -> list[Finding]:
    """When HTTP parse fails, still surface obvious probes at medium severity (pattern-only)."""
    findings: list[Finding] = []
    m = _UNION.search(text)
    if m:
        findings.append(
            Finding(
                id="fallback-sqli-union",
                category="sqli",
                severity="medium",
                confidence=0.5,
                evidence=Evidence(
                    snippet=text[m.start() : min(m.start() + 60, len(text))],
                    start=m.start(),
                    end=m.end(),
                    location="full_blob:sqli_probe",
                ),
                signals=[Signal(type="pattern", name="union_select_probe", weight=0.5)],
            )
        )
    m = _SCRIPT.search(text)
    if m:
        findings.append(
            Finding(
                id="fallback-xss-script",
                category="xss",
                severity="medium",
                confidence=0.5,
                evidence=Evidence(
                    snippet=text[m.start() : min(m.start() + 60, len(text))],
                    start=m.start(),
                    end=m.end(),
                    location="full_blob:xss_probe",
                ),
                signals=[Signal(type="pattern", name="script_tag_probe", weight=0.5)],
            )
        )
    return findings
