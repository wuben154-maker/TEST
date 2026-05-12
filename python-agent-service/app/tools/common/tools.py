"""Common security tools shared across all subagents."""

from __future__ import annotations

import base64
import hashlib
import re
from typing import Any
from urllib.parse import unquote, unquote_plus

import httpx
import structlog
from langchain_core.tools import StructuredTool
from pydantic import BaseModel, Field

from app.config import get_settings
from app.sse.tool_presentation import (
    COMMON_SECURITY_TOOL_ORDER,
    HITL_REGISTRY_TOOL_NAME,
    RESEARCH_TOOL_ORDER,
    common_tools_key_order,
    get_tool_rule,
    is_tiered_tool_registry,
)

logger = structlog.get_logger(__name__)


# ---------------------------------------------------------------------------
# Input schemas
# ---------------------------------------------------------------------------


class ExtractIOCsInput(BaseModel):
    """Input for extract_iocs tool."""

    text: str = Field(description="Text content to extract IOCs from")


class DecodeBase64Input(BaseModel):
    """Input for decode_base64 tool."""

    encoded: str = Field(description="Base64 encoded string to decode")


class DecodeURLInput(BaseModel):
    """Input for decode_url tool."""

    encoded: str = Field(description="URL encoded string to decode")


class ThreatIntelInput(BaseModel):
    """Input for lookup_threat_intel tool."""

    indicator: str = Field(description="Indicator to lookup (IP, domain, or hash)")
    indicator_type: str = Field(description="Type: ip, domain, or hash")


# ---------------------------------------------------------------------------
# Implementation functions
# ---------------------------------------------------------------------------

_COMMON_TOOL_DESCRIPTION_FALLBACKS: dict[str, str] = {
    "extract_iocs": "Extract IOCs (IPs, domains, URLs, hashes, emails) from text",
    "decode_base64": "Decode Base64 encoded string",
    "decode_url": "URL decode a string",
    "lookup_threat_intel": "Query threat intelligence for an indicator (IP, domain, hash)",
}


def extract_iocs(text: str) -> dict[str, Any]:
    """Extract Indicators of Compromise from text."""
    patterns = {
        "ipv4": r"\b(?:(?:25[0-5]|2[0-4][0-9]|[01]?[0-9][0-9]?)\.){3}(?:25[0-5]|2[0-4][0-9]|[01]?[0-9][0-9]?)\b",
        "ipv6": r"\b(?:[0-9a-fA-F]{1,4}:){7}[0-9a-fA-F]{1,4}\b",
        "domain": r"\b(?:[a-zA-Z0-9](?:[a-zA-Z0-9-]{0,61}[a-zA-Z0-9])?\.)+[a-zA-Z]{2,}\b",
        "url": r"https?://[^\s<>\"'{}|\\^`\[\]]+",
        "email": r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}\b",
        "md5": r"\b[a-fA-F0-9]{32}\b",
        "sha1": r"\b[a-fA-F0-9]{40}\b",
        "sha256": r"\b[a-fA-F0-9]{64}\b",
    }

    results: dict[str, list[str]] = {}
    for ioc_type, pattern in patterns.items():
        matches = list(set(re.findall(pattern, text)))
        if matches:
            results[ioc_type] = matches

    return {
        "total_iocs": sum(len(v) for v in results.values()),
        "iocs": results,
    }


def decode_base64(encoded: str) -> dict[str, Any]:
    """Decode Base64 encoded string."""
    try:
        decoded = base64.b64decode(encoded).decode("utf-8", errors="replace")
        return {"success": True, "decoded": decoded, "encoding": "base64"}
    except Exception:
        try:
            decoded = base64.urlsafe_b64decode(encoded).decode("utf-8", errors="replace")
            return {"success": True, "decoded": decoded, "encoding": "base64url"}
        except Exception as e:
            return {"success": False, "error": str(e)}


def decode_url(encoded: str) -> dict[str, Any]:
    """URL decode a string."""
    try:
        decoded = unquote(encoded)
        if "+" in encoded and decoded == encoded:
            decoded = unquote_plus(encoded)
        return {"success": True, "decoded": decoded}
    except Exception as e:
        return {"success": False, "error": str(e)}


async def lookup_threat_intel(indicator: str, indicator_type: str) -> dict[str, Any]:
    """Query threat intelligence for an indicator."""
    settings = get_settings()

    if not settings.virustotal_api_key:
        return _simulate_threat_intel(indicator, indicator_type)

    vt_base_url = settings.virustotal_api_base_url
    endpoint_map = {
        "ip": f"{vt_base_url}/ip_addresses/{indicator}",
        "domain": f"{vt_base_url}/domains/{indicator}",
        "hash": f"{vt_base_url}/files/{indicator}",
    }

    endpoint = endpoint_map.get(indicator_type)
    if not endpoint:
        return {"error": f"Invalid indicator type: {indicator_type}"}

    async with httpx.AsyncClient() as client:
        try:
            response = await client.get(
                endpoint,
                headers={"x-apikey": settings.virustotal_api_key},
                timeout=30.0,
            )

            if response.status_code == 404:
                return {
                    "indicator": indicator,
                    "type": indicator_type,
                    "found": False,
                    "message": "Not found in VirusTotal",
                }

            response.raise_for_status()
            data = response.json()
            attributes = data.get("data", {}).get("attributes", {})
            stats = attributes.get("last_analysis_stats", {})

            return {
                "indicator": indicator,
                "type": indicator_type,
                "found": True,
                "malicious": stats.get("malicious", 0),
                "suspicious": stats.get("suspicious", 0),
                "harmless": stats.get("harmless", 0),
                "reputation": attributes.get("reputation", 0),
            }
        except Exception as e:
            return {"error": str(e)}


