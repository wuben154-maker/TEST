"""Research Tools - Web search and content extraction for Deep Research Agent.

This module provides tools for:
- Web search via Tavily, Serper.dev (Google SERP API), or Crawl4AI scraping Google/Bing HTML,
  then HTTP+BS4 fallback
- URL content scraping using Crawl4AI (with HTTP+BeautifulSoup fallback)
- Content summarization using project LLM (LangChain factory)
"""

import base64
import json
import re
from typing import Any
from urllib.parse import parse_qs, urlencode, urlparse

import httpx
import structlog
from bs4 import BeautifulSoup
from langchain_core.tools import StructuredTool
from pydantic import BaseModel, Field

from app.sse.tool_presentation import RESEARCH_TOOL_ORDER, get_tool_rule

logger = structlog.get_logger()

# User agent for HTTP fallback and Crawl4AI SERP crawls (align with common desktop Chrome)
USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/131.0.0.0 Safari/537.36"
)

# Extra Crawl4AI options for search-engine result pages (generic anti-bot / rendering hints)
_SERP_BROWSER_CONFIG: dict[str, Any] = {
    "user_agent": USER_AGENT,
    "headers": {
        "Accept-Language": "en-US,en;q=0.9",
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8",
        "Sec-Fetch-Dest": "document",
        "Sec-Fetch-Mode": "navigate",
        "Sec-Fetch-Site": "none",
        "Upgrade-Insecure-Requests": "1",
    },
    "enable_stealth": True,
    "viewport_width": 1365,
    "viewport_height": 900,
}

_SERP_CRAWLER_CONFIG: dict[str, Any] = {
    "locale": "en-US",
    "timezone_id": "America/Los_Angeles",
    "wait_until": "domcontentloaded",
    "delay_before_return_html": 2.5,
    "page_timeout": 90000,
    "remove_consent_popups": True,
    "simulate_user": True,
}


def _is_serp_crawl_url(url: str) -> bool:
    u = url.lower()
    return "google.com/search" in u or "bing.com/search" in u


# ============================================================================
# Tool Input Schemas
# ============================================================================

class WebSearchInput(BaseModel):
    """Input for web search tool."""
    query: str = Field(description="Search query string")
    max_results: int = Field(
        default=10,
        description="Maximum number of results to return (default 10; Serper/Tavily use this as request size / num).",
    )
    search_depth: str = Field(default="basic", description="Search depth: 'basic' or 'advanced'")
    include_domains: list[str] = Field(default_factory=list, description="Limit search to these domains")
    exclude_domains: list[str] = Field(default_factory=list, description="Exclude these domains from search")


class ScrapeUrlInput(BaseModel):
    """Input for URL scraping tool."""
    url: str = Field(description="URL to scrape content from")
    extract_images: bool = Field(default=False, description="Whether to extract image URLs")


class SummarizeInput(BaseModel):
    """Input for content summarization tool."""
    content: str = Field(description="Content to summarize")
    max_length: int = Field(default=500, description="Maximum summary length in words")
    focus: str = Field(default="", description="Specific aspect to focus on in summary")


# ============================================================================
# Crawl4AI Client
# ============================================================================

