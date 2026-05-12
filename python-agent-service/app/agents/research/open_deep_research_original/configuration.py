"""Configuration management for the Open Deep Research system."""

import os
from enum import Enum
from typing import Any, Optional

from langchain_core.runnables import RunnableConfig
from pydantic import BaseModel, Field

from app.config import get_settings

from .research_output_language import normalize_research_response_language

# Parent deep agent puts the user's selected gateway model id here so deep-research
# subgraphs do not rely solely on ContextVar (which may not propagate in all tool paths).
LLM_GATEWAY_MODEL_ID_KEY = "llm_gateway_model_id"


def _effective_gateway_model_id(config: RunnableConfig | None) -> str | None:
    """Prefer graph ``configurable[llm_gateway_model_id]``, then request ContextVar.

    Validated against :class:`ModelRegistry` so invalid/stale ids never override
    a working ContextVar or default.
    """
    from app.llm_gateway.registry import get_registry
    from app.llm_gateway.request_context import get_request_llm_model_id

    reg = get_registry()
    configurable: dict[str, Any] = {}
    if isinstance(config, dict):
        cb = config.get("configurable")
        if isinstance(cb, dict):
            configurable = cb
    gid_raw = configurable.get(LLM_GATEWAY_MODEL_ID_KEY)
    if isinstance(gid_raw, str):
        gid = gid_raw.strip()
        if gid and reg.get_model_config(gid):
            return gid

    ctx = get_request_llm_model_id()
    if ctx and reg.get_model_config(ctx):
        return ctx
    return None


def _request_scoped_gateway_model_id() -> str | None:
    """If ``stream_analyze_request`` set request context, return that gateway id."""
    return _effective_gateway_model_id(None)


def _gateway_default_model(fallback: str) -> str:
    """Read model from active analyze request, then gateway/default settings.

    Intentionally ignores per-stage env vars such as RESEARCH_MODEL to keep
    open_deep_research on a unified llm gateway model selection path.
    """
    scoped = _request_scoped_gateway_model_id()
    if scoped:
        return scoped
    settings = get_settings()
    return (
        os.getenv("DEFAULT_MODEL")
        or settings.default_model
        or fallback
    )


def _normalize_model_ref(model: Any) -> Any:
    """Normalize model provider aliases for init_chat_model compatibility."""
    if not isinstance(model, str) or not model:
        return model

    # Accept provider/model form and normalize to provider:model
    if "/" in model and ":" not in model:
        provider, name = model.split("/", 1)
        provider = provider.strip()
        name = name.strip()
        if provider and name:
            model = f"{provider}:{name}"

    # Normalize provider aliases
    if ":" in model:
        provider, name = model.split(":", 1)
        provider = provider.strip().lower()
        name = name.strip()
        provider_aliases = {
            "google": "google_genai",
            "gemini": "google_genai",
            "google-genai": "google_genai",
            "google_genai": "google_genai",
            "moonshot": "kimi",
            "zhipu": "glm",
        }
        provider = provider_aliases.get(provider, provider)
        return f"{provider}:{name}"

    return model


class SearchAPI(Enum):
    """Enumeration of available search API providers."""
    
    ANTHROPIC = "anthropic"
    OPENAI = "openai"
    RESEARCH_TOOLS = "research_tools"
    NONE = "none"

