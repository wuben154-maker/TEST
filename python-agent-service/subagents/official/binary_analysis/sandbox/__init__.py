"""Sandbox client abstraction and backends (ADR-05 / ADR-16).

Public surface:

- :class:`SandboxClient`  — :class:`typing.Protocol` every backend satisfies.
- :class:`SandboxSession` — opaque per-analysis handle.
- :class:`ExecResult`     — normalised result of :meth:`SandboxClient.exec`.
- :func:`build_binary_sandbox_client` — subprocess vs E2B factory (CLI, LangGraph,
  Deep Agent registry).
- :func:`get_sandbox_client` — alias for ``build_binary_sandbox_client()`` with no
  explicit overrides.
- :class:`SubprocessBackend` — ADR-16 fallback backend.
- :class:`SandboxSessionTool` — LangChain tool exposing the lifecycle to
  the Agent.
"""

from sandbox.client import (
    ExecResult,
    SandboxClient,
    SandboxSession,
    get_sandbox_client,
    sandbox_workspace,
    upload_sample_to_sandbox,
    validate_sandbox_path,
)
from sandbox.factory import build_binary_sandbox_client
from sandbox.registry import (
    all_analysis_ids,
    get_or_create_session,
    get_session,
    register_session,
    unregister_session,
)
from sandbox.session_tool import (
    SandboxSessionInput,
    SandboxSessionTool,
)
from sandbox.subprocess_backend import SubprocessBackend

__all__ = [
    "ExecResult",
    "SandboxClient",
    "SandboxSession",
    "SandboxSessionInput",
    "SandboxSessionTool",
    "SubprocessBackend",
    "build_binary_sandbox_client",
    "all_analysis_ids",
    "get_or_create_session",
    "get_sandbox_client",
    "get_session",
    "register_session",
    "sandbox_workspace",
    "unregister_session",
    "upload_sample_to_sandbox",
    "validate_sandbox_path",
]
