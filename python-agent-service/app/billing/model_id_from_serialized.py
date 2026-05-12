"""Resolve gateway-style model_id (e.g. ``openai/gpt-4o``) from LangChain chat-model callbacks."""

from __future__ import annotations

from typing import Any


def _provider_from_serialized(serialized: dict[str, Any]) -> str | None:
    ids = serialized.get("id")
    if not isinstance(ids, (list, tuple)):
        return None
    path = ".".join(str(x) for x in ids).lower()
    if "anthropic" in path:
        return "anthropic"
    if "openai" in path:
        return "openai"
    if "google" in path or "genai" in path:
        return "google"
    if "moonshot" in path or "kimi" in path:
        return "kimi"
    if "zhipu" in path or "glm" in path:
        return "glm"
    if "deepseek" in path:
        return "deepseek"
    return None


def _nested_serial(
    serialized: dict[str, Any], skw: dict[str, Any]
) -> dict[str, Any] | None:
    """RunnableBinding / pipeline may nest the real chat model under ``bound`` / ``first``."""
    for container in (serialized, skw):
        bound = container.get("bound")
        if isinstance(bound, dict) and bound.get("kwargs") is not None:
            return bound
        first = container.get("first")
        if isinstance(first, dict) and first.get("kwargs") is not None:
            return first
    return None


def _model_name_from_maps(inv: dict[str, Any], skw: dict[str, Any]) -> str | None:
    for key in ("model", "model_name", "model_id", "model_kwargs"):
        v = inv.get(key) if isinstance(inv, dict) else None
        if v is None:
            v = skw.get(key) if isinstance(skw, dict) else None
        if isinstance(v, str) and v.strip():
            return v.strip()
        if key == "model_kwargs" and isinstance(v, dict):
            inner = v.get("model") or v.get("model_name")
            if isinstance(inner, str) and inner.strip():
                return inner.strip()
    return None


def resolve_gateway_model_id_from_chat_start(
    serialized: dict[str, Any],
    *,
    kwargs: dict[str, Any] | None = None,
) -> str | None:
    """Best-effort gateway id for pricing rows (``provider/sdk_model``).

    Falls back to nested Runnable (binding) shapes. Returns ``None`` if unknown.
    """
    if not isinstance(serialized, dict):
        return None
    kw = kwargs or {}
    inv = kw.get("invocation_params") if isinstance(kw.get("invocation_params"), dict) else {}
    skw = serialized.get("kwargs") if isinstance(serialized.get("kwargs"), dict) else {}

    model_name = _model_name_from_maps(inv, skw)
    provider = _provider_from_serialized(serialized)

    if model_name and "/" in model_name and not model_name.startswith("http"):
        return model_name

    if provider and model_name:
        return f"{provider}/{model_name}"

    nested = _nested_serial(serialized, skw)
    if nested is not None:
        inner = resolve_gateway_model_id_from_chat_start(nested, kwargs=kw)
        if inner:
            return inner

    return None
