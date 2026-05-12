"""Resolver and executor for generic SOC actions."""

from __future__ import annotations

import inspect
from difflib import SequenceMatcher
from contextlib import nullcontext
from typing import Any

import structlog
from app.request_context.user_id import get_request_user_id
from subagents.official.soc_alert.tools.soc_alert.auth.service import get_vendor_auth_service
from subagents.official.soc_alert.tools.soc_alert.api.provider_registry import (
    ProviderRegistryError,
    get_provider,
)
from subagents.official.soc_alert.tools.soc_alert.api.splunk.api_splunk_tools import (
    splunk_runtime_override,
)

from .types import ResolvedActionCall
from .mappings import VENDOR_ACTION_MAP, VENDOR_ALIASES
from .scope_utils import derive_auth_scope, first_nonempty_str

SUPPORTED_SOC_ACTION_VENDORS = tuple(sorted(VENDOR_ACTION_MAP.keys()))
logger = structlog.get_logger()

# Phase-1 toolset category policy:
# - SIEM class: node3 must provide vendor (splunk / ...).
# - WEB class: vendor is optional, runtime uses default vendor.
_CATEGORY_POLICY: dict[str, dict[str, Any]] = {
    "siem": {"requires_vendor": True, "default_vendor": None},
    "web": {"requires_vendor": False, "default_vendor": "virustotal"},
}
_VENDOR_CATEGORY: dict[str, str] = {
    "splunk": "siem",
    "elastic_security": "siem",
    "virustotal": "web",
}

GLOBAL_PARAM_ALIASES: dict[str, str] = {
    "hostname": "host",
    "host_name": "host",
    "computer_name": "host",
    "username": "user",
    "user_name": "user",
    "file_name": "file_path",
    "filepath": "file_path",
    "ip": "dest_ip",
    "destination": "dest_ip",
    "destination_ip": "dest_ip",
    "start_time": "earliest",
    "end_time": "latest",
    "time_from": "earliest",
    "time_to": "latest",
}

ACTION_PARAM_ALIASES: dict[str, dict[str, str]] = {
    "query_user_process_activity": {
        "username": "user",
    },
    "query_network_connections": {
        "process": "process_name",
    },
    "query_file_events": {
        "filename": "file_path",
    },
    "query_process_tree": {
        "process": "process_name",
    },
}

VENDOR_ACTION_PARAM_ALIASES: dict[str, dict[str, dict[str, str]]] = {
    "splunk": {
        "query_alerts": {
            "start_time": "earliest_time",
            "end_time": "latest_time",
        }
    }
}

MISSING_PARAM_EXTRACTION_ALIASES: dict[str, tuple[str, ...]] = {
    "host": ("hostname", "host_name", "computer_name", "source_host"),
    "user": ("username", "user_name", "account", "principal", "actor"),
    "dest_ip": ("destination_ip", "dst_ip", "target_ip", "remote_ip", "ip"),
    "file_path": ("filepath", "file", "path", "target_path"),
    "process_name": ("process", "proc", "image", "process"),
    "indicator": ("ioc", "ip", "domain", "url", "hash", "sha256", "md5", "file_path"),
    "sid": ("search_id", "job_id", "case_id"),
    "search_name": ("rule_id", "saved_search", "saved_search_name"),
    "earliest": ("start_time", "time_from"),
    "latest": ("end_time", "time_to"),
    "earliest_time": ("start_time", "time_from", "earliest"),
    "latest_time": ("end_time", "time_to", "latest"),
}


class GenericActionResolveError(ValueError):
    """Raised when a generic action cannot be resolved."""


def _is_vendor_explicit(vendor_routing: dict[str, Any] | None, fallback_vendor: str) -> bool:
    if isinstance(vendor_routing, dict):
        for key in ("vendor", "vendor_name", "provider", "platform", "siem_vendor"):
            raw = vendor_routing.get(key)
            if isinstance(raw, str) and raw.strip():
                return True
    return bool(str(fallback_vendor or "").strip())


