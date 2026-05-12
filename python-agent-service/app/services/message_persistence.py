"""Persist analysis results to messages table.

Builds user/assistant messages from stream events, equivalent to frontend
buildConversationMessages. Used when analysis completes (including after client
disconnect) to ensure results are saved to DB.
"""

import json
from typing import Any

import structlog
from app.config import get_settings
from app.parsers.final_message_split import strip_leading_preface_before_cjk_report_body
from app.parsers.write_todos_plan import build_task_plan_dict_from_write_todos_args
from app.db import get_pg_pool, get_supabase_client

logger = structlog.get_logger()

# Keep in sync with frontend `src/lib/formatUserMessageDisplay.ts`
USER_MESSAGE_ATTACHMENT_LINE_PREFIX = "📎 "


def format_user_message_for_persistence(
    message: str, files_payload: list[dict] | None
) -> str:
    """Build user message text for DB/progress (same shape as frontend formatUserMessageForChat).

    Raw `message` is still sent to the LLM separately; this string is for history/replay only.
    """
    names: list[str] = []
    for f in files_payload or []:
        if not isinstance(f, dict):
            continue
        fn = str(f.get("filename") or "").strip()
        if fn:
            names.append(fn)
    base = (message or "").strip()
    if not names:
        return base or "[Attachment-only request]"
    lines = [f"{USER_MESSAGE_ATTACHMENT_LINE_PREFIX}{n}" for n in names]
    if base:
        return base + "\n\n" + "\n".join(lines)
    return "\n".join(lines)


def _timeline_from_events(events: list[dict]) -> list[dict]:
    """User-visible timeline rows for DB replay (omit internal/debug-only events)."""
    out: list[dict] = []
    for ev in events:
        if not isinstance(ev, dict):
            continue
        if ev.get("internal") is True:
            continue
        t = ev.get("type")
        if t == "debug":
            continue
        out.append(dict(ev))
    return out


def _extract_stream_events(events: list[dict]) -> list[dict]:
    """Build stream_events list from raw events (matches frontend StreamEvent format)."""
    stream_events: list[dict] = []
    for ev in events:
        t = ev.get("type")
        if t == "tool_call":
            if ev.get("toolName") in ("write_todos", "task"):
                continue  # Skip write_todos and task like frontend
            stream_events.append({
                "type": "tool_call",
                "id": ev.get("id") or f"tc-{ev.get('timestamp', 0)}",
                "timestamp": ev.get("timestamp"),
                "toolName": ev.get("toolName"),
                "toolInput": ev.get("toolInput"),
            })
        elif t == "tool_result":
            stream_events.append({
                "type": "tool_result",
                "id": ev.get("id") or f"tr-{ev.get('timestamp', 0)}",
                "timestamp": ev.get("timestamp"),
                "toolName": ev.get("toolName"),
                "toolOutput": ev.get("toolOutput"),
                "status": ev.get("status"),
            })
        elif t == "task_start":
            stream_events.append({
                "type": "task_start",
                "id": ev.get("id"),
                "taskId": ev.get("id"),
                "timestamp": ev.get("timestamp"),
            })
        elif t == "task_complete":
            stream_events.append({
                "type": "task_complete",
                "id": ev.get("id"),
                "taskId": ev.get("id"),
                "taskStatus": "success",
                "timestamp": ev.get("timestamp"),
            })
    return stream_events


