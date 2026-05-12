"""Execute node3 (soc_solve_v1) plans via generic actions with full auth + API path.

Reuses ``execute_generic_action`` so behavior matches the former LLM node4 path:
DB / ephemeral credentials, LangGraph ``interrupt`` for HITL when missing, optional
persist on ``remember_auth``, then vendor tool handlers (Splunk runtime override, etc.).

Important: ``VendorAuthService.resolve_or_request_credentials`` uses LangGraph
``interrupt``. Call ``execute_solve_plan`` only from a graph node / tool path where
interrupts are supported (same as existing SOC tools). With DB or ephemeral auth
already populated, no interrupt is emitted.
"""

from __future__ import annotations

import asyncio
import json
import re
from datetime import UTC, datetime
from pathlib import Path
from collections.abc import Awaitable, Callable
from typing import Any, TypeAlias

import structlog
try:
    from langgraph.errors import GraphBubbleUp
except Exception:  # pragma: no cover - defensive fallback for import-time env issues
    class GraphBubbleUp(Exception):  # type: ignore[no-redef]
        """Fallback shim when langgraph.errors is unavailable."""
        pass

from subagents.official.soc_alert.tools.soc_alert.action_adaptor.resolver import (
    GenericActionResolveError,
    execute_generic_action as default_execute_generic_action,
    generic_action_requires_vendor,
)

logger = structlog.get_logger()

SOC_SOLVE_SCHEMA_VERSION = "soc_solve_v1"
SOC_EXECUTION_SCHEMA_VERSION = "soc_execution_v1"

ExecuteGenericAction: TypeAlias = Callable[..., Awaitable[dict[str, Any]]]
class SolvePlanValidationError(ValueError):
    """Raised when node3 JSON does not match the machine contract."""


_FENCE_RE = re.compile(r"^\s*```(?:json)?\s*", re.IGNORECASE)


def unwrap_nested_soc_solve_plan(data: dict[str, Any]) -> dict[str, Any]:
    """Use inner ``soc_solve_v1`` when the model nests it under ``solve_plan``.

    Tool args often look like ``{"solve_plan": {"schema_version": ..., "tasks": [...]}}``.
    If we only validated the outer dict, ``tasks`` would be missing and the executor
    would run zero items while the UI still shows ``query_*`` inside the nested JSON.
    """
    inner = data.get("solve_plan")
    if not isinstance(inner, dict):
        return data
    inner_tasks = inner.get("tasks")
    if not isinstance(inner_tasks, list) or not inner_tasks:
        return data
    outer_tasks = data.get("tasks")
    if isinstance(outer_tasks, list) and len(outer_tasks) > 0:
        return data
    logger.info(
        "soc_solve_plan_unwrapped_from_solve_plan_key",
        inner_task_count=len(inner_tasks),
    )
    return inner


def parse_solve_plan_text(raw: str) -> dict[str, Any]:
    """Parse model output: strip optional markdown fences, then ``json.loads``."""
    text = (raw or "").strip()
    if not text:
        raise SolvePlanValidationError("empty solve plan text")
    text = _FENCE_RE.sub("", text, count=1)
    text = re.sub(r"\s*```\s*$", "", text, count=1).strip()
    try:
        data = json.loads(text)
    except json.JSONDecodeError as exc:
        raise SolvePlanValidationError(f"invalid JSON: {exc}") from exc
    if not isinstance(data, dict):
        raise SolvePlanValidationError("solve plan root must be a JSON object")
    return data