def _find_vendors_supporting_action(generic_action: str) -> list[str]:
    out: list[str] = []
    for vendor_name, mappings in VENDOR_ACTION_MAP.items():
        if generic_action in mappings:
            out.append(vendor_name)
    return out


def generic_action_requires_vendor(generic_action: str) -> bool:
    """Return whether this action requires explicit vendor in node3 output."""
    vendors = _find_vendors_supporting_action(generic_action)
    if not vendors:
        # Keep strict behavior for unknown actions.
        return True
    categories = {_VENDOR_CATEGORY.get(v, "siem") for v in vendors}
    # If action spans multiple categories, stay conservative.
    if len(categories) != 1:
        return True
    category = next(iter(categories))
    policy = _CATEGORY_POLICY.get(category, {})
    return bool(policy.get("requires_vendor", True))


def _resolve_vendor_for_action(
    *,
    fallback_vendor: str,
    generic_action: str,
    vendor_routing: dict[str, Any] | None,
) -> str:
    """Resolve vendor by action category policy (phase-1)."""
    normalized_vendor = _normalize_vendor(vendor_routing, fallback_vendor)
    candidate_vendors = _find_vendors_supporting_action(generic_action)
    if normalized_vendor and generic_action in VENDOR_ACTION_MAP.get(normalized_vendor, {}):
        return normalized_vendor
    if not candidate_vendors:
        if normalized_vendor:
            return normalized_vendor
        raise GenericActionResolveError(f"Unsupported generic_action: {generic_action!r}")

    categories = {_VENDOR_CATEGORY.get(v, "siem") for v in candidate_vendors}
    if normalized_vendor:
        if len(categories) == 1:
            category = next(iter(categories))
            policy = _CATEGORY_POLICY.get(category, {})
            if not policy.get("requires_vendor", True):
                default_vendor = str(policy.get("default_vendor") or "").strip()
                if default_vendor and generic_action in VENDOR_ACTION_MAP.get(default_vendor, {}):
                    logger.info(
                        "soc_action_vendor_ignored_use_default_for_category",
                        category=category,
                        generic_action=generic_action,
                        from_vendor=normalized_vendor,
                        to_vendor=default_vendor,
                    )
                    return default_vendor
        raise GenericActionResolveError(
            f"Unsupported generic_action {generic_action!r} for vendor {normalized_vendor!r}"
        )

    if len(categories) == 1:
        category = next(iter(categories))
        policy = _CATEGORY_POLICY.get(category, {})
        if not policy.get("requires_vendor", True):
            default_vendor = str(policy.get("default_vendor") or "").strip()
            if default_vendor and generic_action in VENDOR_ACTION_MAP.get(default_vendor, {}):
                logger.info(
                    "soc_action_default_vendor_applied",
                    category=category,
                    generic_action=generic_action,
                    default_vendor=default_vendor,
                )
                return default_vendor
            if len(candidate_vendors) == 1:
                return candidate_vendors[0]
        elif not _is_vendor_explicit(vendor_routing, fallback_vendor):
            raise GenericActionResolveError(
                f"generic_action {generic_action!r} requires explicit vendor_routing.provider"
            )

    if len(candidate_vendors) == 1:
        return candidate_vendors[0]
    raise GenericActionResolveError(
        f"Ambiguous vendor for generic_action {generic_action!r}; candidates={candidate_vendors}"
    )


def _normalize_vendor(vendor_routing: dict[str, Any] | None, fallback_vendor: str) -> str:
    candidate = ""
    if isinstance(vendor_routing, dict):
        for key in ("vendor", "vendor_name", "provider", "platform", "siem_vendor"):
            raw = vendor_routing.get(key)
            if isinstance(raw, str) and raw.strip():
                candidate = raw.strip()
                break
    if not candidate:
        candidate = str(fallback_vendor or "").strip()
    normalized = candidate.lower().replace("-", "_").replace(" ", "_")
    return VENDOR_ALIASES.get(normalized, normalized)