def _simulate_threat_intel(indicator: str, indicator_type: str) -> dict[str, Any]:
    """Simulated threat intel when no API key is available."""
    malicious_patterns = [
        "evil", "malware", "phishing", "hack", "exploit",
        "${jndi:", "eval(", "base64_decode", "cmd.exe",
    ]

    is_suspicious = any(p in indicator.lower() for p in malicious_patterns)

    return {
        "indicator": indicator,
        "type": indicator_type,
        "found": True,
        "source": "pattern_analysis",
        "malicious": 10 if is_suspicious else 0,
        "suspicious": 5 if is_suspicious else 0,
        "harmless": 0 if is_suspicious else 60,
        "reputation": -50 if is_suspicious else 0,
        "note": "Simulated result - no VirusTotal API key configured",
    }


# ---------------------------------------------------------------------------
# Tool assembly helpers
# ---------------------------------------------------------------------------


def _registry_tool_description(tool_name: str, code_fallback: str) -> str:
    rule = get_tool_rule(tool_name)
    if rule and rule.description:
        return rule.description
    return code_fallback


def _resolve_common_tool_description(tool_name: str) -> str:
    return _registry_tool_description(
        tool_name,
        _COMMON_TOOL_DESCRIPTION_FALLBACKS[tool_name],
    )


def _structured_tool_description_from_registry(tool_name: str) -> str:
    """LLM-facing description: must come from ``config/tool_presentation.yaml``."""
    rule = get_tool_rule(tool_name)
    if rule and rule.description and str(rule.description).strip():
        return str(rule.description).strip()
    logger.error("common_tool_missing_registry_description", tool_name=tool_name)
    return tool_name


def _mount_search_history(out: list[StructuredTool]) -> None:
    from app.tools.conversation_history_tools import SearchHistoryInput, search_history

    desc = _structured_tool_description_from_registry("search_history")
    out.append(
        StructuredTool.from_function(
            func=search_history,
            name="search_history",
            description=desc,
            args_schema=SearchHistoryInput,
            coroutine=search_history,
        )
    )


def _mount_common_security_tool(tool_name: str, out: list[StructuredTool]) -> None:
    """Append one security tool; caller must already enforce YAML ``enabled``."""
    desc = _resolve_common_tool_description(tool_name)
    if tool_name == "extract_iocs":
        out.append(
            StructuredTool.from_function(
                func=extract_iocs, name="extract_iocs",
                description=desc, args_schema=ExtractIOCsInput,
            )
        )
    elif tool_name == "decode_base64":
        out.append(
            StructuredTool.from_function(
                func=decode_base64, name="decode_base64",
                description=desc, args_schema=DecodeBase64Input,
            )
        )
    elif tool_name == "decode_url":
        out.append(
            StructuredTool.from_function(
                func=decode_url, name="decode_url",
                description=desc, args_schema=DecodeURLInput,
            )
        )
    elif tool_name == "lookup_threat_intel":
        out.append(
            StructuredTool.from_function(
                func=lookup_threat_intel, name="lookup_threat_intel",
                description=desc, args_schema=ThreatIntelInput,
                coroutine=lookup_threat_intel,
            )
        )


def _append_common_security_tool(tool_name: str, out: list[StructuredTool]) -> None:
    rule = get_tool_rule(tool_name)
    if rule is not None and not rule.enabled:
        return
    _mount_common_security_tool(tool_name, out)


def create_common_tools(
    *,
    include_hitl: bool | None = None,
    only_names: frozenset[str] | None = None,
) -> list[StructuredTool]:
    """Assemble tools declared under ``common_tools`` in tiered YAML (in file order).

    ``only_names`` restricts to a subset (e.g. deep-research profile = research trio).

    When ``include_hitl`` is None, defaults to True so ``request_user_input`` can be
    mounted when YAML enables it.
    """
    if include_hitl is None:
        include_hitl = True

    tools: list[StructuredTool] = []

    if is_tiered_tool_registry():
        from app.tools.common_tool_registry import try_mount_common_tool

        for name in common_tools_key_order():
            if only_names is not None and name not in only_names:
                continue
            rule = get_tool_rule(name)
            if rule is None:
                logger.warning("common_tools_missing_rule", tool_name=name)
                continue
            if not rule.enabled:
                continue
            if name == HITL_REGISTRY_TOOL_NAME:
                if include_hitl:
                    from app.tools.hitl_tools import create_hitl_tools

                    override = rule.description if rule.description else None
                    tools.extend(create_hitl_tools(description_override=override))
                continue
            if try_mount_common_tool(name, tools):
                continue
            logger.warning("common_tools_no_impl", tool_name=name)
        return tools

    from app.tools.research_tools import try_append_research_tool

    for name in COMMON_SECURITY_TOOL_ORDER:
        if only_names is not None and name not in only_names:
            continue
        _append_common_security_tool(name, tools)

    for name in RESEARCH_TOOL_ORDER:
        if only_names is not None and name not in only_names:
            continue
        try_append_research_tool(name, tools, assume_yaml_enabled=False)

    hitl_rule = get_tool_rule(HITL_REGISTRY_TOOL_NAME)
    hitl_allowed_by_yaml = hitl_rule is None or hitl_rule.enabled
    if (
        only_names is None
        and include_hitl
        and hitl_allowed_by_yaml
    ):
        from app.tools.hitl_tools import create_hitl_tools

        override = hitl_rule.description if hitl_rule else None
        tools.extend(create_hitl_tools(description_override=override))
    return tools
