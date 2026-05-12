"""Skip main LLM after a tool round that includes ``task(deep-research)`` with no other ``task`` types.

open_deep_research already streams the user-visible conclusion. The main model often emits
``write_todos`` and ``task(deep-research)`` in the **same** ``AIMessage``; we still skip the
follow-up synthesis LLM when every ``task`` call in that anchor is ``deep-research`` and all
tool results (including ``write_todos``) are present.
"""

from __future__ import annotations

from typing import Any, Awaitable, Callable, TypeVar

from langchain.agents.middleware.types import (
    AgentMiddleware,
    ModelRequest,
    ModelResponse,
)
from langchain_core.messages import AIMessage, ToolMessage

ContextT = TypeVar("ContextT")
ResponseT = TypeVar("ResponseT")


def _normalize_subagent_type(raw: Any) -> str:
    return str(raw or "").strip().lower().replace("_", "-")


def _tool_call_name(tc: Any) -> str:
    if isinstance(tc, dict):
        return str(tc.get("name") or "")
    return str(getattr(tc, "name", "") or "")


def _tool_call_args(tc: Any) -> dict[str, Any]:
    if isinstance(tc, dict):
        a = tc.get("args")
        return dict(a) if isinstance(a, dict) else {}
    a = getattr(tc, "args", None)
    return dict(a) if isinstance(a, dict) else {}


def _tool_call_id(tc: Any) -> str:
    if isinstance(tc, dict):
        return str(tc.get("id") or "")
    return str(getattr(tc, "id", "") or "")


def should_skip_main_model_after_deep_research_only_task(messages: list[Any]) -> bool:
    """True if the next model invocation should be skipped (no API call).

    The last message must be ``ToolMessage``. The last ``AIMessage`` with ``tool_calls``
    is the anchor for the pending round. Non-``task`` tools (e.g. ``write_todos``) are
    allowed alongside ``task`` calls. Skip when:

    - There is at least one ``task`` tool call and every ``task`` uses ``deep-research``.
    - The tail after the anchor is only ``ToolMessage`` rows, one per anchor tool call,
      with ``tool_call_id`` matching the anchor ids.
    """
    if not messages or not isinstance(messages[-1], ToolMessage):
        return False

    anchor_idx: int | None = None
    for i in range(len(messages) - 1, -1, -1):
        m = messages[i]
        if isinstance(m, AIMessage):
            tcs = getattr(m, "tool_calls", None) or []
            if tcs:
                anchor_idx = i
                break
    if anchor_idx is None:
        return False

    anchor = messages[anchor_idx]
    tcs = getattr(anchor, "tool_calls", None) or []
    if not tcs:
        return False

    all_ids: set[str] = set()
    saw_deep_research_task = False
    for tc in tcs:
        tid = _tool_call_id(tc)
        if not tid:
            return False
        all_ids.add(tid)
        name = _tool_call_name(tc)
        if name != "task":
            continue
        args = _tool_call_args(tc)
        st = _normalize_subagent_type(args.get("subagent_type"))
        if st != "deep-research":
            return False
        saw_deep_research_task = True

    if not saw_deep_research_task:
        return False

    tail = messages[anchor_idx + 1:]
    if not tail or len(tail) != len(tcs):
        return False
    seen: set[str] = set()
    for msg in tail:
        if not isinstance(msg, ToolMessage):
            return False
        seen.add(str(getattr(msg, "tool_call_id", "") or ""))
    return seen == all_ids


class DeepResearchSynthesisSkipMiddleware(AgentMiddleware[Any, ContextT, ResponseT]):
    """Bypass main LLM when deep-research was the only delegated task in that round."""

    def wrap_model_call(
        self,
        request: ModelRequest[ContextT],
        handler: Callable[[ModelRequest[ContextT]], ModelResponse[ResponseT]],
    ) -> ModelResponse[ResponseT]:
        if should_skip_main_model_after_deep_research_only_task(list(request.messages)):
            return ModelResponse(result=[AIMessage(content="")])
        return handler(request)

    async def awrap_model_call(
        self,
        request: ModelRequest[ContextT],
        handler: Callable[
            [ModelRequest[ContextT]],
            Awaitable[ModelResponse[ResponseT]],
        ],
    ) -> ModelResponse[ResponseT]:
        if should_skip_main_model_after_deep_research_only_task(list(request.messages)):
            return ModelResponse(result=[AIMessage(content="")])
        return await handler(request)