class Crawl4AIClient:
    """Client for Crawl4AI API (scraping and markdown extraction)."""

    def __init__(self, base_url: str | None = None, api_token: str | None = None):
        from app.config import get_settings
        settings = get_settings()
        self.base_url = (base_url or settings.crawl4ai_url).rstrip("/")
        self.api_token = api_token or settings.crawl4ai_api_token
        self._crawl4ai_proxy_server: str | None = settings.crawl4ai_proxy_server

    def _headers(self) -> dict[str, str]:
        headers = {"Content-Type": "application/json"}
        if self.api_token:
            headers["Authorization"] = f"Bearer {self.api_token}"
        return headers

    async def get_markdown(self, url: str, timeout: float = 45.0) -> dict[str, Any]:
        """Fetch URL and return markdown content via /md endpoint."""
        try:
            async with httpx.AsyncClient(timeout=timeout) as client:
                response = await client.post(
                    f"{self.base_url}/md",
                    headers=self._headers(),
                    json={"url": url},
                )
                if response.status_code != 200:
                    return {"success": False, "error": f"Crawl4AI error: {response.status_code}"}
                data = response.json()
                # Handle various response formats (string, object with raw_markdown, etc.)
                md_val = data.get("markdown") or data.get("content")
                if isinstance(md_val, dict):
                    markdown = md_val.get("raw_markdown") or md_val.get("fit_markdown") or ""
                else:
                    markdown = md_val or ""
                title = data.get("title") or (data.get("metadata") or {}).get("title", "")
                return {
                    "success": True,
                    "markdown": markdown,
                    "title": title,
                    "provider": "Crawl4AI",
                }
        except Exception as e:
            logger.exception("Crawl4AI /md error", url=url)
            return {"success": False, "error": str(e)}

    async def get_html(self, url: str, timeout: float = 45.0) -> dict[str, Any]:
        """Fetch URL and return preprocessed HTML via /html endpoint (may strip link attrs)."""
        try:
            async with httpx.AsyncClient(timeout=timeout) as client:
                response = await client.post(
                    f"{self.base_url}/html",
                    headers=self._headers(),
                    json={"url": url},
                )
                if response.status_code != 200:
                    return {"success": False, "error": f"Crawl4AI error: {response.status_code}"}
                data = response.json()
                # Handle various response formats
                html = data.get("html") or data.get("content")
                if isinstance(html, dict):
                    html = html.get("html") or html.get("content") or ""
                html = html or data.get("data", "")
                return {"success": True, "html": html, "provider": "Crawl4AI"}
        except Exception as e:
            logger.exception("Crawl4AI /html error", url=url)
            return {"success": False, "error": str(e)}

    async def get_raw_html(
        self,
        url: str,
        timeout: float = 90.0,
        *,
        for_serp: bool = False,
    ) -> dict[str, Any]:
        """Fetch URL and return raw HTML via /crawl endpoint (preserves href, for search parsing).

        When ``for_serp`` is True (Google/Bing search URL), sends ``browser_config`` / ``crawler_config``
        so Crawl4AI uses stealth, locale, and a short post-load delay.
        """
        payload: dict[str, Any] = {"urls": [url]}
        if for_serp and _is_serp_crawl_url(url):
            bcfg = dict(_SERP_BROWSER_CONFIG)
            if self._crawl4ai_proxy_server:
                bcfg["proxy_config"] = {"server": self._crawl4ai_proxy_server}
            payload["browser_config"] = bcfg
            payload["crawler_config"] = dict(_SERP_CRAWLER_CONFIG)

        try:
            async with httpx.AsyncClient(timeout=timeout) as client:
                response = await client.post(
                    f"{self.base_url}/crawl",
                    headers=self._headers(),
                    json=payload,
                )
                if response.status_code != 200 and for_serp and len(payload) > 1:
                    logger.warning(
                        "Crawl4AI /crawl non-OK with SERP hints, retrying minimal payload",
                        status=response.status_code,
                        url=url[:120],
                    )
                    response = await client.post(
                        f"{self.base_url}/crawl",
                        headers=self._headers(),
                        json={"urls": [url]},
                    )
                if response.status_code != 200:
                    return {"success": False, "error": f"Crawl4AI error: {response.status_code}"}
                data = response.json()
                results = data.get("results") or []
                if not results:
                    return {"success": False, "error": "Crawl4AI returned no results"}
                first = results[0]
                if not first.get("success"):
                    return {"success": False, "error": first.get("error_message", "Crawl failed")}
                html = first.get("html") or first.get("cleaned_html") or ""
                return {"success": True, "html": html, "provider": "Crawl4AI"}
        except Exception as e:
            logger.exception("Crawl4AI /crawl error", url=url)
            return {"success": False, "error": str(e)}


# ============================================================================
# HTTP + BeautifulSoup Fallback
# ============================================================================

def _extract_text_with_bs4(html: str) -> str:
    """Extract readable text from HTML using BeautifulSoup."""
    soup = BeautifulSoup(html, "html.parser")
    # Remove script, style, nav, footer
    for tag in soup(["script", "style", "nav", "footer", "header"]):
        tag.decompose()
    text = soup.get_text(separator="\n", strip=True)
    # Normalize whitespace
    text = re.sub(r"\n\s*\n", "\n\n", text)
    return text.strip()


