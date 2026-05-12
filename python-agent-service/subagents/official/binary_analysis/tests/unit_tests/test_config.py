"""Tests for binary_analysis.config — C1-AC4 + C13 (DocumentSettings)."""

from pathlib import Path

import pytest

from config import (
    DEFAULT_MAX_RECURSION_DEPTH,
    DEFAULT_MAX_ROUNDS,
    DEFAULT_TOKEN_BUDGET,
    TOKEN_BUDGET_HARD_CAP,
    DocumentSettings,
    Settings,
    document_settings,
    settings,
)
from errors import SandboxUnavailable

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_settings(**overrides) -> Settings:
    """Construct a Settings object, bypassing the env-file and cache."""
    settings.cache_clear()
    return Settings(**overrides)


# ---------------------------------------------------------------------------
# Basic field parsing
# ---------------------------------------------------------------------------


def test_use_e2b_default_true(monkeypatch):
    monkeypatch.setenv("E2B_API_KEY", "test-key")
    monkeypatch.delenv("BINARY_ANALYSIS_USE_E2B", raising=False)
    settings.cache_clear()
    cfg = Settings(_env_file=None)
    assert cfg.use_e2b is True


def test_use_e2b_can_be_disabled(monkeypatch):
    monkeypatch.setenv("BINARY_ANALYSIS_USE_E2B", "false")
    monkeypatch.delenv("E2B_API_KEY", raising=False)
    settings.cache_clear()
    cfg = Settings(_env_file=None)
    assert cfg.use_e2b is False


def test_e2b_template_default(monkeypatch):
    monkeypatch.setenv("E2B_API_KEY", "k")
    settings.cache_clear()
    cfg = Settings(_env_file=None)
    assert cfg.e2b_template == "binary-analysis-ubuntu-2204"


def test_e2b_template_override(monkeypatch):
    monkeypatch.setenv("E2B_API_KEY", "k")
    monkeypatch.setenv("BINARY_ANALYSIS_E2B_TEMPLATE", "custom-template")
    settings.cache_clear()
    cfg = Settings(_env_file=None)
    assert cfg.e2b_template == "custom-template"


def test_sandbox_timeout_default(monkeypatch):
    monkeypatch.setenv("E2B_API_KEY", "k")
    monkeypatch.delenv("BINARY_ANALYSIS_SANDBOX_TIMEOUT_SECONDS", raising=False)
    settings.cache_clear()
    cfg = Settings(_env_file=None)
    assert cfg.sandbox_timeout_seconds == 330


def test_sandbox_timeout_override(monkeypatch):
    monkeypatch.setenv("E2B_API_KEY", "k")
    monkeypatch.setenv("BINARY_ANALYSIS_SANDBOX_TIMEOUT_SECONDS", "600")
    settings.cache_clear()
    cfg = Settings(_env_file=None)
    assert cfg.sandbox_timeout_seconds == 600


def test_llm_request_timeout_default(monkeypatch):
    monkeypatch.setenv("E2B_API_KEY", "k")
    monkeypatch.delenv("BINARY_ANALYSIS_LLM_REQUEST_TIMEOUT", raising=False)
    settings.cache_clear()
    cfg = Settings(_env_file=None)
    assert cfg.llm_request_timeout == 600.0  # noqa: PLR2004


def test_llm_request_timeout_override(monkeypatch):
    monkeypatch.setenv("E2B_API_KEY", "k")
    monkeypatch.setenv("BINARY_ANALYSIS_LLM_REQUEST_TIMEOUT", "1200")
    settings.cache_clear()
    cfg = Settings(_env_file=None)
    assert cfg.llm_request_timeout == 1200.0  # noqa: PLR2004


def test_max_file_size_mb_default(monkeypatch):
    monkeypatch.setenv("E2B_API_KEY", "k")
    settings.cache_clear()
    cfg = Settings(_env_file=None)
    assert cfg.max_file_size_mb == 100


# ---------------------------------------------------------------------------
# C1-AC4 core: missing E2B_API_KEY raises SandboxUnavailable
# ---------------------------------------------------------------------------


