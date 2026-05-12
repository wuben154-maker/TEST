"""JSON payloads for project_derived_memory and user_memory_index."""

from __future__ import annotations

from typing import Any, TypedDict

MEMORY_SCHEMA_VERSION = 1


class EntityDict(TypedDict, total=False):
    type: str
    value: str
    verdict: str | None
    confidence: float | None


class ProjectDerivedPayload(TypedDict, total=False):
    version: int
    entities: list[EntityDict]
    findings: list[str]
    open_questions: list[str]
    running_summary: str
    source_last_request_id: str | None


class ProjectRefDict(TypedDict, total=False):
    project_id: str
    title: str
    last_active_at: str
    one_line_summary: str


class UserIndexPayload(TypedDict, total=False):
    version: int
    projects: list[ProjectRefDict]
    preferences: dict[str, str]


def default_project_payload() -> dict[str, Any]:
    return {
        "version": MEMORY_SCHEMA_VERSION,
        "entities": [],
        "findings": [],
        "open_questions": [],
        "running_summary": "",
        "source_last_request_id": None,
    }


def default_user_index_payload() -> dict[str, Any]:
    return {
        "version": MEMORY_SCHEMA_VERSION,
        "projects": [],
        "preferences": {},
    }


def normalize_project_payload(raw: dict[str, Any] | None) -> dict[str, Any]:
    base = default_project_payload()
    if not raw:
        return base
    out = {**base, **raw}
    out["version"] = int(out.get("version") or MEMORY_SCHEMA_VERSION)
    out["entities"] = list(out.get("entities") or [])
    out["findings"] = [str(x) for x in (out.get("findings") or []) if x is not None]
    out["open_questions"] = [
        str(x) for x in (out.get("open_questions") or []) if x is not None
    ]
    out["running_summary"] = str(out.get("running_summary") or "")
    rid = out.get("source_last_request_id")
    out["source_last_request_id"] = str(rid) if rid else None
    return out


def normalize_user_payload(raw: dict[str, Any] | None) -> dict[str, Any]:
    base = default_user_index_payload()
    if not raw:
        return base
    out = {**base, **raw}
    out["version"] = int(out.get("version") or MEMORY_SCHEMA_VERSION)
    out["projects"] = list(out.get("projects") or [])
    prefs = out.get("preferences") or {}
    out["preferences"] = {str(k): str(v) for k, v in prefs.items()} if isinstance(prefs, dict) else {}
    return out
