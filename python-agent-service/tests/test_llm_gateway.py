"""Unit tests for LLM Gateway (ModelRegistry, ModelFactory)."""

from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import pytest

# Ensure app is on path
import sys
APP_DIR = Path(__file__).parent.parent
if str(APP_DIR) not in sys.path:
    sys.path.insert(0, str(APP_DIR))


@pytest.fixture
def minimal_config(tmp_path):
    """Create minimal llm_gateway.yaml with one provider."""
    config = tmp_path / "llm_gateway.yaml"
    config.write_text("""
providers:
  google:
    env_key: GOOGLE_API_KEY
    base_url: null
    models:
      - id: google/gemini-test
        name: Gemini Test
        sdk_model: gemini-test
  anthropic:
    env_key: ANTHROPIC_API_KEY
    base_url: null
    models:
      - id: anthropic/claude-test
        name: Claude Test
        sdk_model: claude-test
default_model: google/gemini-test
""", encoding="utf-8")
    return config


@pytest.fixture
def registry_with_google_key(monkeypatch, minimal_config):
    """Registry with GOOGLE_API_KEY set."""
    monkeypatch.setenv("GOOGLE_API_KEY", "test-key-123")
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    from app.llm_gateway.registry import ModelRegistry
    reg = ModelRegistry(config_path=minimal_config)
    return reg


def test_registry_filters_providers_without_key(registry_with_google_key):
    """Providers without API key are filtered from list_models."""
    models = registry_with_google_key.list_models()
    assert len(models) >= 1
    for m in models:
        assert m.provider == "google"
    assert any(m.id == "google/gemini-test" for m in models)


def test_registry_list_models_returns_correct_structure(registry_with_google_key):
    """list_models returns ModelInfo with id, name, provider."""
    models = registry_with_google_key.list_models()
    assert len(models) > 0
    m = models[0]
    assert hasattr(m, "id")
    assert hasattr(m, "name")
    assert hasattr(m, "provider")
    assert m.id == "google/gemini-test"
    assert m.name == "Gemini Test"
    assert m.provider == "google"


def test_registry_get_model_config_valid(registry_with_google_key):
    """get_model_config returns config for valid model_id."""
    config = registry_with_google_key.get_model_config("google/gemini-test")
    assert config is not None
    assert config["provider_id"] == "google"
    assert config["model"]["id"] == "google/gemini-test"
    assert config["model"]["sdk_model"] == "gemini-test"
    assert "api_key" in config["provider"]


def test_registry_get_model_config_invalid(registry_with_google_key):
    """get_model_config returns None for invalid model_id."""
    assert registry_with_google_key.get_model_config("invalid/model") is None
    assert registry_with_google_key.get_model_config("google/nonexistent") is None
    assert registry_with_google_key.get_model_config("") is None
    assert registry_with_google_key.get_model_config(None) is None


def test_registry_get_model_config_no_key_returns_none(monkeypatch, minimal_config):
    """get_model_config returns None when provider has no API key."""
    monkeypatch.delenv("GOOGLE_API_KEY", raising=False)
    # Registry reads API keys from ENV_PATH file; isolate from workspace .env.
    monkeypatch.setattr("app.llm_gateway.registry.ENV_PATH", minimal_config.parent / ".missing-env")
    import app.llm_gateway.registry as reg_mod

    reg_mod._ENV_CACHE = None
    from app.llm_gateway.registry import ModelRegistry

    reg = ModelRegistry(config_path=minimal_config)
    assert reg.get_model_config("google/gemini-test") is None


def test_registry_get_default_model(registry_with_google_key):
    """get_default_model returns configured default."""
    assert registry_with_google_key.get_default_model() == "google/gemini-test"


