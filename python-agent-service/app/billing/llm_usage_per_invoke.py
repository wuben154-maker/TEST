"""Bill each LLM completion using the model instance for that invoke (main + subagent graphs)."""

from __future__ import annotations

from typing import Any
from uuid import UUID

import structlog
from langchain_core.callbacks import AsyncCallbackHandler

from app.billing.model_id_from_serialized import resolve_gateway_model_id_from_chat_start
from app.billing.pricing import extract_token_usage_from_llm_result
from app.analyze_request_context import (
    get_analyze_project_id,
    get_analyze_request_id,
    get_analyze_user_id,
)
from app.billing.usage_record import record_llm_usage_event_async
from app.llm_gateway.request_context import get_request_llm_model_id

logger = structlog.get_logger()


class LlmUsagePerInvokeCallbackHandler(AsyncCallbackHandler):
    """Record ``llm_usage_events`` on every ``on_llm_end`` (paired with ``on_chat_model_start``).

    Attached once at the analyze stream config (and deduped when merged into subagent configs).
    Uses per-run model id from LangChain serialization, not only the request default.
    """

    def __init__(self) -> None:
        super().__init__()
        self._run_to_model: dict[UUID, str] = {}

    @staticmethod
    def _norm_run_id(run_id: Any) -> UUID | None:
        if run_id is None:
            return None
        if isinstance(run_id, UUID):
            return run_id
        try:
            return UUID(str(run_id))
        except (ValueError, TypeError):
            return None

    async def on_chat_model_start(
        self,
        serialized: dict[str, Any],
        messages: list[Any],
        *,
        run_id: Any,
        **kwargs: Any,
    ) -> None:
        rid = self._norm_run_id(run_id)
        if rid is None:
            return
        resolved = resolve_gateway_model_id_from_chat_start(serialized, kwargs=kwargs)
        req = get_request_llm_model_id() or ""

        def _tail(mid: str) -> str:
            return mid.rsplit("/", 1)[-1] if "/" in mid else mid

        # Prefer request-scoped gateway id when it matches this invoke's SDK model name
        # (e.g. ChatOpenAI serializes as openai/* while UI selected opencode/*).
        if resolved and req and _tail(resolved) == _tail(req):
            self._run_to_model[rid] = req
        elif resolved:
            self._run_to_model[rid] = resolved
        else:
            self._run_to_model[rid] = req

    async def on_llm_end(self, response: Any, *, run_id: Any, **kwargs: Any) -> None:
        rid = self._norm_run_id(run_id)
        if rid is None:
            return
        model_id = self._run_to_model.pop(rid, None)
        if not model_id:
            model_id = get_request_llm_model_id() or ""

        user_id = get_analyze_user_id()
        if not user_id:
            return
        if not model_id:
            logger.warning("llm_usage_per_invoke_skip_no_model_id", run_id=str(rid))
            return

        pt, ct = extract_token_usage_from_llm_result(response)
        if pt == 0 and ct == 0:
            return

        await record_llm_usage_event_async(
            user_id=user_id,
            project_id=get_analyze_project_id(),
            request_id=get_analyze_request_id() or "",
            model_id=model_id,
            prompt_tokens=pt,
            completion_tokens=ct,
        )

    async def on_llm_error(
        self, error: BaseException, *, run_id: Any, **kwargs: Any
    ) -> None:
        rid = self._norm_run_id(run_id)
        if rid is not None:
            self._run_to_model.pop(rid, None)
