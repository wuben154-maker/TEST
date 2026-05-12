"""LLM Gateway: unified model registry and factory."""

from app.llm_gateway.factory import get_model
from app.llm_gateway.registry import ModelInfo, ModelRegistry, get_registry
from app.llm_gateway.request_context import (
    get_request_llm_model_id,
    reset_request_llm_model_id,
    set_request_llm_model_id,
)


def list_models() -> list[dict]:
    """Return list of available models for API response.

    Includes ``context_window`` and ``max_output_tokens`` so the frontend can
    render the realtime context-usage indicator with a per-model divisor.
    """
    return [
        {
            "id": m.id,
            "name": m.name,
            "provider": m.provider,
            "context_window": m.context_window,
            "max_output_tokens": m.max_output_tokens,
        }
        for m in get_registry().list_models()
    ]


__all__ = [
    "get_model",
    "get_registry",
    "get_request_llm_model_id",
    "list_models",
    "ModelInfo",
    "ModelRegistry",
    "reset_request_llm_model_id",
    "set_request_llm_model_id",
]