def test_factory_uses_request_context_when_model_id_none(monkeypatch):
    """get_model(None) uses request-scoped gateway id when set and valid."""
    with patch("app.llm_gateway.factory.get_registry") as mock_get:
        mock_reg = type("R", (), {})()

        def _cfg(mid: str | None):
            if mid == "anthropic/claude-test":
                return {
                    "provider_id": "anthropic",
                    "model_id": mid,
                    "model": {"sdk_model": "claude-test"},
                    "provider": {"api_key": "test-key", "base_url": None},
                }
            return None

        mock_reg.get_model_config = _cfg
        mock_reg.get_default_model = lambda: "google/gemini-test"
        mock_reg.list_models = lambda: []
        mock_get.return_value = mock_reg

        from app.llm_gateway.factory import get_model
        from app.llm_gateway.request_context import reset_request_llm_model_id, set_request_llm_model_id
        from langchain_anthropic import ChatAnthropic

        tok = set_request_llm_model_id("anthropic/claude-test")
        try:
            model = get_model(None)
            assert isinstance(model, ChatAnthropic)
        finally:
            reset_request_llm_model_id(tok)


def test_factory_returns_chat_model(monkeypatch, minimal_config):
    """get_model returns a LangChain BaseChatModel."""
    monkeypatch.setenv("GOOGLE_API_KEY", "test-key")
    with patch("app.llm_gateway.factory.get_registry") as mock_get:
        mock_reg = type("R", (), {})()
        mock_reg.get_model_config = lambda mid: {
            "provider_id": "google",
            "model_id": "google/gemini-test",
            "model": {"sdk_model": "gemini-test"},
            "provider": {"api_key": "test-key", "base_url": None},
        } if mid else None
        mock_reg.get_default_model = lambda: "google/gemini-test"
        mock_get.return_value = mock_reg

        from app.llm_gateway.factory import get_model
        from langchain_core.language_models import BaseChatModel

        model = get_model("google/gemini-test")
        assert isinstance(model, BaseChatModel)


def test_factory_anthropic_provider(monkeypatch):
    """Factory creates ChatAnthropic for anthropic provider."""
    with patch("app.llm_gateway.factory.get_registry") as mock_get:
        mock_reg = type("R", (), {})()
        mock_reg.get_model_config = lambda mid: {
            "provider_id": "anthropic",
            "model_id": "anthropic/claude-test",
            "model": {"sdk_model": "claude-test"},
            "provider": {"api_key": "test-key", "base_url": None},
        }
        mock_reg.get_default_model = lambda: "anthropic/claude-test"
        mock_get.return_value = mock_reg

        from app.llm_gateway.factory import get_model
        from langchain_anthropic import ChatAnthropic

        model = get_model("anthropic/claude-test")
        assert isinstance(model, ChatAnthropic)


def test_factory_openai_provider(monkeypatch):
    """Factory creates ChatOpenAI for openai provider."""
    with patch("app.llm_gateway.factory.get_registry") as mock_get:
        mock_reg = type("R", (), {})()
        mock_reg.get_model_config = lambda mid: {
            "provider_id": "openai",
            "model_id": "openai/gpt-4o",
            "model": {"sdk_model": "gpt-4o"},
            "provider": {"api_key": "test-key", "base_url": None},
        }
        mock_reg.get_default_model = lambda: "openai/gpt-4o"
        mock_get.return_value = mock_reg

        from app.llm_gateway.factory import get_model
        from langchain_openai import ChatOpenAI

        model = get_model("openai/gpt-4o")
        assert isinstance(model, ChatOpenAI)


@pytest.mark.parametrize("provider", ["kimi", "minimax", "glm", "doubao"])
def test_factory_openai_compatible_provider(monkeypatch, provider):
    """Factory creates ChatOpenAI for kimi/minimax/glm/doubao."""
    with patch("app.llm_gateway.factory.get_registry") as mock_get:
        mock_reg = type("R", (), {})()
        mock_reg.get_model_config = lambda mid: {
            "provider_id": provider,
            "model_id": f"{provider}/test",
            "model": {"sdk_model": "test-model"},
            "provider": {"api_key": "test-key", "base_url": f"https://{provider}.com/v1"},
        }
        mock_reg.get_default_model = lambda: "google/gemini-test"
        mock_get.return_value = mock_reg

        from app.llm_gateway.factory import get_model
        from langchain_openai import ChatOpenAI

        model = get_model(f"{provider}/test")
        assert isinstance(model, ChatOpenAI)
        assert getattr(model, "stream_usage", None) is True


