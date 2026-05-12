"""Tool presentation registry for SSE events (hot-loaded from YAML)."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from threading import Lock
from typing import Any, Literal

import structlog
import yaml
from app.config.settings import SERVICE_ROOT

logger = structlog.get_logger()

ToolPresentation = Literal["task", "action", "state", "parameter", "research_task"]
ParameterControl = Literal["single", "multi", "fill"]
ToolRuleCategory = Literal["system", "common", "subagent"]
_VALID_PRESENTATIONS = {"task", "action", "state", "parameter", "research_task"}
_VALID_PARAMETER_CONTROLS = {"single", "multi", "fill"}
DEFAULT_TOOL_PRESENTATION: ToolPresentation = "action"

_TIERED_TOOL_KEYS = frozenset({"system_tools", "common_tools", "subagent_tools"})

_TOOL_REGISTRY_YAML_PATH: Path = SERVICE_ROOT / "config" / "tool_presentation.yaml"
_REGISTRY_LOCK = Lock()
_REGISTRY_CACHE_MTIME: float | None = None


@dataclass(frozen=True)
class ToolRegistrySnapshot:
    """Hot-reloaded tool presentation rules + ``common_tools`` key order (tiered YAML)."""

    rules: dict[str, ToolRule]
    common_tools_key_order: tuple[str, ...]
    tiered_schema: bool


_REGISTRY_SNAPSHOT: ToolRegistrySnapshot | None = None


@dataclass(frozen=True)
class ToolRule:
    presentation: ToolPresentation
    parameter_control: ParameterControl | None = None
    emit_output: bool = True
    # ``common``: ``enabled`` / ``description`` consumed by ``create_common_tools`` (and HITL).
    # ``system`` / ``subagent``: same fields may still be read by factories for optional tools;
    # primarily SSE / UI metadata. ``None`` = legacy flat ``tools:`` YAML (no tier).
    enabled: bool = True
    description: str | None = None
    category: ToolRuleCategory | None = None
    # Optional outbound SSE alias: ``attach_tool_presentation`` rewrites ``toolName`` for the client
    # while registry lookup / ``should_emit_tool_output`` still use the canonical LangChain name.
    sse_tool_name: str | None = None


# Ordered names passed to create_common_tools() (excluding HITL; see HITL_REGISTRY_TOOL_NAME).
COMMON_SECURITY_TOOL_ORDER: tuple[str, ...] = (
    "extract_iocs",
    "decode_base64",
    "decode_url",
    "lookup_threat_intel",
)

# Registry key for request_user_input (HITL); merged into common tools when include_hitl is true.
HITL_REGISTRY_TOOL_NAME = "request_user_input"

# Tool names for create_email_tools() (optional; registry subagents use common tools only).
EMAIL_SECURITY_TOOL_ORDER: tuple[str, ...] = (
    "analyze_email_headers",
    "detect_phishing_indicators",
)

# Tool names for create_web_tools() (optional; registry subagents use common tools only).
WEB_SECURITY_TOOL_ORDER: tuple[str, ...] = ("detect_web_attack",)

# Names assembled by ``create_research_tools()``; ``enabled`` / ``description`` from YAML apply here.
RESEARCH_TOOL_ORDER: tuple[str, ...] = (
    "web_search",
    "scrape_url",
    "summarize_content",
)


def _prefix_default_state(name: str) -> bool:
    n = name.lower()
    return n.startswith("internal_") or n.startswith("hitl_")


def _default_tool_registry() -> dict[str, ToolRule]:
    """Fallback registry when YAML is absent or invalid."""
    return {
        "write_todos": ToolRule("task"),
        "task": ToolRule("task"),
        "web_search": ToolRule("action"),
        "scrape_url": ToolRule("action"),
        "read_file": ToolRule("action", emit_output=False),
        "grep": ToolRule("action"),
        "glob": ToolRule("action"),
        "ls": ToolRule("action"),
        "extract_iocs": ToolRule("action"),
        "decode_base64": ToolRule("action"),
        "decode_url": ToolRule("action"),
        "lookup_threat_intel": ToolRule("action"),
        "request_user_input": ToolRule("parameter"),
        "analyze_email_headers": ToolRule("action"),
        "detect_phishing_indicators": ToolRule("action"),
        "detect_web_attack": ToolRule("action"),
        "summarize_content": ToolRule("action"),
        "search_history": ToolRule("action"),
        "analyze_file_structure": ToolRule("action"),
        "edit_file": ToolRule("action"),
        "write_file": ToolRule("action"),
        "execute": ToolRule("action"),
        "think_tool": ToolRule("state", emit_output=False),
        "ConductResearch": ToolRule("research_task", emit_output=False),
        "ResearchComplete": ToolRule("state", emit_output=False),
        "ResearchQuestion": ToolRule("state", emit_output=False),
        "web_search_deep_research": ToolRule(
            "action", sse_tool_name="web_searchs"
        ),
    }


def _parse_tool_rule(
    name: str, raw: Any, *, category: ToolRuleCategory | None = None
) -> ToolRule | None:
    if not isinstance(raw, dict):
        logger.warning("tool_registry_item_not_object", tool_name=name)
        return None
    p = str(raw.get("presentation") or "").strip()
    if p not in _VALID_PRESENTATIONS:
        logger.warning(
            "tool_registry_invalid_presentation",
            tool_name=name,
            presentation=p,
        )
        return None
    pc_raw = raw.get("parameter_control")
    parameter_control: ParameterControl | None = None
    if pc_raw is not None:
        pc = str(pc_raw).strip()
        if pc not in _VALID_PARAMETER_CONTROLS:
            logger.warning(
                "tool_registry_invalid_parameter_control",
                tool_name=name,
                parameter_control=pc,
            )
            return None
        parameter_control = pc  # type: ignore[assignment]
    emit_output = bool(raw.get("emit_output", True))
    enabled = bool(raw.get("enabled", True))
    desc_raw = raw.get("description")
    description: str | None
    if desc_raw is None:
        description = None
    else:
        description = str(desc_raw).strip() or None
    sse_raw = raw.get("sse_tool_name")
    sse_tool_name: str | None = None
    if sse_raw is not None:
        s = str(sse_raw).strip()
        if s:
            sse_tool_name = s
    return ToolRule(
        presentation=p,  # type: ignore[arg-type]
        parameter_control=parameter_control,
        emit_output=emit_output,
        enabled=enabled,
        description=description,
        category=category,
        sse_tool_name=sse_tool_name,
    )


def _payload_uses_tiered_tool_schema(payload: dict[str, Any]) -> bool:
    return any(k in payload for k in _TIERED_TOOL_KEYS)


def _common_tools_keys_from_payload(payload: dict[str, Any]) -> tuple[str, ...]:
    block = payload.get("common_tools")
    if not isinstance(block, dict):
        return ()
    return tuple(str(k).strip() for k in block if str(k).strip())


def _load_registry_from_yaml(path: Path) -> ToolRegistrySnapshot:
    if not path.exists():
        logger.warning("tool_registry_yaml_missing", path=str(path))
        return ToolRegistrySnapshot(_default_tool_registry(), (), False)
    try:
        payload = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    except Exception:
        logger.exception("tool_registry_yaml_read_failed", path=str(path))
        return ToolRegistrySnapshot(_default_tool_registry(), (), False)

    if not isinstance(payload, dict):
        logger.warning("tool_registry_yaml_invalid_schema", path=str(path))
        return ToolRegistrySnapshot(_default_tool_registry(), (), False)

    tiered = _payload_uses_tiered_tool_schema(payload)
    if tiered:
        out = _parse_tiered_registry(payload)
        common_order = _common_tools_keys_from_payload(payload)
    else:
        tools = payload.get("tools")
        if not isinstance(tools, dict) or not tools:
            logger.warning("tool_registry_yaml_invalid_schema", path=str(path))
            return ToolRegistrySnapshot(_default_tool_registry(), (), False)
        out = {}
        for name, raw in tools.items():
            n = str(name).strip()
            if not n:
                continue
            parsed = _parse_tool_rule(n, raw, category=None)
            if parsed is not None:
                out[n] = parsed
        common_order = ()

    if not out:
        logger.warning("tool_registry_yaml_empty_effective", path=str(path))
        return ToolRegistrySnapshot(_default_tool_registry(), (), False)
    return ToolRegistrySnapshot(out, common_order, tiered)


def _parse_tiered_registry(payload: dict[str, Any]) -> dict[str, ToolRule]:
    out: dict[str, ToolRule] = {}
    for key, cat in (
        ("system_tools", "system"),
        ("common_tools", "common"),
        ("subagent_tools", "subagent"),
    ):
        block = payload.get(key)
        if not isinstance(block, dict):
            continue
        for name, raw in block.items():
            n = str(name).strip()
            if not n:
                continue
            parsed = _parse_tool_rule(n, raw, category=cat)
            if parsed is not None:
                out[n] = parsed
    return out


def _registry_snapshot() -> ToolRegistrySnapshot:
    """Hot reload YAML by file mtime."""
    global _REGISTRY_SNAPSHOT, _REGISTRY_CACHE_MTIME
    path = _TOOL_REGISTRY_YAML_PATH
    try:
        mtime = path.stat().st_mtime
    except FileNotFoundError:
        mtime = -1.0
    with _REGISTRY_LOCK:
        if _REGISTRY_SNAPSHOT is not None and _REGISTRY_CACHE_MTIME == mtime:
            return _REGISTRY_SNAPSHOT
        _REGISTRY_SNAPSHOT = _load_registry_from_yaml(path)
        _REGISTRY_CACHE_MTIME = mtime
        return _REGISTRY_SNAPSHOT


def clear_tool_registry_cache() -> None:
    """Testing helper: force next access to reload YAML."""
    global _REGISTRY_SNAPSHOT, _REGISTRY_CACHE_MTIME
    with _REGISTRY_LOCK:
        _REGISTRY_SNAPSHOT = None
        _REGISTRY_CACHE_MTIME = None


def is_tiered_tool_registry() -> bool:
    """True when YAML uses ``system_tools`` / ``common_tools`` / ``subagent_tools``."""
    return _registry_snapshot().tiered_schema


def common_tools_key_order() -> tuple[str, ...]:
    """Declaration order under ``common_tools`` (empty when legacy ``tools:`` schema)."""
    return _registry_snapshot().common_tools_key_order


def get_tool_rule(tool_name: str) -> ToolRule | None:
    """Return the parsed rule for ``tool_name``, or ``None`` if absent."""
    raw = tool_name.strip()
    if not raw:
        return None
    return _registry_snapshot().rules.get(raw)


def resolve_tool_presentation(
    tool_name: str,
) -> tuple[ToolPresentation, ParameterControl | None, bool]:
    """Return (presentation, parameterControl_or_None, known_in_registry)."""
    raw = tool_name.strip()
    if not raw:
        return DEFAULT_TOOL_PRESENTATION, None, False
    registry = _registry_snapshot().rules
    if raw in registry:
        rule = registry[raw]
        return rule.presentation, rule.parameter_control, True
    if _prefix_default_state(raw):
        return "state", None, True
    return DEFAULT_TOOL_PRESENTATION, None, False


def should_emit_tool_output(tool_name: str) -> bool:
    """Whether this tool's `toolOutput` should be included in SSE events."""
    raw = tool_name.strip()
    if not raw:
        return True
    rule = _registry_snapshot().rules.get(raw)
    if rule is not None:
        return rule.emit_output
    return True