def test_raises_sandbox_unavailable_when_e2b_enabled_and_no_api_key(monkeypatch):
    monkeypatch.setenv("BINARY_ANALYSIS_USE_E2B", "true")
    monkeypatch.delenv("E2B_API_KEY", raising=False)
    settings.cache_clear()
    with pytest.raises(SandboxUnavailable):
        Settings(_env_file=None)


def test_no_error_when_e2b_disabled_and_no_api_key(monkeypatch):
    monkeypatch.setenv("BINARY_ANALYSIS_USE_E2B", "false")
    monkeypatch.delenv("E2B_API_KEY", raising=False)
    settings.cache_clear()
    cfg = Settings(_env_file=None)  # must not raise
    assert cfg.use_e2b is False
    assert cfg.e2b_api_key is None


def test_no_error_when_e2b_enabled_and_api_key_set(monkeypatch):
    monkeypatch.setenv("BINARY_ANALYSIS_USE_E2B", "true")
    monkeypatch.setenv("E2B_API_KEY", "my-secret-key")
    settings.cache_clear()
    cfg = Settings(_env_file=None)  # must not raise
    assert cfg.use_e2b is True
    assert cfg.e2b_api_key == "my-secret-key"


# ---------------------------------------------------------------------------
# settings() singleton behaviour
# ---------------------------------------------------------------------------


def test_settings_returns_settings_instance(monkeypatch):
    monkeypatch.setenv("BINARY_ANALYSIS_USE_E2B", "false")
    monkeypatch.delenv("E2B_API_KEY", raising=False)
    settings.cache_clear()
    cfg = settings()
    assert isinstance(cfg, Settings)


def test_settings_cached(monkeypatch):
    monkeypatch.setenv("BINARY_ANALYSIS_USE_E2B", "false")
    monkeypatch.delenv("E2B_API_KEY", raising=False)
    settings.cache_clear()
    cfg1 = settings()
    cfg2 = settings()
    assert cfg1 is cfg2


def test_settings_cache_clear(monkeypatch):
    monkeypatch.setenv("BINARY_ANALYSIS_USE_E2B", "false")
    monkeypatch.delenv("E2B_API_KEY", raising=False)
    settings.cache_clear()
    cfg1 = settings()
    settings.cache_clear()
    cfg2 = settings()
    assert cfg1 is not cfg2


# ---------------------------------------------------------------------------
# C13: module-level constants
# ---------------------------------------------------------------------------


def test_token_budget_hard_cap_value():
    assert TOKEN_BUDGET_HARD_CAP == 120_000


def test_default_token_budget_value():
    assert DEFAULT_TOKEN_BUDGET == 80_000


def test_default_max_rounds_value():
    assert DEFAULT_MAX_ROUNDS == 15


def test_default_max_recursion_depth_value():
    assert DEFAULT_MAX_RECURSION_DEPTH == 2


# ---------------------------------------------------------------------------
# C13: DocumentSettings defaults
# ---------------------------------------------------------------------------


