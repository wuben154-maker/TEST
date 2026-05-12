"""Regression tests for subagent execution enforcement."""

from pathlib import Path
from typing import Any
from unittest.mock import MagicMock

from app.agents import official_subagents
from app.agents.subagent_registry import SubagentRegistryFile, get_tools_for_agent
from app._vendor.deepagents.middleware.subagents import SubAgentMiddleware


def _dummy_backend_factory(_rt: Any) -> MagicMock:
    return MagicMock()


def test_master_prompt_contains_critical_task_boundary():
    """Prompt should include critical workflow and task() mention."""
    prompt_path = (
        Path(__file__).resolve().parents[1]
        / "app"
        / "prompts"
        / "MASTER_AGENT.md"
    )
    content = prompt_path.read_text(encoding="utf-8")
    assert "CRITICAL" in content
    assert "task()" in content
    assert "subagent" in content.lower()


def test_master_prompt_contains_mandatory_workflow():
    """MASTER_AGENT.md must include routing / delegation guidance."""
    prompt_path = (
        Path(__file__).resolve().parents[1]
        / "app"
        / "prompts"
        / "MASTER_AGENT.md"
    )
    content = prompt_path.read_text(encoding="utf-8")
    assert "task()" in content
    assert "Path A" in content or "Step 1" in content
    assert "subagent" in content.lower()


def test_subagent_web_security_includes_web_profile_tools():
    """Web-security profile merges common tools with create_web_tools()."""
    tools = get_tools_for_agent("web-security")
    tool_names = {tool.name for tool in tools}
    assert "extract_iocs" in tool_names
    assert "detect_web_attack" in tool_names


def test_subagent_email_security_includes_email_profile_tools():
    """Email-security profile merges common tools with create_email_tools()."""
    tools = get_tools_for_agent("email-security")
    tool_names = {tool.name for tool in tools}
    assert "extract_iocs" in tool_names
    assert "analyze_email_headers" in tool_names
    assert "detect_phishing_indicators" in tool_names


def test_build_subagent_specs_count_matches_registry():
    specs = official_subagents.build_subagent_specs(
        backend_factory=_dummy_backend_factory,
    )
    assert len(specs) == 5
    assert {s["name"] for s in specs} == {
        "binary-analysis",
        "email-security",
        "web-security",
        "soc-alert",
        "deep-research",
    }


def test_build_subagent_specs_structure():
    specs = official_subagents.build_subagent_specs(
        backend_factory=_dummy_backend_factory,
    )
    spec = next(s for s in specs if s["name"] == "email-security")
    assert spec.get("description")
    assert "system_prompt" in spec
    assert "model" in spec
    assert "tools" in spec
    assert "skills" in spec
    assert "runnable" not in spec


def test_build_subagent_specs_includes_bundle_skills_sources():
    """Each standard subagent uses bundle-local SkillsMiddleware source."""
    specs = official_subagents.build_subagent_specs(
        backend_factory=_dummy_backend_factory,
    )
    soc = next(s for s in specs if s["name"] == "soc-alert")
    assert soc["skills"] == ["/subagent-skills/soc-alert/"]
    assert len(soc["skills"]) > 0


def test_build_subagent_specs_deep_research_gets_research_tools(monkeypatch):
    """deep-research (standard mode) gets research tools only; email-security keeps its explicit tool list."""
    monkeypatch.setenv("RESEARCH_AGENT_MODE", "standard_agent")
    try:
        specs = official_subagents.build_subagent_specs(
            backend_factory=_dummy_backend_factory,
        )
    finally:
        monkeypatch.delenv("RESEARCH_AGENT_MODE", raising=False)

    spec_map = {s["name"]: s for s in specs}
    dr_tools = spec_map["deep-research"]["tools"]
    em_tools = spec_map["email-security"]["tools"]
    dr_names = {getattr(t, "name", str(t)) for t in dr_tools}
    em_names = {getattr(t, "name", str(t)) for t in em_tools}
    assert "web_search" in dr_names
    assert "extract_iocs" not in dr_names
    # email-security uses an explicit registry tool list (not full common_tools).
    assert "parse_eml" in em_names


def test_email_security_nested_task_middleware_injected():
    specs = official_subagents.build_subagent_specs(
        backend_factory=_dummy_backend_factory,
    )
    spec_map = {s["name"]: s for s in specs}
    email = spec_map["email-security"]
    middleware = email.get("middleware", [])
    nested = [m for m in middleware if isinstance(m, SubAgentMiddleware)]
    assert nested, "email-security should include nested SubAgentMiddleware"


def test_email_security_nested_allowlist_only_binary_analysis():
    specs = official_subagents.build_subagent_specs(
        backend_factory=_dummy_backend_factory,
    )
    spec_map = {s["name"]: s for s in specs}
    email = spec_map["email-security"]
    middleware = email.get("middleware", [])
    nested = [m for m in middleware if isinstance(m, SubAgentMiddleware)]
    assert len(nested) == 1
    child_names = {sub["name"] for sub in nested[0]._subagents}
    assert child_names == {"binary-analysis"}


def test_nested_config_validation_rejects_self_reference():
    cfg = {
        "schema_version": 3,
        "defaults": {"bundles_root": "subagents/official"},
        "subagents": [
            {
                "id": "email-security",
                "enabled": True,
                "source": "official",
                "bundle_path": "email_security",
                "allow_nested_task": True,
                "nested_subagent_allowlist": ["email-security"],
            }
        ],
    }
    try:
        SubagentRegistryFile.model_validate(cfg)
    except ValueError as exc:
        assert "cannot include itself" in str(exc)
    else:
        raise AssertionError("Expected self-reference nested config to fail")


def test_nested_config_validation_rejects_unknown_child():
    cfg = {
        "schema_version": 3,
        "defaults": {"bundles_root": "subagents/official"},
        "subagents": [
            {
                "id": "email-security",
                "enabled": True,
                "source": "official",
                "bundle_path": "email_security",
                "allow_nested_task": True,
                "nested_subagent_allowlist": ["binary-analysis"],
            }
        ],
    }
    try:
        SubagentRegistryFile.model_validate(cfg)
    except ValueError as exc:
        assert "unknown or inactive nested subagent" in str(exc)
    else:
        raise AssertionError("Expected unknown nested child config to fail")