def test_registry_supports_openrouter_provider(tmp_path, monkeypatch):
    """OPENROUTER_API_KEY enables OpenRouter models without enabling OpenCode."""
    cfg = tmp_path / "llm_gateway.yaml"
    cfg.write_text(
        """
providers:
  openrouter:
    env_key: OPENROUTER_API_KEY
    base_url: https://openrouter.ai/api/v1
    models:
      - id: openrouter/anthropic/claude-opus-4.7
        name: Claude Opus 4.7 (OpenRouter)
        sdk_model: anthropic/claude-opus-4.7
        context_window: 1000000
        max_output_tokens: 65536
  opencode:
    env_key: OPENCODE_ZEN_API_KEY
    base_url: https://opencode.ai/zen/v1
    models:
      - id: opencode/gpt-5.5
        name: GPT 5.5 (Zen)
        sdk_model: gpt-5.5
        context_window: 1100000
        max_output_tokens: 16384
default_model: openrouter/anthropic/claude-opus-4.7
""",
        encoding="utf-8",
    )
    monkeypatch.setenv("OPENROUTER_API_KEY", "test-openrouter-key")
    monkeypatch.delenv("OPENCODE_ZEN_API_KEY", raising=False)
    import app.llm_gateway.registry as reg_mod

    reg_mod._ENV_CACHE = None
    monkeypatch.setattr(reg_mod, "ENV_PATH", tmp_path / ".missing-env")

    from app.llm_gateway.registry import ModelRegistry

    reg = ModelRegistry(config_path=cfg)
    models = reg.list_models()

    assert [m.id for m in models] == ["openrouter/anthropic/claude-opus-4.7"]
    assert models[0].provider == "openrouter"
    assert models[0].context_window == 1_000_000
    assert models[0].max_output_tokens == 65536
    assert reg.get_model_config("opencode/gpt-5.5") is None


def test_factory_openrouter_provider_uses_chat_openai(monkeypatch):
    """OpenRouter is OpenAI-compatible but keeps the gateway id distinct."""
    with patch("app.llm_gateway.factory.get_registry") as mock_get:
        mock_reg = type("R", (), {})()
        mock_reg.get_model_config = lambda mid: {
            "provider_id": "openrouter",
            "model_id": "openrouter/anthropic/claude-opus-4.7",
            "model": {"sdk_model": "anthropic/claude-opus-4.7"},
            "provider": {
                "api_key": "test-openrouter-key",
                "base_url": "https://openrouter.ai/api/v1",
            },
        }
        mock_reg.get_default_model = lambda: "openrouter/anthropic/claude-opus-4.7"
        mock_get.return_value = mock_reg

        from app.llm_gateway.factory import get_model
        from langchain_openai import ChatOpenAI

        model = get_model("openrouter/anthropic/claude-opus-4.7")
        assert isinstance(model, ChatOpenAI)
        assert model.model_name == "anthropic/claude-opus-4.7"
        assert str(model.openai_api_base).rstrip("/") == "https://openrouter.ai/api/v1"
        assert getattr(model, "stream_usage", None) is True


