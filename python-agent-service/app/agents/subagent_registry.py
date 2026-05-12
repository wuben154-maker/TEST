"""YAML-driven subagent registry: official bundles, tool profiles, compiled builders."""

from __future__ import annotations

import logging
import os
from pathlib import Path
from typing import Any, Callable, Literal, cast

from app.prompts.skills.discovery import SKILLS_DIR
from app.prompts.subagent_output_appendix import SUBAGENT_OUTPUT_APPENDIX

import yaml
from pydantic import BaseModel, Field, model_validator
from typing_extensions import Self

from app.config.settings import SERVICE_ROOT, get_settings

logger = logging.getLogger(__name__)

SUBAGENT_BASE_PROMPT_FALLBACK = """You are a specialized security/research analyst.
You have access to a skills library.

**How to use skills:**
1. Check the skill list in your system message for available skills and paths.
2. When a task matches a skill, read SKILL.md at the path shown (use read_file).
3. Follow instructions in SKILL.md for workflows, best practices, tool usage.
4. Use execute to run helper scripts in the skill directory if instructed.

Be thorough and follow the skill's guidance when it applies."""

TOOL_PROFILE_DEFAULT = "default"
TOOL_PROFILE_EMAIL = "email-security"
TOOL_PROFILE_WEB = "web-security"
TOOL_PROFILE_DEEP_RESEARCH = "deep-research"
TOOL_PROFILE_SOC_ALERT_API = "soc-alert-api"
# Injected into email-security AGENT.md via __BUDGET__ placeholder (~8 + 2*N_attachments + buffer).
EMAIL_SECURITY_TOOL_CALL_BUDGET = 50
SUPPORTED_REGISTRY_SCHEMA_VERSIONS = frozenset({2, 3})
BackendBindingPolicy = Literal["none", "required"]
ToolProvider = Literal["common", "email_security", "binary_analysis"]


class RegistryDefaults(BaseModel):
    """Default paths for resolving bundle_path."""

    bundles_root: str = "subagents/official"


class ToolDecl(BaseModel):
    """Structured tool declaration in subagent registry (schema v3)."""

    name: str = Field(..., min_length=1)
    provider: ToolProvider = "common"
    backend_binding: BackendBindingPolicy = "none"
    enabled: bool = True
    description_override: str | None = None


class SubagentRegistryEntry(BaseModel):
    """One row in subagents.registry.yaml."""

    id: str = Field(..., min_length=1)
    enabled: bool = True
    source: Literal["official", "user"] = "official"
    bundle_path: str = Field(..., min_length=1)
    description: str = ""
    routing_hints: str | None = None
    # Optional explicit tools list (name-based or structured). When set, overrides ``tool_profile``.
    tools: list[str | ToolDecl] | None = None
    tool_profile: str = TOOL_PROFILE_DEFAULT
    extra_skill_package_ids: list[str] = Field(default_factory=list)
    include_shared_skills: bool = True
    runtime: Literal["standard", "compiled"] = "standard"
    # Optional per-subagent HumanInTheLoopMiddleware config (tool name -> True or InterruptOnConfig dict)
    interrupt_on: dict[str, Any] | None = None
    # Optional nested task() delegation configuration for standard subagents.
    allow_nested_task: bool = False
    nested_subagent_allowlist: list[str] = Field(default_factory=list)
    nested_max_depth: int = 1
    nested_task_system_prompt: str | None = None