def _extract_title_from_html(html: str) -> str:
    """Extract title from HTML."""
    soup = BeautifulSoup(html, "html.parser")
    title_tag = soup.find("title")
    return title_tag.get_text(strip=True) if title_tag else ""


async def _http_fetch(url: str, timeout: float = 20.0) -> tuple[int, str]:
    """Simple HTTP GET, returns (status_code, body)."""
    async with httpx.AsyncClient(timeout=timeout, follow_redirects=True) as client:
        response = await client.get(
            url,
            headers={
                "User-Agent": USER_AGENT,
                "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
                "Accept-Language": "en-US,en;q=0.5",
            },
        )
        return response.status_code, response.text


# ============================================================================
# Web Search (Crawl4AI + Google/Bing HTML, fallback HTTP+BS4)
# ============================================================================

def _resolve_bing_redirect_url(url: str) -> str:
    """Extract actual destination URL from Bing redirect (bing.com/ck/a)."""
    if "bing.com/ck/a" not in url:
        return url
    try:
        parsed = urlparse(url)
        params = parse_qs(parsed.query)
        u_val = (params.get("u") or [None])[0]
        if not u_val:
            return url
        # Bing encodes as "a1" + base64(url); strip "a1" prefix (2 chars) if present
        if u_val.startswith("a1"):
            u_val = u_val[2:]
        # Ensure valid base64 padding (length multiple of 4)
        pad = (4 - len(u_val) % 4) % 4
        decoded = base64.b64decode(u_val + "=" * pad).decode("utf-8", errors="replace")
        return decoded if decoded.startswith("http") else url
    except Exception as e:
        logger.debug("Bing URL resolve failed", url=url[:80], error=str(e))
        return url


def _parse_bing_results(html: str, max_results: int) -> list[dict[str, Any]]:
    """Parse Bing search results from HTML."""
    soup = BeautifulSoup(html, "html.parser")
    results = []
    for li in soup.select("li.b_algo")[:max_results]:
        h2 = li.select_one("h2 a")
        if not h2 or not h2.get("href"):
            continue
        url = _resolve_bing_redirect_url(h2.get("href", ""))
        title = h2.get_text(strip=True)
        p = li.select_one("p")
        snippet = p.get_text(strip=True) if p else ""
        if url and title:
            results.append({
                "title": title,
                "url": url,
                "content": snippet,
                "score": 1.0 - (len(results) * 0.1),
            })
    return results


def _resolve_google_redirect_url(href: str) -> str:
    """Resolve Google /url?q=... wrapper to the destination URL."""
    u = href.strip()
    if u.startswith("/url"):
        u = "https://www.google.com" + u
    if "/url?" not in u and "google.com/url?" not in u.lower():
        return href.strip()
    try:
        parsed = urlparse(u)
        qs = parse_qs(parsed.query)
        for key in ("q", "url", "qurl"):
            vals = qs.get(key) or []
            for v in vals:
                if v.startswith("http"):
                    return v
    except Exception as e:
        logger.debug("Google URL resolve failed", href=href[:100], error=str(e))
    return href.strip()


def _parse_google_results(html: str, max_results: int) -> list[dict[str, Any]]:
    """Parse Google organic results from HTML (layout varies; several selectors tried)."""
    soup = BeautifulSoup(html, "html.parser")
    results: list[dict[str, Any]] = []
    seen_urls: set[str] = set()

    for div in soup.select("div.g"):
        if len(results) >= max_results:
            break
        link = div.select_one("div.yuRUbf a[href]")
        if not link:
            for cand in div.find_all("a", href=True):
                h3 = cand.find("h3", recursive=False)
                if not h3:
                    continue
                href = cand.get("href") or ""
                if href.startswith("#") or "/search?" in href:
                    continue
                if not (href.startswith("http") or href.startswith("/url")):
                    continue
                link = cand
                break
        if not link:
            continue

        href = link.get("href") or ""
        url = _resolve_google_redirect_url(href)
        if not url.startswith("http"):
            continue

        parsed_u = urlparse(url)
        host = (parsed_u.netloc or "").lower()
        if "google.com/search" in url:
            continue
        skip_hosts = (
            "accounts.google.com",
            "policies.google.com",
            "support.google.com",
            "webcache.googleusercontent.com",
        )
        if host in skip_hosts:
            continue

        h3 = link.select_one("h3") or div.select_one("h3")
        title = h3.get_text(strip=True) if h3 else link.get_text(strip=True)
        if not title:
            continue

        snippet = ""
        for sel in (".VwiC3b", ".IsZvec", ".lEBKkf", "span.aCOpRe", ".yXK7lf .MUxGbd"):
            sn = div.select_one(sel)
            if sn:
                snippet = sn.get_text(strip=True)
                if snippet and snippet != title:
                    break

        if url in seen_urls:
            continue
        seen_urls.add(url)
        results.append({
            "title": title,
            "url": url,
            "content": snippet,
            "score": 1.0 - (len(results) * 0.1),
        })

    return results


