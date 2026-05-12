"""Tests for gateway model id resolution from LangChain serialized chat models."""

from __future__ import annotations

from app.billing.model_id_from_serialized import resolve_gateway_model_id_from_chat_start


def test_openai_chat_model():
    ser = {
        "lc": 1,
        "type": "constructor",
        "id": ["langchain", "chat_models", "openai", "ChatOpenAI"],
        "kwargs": {"model": "gpt-4o-mini"},
    }
    assert (
        resolve_gateway_model_id_from_chat_start(ser, kwargs={})
        == "openai/gpt-4o-mini"
    )


def test_invocation_params_overrides_kwargs():
    ser = {
        "id": ["langchain", "chat_models", "openai", "ChatOpenAI"],
        "kwargs": {"model": "old"},
    }
    out = resolve_gateway_model_id_from_chat_start(
        ser, kwargs={"invocation_params": {"model": "gpt-4o"}}
    )
    assert out == "openai/gpt-4o"


def test_anthropic_path():
    ser = {
        "id": ["langchain_anthropic", "ChatAnthropic"],
        "kwargs": {"model_name": "claude-sonnet-4-20250514"},
    }
    out = resolve_gateway_model_id_from_chat_start(ser, kwargs={})
    assert out == "anthropic/claude-sonnet-4-20250514"


def test_already_gateway_form():
    ser = {
        "id": ["langchain", "chat_models", "openai", "ChatOpenAI"],
        "kwargs": {"model": "opencode/gpt-5.4"},
    }
    assert resolve_gateway_model_id_from_chat_start(ser, kwargs={}) == "opencode/gpt-5.4"


def test_runnable_binding_nested():
    inner = {
        "id": ["langchain", "chat_models", "openai", "ChatOpenAI"],
        "kwargs": {"model": "gpt-4o"},
    }
    ser = {"kwargs": {"bound": inner}}
    assert resolve_gateway_model_id_from_chat_start(ser, kwargs={}) == "openai/gpt-4o"
