"""Read flocks-style api_services config for SOC alert API tools."""

from __future__ import annotations

import json
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from app.config.settings import SERVICE_ROOT


@dataclass(frozen=True)
class ApiServiceConfig:
    """Resolved api_services entry from flocks.json."""

    service_id: str
    enabled: bool
    base_url: str
    timeout: int
    api_key: str
    secret: str
    verify: bool


def _resolve_ref(value: Any) -> str:
    if value is None:
        return ""
    if not isinstance(value, str):
        return str(value)
    text = value.strip()
    if text.startswith("{env:") and text.endswith("}"):
        env_name = text[len("{env:") : -1]
        return (os.getenv(env_name, "") or "").strip()
    return text


def _to_int(value: Any, default: int) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def _to_bool(value: Any, default: bool) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return bool(value)
    if isinstance(value, str):
        normalized = value.strip().lower()
        if normalized in {"1", "true", "yes", "y", "on"}:
            return True
        if normalized in {"0", "false", "no", "n", "off"}:
            return False
    return default


def flocks_json_path() -> Path:
    """Resolve API services config path (new location with legacy fallback)."""
    env_override = (os.getenv("SOC_ALERT_API_SERVICES_CONFIG_PATH", "") or "").strip()
    if env_override:
        return Path(env_override)
    primary = SERVICE_ROOT / "config" / "soc_alert_api_services.json"
    if primary.is_file():
        return primary
    # Backward compatibility for earlier implementation.
    return SERVICE_ROOT / ".flocks" / "flocks.json"


def load_api_service_config(service_id: str, *, path: Path | None = None) -> ApiServiceConfig:
    """Load one api_services entry and resolve env placeholders."""
    config_path = path or flocks_json_path()
    if not config_path.is_file():
        return ApiServiceConfig(
            service_id=service_id,
            enabled=False,
            base_url="",
            timeout=30,
            api_key="",
            secret="",
            verify=True,
        )
    try:
        data = json.loads(config_path.read_text(encoding="utf-8"))
    except Exception:
        return ApiServiceConfig(
            service_id=service_id,
            enabled=False,
            base_url="",
            timeout=30,
            api_key="",
            secret="",
            verify=True,
        )
    services = data.get("api_services", {})
    raw = services.get(service_id, {}) if isinstance(services, dict) else {}
    enabled = bool(raw.get("enabled", False))
    base_url = _resolve_ref(raw.get("base_url") or raw.get("baseUrl")).rstrip("/")
    timeout = _to_int(raw.get("timeout", 30), 30)
    verify = _to_bool(raw.get("verify", True), True)
    api_key = _resolve_ref(raw.get("apiKey") or raw.get("authentication", {}).get("key"))
    secret = _resolve_ref(raw.get("secret") or raw.get("authentication", {}).get("secret"))
    return ApiServiceConfig(
        service_id=service_id,
        enabled=enabled,
        base_url=base_url,
        timeout=timeout,
        api_key=api_key,
        secret=secret,
        verify=verify,
    )

