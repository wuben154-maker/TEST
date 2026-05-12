"""BinaryAnalyst DeepAgent graph factory (ADR-01 + ADR-14)."""

from __future__ import annotations

import tempfile
from collections.abc import Sequence
from pathlib import Path
from typing import TYPE_CHECKING, Any

from deepagents import create_deep_agent
from deepagents.backends.composite import CompositeBackend
from deepagents.backends.filesystem import FilesystemBackend

from prompts.system_prompt import BINARY_ANALYST_SYSTEM_PROMPT
from tool_builder import build_binary_analyst_tools

if TYPE_CHECKING:  # pragma: no cover
    from langchain_core.language_models import BaseChatModel
    from langgraph.graph.state import CompiledStateGraph

    from evidence_chain.store import EvidenceChainStore
    from sandbox.client import SandboxClient

__all__ = ["build_binary_analyst_agent"]


def build_binary_analyst_agent(
    *,
    model: BaseChatModel,
    store: EvidenceChainStore,
    sandbox_client: SandboxClient | Any,
    skills_root: Path,
    skills_sources: Sequence[str] | None = None,
    rules_path: Path | None = None,
    extra_middleware: Sequence[Any] = (),
    backend: Any = None,
    embedded_payload_handler: Any = None,
) -> CompiledStateGraph:
    """Construct the BinaryAnalyst DeepAgent (ADR-01).

    The returned graph is the LangGraph compiled state graph produced by
    :func:`deepagents.create_deep_agent`.  The caller drives it via
    ``graph.invoke({"messages": [...]})`` / ``graph.ainvoke`` — that
    dispatch is the responsibility of ``C15`` (CLI + API).

    Skills (ADR-14) are loaded off the local filesystem rooted at
    ``skills_root``.  Callers typically pass
    ``examples/binary_analysis/skills`` so the Agent sees the full set
    of Proto / Gap / Workflow skills shipped in C8–C10.

    Args:
        model: Concrete chat model (e.g. ``ChatAnthropic`` or
            ``FakeListChatModel`` in tests).
        store: Shared per-analysis :class:`EvidenceChainStore`.
        sandbox_client: Concrete SandboxClient backend.
        skills_root: Filesystem root handed to ``FilesystemBackend`` for
            on-demand skill loading.  Must contain the Proto/Gap/Workflow
            skills directory tree.
        skills_sources: Optional override for the skill source paths
            exposed to the Agent (defaults to ``["/"]`` — the entire
            ``skills_root``).
        rules_path: Override for ``scoring_rules.yaml`` passed to
            :class:`ScoringTool`.
        extra_middleware: Additional middleware appended to the
            standard DeepAgents stack (ignored in tests that short-circuit
            via :func:`build_binary_analyst_tools`).
        backend: Optional backend override (``BackendProtocol`` instance
            or a ``(runtime) -> BackendProtocol`` factory) handed
            verbatim to :func:`create_deep_agent`.  ``None`` wraps a
            :class:`FilesystemBackend` rooted at ``skills_root`` inside a
            :class:`CompositeBackend` that additionally routes
            ``/large_tool_results/`` and ``/conversation_history/`` to
            ephemeral tempdirs — otherwise
            :class:`~deepagents.middleware.filesystem.FilesystemMiddleware`
            would evict oversized ToolMessage payloads into the live
            skills tree and pollute ``skills_root`` with binary junk (see
            ``libs/cli/deepagents_cli/agent.py`` for the reference
            wiring).  Useful for the LangGraph dev entrypoint, which
            composes an overlay that surfaces UI-uploaded files alongside
            the skills tree.
        embedded_payload_handler: Optional FR-30 callback passed through to
            payload-producing tools without changing the canonical tool count.

    Returns:
        Compiled LangGraph ready for ``invoke`` / ``ainvoke``.
    """
    tools = build_binary_analyst_tools(
        store=store,
        sandbox_client=sandbox_client,
        rules_path=rules_path,
        embedded_payload_handler=embedded_payload_handler,
    )
    enhanced_system_prompt = BINARY_ANALYST_SYSTEM_PROMPT
    if backend is not None:
        resolved_backend = backend
    else:
        # Isolate FilesystemMiddleware's eviction sinks from the skills
        # tree. Without these routes the middleware writes
        # /large_tool_results/<tool_call_id> and
        # /conversation_history/<...> back into ``skills_root`` on disk
        # (FilesystemBackend(virtual_mode=False) mirrors virtual paths
        # 1:1 to the host), which both pollutes the curated skills
        # directory and risks leaking binary bytes into git. Mirror the
        # CLI wiring from ``libs/cli/deepagents_cli/agent.py`` by
        # routing both prefixes to per-process tempdirs.
        resolved_backend = CompositeBackend(
            default=FilesystemBackend(root_dir=skills_root, virtual_mode=False),
            routes={
                "/large_tool_results/": FilesystemBackend(
                    root_dir=tempfile.mkdtemp(prefix="binary_analysis_large_results_"),
                    virtual_mode=True,
                ),
                "/conversation_history/": FilesystemBackend(
                    root_dir=tempfile.mkdtemp(
                        prefix="binary_analysis_conversation_history_"
                    ),
                    virtual_mode=True,
                ),
            },
        )
    sources = list(skills_sources) if skills_sources is not None else ["/"]

    return create_deep_agent(
        model=model,
        tools=tools,
        system_prompt=enhanced_system_prompt,
        skills=sources,
        backend=resolved_backend,
        middleware=list(extra_middleware),
    )
