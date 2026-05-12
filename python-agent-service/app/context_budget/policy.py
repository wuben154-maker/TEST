"""Thresholds and ``context_budget`` SSE payload construction."""

from __future__ import annotations

from typing import Any, Literal

from app.config import Settings
from app.context_budget.window import resolve_context_window

Tier = Literal["safe", "warn", "danger", "critical"]


def tier_for_fill_ratio(ratio: float, s: Settings) -> Tier:
    if ratio >= s.context_budget_critical_ratio:
        return "critical"
    if ratio >= s.context_budget_danger_ratio:
        return "danger"
    if ratio >= s.context_budget_warn_ratio:
        return "warn"
    return "safe"


def build_context_budget_event_dict(
    *,
    llm_invoke_end: dict[str, Any],
    settings: Settings,
) -> dict[str, Any] | None:
    """Build raw ``context_budget`` dict (before SSE envelope) from a completed main invoke.

    Returns ``None`` when usage is missing or window is invalid.
    """
    if not settings.context_budget_sse_enabled:
        return None
    usage = llm_invoke_end.get("usage")
    if not isinstance(usage, dict):
        return None
    prompt = max(0, int(usage.get("inputTokens") or 0))
    model_id = llm_invoke_end.get("modelId")
    if isinstance(model_id, str):
        model_id = model_id.strip() or None
    else:
        model_id = None
    window = resolve_context_window(model_id)
    if window <= 0:
        return None
    fill = min(1.0, max(0.0, float(prompt) / float(window)))
    fill_source: Literal["provider", "approximate"] = "provider"
    tier = tier_for_fill_ratio(fill, settings)
    ts = llm_invoke_end.get("timestamp")
    try:
        ts_int = int(ts) if ts is not None else 0
    except (TypeError, ValueError):
        ts_int = 0
    return {
        "type": "context_budget",
        "id": f"budget-{llm_invoke_end.get('invokeId') or llm_invoke_end.get('id') or 'unknown'}",
        "scope": "main",
        "contextWindow": window,
        "promptTokens": prompt,
        "fillRatio": round(fill, 6),
        "fillSource": fill_source,
        "tier": tier,
        "modelId": model_id,
        "timestamp": ts_int,
    }
