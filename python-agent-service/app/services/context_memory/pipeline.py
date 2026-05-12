"""Orchestration: merge after persist, injection + hydrate prefixes for analyze."""

from __future__ import annotations

import time
from typing import Any

import structlog

from app.config import get_settings
from app.services.context_memory.merge import (
    format_derived_for_injection,
    format_user_index_for_injection,
    merge_project_derived,
    patch_user_index,
    truncate_for_summary,
)
from app.services.context_memory.repository import (
    fetch_project_title,
    fetch_recent_messages_for_hydrate,
    load_project_derived,
    load_user_index,
    merge_already_processed,
    record_merge_processed,
    save_project_derived,
    save_user_index,
    verify_project_owner,
)
from app.services.context_memory.summary_llm import summarize_turn_delta

logger = structlog.get_logger()


def _assistant_text_from_state(state: dict[str, Any]) -> str:
    parts: list[str] = []
    c = (state.get("content") or "").strip()
    if c:
        parts.append(c)
    for b in state.get("blocks") or []:
        if not isinstance(b, dict):
            continue
        if b.get("type") == "analysis":
            t = str(b.get("content") or "").strip()
            if t:
                parts.append(t)
    return "\n\n".join(parts).strip()


async def merge_after_message_persist(
    project_id: str,
    user_id: str,
    request_id: str | None,
    state: dict[str, Any],
) -> None:
    """Called after messages row upsert succeeds. Safe to await; errors are swallowed."""
    settings = get_settings()
    if not settings.context_memory_enabled:
        return
    rid = (request_id or "").strip()
    if not rid:
        logger.debug("context_memory merge skipped: empty request_id")
        return
    if settings.database_mode == "memory":
        return

    t0 = time.perf_counter()
    summary_model: str | None = None
    try:
        if await merge_already_processed(project_id, rid):
            logger.debug("context_memory merge idempotent skip", request_id=rid)
            return
        if not await verify_project_owner(project_id, user_id):
            logger.warning("context_memory merge denied: not project owner")
            return

        excerpt = _assistant_text_from_state(state)
        excerpt = truncate_for_summary(excerpt, settings.context_summary_input_max_chars)

        findings_delta: list[str] = []
        summary_delta: str | None = None
        if (settings.derived_layer_model or "").strip():
            try:
                fnd, sd, summary_model = await summarize_turn_delta(
                    excerpt, model_id=settings.derived_layer_model
                )
                findings_delta = fnd
                summary_delta = sd
            except Exception as e:
                logger.warning("derived_layer call failed", error=str(e))

        prev = await load_project_derived(project_id, user_id)
        next_payload = merge_project_derived(
            prev,
            assistant_excerpt=excerpt,
            request_id=rid,
            llm_findings_delta=findings_delta or None,
            llm_summary_delta=summary_delta,
        )
        await save_project_derived(project_id, user_id, next_payload)

        title = await fetch_project_title(project_id, user_id)
        one_line = (next_payload.get("running_summary") or "")[:200]
        u_prev = await load_user_index(user_id) or {}
        u_next = patch_user_index(
            u_prev,
            project_id=project_id,
            project_title=title,
            one_line=one_line,
        )
        await save_user_index(user_id, u_next)
        await record_merge_processed(project_id, rid)

        elapsed_ms = (time.perf_counter() - t0) * 1000
        logger.info(
            "context_memory_merge_total",
            merge_duration_ms=round(elapsed_ms, 2),
            summary_model=summary_model,
            project_id=project_id,
        )
    except Exception as e:
        logger.warning("context_memory merge failed", error=str(e), exc_info=True)


async def build_injection_prefix(
    project_id: str | None, user_id: str | None
) -> str:
    settings = get_settings()
    if not settings.context_memory_enabled:
        return ""
    if not project_id or not user_id:
        return ""
    if settings.database_mode == "memory":
        return ""
    try:
        half = max(256, settings.context_inject_max_chars // 2)
        derived = await load_project_derived(project_id, user_id)
        user_idx = await load_user_index(user_id)
        block_p = ""
        block_u = ""
        if derived:
            block_p = format_derived_for_injection(derived, half)
        if user_idx:
            block_u = format_user_index_for_injection(user_idx, half)
        parts: list[str] = []
        if block_p:
            parts.append("[Project memory]\n" + block_p)
        if block_u:
            parts.append("[User context]\n" + block_u)
        merged = truncate_for_summary(
            "\n\n".join(parts).strip(), settings.context_inject_max_chars
        )
        if merged:
            logger.info(
                "context_memory_inject",
                memory_inject_bytes=len(merged.encode("utf-8")),
            )
        return merged
    except Exception as e:
        logger.debug("injection load failed", error=str(e))
        return ""


async def fetch_hydration_prefix(
    project_id: str | None, user_id: str | None
) -> str:
    settings = get_settings()
    if not settings.context_hydrate_enabled or not settings.context_memory_enabled:
        return ""
    if not project_id or not user_id:
        return ""
    if settings.database_mode == "memory":
        return ""
    try:
        rows = await fetch_recent_messages_for_hydrate(
            project_id, user_id, settings.context_hydrate_max_turns
        )
        if not rows:
            return ""
        lines: list[str] = []
        budget = settings.context_inject_max_chars
        for role, content in rows:
            label = "User" if role == "user" else "Assistant"
            chunk = f"{label}: {truncate_for_summary(content, 4000)}"
            lines.append(chunk)
        body = "\n\n".join(lines)
        body = truncate_for_summary(body, budget)
        return "[Hydrated from DB history]\n" + body if body else ""
    except Exception as e:
        logger.debug("hydrate load failed", error=str(e))
        return ""
