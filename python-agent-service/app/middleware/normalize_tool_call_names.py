"""Normalize malformed LLM tool names before ToolNode validation.

Some models occasionally glue together repeated copies of the intended tool name
(e.g. ``tasktasktask`` instead of ``task``, or ``write_todoswrite_todos`` instead
of ``write_todos``). LangGraph then rejects the call as an unknown tool.

For each name in the **current request tool list**, if the model output matches
``^(?:<name>)+$`` (case-insensitive), it is rewritten to the canonical registry
name. Longer tool names are checked first so substrings do not steal matches.
"""

from __future__ import annotations

import re
from typing import Any, Awaitable, Callable, TypeVar

from langchain.agents.middleware.types import (
    AgentMiddleware,
    ExtendedModelResponse,
    ModelRequest,
    ModelResponse,
)
from langchain_core.messages import AIMessage, BaseMessage

ContextT = TypeVar("ContextT")
ResponseT = TypeVar("ResponseT")


def _tool_entry_name(tool: Any) -> str | None:
    if isinstance(tool, dict):
        n = tool.get("name")
        return str(n) if n else None
    n = getattr(tool, "name", None)
    return str(n) if n else None


def _collect_tool_names(tools: list[Any]) -> set[str]:
    names: set[str] = set()
    for t in tools:
        n = _tool_entry_name(t)
        if n:
            names.add(n)
    return names


def _normalize_stuttered_tool_name(name: str, allowed: set[str]) -> str:
    """If ``name`` is N≥1 concatenated copies of an allowed tool name, return that tool name."""
    stripped = (name or "").strip()
    if not stripped:
        return name
    if stripped in allowed:
        return stripped
    for canonical in sorted(allowed, key=len, reverse=True):
        if not canonical:
            continue
        pat = re.compile(rf"^(?:{re.escape(canonical)})+$", re.IGNORECASE)
        if pat.fullmatch(stripped):
            return canonical
    return name


def _fix_tool_call_dict(tc: dict[str, Any], allowed: set[str]) -> tuple[dict[str, Any], bool]:
    raw_name = tc.get("name")
    if raw_name is None:
        return tc, False
    nn = _normalize_stuttered_tool_name(str(raw_name), allowed)
    if nn == raw_name:
        return tc, False
    return {**tc, "name": nn}, True


def _fix_invalid_tool_call_dict(itc: dict[str, Any], allowed: set[str]) -> tuple[dict[str, Any], bool]:
    raw_name = itc.get("name")
    if raw_name is None:
        return itc, False
    nn = _normalize_stuttered_tool_name(str(raw_name), allowed)
    if nn == raw_name:
        return itc, False
    return {**itc, "name": nn}, True


def _fix_ai_message(msg: AIMessage, allowed: set[str]) -> AIMessage:
    tcs = list(msg.tool_calls or [])
    itcs = list(getattr(msg, "invalid_tool_calls", None) or [])

    new_tcs: list[Any] = []
    tc_changed = False
    for tc in tcs:
        if isinstance(tc, dict):
            fixed, ch = _fix_tool_call_dict(tc, allowed)
            new_tcs.append(fixed)
            tc_changed = tc_changed or ch
        else:
            # LangChain typically uses dict tool_calls; keep unknown shapes as-is.
            new_tcs.append(tc)

    new_itcs: list[Any] = []
    itc_changed = False
    for itc in itcs:
        if isinstance(itc, dict):
            fixed, ch = _fix_invalid_tool_call_dict(itc, allowed)
            new_itcs.append(fixed)
            itc_changed = itc_changed or ch
        else:
            new_itcs.append(itc)

    if not tc_changed and not itc_changed:
        return msg

    update: dict[str, Any] = {"tool_calls": new_tcs}
    if itcs:
        update["invalid_tool_calls"] = new_itcs
    return msg.model_copy(update=update)


def _normalize_model_response(mr: ModelResponse[Any], allowed: set[str]) -> ModelResponse[Any]:
    new_result: list[BaseMessage] = []
    changed = False
    for m in mr.result:
        if isinstance(m, AIMessage):
            fixed = _fix_ai_message(m, allowed)
            if fixed is not m:
                changed = True
            new_result.append(fixed)
        else:
            new_result.append(m)
    if not changed:
        return mr
    return ModelResponse(result=new_result, structured_response=mr.structured_response)


def _normalize_handler_response(response: Any, tools: list[Any]) -> Any:
    allowed = _collect_tool_names(tools)
    if isinstance(response, ExtendedModelResponse):
        fixed_mr = _normalize_model_response(response.model_response, allowed)
        if fixed_mr is response.model_response:
            return response
        return ExtendedModelResponse(
            model_response=fixed_mr,
            command=response.command,
        )
    if isinstance(response, ModelResponse):
        return _normalize_model_response(response, allowed)
    if isinstance(response, AIMessage):
        fixed = _fix_ai_message(response, allowed)
        return ModelResponse(result=[fixed])
    return response


class NormalizeToolCallNamesMiddleware(AgentMiddleware[Any, ContextT, ResponseT]):
    """Post-process model output to fix repeated / glued tool names vs the request tool list."""

    def wrap_model_call(
        self,
        request: ModelRequest[ContextT],
        handler: Callable[[ModelRequest[ContextT]], ModelResponse[ResponseT]],
    ) -> ModelResponse[ResponseT] | ExtendedModelResponse[ResponseT]:
        raw = handler(request)
        return _normalize_handler_response(raw, list(request.tools))

    async def awrap_model_call(
        self,
        request: ModelRequest[ContextT],
        handler: Callable[
            [ModelRequest[ContextT]],
            Awaitable[ModelResponse[ResponseT]],
        ],
    ) -> ModelResponse[ResponseT] | ExtendedModelResponse[ResponseT]:
        raw = await handler(request)
        return _normalize_handler_response(raw, list(request.tools))
