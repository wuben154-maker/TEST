"""JSP / Java server-page sink scan (pattern-based, high-signal calls)."""

from __future__ import annotations

import re

from .models import Evidence, Finding, Signal

# Java runtime / process / script sinks in JSP/scriptlet context
_JSP_RULES: tuple[tuple[re.Pattern[str], str], ...] = (
    (re.compile(r"Runtime\.getRuntime\s*\(\s*\)\s*\.exec\s*\(", re.IGNORECASE), "runtime_exec"),
    (re.compile(r"\bnew\s+ProcessBuilder\s*\(", re.IGNORECASE), "process_builder"),
    (re.compile(r"ScriptEngineManager\s*\(\s*\)", re.IGNORECASE), "script_engine_manager"),
    (re.compile(r"\.eval\s*\(", re.IGNORECASE), "eval_call"),
)


def scan_jsp_sinks(content: str) -> tuple[list[Finding], bool, str]:
    if not content.strip():
        return [], False, ""

    if "<%" not in content and "%>" not in content:
        return [], False, "unknown"

    findings: list[Finding] = []
    seen: set[tuple[int, str]] = set()
    for rx, key in _JSP_RULES:
        for m in rx.finditer(content):
            dedupe = (m.start(), key)
            if dedupe in seen:
                continue
            seen.add(dedupe)
            end = min(m.end() + 80, len(content))
            snippet = content[m.start() : end]
            findings.append(
                Finding(
                    id=f"jsp-sink-{key}-{m.start()}",
                    category="rce",
                    severity="high",
                    confidence=0.88,
                    evidence=Evidence(
                        snippet=snippet[:220],
                        start=m.start(),
                        end=m.end(),
                        location=f"jsp:sink:{key}",
                    ),
                    signals=[Signal(type="ast_sink", name=key, weight=1.0)],
                )
            )

    ast_ok = bool(findings)
    return findings, ast_ok, "jsp"