def test_factory_openrouter_passes_reasoning_when_enabled(monkeypatch):
    """OpenRouter: reasoning stays on chat/completions via ``extra_body`` only."""
    monkeypatch.setattr(
        "app.llm_gateway.factory.get_settings",
        lambda: SimpleNamespace(
            llm_request_timeout_seconds=None,
            openrouter_app_url=None,
            openrouter_app_title=None,
            openrouter_reasoning_enabled=True,
            openrouter_reasoning_effort="high",
        ),
    )
    with patch("app.llm_gateway.factory.get_registry") as mock_get:
        mock_reg = type("R", (), {})()
        mock_reg.get_model_config = lambda mid: {
            "provider_id": "openrouter",
            "model_id": "openrouter/anthropic/claude-opus-4.7",
            "model": {"sdk_model": "anthropic/claude-opus-4.7"},
            "provider": {
                "api_key": "test-openrouter-key",
                "base_url": "https://openrouter.ai/api/v1",
            },
        }
        mock_reg.get_default_model = lambda: "openrouter/anthropic/claude-opus-4.7"
        mock_get.return_value = mock_reg

        from app.llm_gateway.factory import get_model
        from langchain_openai import ChatOpenAI

        model = get_model("openrouter/anthropic/claude-opus-4.7")
        assert isinstance(model, ChatOpenAI)
        assert getattr(model, "reasoning", None) is None
        assert getattr(model, "extra_body") == {"reasoning": {"effort": "high"}}
        assert model.use_responses_api is False


def test_factory_openrouter_omits_reasoning_when_disabled(monkeypatch):
    """OpenRouter: no ChatOpenAI.reasoning when openrouter_reasoning_enabled is false."""
    monkeypatch.setattr(
        "app.llm_gateway.factory.get_settings",
        lambda: SimpleNamespace(
            llm_request_timeout_seconds=None,
            openrouter_app_url=None,
            openrouter_app_title=None,
            openrouter_reasoning_enabled=False,
            openrouter_reasoning_effort="medium",
        ),
    )
    with patch("app.llm_gateway.factory.get_registry") as mock_get:
        mock_reg = type("R", (), {})()
        mock_reg.get_model_config = lambda mid: {
            "provider_id": "openrouter",
            "model_id": "openrouter/anthropic/claude-opus-4.7",
            "model": {"sdk_model": "anthropic/claude-opus-4.7"},
            "provider": {
                "api_key": "test-openrouter-key",
                "base_url": "https://openrouter.ai/api/v1",
            },
        }
        mock_reg.get_default_model = lambda: "openrouter/anthropic/claude-opus-4.7"
        mock_get.return_value = mock_reg

        from app.llm_gateway.factory import get_model
        from langchain_openai import ChatOpenAI

        model = get_model("openrouter/anthropic/claude-opus-4.7")
        assert isinstance(model, ChatOpenAI)
        assert getattr(model, "reasoning", None) is None
        assert getattr(model, "extra_body", None) is None


def test_factory_openrouter_attribution_headers(monkeypatch):
    """OpenRouter attribution env vars become optional default headers."""
    monkeypatch.setenv("OPENROUTER_APP_URL", "https://secmanus.example")
    monkeypatch.setenv("OPENROUTER_APP_TITLE", "SecManus Workspace")
    with patch("app.llm_gateway.factory.get_registry") as mock_get:
        mock_reg = type("R", (), {})()
        mock_reg.get_model_config = lambda mid: {
            "provider_id": "openrouter",
            "model_id": "openrouter/anthropic/claude-sonnet-4.6",
            "model": {"sdk_model": "anthropic/claude-sonnet-4.6"},
            "provider": {
                "api_key": "test-openrouter-key",
                "base_url": "https://openrouter.ai/api/v1",
            },
        }
        mock_reg.get_default_model = lambda: "openrouter/anthropic/claude-sonnet-4.6"
        mock_get.return_value = mock_reg

        from app.llm_gateway.factory import get_model

        model = get_model("openrouter/anthropic/claude-sonnet-4.6")
        headers = getattr(model, "default_headers", None)
        assert headers["HTTP-Referer"] == "https://secmanus.example"
        assert headers["X-OpenRouter-Title"] == "SecManus Workspace"


