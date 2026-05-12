"""Tests for ``usage`` + ``modelId`` fields on llm_invoke_start / llm_invoke_end events.

These fields feed the frontend realtime context-usage indicator. The start
event carries the resolved gateway ``modelId`` and the end event carries the
extracted ``usage`` from the LLM response (``inputTokens`` / ``outputTokens``).

See: docs/Process/realtime-context-usage-indicator/acceptance.md (A-01, A-02, A-05, A-07).
"""

from __future__ import annotations

from types import SimpleNamespace
from uuid import uuid4

import pytest
from langchain_core.messages import AIMessage
from langchain_core.outputs import ChatGeneration, LLMResult

from app.parsers.llm_invoke_callbacks import LlmInvokeLifecycleCallbackHandler


def _make_handler():
    events: list[dict] = []
    handler = LlmInvokeLifecycleCallbackHandler(emit_event=events.append)
    return handler, events


def _llm_result_with_usage(input_tokens: int, output_tokens: int) -> LLMResult:
    msg = AIMessage(
        content="ok",
        usage_metadata={
            "input_tokens": input_tokens,
            "output_tokens": output_tokens,
            "total_tokens": input_tokens + output_tokens,
        },
    )
    gen = ChatGeneration(message=msg)
    return LLMResult(generations=[[gen]], llm_output={"token_usage": {
        "prompt_tokens": input_tokens,
        "completion_tokens": output_tokens,
    }})


def _llm_result_without_usage() -> LLMResult:
    msg = AIMessage(content="ok")
    gen = ChatGeneration(message=msg)
    return LLMResult(generations=[[gen]], llm_output={})


class TestLlmInvokeEndUsage:
    """A-01 / A-05 / A-07 — llm_invoke_end must carry ``usage``."""

    @pytest.mark.asyncio
    async def test_end_event_carries_usage_when_response_has_metadata(self):
        handler, events = _make_handler()
        run_id = uuid4()
        await handler.on_chat_model_start({}, [[]], run_id=run_id)
        await handler.on_llm_end(_llm_result_with_usage(12345, 678), run_id=run_id)
        end_events = [e for e in events if e["type"] == "llm_invoke_end"]
        assert len(end_events) == 1
        assert end_events[0]["usage"] == {"inputTokens": 12345, "outputTokens": 678}

    @pytest.mark.asyncio
    async def test_end_event_has_zero_usage_when_provider_omits_metadata(self):
        """A-05 — zero-usage fallback, event still emitted."""
        handler, events = _make_handler()
        run_id = uuid4()
        await handler.on_chat_model_start({}, [[]], run_id=run_id)
        await handler.on_llm_end(_llm_result_without_usage(), run_id=run_id)
        end_events = [e for e in events if e["type"] == "llm_invoke_end"]
        assert len(end_events) == 1
        assert end_events[0]["usage"] == {"inputTokens": 0, "outputTokens": 0}

    @pytest.mark.asyncio
    async def test_end_event_has_zero_usage_on_error_path(self):
        """A-07 — on_llm_error emits end with zero usage, no exception escapes."""
        handler, events = _make_handler()
        run_id = uuid4()
        await handler.on_chat_model_start({}, [[]], run_id=run_id)
        await handler.on_llm_error(RuntimeError("boom"), run_id=run_id)
        end_events = [e for e in events if e["type"] == "llm_invoke_end"]
        assert len(end_events) == 1
        assert end_events[0]["usage"] == {"inputTokens": 0, "outputTokens": 0}

    @pytest.mark.asyncio
    async def test_end_event_tolerates_non_llmresult_response(self):
        """Legacy tests pass ``object()`` as response; must not crash — usage falls back to 0/0."""
        handler, events = _make_handler()
        run_id = uuid4()
        await handler.on_chat_model_start({}, [[]], run_id=run_id)
        await handler.on_llm_end(object(), run_id=run_id)
        end_events = [e for e in events if e["type"] == "llm_invoke_end"]
        assert len(end_events) == 1
        assert end_events[0]["usage"] == {"inputTokens": 0, "outputTokens": 0}


class TestLlmInvokeStartModelId:
    """A-02 — llm_invoke_start carries ``modelId`` (provider/model)."""

    @pytest.mark.asyncio
    async def test_start_event_has_modelid_for_anthropic_serialized(self):
        handler, events = _make_handler()
        run_id = uuid4()
        serialized = {
            "id": ["langchain", "chat_models", "anthropic", "ChatAnthropic"],
            "kwargs": {"model": "claude-sonnet-4-20250514"},
        }
        await handler.on_chat_model_start(serialized, [[]], run_id=run_id)
        start = [e for e in events if e["type"] == "llm_invoke_start"][0]
        assert start["modelId"] == "anthropic/claude-sonnet-4-20250514"

    @pytest.mark.asyncio
    async def test_start_event_has_modelid_for_prefixed_model(self):
        """When model already contains ``provider/model`` form, keep it as-is."""
        handler, events = _make_handler()
        run_id = uuid4()
        serialized = {
            "id": ["langchain", "chat_models", "openai", "ChatOpenAI"],
            "kwargs": {"model": "openai/gpt-4o"},
        }
        await handler.on_chat_model_start(serialized, [[]], run_id=run_id)
        start = [e for e in events if e["type"] == "llm_invoke_start"][0]
        assert start["modelId"] == "openai/gpt-4o"

    @pytest.mark.asyncio
    async def test_start_event_modelid_absent_when_unresolvable(self):
        """When no provider + no model in serialized, modelId field is omitted (not a crash)."""
        handler, events = _make_handler()
        run_id = uuid4()
        await handler.on_chat_model_start({}, [[]], run_id=run_id)
        start = [e for e in events if e["type"] == "llm_invoke_start"][0]
        # Either absent or empty string, but must not crash.
        assert "modelId" not in start or start["modelId"] in (None, "")
