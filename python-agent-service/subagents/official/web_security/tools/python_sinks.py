"""Python sink scan (pattern-based dangerous builtins / subprocess)."""

from __future__ import annotations

import re

from .models import Evidence, Finding, Signal

_PY_SINK = re.compile(
    r"\b(eval|exec|__import__|compile)\s*\(",
    re.IGNORECASE,
)

_SUBPROC = re.compile(
    r"\b(subprocess\.(run|call|Popen|check_output)|os\.(system|popen|spawn|execv|execl))\s*\(",
    re.IGNORECASE,
)


def scan_python_sinks(content: str) -> tuple[list[Finding], bool, str]:
    if not content.strip():
        return [], False, ""

    findings: list[Finding] = []

    for m in _PY_SINK.finditer(content):
        name = m.group(1).lower()
        end = min(m.end() + 60, len(content))
        snippet = content[m.start() : end]
        findings.append(
            Finding(
                id=f"python-sink-{name}-{m.start()}",
                category="webshell",
                severity="high",
                confidence=0.9,
                evidence=Evidence(
                    snippet=snippet[:220],
                    start=m.start(),
                    end=m.end(),
                    location=f"python:sink:{name}",
                ),
                signals=[Signal(type="ast_sink", name=name, weight=1.0)],
            )
        )

    for m in _SUBPROC.finditer(content):
        raw = m.group(0).split("(")[0].lower().replace(".", "_")
        end = min(m.end() + 60, len(content))
        snippet = content[m.start() : end]
        findings.append(
            Finding(
                id=f"python-sink-{raw}-{m.start()}",
                category="rce",
                severity="high",
                confidence=0.85,
                evidence=Evidence(
                    snippet=snippet[:220],
                    start=m.start(),
                    end=m.end(),
                    location=f"python:sink:{raw}",
                ),
                signals=[Signal(type="ast_sink", name=raw, weight=1.0)],
            )
        )

    # Primary language was inferred as Python; keep label even if no sink match.
    ast_ok = bool(findings)
    return findings, ast_ok, "python"