def _normalize_web_search_engine(raw: str) -> str:
    e = (raw or "google").strip().lower()
    return e if e in ("google", "bing") else "google"


def _build_filtered_search_query(
    query: str,
    include_domains: list[str],
    exclude_domains: list[str] | None,
) -> str:
    """Apply site: / -site: filters to the query string (Tavily, Serper, and SERP URLs)."""
    search_query = query
    if include_domains:
        site_filters = " OR ".join([f"site:{d}" for d in include_domains])
        search_query = f"({site_filters}) {query}"
    for domain in exclude_domains or []:
        search_query = f"{search_query} -site:{domain}"
    return search_query


# ============================================================================
# Tavily Search Provider
# ============================================================================

class TavilySearchProvider:
    """Web search via Tavily API (https://tavily.com).

    Tavily is an AI-first search API purpose-built for LLM agents.
    When TAVILY_API_KEY is configured it is tried *first*, before any
    scraping-based fallback.
    """

    TAVILY_API_URL = "https://api.tavily.com/search"

    def __init__(self, api_key: str):
        self.api_key = api_key

    async def search(
        self,
        query: str,
        max_results: int = 10,
        search_depth: str = "basic",
        include_domains: list[str] | None = None,
        exclude_domains: list[str] | None = None,
    ) -> dict[str, Any]:
        """Call Tavily Search API and return normalised result dict."""
        payload: dict[str, Any] = {
            "api_key": self.api_key,
            "query": query,
            "max_results": min(max_results, 20),
            "search_depth": search_depth if search_depth in ("basic", "advanced") else "basic",
        }
        if include_domains:
            payload["include_domains"] = include_domains
        if exclude_domains:
            payload["exclude_domains"] = exclude_domains

        try:
            async with httpx.AsyncClient(timeout=30.0) as client:
                response = await client.post(
                    self.TAVILY_API_URL,
                    json=payload,
                    headers={"Content-Type": "application/json"},
                )
            if response.status_code != 200:
                logger.warning(
                    "Tavily API non-OK response",
                    status=response.status_code,
                    body=response.text[:300],
                )
                return {
                    "success": False,
                    "error": f"Tavily HTTP {response.status_code}",
                    "results": [],
                    "http_status": response.status_code,
                }

            data = response.json()
            raw_results = data.get("results") or []
            results = [
                {
                    "title": r.get("title", ""),
                    "url": r.get("url", ""),
                    "content": r.get("content", ""),
                    "score": r.get("score", 1.0),
                }
                for r in raw_results
                if r.get("url")
            ]
            return {
                "success": True,
                "results": results,
                "query": query,
                "engine": "tavily",
                "provider": "Tavily",
            }
        except Exception:
            logger.exception("Tavily search error", query=query)
            return {
                "success": False,
                "error": "Tavily request failed",
                "results": [],
                "http_status": None,
            }


# ============================================================================
# Serper Search Provider (https://serper.dev)
# ============================================================================

