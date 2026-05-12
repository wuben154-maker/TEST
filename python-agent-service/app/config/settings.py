"""Configuration settings for the Deep Agent service.

All URLs and addresses are configured via environment variables.
See .env.example for available configuration options.
"""

from functools import lru_cache
from pathlib import Path
from typing import Literal

from pydantic import model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


SERVICE_ROOT = Path(__file__).resolve().parents[2]
SERVICE_ENV_FILE = SERVICE_ROOT / ".env"


class Settings(BaseSettings):
    """Application settings loaded from environment variables."""
    model_config = SettingsConfigDict(
        env_file=str(SERVICE_ENV_FILE),
        case_sensitive=False,
        extra="ignore",
    )

    # ============================================
    # MODE SWITCHES
    # ============================================
    # Agent mode is hard-pinned to "deepagent" regardless of env/config input.
    agent_mode: str = "deepagent"

    # Database mode: "supabase" (cloud), "local" (PostgreSQL), or "memory" (InMemoryStore for dev/test)
    database_mode: Literal["supabase", "local", "memory"] = "local"

    # ============================================
    # LOCAL DATABASE (used when database_mode=local)
    # ============================================
    local_db_host: str = "localhost"
    local_db_port: int = 5432
    local_db_name: str = "secmanus"
    local_db_user: str = "postgres"
    local_db_password: str = "postgres"
    # asyncpg pool (local mode). Increase max_size for concurrent /analyze + auth/API traffic.
    local_db_pool_min_size: int = 2
    local_db_pool_max_size: int = 30
    # Throttle project_analysis_progress writes during SSE (reduces pool contention).
    # Set min interval to 0 to flush on every stream event (legacy behavior, higher DB load).
    progress_upsert_min_interval_seconds: float = 0.2
    # Also force a progress write every N stream events (safety when events flood in bursts).
    progress_upsert_force_every_n_events: int = 20

    # ============================================
    # API KEYS
    # ============================================
    openai_api_key: str | None = None
    anthropic_api_key: str | None = None
    google_api_key: str | None = None
    kimi_api_key: str | None = None
    minimax_api_key: str | None = None
    glm_api_key: str | None = None
    doubao_api_key: str | None = None
    opencode_zen_api_key: str | None = None
    openrouter_api_key: str | None = None
    openrouter_app_url: str | None = None
    openrouter_app_title: str | None = None
    # OpenRouter unified reasoning API (Gemini thinking, o-series, etc.):
    # https://openrouter.ai/docs/guides/best-practices/reasoning-tokens
    openrouter_reasoning_enabled: bool = True
    openrouter_reasoning_effort: str = "medium"  # minimal|low|medium|high|xhigh
    virustotal_api_key: str | None = None
    lovable_api_key: str | None = None
    tavily_api_key: str | None = None
    # E2B cloud sandbox — when set, sandbox tools are mounted on the agent
    e2b_api_key: str | None = None
    # Override the default template from config/sandbox.yaml (optional)
    e2b_default_template: str | None = None
    # Serper.dev Google SERP API (https://serper.dev) — optional; used after Tavily, before Crawl4AI scraping
    serper_api_key: str | None = None
    serper_api_base_url: str = "https://google.serper.dev"
    # ============================================
    # EXTERNAL API URLS
    # ============================================
    # AI Provider base URLs (override for custom/proxy endpoints)
    openai_api_base_url: str | None = None
    gemini_api_base_url: str = "https://generativelanguage.googleapis.com/v1beta"
    doubao_api_base_url: str = "https://ark.cn-beijing.volces.com/api/v3"
    kimi_api_base_url: str = "https://api.moonshot.cn/v1"
    glm_api_base_url: str = "https://open.bigmodel.cn/api/paas/v4"
    lovable_ai_gateway_url: str = "https://ai.gateway.lovable.dev/v1"

    # Intent classifier LLM backend: "langchain" | "gateway" | "auto"
    intent_llm_backend: Literal["langchain", "gateway", "auto"] = "auto"
    intent_gateway_model: str = "google/gemini-3-flash-preview"

    # VirusTotal API URL
    virustotal_api_base_url: str = "https://www.virustotal.com/api/v3"
    virustotal_gui_base_url: str = "https://www.virustotal.com/gui"
    # SOC alert API tools (profile-only: soc-alert-api)
    soc_alert_api_timeout_seconds: int = 30
    soc_alert_edr_base_url: str | None = None
    soc_alert_edr_api_key: str | None = None
    soc_alert_tdp_base_url: str | None = None
    soc_alert_tdp_api_key: str | None = None
    soc_alert_tdp_secret: str | None = None

    # Firecrawl API URL (for web scraping, deprecated - use Crawl4AI)
    firecrawl_api_url: str | None = None
    firecrawl_api_key: str | None = None

    # Crawl4AI API (primary web scraping and search page crawling)
    crawl4ai_url: str = "http://localhost:11235"
    crawl4ai_api_token: str | None = None
    # Optional HTTP(S) proxy for SERP crawls via Crawl4AI (datacenter IPs often get a different SERP)
    crawl4ai_proxy_server: str | None = None
    # web_search backend: "google" (default) or "bing" (HTML scraping, not official APIs)
    # When TAVILY_API_KEY is set, Tavily is always tried first regardless of this setting.
    web_search_engine: str = "google"

    # ============================================
    # SUPABASE (used when database_mode=supabase)
    # ============================================
    supabase_url: str | None = None
    supabase_anon_key: str | None = None
    supabase_service_role_key: str | None = None
    # Direct PostgreSQL URI for LangGraph checkpointing (psycopg). Supabase Dashboard →
    # Settings → Database → Connection string (URI). Not the same as SUPABASE_URL (HTTPS API).
    supabase_db_url: str | None = None

    # ============================================
    # LANGSMITH
    # ============================================
    langsmith_api_key: str | None = None
    langsmith_project: str = "security-deep-agent"
    langsmith_tracing: bool = False

    # ============================================
    # LOGGING PERSISTENCE
    # ============================================
    log_sink: Literal["stdout", "file", "both"] = "stdout"
    log_file_path: str = "logs/secmanus.log"
    log_file_max_bytes: int = 10_485_760  # 10 MiB
    log_file_backup_count: int = 5

    # ============================================
    # TIMEZONE (fallback only)
    # ============================================
    # IANA zone when X-Client-Timezone header is absent or invalid (webhooks, CLI, curl).
    # Normal browser traffic sends X-Client-Timezone from Intl; this is not the primary source.
    app_timezone: str = "UTC"

    # ============================================
    # SERVER & UPLOADS
    # ============================================
    host: str = "0.0.0.0"
    port: int = 8000
    upload_dir: str = str(SERVICE_ROOT / "uploads")  # Directory for uploaded files (CompositeBackend, deep_agent)
    # ``{knowledge_storage_root or upload_dir}/knowledge/<user_id>/*.docx``
    knowledge_storage_root: str | None = None
    knowledge_max_bytes_per_file: int | None = None  # defaults to max_upload_bytes_per_file when None
    max_upload_files_per_batch: int = 10
    max_upload_bytes_per_file: int = 104_857_600  # 100 MiB
    main_agent_manifest_sniff_bytes_per_file: int = 4096
    main_agent_manifest_sniff_bytes_total: int = 16_384
    attachment_inline_max_total_bytes: int = 65_536  # legacy JSON inline attachments
    allow_legacy_flat_upload_paths: bool = True  # /uploads/<single>/file without u_/s_ prefix
    workers: int = 4
    reload: bool = True
    # When true, prefer the leftmost IP in X-Forwarded-For (use behind a trusted reverse proxy).
    trust_x_forwarded_for: bool = False
    # Login audit: call ip-api.com to store country/region for the client IP (public IPs only).
    login_ip_geo_lookup_enabled: bool = True
    login_ip_geo_timeout_seconds: float = 2.5

    # ============================================
    # SSE / UI — generic tool-result humanizer (JSON → plaintext)
    # ============================================
    # Caps long strings in ``humanize_tool_output`` (stdout/content blocks vs
    # inline scalars). Tune when UI payloads get too large.
    sse_tool_result_max_block_chars: int = 2000
    sse_tool_result_max_scalar_chars: int = 2000

    # ============================================
    # AGENT
    # ============================================
    default_model: str = "google/gemini-3-flash-preview"
    # Optional model overrides used by open_deep_research_original.
    research_model: str | None = None
    summarization_model: str | None = None
    compression_model: str | None = None
    final_report_model: str | None = None
    max_iterations: int = 20
    timeout_seconds: int = 300
    # Per-LLM-call HTTP read timeout (seconds). Caps idle time between streaming
    # chunks. Does NOT limit total request duration for long-running thinking.
    llm_request_timeout_seconds: int = 120
    # Total wall-clock cap for a single subagent invocation (seconds).
    # Prevents extended-thinking models from running indefinitely.
    # 0 = no limit (relies on outer session timeout_seconds only).
    subagent_timeout_seconds: int = 300
    # Enable Anthropic Extended Thinking (only for supported models: sonnet-4.x, opus-4.x, haiku-4.5)
    enable_anthropic_thinking: bool = True
    # Enable Gemini thinking/reasoning mode (thinking_budget for supported models)
    enable_gemini_thinking: bool = True

    # ============================================
    # CONTEXT MANAGEMENT (DeepAgents Layered Strategy)
    # ============================================
    # Short-term context (Working Memory)
    context_max_tokens: int = 4000  # Trigger summarization threshold
    context_keep_recent: int = 20  # Keep last N messages in full
    context_offload_threshold: int = 1000  # Chars for large output offload
    # Context budget SSE + summarization alignment (provider meter)
    context_budget_sse_enabled: bool = True
    context_compress_enable_provider_meter: bool = True
    context_budget_warn_ratio: float = 0.70
    context_budget_danger_ratio: float = 0.90
    context_budget_critical_ratio: float = 0.95
    context_compress_trigger_ratio: float = 0.85

    # Long-term context (Persistent Storage)
    memory_ttl_hours: int = 24  # TTL for short-term memories
    store_backend: str = "memory"  # "memory", "postgres", or "redis"

    # ============================================
    # CHECKPOINTING (LangGraph State Persistence)
    # ============================================
    enable_checkpointing: bool = True  # Enable state checkpointing
    checkpoint_backend: Literal["memory", "postgres"] = "postgres"  # Checkpoint storage backend
    checkpoint_table_name: str = "langgraph_checkpoints"  # PostgreSQL table name for checkpoints

    # ============================================
    # CONTEXT MEMORY (derived layer + user index)
    # ============================================
    context_memory_enabled: bool = False
    derived_layer_model: str | None = None  # Gateway model id; empty = rules-only merge
    context_inject_max_chars: int = 6000
    context_hydrate_enabled: bool = False
    context_hydrate_max_turns: int = 3  # user/assistant pairs
    context_merge_async: bool = False  # v1: ignored; merge runs inline after persist
    context_summary_input_max_chars: int = 8000  # cap text sent to summarizer LLM

    # Context routing prefixes (for CompositeBackend)
    temp_path_prefix: str = "/temp/"
    memories_path_prefix: str = "/memories/"
    reports_path_prefix: str = "/reports/"
    parameters_path_prefix: str = "/parameters/"
    artifact_storage_dir: str = str(SERVICE_ROOT / ".artifacts")
    # Comma-separated step ids to KEEP when filtering running steps; empty = emit all (no filter).
    step_running_whitelist: str = ""

    # Subagent registry (YAML + bundles under subagents/official/)
    subagents_registry_path: str | None = None
    # Main-agent global skill allowlist (default: config/main_agent_skills.yaml)
    main_agent_skills_config_path: str | None = None

    # Human-in-the-loop (LangGraph interrupt + HumanInTheLoopMiddleware)
    # HITL is always enabled in current runtime. Keep only tool list + pending guard controls.
    # Comma-separated tool names for main + general-purpose subagent interrupt_on (all True).
    agent_hitl_interrupt_tools: str = ""
    # Reject new /analyze turns while the graph has pending interrupts (409 / SSE error).
    agent_hitl_block_analyze_when_pending: bool = True

    # ============================================
    # BILLING / STRIPE (billing-token-stripe-usage)
    # ============================================
    billing_enforce: bool = False
    stripe_secret_key: str | None = None
    stripe_webhook_secret: str | None = None
    stripe_price_pro_monthly: str | None = None
    stripe_price_ultra_monthly: str | None = None
    billing_free_included_tokens: int = 500_000
    billing_default_monthly_spend_cap_usd: float = 100.0
    billing_default_arrears_usd: float = 5.0
    billing_max_monthly_spend_cap_usd: float = 100.0
    billing_checkout_success_url: str | None = None
    billing_checkout_cancel_url: str | None = None
    billing_portal_return_url: str | None = None

    @property
    def database_url(self) -> str | None:
        """PostgreSQL URI for LangGraph checkpointing (AsyncPostgresSaver / psycopg).

        ``SUPABASE_URL`` is only the REST API base (``https://…``); it must never be used
        as ``conninfo``. In ``supabase`` mode, set ``SUPABASE_DB_URL`` to the pooler URI
        from the Supabase dashboard, or leave it unset to skip Postgres checkpointing.
        """
        if self.database_mode == "local":
            return (
                f"postgresql://{self.local_db_user}:{self.local_db_password}"
                f"@{self.local_db_host}:{self.local_db_port}/{self.local_db_name}"
            )
        if self.database_mode == "memory":
            return None
        if self.database_mode == "supabase":
            raw = (self.supabase_db_url or "").strip()
            if raw.startswith(("postgresql://", "postgres://")):
                return raw
            return None
        return None

    @property
    def is_deepagent_mode(self) -> bool:
        """Check if running in DeepAgent mode."""
        return True

    @model_validator(mode="after")
    def _force_deepagent_mode(self):
        """Force runtime mode to deepagent even if env tries to override it."""
        self.agent_mode = "deepagent"
        return self

    @model_validator(mode="after")
    def _validate_local_db_pool_bounds(self):
        if self.local_db_pool_max_size < self.local_db_pool_min_size:
            raise ValueError(
                "local_db_pool_max_size must be >= local_db_pool_min_size"
            )
        return self

    @property
    def is_local_database(self) -> bool:
        """Check if using local database."""
        return self.database_mode == "local"

    @property
    def firecrawl_url(self) -> str:
        """Get Firecrawl API URL with fallback logic."""
        if self.firecrawl_api_url:
            return self.firecrawl_api_url
        # Check if using local key
        if self.firecrawl_api_key and self.firecrawl_api_key.startswith("fc-local"):
            return "http://firecrawl:3002/v1"
        return "https://api.firecrawl.dev/v1"

    @property
    def main_agent_interrupt_on(self) -> dict[str, bool] | None:
        """Tool-name map for create_deep_agent(interrupt_on=...)."""
        raw = (self.agent_hitl_interrupt_tools or "").strip()
        if not raw:
            return None
        out: dict[str, bool] = {}
        for part in raw.split(","):
            name = part.strip()
            if name:
                out[name] = True
        return out or None

@lru_cache()
def get_settings() -> Settings:
    """Get cached settings instance."""
    return Settings()


def clear_settings_cache():
    """Clear the settings cache (useful for testing)."""
    get_settings.cache_clear()
    try:
        from app.datetime_support import clear_app_tz_cache

        clear_app_tz_cache()
    except ImportError:
        pass
