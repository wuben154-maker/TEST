"""Bundle-level checks for official binary-analysis subagent (registry wiring)."""

from __future__ import annotations

from app.agents.subagent_registry import build_subagent_specs_from_registry
from subagents.official.binary_analysis.registry import (
    REGISTRY_TOOL_ORDER,
    build_subagent_tool_map,
)


def test_build_subagent_tool_map_canonical_order():
    m = build_subagent_tool_map(backend_factory=lambda _rt: object())
    assert list(m.keys()) == list(REGISTRY_TOOL_ORDER)


def test_shipped_registry_binary_analysis_resolves_private_tools():
    specs = build_subagent_specs_from_registry(
        backend_factory=lambda _rt: object(),
    )
    ba = next(s for s in specs if s.get("name") == "binary-analysis")
    assert [t.name for t in ba["tools"]] == list(REGISTRY_TOOL_ORDER)
    assert "/subagent-skills/binary-analysis/" in ba.get("skills", [])


def test_registry_file_identify_sandbox_client_matches_factory(monkeypatch):
    """Registry tools must use the same factory as CLI / LangGraph (subprocess branch)."""
    monkeypatch.setenv("BINARY_ANALYSIS_USE_E2B", "false")
    monkeypatch.delenv("E2B_API_KEY", raising=False)
    import subagents.official.binary_analysis  # noqa: F401 — prepends bundle to sys.path

    from config import settings
    from sandbox.factory import build_binary_sandbox_client
    from subagents.official.binary_analysis.registry import build_subagent_tool_map

    settings.cache_clear()
    try:
        factory_client = build_binary_sandbox_client()
        mapped = build_subagent_tool_map()["file_identify"].sandbox_client
        assert type(mapped) is type(factory_client)
    finally:
        settings.cache_clear()


def test_registry_file_identify_e2b_branch_matches_factory(monkeypatch):
    monkeypatch.setenv("BINARY_ANALYSIS_USE_E2B", "true")
    monkeypatch.setenv("E2B_API_KEY", "dummy-key-for-registry-tests")
    import subagents.official.binary_analysis  # noqa: F401

    from config import settings
    from sandbox.factory import build_binary_sandbox_client
    from subagents.official.binary_analysis.registry import build_subagent_tool_map

    settings.cache_clear()
    try:
        factory_client = build_binary_sandbox_client()
        mapped = build_subagent_tool_map()["file_identify"].sandbox_client
        assert type(mapped) is type(factory_client)
    finally:
        settings.cache_clear()
