"""Project analysis progress persistence for refresh recovery.

Writes/updates project_analysis_progress during streaming so the frontend
can restore UI state after a page refresh.
"""

import copy
import json
import time
from typing import Any

import structlog
from app.config import get_settings
from app.db import get_pg_pool, get_supabase_client
from app.services.message_persistence import _timeline_from_events
from app.parsers.write_todos_plan import build_task_plan_dict_from_write_todos_args

logger = structlog.get_logger()


def _apply_task_lifecycle(task_plan: dict | None, events: list[dict]) -> dict | None:
    """Apply task_start/task_complete/task_step/task_error/plan_complete to task_plan."""
    if task_plan is None:
        return None

    tasks: list[dict] = task_plan.get("tasks") or []
    tasks_by_id = {t.get("id"): t for t in tasks}
    current_task_id: str | None = None

    for ev in events:
        t = ev.get("type")
        eid = ev.get("id", "")

        if t == "task_start" and eid in tasks_by_id:
            tasks_by_id[eid]["status"] = "running"
            current_task_id = eid

        elif t == "task_complete" and eid in tasks_by_id:
            tasks_by_id[eid]["status"] = "success"
            if ev.get("task") and isinstance(ev["task"], dict):
                tasks_by_id[eid]["result"] = ev["task"].get("result")
                tasks_by_id[eid]["durationMs"] = ev["task"].get("durationMs", 0)
            current_task_id = None

        elif t == "task_error" and eid in tasks_by_id:
            tasks_by_id[eid]["status"] = "error"
            tasks_by_id[eid]["error"] = ev.get("detail", "")
            current_task_id = None

        elif t == "task_step":
            task_id = ev.get("taskId", "")
            step = ev.get("step")
            if task_id in tasks_by_id and step:
                existing_steps = tasks_by_id[task_id].get("steps") or []
                step_ids = {s.get("id") for s in existing_steps}
                if step.get("id") not in step_ids:
                    existing_steps.append(step)
                else:
                    existing_steps = [
                        step if s.get("id") == step.get("id") else s
                        for s in existing_steps
                    ]
                tasks_by_id[task_id]["steps"] = existing_steps

        elif t == "plan_complete" and ev.get("plan"):
            incoming = ev["plan"]
            task_plan = {**task_plan, **incoming}
            task_plan["tasks"] = tasks
            task_plan["status"] = incoming.get("status", task_plan.get("status"))

    has_running = any(tk.get("status") == "running" for tk in tasks)
    all_done = all(tk.get("status") in ("success", "error") for tk in tasks) and len(tasks) > 0
    if all_done:
        task_plan["status"] = "success"
    elif has_running:
        task_plan["status"] = "running"

    task_plan["tasks"] = tasks
    task_plan["currentTaskId"] = current_task_id
    return task_plan


def _state_from_events(events: list[dict]) -> dict[str, Any]:
    """Extract progress state from events (same logic as message_persistence)."""
    thinking_steps: list[dict] = []
    task_plan: dict | None = None
    task_summary = ""
    conclusion = ""
    understanding: dict | None = None
    blocks: list[dict] = []
    error_detail = ""

    for ev in events:
        t = ev.get("type")
        if t == "step":
            thinking_steps.append({
                "id": ev.get("id", ""),
                "label": ev.get("label", ""),
                "status": ev.get("status", "running"),
                "detail": ev.get("detail"),
            })
        elif t == "task_plan" and ev.get("plan"):
            task_plan = ev.get("plan")
        elif t == "tool_call" and ev.get("toolName") == "write_todos":
            inp = ev.get("toolInput")
            if isinstance(inp, dict):
                snap = build_task_plan_dict_from_write_todos_args(inp)
                if snap is not None:
                    task_plan = snap
        elif t == "task_summary" and ev.get("summary"):
            task_summary = ev.get("summary", "")
        elif t == "conclusion" and ev.get("content"):
            conclusion = ev.get("content", "")
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

    task_plan = _apply_task_lifecycle(task_plan, events)

    return {
        "thinking_steps": thinking_steps,
        "task_plan": task_plan,
        "understanding": understanding,
        "task_summary": task_summary,
        "conclusion": conclusion,
        "blocks": blocks,
        "error_detail": error_detail,
        # Same filter as final message persistence — enables ReAct/timeline UI after refresh.
        "timeline": _timeline_from_events(events),
    }