class SubagentRegistryFile(BaseModel):
    """Root document for subagents.registry.yaml."""

    schema_version: int = 3
    defaults: RegistryDefaults = Field(default_factory=RegistryDefaults)
    shared_skills: dict[str, Any] = Field(default_factory=dict)
    subagents: list[SubagentRegistryEntry]

    @model_validator(mode="after")
    def _unique_ids(self) -> Self:
        if self.schema_version not in SUPPORTED_REGISTRY_SCHEMA_VERSIONS:
            raise ValueError(
                f"Unsupported registry schema_version={self.schema_version}. "
                f"Supported: {sorted(SUPPORTED_REGISTRY_SCHEMA_VERSIONS)}"
            )
        ids = [s.id for s in self.subagents]
        if len(ids) != len(set(ids)):
            raise ValueError(f"Duplicate subagent ids in registry: {ids}")
        active_official_ids = {
            s.id for s in self.subagents if s.enabled and s.source == "official"
        }
        for row in self.subagents:
            if not row.allow_nested_task:
                continue
            if row.nested_max_depth < 1:
                raise ValueError(
                    f"Subagent {row.id!r} nested_max_depth must be >= 1"
                )
            allowlist = [x.strip() for x in row.nested_subagent_allowlist if x.strip()]
            if not allowlist:
                raise ValueError(
                    f"Subagent {row.id!r} enables nested task but allowlist is empty"
                )
            if row.id in allowlist:
                raise ValueError(
                    f"Subagent {row.id!r} nested allowlist cannot include itself"
                )
            unknown = [x for x in allowlist if x not in active_official_ids]
            if unknown:
                raise ValueError(
                    f"Subagent {row.id!r} references unknown or inactive nested subagent(s): {unknown}"
                )
        return self


def default_registry_path() -> Path:
    """Resolved path to subagents.registry.yaml."""
    settings = get_settings()
    raw = getattr(settings, "subagents_registry_path", None)
    if raw:
        p = Path(raw)
        return p if p.is_absolute() else SERVICE_ROOT / p
    return SERVICE_ROOT / "config" / "subagents.registry.yaml"


