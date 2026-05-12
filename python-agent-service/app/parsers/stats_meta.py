"""Task-kind stats meta derivation for the `conclusion` SSE event.

The adapter attaches a compact, decision-oriented `meta` payload to the final
`conclusion` event so the frontend `TaskStatsBar` can render task-specific
chips without regex-parsing the report body.

Two profiles are supported:

- ``security`` (subagent in {web-security, email-security, binary-analysis,
  soc-alert}) — severity, risk score, threat classes, validation trail.
- ``research`` (subagent deep-research) — key findings / recommendations /
  sources / freshness band / gaps, parsed from the subagent's final markdown
  report.

All functions are pure, side-effect free, and must never raise on malformed
input — they return ``None`` or omit fields instead (see acceptance N-02).
"""

from __future__ import annotations

import json
import re
from collections.abc import Iterable, Mapping
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Any
from urllib.parse import urlparse


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

SECURITY_SUBAGENT_TYPES: frozenset[str] = frozenset(
    {
        "web-security",
        "email-security",
        "binary-analysis",
        "soc-alert",
        # Older labels that still appear in some tests / prompts.
        "security",
    }
)
RESEARCH_SUBAGENT_TYPES: frozenset[str] = frozenset({"deep-research"})

VALID_SEVERITIES: tuple[str, ...] = ("critical", "high", "medium", "low", "info")
_SEVERITY_RANK: dict[str, int] = {s: i for i, s in enumerate(VALID_SEVERITIES)}

# Tools that imply a specific validation dimension.
_VALIDATION_TOOL_MAP: dict[str, str] = {
    # Static analysis — pattern/signature matching on artifacts.
    "detect_web_attack": "static",
    "static_analyzer": "static",
    "parse_php": "static",
    "parse_eml": "static",
    "strings_scan": "static",
    # YARA / rule-based matching.
    "yara_scan": "yara",
    "run_yara": "yara",
    # Sandbox execution.
    "run_in_sandbox": "sandbox",
    "sandbox_exec": "sandbox",
    "sandbox_run": "sandbox",
    "run_code_in_sandbox": "sandbox",
    # Threat intelligence.
    "threat_intel_lookup": "ti",
    "ioc_lookup": "ti",
    "virustotal_lookup": "ti",
}
_VALIDATION_ORDER: tuple[str, ...] = ("static", "yara", "sandbox", "ti")


# ---------------------------------------------------------------------------
# Dataclasses (dict-serialised; the adapter uses asdict() → dict)
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class SecurityMeta:
    severity: str
    risk_score: int | None = None
    threat_classes: tuple[str, ...] | None = None
    validation: tuple[str, ...] | None = None
    actionable: Mapping[str, int] | None = None


@dataclass(frozen=True)
class ResearchMeta:
    key_findings: int | None = None
    recommendations: int | None = None
    sources: int | None = None
    freshness: str | None = None
    gaps: int | None = None


@dataclass(frozen=True)
class TaskStatsMeta:
    task_kind: str  # "security" | "research"
    security: SecurityMeta | None = None
    research: ResearchMeta | None = None


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def classify_task_kind(subagent_types: Iterable[str]) -> str | None:
    """Decide which stats profile applies.

    Priority (per design `## Rationale`): security wins over research on mixed
    multi-domain runs — analysts need the safety decision first.
    """
    try:
        norm = {_normalize(x) for x in subagent_types}
    except Exception:
        return None
    if norm & SECURITY_SUBAGENT_TYPES:
        return "security"
    if norm & RESEARCH_SUBAGENT_TYPES:
        return "research"
    return None