def _normalize_params(data: dict[str, Any] | None) -> dict[str, Any]:
    if not isinstance(data, dict):
        return {}
    return dict(data)


def _alias_for_param(
    *,
    vendor: str,
    generic_action: str,
    key: str,
) -> str:
    """Resolve canonical parameter key from layered alias maps."""
    vendor_aliases = (
        VENDOR_ACTION_PARAM_ALIASES.get(vendor, {}).get(generic_action, {})
    )
    if key in vendor_aliases:
        return vendor_aliases[key]
    action_aliases = ACTION_PARAM_ALIASES.get(generic_action, {})
    if key in action_aliases:
        return action_aliases[key]
    return GLOBAL_PARAM_ALIASES.get(key, key)


def _canonicalize_action_params(
    *,
    vendor: str,
    generic_action: str,
    params: dict[str, Any],
) -> dict[str, Any]:
    """Normalize unstable LLM field names into canonical action params."""
    if not params:
        return {}
    canonical: dict[str, Any] = {}
    alias_applied: dict[str, str] = {}
    conflicts: dict[str, str] = {}
    for raw_key, value in params.items():
        canonical_key = _alias_for_param(
            vendor=vendor,
            generic_action=generic_action,
            key=raw_key,
        )
        if canonical_key in canonical and raw_key != canonical_key:
            conflicts[raw_key] = canonical_key
            continue
        if raw_key != canonical_key:
            alias_applied[raw_key] = canonical_key
        canonical[canonical_key] = value
    if alias_applied:
        logger.info(
            "soc_action_param_alias_applied",
            vendor=vendor,
            generic_action=generic_action,
            alias_applied=alias_applied,
        )
    if conflicts:
        logger.warning(
            "soc_action_param_alias_conflict",
            vendor=vendor,
            generic_action=generic_action,
            conflicts=conflicts,
        )
    return canonical


def _prepare_handler_input(
    *,
    handler: Any,
    tool_input: dict[str, Any],
    vendor: str,
    generic_action: str,
    tool_name: str,
) -> dict[str, Any]:
    """Drop unknown kwargs for strict handler signatures to avoid hard failure."""
    signature = inspect.signature(handler)
    params = signature.parameters
    accepts_var_kwargs = any(
        p.kind == inspect.Parameter.VAR_KEYWORD
        for p in params.values()
    )
    if accepts_var_kwargs:
        return dict(tool_input)

    accepted_keys = {
        name
        for name, p in params.items()
        if p.kind in (inspect.Parameter.POSITIONAL_OR_KEYWORD, inspect.Parameter.KEYWORD_ONLY)
    }
    filtered = {k: v for k, v in tool_input.items() if k in accepted_keys}
    dropped = sorted(k for k in tool_input.keys() if k not in accepted_keys)
    if dropped:
        logger.warning(
            "soc_action_drop_unknown_params",
            vendor=vendor,
            generic_action=generic_action,
            tool_name=tool_name,
            dropped_params=dropped,
            accepted_params=sorted(accepted_keys),
        )
    required = [
        name
        for name, p in params.items()
        if p.kind in (inspect.Parameter.POSITIONAL_OR_KEYWORD, inspect.Parameter.KEYWORD_ONLY)
        and p.default is inspect.Parameter.empty
    ]
    missing_required = [
        key for key in required
        if key not in filtered or filtered.get(key) is None or (isinstance(filtered.get(key), str) and not filtered[key].strip())
    ]
    if missing_required:
        raise GenericActionResolveError(
            f"Missing required params after signature filtering: {missing_required}"
        )
    return filtered


def _flatten_strings(obj: Any) -> list[str]:
    out: list[str] = []
    if isinstance(obj, dict):
        for value in obj.values():
            out.extend(_flatten_strings(value))
    elif isinstance(obj, list):
        for item in obj:
            out.extend(_flatten_strings(item))
    elif isinstance(obj, str):
        text = obj.strip()
        if text:
            out.append(text)
    return out