def _build_state_from_events(
    events: list[dict],
    user_input: str,
    ui_language: str = "en",
) -> dict[str, Any]:
    """Build streaming state dict from collected events (mirrors frontend logic)."""
    thinking_steps: list[dict] = []
    task_plan: dict | None = None
    task_summary = ""
    conclusion = ""
    current_reasoning = ""
    understanding: dict | None = None
    blocks: list[dict] = []
    error_detail = ""
    workspace_title = ""
    is_research_route = False
    # Latest `conclusion.meta` (TaskStatsMeta) wins if adapter replays conclusion.
    stats_meta: dict | None = None

    for ev in events:
        t = ev.get("type")
        if t == "step":
            step_id = ev.get("id", "")
            if step_id == "open-deep-research-start":
                is_research_route = True
            label = ev.get("label", "")
            status = ev.get("status", "running")
            detail = ev.get("detail", "")
            thinking_steps.append({
                "id": step_id,
                "label": label,
                "status": status,
                "detail": detail or None,
            })
        elif t == "research_clarification_required":
            is_research_route = True
        elif t == "reasoning" and ev.get("content"):
            current_reasoning += (ev.get("content") or "")
        elif t == "task_plan" and ev.get("plan"):
            task_plan = ev.get("plan")
            if not workspace_title and isinstance(task_plan, dict):
                workspace_title = task_plan.get("workspaceTitle", "") or ""
        elif t == "tool_call" and ev.get("toolName") == "write_todos":
            inp = ev.get("toolInput")
            if isinstance(inp, dict):
                snap = build_task_plan_dict_from_write_todos_args(inp)
                if snap is not None:
                    task_plan = snap
                    if not workspace_title:
                        workspace_title = str(snap.get("workspaceTitle", "") or "")
        elif t == "task_summary" and ev.get("summary"):
            task_summary = ev.get("summary", "")
        elif t == "conclusion" and ev.get("content"):
            conclusion = ev.get("content", "")
            # Pair with app.parsers.stats_meta.build_task_stats_meta output
            # on the SSE conclusion event — same dict, two consumers
            # (SSE live UI + DB row for reload).
            meta_candidate = ev.get("meta")
            if isinstance(meta_candidate, dict) and meta_candidate.get("taskKind"):
                stats_meta = meta_candidate
        elif t == "understanding":
            understanding = ev
        elif t == "error" and ev.get("detail"):
            error_detail = ev.get("detail", "")
            thinking_steps.append({
                "id": "error",
                "label": ev.get("label", "Error"),
                "status": "error",
                "detail": error_detail,
            })

    has_task_plan = bool(task_plan)
    has_task_summary = bool(task_summary)
    has_conclusion = bool(conclusion)
    has_error = any(s.get("status") == "error" for s in thinking_steps)

    if has_task_plan:
        # Keep chat concise for task-based analyses; details go to workspace blocks.
        content = task_summary or ""
        # Persist streaming reasoning (current_reasoning) so it survives refresh; fallback to understanding.reasoningSummary
        reasoning = (understanding or {}).get("reasoningSummary", "") or current_reasoning or ""
    else:
        content = conclusion or current_reasoning or ""
        reasoning = (understanding or {}).get("reasoningSummary", "") or current_reasoning

    def _analysis_block_from_conclusion(conc: str) -> list[dict]:
        body = strip_leading_preface_before_cjk_report_body(conc.strip())
        return [{
            "type": "analysis",
            "id": "full-analysis",
            "content": body,
            "title": "🔍 Analysis Report" if ui_language == "en" else "🔍 分析报告",
        }]

    # Ensure history can restore workspace content after refresh.
    # Fallback 1: task-based path (existing behavior).
    if has_task_plan and not blocks and isinstance(conclusion, str) and conclusion.strip():
        blocks = _analysis_block_from_conclusion(conclusion)
    # Fallback 2: research route without task_plan/workspace events.
    if (not has_task_plan) and is_research_route and not blocks and isinstance(conclusion, str) and conclusion.strip():
        blocks = _analysis_block_from_conclusion(conclusion)
    # Fallback 3: resume leg with no merged first-leg timeline — user row stays "[HITL resume]".
    # Do not mirror every conclusion-only /analyze turn into workspace (breaks chat replay).
    _resume_placeholder = (user_input or "").strip() == "[HITL resume]"
    if (
        _resume_placeholder
        and not blocks
        and isinstance(conclusion, str)
        and conclusion.strip()
    ):
        blocks = _analysis_block_from_conclusion(conclusion)

    # Dedup: if reasoning and content are substantially same, clear reasoning
    # Skip for task flows when we have streaming reasoning (different purpose from content)
    if reasoning and content and not (has_task_plan and current_reasoning):
        r = reasoning.strip()
        c = content.strip()
        shorter = r if len(r) < len(c) else c
        longer = r if len(r) >= len(c) else c
        if longer.startswith(shorter):
            reasoning = (understanding or {}).get("reasoningSummary", "") or ""

    if not content and has_error:
        content = f"分析失败: {error_detail or '未知错误（请查看后端日志）'}"
    elif not content and understanding:
        u = understanding
        alts = u.get("suggestedAlternatives") or []
        is_out_of_scope = u.get("taskCategory") == "unknown" and len(alts) > 0
        if is_out_of_scope:
            lines = [
                f"{a.get('option', '-')}. {a.get('title', '')}\n{a.get('description', '')}"
                for a in alts
            ]
            content = f"{u.get('summary', '此请求超出系统能力范围。')}\n\n你可以尝试以下方向：\n\n" + "\n\n".join(lines)
        elif u.get("summary"):
            content = u.get("summary", "")
    elif (not content) and thinking_steps and (not blocks) and (not has_task_plan):
        content = "分析过程中断，未能获取完整结果。请重试。"
    elif not content and blocks:
        parts = []
        for b in blocks:
            if b.get("type") == "summary":
                parts.append((b.get("description") or b.get("title") or "").strip())
            elif b.get("type") == "text":
                parts.append((b.get("content") or "").strip())
            elif b.get("type") == "analysis":
                parts.append((b.get("content") or "").strip())
            elif b.get("type") == "log":
                parts.append((b.get("content") or "").strip())
        content = "\n\n".join(p for p in parts if p)

    stream_events = _extract_stream_events(events)
    timeline = _timeline_from_events(events)

    result: dict[str, Any] = {
        "user_input": user_input or "[Attachment-only request]",
        "content": content or "",
        "reasoning": reasoning or "",
        "thinking_steps": thinking_steps,
        "task_plan": task_plan,
        "understanding": understanding,
        "task_summary": task_summary,
        "blocks": blocks,
        "workspace_title": workspace_title,
        "stream_events": stream_events,
        "timeline": timeline,
    }
    if stats_meta is not None:
        result["stats"] = stats_meta
    return result


