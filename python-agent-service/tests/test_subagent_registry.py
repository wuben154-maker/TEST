"""Tests for YAML subagent registry and skill_source."""

from __future__ import annotations

from pathlib import Path

import pytest
import yaml

from app.agents.skill_source import OfficialSkillSource
from app.agents.subagent_registry import (
    SubagentRegistryFile,
    build_subagent_specs_from_registry,
    build_tool_profiles,
    bundle_skills_has_packages,
    compute_skill_backend_routes,
    load_subagent_registry_file,
    merge_task_catalog_description,
    resolve_skills_middleware_sources,
)
from app.prompts.skills.discovery import (
    discover_official_skill_packages,
    discover_skill_metadata,
    load_main_agent_skill_allowlist,
    resolve_main_skills_route_plan,
)


def test_load_main_agent_skill_allowlist_missing_file_returns_none(tmp_path: Path):
    missing = tmp_path / "nope.yaml"
    assert load_main_agent_skill_allowlist(missing) is None


def test_discover_all_enabled_when_allowlist_config_missing(tmp_path: Path):
    skills = tmp_path / "skills"
    skills.mkdir()
    (skills / "a").mkdir()
    (skills / "a" / "SKILL.md").write_text("---\nname: a\n---\n", encoding="utf-8")
    cfg = tmp_path / "missing.yaml"
    pkgs = discover_official_skill_packages(skills, main_agent_skills_config_path=cfg)
    assert len(pkgs) == 1
    assert pkgs[0].enabled_for_main_agent is True


def test_merge_task_catalog_description():
    assert "foo" in merge_task_catalog_description("foo", "bar")
    assert merge_task_catalog_description("", "hint") == "hint"


def test_official_skill_source_tenant_empty():
    src = OfficialSkillSource()
    assert src.list_for_tenant("any") == []


def test_official_skill_source_list_official_matches_discover():
    src = OfficialSkillSource()
    direct = discover_skill_metadata()
    via = src.list_official()
    assert {x.name for x in via} == {x.name for x in direct}


def test_build_specs_from_shipped_registry():
    specs = build_subagent_specs_from_registry(
        backend_factory=lambda _rt: object()
    )
    names = []
    for s in specs:
        names.append(s.get("name"))
    assert set(names) == {
        "binary-analysis",
        "email-security",
        "web-security",
        "soc-alert",
        "deep-research",
    }
    dr = next(x for x in specs if x.get("name") == "deep-research")
    assert "runnable" in dr
    soc = next(x for x in specs if x.get("name") == "soc-alert")
    assert "runnable" not in soc
    assert soc.get("skills")
    assert "/subagent-skills/soc-alert/" in soc.get("skills")


def test_user_source_skipped(tmp_path: Path, monkeypatch):
    reg_path = tmp_path / "reg.yaml"
    reg_path.write_text(
        yaml.dump(
            {
                "schema_version": 2,
                "defaults": {"bundles_root": "bundles"},
                "subagents": [
                    {
                        "id": "x-agent",
                        "enabled": True,
                        "source": "user",
                        "bundle_path": "x",
                        "description": "User agent",
                        "tool_profile": "default",
                        "runtime": "standard",
                    }
                ],
            }
        ),
        encoding="utf-8",
    )
    (tmp_path / "bundles").mkdir()
    # No bundle for x — should not be reached because user is skipped
    specs = build_subagent_specs_from_registry(reg_path)
    assert specs == []


def test_disabled_subagent_excluded(tmp_path: Path):
    bundles = tmp_path / "official"
    bundles.mkdir()
    b = bundles / "only"
    b.mkdir()
    (b / "AGENT.md").write_text("Body\n", encoding="utf-8")
    reg_path = tmp_path / "reg.yaml"
    reg_path.write_text(
        yaml.dump(
            {
                "schema_version": 2,
                "defaults": {"bundles_root": str(bundles)},
                "subagents": [
                    {
                        "id": "only",
                        "enabled": False,
                        "source": "official",
                        "bundle_path": "only",
                        "description": "Off",
                        "tool_profile": "default",
                        "runtime": "standard",
                    }
                ],
            }
        ),
        encoding="utf-8",
    )
    specs = build_subagent_specs_from_registry(reg_path)
    assert specs == []


def test_missing_bundle_raises(tmp_path: Path):
    reg_path = tmp_path / "reg.yaml"
    reg_path.write_text(
        yaml.dump(
            {
                "schema_version": 2,
                "defaults": {"bundles_root": str(tmp_path / "missing_root")},
                "subagents": [
                    {
                        "id": "nope",
                        "enabled": True,
                        "source": "official",
                        "bundle_path": "nope",
                        "description": "x",
                        "tool_profile": "default",
                        "runtime": "standard",
                    }
                ],
            }
        ),
        encoding="utf-8",
    )
    with pytest.raises(FileNotFoundError):
        build_subagent_specs_from_registry(reg_path)


