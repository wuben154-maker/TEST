"""PHP structural sink scan (minimal parser: tag detection + call-site spans)."""

from __future__ import annotations

import re

from .models import Evidence, Finding, Signal

# Dangerous sinks with explicit call parentheses
_SINK_CALL = re.compile(
    r"\b(eval|assert|system|exec|shell_exec|passthru|popen|proc_open|create_function)\s*\(",
    re.IGNORECASE,
)

# preg_replace with /e modifier (deprecated RCE vector)
_PREG_E = re.compile(r"\bpreg_replace\s*\(", re.IGNORECASE)


def scan_php_sinks(content: str) -> tuple[list[Finding], bool, str]:
    """
    Scan PHP text for dangerous sinks.

    Returns:
        findings, ast_ok (structural scan succeeded for PHP blocks), language label.
    """
    if not content.strip():
        return [], False, ""

    has_tag = "<?php" in content or "<?=" in content
    if not has_tag:
        return [], False, "unknown"

    findings: list[Finding] = []
    for m in _SINK_CALL.finditer(content):
        name = m.group(1).lower()
        end = min(m.end() + 60, len(content))
        snippet = content[m.start() : end]
        findings.append(
            Finding(
                id=f"php-sink-{name}-{m.start()}",
                category="webshell",
                severity="high",
                confidence=0.9,
                evidence=Evidence(
                    snippet=snippet[:220],
                    start=m.start(),
                    end=m.end(),
                    location=f"php:ast:Call:{name}",
                ),
                signals=[Signal(type="ast_sink", name=name, weight=1.0)],
            )
        )

    for m in _PREG_E.finditer(content):
        # Inspect following chars for /e in quote
        tail = content[m.start() : m.start() + 400]
        if re.search(r"['\"][^'\"]*/e[a-z]*['\"]", tail, re.IGNORECASE):
            findings.append(
                Finding(
                    id=f"php-sink-preg_replace_e-{m.start()}",
                    category="rce",
                    severity="high",
                    confidence=0.85,
                    evidence=Evidence(
                        snippet=tail[:220],
                        start=m.start(),
                        end=min(m.start() + 80, len(content)),
                        location="php:ast:Call:preg_replace_e",
                    ),
                    signals=[Signal(type="ast_sink", name="preg_replace_e", weight=1.0)],
                )
            )

    ast_ok = True
    return findings, ast_ok, "php"
