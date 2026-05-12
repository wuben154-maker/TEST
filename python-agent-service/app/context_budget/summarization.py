"""SECManus summarization middleware — adds provider-meter OR-trigger."""

from __future__ import annotations

from typing import Any

import structlog
from langchain.chat_models import BaseChatModel as RuntimeBaseChatModel
from langchain_core.messages import AnyMessage

from app._vendor.deepagents.middleware.summarization import (
    SummarizationMiddleware,
    compute_summarization_defaults,
)
from app.config import get_settings
from app.context_budget.meter import ContextMeter
from app.context_budget.window import resolve_context_window
from langgraph.config import get_config

logger = structlog.get_logger()


class SecmanusSummarizationMiddleware(SummarizationMiddleware):
    """DeepAgents summarization plus optional compression when provider usage passes ratio."""

    def _should_summarize(self, messages: list[AnyMessage], total_tokens: int) -> bool:
        if super()._should_summarize(messages, total_tokens):
            return True
        s = get_settings()
        if not s.context_compress_enable_provider_meter:
            return False
        try:
            cfg = get_config()
            meter = (cfg.get("configurable") or {}).get("_context_meter")
            if not isinstance(meter, ContextMeter):
                return False
            if meter.last_main_input_tokens <= 0:
                return False
            window = resolve_context_window(meter.last_main_model_id)
            if window <= 0:
                return False
            ratio = float(meter.last_main_input_tokens) / float(window)
            thr = float(s.context_compress_trigger_ratio)
            if ratio >= thr:
                logger.info(
                    "summarization_provider_meter_trigger",
                    ratio=round(ratio, 4),
                    threshold=thr,
                    prompt_tokens=meter.last_main_input_tokens,
                    window=window,
                )
                return True
        except Exception as exc:  # noqa: BLE001
            logger.debug("summarization_provider_meter_check_failed", error=str(exc))
        return False


def create_secmanus_summarization_middleware(
    model: RuntimeBaseChatModel,
    backend: Any,
) -> SecmanusSummarizationMiddleware:
    if not isinstance(model, RuntimeBaseChatModel):
        msg = "`create_secmanus_summarization_middleware` expects a `BaseChatModel` instance."
        raise TypeError(msg)
    defaults = compute_summarization_defaults(model)
    return SecmanusSummarizationMiddleware(
        model=model,
        backend=backend,
        trigger=defaults["trigger"],
        keep=defaults["keep"],
        trim_tokens_to_summarize=None,
        truncate_args_settings=defaults["truncate_args_settings"],
    )
