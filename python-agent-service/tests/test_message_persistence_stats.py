"""F2b/F2c: conclusion.meta (TaskStatsMeta) must survive persistence.

Phase 5 regression against the systematic fix — verifies that the persistence
state dict produced by `_build_state_from_events` carries `stats` populated
from the SSE `conclusion.meta` payload so DB writes can persist it.

We deliberately do NOT exercise the DB driver here — asyncpg / supabase
clients are mocked elsewhere. These tests pin the contract between adapter
output and persistence-state input.
"""

from __future__ import annotations

from app.services.message_persistence import _build_state_from_events


def _security_meta() -> dict:
    return {
        "taskKind": "security",
        "security": {
            "severity": "high",
            "riskScore": 72,
            "actionable": {"total": 3, "critical": 1, "medium": 2},
            "threatClasses": ["XSS", "SQLi"],
            "validation": ["static", "yara"],
        },
    }


def _research_meta() -> dict:
    return {
        "taskKind": "research",
        "research": {
            "keyFindings": 5,
            "recommendations": 2,
            "sources": 18,
            "freshness": "<=30d",
            "gaps": 1,
        },
    }


def test_conclusion_meta_security_populates_state_stats():
    events = [
        {"type": "conclusion", "id": "conclusion", "content": "report body", "meta": _security_meta()},
    ]
    state = _build_state_from_events(events, "analyze this url", ui_language="en")
    assert state.get("stats") == _security_meta()


def test_conclusion_meta_research_populates_state_stats():
    events = [
        {"type": "conclusion", "id": "conclusion", "content": "research body", "meta": _research_meta()},
    ]
    state = _build_state_from_events(events, "compare approaches", ui_language="en")
    assert state.get("stats") == _research_meta()


def test_conclusion_without_meta_leaves_stats_absent_or_none():
    events = [
        {"type": "conclusion", "id": "conclusion", "content": "plain answer"},
    ]
    state = _build_state_from_events(events, "hi", ui_language="en")
    # Absent OR None — both acceptable; must NOT be a truthy falsy mix
    assert not state.get("stats")


def test_multiple_conclusions_last_meta_wins():
    """Guard against partial adapter replays — latest meta should overwrite earlier."""
    events = [
        {"type": "conclusion", "id": "conclusion", "content": "early", "meta": _research_meta()},
        {"type": "conclusion", "id": "conclusion", "content": "late", "meta": _security_meta()},
    ]
    state = _build_state_from_events(events, "x", ui_language="en")
    assert state.get("stats") == _security_meta()


def test_malformed_meta_does_not_break_build():
    """Contract: persistence never raises on adapter noise."""
    events = [
        {"type": "conclusion", "id": "conclusion", "content": "body", "meta": "not-a-dict"},
    ]
    state = _build_state_from_events(events, "x", ui_language="en")
    # Malformed meta is discarded; state must still contain core keys.
    assert "stats" not in state or state["stats"] in (None, {})
    assert state["content"] == "body"