def normalize_solve_plan(data: dict[str, Any]) -> dict[str, Any]:
    """Validate ``soc_solve_v1`` shape; return the same dict if valid."""
    # Backward compatibility: some node3 outputs may omit schema_version while
    # still matching the soc_solve_v1 shape. Auto-fill here instead of failing
    # fast, then keep strict validation for mismatched non-empty versions.
    schema_version = data.get("schema_version")
    if schema_version is None:
        data["schema_version"] = SOC_SOLVE_SCHEMA_VERSION
        schema_version = SOC_SOLVE_SCHEMA_VERSION
        logger.warning(
            "soc_solve_plan_schema_version_missing_autofilled",
            expected=SOC_SOLVE_SCHEMA_VERSION,
        )
    if schema_version != SOC_SOLVE_SCHEMA_VERSION:
        raise SolvePlanValidationError(
            f"schema_version must be {SOC_SOLVE_SCHEMA_VERSION!r}, "
            f"got {schema_version!r}"
        )
    tasks = data.get("tasks")
    if tasks is None:
        data["tasks"] = []
        tasks = data["tasks"]
        logger.warning("soc_solve_plan_tasks_missing_autofilled_empty")
    if not isinstance(tasks, list):
        raise SolvePlanValidationError("tasks must be a JSON array")
    if not tasks:
        logger.warning("soc_solve_plan_tasks_empty")
        return data

    seen_ids: set[str] = set()
    for ti, task in enumerate(tasks):
        if not isinstance(task, dict):
            raise SolvePlanValidationError(f"tasks[{ti}] must be an object")
        for key in ("action_id", "action_title"):
            if key not in task or not isinstance(task[key], str) or not task[key].strip():
                raise SolvePlanValidationError(f"tasks[{ti}].{key} must be a non-empty string")
        subs = task.get("sub_questions")
        if not isinstance(subs, list) or not subs:
            raise SolvePlanValidationError(f"tasks[{ti}].sub_questions must be a non-empty array")
        for si, sq in enumerate(subs):
            if not isinstance(sq, dict):
                raise SolvePlanValidationError(f"tasks[{ti}].sub_questions[{si}] must be an object")
            _validate_sub_question(ti, si, sq, seen_ids)
    return data


def _validate_sub_question(task_idx: int, sub_idx: int, sq: dict[str, Any], seen_ids: set[str]) -> None:
    prefix = f"tasks[{task_idx}].sub_questions[{sub_idx}]"
    sid = sq.get("id")
    if not isinstance(sid, str) or not sid.strip():
        raise SolvePlanValidationError(f"{prefix}.id must be a non-empty string")
    if sid in seen_ids:
        raise SolvePlanValidationError(f"duplicate sub_question id: {sid!r}")
    seen_ids.add(sid)

    if not isinstance(sq.get("question"), str):
        raise SolvePlanValidationError(f"{prefix}.question must be a string")

    ga = sq.get("generic_action")
    if ga is not None and (not isinstance(ga, str) or not ga.strip()):
        raise SolvePlanValidationError(
            f"{prefix}.generic_action must be JSON null or a non-empty string"
        )
    params = sq.get("action_params")
    if not isinstance(params, dict):
        raise SolvePlanValidationError(f"{prefix}.action_params must be a JSON object")

    vr = sq.get("vendor_routing")
    if ga is None:
        if vr is not None:
            raise SolvePlanValidationError(
                f"{prefix}.vendor_routing must be JSON null when generic_action is null"
            )
    else:
        if generic_action_requires_vendor(str(ga)):
            if not isinstance(vr, dict):
                raise SolvePlanValidationError(
                    f"{prefix}.vendor_routing must be an object when generic_action is set"
                )
            prov = vr.get("provider")
            if not isinstance(prov, str) or not prov.strip():
                raise SolvePlanValidationError(
                    f"{prefix}.vendor_routing.provider must be a non-empty string"
                )
        elif vr is not None and not isinstance(vr, dict):
            raise SolvePlanValidationError(
                f"{prefix}.vendor_routing must be JSON null or an object"
            )

    ar = sq.get("action_reason")
    if ar is not None and not isinstance(ar, str):
        raise SolvePlanValidationError(f"{prefix}.action_reason must be a string or omitted")


def _truncate_value(obj: Any, max_chars: int | None) -> Any:
    if max_chars is None or max_chars <= 0:
        return obj
    text = json.dumps(obj, ensure_ascii=False, default=str)
    if len(text) <= max_chars:
        return obj
    return {
        "_truncated": True,
        "preview": text[: max_chars - 80] + "…",
        "original_char_len": len(text),
    }


