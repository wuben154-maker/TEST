"""Tests for deep-research per-node output language injection."""

import pytest

from app.agents.research.open_deep_research_original.configuration import Configuration
from app.agents.research.open_deep_research_original.prompts import (
    clarify_with_user_instructions,
    compress_research_system_prompt,
    final_report_generation_prompt,
    lead_researcher_prompt,
    research_system_prompt,
    transform_messages_into_research_topic_prompt,
)
from app.agents.research.open_deep_research_original.research_output_language import (
    normalize_research_response_language,
    research_prompt_language_block,
)


def test_normalize_research_response_language_defaults():
    assert normalize_research_response_language(None) == "en"
    assert normalize_research_response_language("") == "en"
    assert normalize_research_response_language("zh") == "zh"
    assert normalize_research_response_language("zh-CN") == "zh"
    assert normalize_research_response_language("zh-TW") == "zh-hant"
    assert normalize_research_response_language("zh-Hant") == "zh-hant"
    assert normalize_research_response_language("ja") == "ja"
    assert normalize_research_response_language("ko") == "ko"


def test_configuration_reads_subagent_response_language(monkeypatch):
    monkeypatch.delenv("RESEARCH_RESPONSE_LANGUAGE", raising=False)
    cfg = Configuration.from_runnable_config(
        {"configurable": {"subagent_response_language": "zh-CN"}}
    )
    assert cfg.research_response_language == "zh"


def test_configuration_falls_back_to_sse_ui_language(monkeypatch):
    monkeypatch.delenv("RESEARCH_RESPONSE_LANGUAGE", raising=False)
    cfg = Configuration.from_runnable_config(
        {"configurable": {"sse_ui_language": "ja"}}
    )
    assert cfg.research_response_language == "ja"


@pytest.mark.parametrize(
    "template,extra_kwargs",
    [
        (
            clarify_with_user_instructions,
            {"messages": "Human: hi", "date": "2026-01-01"},
        ),
        (
            transform_messages_into_research_topic_prompt,
            {"messages": "Human: hi", "date": "2026-01-01"},
        ),
        (
            lead_researcher_prompt,
            {
                "date": "2026-01-01",
                "max_concurrent_research_units": 3,
                "max_researcher_iterations": 4,
            },
        ),
        (research_system_prompt, {"date": "2026-01-01"}),
        (compress_research_system_prompt, {"date": "2026-01-01"}),
        (
            final_report_generation_prompt,
            {
                "research_brief": "brief",
                "messages": "Human: hi",
                "findings": "f",
                "date": "2026-01-01",
            },
        ),
    ],
)
def test_prompt_templates_accept_output_language_placeholder(template, extra_kwargs):
    block = research_prompt_language_block("zh")
    template.format(output_language_instructions=block, **extra_kwargs)


def test_research_prompt_language_block_contains_target_language_name():
    zh_block = research_prompt_language_block("zh")
    assert "Simplified Chinese" in zh_block or "简体中文" in zh_block
    en_block = research_prompt_language_block("en")
    assert "English" in en_block
