"""Pure merge helpers for derived memory (rules + bounded lists)."""

from __future__ import annotations

import re
from typing import Any

from app.datetime_support import format_api_datetime, now_app
from app.services.context_memory.schema import (
    EntityDict,
    MEMORY_SCHEMA_VERSION,
    normalize_project_payload,
    normalize_user_payload,
)

_MAX_ENTITIES = 80
_MAX_FINDINGS = 40
_MAX_OPEN_QUESTIONS = 20
_MAX_RUNNING_SUMMARY_CHARS = 2000
_MAX_ONE_LINE = 200


def truncate_for_summary(text: str, max_chars: int) -> str:
    t = (text or "").strip()
    if len(t) <= max_chars:
        return t
    return t[: max_chars - 20] + "\n…(truncated)"


def extract_iocs_rules(text: str) -> list[EntityDict]:
    """Rule-based IOC extraction (no LLM)."""
    if not text:
        return []
    entities: list[EntityDict] = []
    seen: set[tuple[str, str]] = set()

    def add(t: str, v: str) -> None:
        v = v.strip()
        if not v or len(v) > 512:
            return
        key = (t, v.lower())
        if key in seen:
            return
        seen.add(key)
        entities.append({"type": t, "value": v, "verdict": None, "confidence": None})

    ip_pattern = r"\b(?:\d{1,3}\.){3}\d{1,3}\b"
    for m in re.finditer(ip_pattern, text):
        add("ip", m.group(0))

    domain_pattern = (
        r"\b(?:[a-zA-Z0-9](?:[a-zA-Z0-9-]{0,61}[a-zA-Z0-9])?\.)+[a-zA-Z]{2,}\b"
    )
    for m in re.finditer(domain_pattern, text):
        add("domain", m.group(0))

    hash_pattern = r"\b[a-fA-F0-9]{32,64}\b"
    for m in re.finditer(hash_pattern, text):
        add("hash", m.group(0))

    file_pattern = r"\b[\w\-\.]+\.(exe|dll|pdf|docx?|xlsx?|zip|rar|7z|pcap|elf|ps1|bat|js)\b"
    for m in re.finditer(file_pattern, text, re.IGNORECASE):
        add("filename", m.group(0))

    return entities[:_MAX_ENTITIES]


def merge_entity_lists(
    prev: list[EntityDict], new: list[EntityDict]
) -> list[EntityDict]:
    seen: set[tuple[str, str]] = set()
    out: list[EntityDict] = []
    for e in prev + new:
        t = str(e.get("type") or "unknown")
        v = str(e.get("value") or "").strip()
        if not v:
            continue
        key = (t, v.lower())
        if key in seen:
            continue
        seen.add(key)
        out.append(
            {
                "type": t,
                "value": v,
                "verdict": e.get("verdict"),
                "confidence": e.get("confidence"),
            }
        )
        if len(out) >= _MAX_ENTITIES:
            break
    return out


def merge_string_lists(prev: list[str], delta: list[str], cap: int) -> list[str]:
    seen: set[str] = set()
    out: list[str] = []
    for s in prev + delta:
        s = str(s).strip()
        if not s or s in seen:
            continue
        seen.add(s)
        out.append(s[:500])
        if len(out) >= cap:
            break
    return out


def merge_running_summary(prev: str, delta: str | None) -> str:
    prev = (prev or "").strip()
    d = (delta or "").strip()
    if not d:
        return prev[:_MAX_RUNNING_SUMMARY_CHARS]
    if not prev:
        merged = d
    elif d.lower() in prev.lower():
        merged = prev
    else:
        merged = f"{prev}\n{d}".strip()
    if len(merged) > _MAX_RUNNING_SUMMARY_CHARS:
        merged = merged[: _MAX_RUNNING_SUMMARY_CHARS - 12] + "\n…(truncated)"
    return merged


def merge_project_derived(
    prev: dict[str, Any] | None,
    *,
    assistant_excerpt: str,
    request_id: str | None,
    llm_findings_delta: list[str] | None,
    llm_summary_delta: str | None,
) -> dict[str, Any]:
    base = normalize_project_payload(prev)
    new_entities = extract_iocs_rules(assistant_excerpt)
    base["entities"] = merge_entity_lists(base["entities"], new_entities)
    findings_delta = list(llm_findings_delta or [])
    base["findings"] = merge_string_lists(base["findings"], findings_delta, _MAX_FINDINGS)
    base["running_summary"] = merge_running_summary(
        base["running_summary"], llm_summary_delta
    )
    base["source_last_request_id"] = request_id
    base["version"] = MEMORY_SCHEMA_VERSION
    return base


def patch_user_index(
    prev: dict[str, Any] | None,
    *,
    project_id: str,
    project_title: str,
    one_line: str,
) -> dict[str, Any]:
    base = normalize_user_payload(prev)
    now = format_api_datetime(now_app())
    one_line = (one_line or "").strip()[:_MAX_ONE_LINE]
    projects = list(base["projects"])
    filtered = [p for p in projects if str(p.get("project_id")) != project_id]
    filtered.append(
        {
            "project_id": project_id,
            "title": (project_title or "")[:200],
            "last_active_at": now,
            "one_line_summary": one_line,
        }
    )
    filtered.sort(key=lambda p: str(p.get("last_active_at") or ""), reverse=True)
    base["projects"] = filtered[:50]
    base["version"] = MEMORY_SCHEMA_VERSION
    return base


def format_derived_for_injection(payload: dict[str, Any], max_chars: int) -> str:
    p = normalize_project_payload(payload)
    parts: list[str] = []
    if p["running_summary"]:
        parts.append(f"Summary: {p['running_summary']}")
    if p["entities"]:
        bits = [f"{e.get('type')}:{e.get('value')}" for e in p["entities"][:30]]
        parts.append("Entities: " + "; ".join(bits))
    if p["findings"]:
        parts.append("Findings: " + " | ".join(p["findings"][:15]))
    if p["open_questions"]:
        parts.append("Open: " + " | ".join(p["open_questions"][:10]))
    text = "\n".join(parts).strip()
    return truncate_for_summary(text, max_chars) if text else ""


def format_user_index_for_injection(payload: dict[str, Any], max_chars: int) -> str:
    p = normalize_user_payload(payload)
    lines: list[str] = []
    for proj in (p.get("projects") or [])[:15]:
        pid = str(proj.get("project_id") or "")
        title = str(proj.get("title") or "")
        ol = str(proj.get("one_line_summary") or "")
        if pid:
            lines.append(f"- {title or pid}: {ol}".strip())
    text = "\n".join(lines).strip()
    return truncate_for_summary(text, max_chars) if text else ""