def _normalize_key_name(key: str) -> str:
    return "".join(ch for ch in key.strip().lower() if ch.isalnum())


def _is_scalar(value: Any) -> bool:
    return isinstance(value, (str, int, float, bool))


def _iter_scalar_fields(obj: Any, *, prefix: str = "") -> list[tuple[str, Any]]:
    out: list[tuple[str, Any]] = []
    if isinstance(obj, dict):
        for key, value in obj.items():
            key_text = str(key).strip()
            if not key_text:
                continue
            path = f"{prefix}.{key_text}" if prefix else key_text
            if _is_scalar(value):
                out.append((path, value))
            else:
                out.extend(_iter_scalar_fields(value, prefix=path))
    elif isinstance(obj, list):
        for idx, value in enumerate(obj):
            path = f"{prefix}[{idx}]" if prefix else f"[{idx}]"
            if _is_scalar(value):
                out.append((path, value))
            else:
                out.extend(_iter_scalar_fields(value, prefix=path))
    return out


def _extract_from_raw_alert_by_key(
    *,
    required_key: str,
    raw_alert_context: dict[str, Any] | None,
) -> tuple[Any | None, str | None]:
    if not isinstance(raw_alert_context, dict):
        return None, None

    scalar_fields = _iter_scalar_fields(raw_alert_context)
    if not scalar_fields:
        return None, None

    by_leaf: dict[str, list[tuple[str, Any]]] = {}
    for path, value in scalar_fields:
        leaf = path.split(".")[-1]
        leaf = leaf.split("[", 1)[0]
        by_leaf.setdefault(_normalize_key_name(leaf), []).append((path, value))

    normalized_required = _normalize_key_name(required_key)
    if normalized_required in by_leaf:
        path, value = by_leaf[normalized_required][0]
        return value, path

    for alias in MISSING_PARAM_EXTRACTION_ALIASES.get(required_key, ()):
        normalized_alias = _normalize_key_name(alias)
        if normalized_alias in by_leaf:
            path, value = by_leaf[normalized_alias][0]
            return value, path

    # Minimal fuzzy fallback for near-same leaf names.
    best_score = 0.0
    best: tuple[str, Any] | None = None
    for leaf_norm, entries in by_leaf.items():
        score = SequenceMatcher(None, normalized_required, leaf_norm).ratio()
        if score >= 0.86 and score > best_score:
            best_score = score
            best = entries[0]
    if best is not None:
        return best[1], best[0]

    if required_key == "indicator":
        for candidate_key in ("dest_ip", "destination_ip", "url", "domain", "file_path", "command_line", "query"):
            normalized_alias = _normalize_key_name(candidate_key)
            if normalized_alias in by_leaf:
                path, value = by_leaf[normalized_alias][0]
                return value, path

    return None, None


def _extract_case_id(raw_alert_context: dict[str, Any] | None) -> str | None:
    if not isinstance(raw_alert_context, dict):
        return None
    candidate_keys = ("case_id", "caseId", "case", "kibana_case_id", "sid", "search_id", "job_id")
    for key in candidate_keys:
        value = raw_alert_context.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
    for text in _flatten_strings(raw_alert_context):
        if "case-" in text.lower():
            return text.strip()
    return None


def _extract_rule_id(raw_alert_context: dict[str, Any] | None) -> str | None:
    if not isinstance(raw_alert_context, dict):
        return None
    candidate_keys = ("rule_id", "ruleId", "kibana_rule_id", "saved_search", "saved_search_name")
    for key in candidate_keys:
        value = raw_alert_context.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
    return None


