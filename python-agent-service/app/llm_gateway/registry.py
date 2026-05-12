"""ModelRegistry: load llm_gateway.yaml, filter providers by API key, expose list_models and get_model_config."""

import os
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import Any

import yaml

SERVICE_ROOT = Path(__file__).resolve().parents[2]
CONFIG_PATH = SERVICE_ROOT / "config" / "llm_gateway.yaml"
ENV_PATH = SERVICE_ROOT / ".env"


_ENV_CACHE: dict[str, str] | None = None

_API_KEYS = (
    "ANTHROPIC_API_KEY", "OPENAI_API_KEY", "GOOGLE_API_KEY",
    "KIMI_API_KEY", "MINIMAX_API_KEY", "GLM_API_KEY",
    "DOUBAO_API_KEY", "OPENCODE_ZEN_API_KEY", "OPENROUTER_API_KEY",
)


def _load_env_vars() -> dict[str, str]:
    """Load .env file directly (avoids load_dotenv/pydantic parsing issues)."""
    global _ENV_CACHE
    if _ENV_CACHE is not None:
        return _ENV_CACHE
    result: dict[str, str] = {}
    if not ENV_PATH.exists():
        _ENV_CACHE = result
        return result
    try:
        from dotenv import dotenv_values
        vals = dotenv_values(ENV_PATH)
        result = {k: v for k, v in (vals or {}).items() if v and str(v).strip()}
    except Exception:
        result = {}
    # Fallback: manual parse for API keys when dotenv returns few (handles encoding issues)
    if len([k for k in _API_KEYS if k in result]) < 2:
        try:
            with open(ENV_PATH, encoding="utf-8-sig") as f:
                for line in f:
                    line = line.strip()
                    if not line or line.startswith("#"):
                        continue
                    if "=" in line:
                        k, _, v = line.partition("=")
                        k = k.strip()
                        v = v.strip().strip('"').strip("'")
                        if k in _API_KEYS and v and "your-" not in v.lower():
                            result[k] = v
        except Exception:
            pass
    _ENV_CACHE = result
    return result


# Fallback when a model entry omits context_window (keeps UI indicator functional).
DEFAULT_CONTEXT_WINDOW = 200_000
DEFAULT_MAX_OUTPUT_TOKENS = 4096


@dataclass
class ModelInfo:
    """Model metadata for API response.

    ``context_window`` and ``max_output_tokens`` support the frontend realtime
    context-usage indicator — they are sourced from ``llm_gateway.yaml`` and
    fall back to conservative defaults when missing.
    """

    id: str
    name: str
    provider: str
    sdk_model: str
    context_window: int = DEFAULT_CONTEXT_WINDOW
    max_output_tokens: int = DEFAULT_MAX_OUTPUT_TOKENS


def _load_raw_config() -> dict[str, Any]:
    """Load YAML config from disk."""
    if not CONFIG_PATH.exists():
        return {"providers": {}, "default_model": "google/gemini-3-flash-preview"}
    with open(CONFIG_PATH, encoding="utf-8") as f:
        return yaml.safe_load(f) or {"providers": {}, "default_model": "google/gemini-3-flash-preview"}


def _get_api_key(env_key: str) -> str | None:
    """Get API key from .env file, then os.environ."""
    env_vars = _load_env_vars()
    val = env_vars.get(env_key) or os.environ.get(env_key)
    if val is None or not str(val).strip():
        return None
    return str(val).strip()


class ModelRegistry:
    """Registry of available LLM models, filtered by provider API key availability."""

    def __init__(self, config_path: Path | None = None):
        self._config_path = config_path or CONFIG_PATH
        self._raw: dict[str, Any] | None = None
        self._available_providers: dict[str, dict] | None = None

    def _ensure_loaded(self) -> None:
        if self._raw is None:
            if not self._config_path.exists():
                self._raw = {"providers": {}, "default_model": "google/gemini-3-flash-preview"}
            else:
                with open(self._config_path, encoding="utf-8") as f:
                    self._raw = yaml.safe_load(f) or {"providers": {}, "default_model": "google/gemini-3-flash-preview"}
            self._available_providers = {}
            providers = self._raw.get("providers") or {}
            for pid, pconfig in providers.items():
                if not isinstance(pconfig, dict):
                    continue
                env_key = pconfig.get("env_key")
                if not env_key:
                    continue
                if _get_api_key(env_key) is None:
                    continue
                self._available_providers[pid] = {
                    **pconfig,
                    "api_key": _get_api_key(env_key),
                }

    def list_models(self) -> list[ModelInfo]:
        """Return list of available models (only from providers with API key set)."""
        self._ensure_loaded()
        result: list[ModelInfo] = []
        for pid, pconfig in (self._available_providers or {}).items():
            models = pconfig.get("models") or []
            for m in models:
                if not isinstance(m, dict):
                    continue
                mid = m.get("id")
                name = m.get("name", mid or "")
                sdk_model = m.get("sdk_model", mid or "")
                if mid:
                    ctx_raw = m.get("context_window")
                    out_raw = m.get("max_output_tokens")
                    ctx = int(ctx_raw) if isinstance(ctx_raw, int) and ctx_raw > 0 else DEFAULT_CONTEXT_WINDOW
                    out = int(out_raw) if isinstance(out_raw, int) and out_raw > 0 else DEFAULT_MAX_OUTPUT_TOKENS
                    result.append(
                        ModelInfo(
                            id=mid,
                            name=name,
                            provider=pid,
                            sdk_model=sdk_model,
                            context_window=ctx,
                            max_output_tokens=out,
                        )
                    )
        return result

    def get_model_config(self, model_id: str | None) -> dict | None:
        """Get model config + provider config for given model_id. Returns None if not found or no key."""
        if not model_id or not str(model_id).strip():
            return None
        model_id = str(model_id).strip()
        self._ensure_loaded()
        parts = model_id.split("/", 1)
        if len(parts) != 2:
            return None
        provider_id, model_suffix = parts
        pconfig = (self._available_providers or {}).get(provider_id)
        if not pconfig:
            return None
        models = pconfig.get("models") or []
        for m in models:
            if not isinstance(m, dict):
                continue
            if m.get("id") == model_id:
                return {
                    "provider_id": provider_id,
                    "model_id": model_id,
                    "model": m,
                    "provider": pconfig,
                }
        return None

    def get_default_model(self) -> str:
        """Return default model id from config."""
        self._ensure_loaded()
        default = (self._raw or {}).get("default_model") or "google/gemini-3-flash-preview"
        return str(default)

    def clear_cache(self) -> None:
        """Clear in-memory cache (for testing)."""
        global _ENV_CACHE
        _ENV_CACHE = None
        self._raw = None
        self._available_providers = None


@lru_cache(maxsize=1)
def get_registry(config_path: str | None = None) -> ModelRegistry:
    """Get cached ModelRegistry instance."""
    return ModelRegistry(Path(config_path) if config_path else None)