def build_task_stats_meta(
    *,
    subagent_types: Iterable[str],
    tools_used: Iterable[str],
    task_outputs: Iterable[str],
    report_markdown: str,
    security_findings_raw: Iterable[Mapping[str, Any]] | None = None,
    language: str = "en",
) -> dict[str, Any] | None:
    """Entry point used by the stream adapter.

    Returns a JSON-serialisable dict ready to be attached as
    ``event["meta"] = build_task_stats_meta(...)`` on the ``conclusion`` event,
    or ``None`` if the task does not match a known profile (generic chat, tool
    failure, etc.).

    Never raises — malformed inputs fall through to ``None``.
    """
    try:
        kind = classify_task_kind(subagent_types)
        if kind == "security":
            sec = derive_security_meta(
                tools_used=tools_used,
                task_outputs=task_outputs,
                security_findings_raw=security_findings_raw,
            )
            if sec is None:
                return {"taskKind": "security"}
            return {"taskKind": "security", "security": _security_to_dict(sec)}
        if kind == "research":
            res = derive_research_meta(
                report_markdown=report_markdown,
                task_outputs=task_outputs,
            )
            if res is None:
                return {"taskKind": "research"}
            return {"taskKind": "research", "research": _research_to_dict(res)}
        return None
    except Exception:
        # Never crash the stream adapter because of meta derivation.
        return None


# ---------------------------------------------------------------------------
# Security derivation
# ---------------------------------------------------------------------------


# Tool names whose tool_result output carries a ``findings`` array that the
# adapter should accumulate for the ``security`` profile.
SECURITY_FINDING_TOOLS: frozenset[str] = frozenset({"detect_web_attack"})


def collect_security_findings_from_tool_output(
    raw_output: str,
) -> list[dict[str, Any]]:
    """Parse a security tool's text output into a list of findings dicts.

    Accepts either a raw JSON object/array string, or text that contains a
    fenced ``json`` block. Never raises — returns an empty list on any error.
    """
    if not isinstance(raw_output, str) or not raw_output.strip():
        return []
    out: list[dict[str, Any]] = []
    # Direct JSON parse first.
    stripped = raw_output.strip()
    try:
        parsed = json.loads(stripped)
    except Exception:
        parsed = None
    if isinstance(parsed, Mapping) and isinstance(parsed.get("findings"), list):
        out.extend(
            dict(f) for f in parsed["findings"] if isinstance(f, Mapping)
        )
    elif isinstance(parsed, list):
        out.extend(dict(f) for f in parsed if isinstance(f, Mapping))
    # Also try fenced blocks — some subagents wrap JSON in ```json ... ```.
    out.extend(
        dict(f) for f in _extract_findings_from_task_output(raw_output)
    )
    return out


def derive_security_meta(
    *,
    tools_used: Iterable[str],
    task_outputs: Iterable[str],
    security_findings_raw: Iterable[Mapping[str, Any]] | None,
) -> SecurityMeta | None:
    """Derive the security profile from tool usage and (optionally) parsed
    structured findings."""
    findings: list[Mapping[str, Any]] = []
    if security_findings_raw:
        findings.extend(f for f in security_findings_raw if isinstance(f, Mapping))
    # If the caller did not pre-parse, make a best-effort pass over task_outputs
    # looking for ```json ... ``` fenced findings blocks.
    if not findings:
        for out in task_outputs or ():
            findings.extend(_extract_findings_from_task_output(out))

    severity = _max_severity(findings) or "info"
    risk_score = _max_risk_score(findings)
    threat_classes = _top_threat_classes(findings)
    validation = _validation_trail(tools_used)
    actionable = _actionable_breakdown(findings)

    return SecurityMeta(
        severity=severity,
        risk_score=risk_score,
        threat_classes=threat_classes or None,
        validation=validation or None,
        actionable=actionable,
    )


def _actionable_breakdown(
    findings: Iterable[Mapping[str, Any]],
) -> dict[str, int] | None:
    """Group findings into critical / high / medium counts for the UI chip.

    Frontend `SecurityActionableBreakdown` is `{total, critical, high, medium}`.
    Low/info findings are intentionally excluded — the "Actionable" chip shows
    items a SOC analyst should triage now, not noise.
    """
    counts = {"total": 0, "critical": 0, "high": 0, "medium": 0}
    for f in findings:
        sev = _normalize(f.get("severity"))
        if sev not in ("critical", "high", "medium"):
            continue
        counts[sev] += 1
        counts["total"] += 1
    if counts["total"] == 0:
        return None
    return counts


