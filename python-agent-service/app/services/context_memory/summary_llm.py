"""Optional LLM delta for derived memory (bounded input)."""

from __future__ import annotations

import json
import re
from typing import Any

import structlog
from langchain_core.messages import HumanMessage, SystemMessage

from app.config import get_settings
from app.llm_gateway.factory import get_model
from app.services.context_memory.merge import truncate_for_summary

logger = structlog.get_logger()

_SYSTEM = """You extract structured deltas for a security analyst assistant memory.
Return ONLY a JSON object with keys:
- "findings": string array (0-5 short bullet strings, no PII)
- "summary_delta": string (one paragraph, <=400 chars) to merge into running summary
If nothing useful, return {"findings":[],"summary_delta":""}.
No markdown fences."""


def _parse_json_loose(text: str) -> dict[str, Any]:
    t = (text or "").strip()
    if not t:
        return {}
    t = re.sub(r"^```(?:json)?\s*", "", t, flags=re.IGNORECASE)
    t = re.sub(r"\s*```\s*$", "", t)
    try:
        obj = json.loads(t)
        return obj if isinstance(obj, dict) else {}
    except json.JSONDecodeError:
        return {}


async def summarize_turn_delta(
    assistant_excerpt: str, *, model_id: str | None
) -> tuple[list[str], str | None, str | None]:
    """Returns (findings_delta, summary_delta, resolved_model_id or None on skip/failure)."""
    settings = get_settings()
    mid = (model_id or "").strip() or (settings.derived_layer_model or "").strip()
    if not mid:
        return [], None, None
    capped = truncate_for_summary(assistant_excerpt, settings.context_summary_input_max_chars)
    if not capped:
        return [], None, None
    try:
        llm = get_model(mid)
    except Exception as e:
        logger.warning("derived_layer model unavailable", model_id=mid, error=str(e))
        return [], None, None
    try:
        resp = await llm.ainvoke(
            [
                SystemMessage(content=_SYSTEM),
                HumanMessage(
                    content="Assistant turn excerpt (may be truncated):\n\n" + capped
                ),
            ]
        )
        raw = getattr(resp, "content", None)
        text = raw if isinstance(raw, str) else str(raw or "")
        parsed = _parse_json_loose(text)
        findings_raw = parsed.get("findings") or []
        findings = [
            str(x).strip()
            for x in findings_raw
            if x is not None and str(x).strip()
        ][:5]
        sd = parsed.get("summary_delta")
        summary_delta = str(sd).strip()[:400] if sd else None
        return findings, summary_delta, mid
    except Exception as e:
        logger.warning("derived_layer LLM invoke failed", model_id=mid, error=str(e))
        return [], None, mid