def _extract_alerts_query(raw_alert_context: dict[str, Any] | None) -> dict[str, Any]:
    # Safe default query body: recent window + basic IOC terms when available.
    if not isinstance(raw_alert_context, dict):
        return {"size": 50, "query": {"match_all": {}}}
    iocs = []
    for key in ("ip", "src_ip", "source_ip", "dst_ip", "destination_ip", "host", "hostname", "domain", "url"):
        value = raw_alert_context.get(key)
        if isinstance(value, str) and value.strip():
            iocs.append(value.strip())
    should = [{"match_phrase": {"message": value}} for value in iocs[:5]]
    time_gte = raw_alert_context.get("time_from") or raw_alert_context.get("start_time") or "now-24h"
    time_lte = raw_alert_context.get("time_to") or raw_alert_context.get("end_time") or "now"
    if should:
        return {
            "size": 50,
            "query": {
                "bool": {
                    "filter": [{"range": {"@timestamp": {"gte": time_gte, "lte": time_lte}}}],
                    "should": should,
                    "minimum_should_match": 1,
                }
            },
        }
    return {
        "size": 50,
        "query": {"bool": {"filter": [{"range": {"@timestamp": {"gte": time_gte, "lte": time_lte}}}]}},
    }


def _autofill_from_raw_alert(
    *,
    generic_action: str,
    params: dict[str, Any],
    raw_alert_context: dict[str, Any] | None,
) -> dict[str, Any]:
    out = dict(params)
    if generic_action in {"query_case_detail", "query_case_alerts", "query_case_comments", "query_case_activity"}:
        if not out.get("case_id") and not out.get("sid"):
            case_id = _extract_case_id(raw_alert_context)
            if case_id:
                out["case_id"] = case_id
                out["sid"] = case_id
    if generic_action == "query_rule_detail":
        if not out.get("rule_id") and not out.get("search_name"):
            rule_id = _extract_rule_id(raw_alert_context)
            if rule_id:
                out["rule_id"] = rule_id
                out["search_name"] = rule_id
    if generic_action == "query_alerts":
        if not isinstance(out.get("query"), dict) or not out.get("query"):
            out["query"] = _extract_alerts_query(raw_alert_context)
    return out


def _materialize_tool_input(
    *,
    params: dict[str, Any],
    param_map: dict[str, str],
    defaults: dict[str, Any],
    required_params: tuple[str, ...],
) -> dict[str, Any]:
    out: dict[str, Any] = dict(defaults)
    for source_key, value in params.items():
        target_key = param_map.get(source_key, source_key)
        out[target_key] = value

    missing = [
        key
        for key in required_params
        if key not in out or out.get(key) is None or (isinstance(out.get(key), str) and not str(out.get(key)).strip())
    ]
    if missing:
        raise GenericActionResolveError(
            f"Missing required params: {missing}"
        )
    return out


def _adapt_splunk_alert_search_params(
    *,
    generic_action: str,
    params: dict[str, Any],
) -> dict[str, Any]:
    """Normalize Splunk query_alerts params to match soc_splunk_search_export signature."""
    if generic_action != "query_alerts":
        return params
    out = dict(params)
    if "search" in out:
        return out
    query = out.pop("query", None)
    if isinstance(query, str) and query.strip():
        out["search"] = query.strip()
        return out
    # Elastic-style query DSL cannot be passed to Splunk export endpoint.
    out["search"] = "search index=*"
    return out


