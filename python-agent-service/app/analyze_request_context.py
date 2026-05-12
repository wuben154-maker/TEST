"""Per-analyze HTTP request: user_id, project_id, request_id for tools and billing.

Lives outside ``app.middleware`` so billing and parsers can import it without
pulling ``app.middleware``'s heavy ``__init__`` (deepagents), which would cycle
with ``subagents`` ↔ ``deepagents_stream_adapter``.
"""

from __future__ import annotations

from contextvars import ContextVar, Token

_analyze_user_id: ContextVar[str | None] = ContextVar("analyze_user_id", default=None)
_analyze_project_id: ContextVar[str | None] = ContextVar("analyze_project_id", default=None)
_analyze_request_id: ContextVar[str | None] = ContextVar("analyze_request_id", default=None)
_analyze_session_id: ContextVar[str | None] = ContextVar("analyze_session_id", default=None)


def get_analyze_user_id() -> str | None:
    return _analyze_user_id.get()


def get_analyze_project_id() -> str | None:
    return _analyze_project_id.get()


def get_analyze_request_id() -> str | None:
    return _analyze_request_id.get()


def get_analyze_session_id() -> str | None:
    return _analyze_session_id.get()


def set_analyze_request_context(
    *,
    user_id: str | None,
    project_id: str | None,
    request_id: str | None = None,
    session_id: str | None = None,
) -> tuple[
    Token[str | None],
    Token[str | None],
    Token[str | None],
    Token[str | None],
]:
    """Bind tenant scope for the current async context. Returns tokens for ``reset``."""
    return (
        _analyze_user_id.set(user_id),
        _analyze_project_id.set(project_id),
        _analyze_request_id.set(request_id or ""),
        _analyze_session_id.set(session_id),
    )


def reset_analyze_request_context(
    user_token: Token[str | None],
    project_token: Token[str | None],
    request_token: Token[str | None],
    session_token: Token[str | None],
) -> None:
    _analyze_session_id.reset(session_token)
    _analyze_request_id.reset(request_token)
    _analyze_project_id.reset(project_token)
    _analyze_user_id.reset(user_token)