class SerperSearchProvider:
    """Web search via Serper.dev Google SERP API (structured JSON, no HTML scraping)."""

    def __init__(self, api_key: str, base_url: str | None = None):
        from app.config import get_settings

        settings = get_settings()
        self.api_key = api_key
        self.base_url = (base_url or settings.serper_api_base_url).rstrip("/")

    async def search(
        self,
        query: str,
        max_results: int = 10,
        search_depth: str = "basic",
        include_domains: list[str] | None = None,
        exclude_domains: list[str] | None = None,
    ) -> dict[str, Any]:
        """Call Serper POST /search and return normalised result dict."""
        q = _build_filtered_search_query(query, include_domains or [], exclude_domains)
        num = min(max(max_results, 1), 100)
        url = f"{self.base_url}/search"
        try:
            async with httpx.AsyncClient(timeout=30.0) as client:
                response = await client.post(
                    url,
                    headers={
                        "X-API-KEY": self.api_key,
                        "Content-Type": "application/json",
                    },
                    json={"q": q, "num": num},
                )
            if response.status_code != 200:
                logger.warning(
                    "Serper API non-OK response",
                    status=response.status_code,
                    body=response.text[:300],
                )
                return {
                    "success": False,
                    "error": f"Serper HTTP {response.status_code}",
                    "results": [],
                    "http_status": response.status_code,
                }

            data = response.json()
            organic = data.get("organic") or []
            results: list[dict[str, Any]] = []
            for i, item in enumerate(organic[:num]):
                link = item.get("link") or item.get("url") or ""
                if not link:
                    continue
                results.append({
                    "title": item.get("title") or "",
                    "url": link,
                    "content": item.get("snippet") or "",
                    "score": max(0.0, 1.0 - i * 0.1),
                })
            return {
                "success": True,
                "results": results,
                "query": query,
                "engine": "google",
                "provider": "Serper",
            }
        except Exception:
            logger.exception("Serper search error", query=query)
            return {
                "success": False,
                "error": "Serper request failed",
                "results": [],
                "http_status": None,
            }


