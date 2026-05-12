"""Official-style skill discovery - frontmatter-only, no full parsing.

Aligns with DeepAgents: SkillsMiddleware loads from backend at runtime.
This module provides minimal metadata (name, description) for:
- Building SubAgent specs (create_deep_agent)
- Validation (task_planner)
- API responses (/health, /agents)

Full SKILL.md content is loaded by SkillsMiddleware when SubAgent runs.
"""

from __future__ import annotations

import logging
import os
import re
from dataclasses import dataclass
from pathlib import Path

import yaml

from app.config.settings import SERVICE_ROOT, get_settings

logger = logging.getLogger(__name__)


@dataclass
class SkillMetadataRef:
    """Lightweight skill metadata for discovery and SubAgent building."""

    name: str
    description: str


@dataclass
class OfficialSkillPackage:
    """One official skill directory under ``SKILLS_DIR`` (``SKILL.md`` + frontmatter)."""

    directory_name: str
    name: str
    description: str
    enabled_for_main_agent: bool = True
    """Set from ``config/main_agent_skills.yaml`` allowlist."""


@dataclass
class MainSkillsRoutePlan:
    """How to mount skills for the main DeepAgent (SkillsMiddleware ``sources``)."""

    middleware_sources: list[str]
    """Virtual paths, e.g. ``["/skills/"]`` or ``["/skills-main/"]``."""

    filtered_dir_names: frozenset[str] | None
    """If set, CompositeBackend exposes ``/skills-main/``: only dirs enabled for the main agent."""


def get_skills_dir() -> Path:
    """Find the skills directory (same logic as legacy loader)."""
    relative_path = Path(__file__).parent.parent.parent.parent / "skills"
    if relative_path.exists():
        return relative_path

    cwd_path = Path.cwd() / "skills"
    if cwd_path.exists():
        return cwd_path

    env_path = os.environ.get("SKILLS_DIR")
    if env_path:
        p = Path(env_path)
        if p.exists():
            return p

    for p in [
        Path("/app/skills"),
        Path("/python-agent-service/skills"),
        Path("./python-agent-service/skills"),
    ]:
        if p.exists():
            return p

    logger.warning("Skills directory not found, using fallback: %s", relative_path)
    return relative_path


SKILLS_DIR = get_skills_dir()


def default_main_agent_skills_config_path() -> Path:
    """Resolved path to ``main_agent_skills.yaml``."""
    settings = get_settings()
    raw = getattr(settings, "main_agent_skills_config_path", None)
    if raw:
        p = Path(raw)
        return p if p.is_absolute() else SERVICE_ROOT / p
    return SERVICE_ROOT / "config" / "main_agent_skills.yaml"


def load_main_agent_skill_allowlist(config_path: Path | None = None) -> frozenset[str] | None:
    """Load directory names the main agent may use under ``SKILLS_DIR``.

    Returns:
        ``None`` if the config file is **missing** → every discovered package is treated as
        enabled for the main agent (dev / container without file).
        A **frozenset** (possibly empty) if the file exists and defines ``main_agent_skill_packages``:
        only those directory names are enabled.
        If the file exists but the key is omitted → ``None`` (same as missing key: all enabled).
    """
    p = config_path or default_main_agent_skills_config_path()
    if not p.is_file():
        return None
    try:
        raw = p.read_text(encoding="utf-8")
        data = yaml.safe_load(raw)
    except (OSError, yaml.YAMLError) as e:
        logger.warning("Invalid main agent skills config %s: %s", p, e)
        return frozenset()
    if not isinstance(data, dict):
        return frozenset()
    listed = data.get("main_agent_skill_packages")
    if listed is None:
        return None
    if not isinstance(listed, list):
        logger.warning("main_agent_skill_packages must be a list in %s", p)
        return frozenset()
    out: list[str] = []
    for x in listed:
        s = str(x).strip()
        if s and s not in {".", ".."}:
            out.append(s)
    return frozenset(out)


def _parse_frontmatter(content: str) -> dict:
    """Parse YAML frontmatter from SKILL.md content."""
    match = re.match(r"^---\s*\n(.*?)\n---\s*\n", content, re.DOTALL)
    if not match:
        return {}
    try:
        data = yaml.safe_load(match.group(1))
        return data if isinstance(data, dict) else {}
    except yaml.YAMLError:
        return {}


