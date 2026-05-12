"""Registry-backed JSON for workspace catalog pages (subagents + skills)."""

from __future__ import annotations

from typing import Any

from app.agents.subagent_registry import (
    load_subagent_registry_file,
    merge_task_catalog_description,
)
from app.config.settings import SERVICE_ROOT
from app.prompts.skills.discovery import (
    OfficialSkillPackage,
    discover_bundle_skill_packages,
    discover_official_skill_packages,
)


def _package_to_skill_dict(p: OfficialSkillPackage, *, include_main_flag: bool) -> dict[str, Any]:
    out: dict[str, Any] = {
        "directory_name": p.directory_name,
        "name": p.name,
        "description": p.description,
    }
    if include_main_flag:
        out["enabled_for_main_agent"] = p.enabled_for_main_agent
    return out


def build_subagents_catalog() -> dict[str, Any]:
    """Official enabled subagents from ``subagents.registry.yaml`` + bundle/global skill metadata."""
    reg = load_subagent_registry_file()
    bundles_root = (SERVICE_ROOT / reg.defaults.bundles_root).resolve()
    global_packages = discover_official_skill_packages()
    by_dir: dict[str, OfficialSkillPackage] = {p.directory_name: p for p in global_packages}

    rows: list[dict[str, Any]] = []
    for row in reg.subagents:
        if not row.enabled or row.source != "official":
            continue
        bundle = (bundles_root / row.bundle_path).resolve()
        purpose = merge_task_catalog_description(row.description, row.routing_hints)
        bundle_skills = discover_bundle_skill_packages(bundle)

        attached: list[OfficialSkillPackage] = []
        if row.include_shared_skills:
            attached = list(global_packages)
        else:
            for pid in row.extra_skill_package_ids:
                pkg = by_dir.get(str(pid).strip())
                if pkg is not None:
                    attached.append(pkg)

        attached.sort(key=lambda p: p.directory_name)
        bundle_skills_sorted = sorted(bundle_skills, key=lambda p: p.directory_name)

        rows.append(
            {
                "id": row.id,
                "purpose": purpose,
                "runtime": row.runtime,
                "tool_profile": row.tool_profile,
                "include_shared_skills": row.include_shared_skills,
                "extra_skill_package_ids": list(row.extra_skill_package_ids),
                "bundle_skills": [
                    _package_to_skill_dict(p, include_main_flag=False) for p in bundle_skills_sorted
                ],
                "attached_global_skills": [
                    _package_to_skill_dict(p, include_main_flag=True) for p in attached
                ],
            }
        )

    rows.sort(key=lambda r: r["id"])
    return {"subagents": rows}


def build_global_skills_catalog() -> dict[str, Any]:
    """All official skill packages under the global ``skills/`` directory."""
    packages = discover_official_skill_packages()
    sorted_pkgs = sorted(packages, key=lambda p: p.directory_name)
    return {
        "skills": [_package_to_skill_dict(p, include_main_flag=True) for p in sorted_pkgs],
    }
