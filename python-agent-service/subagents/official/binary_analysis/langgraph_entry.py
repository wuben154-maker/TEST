"""LangGraph dev entrypoint for deep-agents-ui integration.

This module exposes the BinaryAnalyst agent as a per-thread graph factory
consumed by ``langgraph-cli[inmem]`` (see sibling ``langgraph.json``).
The factory signature — ``make_graph(config) -> CompiledStateGraph`` — is
the shape recognised by the LangGraph server; it is invoked once per
thread so every session receives its own :class:`EvidenceChainStore`
instance, preserving the FR-09 / ADR-02 append-only invariant.

Differences from :mod:`api`:

- :func:`binary_analysis.api.analyze_binary` drives a single sample end
  to end and relies on a caller-supplied host path. The UI workflow
  instead has the analyst paste a host-side absolute path into the first
  message; ``FileIdentifyTool`` still performs the sandbox upload so
  ADR-05 "zero execution on host" and NFR-03 "sample bytes never enter
  the LLM request body" remain intact.
- ``analysis_id`` is derived from the LangGraph ``thread_id`` so the
  audit log correlates with the UI thread.
"""

from __future__ import annotations

import os
import tempfile
from pathlib import Path
from typing import TYPE_CHECKING, Any

from deepagents.backends.composite import CompositeBackend
from deepagents.backends.filesystem import FilesystemBackend

from analyst_graph import build_binary_analyst_agent
from api import (
    _locate_skills_root,
    _resolve_model_id,
    init_binary_analysis_chat_model,
)
from config import settings as _settings_factory
from evidence_chain.store import EvidenceChainStore
from report_bootstrap import ReportBootstrapMiddleware
from sandbox.factory import build_binary_sandbox_client
from ui_backend import ROUTE_PREFIX, UploadsStateBackend
from upload_materializer import UploadMaterializerMiddleware

if TYPE_CHECKING:  # pragma: no cover
    from langchain.tools import ToolRuntime
    from langchain_core.runnables import RunnableConfig
    from langgraph.graph.state import CompiledStateGraph

# Dev server default; `analyze_binary` keeps its own (higher) cap. Overridable
# via the same `BINARY_ANALYSIS_RECURSION_LIMIT` env var honored by `api.py`.
_DEFAULT_DEV_RECURSION_LIMIT = 300

# Ephemeral roots for :class:`~deepagents.middleware.filesystem.FilesystemMiddleware`
# eviction sinks (``/large_tool_results/`` and ``/conversation_history/``).
# Created once per process — not per thread — so multiple LangGraph sessions
# share one tempdir tree and we do not leak a new directory on every
# ``make_graph`` call. These MUST be routed away from the skills-root
# FilesystemBackend; otherwise the middleware would write oversized tool
# payloads back into ``examples/binary_analysis/skills/`` on disk and pollute
# the curated skills tree / git status (see ``libs/cli/deepagents_cli/agent.py``
# for the canonical wiring this mirrors).
_LARGE_RESULTS_ROOT = Path(tempfile.mkdtemp(prefix="binary_analysis_large_results_"))
_CONVERSATION_HISTORY_ROOT = Path(
    tempfile.mkdtemp(prefix="binary_analysis_conversation_history_")
)

# Host-side root for FR-15 report artefacts produced by ``report_gen``. The
# LangGraph dev path does not run through ``api._build_initial_prompt`` which
# normally tells the agent a concrete ``output_dir``; without that hint the
# LLM tends to guess a sandbox path (``/workspace/<analysis_id>/output``),
# which ``ReportGenTool`` silently resolves against the host filesystem (and
# then the agent's follow-up ``file_read`` — sandbox-only — fails). We
# pre-create a stable host root once per process and let
# :class:`ReportBootstrapMiddleware` publish a per-thread sub-directory to
# the agent as a SystemMessage.
_REPORTS_ROOT = Path(tempfile.mkdtemp(prefix="binary_analysis_reports_"))


def _resolve_dev_recursion_limit() -> int:
    """Resolve the LangGraph `recursion_limit` for the dev server path.

    Returns:
        Integer cap; falls back to `_DEFAULT_DEV_RECURSION_LIMIT` when the
        `BINARY_ANALYSIS_RECURSION_LIMIT` env var is unset or non-numeric.
    """
    raw = os.environ.get("BINARY_ANALYSIS_RECURSION_LIMIT", "").strip()
    if not raw:
        return _DEFAULT_DEV_RECURSION_LIMIT
    try:
        return int(raw)
    except ValueError:
        return _DEFAULT_DEV_RECURSION_LIMIT