def discover_official_skill_packages(
    skills_dir: Path | None = None,
    *,
    main_agent_skills_config_path: Path | None = None,
) -> list[OfficialSkillPackage]:
    """Discover packages under ``skills_dir`` (directories containing ``SKILL.md``).

    ``enabled_for_main_agent`` comes from ``config/main_agent_skills.yaml``
    (``main_agent_skill_packages``). If that file is missing, or the key is omitted, all
    discovered packages are enabled for the main agent.
    """
    base = skills_dir or SKILLS_DIR
    if not base.exists():
        logger.warning("Skills directory does not exist: %s", base)
        return []

    allowlist = load_main_agent_skill_allowlist(main_agent_skills_config_path)

    result: list[OfficialSkillPackage] = []
    for item in base.iterdir():
        if not item.is_dir():
            continue
        skill_md = item / "SKILL.md"
        if not skill_md.is_file():
            continue
        try:
            content = skill_md.read_text(encoding="utf-8")
            fm = _parse_frontmatter(content)
            name = str(fm.get("name", item.name)).strip()
            desc = str(fm.get("description", "")).strip()
            if not name:
                name = item.name
            if not desc:
                desc = f"Skill: {name}"
            if allowlist is None:
                enabled_main = True
            else:
                enabled_main = item.name in allowlist
            result.append(
                OfficialSkillPackage(
                    directory_name=item.name,
                    name=name,
                    description=desc,
                    enabled_for_main_agent=enabled_main,
                )
            )
        except Exception as e:
            logger.warning("Failed to parse %s: %s", skill_md, e)
    return result


def discover_bundle_skill_packages(bundle_dir: Path) -> list[OfficialSkillPackage]:
    """Discover skills under ``<bundle_dir>/skills/<package>/SKILL.md`` (subagent bundle-local).

    Same frontmatter rules as global packages; ``enabled_for_main_agent`` is always ``True``
    here because the field is N/A for bundle-only listings (UI/catalog use).
    """
    skills_root = bundle_dir / "skills"
    if not skills_root.is_dir():
        return []

    result: list[OfficialSkillPackage] = []
    for item in sorted(skills_root.iterdir(), key=lambda p: p.name):
        if not item.is_dir():
            continue
        skill_md = item / "SKILL.md"
        if not skill_md.is_file():
            continue
        try:
            content = skill_md.read_text(encoding="utf-8")
            fm = _parse_frontmatter(content)
            name = str(fm.get("name", item.name)).strip()
            desc = str(fm.get("description", "")).strip()
            if not name:
                name = item.name
            if not desc:
                desc = f"Skill: {name}"
            result.append(
                OfficialSkillPackage(
                    directory_name=item.name,
                    name=name,
                    description=desc,
                    enabled_for_main_agent=True,
                )
            )
        except OSError as e:
            logger.warning("Failed to read bundle skill %s: %s", skill_md, e)
        except Exception as e:
            logger.warning("Failed to parse bundle skill %s: %s", skill_md, e)
    return result


def discover_skill_metadata(
    skills_dir: Path | None = None,
) -> list[SkillMetadataRef]:
    """Discover skills: parse frontmatter only (name, description).

    Full catalog under ``skills_dir``. Main-agent exposure is still driven by
    ``config/main_agent_skills.yaml`` on each ``discover_official_skill_packages`` call.
    """
    return [
        SkillMetadataRef(name=p.name, description=p.description)
        for p in discover_official_skill_packages(skills_dir)
    ]


def resolve_main_skills_route_plan(
    skills_dir: Path | None = None,
    *,
    main_agent_skills_config_path: Path | None = None,
) -> MainSkillsRoutePlan:
    """Main agent: global skill dirs allowed by ``config/main_agent_skills.yaml``."""
    base = skills_dir or SKILLS_DIR
    if not base.exists():
        return MainSkillsRoutePlan([], None)
    packages = discover_official_skill_packages(
        base, main_agent_skills_config_path=main_agent_skills_config_path
    )
    if not packages:
        return MainSkillsRoutePlan([], None)
    visible = [p for p in packages if p.enabled_for_main_agent]
    if not visible:
        return MainSkillsRoutePlan([], None)
    all_dirs = frozenset(p.directory_name for p in packages)
    vis_dirs = frozenset(p.directory_name for p in visible)
    if vis_dirs == all_dirs:
        return MainSkillsRoutePlan(["/skills/"], None)
    return MainSkillsRoutePlan(["/skills-main/"], vis_dirs)


def get_skill_metadata(
    name: str, skills_dir: Path | None = None
) -> SkillMetadataRef | None:
    """Get metadata for a single skill by name."""
    base = skills_dir or SKILLS_DIR
    skill_dir = base / name
    skill_md = skill_dir / "SKILL.md"
    if not skill_md.exists():
        return None
    try:
        content = skill_md.read_text(encoding="utf-8")
        fm = _parse_frontmatter(content)
        n = str(fm.get("name", name)).strip() or name
        d = str(fm.get("description", "")).strip() or f"Skill: {n}"
        return SkillMetadataRef(name=n, description=d)
    except Exception:
        return None
