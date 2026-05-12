"""Legacy LangChain callback: record LLM token usage on a single wrapped model.

Analyze streaming now uses :class:`LlmUsagePerInvokeCallbackHandler` in
``deepagents_stream_adapter`` / subagent invoke so **every** graph LLM call is
billed with the **per-invoke** model id. This module is kept for reference
and any non-stream call sites that might attach it explicitly.
"""

from __future__ import annotations

from typing import Any

import structlog
from langchain_core.callbacks import AsyncCallbackHandler
from langchain_core.outputs import LLMResult

from app.billing.pricing import extract_token_usage_from_llm_result
from app.billing.usage_record import record_llm_usage_event_async
from app.llm_gateway.request_context import get_request_llm_model_id
from app.analyze_request_context import (
    get_analyze_project_id,
    get_analyze_request_id,
    get_analyze_user_id,
)

logger = structlog.get_logger()


class LlmUsageRecordingCallbackHandler(AsyncCallbackHandler):
    """On each LLM completion, insert ``llm_usage_events`` when user context exists."""

    async def on_llm_end(
        self,
        response: LLMResult,
        *,
        run_id: Any = None,
        parent_run_id: Any = None,
        **kwargs: Any,
    ) -> None:
        user_id = get_analyze_user_id()
        if not user_id:
            return

        model_id = get_request_llm_model_id() or ""
        if not model_id:
            logger.warning("llm_usage_skip_no_model_id", run_id=str(run_id))
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


def build_llm_usage_callback_handler() -> LlmUsageRecordingCallbackHandler:
    return LlmUsageRecordingCallbackHandler()