def test_factory_opencode_provider(monkeypatch):
    """Factory creates ChatOpenAI for opencode GPT (responses) via api.opencode.ai."""
    with patch("app.llm_gateway.factory.get_registry") as mock_get:
        mock_reg = type("R", (), {})()
        mock_reg.get_model_config = lambda mid: {
            "provider_id": "opencode",
            "model_id": "opencode/gpt-5.3-codex",
            "model": {"sdk_model": "gpt-5.3-codex", "endpoint_suffix": "responses"},
            "provider": {"api_key": "test-key", "base_url": "https://opencode.ai/zen/v1"},
        }
        mock_reg.get_default_model = lambda: "opencode/gpt-5.3-codex"
        mock_get.return_value = mock_reg

        from app.llm_gateway.factory import get_model
        from langchain_openai import ChatOpenAI

        model = get_model("opencode/gpt-5.3-codex")
        assert isinstance(model, ChatOpenAI)
        # responses endpoint uses api.opencode.ai (no URL rewrite); no http_async_client
        assert getattr(model, "http_async_client", None) is None


def test_factory_opencode_gpt_bind_tools_forces_serial_tool_calls(monkeypatch):
    """OpenCode GPT bind_tools uses the safest tool-calling mode."""
    with patch("app.llm_gateway.factory.get_registry") as mock_get:
        mock_reg = type("R", (), {})()
        mock_reg.get_model_config = lambda mid: {
            "provider_id": "opencode",
            "model_id": "opencode/gpt-5.3-codex",
            "model": {
                "sdk_model": "gpt-5.3-codex",
                "endpoint_suffix": "responses",
            },
            "provider": {
                "api_key": "test-key",
                "base_url": "https://opencode.ai/zen/v1",
            },
        }
        mock_reg.get_default_model = lambda: "opencode/gpt-5.3-codex"
        mock_get.return_value = mock_reg

        from app.llm_gateway.factory import get_model
        from langchain_core.tools import StructuredTool

        def echo_tool(value: str) -> str:
            return value

        tool = StructuredTool.from_function(
            echo_tool,
            name="echo_tool",
            description="Echo a value.",
        )
        model = get_model("opencode/gpt-5.3-codex")
        bound = model.bind_tools([tool], parallel_tool_calls=True)

        assert getattr(model, "disable_streaming", None) == "tool_calling"
        assert bound.kwargs["parallel_tool_calls"] is False


def test_factory_opencode_gemini_uses_chat_google_generative_ai(monkeypatch):
    """Zen Gemini (models/*) uses ChatGoogleGenerativeAI with cleared api_version path."""
    with patch("app.llm_gateway.factory.get_registry") as mock_get:
        mock_reg = type("R", (), {})()
        mock_reg.get_model_config = lambda mid: {
            "provider_id": "opencode",
            "model_id": "opencode/gemini-3-flash",
            "model": {
                "sdk_model": "gemini-3-flash",
                "endpoint_suffix": "models/gemini-3-flash",
            },
            "provider": {"api_key": "test-key", "base_url": "https://opencode.ai/zen/v1"},
        }
        mock_reg.get_default_model = lambda: "opencode/gemini-3-flash"
        mock_get.return_value = mock_reg

        from app.llm_gateway.factory import get_model
        from langchain_google_genai import ChatGoogleGenerativeAI

        model = get_model("opencode/gemini-3-flash")
        assert isinstance(model, ChatGoogleGenerativeAI)
        assert model.model == "gemini-3-flash"
        assert model.client._api_client._http_options.base_url.rstrip("/") == "https://opencode.ai/zen/v1"
        assert model.client._api_client._http_options.api_version is None


