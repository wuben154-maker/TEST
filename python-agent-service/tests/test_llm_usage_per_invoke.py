"""Tests for per-invoke LLM usage callback."""

from __future__ import annotations

from unittest.mock import AsyncMock, patch
from uuid import uuid4

import pytest
from langchain_core.outputs import LLMResult

from app.billing.llm_usage_per_invoke import LlmUsagePerInvokeCallbackHandler


@pytest.mark.asyncio
async def test_records_on_llm_end_with_serialized_model():
    run_id = uuid4()
    ser = {
        "id": ["langchain", "chat_models", "openai", "ChatOpenAI"],
        "kwargs": {"model": "gpt-4o-mini"},
    }
    handler = LlmUsagePerInvokeCallbackHandler()

    with (
        patch(
            "app.billing.llm_usage_per_invoke.get_analyze_user_id",
            return_value="550e8400-e29b-41d4-a716-446655440000",
        ),
        patch(
            "app.billing.llm_usage_per_invoke.get_analyze_project_id",
            return_value=None,
        ),
        patch("app.billing.llm_usage_per_invoke.get_analyze_request_id", return_value="r1"),
        patch(
            "app.billing.llm_usage_per_invoke.get_request_llm_model_id",
            return_value=None,
        ),
        patch(
            "app.billing.llm_usage_per_invoke.record_llm_usage_event_async",
            new_callable=AsyncMock,
        ) as rec,
    ):
        await handler.on_chat_model_start(ser, [], run_id=run_id)
        resp = LLMResult(
            generations=[[]],
            llm_output={"token_usage": {"prompt_tokens": 10, "completion_tokens": 20}},
        )
        await handler.on_llm_end(resp, run_id=run_id)

    rec.assert_awaited_once()
    kw = rec.call_args.kwargs
    assert kw["model_id"] == "openai/gpt-4o-mini"
    assert kw["prompt_tokens"] == 10
    assert kw["completion_tokens"] == 20


@pytest.mark.asyncio
async def test_prefers_request_gateway_id_when_sdk_tail_matches():
    run_id = uuid4()
    ser = {
        "id": ["langchain", "chat_models", "openai", "ChatOpenAI"],
        "kwargs": {"model": "gpt-5.4"},
    }
    handler = LlmUsagePerInvokeCallbackHandler()

    with (
        patch(
            "app.billing.llm_usage_per_invoke.get_analyze_user_id",
            return_value="550e8400-e29b-41d4-a716-446655440000",
        ),
        patch("app.billing.llm_usage_per_invoke.get_analyze_project_id", return_value=None),
        patch("app.billing.llm_usage_per_invoke.get_analyze_request_id", return_value="r1"),
        patch(
            "app.billing.llm_usage_per_invoke.get_request_llm_model_id",
            return_value="opencode/gpt-5.4",
        ),
        patch(
            "app.billing.llm_usage_per_invoke.record_llm_usage_event_async",
            new_callable=AsyncMock,
        ) as rec,
    ):
        await handler.on_chat_model_start(ser, [], run_id=run_id)
        resp = LLMResult(
            generations=[[]],
            llm_output={"token_usage": {"prompt_tokens": 1, "completion_tokens": 2}},
        )
        await handler.on_llm_end(resp, run_id=run_id)

    assert rec.call_args.kwargs["model_id"] == "opencode/gpt-5.4"


@pytest.mark.asyncio
async def test_skips_without_user():
    run_id = uuid4()
    handler = LlmUsagePerInvokeCallbackHandler()
    with (
        patch("app.billing.llm_usage_per_invoke.get_analyze_user_id", return_value=None),
        patch(
            "app.billing.llm_usage_per_invoke.record_llm_usage_event_async",
            new_callable=AsyncMock,
        ) as rec,
    ):
        await handler.on_chat_model_start({}, [], run_id=run_id)
        await handler.on_llm_end(
            LLMResult(
                generations=[[]],
                llm_output={"token_usage": {"prompt_tokens": 1, "completion_tokens": 1}},
            ),
            run_id=run_id,
        )
    rec.assert_not_called()
