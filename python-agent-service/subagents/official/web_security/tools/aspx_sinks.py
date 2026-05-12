"""ASPX / C# server-side sink scan (pattern-based)."""

from __future__ import annotations

import re

from .code_language import _looks_aspx
from .models import Evidence, Finding, Signal

_ASPX_SINK = re.compile(
    r"\b("
    r"Process\.Start|"
    r"System\.Diagnostics\.Process|"
    r"Assembly\.Load|"
    r"Activator\.CreateInstance|"
    r"HttpContext\.Current\.Server\.Execute"
    r")\s*\(",
    re.IGNORECASE,
)


def scan_aspx_sinks(content: str) -> tuple[list[Finding], bool, str]:
    if not content.strip():
        return [], False, ""

    if not (_looks_aspx(content) or "<%" in content):
        return [], False, "unknown"

    findings: list[Finding] = []
    for m in _ASPX_SINK.finditer(content):
        raw = m.group(1).replace(".", "_").lower()
        end = min(m.end() + 80, len(content))
        snippet = content[m.start() : end]
        findings.append(
            Finding(
                id=f"aspx-sink-{raw}-{m.start()}",
                category="rce",
                severity="high",
                confidence=0.87,
                evidence=Evidence(
                    snippet=snippet[:220],
                    start=m.start(),
                    end=m.end(),
                    location=f"aspx:sink:{raw}",
                ),
                signals=[Signal(type="ast_sink", name=raw, weight=1.0)],
            )
        )

    ast_ok = bool(findings)
    return findings, ast_ok, "aspx"