def build_parameter_response_timeline_event(
    resume: Any,
    *,
    timestamp_ms: int | None = None,
) -> dict[str, Any] | None:
    """Build a user-visible timeline row for HITL parameter replies (DB replay after refresh).

    Skips pure decision resumes (``{decisions: [...]}`` only) so we do not store tool payloads twice.
    """
    if not isinstance(resume, dict):
        return None
    # Decision-only HITL resumes: no form fields to persist in timeline.
    if set(resume.keys()) <= {"decisions", "requestId"} and "decisions" in resume:
        return None

    parameters: dict[str, str] = {}
    for key, val in resume.items():
        if val is None:
            continue
        if isinstance(val, str):
            parameters[str(key)] = val
        elif isinstance(val, (dict, list)):
            parameters[str(key)] = json.dumps(val, ensure_ascii=False)
        else:
            parameters[str(key)] = str(val)

    if not parameters:
        return None

    ts = int(timestamp_ms if timestamp_ms is not None else time.time() * 1000)
    return {
        "type": "parameter_response",
        "id": "hitl-parameter-response",
        "timestamp": ts,
        "parameters": parameters,
    }


def build_decision_response_timeline_event(
    *,
    decision_ui_id: str | None,
    selected_options: list[str] | None,
    timestamp_ms: int | None = None,
) -> dict[str, Any] | None:
    """Build a timeline row when the user chose HITL options (separate from LangGraph ``resume`` body)."""
    uid = (decision_ui_id or "").strip()
    opts = [str(x) for x in (selected_options or []) if x is not None and str(x).strip() != ""]
    if not uid or not opts:
        return None
    ts = int(timestamp_ms if timestamp_ms is not None else time.time() * 1000)
    return {
        "type": "decision_response",
        "id": "hitl-decision-response",
        "timestamp": ts,
        "decisionUiId": uid,
        "selectedOptions": opts,
    }


def merge_resume_progress_state(
    base: dict[str, Any] | None,
    collected_events: list[dict],
) -> dict[str, Any]:
    """Merge first-leg progress (``base``) with resume-leg SSE events for upsert_progress.

    Without this, POST /analyze/resume would overwrite ``timeline`` / ``task_plan`` with only
    the resume stream, dropping the pre-interrupt analysis from ``project_analysis_progress``.
    """
    base = base or {}
    tail = _state_from_events(collected_events)

    base_tl = base.get("timeline") if isinstance(base.get("timeline"), list) else []
    tail_tl = tail.get("timeline") if isinstance(tail.get("timeline"), list) else []
    merged_tl = list(base_tl) + list(tail_tl)

    base_ts = base.get("thinking_steps") if isinstance(base.get("thinking_steps"), list) else []
    tail_ts = tail.get("thinking_steps") if isinstance(tail.get("thinking_steps"), list) else []
    seen_ids = {s.get("id") for s in base_ts if isinstance(s, dict)}
    merged_ts = list(base_ts) + [
        s for s in tail_ts if isinstance(s, dict) and s.get("id") not in seen_ids
    ]

    base_plan = base.get("task_plan")
    merged_plan: dict | None = None
    if isinstance(base_plan, dict) and base_plan:
        merged_plan = _apply_task_lifecycle(copy.deepcopy(base_plan), collected_events)
    elif isinstance(tail.get("task_plan"), dict) and tail.get("task_plan"):
        merged_plan = tail.get("task_plan")
    elif isinstance(base_plan, dict):
        merged_plan = base_plan

    understanding = tail.get("understanding")
    if understanding is None:
        understanding = base.get("understanding")

    task_summary = (tail.get("task_summary") or base.get("task_summary") or "") or ""
    conclusion = (tail.get("conclusion") or base.get("conclusion") or "") or ""

    tail_blocks = tail.get("blocks") if isinstance(tail.get("blocks"), list) else []
    base_blocks = base.get("blocks") if isinstance(base.get("blocks"), list) else []
    merged_blocks = tail_blocks if tail_blocks else base_blocks

    error_detail = (tail.get("error_detail") or base.get("error_detail") or "") or ""

    return {
        "thinking_steps": merged_ts,
        "task_plan": merged_plan,
        "understanding": understanding,
        "task_summary": task_summary,
        "conclusion": conclusion,
        "blocks": merged_blocks,
        "error_detail": error_detail,
        "timeline": merged_tl,
    }


