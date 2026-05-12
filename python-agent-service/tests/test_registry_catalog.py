"""Registry catalog endpoints — subagent + global skill listings for workspace UI."""

from app.catalog.registry_catalog import build_global_skills_catalog, build_subagents_catalog


def test_build_subagents_catalog_structure():
    data = build_subagents_catalog()
    assert "subagents" in data
    assert isinstance(data["subagents"], list)
    assert len(data["subagents"]) >= 1
    first = data["subagents"][0]
    assert "id" in first
    assert "purpose" in first
    assert "runtime" in first
    assert "tool_profile" in first
    assert "include_shared_skills" in first
    assert "extra_skill_package_ids" in first
    assert "bundle_skills" in first
    assert "attached_global_skills" in first
    assert isinstance(first["bundle_skills"], list)
    assert isinstance(first["attached_global_skills"], list)


def test_build_global_skills_catalog_structure():
    data = build_global_skills_catalog()
    assert "skills" in data
    assert isinstance(data["skills"], list)
    if data["skills"]:
        s0 = data["skills"][0]
        assert "directory_name" in s0
        assert "name" in s0
        assert "description" in s0
        assert "enabled_for_main_agent" in s0