def _force_recursion_limit(graph: CompiledStateGraph, floor: int) -> CompiledStateGraph:
    """Raise `graph`'s effective `recursion_limit` to at least `floor`.

    Why this cannot be done with `with_config` / `RunnableBinding`:

    1. LangSmith Studio (and some other LangGraph clients) hard-code
       `recursion_limit=100` in their run request.
    2. `CompiledStateGraph.astream` / `.ainvoke` merge config via
       `ensure_config(self.config, incoming)` — **last wins, direct
       overwrite**. So a Pregel-level `self.config["recursion_limit"]=300`
       is silently clobbered by the incoming 100.
    3. Wrapping the graph in a `RunnableBinding` with `config_factories`
       (which run after the merge) does pin the limit at runtime, but the
       LangGraph server validates the factory result with
       `isinstance(graph_obj, Pregel | BaseRemotePregel)` and rejects any
       wrapper with `HTTPException 424`.

    The only path that satisfies both constraints is to return the exact
    Pregel instance the server expects, while intercepting the streaming
    entry points to bump any caller-supplied `recursion_limit` below
    `floor` up to `floor`. We do this by promoting the instance's class to
    an anonymous Pregel subclass that overrides the five runtime entry
    points the server calls (`invoke` / `ainvoke` / `stream` / `astream` /
    `astream_events`). All other introspection methods (`aget_state`,
    `get_context_jsonschema`, etc.) continue to resolve on the original
    Pregel class unchanged.

    Args:
        graph: The compiled LangGraph produced by
            `build_binary_analyst_agent`.
        floor: The minimum `recursion_limit` to enforce; caller-supplied
            values at or above `floor` are preserved as-is.

    Returns:
        The same `graph` instance, with its `__class__` promoted to a
        subclass that pins `recursion_limit` on every run.
    """
    base_cls = type(graph)

    def _pin(config: RunnableConfig | None) -> RunnableConfig:
        merged: dict[str, Any] = dict(config) if config else {}
        if int(merged.get("recursion_limit", 0) or 0) < floor:
            merged["recursion_limit"] = floor
        return merged  # type: ignore[return-value]

    class _RecursionLimitPinned(base_cls):  # type: ignore[misc,valid-type]
        """Pregel subclass that raises `recursion_limit` to at least `floor`."""

        def invoke(  # type: ignore[override]
            self,
            input: Any,  # noqa: A002
            config: RunnableConfig | None = None,
            **kwargs: Any,
        ) -> Any:
            return super().invoke(input, _pin(config), **kwargs)

        async def ainvoke(  # type: ignore[override]
            self,
            input: Any,  # noqa: A002
            config: RunnableConfig | None = None,
            **kwargs: Any,
        ) -> Any:
            return await super().ainvoke(input, _pin(config), **kwargs)

        def stream(  # type: ignore[override]
            self,
            input: Any,  # noqa: A002
            config: RunnableConfig | None = None,
            **kwargs: Any,
        ) -> Any:
            yield from super().stream(input, _pin(config), **kwargs)

        async def astream(  # type: ignore[override]
            self,
            input: Any,  # noqa: A002
            config: RunnableConfig | None = None,
            **kwargs: Any,
        ) -> Any:
            async for chunk in super().astream(input, _pin(config), **kwargs):
                yield chunk

        async def astream_events(  # type: ignore[override]
            self,
            input: Any,  # noqa: A002
            config: RunnableConfig | None = None,
            **kwargs: Any,
        ) -> Any:
            async for chunk in super().astream_events(input, _pin(config), **kwargs):
                yield chunk

    _RecursionLimitPinned.__name__ = f"{base_cls.__name__}WithRecursionFloor{floor}"
    _RecursionLimitPinned.__qualname__ = _RecursionLimitPinned.__name__

    graph.__class__ = _RecursionLimitPinned  # type: ignore[assignment]
    return graph


