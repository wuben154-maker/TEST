"""Serper.dev API provider and WebSearchProvider integration."""

import pytest

from app.tools.research_tools import SerperSearchProvider, WebSearchProvider


@pytest.mark.asyncio
async def test_serper_provider_maps_organic_results(monkeypatch):
    class FakeResponse:
        status_code = 200

        def json(self):
            return {
                "organic": [
                    {"title": "A", "link": "https://a.example", "snippet": "sa"},
                    {"title": "B", "link": "https://b.example", "snippet": "sb"},
                ]
            }

    class FakeClient:
        async def __aenter__(self):
            return self

        async def __aexit__(self, *args):
            return None

        async def post(self, *args, **kwargs):
            return FakeResponse()

    monkeypatch.setattr("httpx.AsyncClient", lambda **kw: FakeClient())
    provider = SerperSearchProvider(api_key="k", base_url="https://google.serper.dev")
    out = await provider.search("hello", max_results=5)
    assert out["success"] is True
    assert out["provider"] == "Serper"
    assert len(out["results"]) == 2
    assert out["results"][0]["url"] == "https://a.example"
    assert out["results"][0]["title"] == "A"


@pytest.mark.asyncio
async def test_serper_provider_includes_http_status_on_non_200(monkeypatch):
    class FakeResponse:
        status_code = 429
        text = "rate limited"

    class FakeClient:
        async def __aenter__(self):
            return self

        async def __aexit__(self, *args):
            return None

        async def post(self, *args, **kwargs):
            return FakeResponse()

    monkeypatch.setattr("httpx.AsyncClient", lambda **kw: FakeClient())
    provider = SerperSearchProvider(api_key="k")
    out = await provider.search("q")
    assert out["success"] is False
    assert out["http_status"] == 429


@pytest.mark.asyncio
async def test_web_search_uses_serper_before_crawl_when_configured(monkeypatch):
    provider = WebSearchProvider()
    monkeypatch.setattr(provider, "_get_tavily", lambda: None)

    class FakeSerper:
        async def search(self, **kwargs):
            return {
                "success": True,
                "results": [
                    {
                        "title": "t",
                        "url": "https://example.com",
                        "content": "c",
                        "score": 1.0,
                    }
                ],
                "query": kwargs.get("query"),
                "engine": "google",
                "provider": "Serper",
            }

    monkeypatch.setattr(provider, "_get_serper", lambda: FakeSerper())

    crawl_calls = []

    async def track_crawl(*a, **k):
        crawl_calls.append(1)
        return {"success": False, "html": ""}

    monkeypatch.setattr(provider.crawl4ai, "get_raw_html", track_crawl)

    out = await provider.search("test query")
    assert out["provider"] == "Serper"
    assert crawl_calls == []