def _extract_findings_from_task_output(text: str) -> list[Mapping[str, Any]]:
    """Best-effort: pull a JSON array of findings out of fenced ```json blocks.

    Supported shapes:
      * ``{"findings": [...]}``
      * ``[{"type": ..., "severity": ...}, ...]``
    """
    if not isinstance(text, str) or not text:
        return []
    out: list[Mapping[str, Any]] = []
    for block in re.findall(r"```(?:json|JSON)?\s*\n(.*?)\n```", text, flags=re.DOTALL):
        try:
            parsed = json.loads(block.strip())
        except Exception:
            continue
        if isinstance(parsed, Mapping) and isinstance(parsed.get("findings"), list):
            out.extend(f for f in parsed["findings"] if isinstance(f, Mapping))
        elif isinstance(parsed, list):
            out.extend(f for f in parsed if isinstance(f, Mapping))
    return out


def _max_severity(findings: Iterable[Mapping[str, Any]]) -> str | None:
    best_rank: int | None = None
    for f in findings:
        sev = _normalize(f.get("severity"))
        if sev not in _SEVERITY_RANK:
            continue
        r = _SEVERITY_RANK[sev]
        if best_rank is None or r < best_rank:
            best_rank = r
    if best_rank is None:
        return None
    return VALID_SEVERITIES[best_rank]


def _max_risk_score(findings: Iterable[Mapping[str, Any]]) -> int | None:
    best: int | None = None
    for f in findings:
        raw = f.get("risk") if "risk" in f else f.get("risk_score")
        if raw is None:
            continue
        try:
            score = int(float(raw))
        except (TypeError, ValueError):
            continue
        score = max(0, min(100, score))
        if best is None or score > best:
            best = score
    return best


def _top_threat_classes(findings: Iterable[Mapping[str, Any]]) -> tuple[str, ...]:
    """Return threat-class identifiers ordered by earliest (risk-desc) occurrence.

    The frontend truncates to the top 2; we pass the full ordered list so the
    UI can opt into a ``+N`` suffix.
    """
    scored: list[tuple[int, int, str]] = []  # (-risk, order, class)
    seen: set[str] = set()
    for idx, f in enumerate(findings):
        t = _normalize(f.get("type")) or _normalize(f.get("class")) or _normalize(
            f.get("category")
        )
        if not t or t in seen:
            continue
        seen.add(t)
        risk_raw = f.get("risk") if "risk" in f else f.get("risk_score")
        try:
            risk = int(float(risk_raw)) if risk_raw is not None else 0
        except (TypeError, ValueError):
            risk = 0
        scored.append((-risk, idx, t))
    scored.sort()
    return tuple(t for _r, _i, t in scored)


def _validation_trail(tools_used: Iterable[str]) -> tuple[str, ...]:
    """Return the validation dimensions (static / yara / sandbox / ti) exercised
    during this run, in the canonical display order."""
    dims: set[str] = set()
    for tool in tools_used or ():
        key = (tool or "").strip().lower()
        dim = _VALIDATION_TOOL_MAP.get(key)
        if dim:
            dims.add(dim)
    return tuple(d for d in _VALIDATION_ORDER if d in dims)


# ---------------------------------------------------------------------------
# Research derivation
# ---------------------------------------------------------------------------


# Section-name aliases we're willing to accept for each research chip.
_RESEARCH_SECTION_ALIASES: dict[str, tuple[str, ...]] = {
    "key_findings": (
        "executive summary",
        "key findings",
        "findings",
        "key insights",
    ),
    "recommendations": (
        "recommendations",
        "recommended actions",
        "next steps",
    ),
    "gaps": (
        "gaps & limitations",
        "gaps and limitations",
        "limitations",
        "gaps",
        "open questions",
    ),
    "sources": (
        "sources",
        "references",
        "citations",
    ),
}

_FRESHNESS_BANDS: tuple[tuple[str, timedelta], ...] = (
    ("<=7d", timedelta(days=7)),
    ("<=30d", timedelta(days=30)),
    ("<=90d", timedelta(days=90)),
)


