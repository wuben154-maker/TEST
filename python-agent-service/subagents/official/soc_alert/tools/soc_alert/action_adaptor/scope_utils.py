"""Shared helpers for resolving auth scope ids."""

from __future__ import annotations

from typing import Any


def first_nonempty_str(*values: Any) -> str | None:
    """Return the first non-empty string value."""
    for value in values:
        if isinstance(value, str) and value.strip():
            return value.strip()
    return None


def derive_auth_scope(
    *,
    explicit_session_id: str | None,
    explicit_request_id: str | None,
    explicit_user_id: str | None,
    raw_alert_context: dict[str, Any] | None,
) -> tuple[str | None, str | None, str | None]:
    """Resolve auth scope ids with explicit args first, then raw alert context."""
    context = raw_alert_context if isinstance(raw_alert_context, dict) else {}
    context_meta = context.get("context")
    context_meta = context_meta if isinstance(context_meta, dict) else {}
    meta = context.get("meta")
    meta = meta if isinstance(meta, dict) else {}

    session_id = first_nonempty_str(
        explicit_session_id,
        context.get("session_id"),
        context.get("sessionId"),
        context_meta.get("session_id"),
        context_meta.get("sessionId"),
        meta.get("session_id"),
        meta.get("sessionId"),
    )
    request_id = first_nonempty_str(
        explicit_request_id,
        context.get("request_id"),
        context.get("requestId"),
        context_meta.get("request_id"),
        context_meta.get("requestId"),
        meta.get("request_id"),
        meta.get("requestId"),
    )
    user_id = first_nonempty_str(
        explicit_user_id,
        context.get("user_id"),
        context.get("userId"),
        context_meta.get("user_id"),
        context_meta.get("userId"),
        meta.get("user_id"),
        meta.get("userId"),
    )
    return session_id, request_id, user_id
