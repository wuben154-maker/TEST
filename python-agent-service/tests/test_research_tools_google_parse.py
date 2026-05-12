"""Unit tests for Google SERP HTML parsing (stable layout snippet)."""

from app.tools.research_tools import _parse_google_results


def test_parse_google_results_yurubf_layout():
    html = """
    <html><body><div id="rso">
      <div class="g">
        <div class="yuRUbf"><a href="https://example.com/article">
          <h3>Example Article Title</h3>
        </a></div>
        <div class="VwiC3b">This is the snippet text for the result.</div>
      </div>
    </div></body></html>
    """
    out = _parse_google_results(html, max_results=5)
    assert len(out) == 1
    assert out[0]["title"] == "Example Article Title"
    assert out[0]["url"] == "https://example.com/article"
    assert "snippet" in out[0]["content"].lower() or "Snippet" in out[0]["content"]


def test_parse_google_results_resolves_url_wrapper():
    html = """
    <div class="g">
      <div class="yuRUbf"><a href="https://www.google.com/url?q=https://news.example/story&sa=U">
        <h3>Story</h3>
      </a></div>
      <div class="VwiC3b">Blurb</div>
    </div>
    """
    out = _parse_google_results(html, max_results=3)
    assert len(out) == 1
    assert out[0]["url"] == "https://news.example/story"