def _extract_result_error(result: Any) -> str | None:
    """Return a human-readable error if tool result payload indicates failure."""
    if not isinstance(result, dict):
        return None
    raw_error = result.get("error")
    if isinstance(raw_error, str) and raw_error.strip():
        return raw_error.strip()
    if result.get("error_kind") is not None:
        return str(result.get("error_kind"))
    if result.get("ok") is False:
        return "Tool result marked as not ok"
    return None


def _append_jsonl(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(payload, ensure_ascii=False, default=str, indent=2))
        fh.write("\n\n")


def _write_pretty_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(payload, ensure_ascii=False, default=str, indent=2),
        encoding="utf-8",
    )


def _build_default_execution_log_path(
    *,
    request_id: str | None = None,
    session_id: str | None = None,
) -> Path:
    ts = datetime.now(UTC).strftime("%Y%m%d-%H%M%S-%f")
    rid = (request_id or "").strip() or "no-request-id"
    sid = (session_id or "").strip() or "no-session-id"
    safe_rid = re.sub(r"[^A-Za-z0-9._-]+", "_", rid)
    safe_sid = re.sub(r"[^A-Za-z0-9._-]+", "_", sid)
    filename = f"{ts}_soc_exec_{safe_rid}_{safe_sid}.jsonl"
    service_root = Path(__file__).resolve().parents[6]
    return service_root / "logs" / filename


