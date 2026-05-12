"""Per-request LLM model id (gateway id, e.g. ``opencode/claude-sonnet-4-6``).

Set by ``stream_analyze_request`` / ``stream_resume_request`` so tools and
subgraphs that call ``get_model()`` without an explicit id use the same model as the UI.
"""

from __future__ import annotations

from contextvars import ContextVar, Token

_request_llm_model_id: ContextVar[str | None] = ContextVar("request_llm_model_id", default=None)


def get_request_llm_model_id() -> str | None:
    """Effective gateway model id for the current async context, if any."""
    return _request_llm_model_id.get()


def set_request_llm_model_id(model_id: str | None) -> Token[str | None]:
    """Bind model id for downstream ``get_model(None)`` calls. Returns token for ``reset``."""
    return _request_llm_model_id.set(model_id)


def reset_request_llm_model_id(token: Token[str | None]) -> None:
    """Restore previous context (call from ``finally``)."""
    _request_llm_model_id.reset(token)
