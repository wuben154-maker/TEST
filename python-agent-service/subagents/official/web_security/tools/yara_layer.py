"""L1 YARA scan over UTF-8 bytes (webshell-oriented rules under skill bundle)."""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

from .models import Evidence, Finding, Severity, Signal

logger = logging.getLogger(__name__)

try:
    import yara

    YARA_AVAILABLE = True
except ImportError:
    yara = None  # type: ignore[assignment]
    YARA_AVAILABLE = False


def compile_rules(rules_dir: Path) -> tuple[Any | None, str, int, str]:
    """
    Returns:
        compiled_rules, status, count, detail
    """
    if not YARA_AVAILABLE:
        return None, "unavailable", 0, "yara-python not installed"

    if not rules_dir.is_dir():
        return None, "no_rules", 0, f"directory missing: {rules_dir}"

    paths = sorted(rules_dir.glob("*.yar")) + sorted(rules_dir.glob("*.yara"))
    if not paths:
        return None, "no_rules", 0, "no .yar files"

    # yara-python 4.x expects filepaths as mapping of namespace -> path
    filepaths_dict = {p.stem: str(p.resolve()) for p in paths}
    try:
        rules = yara.compile(filepaths=filepaths_dict)
        return rules, "ok", len(filepaths_dict), ""
    except Exception as e:
        logger.warning("yara_compile_failed: %s", str(e))
        return None, "error", 0, str(e)


def _meta_dict(match: Any) -> dict[str, str]:
    out: dict[str, str] = {}
    raw = getattr(match, "meta", None) or {}
    if isinstance(raw, dict):
        for k, v in raw.items():
            out[str(k)] = str(v) if v is not None else ""
    return out


def _severity_from_meta(meta: dict[str, str], rule: str) -> Severity:
    sev = (meta.get("severity") or "").lower().strip()
    if sev in ("critical", "high", "medium", "low", "info"):
        return sev  # type: ignore[return-value]
    rl = rule.lower()
    if any(x in rl for x in ("webshell", "rce", "backdoor")):
        return "high"
    return "medium"


def matches_to_findings(matches: list[Any], data: bytes) -> list[Finding]:
    findings: list[Finding] = []
    for match in matches:
        meta = _meta_dict(match)
        rule = str(match.rule)
        sev = _severity_from_meta(meta, rule)
        start = 0
        snippet = ""
        if getattr(match, "strings", None):
            try:
                sm = match.strings[0]
                if sm.instances:
                    start = sm.instances[0].offset
                    ln = min(120, len(data) - start) if start < len(data) else 0
                    snippet = data[start : start + ln].decode("utf-8", errors="replace")
            except (IndexError, TypeError):
                pass

        loc = f"L1:yara:{rule}"
        if meta.get("description"):
            loc = f"{loc}:{meta['description'][:80]}"

        findings.append(
            Finding(
                id=f"yara-{rule}-{start}",
                category="webshell",
                severity=sev,
                confidence=0.88,
                layer="L1",
                evidence=Evidence(
                    snippet=snippet[:220],
                    start=start,
                    end=min(start + 220, len(data)),
                    location=loc,
                ),
                signals=[Signal(type="yara_rule", name=rule, weight=1.0)],
            )
        )
    return findings


def scan_with_compiled(rules: Any, data: bytes, timeout: int = 30) -> list[Finding]:
    if rules is None or not data:
        return []
    try:
        matches = rules.match(data=data, timeout=timeout)
    except Exception as e:
        logger.warning("yara_match_failed", error=str(e))
        return []
    return matches_to_findings(matches, data)