def test_factory_opencode_claude_uses_chat_anthropic(monkeypatch):
    """Factory creates ChatAnthropic for opencode Claude (messages endpoint)."""
    with patch("app.llm_gateway.factory.get_registry") as mock_get:
        mock_reg = type("R", (), {})()
        mock_reg.get_model_config = lambda mid: {
            "provider_id": "opencode",
            "model_id": "opencode/claude-sonnet-4-6",
            "model": {"sdk_model": "claude-sonnet-4-6", "endpoint_suffix": "messages"},
            "provider": {"api_key": "test-key", "base_url": "https://opencode.ai/zen/v1"},
        }
        mock_reg.get_default_model = lambda: "opencode/claude-sonnet-4-6"
        mock_get.return_value = mock_reg

        from app.llm_gateway.factory import get_model
        from langchain_anthropic import ChatAnthropic

        model = get_model("opencode/claude-sonnet-4-6")
        assert isinstance(model, ChatAnthropic)
        assert model.model == "claude-sonnet-4-6"
        api_url = getattr(model, "base_url", None) or getattr(model, "anthropic_api_url", None)
        assert api_url and "opencode.ai/zen" in str(api_url)


def test_factory_opencode_chat_completions_no_http_client(monkeypatch):
    """Factory does not pass http_async_client for chat/completions endpoint."""
    with patch("app.llm_gateway.factory.get_registry") as mock_get:
        mock_reg = type("R", (), {})()
        mock_reg.get_model_config = lambda mid: {
            "provider_id": "opencode",
            "model_id": "opencode/minimax-m2.5",
            "model": {"sdk_model": "minimax-m2.5", "endpoint_suffix": "chat/completions"},
            "provider": {"api_key": "test-key", "base_url": "https://opencode.ai/zen/v1"},
        }
        mock_reg.get_default_model = lambda: "opencode/minimax-m2.5"
        mock_get.return_value = mock_reg

        from app.llm_gateway.factory import get_model
        from langchain_openai import ChatOpenAI

        model = get_model("opencode/minimax-m2.5")
        assert isinstance(model, ChatOpenAI)
        # chat/completions uses standard path, no custom client
        assert getattr(model, "http_async_client", None) is None


def test_real_config_includes_current_opencode_zen_models():
    """Real config includes current OpenCode Zen GPT and Kimi models."""
    import yaml

    config_path = APP_DIR / "config" / "llm_gateway.yaml"
    raw = yaml.safe_load(config_path.read_text(encoding="utf-8"))
    opencode_models = {
        m["id"]: m
        for m in raw["providers"]["opencode"]["models"]
    }

    assert opencode_models["opencode/gpt-5.5"] == {
        "id": "opencode/gpt-5.5",
        "name": "GPT 5.5 (Zen)",
        "sdk_model": "gpt-5.5",
        "endpoint_suffix": "responses",
        "context_window": 1100000,
        "max_output_tokens": 16384,
    }
    assert opencode_models["opencode/gpt-5.5-pro"] == {
        "id": "opencode/gpt-5.5-pro",
        "name": "GPT 5.5 Pro (Zen)",
        "sdk_model": "gpt-5.5-pro",
        "endpoint_suffix": "responses",
        "context_window": 1100000,
        "max_output_tokens": 16384,
    }
    assert opencode_models["opencode/kimi-k2.6"] == {
        "id": "opencode/kimi-k2.6",
        "name": "Kimi K2.6 (Zen)",
        "sdk_model": "kimi-k2.6",
        "endpoint_suffix": "chat/completions",
        "context_window": 262144,
        "max_output_tokens": 4096,
    }