def _autofill_missing_required_params(
    *,
    vendor: str,
    generic_action: str,
    params: dict[str, Any],
    param_map: dict[str, str],
    defaults: dict[str, Any],
    required_params: tuple[str, ...],
    raw_alert_context: dict[str, Any] | None,
) -> dict[str, Any]:
    if not required_params:
        return params

    # Probe missing status on target keys (post-map).
    materialized_probe = dict(defaults)
    for source_key, value in params.items():
        materialized_probe[param_map.get(source_key, source_key)] = value

    out = dict(params)
    extracted: dict[str, str] = {}

    for required_key in required_params:
        existing = materialized_probe.get(required_key)
        if existing is not None and (not isinstance(existing, str) or existing.strip()):
            continue
        value, source_path = _extract_from_raw_alert_by_key(
            required_key=required_key,
            raw_alert_context=raw_alert_context,
        )
        if value is None or (isinstance(value, str) and not value.strip()):
            continue

        target_source_key = next(
            (source_key for source_key, target_key in param_map.items() if target_key == required_key),
            required_key,
        )
        if target_source_key in out and out.get(target_source_key) not in (None, ""):
            continue

        out[target_source_key] = value
        materialized_probe[required_key] = value
        if source_path:
            extracted[required_key] = source_path

    if extracted:
        logger.info(
            "soc_action_param_extracted_from_alert",
            vendor=vendor,
            generic_action=generic_action,
            extracted_fields=extracted,
        )
    return out


def list_generic_actions(vendor: str) -> list[str]:
    """List supported generic actions for one vendor."""
    normalized_vendor = _normalize_vendor(None, vendor)
    mappings = VENDOR_ACTION_MAP.get(normalized_vendor)
    if mappings is None:
        raise GenericActionResolveError(
            f"Unsupported vendor: {vendor}. supported={sorted(VENDOR_ACTION_MAP.keys())}"
        )
    return sorted(mappings.keys())


def resolve_generic_action(
    *,
    vendor: str,
    generic_action: str,
    action_params: dict[str, Any] | None = None,
    raw_alert_context: dict[str, Any] | None = None,
    vendor_routing: dict[str, Any] | None = None,
) -> ResolvedActionCall:
    """Resolve generic action into concrete tool call."""
    vendor = _resolve_vendor_for_action(
        fallback_vendor=vendor,
        generic_action=generic_action,
        vendor_routing=vendor_routing,
    )
    mappings = VENDOR_ACTION_MAP.get(vendor)
    if mappings is None:
        raise GenericActionResolveError(
            f"Unsupported vendor: {vendor}. supported={sorted(VENDOR_ACTION_MAP.keys())}"
        )

    mapping = mappings.get(generic_action)
    if mapping is None:
        raise GenericActionResolveError(
            f"Unsupported generic_action {generic_action!r} for vendor {vendor!r}"
        )

    normalized_params = _normalize_params(action_params)
    normalized_params = _canonicalize_action_params(
        vendor=vendor,
        generic_action=generic_action,
        params=normalized_params,
    )
    normalized_params = _autofill_from_raw_alert(
        generic_action=generic_action,
        params=normalized_params,
        raw_alert_context=raw_alert_context,
    )
    if vendor == "splunk":
        normalized_params = _adapt_splunk_alert_search_params(
            generic_action=generic_action,
            params=normalized_params,
        )
    normalized_params = _autofill_missing_required_params(
        vendor=vendor,
        generic_action=generic_action,
        params=normalized_params,
        param_map=mapping.param_map,
        defaults=mapping.defaults,
        required_params=mapping.required_params,
        raw_alert_context=raw_alert_context,
    )
    tool_input = _materialize_tool_input(
        params=normalized_params,
        param_map=mapping.param_map,
        defaults=mapping.defaults,
        required_params=mapping.required_params,
    )
    return ResolvedActionCall(
        vendor=vendor,
        generic_action=generic_action,
        tool_name=mapping.tool_name,
        tool_input=tool_input,
    )


def build_vendor_params(
    *,
    vendor: str,
    generic_action: str,
    canonical_input: dict[str, Any] | None = None,
    raw_alert_context: dict[str, Any] | None = None,
    vendor_routing: dict[str, Any] | None = None,
) -> ResolvedActionCall:
    """Build vendor tool params from canonical input with raw alert autofill."""
    return resolve_generic_action(
        vendor=vendor,
        generic_action=generic_action,
        action_params=canonical_input,
        raw_alert_context=raw_alert_context,
        vendor_routing=vendor_routing,
    )