def test_duplicate_ids_invalid():
    with pytest.raises(ValueError, match="Duplicate"):
        SubagentRegistryFile.model_validate(
            {
                "schema_version": 2,
                "subagents": [
                    {
                        "id": "a",
                        "enabled": True,
                        "source": "official",
                        "bundle_path": "a",
                        "description": "d",
                        "tool_profile": "default",
                        "runtime": "standard",
                    },
                    {
                        "id": "a",
                        "enabled": True,
                        "source": "official",
                        "bundle_path": "b",
                        "description": "d",
                        "tool_profile": "default",
                        "runtime": "standard",
                    },
                ],
            }
        )


def test_load_subagent_registry_file_missing(tmp_path: Path):
    missing = tmp_path / "nope.yaml"
    with pytest.raises(FileNotFoundError):
        load_subagent_registry_file(missing)


def test_discover_official_skill_package_allowlist_from_config(tmp_path: Path):
    skills = tmp_path / "skills"
    skills.mkdir()
    for name in ("in-list", "not-in-list"):
        d = skills / name
        d.mkdir()
        (d / "SKILL.md").write_text(
            f"---\nname: {name}\ndescription: x\n---\n",
            encoding="utf-8",
        )
    cfg = tmp_path / "main_agent_skills.yaml"
    cfg.write_text(
        "schema_version: 1\nmain_agent_skill_packages:\n  - in-list\n",
        encoding="utf-8",
    )
    pkgs = discover_official_skill_packages(
        skills, main_agent_skills_config_path=cfg
    )
    by_dir = {p.directory_name: p for p in pkgs}
    assert by_dir["in-list"].enabled_for_main_agent is True
    assert by_dir["not-in-list"].enabled_for_main_agent is False


def test_resolve_main_skills_route_plan_filtered_when_partial_main(tmp_path: Path):
    skills = tmp_path / "skills"
    skills.mkdir()
    for name in ("on-main", "off-main"):
        d = skills / name
        d.mkdir()
        body = "---\nname: " + name + "\ndescription: x\n---\n"
        (d / "SKILL.md").write_text(body, encoding="utf-8")
    cfg = tmp_path / "main_agent_skills.yaml"
    cfg.write_text(
        "schema_version: 1\nmain_agent_skill_packages:\n  - on-main\n",
        encoding="utf-8",
    )
    plan = resolve_main_skills_route_plan(
        skills, main_agent_skills_config_path=cfg
    )
    assert plan.middleware_sources == ["/skills-main/"]
    assert plan.filtered_dir_names == frozenset({"on-main"})


def test_resolve_skills_middleware_sources_bundle_and_shared(tmp_path: Path, monkeypatch):
    bundle = tmp_path / "b"
    (bundle / "skills" / "local-skill").mkdir(parents=True)
    (bundle / "skills" / "local-skill" / "SKILL.md").write_text(
        "---\nname: local\n---\n", encoding="utf-8"
    )
    gskills = tmp_path / "global_skills"
    gskills.mkdir()
    (gskills / "email-security").mkdir()
    (gskills / "email-security" / "SKILL.md").write_text(
        "---\nname: email-security\n---\n", encoding="utf-8"
    )
    monkeypatch.setattr(
        "app.agents.subagent_registry.SKILLS_DIR",
        gskills,
        raising=False,
    )
    src = resolve_skills_middleware_sources(
        "email-security",
        bundle,
        True,
        [],
    )
    assert "/skills/" in src
    assert "/subagent-skills/email-security/" in src
    assert src.index("/skills/") < src.index("/subagent-skills/email-security/")


def test_compute_skill_backend_routes_includes_bundle_prefix(tmp_path: Path, monkeypatch):
    bundles = tmp_path / "official"
    b = bundles / "only"
    (b / "skills" / "x").mkdir(parents=True)
    (b / "skills" / "x" / "SKILL.md").write_text("---\nname: x\n---\n", encoding="utf-8")
    (b / "AGENT.md").write_text("Body\n", encoding="utf-8")
    reg_path = tmp_path / "reg.yaml"
    reg_path.write_text(
        yaml.dump(
            {
                "schema_version": 2,
                "defaults": {"bundles_root": str(bundles)},
                "subagents": [
                    {
                        "id": "only",
                        "enabled": True,
                        "source": "official",
                        "bundle_path": "only",
                        "description": "d",
                        "tool_profile": "default",
                        "runtime": "standard",
                    }
                ],
            }
        ),
        encoding="utf-8",
    )
    routes = compute_skill_backend_routes(reg_path)
    assert "/subagent-skills/only/" in routes["bundle"]
    assert routes["bundle"]["/subagent-skills/only/"].endswith("skills")