def make_graph(config: RunnableConfig) -> CompiledStateGraph:
    """Build a fresh BinaryAnalyst graph for each LangGraph thread.

    The LangGraph server calls this factory once per thread; the returned
    graph therefore owns its own :class:`EvidenceChainStore`, sandbox
    client, and tool instances — never shared across concurrent UI
    conversations.

    Args:
        config: Runtime configuration supplied by the LangGraph server.
            ``configurable.thread_id`` is used to bind the audit context
            and evidence-chain identifier to the UI session.

    Returns:
        Compiled :class:`CompiledStateGraph` ready for ``ainvoke`` /
        ``astream``.

    Raises:
        RuntimeError: No LLM provider credential is configured. Set one
            of ``BINARY_ANALYSIS_MODEL`` / ``GOOGLE_API_KEY`` /
            ``OPENAI_API_KEY`` / ``ANTHROPIC_API_KEY`` before starting
            the server.
    """
    model_id = _resolve_model_id()
    if model_id is None:
        msg = (
            "No LLM provider credential found. Set BINARY_ANALYSIS_MODEL "
            "(provider:model slug) or one of GOOGLE_API_KEY / "
            "OPENAI_API_KEY / ANTHROPIC_API_KEY before starting "
            "`langgraph dev`."
        )
        raise RuntimeError(msg)

    configurable = (config or {}).get("configurable") or {}
    thread_id = str(configurable.get("thread_id") or "langgraph-dev")

    cfg = _settings_factory()
    skills_root = _locate_skills_root()
    if not skills_root.is_dir():
        msg = (
            f"Skills root is missing: {skills_root}. The BinaryAnalyst agent "
            "requires the sibling `skills/` tree shipped alongside the "
            "package."
        )
        raise RuntimeError(msg)

    store = EvidenceChainStore(analysis_id=thread_id)
    sandbox_client = build_binary_sandbox_client(use_e2b=cfg.use_e2b)
    model = init_binary_analysis_chat_model(model_id)

    def _backend_factory(runtime: ToolRuntime) -> CompositeBackend:
        """Per-thread composite backend.

        * Default route → :class:`FilesystemBackend` scoped to
          ``skills_root`` so ``SkillsMiddleware`` and ``read_file`` work
          on a clean ``/`` virtual filesystem.
        * ``/uploaded/`` → :class:`UploadsStateBackend` reading
          ``runtime.state['files']['uploaded/*']`` the UI writes into
          state.
        * ``/large_tool_results/`` and ``/conversation_history/`` →
          ephemeral per-process tempdirs (see ``_LARGE_RESULTS_ROOT`` /
          ``_CONVERSATION_HISTORY_ROOT``). Without these overrides the
          default route would claim both prefixes and
          ``FilesystemMiddleware`` eviction would write multi-megabyte
          tool payloads into ``skills_root`` on the host filesystem,
          polluting the curated skills tree.

        ``CompositeBackend`` aggregates ``ls`` / ``glob`` / ``grep``
        results from both legs and preserves the original route prefix
        in returned paths, so the agent uniformly sees a flat
        ``/<skill>/...`` plus ``/uploaded/<name>`` namespace.
        """
        return CompositeBackend(
            default=FilesystemBackend(root_dir=skills_root, virtual_mode=True),
            routes={
                ROUTE_PREFIX: UploadsStateBackend(runtime),
                "/large_tool_results/": FilesystemBackend(
                    root_dir=_LARGE_RESULTS_ROOT, virtual_mode=True
                ),
                "/conversation_history/": FilesystemBackend(
                    root_dir=_CONVERSATION_HISTORY_ROOT, virtual_mode=True
                ),
            },
        )

    host_upload_root = Path(tempfile.gettempdir()) / "binary_analysis-uploads"
    materializer = UploadMaterializerMiddleware(
        host_upload_root=host_upload_root,
        thread_id_fallback=thread_id,
    )
    report_bootstrap = ReportBootstrapMiddleware(
        host_reports_root=_REPORTS_ROOT,
        thread_id_fallback=thread_id,
    )

    graph = build_binary_analyst_agent(
        model=model,
        store=store,
        sandbox_client=sandbox_client,
        skills_root=skills_root,
        backend=_backend_factory,
        extra_middleware=(materializer, report_bootstrap),
    )
    # LangSmith Studio and similar clients hard-code `recursion_limit=100`
    # in their run request; `graph.with_config({...})` would be merged
    # BEFORE the client config and silently clobbered. Use a config factory
    # instead: it merges AFTER the client payload, pinning the effective
    # cap regardless of caller intent. See `_force_recursion_limit`.
    return _force_recursion_limit(graph, _resolve_dev_recursion_limit())


__all__ = ["make_graph"]