async def execute_solve_plan(
    plan: dict[str, Any] | str,
    *,
    raw_alert_context: dict[str, Any] | None = None,
    session_id: str | None = None,
    request_id: str | None = None,
    user_id: str | None = None,
    result_max_chars: int | None = 120_000,
    max_parallel: int = 8,
    execution_log_path: str | None = None,
    execute_generic_action: ExecuteGenericAction | None = None,
) -> dict[str, Any]:
    """Run every sub-question in order; auth and HTTP run inside ``execute_generic_action``.

    Args:
        plan: Parsed ``soc_solve_v1`` object or raw JSON string (fences tolerated).
        raw_alert_context: Passed through for param autofill and auth scope derivation.
        session_id / request_id / user_id: Auth scope (same semantics as tools).
        result_max_chars: Bound serialized tool output per item (None = no bound).
        execute_generic_action: Override for tests; defaults to adaptor implementation.

    Returns:
        ``soc_execution_v1`` document suitable as ``execution_result`` for node5.
    """
    exec_fn = execute_generic_action or default_execute_generic_action
    original_plan_input: dict[str, Any] | str = plan
    if isinstance(plan, str):
        plan = parse_solve_plan_text(plan)
    if isinstance(plan, dict):
        plan = unwrap_nested_soc_solve_plan(plan)
    try:
        normalize_solve_plan(plan)
    except SolvePlanValidationError as exc:
        # Per-item logs and the JSONL plan snapshot run only after validation passes;
        # log here so operators still see the failure reason in structured logs.
        logger.warning(
            "soc_solve_plan_validation_failed",
            error=str(exc),
            request_id=request_id,
            session_id=session_id,
            user_id=user_id,
            plan_preview=_truncate_value(plan, 8_000) if isinstance(plan, dict) else None,
        )
        raise

    items_by_index: dict[int, dict[str, Any]] = {}
    success_count = 0
    failed_count = 0
    skipped_count = 0
    log_lock = asyncio.Lock()
    log_path = (
        Path(execution_log_path)
        if execution_log_path
        else _build_default_execution_log_path(request_id=request_id, session_id=session_id)
    )
    semaphore = asyncio.Semaphore(max(1, int(max_parallel)))
    async def _append_execution_log(entry: dict[str, Any]) -> None:
        async with log_lock:
            await asyncio.to_thread(_append_jsonl, log_path, entry)

    # Log the node3 solve-plan snapshot first, so readers can inspect what the
    # executor actually received before per-item execution starts.
    await _append_execution_log(
        {
            "ts": datetime.now(UTC).isoformat(),
            "schema_version": "soc_exec_plan_input_v1",
            "request_id": request_id,
            "session_id": session_id,
            "user_id": user_id,
            "input_format": "json_string" if isinstance(original_plan_input, str) else "json_object",
            "node3_output_original": _truncate_value(original_plan_input, result_max_chars),
            "node3_output_effective": _truncate_value(plan, result_max_chars),
            "node3_task_count": len(plan.get("tasks", [])) if isinstance(plan, dict) else 0,
        }
    )

    def _build_item_log_entry(
        *,
        node3_tool_name: str | None,
        ts: str,
        status: str,
        request: dict[str, Any],
        api_response: Any = None,
        api_request: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        entry: dict[str, Any] = {
            "node3_tool_name": node3_tool_name,
            "ts": ts,
            "schema_version": "soc_exec_item_log_v1",
            "status": status,
            "request": request,
            "api_request": api_request,
            "api_response": api_response,
        }
        return entry

    async def _run_one(
        *,
        item_index: int,
        action_id: str,
        action_title: str,
        sq: dict[str, Any],
    ) -> tuple[int, dict[str, Any], str]:
        sid = str(sq["id"])
        question = str(sq.get("question", ""))
        ga = sq.get("generic_action")
        base_item: dict[str, Any] = {
            "id": sid,
            "action_id": action_id,
            "action_title": action_title,
            "question": question,
            "generic_action": ga,
        }

        if ga is None:
            item = {
                **base_item,
                "status": "skipped",
                "action_reason": sq.get("action_reason"),
            }
            await _append_execution_log(
                _build_item_log_entry(
                    node3_tool_name=str(ga) if ga is not None else None,
                    ts=datetime.now(UTC).isoformat(),
                    status="skipped",
                    request={
                        "id": sid,
                        "action_id": action_id,
                        "action_title": action_title,
                        "question": question,
                        "node3_tool_name": ga,
                        "node3_tool_params": sq.get("action_params"),
                        "generic_action": ga,
                        "action_params": sq.get("action_params"),
                        "vendor_routing": sq.get("vendor_routing"),
                        "session_id": session_id,
                        "request_id": request_id,
                        "user_id": user_id,
                    },
                    api_response=item,
                )
            )
            return item_index, item, "skipped"

        vendor_routing = sq.get("vendor_routing") or {}
        vendor = str((vendor_routing or {}).get("provider") or "").strip()
        action_params = sq.get("action_params") if isinstance(sq.get("action_params"), dict) else {}
        request_payload = {
            "id": sid,
            "action_id": action_id,
            "action_title": action_title,
            "question": question,
            "node3_tool_name": str(ga),
            "node3_tool_params": action_params,
            "generic_action": str(ga),
            "action_params": action_params,
            "vendor_routing": vendor_routing if isinstance(vendor_routing, dict) else None,
            "session_id": session_id,
            "request_id": request_id,
            "user_id": user_id,
        }
        logger.info(
            "soc_solve_plan_execute_item",
            sub_question_id=sid,
            vendor=vendor,
            generic_action=ga,
        )

        async with semaphore:
            try:
                out = await exec_fn(
                    vendor=vendor,
                    generic_action=str(ga),
                    action_params=action_params,
                    raw_alert_context=raw_alert_context,
                    vendor_routing=vendor_routing if isinstance(vendor_routing, dict) else None,
                    session_id=session_id,
                    request_id=request_id,
                    user_id=user_id,
                )
                api_response = out.get("result")
                api_request = None
                if isinstance(out.get("result"), dict):
                    req = out["result"].get("request")
                    if isinstance(req, dict):
                        api_request = req
                result_error = _extract_result_error(api_response)
                if result_error:
                    item = {
                        **base_item,
                        "status": "failed",
                        "action_reason": sq.get("action_reason"),
                        "error": result_error,
                        "resolved": out.get("resolved"),
                        "result": _truncate_value(out.get("result"), result_max_chars),
                    }
                    await _append_execution_log(
                        _build_item_log_entry(
                            node3_tool_name=str(ga),
                            ts=datetime.now(UTC).isoformat(),
                            status="failed",
                            request=request_payload,
                            api_response=api_response,
                            api_request=api_request,
                        )
                    )
                    return item_index, item, "failed"
                item = {
                    **base_item,
                    "status": "success",
                    "action_reason": sq.get("action_reason"),
                    "resolved": out.get("resolved"),
                    "result": _truncate_value(out.get("result"), result_max_chars),
                }
                await _append_execution_log(
                    _build_item_log_entry(
                        node3_tool_name=str(ga),
                        ts=datetime.now(UTC).isoformat(),
                        status="success",
                        request=request_payload,
                        api_response=api_response,
                        api_request=api_request,
                    )
                )
                return item_index, item, "success"
            except GraphBubbleUp as exc:
                logger.info(
                    "soc_solve_plan_execute_interrupt_bubble_up",
                    sub_question_id=sid,
                    error=str(exc),
                )
                await _append_execution_log(
                    _build_item_log_entry(
                        node3_tool_name=str(ga),
                        ts=datetime.now(UTC).isoformat(),
                        status="failed",
                        request=request_payload,
                        api_response={
                            "error": str(exc),
                            "error_type": type(exc).__name__,
                            "graph_bubble_up": True,
                        },
                    )
                )
                raise
            except GenericActionResolveError as exc:
                logger.warning(
                    "soc_solve_plan_execute_resolve_failed",
                    sub_question_id=sid,
                    error=str(exc),
                )
                item = {
                    **base_item,
                    "status": "failed",
                    "action_reason": sq.get("action_reason"),
                    "error": str(exc),
                }
                await _append_execution_log(
                    _build_item_log_entry(
                        node3_tool_name=str(ga),
                        ts=datetime.now(UTC).isoformat(),
                        status="failed",
                        request=request_payload,
                        api_response={
                            "error": str(exc),
                            "error_type": type(exc).__name__,
                        },
                    )
                )
                return item_index, item, "failed"
            except Exception as exc:
                logger.exception(
                    "soc_solve_plan_execute_item_failed",
                    sub_question_id=sid,
                    error=str(exc),
                )
                item = {
                    **base_item,
                    "status": "failed",
                    "action_reason": sq.get("action_reason"),
                    "error": str(exc),
                }
                await _append_execution_log(
                    _build_item_log_entry(
                        node3_tool_name=str(ga),
                        ts=datetime.now(UTC).isoformat(),
                        status="failed",
                        request=request_payload,
                        api_response={
                            "error": str(exc),
                            "error_type": type(exc).__name__,
                        },
                    )
                )
                return item_index, item, "failed"

    jobs: list[asyncio.Task[tuple[int, dict[str, Any], str]]] = []
    item_index = 0
    for task in plan["tasks"]:
        action_id = str(task["action_id"])
        action_title = str(task["action_title"])
        for sq in task["sub_questions"]:
            jobs.append(
                asyncio.create_task(
                    _run_one(
                        item_index=item_index,
                        action_id=action_id,
                        action_title=action_title,
                        sq=sq,
                    )
                )
            )
            item_index += 1

    results = await asyncio.gather(*jobs)
    for idx, item, status in results:
        items_by_index[idx] = item
        if status == "success":
            success_count += 1
        elif status == "failed":
            failed_count += 1
        else:
            skipped_count += 1
    items = [items_by_index[i] for i in sorted(items_by_index)]

    summary = {
        "total": len(items),
        "success": success_count,
        "failed": failed_count,
        "skipped": skipped_count,
    }
    await _append_execution_log(
        {
            "ts": datetime.now(UTC).isoformat(),
            "schema_version": "soc_exec_summary_v1",
            "request_id": request_id,
            "session_id": session_id,
            "user_id": user_id,
            "summary": summary,
        }
    )
    print(f"[soc_solve_plan] execution log: {log_path}")
    logger.info("soc_solve_plan_execute_done", **summary)
    return {
        "schema_version": SOC_EXECUTION_SCHEMA_VERSION,
        "source_schema": SOC_SOLVE_SCHEMA_VERSION,
        "items": items,
        "summary": summary,
        "execution_log_path": str(log_path),
    }