def derive_research_meta(
    *,
    report_markdown: str,
    task_outputs: Iterable[str] | None = None,
) -> ResearchMeta | None:
    """Derive the research profile from the final markdown report.

    Two-tier strategy:

    1. **Subagent-emitted ``research_stats`` JSON block (preferred).** Deep
       research reports use free-form section names ("Overview", "总结与展望",
       etc.) so a fixed alias table cannot reliably catch ``keyFindings`` /
       ``recommendations`` / ``gaps``. The ``deep-research`` subagent emits a
       fenced ``{"research_stats": {...}}`` block per the prompt schema; we
       read it from the raw ``task_outputs`` when present (the fenced block
       lives **after** ``## SM_SUBAGENT_WRAPUP`` and is sliced out by the
       conclusion split, so ``report_markdown`` alone is not enough), then
       fall back to ``report_markdown``.
    2. **Markdown alias derivation (fallback).** Used per-field when the JSON
       block is absent or omits a field, and always for ``sources`` /
       ``freshness`` (those depend on real URLs + dates the model would
       hallucinate).

    Operates on markdown emitted by the ``deep-research`` subagent; not on the
    frontend WorkspaceBlocks (which are a post-render view).
    """
    text = report_markdown or ""
    if not text.strip() and not (task_outputs):
        return None

    # Prefer task_outputs because it preserves the WRAPUP-trailing fenced JSON
    # block; fall back to report_markdown for legacy / inline cases.
    declared: dict[str, int] = {}
    for raw in (task_outputs or ()):
        if isinstance(raw, str) and raw:
            declared = _extract_research_stats_from_text(raw)
            if declared:
                break
    if not declared:
        declared = _extract_research_stats_from_text(text)

    sections = _split_markdown_sections(text)
    kf = declared.get("keyFindings")
    if kf is None:
        kf = _bullet_count_in_first(sections, _RESEARCH_SECTION_ALIASES["key_findings"])
    rec = declared.get("recommendations")
    if rec is None:
        rec = _bullet_count_in_first(sections, _RESEARCH_SECTION_ALIASES["recommendations"])
    gaps = declared.get("gaps")
    if gaps is None:
        gaps = _bullet_count_in_first(sections, _RESEARCH_SECTION_ALIASES["gaps"])

    sources_section = _first_matching_section(sections, _RESEARCH_SECTION_ALIASES["sources"])
    sources_count: int | None
    freshness: str | None
    if sources_section is None:
        sources_count = None
        freshness = None
    else:
        sources_count, freshness = _derive_sources_fields(sources_section)

    if all(v is None for v in (kf, rec, gaps, sources_count, freshness)):
        return None
    return ResearchMeta(
        key_findings=kf,
        recommendations=rec,
        sources=sources_count,
        freshness=freshness,
        gaps=gaps,
    )


def _extract_research_stats_from_text(text: str) -> dict[str, int]:
    """Best-effort: find a fenced ``{"research_stats": {...}}`` block.

    Accepts integer-typed fields ``keyFindings``, ``recommendations``, ``gaps``.
    Also accepts snake_case aliases for robustness against minor model drift.
    Never raises — returns an empty dict on any error.
    """
    if not isinstance(text, str) or not text:
        return {}
    accepted = {
        "keyFindings": "keyFindings",
        "key_findings": "keyFindings",
        "recommendations": "recommendations",
        "gaps": "gaps",
    }
    out: dict[str, int] = {}
    for block in re.findall(r"```(?:json|JSON)?\s*\n(.*?)\n```", text, flags=re.DOTALL):
        try:
            parsed = json.loads(block.strip())
        except Exception:
            continue
        if not isinstance(parsed, Mapping):
            continue
        stats = parsed.get("research_stats")
        if not isinstance(stats, Mapping):
            continue
        for raw_key, canonical in accepted.items():
            if raw_key not in stats or canonical in out:
                continue
            try:
                v = int(stats[raw_key])
            except (TypeError, ValueError):
                continue
            if v < 0:
                continue
            out[canonical] = v
    return out


def _split_markdown_sections(text: str) -> list[tuple[str, str]]:
    """Split a markdown document into ``[(heading, body), ...]`` tuples.

    ``heading`` is the normalised lowercase section title (any ``##``/``###``);
    ``body`` is the raw text between this heading and the next one of the same
    or a higher level.
    """
    out: list[tuple[str, str]] = []
    current_heading: str | None = None
    buf: list[str] = []
    for line in text.splitlines():
        m = re.match(r"^\s*#{1,6}\s+(.+?)\s*$", line)
        if m:
            if current_heading is not None:
                out.append((current_heading, "\n".join(buf)))
            current_heading = _normalize(m.group(1))
            buf = []
        else:
            if current_heading is not None:
                buf.append(line)
    if current_heading is not None:
        out.append((current_heading, "\n".join(buf)))
    return out


