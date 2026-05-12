"""Registry: canonical common tool name -> mounter for tiered YAML assembly."""

from __future__ import annotations

import os
from collections.abc import Callable

from langchain_core.tools import StructuredTool

from app.sse.tool_presentation import COMMON_SECURITY_TOOL_ORDER, RESEARCH_TOOL_ORDER
from app.tools.tool_spec import ToolRisk, ToolSpec

CommonToolMounter = Callable[[list[StructuredTool]], None]

# Canonical names for E2B sandbox tools (order matches tool_presentation.yaml).
SANDBOX_TOOL_NAMES: tuple[str, ...] = (
    "sandbox_create",
    "sandbox_destroy",
    "sandbox_run",
    "sandbox_pty_run",
)


def _make_security_mounter(name: str) -> CommonToolMounter:
    def _mount(out: list[StructuredTool]) -> None:
        from app.tools.common.tools import _mount_common_security_tool

        _mount_common_security_tool(name, out)

    return _mount


def _mount_search_history_registry(out: list[StructuredTool]) -> None:
    from app.tools.common.tools import _mount_search_history

    _mount_search_history(out)


def _mount_sread_file(out: list[StructuredTool]) -> None:
    if any(getattr(t, "name", None) == "SReadFile" for t in out):
        return
    from app.tools.sread_file import create_sread_file_tool

    out.append(create_sread_file_tool())


def _mount_sandbox_tools_registry(out: list[StructuredTool]) -> None:
    """Mount all four sandbox tools if E2B_API_KEY is present.

    This mounter is registered for each of the four sandbox tool names in
    ``common_tools_key_order()``.  The first invocation within one
    ``create_common_tools()`` call appends all four tools; subsequent
    calls are no-ops because the tools are already in ``out``.
    """
    if not os.environ.get("E2B_API_KEY"):
        return
    existing_names = {t.name for t in out}
    if all(n in existing_names for n in SANDBOX_TOOL_NAMES):
        return
    try:
        from app.tools.sandbox_tools import create_sandbox_tools

        for t in create_sandbox_tools():
            if t.name not in {x.name for x in out}:
                out.append(t)
    except Exception as exc:  # noqa: BLE001
        import structlog

        structlog.get_logger(__name__).warning(
            "sandbox_tools_mount_failed", error=str(exc)
        )


def _build_tool_specs() -> dict[str, ToolSpec]:
    specs: dict[str, ToolSpec] = {}
    for n in COMMON_SECURITY_TOOL_ORDER:
        risk = ToolRisk.NETWORK if n == "lookup_threat_intel" else ToolRisk.READ_ONLY
        specs[n] = ToolSpec(name=n, category="security", risk=risk)
    specs["search_history"] = ToolSpec(
        name="search_history", category="history", risk=ToolRisk.READ_ONLY
    )
    for n in RESEARCH_TOOL_ORDER:
        specs[n] = ToolSpec(name=n, category="research", risk=ToolRisk.NETWORK)
    for n in SANDBOX_TOOL_NAMES:
        specs[n] = ToolSpec(name=n, category="sandbox", risk=ToolRisk.NETWORK)
    specs["SReadFile"] = ToolSpec(
        name="SReadFile", category="security", risk=ToolRisk.READ_ONLY
    )
    return specs


COMMON_TOOL_SPECS: dict[str, ToolSpec] = _build_tool_specs()


def _build_common_tool_mounters() -> dict[str, CommonToolMounter]:
    """Security tools + ``search_history`` + sandbox tools; research trio uses ``try_append_research_tool``."""
    m: dict[str, CommonToolMounter] = {}
    for name in COMMON_SECURITY_TOOL_ORDER:
        m[name] = _make_security_mounter(name)
    m["search_history"] = _mount_search_history_registry
    m["SReadFile"] = _mount_sread_file
    for name in SANDBOX_TOOL_NAMES:
        m[name] = _mount_sandbox_tools_registry
    return m


COMMON_TOOL_MOUNTERS: dict[str, CommonToolMounter] = _build_common_tool_mounters()


def get_tool_spec(name: str) -> ToolSpec | None:
    return COMMON_TOOL_SPECS.get(name)


def registered_common_tool_names() -> frozenset[str]:
    """All names supported by ``try_mount_common_tool`` (security + history + research)."""
    return frozenset(COMMON_TOOL_MOUNTERS.keys()) | frozenset(RESEARCH_TOOL_ORDER)


def try_mount_common_tool(name: str, out: list[StructuredTool]) -> bool:
    """Mount one tiered common tool if ``name`` is known. Returns whether a tool was appended."""
    if name in RESEARCH_TOOL_ORDER:
        from app.tools.research_tools import try_append_research_tool

        return try_append_research_tool(name, out, assume_yaml_enabled=True)
    mounter = COMMON_TOOL_MOUNTERS.get(name)
    if mounter is None:
        return False
    mounter(out)
    return True
