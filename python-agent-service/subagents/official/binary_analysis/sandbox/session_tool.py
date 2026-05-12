"""SandboxSessionTool — LangChain tool for sandbox lifecycle (C4-AC5 / §2.3.2).

Exposes three actions to the Agent:

- ``create`` — provision a sandbox for the given ``analysis_id`` and return
  its handle.
- ``kill``   — destroy the sandbox (idempotent; returns ``killed=False``
  when the session did not exist).
- ``info``   — look up the current session handle for ``analysis_id``.

The tool is async-only because the underlying :class:`SandboxClient`
Protocol is async; callers should use :meth:`~langchain_core.tools.BaseTool.ainvoke`.
"""

from __future__ import annotations

from typing import Any, Literal

from langchain_core.tools import BaseTool
from pydantic import BaseModel

from errors import BinaryAnalysisError
from sandbox.client import SandboxClient, SandboxSession
from sandbox.registry import get_or_create_session, get_session


class SandboxSessionInput(BaseModel):
    """Input schema for :class:`SandboxSessionTool`."""

    action: Literal["create", "kill", "info"]
    analysis_id: str


class SandboxSessionTool(BaseTool):
    """LangChain tool for managing the per-analysis sandbox session (ADR-16).

    Args:
        client: A concrete :class:`SandboxClient` implementation
            (typically obtained from
            :func:`~sandbox.client.get_sandbox_client`).
    """

    name: str = "sandbox_session"
    description: str = (
        "Manage the per-analysis sandbox session. "
        "Actions: "
        "'create' — provision a sandbox for the given analysis_id and return its handle; "
        "'kill' — destroy the sandbox (idempotent); "
        "'info' — return the current session handle for analysis_id, or None if absent."
    )
    args_schema: type[BaseModel] = SandboxSessionInput
    # Use `Any` rather than `SandboxClient` so Pydantic does not attempt to
    # build a schema for the structural Protocol type.
    client: Any

    model_config = {"arbitrary_types_allowed": True}

    def _run(self, **kwargs: Any) -> Any:  # type: ignore[override]  # pragma: no cover
        """The subprocess/E2B backends are async-only; use :meth:`ainvoke`."""
        msg = (
            "SandboxSessionTool is async-only; invoke via "
            ".ainvoke(...) rather than .invoke(...)."
        )
        raise NotImplementedError(msg)

    async def _arun(self, **kwargs: Any) -> dict[str, Any]:  # type: ignore[override]
        """Dispatch to the action handler corresponding to ``kwargs['action']``."""
        inp = SandboxSessionInput(**kwargs)
        client: SandboxClient = self.client
        if inp.action == "create":
            # Atomic get-or-create via shared registry helper — serialises
            # the check-or-create window per ``analysis_id`` so parallel
            # LLM tool calls (e.g. ``sandbox_session(action=create)``
            # racing against ``file_identify``'s ``_ensure_session``) do
            # not each spin up a distinct remote sandbox (FB-F-02). The
            # single-session guarantee is preserved; redundant calls are
            # idempotent.
            try:
                session = await get_or_create_session(client, inp.analysis_id)
            except Exception as exc:
                return _exception_to_result(
                    exc,
                    analysis_id=inp.analysis_id,
                    reason="sandbox_create_failed",
                    default_error_code="SANDBOX_UNAVAILABLE",
                )
            return _session_to_dict(session)
        if inp.action == "info":
            session = await get_session(inp.analysis_id)
            return (
                _session_to_dict(session)
                if session is not None
                else {"ok": True, "session": None}
            )
        # action == "kill"
        session = await get_session(inp.analysis_id)
        if session is None:
            return {"ok": True, "killed": False, "analysis_id": inp.analysis_id}
        try:
            await client.kill(session)
        except Exception as exc:
            return _exception_to_result(
                exc,
                analysis_id=inp.analysis_id,
                reason="sandbox_kill_failed",
                default_error_code="TOOL_CRASH",
            )
        return {"ok": True, "killed": True, "analysis_id": inp.analysis_id}


def _session_to_dict(session: SandboxSession) -> dict[str, Any]:
    """Serialise a :class:`SandboxSession` to a tool-output-safe mapping.

    Omits ``host_workdir`` and ``raw`` so Agent-visible output never leaks
    host filesystem paths or backend-specific opaque objects.
    """
    return {
        "ok": True,
        "analysis_id": session.analysis_id,
        "sandbox_id": session.sandbox_id,
        "backend": session.backend,
        "workdir": session.workdir,
        "created_at": session.created_at,
    }


def _exception_to_result(
    exc: Exception,
    *,
    analysis_id: str,
    reason: str,
    default_error_code: str,
) -> dict[str, Any]:
    """Convert sandbox backend failures into recoverable ToolMessages."""
    if isinstance(exc, BinaryAnalysisError):
        details = dict(exc.details)
        message = exc.message
        error_code = exc.error_code
    else:
        details = {}
        message = str(exc) or type(exc).__name__
        error_code = default_error_code

    details.setdefault("reason", reason)
    details.setdefault("analysis_id", analysis_id)
    details.setdefault("error_type", type(exc).__name__)
    return {
        "ok": False,
        "error_code": error_code,
        "reason": details.get("reason"),
        "message": message,
        "details": details,
    }
