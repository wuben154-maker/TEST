"""Tests for registry-only official_subagents.build_subagent_specs."""

from typing import Any
from unittest.mock import MagicMock

from app.parsers.final_message_split import SUBAGENT_WRAPUP_HEADING

from app.agents.official_subagents import build_subagent_specs


def _dummy_backend_factory(_rt: Any) -> MagicMock:
    """email-security tools use backend_binding: required; building specs needs a factory."""
    return MagicMock()

REGISTRY_AGENT_NAMES = frozenset(
    {
        "binary-analysis",
        "email-security",
        "web-security",
        "soc-alert",
        "deep-research",
    }
)


def test_build_subagent_specs_matches_shipped_registry():
    specs = build_subagent_specs(backend_factory=_dummy_backend_factory)
    assert {s["name"] for s in specs} == REGISTRY_AGENT_NAMES


def test_general_security_and_vuln_scan_not_subagents():
    specs = build_subagent_specs(backend_factory=_dummy_backend_factory)
    names = {s["name"] for s in specs}
    assert "general-security" not in names
    assert "vuln-scan" not in names


def test_standard_spec_has_required_keys_and_bundle_skills():
    specs = build_subagent_specs(backend_factory=_dummy_backend_factory)
    by_name = {s["name"]: s for s in specs}
    spec = by_name["email-security"]
    assert spec.get("description")
    assert "system_prompt" in spec
    assert SUBAGENT_WRAPUP_HEADING in spec["system_prompt"]
    assert "tools" in spec
    assert "skills" in spec
    assert spec["skills"] == ["/subagent-skills/email-security/"]
    assert "runnable" not in spec


def test_deep_research_default_is_compiled_subagent():
    specs = build_subagent_specs(backend_factory=_dummy_backend_factory)
    dr = next(s for s in specs if s["name"] == "deep-research")
    assert "runnable" in dr


def test_deep_research_standard_agent_gets_research_tools(monkeypatch):
    monkeypatch.setenv("RESEARCH_AGENT_MODE", "standard_agent")
    try:
        specs = build_subagent_specs(backend_factory=_dummy_backend_factory)
    finally:
        monkeypatch.delenv("RESEARCH_AGENT_MODE", raising=False)

    by_name = {s["name"]: s for s in specs}
    dr = by_name["deep-research"]
    assert "runnable" not in dr
    tool_names = {getattr(t, "name", str(t)) for t in dr["tools"]}
    assert "web_search" in tool_names