def test_bundle_skills_has_packages_false_for_readme_only(tmp_path: Path):
    root = tmp_path / "skills"
    root.mkdir()
    (root / "README.md").write_text("x", encoding="utf-8")
    assert bundle_skills_has_packages(root) is False


def test_resolve_skills_middleware_sources_subset_without_shared(tmp_path: Path, monkeypatch):
    bundle = tmp_path / "b"
    bundle.mkdir()
    gskills = tmp_path / "g"
    (gskills / "email-security").mkdir(parents=True)
    (gskills / "email-security" / "SKILL.md").write_text(
        "---\nname: email-security\n---\n", encoding="utf-8"
    )
    monkeypatch.setattr(
        "app.agents.subagent_registry.SKILLS_DIR",
        gskills,
        raising=False,
    )
    src = resolve_skills_middleware_sources(
        "x-agent",
        bundle,
        False,
        ["email-security"],
    )
    assert src == ["/skills-subset/x-agent/"]


def test_compute_skill_backend_routes_includes_subset(tmp_path: Path, monkeypatch):
    bundles = tmp_path / "official"
    b = bundles / "x-agent"
    b.mkdir(parents=True)
    (b / "AGENT.md").write_text("Body\n", encoding="utf-8")
    gskills = tmp_path / "g"
    (gskills / "email-security").mkdir(parents=True)
    (gskills / "email-security" / "SKILL.md").write_text(
        "---\nname: email-security\n---\n", encoding="utf-8"
    )
    monkeypatch.setattr(
        "app.agents.subagent_registry.SKILLS_DIR",
        gskills,
        raising=False,
    )
    reg_path = tmp_path / "reg.yaml"
    reg_path.write_text(
        yaml.dump(
            {
                "schema_version": 2,
                "defaults": {"bundles_root": str(bundles)},
                "subagents": [
                    {
                        "id": "x-agent",
                        "enabled": True,
                        "source": "official",
                        "bundle_path": "x-agent",
                        "description": "d",
                        "tool_profile": "default",
                        "runtime": "standard",
                        "include_shared_skills": False,
                        "extra_skill_package_ids": ["email-security"],
                    }
                ],
            }
        ),
        encoding="utf-8",
    )
    routes = compute_skill_backend_routes(reg_path)
    assert "/skills-subset/x-agent/" in routes["subset"]
    assert "email-security" in routes["subset"]["/skills-subset/x-agent/"]


def test_build_tool_profiles_soc_alert_api_profile_not_polluting_default():
    profiles = build_tool_profiles()
    default_names = {getattr(t, "name", str(t)) for t in profiles["default"]}
    soc_names = {getattr(t, "name", str(t)) for t in profiles["soc-alert-api"]}
    assert "soc_vt_file_query" in soc_names
    assert "execute_soc_solve_plan" in soc_names
    assert "soc_vt_file_query" not in default_names


def test_explicit_tools_override_tool_profile(tmp_path: Path):
    bundles = tmp_path / "official"
    b = bundles / "x-agent"
    b.mkdir(parents=True)
    (b / "AGENT.md").write_text("Body\n", encoding="utf-8")
    reg_path = tmp_path / "reg.yaml"
    reg_path.write_text(
        yaml.dump(
            {
                "schema_version": 2,
                "defaults": {"bundles_root": str(bundles)},
                "subagents": [
                    {
                        "id": "x-agent",
                        "enabled": True,
                        "source": "official",
                        "bundle_path": "x-agent",
                        "description": "d",
                        "tool_profile": "default",
                        "tools": ["summarize_content", "web_search"],
                        "runtime": "standard",
                    }
                ],
            }
        ),
        encoding="utf-8",
    )
    specs = build_subagent_specs_from_registry(reg_path)
    x = next(s for s in specs if s.get("name") == "x-agent")
    assert [t.name for t in x["tools"]] == ["summarize_content", "web_search"]