def test_real_config_includes_openrouter_models():
    """Real config includes the curated OpenRouter seed models."""
    import yaml

    config_path = APP_DIR / "config" / "llm_gateway.yaml"
    raw = yaml.safe_load(config_path.read_text(encoding="utf-8"))
    provider = raw["providers"]["openrouter"]
    openrouter_models = {m["id"]: m for m in provider["models"]}

    assert provider["env_key"] == "OPENROUTER_API_KEY"
    assert provider["base_url"] == "https://openrouter.ai/api/v1"
    assert openrouter_models["openrouter/anthropic/claude-opus-4.7"] == {
        "id": "openrouter/anthropic/claude-opus-4.7",
        "name": "Claude Opus 4.7 (OpenRouter)",
        "sdk_model": "anthropic/claude-opus-4.7",
        "context_window": 1000000,
        "max_output_tokens": 65536,
    }
    assert openrouter_models["openrouter/anthropic/claude-sonnet-4.6"] == {
        "id": "openrouter/anthropic/claude-sonnet-4.6",
        "name": "Claude Sonnet 4.6 (OpenRouter)",
        "sdk_model": "anthropic/claude-sonnet-4.6",
        "context_window": 1000000,
        "max_output_tokens": 16384,
    }
    assert openrouter_models["openrouter/moonshotai/kimi-k2.6"] == {
        "id": "openrouter/moonshotai/kimi-k2.6",
        "name": "Kimi K2.6 (OpenRouter)",
        "sdk_model": "moonshotai/kimi-k2.6",
        "context_window": 256000,
        "max_output_tokens": 65536,
    }
    assert openrouter_models["openrouter/google/gemini-3.1-pro-preview"] == {
        "id": "openrouter/google/gemini-3.1-pro-preview",
        "name": "Gemini 3.1 Pro (OpenRouter)",
        "sdk_model": "google/gemini-3.1-pro-preview",
        "context_window": 1048576,
        "max_output_tokens": 8192,
    }
    assert openrouter_models["openrouter/google/gemini-3-flash-preview"] == {
        "id": "openrouter/google/gemini-3-flash-preview",
        "name": "Gemini 3 Flash (OpenRouter)",
        "sdk_model": "google/gemini-3-flash-preview",
        "context_window": 1048576,
        "max_output_tokens": 8192,
    }


@pytest.mark.asyncio
async def test_opencode_url_rewrite_hook():
    """URL rewrite hook replaces /chat/completions with target endpoint."""
    import httpx
    from app.llm_gateway.factory import _make_opencode_url_rewrite_hook

    hook = _make_opencode_url_rewrite_hook("responses")
    req = httpx.Request("POST", "https://opencode.ai/zen/v1/chat/completions")
    await hook(req)
    assert req.url.path == "/zen/v1/responses"

    hook2 = _make_opencode_url_rewrite_hook("models/gemini-3-flash")
    req2 = httpx.Request("POST", "https://opencode.ai/zen/v1/chat/completions")
    await hook2(req2)
    assert req2.url.path == "/zen/v1/models/gemini-3-flash"


def test_factory_denormalizes_colon_model_ref():
    """get_model resolves 'provider:model' (normalized) via denormalization to 'provider/model'."""
    with patch("app.llm_gateway.factory.get_registry") as mock_get:
        mock_reg = type("R", (), {})()
        opencode_cfg = {
            "provider_id": "opencode",
            "model_id": "opencode/gemini-3-flash",
            "model": {
                "sdk_model": "gemini-3-flash",
                "endpoint_suffix": "models/gemini-3-flash",
            },
            "provider": {"api_key": "test-key", "base_url": "https://opencode.ai/zen/v1"},
        }
        mock_reg.get_model_config = lambda mid: opencode_cfg if mid == "opencode/gemini-3-flash" else None
        mock_reg.get_default_model = lambda: "opencode/gemini-3-flash"
        mock_reg.list_models = lambda: []
        mock_get.return_value = mock_reg

        from app.llm_gateway.factory import get_model
        from langchain_google_genai import ChatGoogleGenerativeAI

        model = get_model("opencode:gemini-3-flash")
        assert isinstance(model, ChatGoogleGenerativeAI)
        assert model.model == "gemini-3-flash"


