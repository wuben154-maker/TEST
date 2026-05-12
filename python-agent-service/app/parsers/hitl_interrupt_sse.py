"""Map LangGraph ``__interrupt__`` payloads to canonical SSE events (HITL)."""

from __future__ import annotations

import json
import uuid
from typing import Any, Callable

from langgraph.types import Interrupt

# LangGraph internal key streamed in ``updates`` mode (see langgraph._internal._constants).
INTERRUPT_KEY = "__interrupt__"


def _json_safe(obj: Any) -> Any:
    """Best-effort JSON-serializable copy for SSE payloads."""
    if obj is None or isinstance(obj, (bool, int, float, str)):
        return obj
    if isinstance(obj, dict):
        return {str(k): _json_safe(v) for k, v in obj.items()}
    if isinstance(obj, (list, tuple)):
        return [_json_safe(x) for x in obj]
    return str(obj)


def _hitl_decision_from_action_requests(hitl: dict[str, Any]) -> dict[str, Any]:
    """Build a UI-friendly ``decision`` object from HumanInTheLoopMiddleware HITLRequest."""
    actions = hitl.get("action_requests") or []
    options: list[dict[str, Any]] = []
    for i, a in enumerate(actions):
        if not isinstance(a, dict):
            continue
        name = str(a.get("name", "action"))
        desc = str(a.get("description", name))
        options.append(
            {
                "id": f"hitl-action-{i}",
                "label": f"{name}",
                "description": desc[:2000],
                "variant": "default",
            }
        )
    if not options:
        options.append(
            {
                "id": "approve",
                "label": "Approve",
                "description": "Approve pending tool execution",
                "variant": "success",
            }
        )
        options.append(
            {
                "id": "reject",
                "label": "Reject",
                "description": "Reject pending tool execution",
                "variant": "destructive",
            }
        )
    q = "Tool execution requires your review" if actions else "Human review required"
    if actions and isinstance(actions[0], dict) and actions[0].get("description"):
        q = str(actions[0].get("description"))[:4000]
    return {
        "id": f"hitl-{uuid.uuid4().hex[:12]}",
        "question": q,
        "options": options,
        "allowMultiple": len(actions) > 1,
        "timestamp": None,
    }


def interrupts_to_sse_events(
    node_output: Any,
    emit: Callable[[dict[str, Any]], dict[str, Any]],
    *,
    stream_request_id: str | None = None,
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    """Convert a ``__interrupt__`` tuple/list to enveloped SSE dicts.

    Returns:
        (events, metadata) where metadata includes ``interruptIds`` for clients.
    """
    if isinstance(node_output, (list, tuple)):
        intr_list = list(node_output)
    else:
        intr_list = [node_output]

    out: list[dict[str, Any]] = []
    interrupt_ids: list[str] = []

    for intr in intr_list:
        if not isinstance(intr, Interrupt):
            continue
        interrupt_ids.append(intr.id)
        val = intr.value

        if isinstance(val, dict) and "action_requests" in val and "review_configs" in val:
            sse_request_id = (
                stream_request_id.strip()
                if isinstance(stream_request_id, str) and stream_request_id.strip()
                else intr.id
            )
            decision = _hitl_decision_from_action_requests(val)
            out.append(
                emit(
                    {
                        "type": "decision_request",
                        "id": f"hitl-{intr.id}",
                        "requestId": sse_request_id,
                        "interruptRequestId": intr.id,
                        "interruptKind": "langchain_hitl_v1",
                        "interruptId": intr.id,
                        "hitlRequest": _json_safe(val),
                        "decision": decision,
                    }
                )
            )
        elif isinstance(val, dict) and val.get("interruptKind") == "user_input_v1":
            kind = str(val.get("kind", "text"))
            rid = str(val.get("requestId") or intr.id)
            sse_request_id = (
                stream_request_id.strip()
                if isinstance(stream_request_id, str) and stream_request_id.strip()
                else rid
            )
            if kind == "choice":
                opts = val.get("options") or []
                decision_opts = []
                if isinstance(opts, list):
                    for i, o in enumerate(opts):
                        label = str(o) if not isinstance(o, dict) else str(o.get("label", o.get("id", i)))
                        oid = str(i) if not isinstance(o, dict) else str(o.get("id", i))
                        decision_opts.append(
                            {"id": oid, "label": label, "description": label, "variant": "default"}
                        )
                out.append(
                    emit(
                        {
                            "type": "decision_request",
                            "id": rid,
                            "requestId": sse_request_id,
                            "interruptRequestId": rid,
                            "interruptKind": "user_input_v1",
                            "interruptId": intr.id,
                            "userInputKind": "choice",
                            "decision": {
                                "id": rid,
                                "question": str(val.get("prompt", "Please choose")),
                                "options": decision_opts,
                                "allowMultiple": False,
                            },
                        }
                    )
                )
            else:
                fields = val.get("fields") if kind == "form" else None
                preqs: list[dict[str, Any]] = []
                if isinstance(fields, list):
                    for fi, f in enumerate(fields):
                        if not isinstance(f, dict):
                            continue
                        preqs.append(
                            {
                                "id": str(f.get("name", f"field_{fi}")),
                                "name": str(f.get("name", f"field_{fi}")),
                                "description": str(f.get("label", f.get("name", "Field"))),
                                "paramType": str(f.get("paramType", "text")),
                                "required": bool(f.get("required", True)),
                                "placeholder": f.get("placeholder"),
                                "encrypted": False,
                            }
                        )
                if not preqs and kind == "text":
                    preqs.append(
                        {
                            "id": "reply",
                            "name": "reply",
                            "description": "",
                            "paramType": "text",
                            "required": True,
                            "encrypted": False,
                            "isClarification": True,
                        }
                    )
                out.append(
                    emit(
                        {
                            "type": "parameter_request",
                            "id": rid,
                            "requestId": sse_request_id,
                            "interruptRequestId": rid,
                            "interruptKind": "user_input_v1",
                            "interruptId": intr.id,
                            "userInputKind": kind,
                            "parameterRequests": preqs,
                            "detail": str(val.get("prompt", "")),
                        }
                    )
                )
        else:
            sse_request_id = (
                stream_request_id.strip()
                if isinstance(stream_request_id, str) and stream_request_id.strip()
                else intr.id
            )
            out.append(
                emit(
                    {
                        "type": "parameter_request",
                        "id": f"hitl-{intr.id}",
                        "requestId": sse_request_id,
                        "interruptRequestId": intr.id,
                        "interruptKind": "raw_interrupt_v1",
                        "interruptId": intr.id,
                        "parameterRequests": [
                            {
                                "id": "reply",
                                "name": "reply",
                                "description": "Provide input to continue",
                                "paramType": "text",
                                "required": True,
                                "encrypted": False,
                            }
                        ],
                        "detail": json.dumps(_json_safe(val), ensure_ascii=False)[:8000],
                    }
                )
            )

    return out, {"interruptIds": interrupt_ids}
