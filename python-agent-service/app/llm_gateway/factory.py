"""ModelFactory: create LangChain BaseChatModel from model_id."""

import os
from typing import Any

import httpx
import structlog
from langchain_anthropic import ChatAnthropic
from langchain_core.language_models import BaseChatModel
from langchain_google_genai import ChatGoogleGenerativeAI
from langchain_openai import ChatOpenAI

from app.config import get_settings
from app.llm_gateway.registry import get_registry
from app.llm_gateway.request_context import get_request_llm_model_id

logger = structlog.get_logger()

_REVERSE_PROVIDER_ALIASES: dict[str, str] = {
    "google_genai": "google",
    "moonshot": "kimi",
    "zhipu": "glm",
}


class _OpenCodeSerialToolCallChatOpenAI(ChatOpenAI):
    """Force serial tool calls for OpenCode GPT models."""

    def bind_tools(
        self,
        tools: Any,
        *,
        tool_choice: Any = None,
        **kwargs: Any,
    ) -> Any:
        """Bind tools while disabling provider-corrupting parallel tool calls."""
        kwargs["parallel_tool_calls"] = False
        return super().bind_tools(
            tools,
            tool_choice=tool_choice,
            **kwargs,
        )


def _denormalize_model_ref(model_ref: str) -> str | None:
    """Convert ``provider:model`` (init_chat_model format) back to ``provider/model`` (gateway registry format).

    Returns None if the input is already in gateway format or cannot be converted.
    """
    if not model_ref or "/" in model_ref or ":" not in model_ref:
        return None
    provider, name = model_ref.split(":", 1)
    provider = provider.strip()
    name = name.strip()
    if not provider or not name:
        return None
    provider = _REVERSE_PROVIDER_ALIASES.get(provider, provider)
    return f"{provider}/{name}"


def _make_opencode_url_rewrite_hook(target_suffix: str):
    """Create httpx request hook to rewrite /chat/completions to OpenCode endpoint.

    OpenCode Zen uses different endpoints: /responses, /messages, models/{id}.
    ChatOpenAI always appends /chat/completions; we intercept and replace the path.
    """

    async def hook(request: httpx.Request) -> None:
        url = request.url
        if "opencode.ai" in str(url) and url.path.rstrip("/").endswith("chat/completions"):
            new_path = url.path.replace("/chat/completions", "/" + target_suffix.lstrip("/"))
            request.url = url.copy_with(path=new_path)

    return hook


def _opencode_zen_gemini_chat_model(api_key: str, zen_base: str, sdk_model: str, timeout: float | None = None) -> ChatGoogleGenerativeAI:
    """ChatGoogleGenerativeAI against OpenCode Zen ``/zen/v1/models/{id}:generateContent``.

    LangChain's Google client defaults to ``api_version='v1beta'``, which would produce
    ``/zen/v1/v1beta/models/...`` — Zen expects ``/zen/v1/models/{id}:generateContent``.
    Clear ``api_version`` so the SDK uses a ``/models/...`` path under the custom base.

    Note: Zen may still return 500 (e.g. ``promptTokenCount``) due to gateway bugs when
    mapping Google usage metadata; this is the correct client protocol for Gemini on Zen.
    """
    base = zen_base.rstrip("/")
    kw: dict[str, Any] = {
        "model": sdk_model,
        "google_api_key": api_key,
        "base_url": base,
    }
    if timeout:
        kw["timeout"] = timeout
    llm = ChatGoogleGenerativeAI(**kw)
    api_client = llm.client._api_client
    api_client._http_options = api_client._http_options.model_copy(update={"api_version": None})
    return llm


def _no_provider_error() -> ValueError:
    """Build helpful error when no provider has API key."""
    from pathlib import Path
    env_path = Path(__file__).resolve().parents[2] / ".env"
    return ValueError(
        "No LLM provider configured. Add at least one API key to "
        f"{env_path}. Example keys: GOOGLE_API_KEY, OPENAI_API_KEY, ANTHROPIC_API_KEY, "
        "OPENROUTER_API_KEY, OPENCODE_ZEN_API_KEY, DOUBAO_API_KEY. See .env.example for the full list."
    )