def _parse_progress_row_for_merge(row: dict[str, Any]) -> dict[str, Any]:
    """Normalize a progress DB row into merge_resume_progress_state ``base`` shape.

    Also includes ``user_input`` and ``request_id`` so callers (e.g. resume
    persist) can access the original values from the first-leg progress row.
    """

    def _json_field(val: Any, default: Any) -> Any:
        if val is None:
            return default
        if isinstance(val, (list, dict)):
            return val
        if isinstance(val, str):
            s = val.strip()
            if not s:
                return default
            return json.loads(s)
        return default

    raw_timeline = row.get("timeline")
    if raw_timeline is None:
        timeline_parsed: list = []
    elif isinstance(raw_timeline, str):
        timeline_parsed = json.loads(raw_timeline) if raw_timeline.strip() else []
    elif isinstance(raw_timeline, list):
        timeline_parsed = list(raw_timeline)
    else:
        timeline_parsed = []

    return {
        "thinking_steps": _json_field(row.get("thinking_steps"), []) or [],
        "task_plan": _json_field(row.get("task_plan"), None),
        "understanding": _json_field(row.get("understanding"), None),
        "task_summary": row.get("task_summary") or "",
        "conclusion": row.get("conclusion") or "",
        "blocks": _json_field(row.get("blocks"), []) or [],
        "error_detail": row.get("error_detail") or "",
        "timeline": timeline_parsed,
        "user_input": row.get("user_input") or "",
        "request_id": row.get("request_id") or "",
    }


async def fetch_running_progress_for_merge(project_id: str, user_id: str) -> dict[str, Any] | None:
    """Load current running progress row for resume merge (verifies project ownership)."""
    settings = get_settings()
    if settings.database_mode == "memory":
        return None

    try:
        if settings.database_mode == "local":
            pool = await get_pg_pool()
            async with pool.acquire() as conn:
                project = await conn.fetchrow(
                    "SELECT id FROM projects WHERE id = $1 AND user_id = $2",
                    project_id,
                    user_id,
                )
                if not project:
                    return None
                row = await conn.fetchrow(
                    """
                    SELECT thinking_steps, task_plan, understanding, task_summary,
                           conclusion, blocks, error_detail, timeline,
                           user_input, request_id
                    FROM project_analysis_progress
                    WHERE project_id = $1 AND status = 'running'
                    """,
                    project_id,
                )
                if not row:
                    return None
                return _parse_progress_row_for_merge(dict(row))

        if settings.database_mode == "supabase":
            client = get_supabase_client()
            pr = (
                client.table("projects")
                .select("id")
                .eq("id", project_id)
                .eq("user_id", user_id)
                .execute()
            )
            if not pr.data:
                return None
            res = (
                client.table("project_analysis_progress")
                .select(
                    "thinking_steps, task_plan, understanding, task_summary, "
                    "conclusion, blocks, error_detail, timeline, user_input, request_id"
                )
                .eq("project_id", project_id)
                .eq("status", "running")
                .execute()
            )
            if not res.data:
                return None
            return _parse_progress_row_for_merge(res.data[0])
    except Exception as e:
        logger.warning(
            "fetch_running_progress_for_merge failed",
            project_id=project_id,
            error=str(e),
        )
        return None

    return None


async def upsert_progress(
    project_id: str,
    user_id: str,
    request_id: str,
    status: str = "running",
    user_input: str = "",
    ui_language: str | None = None,
    **state: Any,
) -> None:
    """Insert or update project_analysis_progress row."""
    settings = get_settings()
    if settings.database_mode == "memory":
        return

    thinking_steps = state.get("thinking_steps") or []
    task_plan = state.get("task_plan")
    understanding = state.get("understanding")
    task_summary = state.get("task_summary", "")
    conclusion = state.get("conclusion", "")
    blocks = state.get("blocks") or []
    error_detail = state.get("error_detail", "")
    timeline = state.get("timeline") if isinstance(state.get("timeline"), list) else []

    try:
        if settings.database_mode == "local":
            await _upsert_local(
                project_id, user_id, request_id, status, user_input,
                thinking_steps, task_plan, understanding, task_summary,
                conclusion, blocks, error_detail, timeline, ui_language,
            )
        elif settings.database_mode == "supabase":
            await _upsert_supabase(
                project_id, user_id, request_id, status, user_input,
                thinking_steps, task_plan, understanding, task_summary,
                conclusion, blocks, error_detail, timeline, ui_language,
            )
    except Exception as e:
        logger.warning(
            "Failed to upsert progress", project_id=project_id, error=str(e)
        )


