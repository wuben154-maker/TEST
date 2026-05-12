"""Core policy, evidence, and audit utilities for the email security agent.

This subpackage groups framework-agnostic primitives that are shared across
tools.
"""

from .audit import AuditTrace
from .evidence import (
    Artifact,
    Confidence,
    EvidenceItem,
    EvidenceStore,
    Severity,
    domain_from_url,
    normalize_domain,
    normalize_sha256,
    normalize_url,
)
from .investigation_policy import (
    Action,
    ActionType,
    Budget,
    plan_attachment_ti_actions,
    plan_bec_enrich_actions,
    prioritize_attachments_for_second_pass,
)

__all__ = [
    "AuditTrace",
    "Artifact",
    "Confidence",
    "EvidenceItem",
    "EvidenceStore",
    "Severity",
    "domain_from_url",
    "normalize_domain",
    "normalize_sha256",
    "normalize_url",
    "Action",
    "ActionType",
    "Budget",
    "plan_attachment_ti_actions",
    "plan_bec_enrich_actions",
    "prioritize_attachments_for_second_pass",
]