def get_model(model_id: str | None = None) -> BaseChatModel:
    """Create LangChain chat model for given model_id.

    Args:
        model_id: Model id (e.g. "anthropic/claude-sonnet-4"). If None, uses the request-scoped id
            set during ``stream_analyze_request`` / ``stream_resume_request`` when present;
            otherwise registry ``default_model`` or first available model. If a non-None id is invalid,
            falls back the same way (explicit invalid id does not read request scope).

    Returns:
        BaseChatModel instance.

    Raises:
        ValueError: When no provider has API key configured.
    """
    registry = get_registry()
    config = registry.get_model_config(model_id) if model_id else None
    # Configuration._normalize_model_ref converts "provider/model" → "provider:model"
    # for init_chat_model compat, but the registry stores "provider/model".
    # Try de-normalizing when direct lookup fails.
    if config is None and model_id:
        denorm = _denormalize_model_ref(model_id)
        if denorm:
            config = registry.get_model_config(denorm)
            if config is not None:
                model_id = denorm
                logger.debug("Resolved model via denormalization", original=model_id, resolved=denorm)
    if config is None and model_id is None:
        ctx_id = get_request_llm_model_id()
        if ctx_id:
            config = registry.get_model_config(ctx_id)
            if config is not None:
                model_id = ctx_id
                logger.debug("Using request-scoped model id", model_id=model_id)
    if config is None:
        default_id = registry.get_default_model()
        config = registry.get_model_config(default_id)
        if config is not None:
            model_id = default_id
            logger.debug("Using default model", model_id=model_id)
        else:
            # Fallback: use first available model (default's provider may have no key)
            available = registry.list_models()
            if available:
                first_id = available[0].id
                config = registry.get_model_config(first_id)
                if config:
                    model_id = first_id
                    logger.debug("Using first available model (default has no key)", model_id=model_id)
        if config is None:
            raise _no_provider_error()

    provider_id = config["provider_id"]
    model_cfg = config["model"]
    provider_cfg = config["provider"]
    api_key = provider_cfg.get("api_key") or ""
    base_url = provider_cfg.get("base_url")
    sdk_model = model_cfg.get("sdk_model") or model_id

    settings = get_settings()
    llm_timeout: int | None = getattr(settings, "llm_request_timeout_seconds", None)

    # Anthropic — field: default_request_timeout (alias "timeout"); max_retries default=2
    if provider_id == "anthropic":
        kwargs: dict[str, Any] = {
            "model": sdk_model,
            "api_key": api_key,
            "max_tokens": 16000,
            "max_retries": 0,
        }
        if llm_timeout:
            kwargs["timeout"] = float(llm_timeout)
        if getattr(settings, "enable_anthropic_thinking", False):
            kwargs["thinking"] = {"type": "enabled", "budget_tokens": 10000}
        return ChatAnthropic(**kwargs)

    # OpenAI — field: request_timeout (alias "timeout"); max_retries default=None→SDK 2
    if provider_id == "openai":
        kwargs = {
            "model": sdk_model,
            "api_key": api_key,
            "max_retries": 0,
        }
        if base_url:
            kwargs["base_url"] = base_url
        if llm_timeout:
            kwargs["timeout"] = float(llm_timeout)
        return ChatOpenAI(**kwargs)

    # Google
    if provider_id == "google":
        kwargs = {"model": sdk_model, "google_api_key": provider_cfg.get("api_key")}
        if llm_timeout:
            kwargs["timeout"] = float(llm_timeout)
        if getattr(settings, "enable_gemini_thinking", False):
            kwargs["thinking_budget"] = 8192
            kwargs["include_thoughts"] = True  # Return thought blocks for reasoning process
        try:
            return ChatGoogleGenerativeAI(**kwargs)
        except TypeError:
            kwargs.pop("thinking_budget", None)
            kwargs.pop("include_thoughts", None)
            kwargs.pop("timeout", None)
            return ChatGoogleGenerativeAI(**kwargs)

    # OpenAI-compatible: kimi, minimax, glm, doubao
    if provider_id in ("kimi", "minimax", "glm", "doubao"):
        url = base_url or ""
        if not url and provider_id == "doubao":
            url = "https://ark.cn-beijing.volces.com/api/v3"
        kw: dict[str, Any] = {
            "model": sdk_model,
            "api_key": api_key,
            "base_url": url.rstrip("/") if url else None,
            "stream_usage": True,
            "max_retries": 0,
        }
        if llm_timeout:
            kw["timeout"] = float(llm_timeout)
        return ChatOpenAI(**kw)

    # OpenRouter: one OpenAI-compatible gateway for many upstream providers.
    # Keep gateway ids as openrouter/*, but send provider-native sdk_model.
    if provider_id == "openrouter":
        headers: dict[str, str] = {}
        app_url = getattr(settings, "openrouter_app_url", None) or os.environ.get(
            "OPENROUTER_APP_URL"
        )
        app_title = getattr(settings, "openrouter_app_title", None) or os.environ.get(
            "OPENROUTER_APP_TITLE"
        )
        if app_url:
            headers["HTTP-Referer"] = app_url
        if app_title:
            headers["X-OpenRouter-Title"] = app_title

        # LangChain ChatOpenAI: setting top-level ``reasoning=...`` forces the OpenAI
        # **Responses** API (responses.create). OpenRouter reasoning for chat models
        # must stay on **chat/completions** via ``extra_body={"reasoning": ...}``.
        kw_or: dict[str, Any] = {
            "model": sdk_model,
            "api_key": api_key,
            "base_url": (base_url or "https://openrouter.ai/api/v1").rstrip("/"),
            "stream_usage": True,
            "max_retries": 0,
            "use_responses_api": False,
        }
        if headers:
            kw_or["default_headers"] = headers
        if llm_timeout:
            kw_or["timeout"] = float(llm_timeout)
        if getattr(settings, "openrouter_reasoning_enabled", True):
            effort = (
                getattr(settings, "openrouter_reasoning_effort", None) or "medium"
            ).strip() or "medium"
            kw_or["extra_body"] = {"reasoning": {"effort": effort}}
        return ChatOpenAI(**kw_or)

    # OpenCode Zen: different endpoints per model family.
    # - Claude (messages): use ChatAnthropic + base_url; /messages expects Anthropic format.
    # - GPT (responses): Zen /responses expects OpenAI Responses API (input not messages) -> 400.
    #   Use Zen chat/completions with sdk_model (e.g. gpt-5.4); Zen accepts messages format there.
    # - Gemini (models/xxx): ChatGoogleGenerativeAI (Google GenAI protocol); see
    #   _opencode_zen_gemini_chat_model for api_version path fix. Zen may still 500 on usage.
    # - MiniMax/GLM/Kimi (chat/completions): use ChatOpenAI + zen base.
    if provider_id == "opencode":
        base = (base_url or "https://opencode.ai/zen/v1").rstrip("/")
        suffix = model_cfg.get("endpoint_suffix", "chat/completions")

        if suffix == "messages":
            # Claude models: ChatAnthropic with Zen base.
            zen_base = (base_url or "https://opencode.ai/zen/v1").rstrip("/").replace("/v1", "").rstrip("/") or "https://opencode.ai/zen"
            kw_oc: dict[str, Any] = {
                "model": sdk_model,
                "api_key": api_key,
                "base_url": zen_base,
                "max_tokens": 16000,
                "max_retries": 0,
            }
            if llm_timeout:
                kw_oc["timeout"] = float(llm_timeout)
            return ChatAnthropic(**kw_oc)
        if suffix == "responses":
            # GPT models: Zen /responses expects "input" not "messages" -> 400.
            # Zen chat/completions accepts messages; use sdk_model (e.g. gpt-5.4) without prefix.
            # Disable parallel_tool_calls: Zen gateway may drop the streaming
            # chunk "index" field, causing LangChain to merge parallel tool-call
            # deltas into a single slot (e.g. "read_filegrepgrep…").
            kw_gpt: dict[str, Any] = {
                "model": sdk_model,
                "api_key": api_key,
                "base_url": base,
                "disable_streaming": "tool_calling",
                "model_kwargs": {"parallel_tool_calls": False},
                "max_retries": 0,
            }
            if llm_timeout:
                kw_gpt["timeout"] = float(llm_timeout)
            return _OpenCodeSerialToolCallChatOpenAI(**kw_gpt)
        if suffix.startswith("models/"):
            return _opencode_zen_gemini_chat_model(
                api_key=api_key,
                zen_base=base,
                sdk_model=sdk_model,
                timeout=float(llm_timeout) if llm_timeout else None,
            )
        kw_default: dict[str, Any] = {
            "model": sdk_model,
            "api_key": api_key,
            "base_url": base,
            "max_retries": 0,
        }
        if llm_timeout:
            kw_default["timeout"] = float(llm_timeout)
        return ChatOpenAI(**kw_default)

    raise ValueError(f"Unknown provider: {provider_id}")
