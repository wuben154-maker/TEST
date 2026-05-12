"""Utility functions and helpers for the Deep Research agent."""

import json
import os
import time
from datetime import datetime
from typing import Annotated, Any, List, Literal

import httpx
from langchain_core.language_models import BaseChatModel
from langchain_core.messages import (
    AIMessage,
    HumanMessage,
    MessageLikeRepresentation,
    filter_messages,
)
from langchain_core.runnables import RunnableConfig
from langchain_core.tools import (
    BaseTool,
    InjectedToolArg,
    tool,
)
from app.llm_gateway.factory import get_model
from app.tools.research_tools import WebSearchProvider
from .configuration import Configuration, SearchAPI
from .state import ResearchComplete
import structlog
from app.config import get_settings

logger = structlog.get_logger()


# Providers that expose OpenAI-compatible chat/completions APIs.
OPENAI_COMPATIBLE_PROVIDERS = {
    "openai",
    "doubao",
    "kimi",
    "glm",
}


def _normalize_provider_name(provider: str) -> str:
    """Normalize provider aliases into canonical provider names."""
    provider_normalized = provider.strip().lower()
    provider_aliases = {
        "moonshot": "kimi",
        "zhipu": "glm",
    }
    return provider_aliases.get(provider_normalized, provider_normalized)


def _split_model_ref(model_name: str) -> tuple[str, str]:
    """Split model ref into provider and model id.

    Supports both provider:model and provider/model forms.
    Falls back to openai-compatible default when provider is missing.
    """
    if ":" in model_name:
        provider, model_id = model_name.split(":", 1)
        provider = _normalize_provider_name(provider)
        return provider, model_id.strip()

    if "/" in model_name:
        provider, model_id = model_name.split("/", 1)
        provider = _normalize_provider_name(provider)
        return provider, model_id.strip()

    # Keep backward-compatible behavior for bare model names.
    return "openai", model_name.strip()


def _sanitize_openai_compatible_model_id(model_id: str) -> str:
    """Remove accidental provider prefixes from OpenAI-compatible model ids."""
    cleaned = model_id.strip()
    # Defensive: handle values like "doubao:glm-4-xxx" that some providers reject.
    while ":" in cleaned:
        maybe_provider, rest = cleaned.split(":", 1)
        if _normalize_provider_name(maybe_provider) in OPENAI_COMPATIBLE_PROVIDERS:
            cleaned = rest.strip()
            continue
        break
    return cleaned


def _lookup_provider_api_key(
    provider: str, api_keys: dict[str, Any], settings: Any
) -> str | None:
    """Resolve provider API key from runtime config or environment settings."""
    provider_key_map = {
        "openai": ("OPENAI_API_KEY", "openai_api_key"),
        "anthropic": ("ANTHROPIC_API_KEY", "anthropic_api_key"),
        "google": ("GOOGLE_API_KEY", "google_api_key"),
        "google_genai": ("GOOGLE_API_KEY", "google_api_key"),
        "doubao": ("DOUBAO_API_KEY", "doubao_api_key"),
        "kimi": ("KIMI_API_KEY", "kimi_api_key"),
        "glm": ("GLM_API_KEY", "glm_api_key"),
    }

    env_key, settings_key = provider_key_map.get(provider, (None, None))
    if not env_key:
        return None

    if api_keys:
        value = api_keys.get(env_key)
        if isinstance(value, str) and value.strip():
            return value.strip()

    env_value = os.getenv(env_key)
    if env_value:
        return env_value

    settings_value = getattr(settings, settings_key, None)
    if isinstance(settings_value, str) and settings_value.strip():
        return settings_value.strip()

    return None


def _lookup_provider_base_url(provider: str, settings: Any) -> str | None:
    """Resolve provider base URL for OpenAI-compatible providers."""
    if provider == "openai":
        # For OpenAI, keep SDK default unless explicitly overridden.
        custom = os.getenv("OPENAI_API_BASE_URL")
        if custom:
            return custom.strip()
        settings_value = getattr(settings, "openai_api_base_url", None)
        if isinstance(settings_value, str) and settings_value.strip():
            return settings_value.strip()
        return None

    provider_base_map = {
        "doubao": ("DOUBAO_API_BASE_URL", "doubao_api_base_url"),
        "kimi": ("KIMI_API_BASE_URL", "kimi_api_base_url"),
        "glm": ("GLM_API_BASE_URL", "glm_api_base_url"),
    }
    env_key, settings_key = provider_base_map.get(provider, (None, None))
    if not env_key:
        return None

    env_value = os.getenv(env_key)
    if env_value:
        return env_value.strip()

    settings_value = getattr(settings, settings_key, None)
    if isinstance(settings_value, str) and settings_value.strip():
        return settings_value.strip()

    return None


