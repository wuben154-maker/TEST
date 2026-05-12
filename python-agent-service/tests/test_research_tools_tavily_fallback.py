"""Tavily HTTP errors vs empty results: status propagation and fallback logging."""

from unittest.mock import MagicMock

import pytest

from app.tools import research_tools as rt
from app.tools.research_tools import TavilySearchProvider, WebSearchProvider


@pytest.mark.asyncio
async def test_tavily_provider_includes_http_status_on_non_200(monkeypatch):
    class FakeResponse:
        status_code = 432
        text = '{"detail":{"error":"plan limit"}}'

    class FakeClient:
        async def __aenter__(self):
            return self

        async def __aexit__(self, *args):
            return None

        async def post(self, *args, **kwargs):
            return FakeResponse()

    monkeypatch.setattr("httpx.AsyncClient", lambda **kw: FakeClient())
    provider = TavilySearchProvider(api_key="test-key")
    out = await provider.search("q")
    assert out["success"] is False
    assert out["http_status"] == 432
    assert "432" in out["error"]


@pytest.mark.asyncio
async def test_web_search_logs_plan_limit_not_empty_serp(monkeypatch):
    class FakeTavily:
        async def search(self, **kwargs):
            return {
                "success": False,
                "error": "Tavily HTTP 432",
                "results": [],
                "http_status": 432,
            }

    provider = WebSearchProvider()
    monkeypatch.setattr(provider, "_get_tavily", lambda: FakeTavily())
    monkeypatch.setattr(provider, "_get_serper", lambda: None)

    async def noop_crawl(_url, for_serp=False):
        return {"success": False, "html": ""}

    monkeypatch.setattr(provider.crawl4ai, "get_raw_html", noop_crawl)

    async def noop_http(_url, timeout=20.0):
        return 403, ""

    monkeypatch.setattr(rt, "_http_fetch", noop_http)

    mock_warn = MagicMock()
    monkeypatch.setattr(rt.logger, "warning", mock_warn)
    await provider.search("test query")

    event_strings = [c.args[0] for c in mock_warn.call_args_list if c.args]
    assert any("plan or rate limit" in s for s in event_strings), event_strings
    assert not any(s == "Tavily returned no results, falling back to Crawl4AI" for s in event_strings)