def get_all_workspace_tab_configs() -> dict[str, Any]:
    """Return mapping of tool_name → workspace_tab config for tools that declare one.

    Reads the raw YAML directly so workspace_tab data is preserved without modifying ToolRule.
    Falls back to empty dict on error.
    """
    path = _TOOL_REGISTRY_YAML_PATH
    try:
        payload = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    except Exception:
        logger.exception("workspace_tab_config_read_failed", path=str(path))
        return {}
    if not isinstance(payload, dict):
        return {}

    result: dict[str, Any] = {}
    sections = (
        payload.get("system_tools"),
        payload.get("common_tools"),
        payload.get("subagent_tools"),
        payload.get("tools"),
    )
    for section in sections:
        if not isinstance(section, dict):
            continue
        for tool_name, tool_cfg in section.items():
            if not isinstance(tool_cfg, dict):
                continue
            wt = tool_cfg.get("workspace_tab")
            if wt and isinstance(wt, dict):
                result[str(tool_name)] = {"workspace_tab": wt}
    return result


def attach_tool_presentation(ev: dict[str, Any]) -> None:
    """Attach presentation fields to ``tool_call`` / ``tool_result`` events."""
    t = ev.get("type")
    if t not in ("tool_call", "tool_result"):
        return
    name = str(ev.get("toolName") or "").strip()
    if not name:
        return
    presentation, parameter_control, known = resolve_tool_presentation(name)
    if not known:
        logger.info(
            "unknown_tool_name",
            tool_name=name,
            event_type=t,
            event_id=ev.get("id"),
        )
    ev["toolPresentation"] = presentation
    if parameter_control is not None:
        ev["parameterControl"] = parameter_control
    rule = get_tool_rule(name)
    if rule is not None and rule.sse_tool_name:
        ev["toolName"] = rule.sse_tool_name
