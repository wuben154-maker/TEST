"""Lightweight JavaScript/HTML sink scanner for hosted Web code."""

from __future__ import annotations

import re

from .models import Evidence, Finding, Signal

_DOM_SINKS: tuple[tuple[re.Pattern[str], str], ...] = (
    (re.compile(r"\.innerHTML\s*=", re.IGNORECASE), "innerHTML"),
    (re.compile(r"\.outerHTML\s*=", re.IGNORECASE), "outerHTML"),
    (re.compile(r"document\.write\s*\(", re.IGNORECASE), "document.write"),
    (
        re.compile(r"dangerouslySetInnerHTML", re.IGNORECASE),
        "dangerouslySetInnerHTML",
    ),
)

_EXEC_SINKS: tuple[tuple[re.Pattern[str], str], ...] = (
    (re.compile(r"\beval\s*\(", re.IGNORECASE), "eval"),
    (
        re.compile(r"child_process\.(exec|spawn|execFile)\s*\(", re.IGNORECASE),
        "child_process",
    ),
)


def scan_js_html_sinks(content: str) -> tuple[list[Finding], bool, str]:
    """Scan JavaScript/HTML text for common DOM XSS and execution sinks."""
    findings: list[Finding] = []
    for patterns, category, severity, confidence, prefix in (
        (_DOM_SINKS, "xss", "high", 0.78, "js:dom"),
        (_EXEC_SINKS, "rce", "high", 0.82, "js:exec"),
    ):
        for regex, name in patterns:
            for match in regex.finditer(content):
                snippet = content[match.start() : min(match.start() + 220, len(content))]
                findings.append(
                    Finding(
                        id=f"{prefix}-{name}-{match.start()}",
                        category=category,  # type: ignore[arg-type]
                        severity=severity,  # type: ignore[arg-type]
                        confidence=confidence,
                        evidence=Evidence(
                            snippet=snippet,
                            start=match.start(),
                            end=match.end(),
                            location=f"{prefix}:{name}",
                        ),
                        signals=[
                            Signal(type="ast_sink", name=name, weight=0.85)
                        ],
                        layer="L2",
                    )
                )
    lang = (
        "html"
        if re.search(r"<html|<script", content, re.IGNORECASE)
        else "javascript"
    )
    return findings, bool(findings), lang