def load_subagent_registry_file(path: Path | None = None) -> SubagentRegistryFile:
    """Load and validate registry YAML."""
    p = path or default_registry_path()
    if not p.is_file():
        raise FileNotFoundError(f"Subagent registry not found: {p}")
    data = yaml.safe_load(p.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ValueError("Registry root must be a mapping")
    return SubagentRegistryFile.model_validate(data)


def merge_task_catalog_description(description: str, routing_hints: str | None) -> str:
    """Single source for task() tool listing (registry only, not AGENT.md)."""
    d = (description or "").strip()
    h = (routing_hints or "").strip()
    if d and h:
        return f"{d} {h}".strip()
    return d or h or "Specialized security subagent."


def subagent_skills_virtual_prefix(subagent_id: str) -> str:
    return f"/subagent-skills/{subagent_id}/"


def skills_subset_virtual_prefix(subagent_id: str) -> str:
    return f"/skills-subset/{subagent_id}/"


def bundle_skills_has_packages(skills_root: Path) -> bool:
    if not skills_root.is_dir():
        return False
    try:
        for child in skills_root.iterdir():
            if child.is_dir() and (child / "SKILL.md").is_file():
                return True
    except OSError:
        return False
    return False


def valid_extra_skill_dir_names(extra_ids: list[str], skills_base: Path) -> frozenset[str]:
    out: list[str] = []
    for raw in extra_ids:
        e = str(raw).strip()
        if not e or e in {".", ".."}:
            continue
        if (skills_base / e / "SKILL.md").is_file():
            out.append(e)
    return frozenset(out)


def read_agent_md_system_prompt(bundle: Path) -> str | None:
    """Read AGENT.md body; strip optional YAML frontmatter."""
    agent_md = bundle / "AGENT.md"
    if not agent_md.is_file():
        return None
    text = agent_md.read_text(encoding="utf-8")
    if text.startswith("---"):
        parts = text.split("---", 2)
        if len(parts) >= 3:
            return parts[2].strip()
    return text.strip()


def resolve_skills_middleware_sources(
    subagent_id: str,
    bundle: Path,
    include_shared_skills: bool,
    extra_skill_package_ids: list[str],
) -> list[str]:
    """Virtual paths for SkillsMiddleware (order: shared → subset → bundle; bundle wins on name clash)."""
    sources: list[str] = []
    if include_shared_skills and SKILLS_DIR.exists():
        sources.append("/skills/")
    extras = valid_extra_skill_dir_names(extra_skill_package_ids, SKILLS_DIR)
    if not include_shared_skills and extras:
        sources.append(skills_subset_virtual_prefix(subagent_id))
    bundle_skills = bundle / "skills"
    if bundle_skills_has_packages(bundle_skills):
        sources.append(subagent_skills_virtual_prefix(subagent_id))
    return sources


def compute_skill_backend_routes(registry_path: Path | None = None) -> dict[str, dict[str, Any]]:
    """Routes for CompositeBackend: bundle skill roots and per-subagent filtered global picks.

    Returns:
        ``{"bundle": {virtual_prefix: abs_path}, "subset": {virtual_prefix: frozenset[dir_name]}}``
    """
    reg = load_subagent_registry_file(registry_path)
    bundles_root = (SERVICE_ROOT / reg.defaults.bundles_root).resolve()
    bundle_routes: dict[str, str] = {}
    subset_routes: dict[str, frozenset[str]] = {}

    research_mode = os.getenv("RESEARCH_AGENT_MODE", "compiled_subagent").strip().lower()

    for row in reg.subagents:
        if not row.enabled or row.source != "official":
            continue
        effective_runtime = row.runtime
        if row.id == "deep-research" and research_mode != "compiled_subagent":
            effective_runtime = "standard"
        if effective_runtime == "compiled":
            continue
        bundle = (bundles_root / row.bundle_path).resolve()
        skills_sub = bundle / "skills"
        if bundle_skills_has_packages(skills_sub):
            bundle_routes[subagent_skills_virtual_prefix(row.id)] = str(skills_sub.resolve())
        if not row.include_shared_skills:
            extras = valid_extra_skill_dir_names(row.extra_skill_package_ids, SKILLS_DIR)
            if extras:
                subset_routes[skills_subset_virtual_prefix(row.id)] = extras

    return {"bundle": bundle_routes, "subset": subset_routes}


def _merge_tools_by_name(*tool_lists: list[Any]) -> list[Any]:
    """Append tools in order; skip duplicates by ``tool.name`` (first wins)."""
    seen: set[str] = set()
    out: list[Any] = []
    for lst in tool_lists:
        for t in lst:
            name = getattr(t, "name", None)
            if not name or name in seen:
                continue
            seen.add(name)
            out.append(t)
    return out


def build_tool_profiles() -> dict[str, list[Any]]:
    """Map registry ``tool_profile`` id -> LangChain tool list.

    - **default**: ``create_common_tools()`` only.
    - **email-security**: common + ``create_email_tools()`` (deduped by name).
    - **web-security**: common + ``create_web_tools()`` (deduped by name).
    - **deep-research**: research subset only (unchanged).
    """
    from app.sse.tool_presentation import RESEARCH_TOOL_ORDER
    from app.tools.common.tools import create_common_tools
    from subagents.official.soc_alert.tools.soc_alert.api import create_soc_alert_api_tools
    from subagents.official.email_security.tools.tools import create_email_tools
    from subagents.official.web_security.tools.tools import create_web_tools

    common = create_common_tools()
    research = create_common_tools(only_names=frozenset(RESEARCH_TOOL_ORDER))
    soc_alert_api = [*common, *create_soc_alert_api_tools()]
    return {
        TOOL_PROFILE_DEFAULT: common,
        TOOL_PROFILE_EMAIL: _merge_tools_by_name(common, create_email_tools()),
        TOOL_PROFILE_WEB: _merge_tools_by_name(common, create_web_tools()),
        TOOL_PROFILE_DEEP_RESEARCH: research,
        TOOL_PROFILE_SOC_ALERT_API: soc_alert_api,
    }


def tools_for_profile(profile_id: str) -> list[Any]:
    profiles = build_tool_profiles()
    if profile_id not in profiles:
        logger.warning("Unknown tool_profile %r, using %s", profile_id, TOOL_PROFILE_DEFAULT)
        return profiles[TOOL_PROFILE_DEFAULT]
    return profiles[profile_id]


def normalize_tool_declarations(
    subagent_id: str,
    raw: list[str | ToolDecl] | None,
) -> list[ToolDecl] | None:
    """Normalize mixed ``tools`` formats to structured declarations.

    Accepts either legacy ``list[str]`` or schema-v3 ``list[ToolDecl]``.
    """
    if raw is None:
        return None
    out: list[ToolDecl] = []
    for item in raw:
        if isinstance(item, ToolDecl):
            out.append(item)
            continue
        name = str(item).strip()
        if not name:
            continue
        if subagent_id == "email-security":
            default_provider: ToolProvider = "email_security"
        elif subagent_id == "binary-analysis":
            default_provider = "binary_analysis"
        else:
            default_provider = "common"
        out.append(
            ToolDecl(
                name=name,
                # Backward compatibility: legacy declarations without provider use
                # subagent-specific defaults (email_security / binary_analysis / common).
                provider=default_provider,
            )
        )
    return out


def _copy_tool_with_description(tool_obj: Any, description_override: str | None) -> Any:
    """Return tool with description override when possible; otherwise original."""
    if not description_override:
        return tool_obj
    desc = description_override.strip()
    if not desc:
        return tool_obj
    from langchain_core.tools import StructuredTool

    if isinstance(tool_obj, StructuredTool):
        return StructuredTool.from_function(
            func=cast(Any, tool_obj).func,
            name=tool_obj.name,
            description=desc,
            args_schema=tool_obj.args_schema,
        )
    logger.warning(
        "description_override_ignored_non_structured_tool",
        tool_name=getattr(tool_obj, "name", "<unknown>"),
    )
    return tool_obj


def _resolve_from_email_security_provider(name: str) -> Any:
    """Resolve one tool by name from ``subagents.official.email_security.tools``."""
    from subagents.official.email_security import tools as email_tools

    exported = set(getattr(email_tools, "__all__", []))
    if name not in exported:
        raise ValueError(
            f"Tool {name!r} is not exported by email_security tools provider"
        )
    obj = getattr(email_tools, name, None)
    if obj is None:
        raise ValueError(f"Tool {name!r} not found in email_security provider")
    return obj


def tools_for_declared_names(
    subagent_id: str,
    tool_decls: list[ToolDecl],
    *,
    backend_factory: Callable[[Any], Any] | None = None,
) -> list[Any]:
    """Resolve explicit ``tools`` declarations to tool objects."""
    from app.tools.common.tools import create_common_tools
    from subagents.official.email_security.tools import bind_backend

    resolved: list[Any] = []
    available_common: dict[str, Any] = {}
    binary_tool_map: dict[str, Any] | None = None

    for t in create_common_tools():
        name = getattr(t, "name", "").strip()
        if name:
            available_common[name] = t

    for decl in tool_decls:
        if not decl.enabled:
            continue
        name = decl.name.strip()
        if not name:
            continue
        provider = decl.provider
        tool_obj: Any | None = None
        if provider == "common":
            tool_obj = available_common.get(name)
            if tool_obj is None and subagent_id == "email-security":
                # Backward compatibility for legacy email rows missing provider.
                tool_obj = _resolve_from_email_security_provider(name)
        elif provider == "email_security":
            tool_obj = _resolve_from_email_security_provider(name)
        elif provider == "binary_analysis":
            if binary_tool_map is None:
                from subagents.official.binary_analysis.registry import (
                    build_subagent_tool_map,
                )

                binary_tool_map = build_subagent_tool_map(backend_factory)
            tool_obj = binary_tool_map.get(name)
        else:
            raise ValueError(
                f"Unknown tool provider {provider!r} for tool {name!r} in subagent {subagent_id!r}"
            )

        if tool_obj is None:
            raise ValueError(
                f"Unknown tool {name!r} (provider={provider}) in subagent {subagent_id!r}"
            )
        binding = decl.backend_binding
        if binding == "required":
            if backend_factory is None:
                raise RuntimeError(
                    f"Tool {name!r} in subagent {subagent_id!r} requires backend binding, "
                    "but backend_factory is None."
                )
            tool_obj = bind_backend(cast(Any, tool_obj), backend_factory)
        tool_obj = _copy_tool_with_description(tool_obj, decl.description_override)
        resolved.append(tool_obj)
    return resolved


CompiledSubAgentBuilder = Callable[[str], dict[str, Any]]

COMPILED_SUBAGENT_BUILDERS: dict[str, CompiledSubAgentBuilder] = {}


def _register_compiled_builders() -> None:
    from app.agents.research.open_deep_research_compiled import (
        build_open_deep_research_compiled_subagent,
    )

    COMPILED_SUBAGENT_BUILDERS.clear()
    COMPILED_SUBAGENT_BUILDERS["deep-research"] = build_open_deep_research_compiled_subagent


_register_compiled_builders()


def validate_compiled_builders_for_entries(entries: list[SubagentRegistryEntry]) -> None:
    """Fail fast if compiled runtime lacks a factory."""
    for e in entries:
        if e.runtime != "compiled" or not e.enabled:
            continue
        if e.source == "user":
            continue
        if e.id not in COMPILED_SUBAGENT_BUILDERS:
            raise RuntimeError(
                f"Compiled subagent {e.id!r} has no entry in COMPILED_SUBAGENT_BUILDERS; "
                f"available: {sorted(COMPILED_SUBAGENT_BUILDERS)}"
            )


def _build_nested_subagent_spec(spec: dict[str, Any]) -> dict[str, Any]:
    """Build a nested task() child spec from a top-level subagent spec."""
    if "runnable" in spec:
        return {
            "name": spec["name"],
            "description": spec["description"],
            "runnable": spec["runnable"],
        }
    if "model" not in spec or "tools" not in spec:
        raise RuntimeError(
            f"Nested subagent {spec.get('name', '<unknown>')!r} lacks model/tools"
        )
    out: dict[str, Any] = {
        "name": spec["name"],
        "description": spec["description"],
        "system_prompt": spec["system_prompt"],
        "model": spec["model"],
        "tools": spec["tools"],
    }
    if "interrupt_on" in spec:
        out["interrupt_on"] = spec["interrupt_on"]
    return out


def _inject_nested_subagent_middlewares(
    *,
    specs: list[dict[str, Any]],
    active_official: list[SubagentRegistryEntry],
    backend_factory: Callable[[Any], Any] | None,
) -> None:
    """Append SubAgentMiddleware for rows that enable nested task delegation."""
    from app._vendor.deepagents.middleware.subagents import SubAgentMiddleware

    nested_rows = [row for row in active_official if row.allow_nested_task]
    if not nested_rows:
        return
    if backend_factory is None:
        raise RuntimeError(
            "Nested task delegation requires backend_factory, but got None."
        )

    spec_by_name = {spec["name"]: spec for spec in specs}
    for row in nested_rows:
        parent = spec_by_name.get(row.id)
        if parent is None:
            raise RuntimeError(
                f"Nested task parent spec {row.id!r} not found while injecting middleware"
            )
        child_specs: list[dict[str, Any]] = []
        for child_name in row.nested_subagent_allowlist:
            child = spec_by_name.get(child_name)
            if child is None:
                raise RuntimeError(
                    f"Nested task child spec {child_name!r} not found for parent {row.id!r}"
                )
            child_specs.append(_build_nested_subagent_spec(child))

        nested_system_prompt = row.nested_task_system_prompt
        if not nested_system_prompt:
            allowed = ", ".join(row.nested_subagent_allowlist)
            nested_system_prompt = (
                "Use task() only for approved nested delegation. "
                f"Allowed nested subagent types: {allowed}. "
                "Do not recurse beyond one nested level."
            )
        parent.setdefault("middleware", [])
        cast(list[Any], parent["middleware"]).append(
            SubAgentMiddleware(
                backend=backend_factory,
                subagents=child_specs,
                system_prompt=nested_system_prompt,
            )
        )


def build_subagent_specs_from_registry(
    registry_path: Path | None = None,
    *,
    backend_factory: Callable[[Any], Any] | None = None,
    default_subagent_model: Any | None = None,
) -> list[dict[str, Any]]:
    """Build create_deep_agent(subagents=...) specs from registry + bundles.

    Explicit ``tools`` declarations are resolved by provider + binding policy.
    When ``tools`` is absent, profile-based fallback remains for compatibility.
    """
    reg = load_subagent_registry_file(registry_path)
    bundles_root = (SERVICE_ROOT / reg.defaults.bundles_root).resolve()

    active_official = [
        r
        for r in reg.subagents
        if r.enabled and r.source == "official"
    ]
    for r in reg.subagents:
        if r.source == "user" and r.enabled:
            logger.warning(
                "Skipping subagent %s: source=user is not supported in Phase 1",
                r.id,
            )

    compiled_to_check = [r for r in active_official if r.runtime == "compiled"]
    validate_compiled_builders_for_entries(compiled_to_check)

    specs: list[dict[str, Any]] = []
    research_mode = os.getenv("RESEARCH_AGENT_MODE", "compiled_subagent").strip().lower()
    if default_subagent_model is None:
        from langchain_core.language_models.fake_chat_models import FakeListChatModel

        default_subagent_model = FakeListChatModel(responses=["Nested task fallback"])

    for row in active_official:
        bundle = (bundles_root / row.bundle_path).resolve()
        if not bundle.is_dir():
            raise FileNotFoundError(
                f"Subagent bundle missing: id={row.id!r} expected_dir={bundle}"
            )

        catalog_desc = merge_task_catalog_description(row.description, row.routing_hints)

        effective_runtime = row.runtime
        if row.id == "deep-research" and research_mode != "compiled_subagent":
            effective_runtime = "standard"

        if effective_runtime == "compiled":
            if row.interrupt_on:
                logger.warning(
                    "interrupt_on on registry entry %s is ignored for compiled runtime (Phase 1 policy)",
                    row.id,
                )
            builder = COMPILED_SUBAGENT_BUILDERS[row.id]
            compiled_spec = builder(catalog_desc)
            compiled_spec["description"] = catalog_desc
            specs.append(compiled_spec)
            continue

        body = read_agent_md_system_prompt(bundle)
        if body:
            system_prompt = body
            if row.id == "email-security":
                system_prompt = system_prompt.replace(
                    "__BUDGET__", str(EMAIL_SECURITY_TOOL_CALL_BUDGET)
                )
        else:
            logger.warning(
                "Missing or empty AGENT.md for standard subagent %s; using fallback prompt",
                row.id,
            )
            system_prompt = SUBAGENT_BASE_PROMPT_FALLBACK

        normalized_tool_decls = normalize_tool_declarations(row.id, row.tools)
        if normalized_tool_decls is not None:
            tool_list = tools_for_declared_names(
                row.id,
                normalized_tool_decls,
                backend_factory=backend_factory,
            )
        elif row.id == "deep-research" and effective_runtime == "standard":
            tool_list = tools_for_profile(TOOL_PROFILE_DEEP_RESEARCH)
        else:
            tool_list = tools_for_profile(row.tool_profile)

        skills_sources = resolve_skills_middleware_sources(
            row.id,
            bundle,
            row.include_shared_skills,
            row.extra_skill_package_ids,
        )

        system_prompt = system_prompt.rstrip() + SUBAGENT_OUTPUT_APPENDIX

        entry: dict[str, Any] = {
            "name": row.id,
            "description": catalog_desc,
            "system_prompt": system_prompt,
            "model": default_subagent_model,
            "tools": tool_list,
            "skills": skills_sources,
        }
        if row.interrupt_on:
            entry["interrupt_on"] = dict(row.interrupt_on)
        specs.append(entry)

    _inject_nested_subagent_middlewares(
        specs=specs,
        active_official=active_official,
        backend_factory=backend_factory,
    )

    return specs


def available_agents_lines_from_registry(registry_path: Path | None = None) -> str:
    """Debug/helper: same lines as embedded in task tool (from registry only)."""
    reg = load_subagent_registry_file(registry_path)
    lines: list[str] = []
    for row in reg.subagents:
        if not row.enabled or row.source != "official":
            continue
        desc = merge_task_catalog_description(row.description, row.routing_hints)
        lines.append(f"- {row.id}: {desc}")
    return "\n".join(lines)


def get_tools_for_agent(agent_name: str):
    """Return the tool list for a given subagent registry id."""
    profile_by_id: dict[str, str] = {
        "email-security": TOOL_PROFILE_EMAIL,
        "web-security": TOOL_PROFILE_WEB,
        "deep-research": TOOL_PROFILE_DEEP_RESEARCH,
    }
    pid = profile_by_id.get(agent_name, TOOL_PROFILE_DEFAULT)
    return tools_for_profile(pid)
