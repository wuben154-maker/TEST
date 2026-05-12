"""Unit tests for billing cost math and token extraction."""

from decimal import Decimal
from unittest.mock import MagicMock

from langchain_core.messages import AIMessage
from langchain_core.outputs.chat_generation import ChatGeneration
from langchain_core.outputs.llm_result import LLMResult

from app.billing.pricing import (
    compute_cost_usd,
    extract_token_usage_from_llm_result,
)


def test_compute_cost_usd_formula():
    cost = compute_cost_usd(
        1_000_000,
        2_000_000,
        Decimal("1.00"),
        Decimal("2.00"),
    )
    assert cost == Decimal("5.000000")


def test_extract_token_usage_from_llm_output():
    resp = MagicMock()
    resp.llm_output = {"token_usage": {"prompt_tokens": 10, "completion_tokens": 20}}
    resp.generations = []
    pt, ct = extract_token_usage_from_llm_result(resp)
    assert pt == 10
    assert ct == 20


def test_extract_token_usage_from_llm_output_usage_alias():
    """Some OpenAI-compatible APIs expose counts under ``usage`` (like raw REST)."""
    resp = MagicMock()
    resp.llm_output = {"usage": {"prompt_tokens": 3, "completion_tokens": 4}}
    resp.generations = []
    pt, ct = extract_token_usage_from_llm_result(resp)
    assert pt == 3
    assert ct == 4


def test_extract_token_usage_from_aimessage_usage_metadata():
    """LangChain 0.3+ often puts counts on AIMessage.usage_metadata only."""
    msg = AIMessage(
        content="hi",
        usage_metadata={
            "input_tokens": 5,
            "output_tokens": 7,
            "total_tokens": 12,
        },
    )
    cg = ChatGeneration(message=msg)
    resp = LLMResult(generations=[[cg]], llm_output=None)
    pt, ct = extract_token_usage_from_llm_result(resp)
    assert pt == 5
    assert ct == 7