async def persist_analysis_result(
    project_id: str,
    user_id: str,
    user_input: str,
    events: list[dict],
    request_id: str | None = None,
    ui_language: str = "en",
) -> bool:
    """Persist analysis result to messages table.

    Builds user and assistant messages from events and inserts into DB.
    Returns True on success, False on skip/failure.
    """
    settings = get_settings()
    if settings.database_mode == "memory":
        logger.debug("Skipping persist: database_mode=memory")
        return False

    state = _build_state_from_events(events, user_input, ui_language=ui_language)
    has_content = bool(
        state["content"]
        or state["reasoning"]
        or state["thinking_steps"]
        or state["blocks"]
        or state.get("timeline")
    )
    if not has_content:
        logger.debug("Skipping persist: no meaningful content from events")
        return False

    try:
        ok = False
        if settings.database_mode == "local":
            ok = await _persist_local(project_id, user_id, state, request_id)
        elif settings.database_mode == "supabase":
            ok = await _persist_supabase(project_id, user_id, state, request_id)
        if ok:
            from app.services.context_memory.pipeline import merge_after_message_persist

            await merge_after_message_persist(
                project_id, user_id, request_id, state
            )
        return ok
    except Exception as e:
        logger.error(
            "Failed to persist analysis result",
            project_id=project_id,
            error=str(e),
            exc_info=True,
        )
        return False


def _extended_thinking_steps(state: dict) -> dict:
    """Build extended thinking_steps structure for DB (matches frontend)."""
    return {
        "steps": state["thinking_steps"],
        "__extended": {
            "taskPlan": state.get("task_plan"),
            "understanding": state.get("understanding"),
            "taskSummary": state.get("task_summary"),
            "workspaceTitle": state.get("workspace_title") or None,
            "streamEvents": state.get("stream_events") or [],
        },
    }


