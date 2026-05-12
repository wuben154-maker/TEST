"""Web-security subagent: analysis pipeline and LangChain tool wrappers."""

from .pipeline import analyze_web_threat

# Importing ``result_renderer`` registers the per-tool SSE renderer for
# ``detect_web_attack`` in :mod:`app.sse.tool_result_renderers`. The import is
# side-effect-only; the module does not export any public symbol.
from . import result_renderer  # noqa: F401

__all__ = ["analyze_web_threat"]
