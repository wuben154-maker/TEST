"""SchemaVersion 1 envelope fields for analysis SSE event dicts."""

from __future__ import annotations

import time
from typing import Any

from app.parsers.message_content import normalize_llm_visible_content
from app.sse.tool_presentation import should_emit_tool_output
from app.sse.tool_result_renderers import render_tool_result

# SSE event fields that carry user-visible LLM text and should be normalized.
_VISIBLE_CONTENT_FIELDS: frozenset[str] = frozenset({
    "content",
    "detail",
})


def tag_merged_subagent_sse(evt: dict[str, Any]) -> dict[str, Any]:
    """Tag events bridged from any task() subagent into the main SSE stream.

    Maps skill_* types to canonical kinds aligned with the main agent stream.
    """
    out = {**evt}
    out["subagentStream"] = True
    if not out.get("subagentName"):
        out["subagentName"] = "subagent"
    eid = out.get("id")
    if isinstance(eid, str) and eid:
        if not (eid.startswith("subagent-") or eid.startswith("research-")):
            st = str(out.get("subagentName") or "subagent").replace(" ", "-")
            out["id"] = f"subagent-{st}-{eid}"[:240]
    if (
        out.get("subagentName") == "deep-research"
        or out.get("researchSubgraph")
    ):
        out["researchSubgraph"] = True
    stype = out.get("type")
    if stype == "skill_reasoning":
        out["type"] = "llm_delta"
        out["channel"] = "reasoning"
    elif stype == "reasoning":
        out["type"] = "llm_delta"
        out["channel"] = "reasoning"
    elif stype == "answer":
        out["type"] = "llm_delta"
        out["channel"] = "text"
    elif stype == "skill_error":
        out["type"] = "error"
    elif stype in ("skill_start", "skill_complete"):
        out["type"] = "step"
    # Apply tool_output humanization + suppression for merged subagent
    # tool_result events. Humanization runs first so:
    #   1. Per-tool renderers (registered via app.sse.tool_result_renderers)
    #      reach subagent-internal tools (e.g. detect_web_attack inside the
    #      web_security subagent), matching main-thread parity without
    #      patching vendored deepagents source.
    #   2. The error-bypass check sees humanized text, so a JSON error
    #      payload like {"error": "..."} that becomes "error: ..." still
    #      bypasses suppression for emit_output=False tools.
    # Error payloads (plain "Error: ..." strings from DeepAgents filesystem
    # tools, or events already tagged status="error") bypass suppression so
    # the UI can show *why* the call failed — without this, a failing
    # read_file in a subagent renders as an empty error card.
    if out.get("type") == "tool_result":
        tn = str(out.get("toolName") or "").strip()
        raw_out = out.get("toolOutput")
        if tn and isinstance(raw_out, str) and raw_out:
            try:
                rendered = render_tool_result(tn, raw_out)
            except Exception:
                rendered = raw_out
            if rendered:
                out["toolOutput"] = rendered
                raw_out = rendered
        stripped = (
            (raw_out or "").strip().lower()
            if isinstance(raw_out, str)
            else ""
        )
        is_plain_error = (
            stripped.startswith("error:") or stripped.startswith("error ")
        )
        is_error_status = str(out.get("status") or "").lower() == "error"
        if (
            tn
            and not should_emit_tool_output(tn)
            and not is_plain_error
            and not is_error_status
        ):
            out["toolOutput"] = ""
    return out


def _normalize_visible_fields(event: dict[str, Any]) -> dict[str, Any]:
    """Run ``normalize_llm_visible_content`` on user-facing text fields."""
    for field in _VISIBLE_CONTENT_FIELDS:
        val = event.get(field)
        if isinstance(val, str) and val:
            event[field] = normalize_llm_visible_content(val)
    return event


def apply_sse_envelope(
    event: dict[str, Any],
    seq_counter: list[int],
) -> dict[str, Any]:
    """Attach schemaVersion, monotonic seq, scope, and preserve ``turn``."""
    seq_counter[0] += 1
    out = _normalize_visible_fields(dict(event))
    out["schemaVersion"] = 1
    out["seq"] = seq_counter[0]
    # Preserve semantic wall time when the producer set it (e.g. LangChain
    # llm_invoke_* callbacks enqueue before SSE drain). Otherwise stamp at emit time.
    ts_raw = out.get("timestamp")
    if ts_raw is None:
        out["timestamp"] = int(time.time() * 1000)
    else:
        try:
            out["timestamp"] = int(ts_raw)
        except (TypeError, ValueError):
            out["timestamp"] = int(time.time() * 1000)
    if "scope" not in out:
        out["scope"] = "subagent" if out.get("subagentStream") else "main"
    return out
