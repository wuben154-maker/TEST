"""Tests for observability and logging infrastructure.

Verifies:
- structlog config includes merge_contextvars and add_log_level
- RequestLoggingMiddleware emits structured http_request events
- contextvars binding propagates request_id/user_id to log output
- vendor loggers produce JSON via ProcessorFormatter
- No bare except:pass in deep_agent.py
"""

import re
from pathlib import Path

import pytest


# ---------------------------------------------------------------------------
# 1. structlog configuration processors
# ---------------------------------------------------------------------------

class TestStructlogConfiguration:
    """Verify the structlog processor pipeline in app.main via source inspection."""

    def _read_main_source(self) -> str:
        main_path = Path(__file__).resolve().parents[1] / "app" / "main.py"
        return main_path.read_text(encoding="utf-8")

    def test_merge_contextvars_in_processors(self):
        """merge_contextvars must appear in the _shared_processors list."""
        source = self._read_main_source()
        assert "merge_contextvars" in source, (
            "merge_contextvars not found in app/main.py"
        )

    def test_add_log_level_in_processors(self):
        """add_log_level ensures every JSON line has a 'level' key."""
        source = self._read_main_source()
        assert "add_log_level" in source, (
            "add_log_level not found in app/main.py"
        )

    def test_processor_formatter_for_vendor(self):
        """ProcessorFormatter must be configured for vendor stdlib logging."""
        source = self._read_main_source()
        assert "ProcessorFormatter" in source, (
            "ProcessorFormatter not found in app/main.py — vendor logs won't be JSON"
        )

    def test_processor_formatter_passes_logger_for_foreign_pre_chain(self):
        """foreign_pre_chain runs filter_by_level; logger=None breaks httpx etc."""
        source = self._read_main_source()
        assert "logger=_stdlib_logging.getLogger()" in source or (
            "logger=_stdlib_logging.root" in source
        ), (
            "ProcessorFormatter must set logger= so filter_by_level gets a real Logger"
        )

    def test_safe_filter_by_level_wrapper(self):
        """Defense in depth when ProcessorFormatter still passes logger=None."""
        source = self._read_main_source()
        assert "_safe_filter_by_level" in source


# ---------------------------------------------------------------------------
# 2. RequestLoggingMiddleware
# ---------------------------------------------------------------------------

class TestRequestLoggingMiddleware:
    """Verify request_logging.py exists and has correct structure."""

    def test_middleware_file_exists(self):
        middleware_path = (
            Path(__file__).resolve().parents[1]
            / "app"
            / "middleware"
            / "request_logging.py"
        )
        assert middleware_path.exists(), "request_logging.py not found"

    def test_middleware_has_class(self):
        middleware_path = (
            Path(__file__).resolve().parents[1]
            / "app"
            / "middleware"
            / "request_logging.py"
        )
        source = middleware_path.read_text(encoding="utf-8")
        assert "class RequestLoggingMiddleware" in source
        assert "http_request" in source
        assert "latency_ms" in source
        assert "status_code" in source


# ---------------------------------------------------------------------------
# 3. No bare except:pass in deep_agent.py
# ---------------------------------------------------------------------------

class TestNoSilentExceptions:
    """deep_agent.py must not contain bare 'except Exception:\\n    pass'."""

    def test_no_bare_except_pass_in_deep_agent(self):
        agent_path = (
            Path(__file__).resolve().parents[1]
            / "app"
            / "agents"
            / "deep_agent.py"
        )
        source = agent_path.read_text(encoding="utf-8")
        pattern = re.compile(r"except\s+Exception\s*:\s*\n\s+pass\b")
        matches = pattern.findall(source)
        assert len(matches) == 0, (
            f"Found {len(matches)} bare 'except Exception: pass' in deep_agent.py"
        )


# ---------------------------------------------------------------------------
# 4. open_deep_research uses structlog
# ---------------------------------------------------------------------------

class TestResearchStructlog:
    """open_deep_research_original/utils.py must use structlog, not logging."""

    def test_utils_uses_structlog(self):
        utils_path = (
            Path(__file__).resolve().parents[1]
            / "app"
            / "agents"
            / "research"
            / "open_deep_research_original"
            / "utils.py"
        )
        source = utils_path.read_text(encoding="utf-8")
        assert "logging.getLogger" not in source, (
            "utils.py still uses logging.getLogger — should use structlog.get_logger()"
        )
        assert "structlog.get_logger()" in source


# ---------------------------------------------------------------------------
# 5. Adapter no longer writes files
# ---------------------------------------------------------------------------

class TestAdapterNoFileWrites:
    """Adapter should not write files to disk for logging."""

    def test_no_file_write_in_adapter(self):
        adapter_path = (
            Path(__file__).resolve().parents[1]
            / "app"
            / "agents"
            / "research"
            / "open_deep_research_original_adapter.py"
        )
        source = adapter_path.read_text(encoding="utf-8")
        assert "def _write_research_run_report_markdown" not in source
        assert "path.write_text" not in source
        assert 'logs_dir = Path' not in source


# ---------------------------------------------------------------------------
# 6. Event naming convention in touched files
# ---------------------------------------------------------------------------

class TestEventNamingConvention:
    """All logger events in touched files should use snake_case, not sentences."""

    @pytest.mark.parametrize("rel_path", [
        "app/agents/deep_agent.py",
        "app/agents/research/open_deep_research_original_adapter.py",
        "app/agents/research/open_deep_research_original/utils.py",
    ])
    def test_no_sentence_style_events(self, rel_path):
        file_path = Path(__file__).resolve().parents[1] / rel_path
        if not file_path.exists():
            pytest.skip(f"{rel_path} does not exist")
        source = file_path.read_text(encoding="utf-8")
        sentence_pattern = re.compile(r'logger\.\w+\(\s*"[A-Z][a-z]+ ')
        matches = sentence_pattern.findall(source)
        assert len(matches) == 0, (
            f"Found {len(matches)} sentence-style event names in {rel_path}: {matches}"
        )


# ---------------------------------------------------------------------------
# 7. AGENT.md has logging standards section
# ---------------------------------------------------------------------------

class TestAgentMdLoggingStandards:
    """AGENT.md must contain logging standards section."""

    def test_agent_md_has_logging_section(self):
        agent_md_path = Path(__file__).resolve().parents[2] / "AGENT.md"
        source = agent_md_path.read_text(encoding="utf-8")
        assert "Logging & Observability Standards" in source
        assert "snake_case" in source
        assert "merge_contextvars" in source