def test_factory_denormalizes_google_genai_alias():
    """get_model resolves 'google_genai:model' back to 'google/model'."""
    with patch("app.llm_gateway.factory.get_registry") as mock_get:
        mock_reg = type("R", (), {})()
        google_cfg = {
            "provider_id": "google",
            "model_id": "google/gemini-3-flash-preview",
            "model": {"sdk_model": "gemini-3-flash-preview"},
            "provider": {"api_key": "test-key", "base_url": None},
        }
        mock_reg.get_model_config = lambda mid: google_cfg if mid == "google/gemini-3-flash-preview" else None
        mock_reg.get_default_model = lambda: "google/gemini-3-flash-preview"
        mock_reg.list_models = lambda: []
        mock_get.return_value = mock_reg

        from app.llm_gateway.factory import get_model
        from langchain_google_genai import ChatGoogleGenerativeAI

        model = get_model("google_genai:gemini-3-flash-preview")
        assert isinstance(model, ChatGoogleGenerativeAI)


def test_api_models_returns_200_and_structure():
    """GET /api/models returns 200 and correct structure."""
    from fastapi.testclient import TestClient
    from app.main import app

    client = TestClient(app)
    response = client.get("/api/models")
    assert response.status_code == 200
    data = response.json()
    assert "models" in data
    assert isinstance(data["models"], list)
    for m in data["models"]:
        assert "id" in m
        assert "name" in m
        assert "provider" in m
        # A-04: context_window + max_output_tokens surfaced for the UI indicator.
        assert "context_window" in m and isinstance(m["context_window"], int)
        assert m["context_window"] > 0
        assert "max_output_tokens" in m and isinstance(m["max_output_tokens"], int)
        assert m["max_output_tokens"] > 0


def test_registry_list_models_exposes_context_window(tmp_path, monkeypatch):
    """ModelInfo carries context_window + max_output_tokens read from YAML."""
    cfg = tmp_path / "llm_gateway.yaml"
    cfg.write_text(
        """
providers:
  anthropic:
    env_key: ANTHROPIC_API_KEY
    base_url: null
    models:
      - id: anthropic/c4
        name: Claude 4
        sdk_model: c4
        context_window: 200000
        max_output_tokens: 8192
default_model: anthropic/c4
""",
        encoding="utf-8",
    )
    monkeypatch.setenv("ANTHROPIC_API_KEY", "k")
    import app.llm_gateway.registry as reg_mod
    reg_mod._ENV_CACHE = None
    monkeypatch.setattr(reg_mod, "ENV_PATH", tmp_path / ".missing-env")

    from app.llm_gateway.registry import ModelRegistry
    reg = ModelRegistry(config_path=cfg)
    models = reg.list_models()
    assert len(models) == 1
    assert models[0].context_window == 200_000
    assert models[0].max_output_tokens == 8192


def test_registry_fills_defaults_when_yaml_omits_context_window(tmp_path, monkeypatch):
    """Missing YAML keys fall back to conservative defaults rather than crashing."""
    cfg = tmp_path / "llm_gateway.yaml"
    cfg.write_text(
        """
providers:
  anthropic:
    env_key: ANTHROPIC_API_KEY
    base_url: null
    models:
      - id: anthropic/c4
        name: Claude 4
        sdk_model: c4
default_model: anthropic/c4
""",
        encoding="utf-8",
    )
    monkeypatch.setenv("ANTHROPIC_API_KEY", "k")
    import app.llm_gateway.registry as reg_mod
    reg_mod._ENV_CACHE = None
    monkeypatch.setattr(reg_mod, "ENV_PATH", tmp_path / ".missing-env")

    from app.llm_gateway.registry import (
        DEFAULT_CONTEXT_WINDOW,
        DEFAULT_MAX_OUTPUT_TOKENS,
        ModelRegistry,
    )
    reg = ModelRegistry(config_path=cfg)
    models = reg.list_models()
    assert models[0].context_window == DEFAULT_CONTEXT_WINDOW
    assert models[0].max_output_tokens == DEFAULT_MAX_OUTPUT_TOKENS