class WebSearchProvider:
    """Web search: Tavily, Serper, Crawl4AI (Google/Bing HTML), then HTTP+BS4.

    Priority:
      1. Tavily API (if TAVILY_API_KEY is set)
      2. Serper.dev (if SERPER_API_KEY is set)
      3. Crawl4AI scraping (WEB_SEARCH_ENGINE: google or bing)
      4. HTTP + BeautifulSoup fallback
    """

    GOOGLE_SEARCH_BASE = "https://www.google.com/search"
    BING_SEARCH_BASE = "https://www.bing.com/search"

    def __init__(self):
        self.crawl4ai = Crawl4AIClient()
        self._tavily: TavilySearchProvider | None = None
        self._serper: SerperSearchProvider | None = None

    def _get_tavily(self) -> TavilySearchProvider | None:
        """Return a TavilySearchProvider if TAVILY_API_KEY is configured."""
        if self._tavily is not None:
            return self._tavily
        from app.config import get_settings
        key = get_settings().tavily_api_key
        if key:
            self._tavily = TavilySearchProvider(api_key=key)
        return self._tavily

    def _get_serper(self) -> SerperSearchProvider | None:
        """Return a SerperSearchProvider if SERPER_API_KEY is configured."""
        if self._serper is not None:
            return self._serper
        from app.config import get_settings
        key = get_settings().serper_api_key
        if key:
            self._serper = SerperSearchProvider(api_key=key)
        return self._serper

    def _build_search_query(
        self,
        query: str,
        include_domains: list[str],
        exclude_domains: list[str],
    ) -> str:
        return _build_filtered_search_query(query, include_domains, exclude_domains)

    def _build_google_search_url(self, search_query: str, max_results: int) -> str:
        num = min(20, max(10, max_results))
        params = {
            "q": search_query,
            "hl": "en",
            "num": str(num),
        }
        return f"{self.GOOGLE_SEARCH_BASE}?{urlencode(params)}"

    def _build_bing_search_url(self, search_query: str) -> str:
        from urllib.parse import quote
        return f"{self.BING_SEARCH_BASE}?q={quote(search_query)}"

    def _build_search_url(self, engine: str, search_query: str, max_results: int) -> str:
        if engine == "bing":
            return self._build_bing_search_url(search_query)
        return self._build_google_search_url(search_query, max_results)

    async def search(
        self,
        query: str,
        max_results: int = 10,
        search_depth: str = "basic",
        include_domains: list[str] | None = None,
        exclude_domains: list[str] | None = None,
    ) -> dict[str, Any]:
        """Execute web search.

        Priority:
          1. Tavily API (if TAVILY_API_KEY is set)
          2. Serper.dev (if SERPER_API_KEY is set)
          3. Crawl4AI scraping (Google or Bing HTML)
          4. HTTP + BeautifulSoup fallback
        """
        from app.config import get_settings

        # --- Priority 1: Tavily ---
        tavily = self._get_tavily()
        if tavily:
            logger.info("Web search via Tavily (priority)", query=query)
            result = await tavily.search(
                query=query,
                max_results=max_results,
                search_depth=search_depth,
                include_domains=include_domains,
                exclude_domains=exclude_domains,
            )
            if result.get("success") and result.get("results"):
                return result
            http_status = result.get("http_status")
            # 402/429/432: billing, rate limit, or plan usage cap — not "empty SERP".
            if http_status in (402, 429, 432):
                logger.warning(
                    "Tavily plan or rate limit exceeded, falling back to Serper/Crawl4AI",
                    query=query,
                    http_status=http_status,
                )
            elif not result.get("success"):
                logger.warning(
                    "Tavily request failed, falling back to Serper/Crawl4AI",
                    query=query,
                    error=result.get("error"),
                    http_status=http_status,
                )
            else:
                logger.warning("Tavily returned no results, falling back to Serper/Crawl4AI", query=query)

        # --- Priority 2: Serper (Google SERP API) ---
        serper = self._get_serper()
        if serper:
            logger.info("Web search via Serper", query=query)
            result = await serper.search(
                query=query,
                max_results=max_results,
                search_depth=search_depth,
                include_domains=include_domains,
                exclude_domains=exclude_domains,
            )
            if result.get("success") and result.get("results"):
                return result
            http_status = result.get("http_status")
            if http_status in (402, 429, 432):
                logger.warning(
                    "Serper plan or rate limit exceeded, falling back to Crawl4AI",
                    query=query,
                    http_status=http_status,
                )
            elif not result.get("success"):
                logger.warning(
                    "Serper request failed, falling back to Crawl4AI",
                    query=query,
                    error=result.get("error"),
                    http_status=http_status,
                )
            else:
                logger.warning("Serper returned no results, falling back to Crawl4AI", query=query)

        # --- Priority 3: Crawl4AI (Google / Bing HTML scraping) ---
        engine = _normalize_web_search_engine(get_settings().web_search_engine)
        search_query = self._build_search_query(
            query, include_domains or [], exclude_domains or []
        )
        search_url = self._build_search_url(engine, search_query, max_results)
        parse_fn = _parse_google_results if engine == "google" else _parse_bing_results

        logger.info("Web search via Crawl4AI", query=query, engine=engine, search_url=search_url)

        html_result = await self.crawl4ai.get_raw_html(search_url, for_serp=True)
        if html_result.get("success") and html_result.get("html"):
            results = parse_fn(html_result["html"], max_results)
            if results:
                return {
                    "success": True,
                    "results": results,
                    "query": query,
                    "engine": engine,
                    "provider": "Crawl4AI",
                }
            logger.warning("Crawl4AI returned empty parsed results, trying HTTP fallback", query=query, engine=engine)

        # --- Priority 4: HTTP + BeautifulSoup ---
        logger.info("Web search via HTTP+BeautifulSoup fallback", query=query, engine=engine)
        try:
            status, body = await _http_fetch(search_url)
            if status != 200:
                return {
                    "success": False,
                    "error": f"Search page HTTP {status}",
                    "results": [],
                    "query": query,
                    "engine": engine,
                }
            results = parse_fn(body, max_results)
            return {
                "success": True,
                "results": results,
                "query": query,
                "engine": engine,
                "provider": "HTTP+BeautifulSoup",
                "note": "Fallback: simple HTTP scraping",
            }
        except Exception as e:
            logger.exception("Web search fallback error", query=query)
            return {"success": False, "error": str(e), "results": [], "query": query, "engine": engine}


# ============================================================================
# URL Scraper (Crawl4AI primary, HTTP+BeautifulSoup fallback)
# ============================================================================