def build_model_runtime_config(
    *,
    model_name: str,
    max_tokens: int,
    config: RunnableConfig,
    extra: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Build normalized model runtime config for init_chat_model.with_config.

    This keeps model/provider routing isolated inside open_deep_research.
    """
    provider, model_id = _split_model_ref(model_name)
    settings = get_settings()
    should_get_from_config = os.getenv("GET_API_KEYS_FROM_CONFIG", "false").lower() == "true"
    api_keys = config.get("configurable", {}).get("apiKeys", {}) if (config and should_get_from_config) else {}

    runtime_model = model_name
    if provider in OPENAI_COMPATIBLE_PROVIDERS:
        model_id = _sanitize_openai_compatible_model_id(model_id)
        # Route all OpenAI-compatible providers through OpenAI backend.
        # IMPORTANT: send plain model_id to avoid leaking provider prefix
        # (e.g., "doubao:glm-*" should not be sent verbatim to provider API).
        runtime_model = model_id

    runtime: dict[str, Any] = {
        "model": runtime_model,
        "max_tokens": max_tokens,
    }
    if provider in OPENAI_COMPATIBLE_PROVIDERS:
        runtime["model_provider"] = "openai"

    api_key = _lookup_provider_api_key(provider, api_keys, settings)
    if api_key:
        runtime["api_key"] = api_key

    if provider in OPENAI_COMPATIBLE_PROVIDERS:
        base_url = _lookup_provider_base_url(provider, settings)
        if base_url:
            runtime["base_url"] = base_url

    if extra:
        runtime.update(extra)

    return runtime


def _is_google_genai_model(model: BaseChatModel) -> bool:
    """Check if model is a ChatGoogleGenerativeAI instance (direct or proxied)."""
    try:
        from langchain_google_genai import ChatGoogleGenerativeAI
        return isinstance(model, ChatGoogleGenerativeAI)
    except ImportError:
        return False


def get_gateway_chat_model(*, model_name: str, max_tokens: int | None = None) -> BaseChatModel:
    """Create a chat model via llm_gateway and apply optional runtime max_tokens."""
    model = get_model(model_name)
    if max_tokens is None:
        return model
    provider, _ = _split_model_ref(model_name)
    is_google = (
        provider in {"google", "google_genai", "gemini"}
        or _is_google_genai_model(model)
    )
    try:
        if is_google:
            # google-genai SDK's GenerateContentConfig rejects "max_tokens"
            # (extra='forbid'); ChatGoogleGenerativeAI._prepare_request only
            # consumes "max_output_tokens" from bind kwargs.
            return model.bind(max_output_tokens=max_tokens)
        return model.bind(max_tokens=max_tokens)
    except Exception:
        return model


def _ensure_token_usage_store(config: RunnableConfig | None) -> list[dict[str, Any]]:
    """Get or initialize shared token usage store inside runnable config."""
    if not isinstance(config, dict):
        return []
    configurable = config.setdefault("configurable", {})
    if not isinstance(configurable, dict):
        return []
    store = configurable.get("token_usage_events")
    if not isinstance(store, list):
        store = []
        configurable["token_usage_events"] = store
    return store


def _to_int(value: Any) -> int | None:
    """Convert value to int if possible."""
    try:
        if value is None:
            return None
        return int(value)
    except (TypeError, ValueError):
        return None


def _normalize_usage_fields(raw: dict[str, Any]) -> tuple[int | None, int | None, int | None]:
    """Normalize provider-specific usage fields to prompt/completion/total."""
    prompt = (
        _to_int(raw.get("prompt_tokens"))
        or _to_int(raw.get("input_tokens"))
        or _to_int(raw.get("promptTokenCount"))
        or _to_int(raw.get("inputTokenCount"))
    )
    completion = (
        _to_int(raw.get("completion_tokens"))
        or _to_int(raw.get("output_tokens"))
        or _to_int(raw.get("candidatesTokenCount"))
        or _to_int(raw.get("outputTokenCount"))
    )
    total = (
        _to_int(raw.get("total_tokens"))
        or _to_int(raw.get("totalTokenCount"))
    )
    if total is None and (prompt is not None or completion is not None):
        total = (prompt or 0) + (completion or 0)
    return prompt, completion, total


def _extract_usage_from_response(response: Any) -> tuple[dict[str, Any] | None, int | None, int | None, int | None]:
    """Extract token usage dict and normalized token counts from model response."""
    usage_raw: dict[str, Any] | None = None

    usage_metadata = getattr(response, "usage_metadata", None)
    if isinstance(usage_metadata, dict) and usage_metadata:
        usage_raw = usage_metadata

    response_metadata = getattr(response, "response_metadata", None)
    if isinstance(response_metadata, dict):
        for key in ("token_usage", "usage", "usage_metadata", "usageMetadata"):
            candidate = response_metadata.get(key)
            if isinstance(candidate, dict) and candidate:
                usage_raw = candidate
                break

    if usage_raw is None:
        return None, None, None, None

    prompt, completion, total = _normalize_usage_fields(usage_raw)
    return usage_raw, prompt, completion, total


async def ainvoke_with_usage(
    *,
    model: BaseChatModel,
    messages: list[MessageLikeRepresentation],
    config: RunnableConfig | None,
    step: str,
    action: str,
    model_name: str,
) -> Any:
    """Invoke model once and record exact usage returned by provider.

    ``config`` must be forwarded to ``ainvoke`` so merged graph callbacks
    (e.g. ``LlmUsagePerInvokeCallbackHandler`` for ``llm_usage_events``) run
    for Deep Research internal LLM calls, not only the main agent path.
    """
    started_at = time.perf_counter()
    response = await model.ainvoke(messages, config=config)
    elapsed_ms = int((time.perf_counter() - started_at) * 1000)
    store = _ensure_token_usage_store(config)

    provider, _ = _split_model_ref(model_name)
    usage_raw, prompt_tokens, completion_tokens, total_tokens = _extract_usage_from_response(response)

    store.append(
        {
            "step": step,
            "action": action,
            "provider": provider,
            "model": model_name,
            "prompt_tokens": prompt_tokens,
            "completion_tokens": completion_tokens,
            "total_tokens": total_tokens,
            "elapsed_ms": elapsed_ms,
            "usage_missing": usage_raw is None,
            "usage_raw": usage_raw,
        }
    )
    return response


def render_token_usage_summary(config: RunnableConfig | None) -> str:
    """Render token usage summary as markdown for final report."""
    store = _ensure_token_usage_store(config)
    if not store:
        return "\n\n## Token Usage\n\nNo token usage data was returned by the model provider."

    lines = [
        "",
        "",
        "## Token Usage",
        "",
        "| Step | Action | Prompt | Completion | Total |",
        "| --- | --- | ---: | ---: | ---: |",
    ]

    total_prompt = 0
    total_completion = 0
    total_all = 0
    has_prompt = False
    has_completion = False
    has_total = False

    for item in store:
        prompt = item.get("prompt_tokens")
        completion = item.get("completion_tokens")
        total = item.get("total_tokens")

        if isinstance(prompt, int):
            total_prompt += prompt
            has_prompt = True
        if isinstance(completion, int):
            total_completion += completion
            has_completion = True
        if isinstance(total, int):
            total_all += total
            has_total = True

        lines.append(
            f"| {item.get('step', '-')}"
            f" | {str(item.get('action', '-')).replace('|', '/')} "
            f"| {prompt if isinstance(prompt, int) else 'N/A'}"
            f" | {completion if isinstance(completion, int) else 'N/A'}"
            f" | {total if isinstance(total, int) else 'N/A'} |"
        )

    lines.extend(
        [
            "",
            f"- Total prompt tokens: {total_prompt if has_prompt else 'N/A'}",
            f"- Total completion tokens: {total_completion if has_completion else 'N/A'}",
            f"- Total tokens: {total_all if has_total else 'N/A'}",
        ]
    )
    return "\n".join(lines)


def _structured_output_method_for_model(model_name: str) -> str | None:
    """Select structured output method based on provider compatibility."""
    provider, _ = _split_model_ref(str(model_name))

    # OpenAI-compatible providers often do not support json_schema response_format.
    # Force function_calling to avoid provider-specific 400 errors.
    if provider in OPENAI_COMPATIBLE_PROVIDERS:
        return "function_calling"

    # Anthropic also works reliably with function calling style tool schemas.
    if provider == "anthropic":
        return "function_calling"

    # For other providers, keep framework default behavior.
    return None


def with_provider_aware_structured_output(
    *,
    model: BaseChatModel,
    schema: Any,
    model_name: str,
) -> BaseChatModel:
    """Bind structured output with provider-aware fallback behavior."""
    preferred_method = _structured_output_method_for_model(model_name)

    if preferred_method:
        try:
            return model.with_structured_output(schema, method=preferred_method)
        except TypeError:
            # Older LangChain versions may not expose "method" kwarg.
            return model.with_structured_output(schema)

    return model.with_structured_output(schema)

WEB_SEARCH_DEEP_RESEARCH_DESCRIPTION = (
    "Deep research web search using the shared research_tools provider. "
    "Uses Crawl4AI as primary and HTTP+BeautifulSoup fallback."
)


def _has_nonempty_results(payload: dict[str, Any]) -> bool:
    """Check whether a provider payload contains non-empty search results."""
    results = payload.get("results")
    return isinstance(results, list) and len(results) > 0


async def web_search_deep_research_impl(
    *,
    queries: List[str],
    max_results: int = 5,
    search_depth: str = "basic",
    include_domains: list[str] | None = None,
    exclude_domains: list[str] | None = None,
    config: RunnableConfig = None,
) -> str:
    """Search the web via the shared research_tools WebSearchProvider."""
    include_domains = include_domains or []
    exclude_domains = exclude_domains or []
    safe_queries = [str(q).strip() for q in queries if str(q).strip()]
    if not safe_queries:
        return json.dumps(
            {
                "success": False,
                "provider": "none",
                "query": "",
                "results": [],
                "error": "No valid search query provided.",
            },
            ensure_ascii=False,
            indent=2,
        )

    provider = WebSearchProvider()
    merged_results: list[dict[str, Any]] = []
    seen_urls: set[str] = set()
    providers_used: set[str] = set()
    errors: list[str] = []

    for query in safe_queries:
        try:
            search_result = await provider.search(
                query=query,
                max_results=max_results,
                search_depth=search_depth,
                include_domains=include_domains,
                exclude_domains=exclude_domains,
            )
        except Exception as exc:
            logger.warning("research_web_search_failed", query=query, error=str(exc))
            errors.append(f"{query}: {str(exc)}")
            continue

        providers_used.add(str(search_result.get("provider", "research_tools")))
        if not _has_nonempty_results(search_result):
            error = str(search_result.get("error", "")).strip()
            if error:
                errors.append(f"{query}: {error}")
            continue

        for item in search_result.get("results", []):
            if not isinstance(item, dict):
                continue
            normalized = dict(item)
            normalized.setdefault("query", query)
            url = str(normalized.get("url", "")).strip()
            if url:
                if url in seen_urls:
                    continue
                seen_urls.add(url)
            merged_results.append(normalized)

    if merged_results:
        return json.dumps(
            {
                "success": True,
                "provider": ", ".join(sorted(providers_used)) or "research_tools",
                "query": safe_queries[0],
                "queries": safe_queries,
                "results": merged_results,
                "answer": "",
                "error": "",
                "note": "Using app.tools.research_tools.WebSearchProvider",
            },
            ensure_ascii=False,
            indent=2,
        )

    return json.dumps(
        {
            "success": False,
            "provider": ", ".join(sorted(providers_used)) or "research_tools",
            "query": safe_queries[0],
            "queries": safe_queries,
            "results": [],
            "answer": "",
            "error": "; ".join(errors) if errors else "No valid search results found.",
            "note": "Using app.tools.research_tools.WebSearchProvider",
        },
        ensure_ascii=False,
        indent=2,
    )


@tool(description=WEB_SEARCH_DEEP_RESEARCH_DESCRIPTION)
async def web_search_deep_research(
    queries: List[str],
    max_results: Annotated[int, InjectedToolArg] = 5,
    search_depth: Annotated[Literal["basic", "advanced"], InjectedToolArg] = "basic",
    include_domains: Annotated[List[str] | None, InjectedToolArg] = None,
    exclude_domains: Annotated[List[str] | None, InjectedToolArg] = None,
    config: RunnableConfig = None,
) -> str:
    """Run deep research web search with multi-provider fallback chain."""
    return await web_search_deep_research_impl(
        queries=queries,
        max_results=max_results,
        search_depth=search_depth,
        include_domains=include_domains,
        exclude_domains=exclude_domains,
        config=config,
    )

##########################
# Reflection Tool Utils
##########################

@tool(description="Strategic reflection tool for research planning")
def think_tool(reflection: str) -> str:
    """Tool for strategic reflection on research progress and decision-making.

    Use this tool after each search to analyze results and plan next steps systematically.
    This creates a deliberate pause in the research workflow for quality decision-making.

    When to use:
    - After receiving search results: What key information did I find?
    - Before deciding next steps: Do I have enough to answer comprehensively?
    - When assessing research gaps: What specific information am I still missing?
    - Before concluding research: Can I provide a complete answer now?

    Reflection should address:
    1. Analysis of current findings - What concrete information have I gathered?
    2. Gap assessment - What crucial information is still missing?
    3. Quality evaluation - Do I have sufficient evidence/examples for a good answer?
    4. Strategic decision - Should I continue searching or provide my answer?

    Args:
        reflection: Your detailed reflection on research progress, findings, gaps, and next steps

    Returns:
        Confirmation that reflection was recorded for decision-making
    """
    return f"Reflection recorded: {reflection}"

##########################
# Tool Utils
##########################

async def get_search_tool(search_api: SearchAPI):
    """Configure and return search tools based on the specified API provider.
    
    Args:
        search_api: The search API provider to use (Anthropic, OpenAI, shared tools, or None)
        
    Returns:
        List of configured search tool objects for the specified provider
    """
    if search_api == SearchAPI.ANTHROPIC:
        # Anthropic's native web search with usage limits
        return [{
            "type": "web_search_20250305", 
            "name": "web_search", 
            "max_uses": 5
        }]
        
    elif search_api == SearchAPI.OPENAI:
        # OpenAI's web search preview functionality
        return [{"type": "web_search_preview"}]
        
    elif search_api == SearchAPI.RESEARCH_TOOLS:
        # Use shared research_tools search chain.
        search_tool = web_search_deep_research
        search_tool.metadata = {
            **(search_tool.metadata or {}), 
            "type": "search", 
            "name": "web_search"
        }
        return [search_tool]
        
    elif search_api == SearchAPI.NONE:
        # No search functionality configured
        return []
        
    # Default fallback for unknown search API types
    return []
    
async def get_all_tools(config: RunnableConfig):
    """Assemble complete toolkit for research operations.
    
    Args:
        config: Runtime configuration specifying search API
        
    Returns:
        List of all configured and available tools for research operations
    """
    # Start with core research tools
    tools = [tool(ResearchComplete), think_tool]
    
    # Add configured search tools
    configurable = Configuration.from_runnable_config(config)
    search_api = SearchAPI(get_config_value(configurable.search_api))
    search_tools = await get_search_tool(search_api)
    tools.extend(search_tools)

    return tools

def get_notes_from_tool_calls(messages: list[MessageLikeRepresentation]):
    """Extract notes from tool call messages."""
    return [tool_msg.content for tool_msg in filter_messages(messages, include_types="tool")]

##########################
# Model Provider Native Websearch Utils
##########################

def anthropic_websearch_called(response):
    """Detect if Anthropic's native web search was used in the response.
    
    Args:
        response: The response object from Anthropic's API
        
    Returns:
        True if web search was called, False otherwise
    """
    try:
        # Navigate through the response metadata structure
        usage = response.response_metadata.get("usage")
        if not usage:
            return False
        
        # Check for server-side tool usage information
        server_tool_use = usage.get("server_tool_use")
        if not server_tool_use:
            return False
        
        # Look for web search request count
        web_search_requests = server_tool_use.get("web_search_requests")
        if web_search_requests is None:
            return False
        
        # Return True if any web search requests were made
        return web_search_requests > 0
        
    except (AttributeError, TypeError):
        # Handle cases where response structure is unexpected
        return False

def openai_websearch_called(response):
    """Detect if OpenAI's web search functionality was used in the response.
    
    Args:
        response: The response object from OpenAI's API
        
    Returns:
        True if web search was called, False otherwise
    """
    # Check for tool outputs in the response metadata
    tool_outputs = response.additional_kwargs.get("tool_outputs")
    if not tool_outputs:
        return False
    
    # Look for web search calls in the tool outputs
    for tool_output in tool_outputs:
        if tool_output.get("type") == "web_search_call":
            return True
    
    return False


##########################
# Token Limit Exceeded Utils
##########################

def is_token_limit_exceeded(exception: Exception, model_name: str = None) -> bool:
    """Determine if an exception indicates a token/context limit was exceeded.
    
    Args:
        exception: The exception to analyze
        model_name: Optional model name to optimize provider detection
        
    Returns:
        True if the exception indicates a token limit was exceeded, False otherwise
    """
    error_str = str(exception).lower()
    
    # Step 1: Determine provider from model name if available
    provider = None
    if model_name:
        model_str = str(model_name).lower()
        if model_str.startswith('openai:') or model_str.startswith('doubao:') or model_str.startswith('kimi:') or model_str.startswith('glm:'):
            provider = 'openai'
        elif model_str.startswith('anthropic:'):
            provider = 'anthropic'
        elif model_str.startswith('gemini:') or model_str.startswith('google:'):
            provider = 'gemini'
    
    # Step 2: Check provider-specific token limit patterns
    if provider == 'openai':
        return _check_openai_token_limit(exception, error_str)
    elif provider == 'anthropic':
        return _check_anthropic_token_limit(exception, error_str)
    elif provider == 'gemini':
        return _check_gemini_token_limit(exception, error_str)
    
    # Step 3: If provider unknown, check all providers
    return (
        _check_openai_token_limit(exception, error_str) or
        _check_anthropic_token_limit(exception, error_str) or
        _check_gemini_token_limit(exception, error_str)
    )

def _check_openai_token_limit(exception: Exception, error_str: str) -> bool:
    """Check if exception indicates OpenAI token limit exceeded."""
    # Analyze exception metadata
    exception_type = str(type(exception))
    class_name = exception.__class__.__name__
    module_name = getattr(exception.__class__, '__module__', '')
    
    # Check if this is an OpenAI exception
    is_openai_exception = (
        'openai' in exception_type.lower() or 
        'openai' in module_name.lower()
    )
    
    # Check for typical OpenAI token limit error types
    is_request_error = class_name in ['BadRequestError', 'InvalidRequestError']
    
    if is_openai_exception and is_request_error:
        # Look for token-related keywords in error message
        token_keywords = ['token', 'context', 'length', 'maximum context', 'reduce']
        if any(keyword in error_str for keyword in token_keywords):
            return True
    
    # Check for specific OpenAI error codes
    if hasattr(exception, 'code') and hasattr(exception, 'type'):
        error_code = getattr(exception, 'code', '')
        error_type = getattr(exception, 'type', '')
        
        if (error_code == 'context_length_exceeded' or
            error_type == 'invalid_request_error'):
            return True
    
    return False

def _check_anthropic_token_limit(exception: Exception, error_str: str) -> bool:
    """Check if exception indicates Anthropic token limit exceeded."""
    # Analyze exception metadata
    exception_type = str(type(exception))
    class_name = exception.__class__.__name__
    module_name = getattr(exception.__class__, '__module__', '')
    
    # Check if this is an Anthropic exception
    is_anthropic_exception = (
        'anthropic' in exception_type.lower() or 
        'anthropic' in module_name.lower()
    )
    
    # Check for Anthropic-specific error patterns
    is_bad_request = class_name == 'BadRequestError'
    
    if is_anthropic_exception and is_bad_request:
        # Anthropic uses specific error messages for token limits
        if 'prompt is too long' in error_str:
            return True
    
    return False

def _check_gemini_token_limit(exception: Exception, error_str: str) -> bool:
    """Check if exception indicates Google/Gemini token limit exceeded."""
    # Analyze exception metadata
    exception_type = str(type(exception))
    class_name = exception.__class__.__name__
    module_name = getattr(exception.__class__, '__module__', '')
    
    # Check if this is a Google/Gemini exception
    is_google_exception = (
        'google' in exception_type.lower() or 
        'google' in module_name.lower()
    )
    
    # Check for Google-specific resource exhaustion errors
    is_resource_exhausted = class_name in [
        'ResourceExhausted', 
        'GoogleGenerativeAIFetchError'
    ]
    
    if is_google_exception and is_resource_exhausted:
        return True
    
    # Check for specific Google API resource exhaustion patterns
    if 'google.api_core.exceptions.resourceexhausted' in exception_type.lower():
        return True
    
    return False

# NOTE: This may be out of date or not applicable to your models. Please update this as needed.
MODEL_TOKEN_LIMITS = {
    "openai:gpt-4.1-mini": 1047576,
    "openai:gpt-4.1-nano": 1047576,
    "openai:gpt-4.1": 1047576,
    "openai:gpt-4o-mini": 128000,
    "openai:gpt-4o": 128000,
    "openai:o4-mini": 200000,
    "openai:o3-mini": 200000,
    "openai:o3": 200000,
    "openai:o3-pro": 200000,
    "openai:o1": 200000,
    "openai:o1-pro": 200000,
    "anthropic:claude-opus-4": 200000,
    "anthropic:claude-sonnet-4": 200000,
    "anthropic:claude-3-7-sonnet": 200000,
    "anthropic:claude-3-5-sonnet": 200000,
    "anthropic:claude-3-5-haiku": 200000,
    "google:gemini-1.5-pro": 2097152,
    "google:gemini-1.5-flash": 1048576,
    "google:gemini-pro": 32768,
    "cohere:command-r-plus": 128000,
    "cohere:command-r": 128000,
    "cohere:command-light": 4096,
    "cohere:command": 4096,
    "mistral:mistral-large": 32768,
    "mistral:mistral-medium": 32768,
    "mistral:mistral-small": 32768,
    "mistral:mistral-7b-instruct": 32768,
    "ollama:codellama": 16384,
    "ollama:llama2:70b": 4096,
    "ollama:llama2:13b": 4096,
    "ollama:llama2": 4096,
    "ollama:mistral": 32768,
    "bedrock:us.amazon.nova-premier-v1:0": 1000000,
    "bedrock:us.amazon.nova-pro-v1:0": 300000,
    "bedrock:us.amazon.nova-lite-v1:0": 300000,
    "bedrock:us.amazon.nova-micro-v1:0": 128000,
    "bedrock:us.anthropic.claude-3-7-sonnet-20250219-v1:0": 200000,
    "bedrock:us.anthropic.claude-sonnet-4-20250514-v1:0": 200000,
    "bedrock:us.anthropic.claude-opus-4-20250514-v1:0": 200000,
    "anthropic.claude-opus-4-1-20250805-v1:0": 200000,
}

def get_model_token_limit(model_string):
    """Look up the token limit for a specific model.
    
    Args:
        model_string: The model identifier string to look up
        
    Returns:
        Token limit as integer if found, None if model not in lookup table
    """
    # Search through known model token limits
    for model_key, token_limit in MODEL_TOKEN_LIMITS.items():
        if model_key in model_string:
            return token_limit
    
    # Model not found in lookup table
    return None

def remove_up_to_last_ai_message(messages: list[MessageLikeRepresentation]) -> list[MessageLikeRepresentation]:
    """Truncate message history by removing up to the last AI message.
    
    This is useful for handling token limit exceeded errors by removing recent context.
    
    Args:
        messages: List of message objects to truncate
        
    Returns:
        Truncated message list up to (but not including) the last AI message
    """
    # Search backwards through messages to find the last AI message
    for i in range(len(messages) - 1, -1, -1):
        if isinstance(messages[i], AIMessage):
            # Return everything up to (but not including) the last AI message
            return messages[:i]
    
    # No AI messages found, return original list
    return messages

##########################
# Misc Utils
##########################

def get_today_str() -> str:
    """Get current date formatted for display in prompts and outputs.
    
    Returns:
        Human-readable date string in format like 'Mon Jan 15, 2024'
    """
    now = datetime.now()
    return f"{now:%a} {now:%b} {now.day}, {now:%Y}"

def get_config_value(value):
    """Extract value from configuration, handling enums and None values."""
    if value is None:
        return None
    if isinstance(value, str):
        return value
    elif isinstance(value, dict):
        return value
    else:
        return value.value

def get_api_key_for_model(model_name: str, config: RunnableConfig):
    """Get API key for a specific model from environment or config."""
    provider, _ = _split_model_ref(model_name.lower())
    settings = get_settings()
    should_get_from_config = os.getenv("GET_API_KEYS_FROM_CONFIG", "false").lower() == "true"
    api_keys = config.get("configurable", {}).get("apiKeys", {}) if (config and should_get_from_config) else {}
    return _lookup_provider_api_key(provider, api_keys, settings)