class Configuration(BaseModel):
    """Main configuration class for the Deep Research agent."""
    
    # General Configuration
    max_structured_output_retries: int = Field(
        default=3,
        metadata={
            "x_oap_ui_config": {
                "type": "number",
                "default": 3,
                "min": 1,
                "max": 10,
                "description": "Maximum number of retries for structured output calls from models"
            }
        }
    )
    allow_clarification: bool = Field(
        default=True,
        metadata={
            "x_oap_ui_config": {
                "type": "boolean",
                "default": True,
                "description": "Whether to allow the researcher to ask the user clarifying questions before starting research"
            }
        }
    )
    max_concurrent_research_units: int = Field(
        default=5,
        metadata={
            "x_oap_ui_config": {
                "type": "slider",
                "default": 5,
                "min": 1,
                "max": 20,
                "step": 1,
                "description": "Maximum number of research units to run concurrently. This will allow the researcher to use multiple sub-agents to conduct research. Note: with more concurrency, you may run into rate limits."
            }
        }
    )
    # Research Configuration
    search_api: SearchAPI = Field(
        default=SearchAPI.RESEARCH_TOOLS,
        metadata={
            "x_oap_ui_config": {
                "type": "select",
                "default": SearchAPI.RESEARCH_TOOLS.value,
                "description": "Search API to use for research. NOTE: Make sure your Researcher Model supports the selected search API.",
                "options": [
                    {"label": "Shared Research Tools", "value": SearchAPI.RESEARCH_TOOLS.value},
                    {"label": "OpenAI Native Web Search", "value": SearchAPI.OPENAI.value},
                    {"label": "Anthropic Native Web Search", "value": SearchAPI.ANTHROPIC.value},
                    {"label": "None", "value": SearchAPI.NONE.value}
                ]
            }
        }
    )
    max_researcher_iterations: int = Field(
        default=6,
        metadata={
            "x_oap_ui_config": {
                "type": "slider",
                "default": 6,
                "min": 1,
                "max": 10,
                "step": 1,
                "description": "Maximum number of research iterations for the Research Supervisor. This is the number of times the Research Supervisor will reflect on the research and ask follow-up questions."
            }
        }
    )
    max_react_tool_calls: int = Field(
        default=10,
        metadata={
            "x_oap_ui_config": {
                "type": "slider",
                "default": 10,
                "min": 1,
                "max": 30,
                "step": 1,
                "description": "Maximum number of tool calling iterations to make in a single researcher step."
            }
        }
    )
    # Model Configuration
    summarization_model: str = Field(
        default_factory=lambda: _gateway_default_model("openai:gpt-4.1-mini"),
        metadata={
            "x_oap_ui_config": {
                "type": "text",
                "default": "${DEFAULT_MODEL}",
                "description": "Model for summarizing research results"
            }
        }
    )
    summarization_model_max_tokens: int = Field(
        default=8192,
        metadata={
            "x_oap_ui_config": {
                "type": "number",
                "default": 8192,
                "description": "Maximum output tokens for summarization model"
            }
        }
    )
    max_content_length: int = Field(
        default=50000,
        metadata={
            "x_oap_ui_config": {
                "type": "number",
                "default": 50000,
                "min": 1000,
                "max": 200000,
                "description": "Maximum character length for webpage content before summarization"
            }
        }
    )
    research_model: str = Field(
        default_factory=lambda: _gateway_default_model("openai:gpt-4.1"),
        metadata={
            "x_oap_ui_config": {
                "type": "text",
                "default": "${DEFAULT_MODEL}",
                "description": "Model for conducting research. NOTE: Make sure your Researcher Model supports the selected search API."
            }
        }
    )
    research_model_max_tokens: int = Field(
        default=10000,
        metadata={
            "x_oap_ui_config": {
                "type": "number",
                "default": 10000,
                "description": "Maximum output tokens for research model"
            }
        }
    )
    compression_model: str = Field(
        default_factory=lambda: _gateway_default_model("openai:gpt-4.1"),
        metadata={
            "x_oap_ui_config": {
                "type": "text",
                "default": "${DEFAULT_MODEL}",
                "description": "Model for compressing research findings from sub-agents. NOTE: Make sure your Compression Model supports the selected search API."
            }
        }
    )
    compression_model_max_tokens: int = Field(
        default=16384,
        metadata={
            "x_oap_ui_config": {
                "type": "number",
                "default": 8192,
                "description": "Maximum output tokens for compression model"
            }
        }
    )
    final_report_model: str = Field(
        default_factory=lambda: _gateway_default_model("openai:gpt-4.1"),
        metadata={
            "x_oap_ui_config": {
                "type": "text",
                "default": "${DEFAULT_MODEL}",
                "description": "Model for writing the final report from all research findings"
            }
        }
    )
    final_report_model_max_tokens: int = Field(
        default=65536,
        metadata={
            "x_oap_ui_config": {
                "type": "number",
                "default": 10000,
                "description": "Maximum output tokens for final report model"
            }
        }
    )
    research_response_language: str = Field(
        default="en",
        description=(
            "Normalized output locale (en|zh|zh-hant|ja|ko) for deep-research prompts; "
            "derived from configurable subagent_response_language or sse_ui_language."
        ),
    )

    @classmethod
    def from_runnable_config(
        cls, config: Optional[RunnableConfig] = None
    ) -> "Configuration":
        """Create a Configuration instance from a RunnableConfig."""
        configurable = config.get("configurable", {}) if config else {}
        field_names = list(cls.model_fields.keys())
        model_fields = {
            "research_model",
            "summarization_model",
            "compression_model",
            "final_report_model",
        }
        values: dict[str, Any] = {
            field_name: (
                configurable.get(field_name)
                if field_name in model_fields
                else os.environ.get(field_name.upper(), configurable.get(field_name))
            )
            for field_name in field_names
        }
        settings = get_settings()
        for model_field in model_fields:
            if not values.get(model_field):
                scoped = _effective_gateway_model_id(config)
                values[model_field] = (
                    scoped
                    if scoped
                    else (os.getenv("DEFAULT_MODEL") or settings.default_model)
                )
        for model_field in model_fields:
            if model_field in values:
                values[model_field] = _normalize_model_ref(values[model_field])
        _raw_lang = configurable.get("subagent_response_language") or configurable.get(
            "sse_ui_language"
        )
        if _raw_lang is None:
            _raw_lang = os.environ.get("RESEARCH_RESPONSE_LANGUAGE")
        values["research_response_language"] = normalize_research_response_language(
            str(_raw_lang) if _raw_lang is not None else None
        )
        return cls(**{k: v for k, v in values.items() if v is not None})

    class Config:
        """Pydantic configuration."""
        
        arbitrary_types_allowed = True