def _first_matching_section(
    sections: list[tuple[str, str]], aliases: tuple[str, ...]
) -> str | None:
    aliases_norm = tuple(a.lower() for a in aliases)
    for heading, body in sections:
        if any(heading.startswith(a) or a in heading for a in aliases_norm):
            return body
    return None


def _bullet_count_in_first(
    sections: list[tuple[str, str]], aliases: tuple[str, ...]
) -> int | None:
    body = _first_matching_section(sections, aliases)
    if body is None:
        return None
    return _count_top_level_bullets(body)


def _count_top_level_bullets(body: str) -> int:
    """Count top-level list items — lines that start with ``-``, ``*``, or a
    numbered ``N.`` marker with at most one leading space.
    """
    n = 0
    for raw in body.splitlines():
        line = raw.rstrip()
        if not line.strip():
            continue
        leading_ws = len(line) - len(line.lstrip())
        if leading_ws > 1:
            continue
        stripped = line.lstrip()
        if stripped.startswith(("- ", "* ", "• ")):
            n += 1
            continue
        if re.match(r"^\d+[.)]\s+", stripped):
            n += 1
    return n


def _derive_sources_fields(body: str) -> tuple[int | None, str | None]:
    """Extract (unique hostname count, freshness band) from a sources section."""
    urls: list[str] = []
    dates: list[datetime] = []
    for line in body.splitlines():
        for url in re.findall(r"https?://[^\s)>\]\"']+", line):
            urls.append(url.rstrip(".,;:"))
        # NOTE: alternation order matters — Python regex is leftmost-first with
        # no backtracking across branches. Put longer branches first so "04-21"
        # matches "21" (day) rather than greedily biting off just "2".
        for m in re.findall(
            r"(20\d{2}[-/](?:1[0-2]|0?[1-9])[-/](?:3[01]|[12]\d|0?[1-9]))",
            line,
        ):
            dt = _parse_iso_date(m)
            if dt is not None:
                dates.append(dt)
    hostnames: set[str] = set()
    for u in urls:
        try:
            host = urlparse(u).hostname
        except Exception:
            host = None
        if host:
            hostnames.add(host.lower().removeprefix("www."))
    count: int | None = len(hostnames) if hostnames else None

    if not dates:
        freshness: str | None = "n/a" if count else None
    else:
        latest = max(dates)
        now = datetime.now(tz=timezone.utc)
        age = now - latest
        freshness = "older"
        for label, bound in _FRESHNESS_BANDS:
            if age <= bound:
                freshness = label
                break
    return count, freshness


def _parse_iso_date(s: str) -> datetime | None:
    s = s.replace("/", "-")
    try:
        return datetime.strptime(s, "%Y-%m-%d").replace(tzinfo=timezone.utc)
    except ValueError:
        pass
    try:
        return datetime.strptime(s, "%Y-%-m-%-d").replace(tzinfo=timezone.utc)
    except ValueError:
        return None


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _normalize(value: Any) -> str:
    if value is None:
        return ""
    return str(value).strip().lower().replace("_", "-")


def _security_to_dict(sec: SecurityMeta) -> dict[str, Any]:
    out: dict[str, Any] = {"severity": sec.severity}
    if sec.risk_score is not None:
        out["riskScore"] = int(sec.risk_score)
    if sec.actionable is not None:
        out["actionable"] = dict(sec.actionable)
    if sec.threat_classes:
        out["threatClasses"] = list(sec.threat_classes)
    if sec.validation:
        out["validation"] = list(sec.validation)
    return out


def _research_to_dict(res: ResearchMeta) -> dict[str, Any]:
    out: dict[str, Any] = {}
    if res.key_findings is not None:
        out["keyFindings"] = int(res.key_findings)
    if res.recommendations is not None:
        out["recommendations"] = int(res.recommendations)
    if res.sources is not None:
        out["sources"] = int(res.sources)
    if res.freshness is not None:
        out["freshness"] = res.freshness
    if res.gaps is not None:
        out["gaps"] = int(res.gaps)
    return out