class UrlScraper:
    """Extract content from URLs using Crawl4AI, fallback to HTTP+BeautifulSoup."""

    def __init__(self, crawl4ai_url: str | None = None, crawl4ai_token: str | None = None):
        self.crawl4ai = Crawl4AIClient(
            base_url=crawl4ai_url,
            api_token=crawl4ai_token,
        )

    async def scrape(self, url: str, extract_images: bool = False) -> dict[str, Any]:
        """Scrape content from URL. Crawl4AI first, then HTTP+BeautifulSoup fallback."""
        # Primary: Crawl4AI /md
        result = await self.crawl4ai.get_markdown(url)
        if result.get("success") and result.get("markdown"):
            return {
                "success": True,
                "url": url,
                "content": result["markdown"],
                "title": result.get("title", ""),
                "provider": "Crawl4AI",
            }
        logger.warning("Crawl4AI scrape failed, using HTTP+BeautifulSoup fallback", url=url)

        # Fallback: HTTP + BeautifulSoup
        return await self._scrape_with_http_bs4(url, extract_images)

    async def _scrape_with_http_bs4(
        self, url: str, extract_images: bool = False
    ) -> dict[str, Any]:
        """Simple HTTP + BeautifulSoup scrape."""
        try:
            status, html = await _http_fetch(url)
            if status != 200:
                return {"success": False, "error": f"HTTP {status}"}
            text = _extract_text_with_bs4(html)
            title = _extract_title_from_html(html)
            result = {
                "success": True,
                "url": url,
                "content": text[:15000],
                "title": title,
                "provider": "HTTP+BeautifulSoup",
                "note": "Fallback: simple HTTP scraping",
            }
            if extract_images:
                soup = BeautifulSoup(html, "html.parser")
                imgs = soup.find_all("img", src=True)
                result["links"] = [img["src"] for img in imgs[:50]]
            return result
        except Exception as e:
            logger.exception("HTTP+BS4 scrape error", url=url)
            return {"success": False, "error": str(e)}


# ============================================================================
# Content Summarizer
# ============================================================================

class ContentSummarizer:
    """Summarize long content using project LLM (LangChain factory)."""

    def __init__(self):
        pass

    async def summarize(
        self,
        content: str,
        max_length: int = 500,
        focus: str = "",
        language: str = "auto",
    ) -> dict[str, Any]:
        """Summarize content using AI."""
        try:
            from langchain_core.messages import HumanMessage, SystemMessage
            from app.llm_gateway.factory import get_model

            model = get_model()

            focus_instruction = f" Focus on: {focus}" if focus else ""
            lang_instruction = (
                " Respond in the same language as the input content."
                if language == "auto"
                else f" Respond in {language}."
            )
            system_content = (
                f"Summarize the following content in under {max_length} words. "
                f"Be concise and focus on key points.{focus_instruction}{lang_instruction}"
            )
            messages = [
                SystemMessage(content=system_content),
                HumanMessage(content=content[:20000]),
            ]
            summary = await model.ainvoke(messages)
            summary_text = summary.content if hasattr(summary, "content") else str(summary)
            return {
                "success": True,
                "summary": summary_text,
                "original_length": len(content.split()),
                "summary_length": len(summary_text.split()),
            }
        except ValueError as e:
            if "No LLM provider configured" in str(e):
                return {"success": False, "error": "No LLM provider configured. Add GOOGLE_API_KEY, OPENAI_API_KEY, or other API key."}
            raise
        except Exception as e:
            logger.exception("Summarization error")
            return {"success": False, "error": str(e)}


# ============================================================================
# Tool Factory
# ============================================================================

_web_search_provider: WebSearchProvider | None = None
_url_scraper: UrlScraper | None = None
_summarizer: ContentSummarizer | None = None


def _get_web_search_provider() -> WebSearchProvider:
    global _web_search_provider
    if _web_search_provider is None:
        _web_search_provider = WebSearchProvider()
    return _web_search_provider


def _get_scraper() -> UrlScraper:
    global _url_scraper
    if _url_scraper is None:
        _url_scraper = UrlScraper()
    return _url_scraper


def _get_summarizer() -> ContentSummarizer:
    global _summarizer
    if _summarizer is None:
        _summarizer = ContentSummarizer()
    return _summarizer


