"""Resolve prompt budget (context window) from gateway catalog."""

from __future__ import annotations

from app.llm_gateway.registry import DEFAULT_CONTEXT_WINDOW, get_registry


def resolve_context_window(model_id: str | None) -> int:
    """Return ``context_window`` for a gateway model id, or ``DEFAULT_CONTEXT_WINDOW``."""
    if not model_id or not str(model_id).strip():
        return DEFAULT_CONTEXT_WINDOW
    mid = str(model_id).strip()
    cfg = get_registry().get_model_config(mid)
    if not cfg:
        return DEFAULT_CONTEXT_WINDOW
    model = cfg.get("model") or {}
    raw = model.get("context_window")
    if isinstance(raw, int) and raw > 0:
        return raw
    return DEFAULT_CONTEXT_WINDOW