class TestDocumentSettingsDefaults:
    def setup_method(self):
        document_settings.cache_clear()

    def teardown_method(self):
        document_settings.cache_clear()

    def test_max_recursion_depth_default(self, monkeypatch):
        monkeypatch.delenv("DEEPAGENT_MAX_RECURSION_DEPTH", raising=False)
        cfg = DocumentSettings(_env_file=None)
        assert cfg.max_recursion_depth == DEFAULT_MAX_RECURSION_DEPTH

    def test_token_budget_default(self, monkeypatch):
        monkeypatch.delenv("DEEPAGENT_TOKEN_BUDGET", raising=False)
        cfg = DocumentSettings(_env_file=None)
        assert cfg.token_budget == DEFAULT_TOKEN_BUDGET

    def test_max_rounds_default(self, monkeypatch):
        monkeypatch.delenv("DEEPAGENT_MAX_ROUNDS", raising=False)
        cfg = DocumentSettings(_env_file=None)
        assert cfg.max_rounds == DEFAULT_MAX_ROUNDS

    def test_vba_simulation_timeout_sec_default(self, monkeypatch):
        monkeypatch.delenv("DEEPAGENT_VBA_SIMULATION_TIMEOUT_SEC", raising=False)
        cfg = DocumentSettings(_env_file=None)
        assert cfg.vba_simulation_timeout_sec == 60

    def test_vba_max_instructions_default(self, monkeypatch):
        monkeypatch.delenv("DEEPAGENT_VBA_MAX_INSTRUCTIONS", raising=False)
        cfg = DocumentSettings(_env_file=None)
        assert cfg.vba_max_instructions == 100_000

    def test_password_list_path_default(self, monkeypatch):
        monkeypatch.delenv("DEEPAGENT_PASSWORD_LIST_PATH", raising=False)
        cfg = DocumentSettings(_env_file=None)
        assert cfg.password_list_path == Path(
            "/etc/deepagent/container_password_list.yaml"
        )


# ---------------------------------------------------------------------------
# C13: DocumentSettings env var overrides
# ---------------------------------------------------------------------------


class TestDocumentSettingsEnvOverrides:
    def setup_method(self):
        document_settings.cache_clear()

    def teardown_method(self):
        document_settings.cache_clear()

    def test_max_recursion_depth_override(self, monkeypatch):
        monkeypatch.setenv("DEEPAGENT_MAX_RECURSION_DEPTH", "5")
        cfg = DocumentSettings(_env_file=None)
        assert cfg.max_recursion_depth == 5

    def test_token_budget_override(self, monkeypatch):
        monkeypatch.setenv("DEEPAGENT_TOKEN_BUDGET", "60000")
        cfg = DocumentSettings(_env_file=None)
        assert cfg.token_budget == 60_000

    def test_max_rounds_override(self, monkeypatch):
        monkeypatch.setenv("DEEPAGENT_MAX_ROUNDS", "20")
        cfg = DocumentSettings(_env_file=None)
        assert cfg.max_rounds == 20

    def test_vba_simulation_timeout_sec_override(self, monkeypatch):
        monkeypatch.setenv("DEEPAGENT_VBA_SIMULATION_TIMEOUT_SEC", "120")
        cfg = DocumentSettings(_env_file=None)
        assert cfg.vba_simulation_timeout_sec == 120

    def test_vba_max_instructions_override(self, monkeypatch):
        monkeypatch.setenv("DEEPAGENT_VBA_MAX_INSTRUCTIONS", "50000")
        cfg = DocumentSettings(_env_file=None)
        assert cfg.vba_max_instructions == 50_000

    def test_password_list_path_override(self, monkeypatch):
        monkeypatch.setenv("DEEPAGENT_PASSWORD_LIST_PATH", "/custom/passwords.yaml")
        cfg = DocumentSettings(_env_file=None)
        assert cfg.password_list_path == Path("/custom/passwords.yaml")


# ---------------------------------------------------------------------------
# C13: document_settings() singleton
# ---------------------------------------------------------------------------


def test_document_settings_returns_instance(monkeypatch):
    monkeypatch.delenv("DEEPAGENT_TOKEN_BUDGET", raising=False)
    document_settings.cache_clear()
    cfg = document_settings()
    assert isinstance(cfg, DocumentSettings)
    document_settings.cache_clear()


def test_document_settings_cached(monkeypatch):
    monkeypatch.delenv("DEEPAGENT_TOKEN_BUDGET", raising=False)
    document_settings.cache_clear()
    cfg1 = document_settings()
    cfg2 = document_settings()
    assert cfg1 is cfg2
    document_settings.cache_clear()


def test_document_settings_cache_clear(monkeypatch):
    monkeypatch.delenv("DEEPAGENT_TOKEN_BUDGET", raising=False)
    document_settings.cache_clear()
    cfg1 = document_settings()
    document_settings.cache_clear()
    cfg2 = document_settings()
    assert cfg1 is not cfg2
    document_settings.cache_clear()