async def _persist_local(project_id: str, user_id: str, state: dict, request_id: str | None) -> bool:
    from uuid import uuid4

    pool = await get_pg_pool()
    async with pool.acquire() as conn:
        project = await conn.fetchrow(
            "SELECT id FROM projects WHERE id = $1 AND user_id = $2",
            project_id, user_id
        )
        if not project:
            logger.warning("Project not found or access denied", project_id=project_id)
            return False

        msg_count_before = await conn.fetchval(
            "SELECT COUNT(*) FROM messages WHERE project_id = $1",
            project_id
        )
        is_first = msg_count_before == 0

        user_msg_id = str(uuid4())
        assistant_msg_id = str(uuid4())
        thinking_val = _extended_thinking_steps(state)
        blocks_val = state.get("blocks") or []

        await conn.execute(
            """
            INSERT INTO messages (id, project_id, user_id, type, content, reasoning, thinking_steps, blocks, request_id)
            VALUES ($1, $2, $3, $4, $5, $6, $7::jsonb, $8::jsonb, $9)
            ON CONFLICT (project_id, request_id, type)
            DO UPDATE SET
                content = EXCLUDED.content,
                reasoning = EXCLUDED.reasoning,
                thinking_steps = EXCLUDED.thinking_steps,
                blocks = EXCLUDED.blocks
            """,
            user_msg_id,
            project_id,
            user_id,
            "user",
            state["user_input"],
            None,
            None,
            None,
            request_id,
        )
        timeline_val = state.get("timeline") or []
        # TaskStatsMeta (from SSE conclusion.meta) — survives refresh so the
        # stats bar renders on historical turns, not just the live session.
        stats_val = state.get("stats")
        stats_json = json.dumps(stats_val) if stats_val else None
        await conn.execute(
            """
            INSERT INTO messages (id, project_id, user_id, type, content, reasoning, thinking_steps, blocks, request_id, workspace_title, timeline, stats)
            VALUES ($1, $2, $3, $4, $5, $6, $7::jsonb, $8::jsonb, $9, $10, $11::jsonb, $12::jsonb)
            ON CONFLICT (project_id, request_id, type)
            DO UPDATE SET
                content = EXCLUDED.content,
                reasoning = EXCLUDED.reasoning,
                thinking_steps = EXCLUDED.thinking_steps,
                blocks = EXCLUDED.blocks,
                workspace_title = EXCLUDED.workspace_title,
                timeline = EXCLUDED.timeline,
                stats = EXCLUDED.stats
            """,
            assistant_msg_id,
            project_id,
            user_id,
            "assistant",
            state["content"],
            state["reasoning"],
            json.dumps(thinking_val),
            json.dumps(blocks_val),
            request_id,
            state.get("workspace_title") or None,
            json.dumps(timeline_val),
            stats_json,
        )
        await conn.execute(
            "UPDATE projects SET updated_at = now() WHERE id = $1",
            project_id
        )
        if is_first:
            new_title = (state["user_input"] or "")[:30] + ("..." if len(state["user_input"] or "") > 30 else "")
            await conn.execute(
                "UPDATE projects SET title = $1 WHERE id = $2",
                new_title, project_id
            )
    logger.info("Persisted analysis result", project_id=project_id)
    return True


async def _persist_supabase(project_id: str, user_id: str, state: dict, request_id: str | None) -> bool:
    from app.datetime_support import format_api_datetime, now_app

    client = get_supabase_client()
    project_result = client.table("projects").select("id").eq("id", project_id).eq("user_id", user_id).execute()
    if not project_result.data:
        logger.warning("Project not found or access denied", project_id=project_id)
        return False

    thinking_val = _extended_thinking_steps(state)
    blocks_val = state.get("blocks") or []

    client.table("messages").upsert({
        "project_id": project_id,
        "user_id": user_id,
        "type": "user",
        "content": state["user_input"],
        "reasoning": None,
        "thinking_steps": None,
        "blocks": None,
        "request_id": request_id,
    }, on_conflict="project_id,request_id,type").execute()

    stats_val = state.get("stats") or None
    client.table("messages").upsert({
        "project_id": project_id,
        "user_id": user_id,
        "type": "assistant",
        "content": state["content"],
        "reasoning": state["reasoning"],
        "thinking_steps": thinking_val,
        "blocks": blocks_val,
        "request_id": request_id,
        "workspace_title": state.get("workspace_title") or None,
        "timeline": state.get("timeline") or [],
        "stats": stats_val,
    }, on_conflict="project_id,request_id,type").execute()

    client.table("projects").update({
        "updated_at": format_api_datetime(now_app())
    }).eq("id", project_id).execute()

    msg_result = client.table("messages").select("id").eq("project_id", project_id).execute()
    if len(msg_result.data) == 2:
        new_title = (state["user_input"] or "")[:30] + ("..." if len(state["user_input"] or "") > 30 else "")
        client.table("projects").update({"title": new_title}).eq("id", project_id).execute()

    logger.info("Persisted analysis result", project_id=project_id)
    return True
