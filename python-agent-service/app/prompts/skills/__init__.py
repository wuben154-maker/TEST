"""Security Analysis Skills - Official DeepAgents Pattern.

Uses lightweight discovery (frontmatter only). SkillsMiddleware loads full
SKILL.md from backend at runtime. No pre-parsing of SKILL.md body.
"""

from pathlib import Path

from .base import (
    SkillSpec,
    SkillMetadata,
    SkillInstructions,
    SkillRegistry,
    WorkflowStep,
    create_skill,
)
from .discovery import (
    SKILLS_DIR,
    SkillMetadataRef,
    discover_skill_metadata,
    get_skill_metadata,
)


# ============================================================================
# OFFICIAL-STYLE REGISTRY (discovery-based)
# ============================================================================

class UnifiedSkillRegistry:
    """Thin registry using discovery - no full SKILL.md parsing.

    Provides list_skills(), get() for compatibility with task_planner,
    main.py, and health APIs. Returns SkillMetadataRef or minimal
    SkillSpec for legacy consumers.
    """

    def __init__(self, skills_dir: Path | None = None):
        self._skills_dir = skills_dir or SKILLS_DIR
        self._cache: list[SkillMetadataRef] = []

    def _refresh(self) -> None:
        self._cache = discover_skill_metadata(self._skills_dir)

    def load_from_filesystem(self) -> int:
        """Load skills from filesystem (alias for compatibility)."""
        self._refresh()
        return len(self._cache)

    def reload(self) -> None:
        """Reload skills from filesystem."""
        self._cache = []
        self._refresh()

    def list_skills(self) -> list[SkillMetadataRef]:
        """List discovered skills (metadata only)."""
        if not self._cache:
            self._refresh()
        return list(self._cache)

    def get(self, name: str) -> SkillMetadataRef | None:
        """Get skill metadata by name."""
        for s in self.list_skills():
            if s.name == name:
                return s
        return None

    def get_summaries(self) -> list[str]:
        return [f"{s.name}: {s.description}" for s in self.list_skills()]


_registry: UnifiedSkillRegistry | None = None


def _ensure_initialized() -> UnifiedSkillRegistry:
    global _registry
    if _registry is None:
        import logging
        logger = logging.getLogger(__name__)
        _registry = UnifiedSkillRegistry()
        skills = _registry.list_skills()
        logger.info("Skill registry (official mode) initialized: %d skills from %s",
                    len(skills), _registry._skills_dir)
    return _registry


def get_skill_registry() -> UnifiedSkillRegistry:
    """Get the skill registry (discovery-based, official mode)."""
    return _ensure_initialized()


def reload_skills() -> int:
    """Reload skills from filesystem."""
    global _registry
    _registry = None
    return len(_ensure_initialized().list_skills())


# ============================================================================
# COMPATIBILITY
# ============================================================================

INPUT_TYPE_TO_SKILL = {
    "email": "email-security",
    "binary": "binary-analysis",
    "web": "web-security",
    "soc_alert": "soc-alert",
    "vuln_scan": "vuln-scan",
    "generic": "general-security",
    "research": "deep-research",
    "topic": "deep-research",
}


def get_all_skills() -> list[SkillMetadataRef]:
    """Get all discovered skills."""
    return _ensure_initialized().list_skills()


def list_skill_summaries() -> list[str]:
    """List lightweight skill summaries."""
    return _ensure_initialized().get_summaries()


def get_skill(name: str) -> SkillMetadataRef | None:
    """Get skill by name."""
    return _ensure_initialized().get(name)


def find_skill_for_query(query: str) -> SkillSpec | None:
    """Find best-matching skill by keyword in description. Returns SkillSpec for legacy compat."""
    query_lower = query.lower()
    best = None
    for s in _ensure_initialized().list_skills():
        if query_lower in s.description.lower():
            best = s
            break
    ref = best or _ensure_initialized().get("general-security") or SkillMetadataRef(
        name="general-security", description="General security analysis"
    )
    return _metadata_to_skill_spec(ref)


def find_skills_by_tag(tag: str) -> list[SkillMetadataRef]:
    """Find skills by tag (tags not in discovery - returns empty)."""
    return []


def get_skill_for_input_type(input_type: str) -> SkillSpec | None:
    """Get skill for input type. Returns SkillSpec for legacy compat."""
    skill_name = INPUT_TYPE_TO_SKILL.get(input_type, "general-security")
    ref = _ensure_initialized().get(skill_name) or SkillMetadataRef(
        name=skill_name, description=f"Skill: {skill_name}"
    )
    return _metadata_to_skill_spec(ref)


def get_skills_info() -> dict:
    """Get skill loading info for /health."""
    r = _ensure_initialized()
    return {
        "total": len(r.list_skills()),
        "skills": [s.name for s in r.list_skills()],
        "skills_dir": str(r._skills_dir),
        "skills_dir_exists": r._skills_dir.exists(),
        "mode": "official",  # discovery-based, no full parsing
    }


# ============================================================================
# BACKWARD COMPATIBILITY (lazy skill constants / SkillSpec shims)
# ============================================================================

def _metadata_to_skill_spec(ref: SkillMetadataRef) -> SkillSpec:
    """Build minimal SkillSpec for legacy consumers."""
    return create_skill(
        name=ref.name,
        display_name=ref.name.replace("-", " ").title(),
        description=ref.description,
        system_prompt="You are a specialized analyst. Read SKILL.md for instructions when needed.",
        triggers=[ref.name.split("-")[0]],
        tags=["security"],
    )


def __getattr__(name: str):
    """Lazy-load legacy skill constants and deprecated loader exports."""
    if name in ("discover_skills", "load_skill_from_file"):
        from . import loader
        return getattr(loader, name)
    _DEFS = {
        "EMAIL_SECURITY_SKILL": ("email-security", "Analyze email headers, detect phishing"),
        "BINARY_ANALYSIS_SKILL": ("binary-analysis", "Analyze binary files, detect malware"),
        "WEB_SECURITY_SKILL": ("web-security", "Detect web vulnerabilities"),
        "SOC_ALERT_SKILL": ("soc-alert", "Triage SOC/SIEM alerts"),
        "VULN_SCAN_SKILL": ("vuln-scan", "Analyze vulnerability scan results"),
        "GENERAL_SECURITY_SKILL": ("general-security", "General security analysis"),
        "DEEP_RESEARCH_SKILL": ("deep-research", "Comprehensive research"),
    }
    if name in _DEFS:
        skill_name, desc = _DEFS[name]
        ref = get_skill(skill_name) or SkillMetadataRef(name=skill_name, description=desc)
        return _metadata_to_skill_spec(ref)
    if name == "SKILL_REGISTRY":
        return _ensure_initialized()
    if name == "SECURITY_SKILLS":
        return [_metadata_to_skill_spec(s) for s in get_all_skills()]
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")


__all__ = [
    "SkillSpec",
    "SkillMetadata",
    "SkillInstructions",
    "SkillRegistry",
    "WorkflowStep",
    "create_skill",
    "SkillMetadataRef",
    "discover_skill_metadata",
    "get_skill_registry",
    "get_all_skills",
    "reload_skills",
    "list_skill_summaries",
    "get_skill",
    "find_skill_for_query",
    "find_skills_by_tag",
    "get_skill_for_input_type",
    "get_skills_info",
    "INPUT_TYPE_TO_SKILL",
    "SKILLS_DIR",
]
