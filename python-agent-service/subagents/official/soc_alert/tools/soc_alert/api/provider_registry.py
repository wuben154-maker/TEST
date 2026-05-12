"""Provider registry loader for SOC API provider_info.yaml files."""

from __future__ import annotations

from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import Any

import yaml


class ProviderRegistryError(ValueError):
    """Raised when provider metadata cannot be loaded or validated."""


@dataclass(frozen=True)
class ProviderAuthSchema:
    """Auth schema extracted from provider_info.yaml."""

    auth_type: str
    inject_as: str
    header_name: str


@dataclass(frozen=True)
class ProviderInfo:
    """Normalized provider info for runtime usage."""

    provider_code: str
    name: str
    service_id: str
    auth: dict[str, Any]
    credential_fields: list[dict[str, Any]]
    defaults: dict[str, Any]
    raw: dict[str, Any]


def _api_root() -> Path:
    return Path(__file__).resolve().parent


def _list_provider_info_files() -> list[Path]:
    root = _api_root()
    return sorted(
        p for p in root.glob("**/provider_info.yaml") if p.is_file()
    )


def _normalize_provider(payload: dict[str, Any], path: Path) -> ProviderInfo:
    code = str(payload.get("provider_code", "")).strip()
    if not code:
        raise ProviderRegistryError(
            f"provider_info missing provider_code: {path}"
        )
    name = str(payload.get("name", code)).strip() or code
    service_id = str(payload.get("service_id", "")).strip()
    auth = payload.get("auth", {}) if isinstance(payload.get("auth"), dict) else {}
    credential_fields = payload.get("credential_fields", [])
    if not isinstance(credential_fields, list):
        credential_fields = []
    defaults = payload.get("defaults", {}) if isinstance(payload.get("defaults"), dict) else {}
    return ProviderInfo(
        provider_code=code,
        name=name,
        service_id=service_id,
        auth=auth,
        credential_fields=credential_fields,
        defaults=defaults,
        raw=payload,
    )


@lru_cache(maxsize=1)
def load_provider_registry() -> dict[str, ProviderInfo]:
    """Load all provider_info.yaml files keyed by provider_code."""
    registry: dict[str, ProviderInfo] = {}
    for path in _list_provider_info_files():
        raw = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
        if not isinstance(raw, dict):
            raise ProviderRegistryError(f"provider_info must be mapping: {path}")
        info = _normalize_provider(raw, path)
        if info.provider_code in registry:
            raise ProviderRegistryError(
                f"duplicate provider_code {info.provider_code!r}: {path}"
            )
        registry[info.provider_code] = info
    return registry


def reload_provider_registry() -> None:
    """Clear provider registry cache."""
    load_provider_registry.cache_clear()


def get_provider(provider_code: str) -> ProviderInfo:
    """Get one provider by provider_code."""
    code = str(provider_code or "").strip()
    if not code:
        raise ProviderRegistryError("provider_code is required")
    info = load_provider_registry().get(code)
    if info is None:
        raise ProviderRegistryError(f"unknown provider_code: {code}")
    return info


def build_hitl_fields(provider_code: str) -> list[dict[str, Any]]:
    """Build request_user_input fields from provider credential_fields."""
    info = get_provider(provider_code)
    out: list[dict[str, Any]] = []
    for f in info.credential_fields:
        if not isinstance(f, dict):
            continue
        key = str(f.get("key", "")).strip()
        if not key:
            continue
        out.append(
            {
                "name": key,
                "label": str(f.get("label", key)),
                "paramType": str(f.get("input_type", "text")),
                "required": bool(f.get("required", True)),
                "placeholder": f.get("placeholder"),
            }
        )
    out.append(
        {
            "name": "remember_auth",
            "label": "Remember authorization",
            "paramType": "boolean",
            "required": False,
            "placeholder": "true/false",
        }
    )
    return out


def resolve_auth_schema(provider_code: str) -> ProviderAuthSchema:
    """Resolve auth injection schema from provider metadata."""
    info = get_provider(provider_code)
    auth = info.auth or {}
    return ProviderAuthSchema(
        auth_type=str(auth.get("type", "custom")).strip() or "custom",
        inject_as=str(auth.get("inject_as", "header")).strip() or "header",
        header_name=str(auth.get("header_name", "Authorization")).strip() or "Authorization",
    )

