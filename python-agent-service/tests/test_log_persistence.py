"""Tests for log-persistence-configurable delivery."""

from __future__ import annotations

import logging
import textwrap
from pathlib import Path
from unittest.mock import patch

import pytest

# ---------------------------------------------------------------------------
# 1. Settings: LOG_SINK / LOG_FILE_* fields
# ---------------------------------------------------------------------------


class TestLogSinkSettings:
    def test_default_is_stdout(self):
        from app.config.settings import Settings

        s = Settings()
        assert s.log_sink == "stdout"

    def test_log_file_defaults(self):
        from app.config.settings import Settings

        s = Settings()
        assert s.log_file_path == "logs/secmanus.log"
        assert s.log_file_max_bytes == 10_485_760
        assert s.log_file_backup_count == 5

    def test_log_sink_file_accepted(self):
        from app.config.settings import Settings

        s = Settings(log_sink="file")
        assert s.log_sink == "file"

    def test_log_sink_both_accepted(self):
        from app.config.settings import Settings

        s = Settings(log_sink="both")
        assert s.log_sink == "both"


# ---------------------------------------------------------------------------
# 2. main.py: handler configuration logic (source inspection)
# ---------------------------------------------------------------------------


class TestMainLogHandlerSetup:
    """Verify main.py configures handlers based on LOG_SINK."""

    _main_src = (
        Path(__file__).resolve().parents[1] / "app" / "main.py"
    ).read_text(encoding="utf-8")

    def test_stdout_handler_conditional(self):
        assert 'if _log_sink in ("stdout", "both")' in self._main_src

    def test_file_handler_conditional(self):
        assert 'if _log_sink in ("file", "both")' in self._main_src

    def test_rotating_file_handler_used(self):
        assert "RotatingFileHandler" in self._main_src

    def test_log_dir_created(self):
        assert "mkdir(parents=True, exist_ok=True)" in self._main_src


# ---------------------------------------------------------------------------
# 3. POST /api/client-errors endpoint
# ---------------------------------------------------------------------------


class TestClientErrorsEndpoint:
    @pytest.fixture(autouse=True)
    def _clear_rate_buckets(self):
        import app.api.client_errors as mod
        mod._rate_buckets.clear()

    @pytest.fixture
    def client(self):
        """Create a TestClient without importing main (avoids circular imports)."""
        from fastapi import FastAPI
        from fastapi.testclient import TestClient

        from app.api.client_errors import router

        test_app = FastAPI()
        test_app.include_router(router)
        return TestClient(test_app)

    def test_valid_payload_returns_204(self, client):
        resp = client.post(
            "/api/client-errors",
            json={
                "errors": [
                    {
                        "timestamp": "2026-04-16T10:00:00.000Z",
                        "level": "error",
                        "event": "test_event",
                    }
                ]
            },
        )
        assert resp.status_code == 204

    def test_empty_errors_returns_204(self, client):
        resp = client.post("/api/client-errors", json={"errors": []})
        assert resp.status_code == 204

    def test_invalid_payload_returns_422(self, client):
        resp = client.post("/api/client-errors", json={"bad": "data"})
        assert resp.status_code == 422

    def test_too_many_entries_returns_422(self, client):
        entries = [
            {"timestamp": "t", "level": "error", "event": f"e{i}"}
            for i in range(51)
        ]
        resp = client.post("/api/client-errors", json={"errors": entries})
        assert resp.status_code == 422

    def test_rate_limit_returns_429(self, client):
        payload = {
            "errors": [
                {"timestamp": "t", "level": "error", "event": "e"}
            ]
        }
        for _ in range(10):
            resp = client.post("/api/client-errors", json=payload)
            assert resp.status_code == 204
        resp = client.post("/api/client-errors", json=payload)
        assert resp.status_code == 429

    def test_extra_fields_passed_through(self, client):
        resp = client.post(
            "/api/client-errors",
            json={
                "errors": [
                    {
                        "timestamp": "t",
                        "level": "warn",
                        "event": "e",
                        "extra": {"request_id": "abc", "url": "/foo"},
                    }
                ]
            },
        )
        assert resp.status_code == 204

    def test_long_extra_values_truncated(self, client):
        from app.api.client_errors import ClientErrorEntry

        entry = ClientErrorEntry(
            timestamp="t",
            level="error",
            event="e",
            extra={"big": "x" * 5000},
        )
        assert len(entry.extra["big"]) < 5000
        assert entry.extra["big"].endswith("…[truncated]")
