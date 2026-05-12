"""Tests for model runtime config in open_deep_research_original."""

import pytest
from langchain_core.messages import HumanMessage

from app.agents.research.open_deep_research_original.configuration import Configuration
from app.agents.research.open_deep_research_original.deep_researcher import clarify_with_user
from app.agents.research.open_deep_research_original.utils import (
    ainvoke_with_usage,
    build_model_runtime_config,
    get_api_key_for_model,
    web_search_deep_research_impl,
    render_token_usage_summary,
    with_provider_aware_structured_output,
)
from app.config import clear_settings_cache


def test_build_runtime_config_for_doubao_uses_openai_compatible_route(monkeypatch):
    """Doubao should route through OpenAI backend with provider base URL."""
    monkeypatch.setenv("DOUBAO_API_KEY", "doubao-key")
    monkeypatch.setenv("DOUBAO_API_BASE_URL", "https://doubao.example/v1")
    monkeypatch.delenv("GET_API_KEYS_FROM_CONFIG", raising=False)
    clear_settings_cache()

    runtime = build_model_runtime_config(
        model_name="doubao:ep-20260312",
        max_tokens=4096,
        config={},
        extra={"tags": ["langsmith:nostream"]},
    )

    assert runtime["model"] == "ep-20260312"
    assert runtime["model_provider"] == "openai"
    assert runtime["max_tokens"] == 4096
    assert runtime["api_key"] == "doubao-key"
    assert runtime["base_url"] == "https://doubao.example/v1"
    assert runtime["tags"] == ["langsmith:nostream"]


def test_get_api_key_for_model_supports_moonshot_alias(monkeypatch):
    """Moonshot alias should resolve to Kimi provider keys."""
    monkeypatch.setenv("KIMI_API_KEY", "kimi-key")
    monkeypatch.delenv("GET_API_KEYS_FROM_CONFIG", raising=False)
    clear_settings_cache()

    assert get_api_key_for_model("moonshot:kimi-k2", {}) == "kimi-key"


def test_build_runtime_config_prefers_configurable_api_keys(monkeypatch):
    """Configurable apiKeys should take precedence when flag is enabled."""
    monkeypatch.setenv("GET_API_KEYS_FROM_CONFIG", "true")
    monkeypatch.setenv("GLM_API_KEY", "glm-key-env")
    monkeypatch.setenv("GLM_API_BASE_URL", "https://glm.example/v1")
    clear_settings_cache()

    runtime = build_model_runtime_config(
        model_name="glm:glm-4-plus",
        max_tokens=2048,
        config={"configurable": {"apiKeys": {"GLM_API_KEY": "glm-key-from-config"}}},
    )

    assert runtime["model"] == "glm-4-plus"
    assert runtime["model_provider"] == "openai"
    assert runtime["api_key"] == "glm-key-from-config"
    assert runtime["base_url"] == "https://glm.example/v1"


def test_configuration_uses_default_model_and_normalizes_alias(monkeypatch):
    """Configuration should ignore RESEARCH_MODEL env and use DEFAULT_MODEL."""
    monkeypatch.setenv("RESEARCH_MODEL", "openai/should-be-ignored")
    monkeypatch.setenv("DEFAULT_MODEL", "zhipu/glm-4-plus")
    clear_settings_cache()

    cfg = Configuration.from_runnable_config({"configurable": {}})
    assert cfg.research_model == "glm:glm-4-plus"


def test_provider_aware_structured_output_prefers_function_calling():
    """OpenAI-compatible providers should prefer function_calling method."""

    class DummyModel:
        def __init__(self):
            self.called_with = None

        def with_structured_output(self, schema, **kwargs):
            self.called_with = {"schema": schema, **kwargs}
            return self

    model = DummyModel()
    result = with_provider_aware_structured_output(
        model=model,
        schema={"type": "object"},
        model_name="doubao:ep-20260312",
    )

    assert result is model
    assert model.called_with is not None
    assert model.called_with.get("method") == "function_calling"


@pytest.mark.asyncio
async def test_ainvoke_with_usage_records_openai_compatible_usage():
    """Usage should be captured from usage_metadata without estimation."""

    class DummyModel:
        def __init__(self) -> None:
            self.last_config = None

        async def ainvoke(self, messages, config=None, **kwargs):
            self.last_config = config

            class DummyResponse:
                usage_metadata = {"input_tokens": 10, "output_tokens": 5, "total_tokens": 15}

            return DummyResponse()

    config = {"configurable": {}}
    dummy = DummyModel()
    await ainvoke_with_usage(
        model=dummy,
        messages=[],
        config=config,
        step="supervisor_loop_1",
        action="Plan and delegate research tasks",
        model_name="doubao:ep-20260312",
    )

    assert dummy.last_config is config

    events = config["configurable"]["token_usage_events"]
    assert len(events) == 1
    assert events[0]["prompt_tokens"] == 10
    assert events[0]["completion_tokens"] == 5
    assert events[0]["total_tokens"] == 15
    assert events[0]["usage_missing"] is False


