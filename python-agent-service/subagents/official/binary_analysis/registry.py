"""Registry-facing BinaryAnalyst tool assembly (``provider: binary_analysis``).

Mirrors how :mod:`subagents.official.email_security.tools` supplies callables for
:func:`~app.agents.subagent_registry.tools_for_declared_names`: this module
builds the canonical ten-tool instance map from :func:`tool_builder.build_binary_analyst_tools`.

Sandbox: uses :func:`~sandbox.factory.build_binary_sandbox_client` (same backend
selection as :mod:`binary_analysis.api` / LangGraph UI). ``backend_factory`` remains
reserved for future SECMANUS CompositeBackend bridging.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

# Canonical order matches tool_builder.build_binary_analyst_tools (DESIGN §4.1 L2/L3).
REGISTRY_TOOL_ORDER: tuple[str, ...] = (
    "file_identify",
    "evidence_chain",
    "scoring",
    "decision_gate",
    "report_gen",
    "bash",
    "python_exec",
    "file_read",
    "sandbox_session",
    "document_extract",
)


class _LazyBinarySandboxClient:
    """Defer sandbox backend construction until the first tool call.

    App startup and subagent registry assembly should not fail merely because
    E2B credentials are missing. The concrete backend still raises on first
    use, where tools convert the failure into structured ToolMessage output.
    """

    def __init__(self) -> None:
        self._inner: Any | None = None

    def _client(self) -> Any:
        if self._inner is None:
            from sandbox.factory import build_binary_sandbox_client

            self._inner = build_binary_sandbox_client()
        return self._inner

    async def create(self, analysis_id: str) -> Any:
        return await self._client().create(analysis_id)

    async def exec(self, *args: Any, **kwargs: Any) -> Any:
        return await self._client().exec(*args, **kwargs)

    async def upload(self, *args: Any, **kwargs: Any) -> Any:
        return await self._client().upload(*args, **kwargs)

    async def download(self, *args: Any, **kwargs: Any) -> Any:
        return await self._client().download(*args, **kwargs)

    async def kill(self, *args: Any, **kwargs: Any) -> Any:
        return await self._client().kill(*args, **kwargs)


def build_subagent_tool_map(
    backend_factory: Callable[[Any], Any] | None = None,
) -> dict[str, Any]:
    """Return LangChain tool instances keyed by name for subagent registry YAML."""
    _ = backend_factory  # reserved for CompositeBackend / uploads bridging
    import tool_builder
    from evidence_chain.store import EvidenceChainStore

    store = EvidenceChainStore()
    client = _LazyBinarySandboxClient()
    try:
        from app.services.sample_path_resolver import (
            build_current_request_sample_path_resolver,
        )

        sample_path_resolver = build_current_request_sample_path_resolver()
    except Exception:
        sample_path_resolver = None
    tools = tool_builder.build_binary_analyst_tools(
        store=store,
        sandbox_client=client,
        sample_path_resolver=sample_path_resolver,
    )
    return {t.name: t for t in tools}


def create_binary_analysis_tools(
    backend_factory: Callable[[Any], Any] | None = None,
) -> list[Any]:
    """Return the canonical tool list in registry order (parallel to ``create_email_tools``)."""
    m = build_subagent_tool_map(backend_factory)
    return [m[name] for name in REGISTRY_TOOL_ORDER]


__all__ = [
    "REGISTRY_TOOL_ORDER",
    "build_subagent_tool_map",
    "create_binary_analysis_tools",
]