async def execute_generic_action(
    *,
    vendor: str,
    generic_action: str,
    action_params: dict[str, Any] | None = None,
    raw_alert_context: dict[str, Any] | None = None,
    vendor_routing: dict[str, Any] | None = None,
    session_id: str | None = None,
    request_id: str | None = None,
    user_id: str | None = None,
) -> dict[str, Any]:
    """Resolve and execute one generic action against vendor handler."""
    effective_user_id = first_nonempty_str(user_id, get_request_user_id())
    logger.info(
        "soc_action_execute_start",
        vendor=vendor,
        generic_action=generic_action,
        has_action_params=isinstance(action_params, dict) and bool(action_params),
        has_raw_alert_context=isinstance(raw_alert_context, dict) and bool(raw_alert_context),
        has_explicit_user_id=bool((user_id or "").strip()),
        has_effective_user_id=bool((effective_user_id or "").strip()),
    )
    resolved = resolve_generic_action(
        vendor=vendor,
        generic_action=generic_action,
        action_params=action_params,
        raw_alert_context=raw_alert_context,
        vendor_routing=vendor_routing,
    )
    mapping = VENDOR_ACTION_MAP[resolved.vendor][resolved.generic_action]
    provider_code = resolved.vendor
    logger.info(
        "soc_action_resolved",
        vendor=resolved.vendor,
        generic_action=resolved.generic_action,
        tool_name=resolved.tool_name,
        tool_input_keys=sorted(resolved.tool_input.keys()),
    )
    scope_session_id, scope_request_id, scope_user_id = derive_auth_scope(
        explicit_session_id=session_id,
        explicit_request_id=request_id,
        explicit_user_id=effective_user_id,
        raw_alert_context=raw_alert_context,
    )
    provider_auth: dict[str, Any] | None = None
    try:
        _ = get_provider(provider_code)
        auth_service = get_vendor_auth_service()
        logger.info(
            "soc_action_auth_resolve_start",
            provider_code=provider_code,
            has_scope_session=bool(scope_session_id),
            has_scope_request=bool(scope_request_id),
            has_scope_user=bool(scope_user_id),
        )
        provider_auth = await auth_service.resolve_or_request_credentials(
            provider_code=provider_code,
            session_id=scope_session_id,
            request_id=scope_request_id,
            user_id=scope_user_id,
        )
        logger.info(
            "soc_action_auth_resolve_done",
            provider_code=provider_code,
            auth_fields=sorted((provider_auth or {}).keys()),
        )
    except ProviderRegistryError:
        logger.info(
            "soc_action_auth_skipped",
            provider_code=provider_code,
            reason="provider_not_registered",
        )
        provider_auth = None

    runtime_ctx = nullcontext()
    if provider_code == "splunk" and provider_auth:
        logger.info("soc_action_runtime_override", provider_code=provider_code, enabled=True)
        runtime_ctx = splunk_runtime_override(
            {
                "credentials": provider_auth,
                "base_url": provider_auth.get("base_url"),
            }
        )
    with runtime_ctx:
        handler_input = _prepare_handler_input(
            handler=mapping.handler,
            tool_input=resolved.tool_input,
            vendor=provider_code,
            generic_action=resolved.generic_action,
            tool_name=resolved.tool_name,
        )
        logger.info(
            "soc_action_handler_call",
            provider_code=provider_code,
            tool_name=resolved.tool_name,
            tool_input_keys=sorted(handler_input.keys()),
        )
        result = await mapping.handler(**handler_input)
    logger.info(
        "soc_action_handler_done",
        provider_code=provider_code,
        tool_name=resolved.tool_name,
        result_type=type(result).__name__,
        is_result_dict=isinstance(result, dict),
    )
    if isinstance(result, dict):
        return {
            "resolved": {
                **resolved.model_dump(),
                "tool_input": handler_input,
            },
            "result": result,
        }
    return {
        "resolved": {
            **resolved.model_dump(),
            "tool_input": handler_input,
        },
        "result": {"raw": result},
    }
