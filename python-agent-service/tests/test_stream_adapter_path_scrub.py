"""Verify ``_emit`` / ``_emit_subagent`` strip internal paths before SSE.

We don't spin up the full DeepAgent graph here; instead we construct tiny
event dicts that mimic what ``adapt_deepagent_astream_to_sse`` + its
subagent sibling feed through ``_emit`` and confirm the output contains
user-facing path labels, not raw ``/workspace/u_*/p_*/...``.
"""

from __future__ import annotations

from app.parsers.path_scrub import scrub_event


def test_scrub_event_rewrites_workspace_tail():
    ev = {
        "type": "tool_result",
        "label": "Wrote /workspace/u_alice/p_proj1/report.md",
        "detail": "Saved at /workspace/u_alice/p_proj1/report.md",
    }
    out = scrub_event(ev)
    assert "u_alice" not in out["label"]
    assert "u_alice" not in out["detail"]
    assert "workspace/report.md" in out["label"]
    assert "workspace/report.md" in out["detail"]


def test_scrub_event_masks_memories_and_skills():
    ev = {
        "type": "tool_call",
        "label": "Load /skills/web-security/SKILL.md and note /memories/u_bob/history.md",
    }
    out = scrub_event(ev)
    assert "/skills/web-security/SKILL.md" not in out["label"]
    assert "/memories/u_bob/history.md" not in out["label"]
    assert "System Skill: web-security" in out["label"]
    assert "Memory: history.md" in out["label"]


def test_scrub_event_idempotent_on_clean_text():
    ev = {"type": "chunk", "text": "Hello world"}
    assert scrub_event(ev) == ev


def test_scrub_event_preserves_non_string_fields():
    ev = {"type": "tool_result", "count": 3, "flag": True, "label": "ok"}
    out = scrub_event(ev)
    assert out["count"] == 3
    assert out["flag"] is True
    assert out["label"] == "ok"
