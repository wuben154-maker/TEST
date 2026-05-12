"""Environment toggles for L1 YARA / entropy / L3 syntax sandbox / L4 E2B escalation."""

from __future__ import annotations

import os


def _truthy(key: str, default: str = "true") -> bool:
    return os.environ.get(key, default).strip().lower() in ("1", "true", "yes", "on")


def yara_enabled() -> bool:
    return _truthy("WEB_THREAT_YARA_ENABLED", "true")


def entropy_enabled() -> bool:
    return _truthy("WEB_THREAT_ENTROPY_ENABLED", "true")


def sandbox_enabled() -> bool:
    return _truthy("WEB_THREAT_SANDBOX_ENABLED", "true")


def sandbox_timeout_sec() -> float:
    raw = os.environ.get("WEB_THREAT_SANDBOX_TIMEOUT_SEC", "8")
    try:
        v = float(raw)
        return max(1.0, min(120.0, v))
    except ValueError:
        return 8.0


def e2b_escalation_enabled() -> bool:
    """L4 E2B dynamic sandbox escalation. Off by default; requires E2B_API_KEY."""
    return _truthy("WEB_THREAT_E2B_ESCALATION_ENABLED", "false")


def e2b_escalation_confidence_threshold() -> float:
    """Confidence threshold above which L1-L3 result is considered definitive (skip L4).

    If max finding confidence >= threshold AND severity >= high, escalation is skipped.
    Default 0.80.
    """
    raw = os.environ.get("WEB_THREAT_E2B_CONFIDENCE_THRESHOLD", "0.80")
    try:
        v = float(raw)
        return max(0.0, min(1.0, v))
    except ValueError:
        return 0.80