def test_render_token_usage_summary_includes_step_table_and_totals():
    """Summary markdown should list each step and aggregate totals."""
    config = {
        "configurable": {
            "token_usage_events": [
                {
                    "step": "clarify_with_user",
                    "action": "Clarify research scope",
                    "prompt_tokens": 20,
                    "completion_tokens": 8,
                    "total_tokens": 28,
                },
                {
                    "step": "final_report_generation_attempt_1",
                    "action": "Generate final report",
                    "prompt_tokens": 100,
                    "completion_tokens": 50,
                    "total_tokens": 150,
                },
            ]
        }
    }

    summary = render_token_usage_summary(config)
    assert "## Token Usage" in summary
    assert "clarify_with_user" in summary
    assert "final_report_generation_attempt_1" in summary
    assert "Total prompt tokens: 120" in summary
    assert "Total completion tokens: 58" in summary
    assert "Total tokens: 178" in summary


@pytest.mark.asyncio
async def test_web_search_deep_research_uses_shared_research_tools_provider(monkeypatch):
    """Deep research search should use research_tools.WebSearchProvider."""

    class DummyProvider:
        async def search(self, **kwargs):
            return {
                "success": True,
                "query": kwargs.get("query", ""),
                "provider": "Crawl4AI",
                "results": [
                    {
                        "title": "A",
                        "url": "https://a.example",
                        "content": "snippet",
                        "score": 0.9,
                    }
                ],
            }

    monkeypatch.setattr(
        "app.agents.research.open_deep_research_original.utils.WebSearchProvider",
        DummyProvider,
    )

    output = await web_search_deep_research_impl(
        queries=["ransomware trend"],
        max_results=3,
        search_depth="basic",
        include_domains=[],
        exclude_domains=[],
        config={"configurable": {}},
    )
    assert "https://a.example" in output
    assert "Crawl4AI" in output


@pytest.mark.asyncio
async def test_web_search_deep_research_merges_multi_query_results(monkeypatch):
    """Deep research search should merge results from multiple queries."""

    class DummyProvider:
        async def search(self, **kwargs):
            query = kwargs.get("query", "")
            return {
                "success": True,
                "query": query,
                "provider": "HTTP+BeautifulSoup",
                "results": [
                    {
                        "title": f"Result for {query}",
                        "url": f"https://{query.replace(' ', '-')}.example",
                        "content": "snippet",
                        "score": 0.8,
                    }
                ],
            }

    monkeypatch.setattr(
        "app.agents.research.open_deep_research_original.utils.WebSearchProvider",
        DummyProvider,
    )

    output = await web_search_deep_research_impl(
        queries=["c2 infrastructure", "malware analysis"],
        max_results=5,
        search_depth="advanced",
        include_domains=[],
        exclude_domains=[],
        config={"configurable": {}},
    )
    assert "HTTP+BeautifulSoup" in output
    assert "https://c2-infrastructure.example" in output
    assert "https://malware-analysis.example" in output


@pytest.mark.asyncio
async def test_clarify_with_user_uses_hitl_interrupt_when_needed(monkeypatch):
    """need_clarification=true should pause via interrupt and continue with user reply."""

    class DummyCfg:
        allow_clarification = True
        research_model = "openai:gpt-4.1"
        research_model_max_tokens = 2048
        max_structured_output_retries = 1
        research_response_language = "en"

    class DummyResp:
        need_clarification = True
        question = "Please specify geography."
        verification = ""

    class DummyModel:
        pass

    async def _fake_ainvoke_with_usage(**kwargs):
        return DummyResp()

    monkeypatch.setattr(
        "app.agents.research.open_deep_research_original.deep_researcher.Configuration.from_runnable_config",
        lambda _cfg: DummyCfg(),
    )
    monkeypatch.setattr(
        "app.agents.research.open_deep_research_original.deep_researcher.get_gateway_chat_model",
        lambda **_kwargs: DummyModel(),
    )
    monkeypatch.setattr(
        "app.agents.research.open_deep_research_original.deep_researcher.with_provider_aware_structured_output",
        lambda **_kwargs: type("M", (), {"with_retry": lambda self, **_k: self})(),
    )
    monkeypatch.setattr(
        "app.agents.research.open_deep_research_original.deep_researcher.ainvoke_with_usage",
        _fake_ainvoke_with_usage,
    )
    monkeypatch.setattr(
        "app.agents.research.open_deep_research_original.deep_researcher.interrupt",
        lambda payload: "Focus on APAC market",
    )

    cmd = await clarify_with_user(
        {"messages": [HumanMessage(content="Research RSA 2026 AI security")]},
        {"configurable": {}},
    )

    assert cmd.goto == "write_research_brief"
    resumed_msg = cmd.update["messages"][0]
    assert isinstance(resumed_msg, HumanMessage)
    assert resumed_msg.content == "Focus on APAC market"