_RESEARCH_TOOL_DESCRIPTION_FALLBACKS: dict[str, str] = {
    "web_search": (
        "Use for keyword/topic discovery when target pages are unknown: returns titles, URLs, snippets. "
        "Not for a user-provided URL alone—use scrape_url. After choosing URLs, use scrape_url for full text. "
        "max_results defaults to 10. Backend: Tavily (TAVILY_API_KEY), else Serper (SERPER_API_KEY), "
        "else Crawl4AI (WEB_SEARCH_ENGINE), else HTTP+BeautifulSoup."
    ),
    "scrape_url": (
        "Fetch readable content from one HTTP(S) URL. Prefer when the user gave a link or asked about a "
        "specific page (no web_search required). Also use for full text of URLs from web_search results. "
        "Crawl4AI primary; HTTP+BeautifulSoup fallback."
    ),
    "summarize_content": (
        "Generate a concise AI-powered summary of long content. "
        "Useful for processing scraped articles."
    ),
}


def _research_tool_description(tool_name: str) -> str:
    rule = get_tool_rule(tool_name)
    if rule and rule.description:
        return rule.description
    return _RESEARCH_TOOL_DESCRIPTION_FALLBACKS[tool_name]


def _research_tool_enabled(tool_name: str) -> bool:
    rule = get_tool_rule(tool_name)
    if rule is None:
        return True
    return rule.enabled


async def _web_search_impl(
    query: str,
    max_results: int = 10,
    search_depth: str = "basic",
    include_domains: list[str] | None = None,
    exclude_domains: list[str] | None = None,
) -> str:
    provider = _get_web_search_provider()
    result = await provider.search(
        query=query,
        max_results=max_results,
        search_depth=search_depth,
        include_domains=include_domains or [],
        exclude_domains=exclude_domains or [],
    )
    return json.dumps(result, ensure_ascii=False, indent=2)


async def _scrape_url_impl(url: str, extract_images: bool = False) -> str:
    scraper = _get_scraper()
    result = await scraper.scrape(url, extract_images)
    return json.dumps(result, ensure_ascii=False, indent=2)


async def _summarize_content_impl(
    content: str,
    max_length: int = 500,
    focus: str = "",
) -> str:
    summarizer = _get_summarizer()
    result = await summarizer.summarize(content, max_length, focus)
    return json.dumps(result, ensure_ascii=False, indent=2)


def _build_research_structured_tool(name: str) -> StructuredTool | None:
    if name == "web_search":
        return StructuredTool.from_function(
            func=_web_search_impl,
            name="web_search",
            description=_research_tool_description("web_search"),
            args_schema=WebSearchInput,
            coroutine=_web_search_impl,
        )
    if name == "scrape_url":
        return StructuredTool.from_function(
            func=_scrape_url_impl,
            name="scrape_url",
            description=_research_tool_description("scrape_url"),
            args_schema=ScrapeUrlInput,
            coroutine=_scrape_url_impl,
        )
    if name == "summarize_content":
        return StructuredTool.from_function(
            func=_summarize_content_impl,
            name="summarize_content",
            description=_research_tool_description("summarize_content"),
            args_schema=SummarizeInput,
            coroutine=_summarize_content_impl,
        )
    return None


def try_append_research_tool(
    name: str,
    out: list[StructuredTool],
    *,
    assume_yaml_enabled: bool = False,
) -> bool:
    """Mount one research tool if ``name`` is known. Respects YAML ``enabled`` unless
    ``assume_yaml_enabled`` (caller already enforced tiered ``common_tools`` rules).
    """
    if name not in RESEARCH_TOOL_ORDER:
        return False
    if not assume_yaml_enabled and not _research_tool_enabled(name):
        return False
    built = _build_research_structured_tool(name)
    if built is None:
        return False
    out.append(built)
    return True


def create_research_tools() -> list[StructuredTool]:
    """Same as ``create_common_tools(only_names=RESEARCH_TOOL_ORDER)`` (YAML-driven)."""
    from app.tools.common.tools import create_common_tools

    return create_common_tools(only_names=frozenset(RESEARCH_TOOL_ORDER))


__all__ = [
    "create_research_tools",
    "Crawl4AIClient",
    "TavilySearchProvider",
    "SerperSearchProvider",
    "WebSearchProvider",
    "UrlScraper",
    "ContentSummarizer",
]
