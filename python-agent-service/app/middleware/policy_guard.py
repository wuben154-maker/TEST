"""Policy guard and capability negotiation helpers."""

from __future__ import annotations

from dataclasses import dataclass

from app.middleware.intent_models import AnalysisScope


KNOWN_CAPABILITIES = {
    "static_analysis",
    "ioc_extraction",
    "email_header_analysis",
    "url_extraction",
    "attachment_correlation",
    "binary_unpack",
    "sandbox_behavior",
    "web_artifact_analysis",
    "cross_file_correlation",
}


@dataclass
class PolicyDecision:
    """Result of policy guard evaluation."""

    scope: AnalysisScope
    scope_source: str
    allowed: bool
    fallback_applied: bool
    reason: str = ""

    def to_dict(self) -> dict:
        return {
            "scope": self.scope.value,
            "scope_source": self.scope_source,
            "allowed": self.allowed,
            "fallback_applied": self.fallback_applied,
            "reason": self.reason,
        }


def normalize_scope(raw_scope: str | None, default: AnalysisScope = AnalysisScope.ALL_INPUT) -> AnalysisScope:
    """Normalize free-form scope string into enum."""
    if not raw_scope:
        return default
    normalized = str(raw_scope).strip().lower()
    mapping = {
        "all": AnalysisScope.ALL_INPUT,
        "all_input": AnalysisScope.ALL_INPUT,
        "full": AnalysisScope.ALL_INPUT,
        "attachment_only": AnalysisScope.ATTACHMENT_ONLY,
        "attachments_only": AnalysisScope.ATTACHMENT_ONLY,
        "only_attachments": AnalysisScope.ATTACHMENT_ONLY,
        "text_only": AnalysisScope.TEXT_ONLY,
        "only_text": AnalysisScope.TEXT_ONLY,
    }
    return mapping.get(normalized, default)


def negotiate_capabilities(request: dict | None) -> dict:
    """Negotiate capability request against known capabilities."""
    req = request or {}
    required = [c for c in req.get("required", []) if c in KNOWN_CAPABILITIES]
    optional = [c for c in req.get("optional", []) if c in KNOWN_CAPABILITIES]
    extensions = req.get("extensions", []) or []
    approved_extensions = [c for c in extensions if c in KNOWN_CAPABILITIES]
    rejected_extensions = [c for c in extensions if c not in KNOWN_CAPABILITIES]
    return {
        "required": required,
        "optional": optional,
        "approvedExtensions": approved_extensions,
        "rejectedExtensions": rejected_extensions,
        "needsClarification": bool(rejected_extensions),
    }


def evaluate_policy(scope: AnalysisScope) -> PolicyDecision:
    """Evaluate high-level policy for scope."""
    if scope in (AnalysisScope.ALL_INPUT, AnalysisScope.ATTACHMENT_ONLY, AnalysisScope.TEXT_ONLY):
        return PolicyDecision(
            scope=scope,
            scope_source="normalized",
            allowed=True,
            fallback_applied=False,
        )
    return PolicyDecision(
        scope=AnalysisScope.ALL_INPUT,
        scope_source="fallback",
        allowed=False,
        fallback_applied=True,
        reason="scope_not_allowed",
    )

