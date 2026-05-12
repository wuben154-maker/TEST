"""Per-request authenticated user id for downstream tool execution.

HTTP handlers set this from ``Depends(get_optional_user)`` so SOC tools that omit
``user_id`` in LLM tool calls can still resolve persistent vendor credentials.
"""

from __future__ import annotations

from contextvars import ContextVar, Token

_request_user_id: ContextVar[str | None] = ContextVar("request_user_id", default=None)


def get_request_user_id() -> str | None:
    """Effective user id for the current async context, if any."""
    rid = _request_user_id.get()
    if isinstance(rid, str):
        rid = rid.strip()
    return rid or None


def set_request_user_id(user_id: str | None) -> Token[str | None]:
    """Bind user id for downstream tool calls. Returns token for ``reset``."""
    return _request_user_id.set(user_id)


def reset_request_user_id(token: Token[str | None]) -> None:
    """Restore previous context (call from ``finally``)."""
    _request_user_id.reset(token)