async def _upsert_local(
    project_id: str,
    user_id: str,
    request_id: str,
    status: str,
    user_input: str,
    thinking_steps: list,
    task_plan: dict | None,
    understanding: dict | None,
    task_summary: str,
    conclusion: str,
    blocks: list,
    error_detail: str,
    timeline: list,
    ui_language: str | None,
) -> None:
    """Upsert for local PostgreSQL."""
    pool = await get_pg_pool()
    async with pool.acquire() as conn:
        await conn.execute(
            """
            INSERT INTO project_analysis_progress
            (project_id, user_id, request_id, status, user_input, thinking_steps,
             task_plan, understanding, task_summary, conclusion, blocks,
             error_detail, timeline, ui_language, updated_at)
            VALUES ($1, $2, $3, $4, $5, $6::jsonb, $7::jsonb, $8::jsonb,
                    $9, $10, $11::jsonb, $12, $13::jsonb, $14, now())
            ON CONFLICT (project_id) DO UPDATE SET
                status = EXCLUDED.status,
                user_input = EXCLUDED.user_input,
                thinking_steps = EXCLUDED.thinking_steps,
                task_plan = EXCLUDED.task_plan,
                understanding = EXCLUDED.understanding,
                task_summary = EXCLUDED.task_summary,
                conclusion = EXCLUDED.conclusion,
                blocks = EXCLUDED.blocks,
                error_detail = EXCLUDED.error_detail,
                timeline = EXCLUDED.timeline,
                ui_language = EXCLUDED.ui_language,
                updated_at = now()
            """,
            project_id,
            user_id,
            request_id,
            status,
            user_input,
            json.dumps(thinking_steps),
            json.dumps(task_plan) if task_plan else None,
            json.dumps(understanding) if understanding else None,
            task_summary,
            conclusion,
            json.dumps(blocks),
            error_detail or None,
            json.dumps(timeline),
            ui_language,
        )


async def _upsert_supabase(
    project_id: str,
    user_id: str,
    request_id: str,
    status: str,
    user_input: str,
    thinking_steps: list,
    task_plan: dict | None,
    understanding: dict | None,
    task_summary: str,
    conclusion: str,
    blocks: list,
    error_detail: str,
    timeline: list,
    ui_language: str | None,
) -> None:
    """Upsert for Supabase."""
    from app.datetime_support import format_api_datetime, now_app

    client = get_supabase_client()
    now = format_api_datetime(now_app())
    row = {
        "project_id": project_id,
        "user_id": user_id,
        "request_id": request_id,
        "status": status,
        "user_input": user_input,
        "thinking_steps": thinking_steps,
        "task_plan": task_plan,
        "understanding": understanding,
        "task_summary": task_summary,
        "conclusion": conclusion,
        "blocks": blocks,
        "error_detail": error_detail or None,
        "timeline": timeline,
        "ui_language": ui_language,
        "updated_at": now,
    }
    client.table("project_analysis_progress").upsert(
        row, on_conflict="project_id"
    ).execute()


async def clear_progress(project_id: str) -> None:
    """Clear progress row when task completes.

    Two-phase approach: first UPDATE status to 'completed', then DELETE.
    The frontend query filters ``WHERE status = 'running'``, so even if
    DELETE fails the row will no longer be returned and the UI won't be
    stuck in an infinite polling loop.
    """
    settings = get_settings()
    if settings.database_mode == "memory":
        return

    # Phase 1: mark completed (safe against DELETE failure)
    try:
        if settings.database_mode == "local":
            pool = await get_pg_pool()
            async with pool.acquire() as conn:
                await conn.execute(
                    "UPDATE project_analysis_progress SET status = 'completed', updated_at = now() WHERE project_id = $1",
                    project_id,
                )
        elif settings.database_mode == "supabase":
            client = get_supabase_client()
            client.table("project_analysis_progress").update(
                {"status": "completed"}
            ).eq("project_id", project_id).execute()
    except Exception as e:
        logger.warning("Failed to mark progress completed", project_id=project_id, error=str(e))

    # Phase 2: delete the row (best-effort cleanup)
    try:
        if settings.database_mode == "local":
            pool = await get_pg_pool()
            async with pool.acquire() as conn:
                await conn.execute(
                    "DELETE FROM project_analysis_progress WHERE project_id = $1",
                    project_id,
                )
        elif settings.database_mode == "supabase":
            client = get_supabase_client()
            client.table("project_analysis_progress").delete().eq(
                "project_id", project_id
            ).execute()
    except Exception as e:
        logger.warning("Failed to delete progress row (status already completed)", project_id=project_id, error=str(e))
