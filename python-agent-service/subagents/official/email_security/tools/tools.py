"""Email-security subagent tools: header analysis and phishing detection."""

from __future__ import annotations

import re
from typing import Any

from langchain_core.tools import StructuredTool
from pydantic import BaseModel, Field

from app.sse.tool_presentation import EMAIL_SECURITY_TOOL_ORDER, get_tool_rule

# ---------------------------------------------------------------------------
# Input schemas
# ---------------------------------------------------------------------------


class AnalyzeEmailHeadersInput(BaseModel):
    """Input for analyze_email_headers tool."""

    headers: str = Field(description="Raw email headers to analyze")


class CheckSenderReputationInput(BaseModel):
    """Input for check_sender_reputation tool."""

    sender_email: str = Field(description="Sender email address")
    sender_domain: str = Field(description="Sender domain")


# ---------------------------------------------------------------------------
# Implementation functions
# ---------------------------------------------------------------------------

_EMAIL_TOOL_DESCRIPTION_FALLBACKS: dict[str, str] = {
    "analyze_email_headers": "Analyze email headers for authentication and spoofing indicators",
    "detect_phishing_indicators": "Detect phishing indicators in email content",
}


def _registry_tool_description(tool_name: str, code_fallback: str) -> str:
    rule = get_tool_rule(tool_name)
    if rule and rule.description:
        return rule.description
    return code_fallback


def analyze_email_headers(headers: str) -> dict[str, Any]:
    """Analyze email headers for security indicators."""
    findings: dict[str, Any] = {
        "authentication": {},
        "routing": [],
        "suspicious_indicators": [],
        "extracted_ips": [],
    }

    if "spf=pass" in headers.lower():
        findings["authentication"]["spf"] = "pass"
    elif "spf=fail" in headers.lower():
        findings["authentication"]["spf"] = "fail"
        findings["suspicious_indicators"].append("SPF failed")

    if "dkim=pass" in headers.lower():
        findings["authentication"]["dkim"] = "pass"
    elif "dkim=fail" in headers.lower():
        findings["authentication"]["dkim"] = "fail"
        findings["suspicious_indicators"].append("DKIM failed")

    if "dmarc=pass" in headers.lower():
        findings["authentication"]["dmarc"] = "pass"
    elif "dmarc=fail" in headers.lower():
        findings["authentication"]["dmarc"] = "fail"
        findings["suspicious_indicators"].append("DMARC failed")

    received_pattern = r"Received:.*?from.*?\[(\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3})\]"
    ips = re.findall(received_pattern, headers, re.IGNORECASE)
    findings["extracted_ips"] = list(set(ips))

    if "Reply-To:" in headers:
        from_match = re.search(r"From:.*?<([^>]+)>", headers)
        reply_match = re.search(r"Reply-To:.*?<([^>]+)>", headers)
        if from_match and reply_match:
            if from_match.group(1) != reply_match.group(1):
                findings["suspicious_indicators"].append(
                    "Reply-To differs from From address"
                )

    return findings


def detect_phishing_indicators(content: str) -> dict[str, Any]:
    """Detect phishing indicators in email content."""
    indicators: list[str] = []
    severity_score = 0

    urgency_patterns = [
        r"urgent",
        r"immediately",
        r"within \d+ hours?",
        r"act now",
        r"limited time",
        r"expires? (today|soon|tomorrow)",
        r"account.*suspend",
        r"verify.*account",
    ]

    for pattern in urgency_patterns:
        if re.search(pattern, content, re.IGNORECASE):
            indicators.append(f"Urgency indicator: {pattern}")
            severity_score += 1

    credential_patterns = [
        r"password",
        r"login",
        r"sign.?in",
        r"verify.*identity",
        r"confirm.*details",
        r"update.*information",
    ]

    for pattern in credential_patterns:
        if re.search(pattern, content, re.IGNORECASE):
            indicators.append(f"Credential harvesting indicator: {pattern}")
            severity_score += 2

    suspicious_url_patterns = [
        r"http://",
        r"bit\.ly",
        r"tinyurl",
        r"goo\.gl",
        r"\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3}",
    ]

    for pattern in suspicious_url_patterns:
        if re.search(pattern, content, re.IGNORECASE):
            indicators.append(f"Suspicious URL pattern: {pattern}")
            severity_score += 2

    return {
        "phishing_indicators": indicators,
        "severity_score": severity_score,
        "risk_level": "high" if severity_score >= 5 else "medium" if severity_score >= 2 else "low",
    }


# ---------------------------------------------------------------------------
# Tool assembly
# ---------------------------------------------------------------------------


def _append_email_tool(tool_name: str, out: list[StructuredTool]) -> None:
    rule = get_tool_rule(tool_name)
    if rule is not None and not rule.enabled:
        return
    desc = _registry_tool_description(
        tool_name,
        _EMAIL_TOOL_DESCRIPTION_FALLBACKS[tool_name],
    )
    if tool_name == "analyze_email_headers":
        out.append(
            StructuredTool.from_function(
                func=analyze_email_headers,
                name="analyze_email_headers",
                description=desc,
                args_schema=AnalyzeEmailHeadersInput,
            )
        )
    elif tool_name == "detect_phishing_indicators":
        out.append(
            StructuredTool.from_function(
                func=detect_phishing_indicators,
                name="detect_phishing_indicators",
                description=desc,
            )
        )


def create_email_tools() -> list[StructuredTool]:
    """Create email-specific security tools.

    Enabled flags and descriptions come from ``config/tool_presentation.yaml``
    (keys under ``EMAIL_SECURITY_TOOL_ORDER``).
    """
    out: list[StructuredTool] = []
    for name in EMAIL_SECURITY_TOOL_ORDER:
        _append_email_tool(name, out)
    return out