def test_explicit_tools_unknown_name_raises(tmp_path: Path):
    bundles = tmp_path / "official"
    b = bundles / "x-agent"
    b.mkdir(parents=True)
    (b / "AGENT.md").write_text("Body\n", encoding="utf-8")
    reg_path = tmp_path / "reg.yaml"
    reg_path.write_text(
        yaml.dump(
            {
                "schema_version": 2,
                "defaults": {"bundles_root": str(bundles)},
                "subagents": [
                    {
                        "id": "x-agent",
                        "enabled": True,
                        "source": "official",
                        "bundle_path": "x-agent",
                        "description": "d",
                        "tools": ["not_a_real_tool"],
                        "runtime": "standard",
                    }
                ],
            }
        ),
        encoding="utf-8",
    )
    with pytest.raises(ValueError, match="Unknown tool"):
        build_subagent_specs_from_registry(reg_path)


def test_structured_tools_required_binding_without_backend_fails(tmp_path: Path):
    bundles = tmp_path / "official"
    b = bundles / "email-security"
    b.mkdir(parents=True)
    (b / "AGENT.md").write_text("Body\n", encoding="utf-8")
    reg_path = tmp_path / "reg.yaml"
    reg_path.write_text(
        yaml.dump(
            {
                "schema_version": 3,
                "defaults": {"bundles_root": str(bundles)},
                "subagents": [
                    {
                        "id": "email-security",
                        "enabled": True,
                        "source": "official",
                        "bundle_path": "email-security",
                        "description": "d",
                        "tools": [
                            {
                                "name": "parse_eml",
                                "backend_binding": "required",
                            }
                        ],
                        "runtime": "standard",
                    }
                ],
            }
        ),
        encoding="utf-8",
    )
    with pytest.raises(RuntimeError, match="requires backend binding"):
        build_subagent_specs_from_registry(reg_path)


def test_structured_tools_email_provider_with_backend_succeeds(tmp_path: Path):
    bundles = tmp_path / "official"
    b = bundles / "email-security"
    b.mkdir(parents=True)
    (b / "AGENT.md").write_text("Body\n", encoding="utf-8")
    reg_path = tmp_path / "reg.yaml"
    reg_path.write_text(
        yaml.dump(
            {
                "schema_version": 3,
                "defaults": {"bundles_root": str(bundles)},
                "subagents": [
                    {
                        "id": "email-security",
                        "enabled": True,
                        "source": "official",
                        "bundle_path": "email-security",
                        "description": "d",
                        "tools": [
                            {
                                "name": "parse_eml",
                                "provider": "email_security",
                                "backend_binding": "required",
                            },
                            {
                                "name": "compute_risk_score",
                                "provider": "email_security",
                                "backend_binding": "none",
                            },
                        ],
                        "runtime": "standard",
                    }
                ],
            }
        ),
        encoding="utf-8",
    )
    specs = build_subagent_specs_from_registry(
        reg_path,
        backend_factory=lambda _rt: object(),
    )
    email = next(x for x in specs if x.get("name") == "email-security")
    assert [t.name for t in email["tools"]] == ["parse_eml", "compute_risk_score"]


def test_structured_tools_email_provider_unknown_symbol_raises(tmp_path: Path):
    bundles = tmp_path / "official"
    b = bundles / "email-security"
    b.mkdir(parents=True)
    (b / "AGENT.md").write_text("Body\n", encoding="utf-8")
    reg_path = tmp_path / "reg.yaml"
    reg_path.write_text(
        yaml.dump(
            {
                "schema_version": 3,
                "defaults": {"bundles_root": str(bundles)},
                "subagents": [
                    {
                        "id": "email-security",
                        "enabled": True,
                        "source": "official",
                        "bundle_path": "email-security",
                        "description": "d",
                        "tools": [
                            {
                                "name": "not_exported_email_tool",
                                "provider": "email_security",
                                "backend_binding": "none",
                            }
                        ],
                        "runtime": "standard",
                    }
                ],
            }
        ),
        encoding="utf-8",
    )
    with pytest.raises(ValueError, match="not exported"):
        build_subagent_specs_from_registry(reg_path)


def test_security_report_mermaid_skill_bundle_shipped():
    """Global skill with upstream references + LICENSE for Apache-2.0 redistribution."""
    svc_root = Path(__file__).resolve().parents[1]
    root = svc_root / "skills" / "security-report-mermaid"
    assert (root / "SKILL.md").is_file()
    assert (root / "LICENSE").is_file()
    assert (root / "NOTICE.txt").is_file()
    assert (root / "references" / "mermaid_style_guide.md").is_file()
    assert (root / "references" / "diagrams" / "flowchart.md").is_file()
    assert (root / "templates" / "status_report.md").is_file()
    cfg = svc_root / "config" / "main_agent_skills.yaml"
    raw_cfg = cfg.read_text(encoding="utf-8")
    assert "security-report-mermaid" in raw_cfg

