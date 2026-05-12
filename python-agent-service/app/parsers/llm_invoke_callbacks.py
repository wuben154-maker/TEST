"""LangChain callbacks for ``llm_invoke_start`` / ``llm_invoke_end`` SSE boundaries.

``on_chat_model_start`` emits ``llm_invoke_start`` for **every** LLM call so the
frontend can count invocations and compute per-call duration — including ReAct
decision rounds that produce no visible content.

Uses ``on_llm_end`` / ``on_llm_error`` (not ``on_chat_model_end``), LangChain
invokes those after chat model completion.

**AsyncCallbackHandler** is used (not ``BaseCallbackHandler``) so LangChain runs
these methods in the event-loop thread instead of ``run_in_executor``.

The invoke-id stack uses a **mutable list** stored in a ContextVar rather than
immutable tuples with ``set()``/``reset()``.  LangChain's ``AsyncCallbackManager``
wraps each callback coroutine in ``asyncio.create_task()`` (via ``gather()``),
which **copies** the current context.  ``ContextVar.set()`` and ``reset()`` only
affect the copy, so the parent context (where ``LlmInvokeEmitter.delta()`` calls
``current_llm_invoke_id_for_delta()``) never sees changes.  In contrast, in-place
mutations on a shared list reference (``append`` / ``remove``) are visible across
all context copies because they share the same object.

The handler's ``__init__`` creates a fresh list and ``set()``s the ContextVar
**once** in the caller's context (the adapter async-generator / request task).
All child tasks inherit this reference.
"""

from __future__ import annotations

import time
from contextvars import ContextVar
from typing import Any, Callable
from uuid import UUID

from langchain_core.callbacks.base import AsyncCallbackHandler

import structlog

from app.billing.model_id_from_serialized import resolve_gateway_model_id_from_chat_start
from app.billing.pricing import extract_token_usage_from_llm_result

logger = structlog.get_logger()

EmitFn = Callable[[dict[str, Any]], None]


def _safe_extract_usage(response: Any) -> dict[str, int]:
    """Extract ``{inputTokens, outputTokens}`` from an ``LLMResult``-like response.

    Tolerates legacy callers that pass ``object()`` (historical tests) or providers
    that omit ``usage_metadata``. Always returns a dict; never raises.
    """
    try:
        prompt_t, completion_t = extract_token_usage_from_llm_result(response)
    except Exception as exc:  # noqa: BLE001 - usage extraction must never fail the callback chain
        logger.debug("llm_invoke_usage_extract_failed", error=str(exc))
        return {"inputTokens": 0, "outputTokens": 0}
    return {"inputTokens": int(prompt_t or 0), "outputTokens": int(completion_t or 0)}

# Mutable list shared via ContextVar; mutations are visible across copied contexts.
_llm_invoke_id_stack: ContextVar[list[str] | None] = ContextVar(
    "llm_invoke_id_stack", default=None
)


def current_llm_invoke_id_for_delta() -> str | None:
    """Active invoke id for the innermost in-flight chat model run, if any."""
    stack = _llm_invoke_id_stack.get()
    return stack[-1] if stack else None


def flatten_runnable_callbacks(callbacks: Any) -> list[Any]:
    """Expand RunnableConfig ``callbacks`` (list/tuple or CallbackManager) to a handler list.

    LangGraph / LangChain may pass ``AsyncCallbackManager`` or ``CallbackManager``;
    those are not iterable as a whole — handlers live on ``.handlers``.
    """
    if callbacks is None:
        return []
    if isinstance(callbacks, (list, tuple)):
        return list(callbacks)
    handlers = getattr(callbacks, "handlers", None)
    if isinstance(handlers, (list, tuple)):
        return list(handlers)
    return [callbacks]


class LlmInvokeLifecycleCallbackHandler(AsyncCallbackHandler):
    def __init__(
        self,
        emit_event: EmitFn | None = None,
        *,
        emit_start: EmitFn | None = None,
        emit_end: EmitFn | None = None,
        context_meter: Any | None = None,
    ) -> None:
        super().__init__()
        if emit_event is not None:
            self._emit_start = emit_event
            self._emit_end = emit_event
        elif emit_start is not None and emit_end is not None:
            self._emit_start = emit_start
            self._emit_end = emit_end
        else:

            def _noop(_: dict[str, Any]) -> None:
                return None

            self._emit_start = _noop
            self._emit_end = _noop

        # Shared mutable stack — set once in the creator's context so child tasks
        # (callback coroutines wrapped by asyncio.gather) share the same list object.
        self._invoke_stack: list[str] = []
        _llm_invoke_id_stack.set(self._invoke_stack)

        # invokeId (12-char hex) -> run_id for synthetic llm_invoke_end when on_llm_end never fires
        self._invoke_id_to_run_id: dict[str, UUID] = {}
        # invokeId -> gateway model id (for context_budget + ContextMeter)
        self._invoke_model_id: dict[str, str | None] = {}
        self._context_meter = context_meter

    @staticmethod
    def _invoke_id(run_id: UUID) -> str:
        if not isinstance(run_id, UUID):
            run_id = UUID(str(run_id))
        return run_id.hex[:12]

    @staticmethod
    def _wall_clock_ms() -> int:
        return int(time.time() * 1000)

    async def on_chat_model_start(
        self,
        serialized: dict[str, Any],
        messages: list[Any],
        *,
        run_id: UUID,
        **kwargs: Any,
    ) -> Any:
        iid = self._invoke_id(run_id)
        self._invoke_id_to_run_id[iid] = run_id
        self._invoke_stack.append(iid)
        ts = self._wall_clock_ms()
        event: dict[str, Any] = {
            "type": "llm_invoke_start",
            "id": iid,
            "invokeId": iid,
            "timestamp": ts,
        }
        # modelId is best-effort — used by the realtime context-usage indicator
        # to pick the right context_window. Frontend falls back gracefully when absent.
        try:
            model_id = resolve_gateway_model_id_from_chat_start(
                serialized or {}, kwargs=kwargs
            )
        except Exception as exc:  # noqa: BLE001 - never fail the callback
            logger.debug("llm_invoke_modelid_resolve_failed", error=str(exc))
            model_id = None
        if model_id:
            event["modelId"] = model_id
        self._invoke_model_id[iid] = model_id
        self._emit_start(event)

    def _pop_run_stack(self, run_id: UUID) -> None:
        iid = self._invoke_id(run_id)
        try:
            self._invoke_stack.remove(iid)
        except ValueError:
            pass

    def is_invoke_tracked(self, iid: str) -> bool:
        """True if ``on_chat_model_start`` registered ``iid`` and it was not released yet."""
        return bool(iid) and iid in self._invoke_id_to_run_id

    async def on_llm_end(self, response: Any, *, run_id: UUID, **kwargs: Any) -> Any:
        iid = self._invoke_id(run_id)
        model_id = self._invoke_model_id.pop(iid, None)
        was_tracked = iid in self._invoke_id_to_run_id
        self._invoke_id_to_run_id.pop(iid, None)
        ts = self._wall_clock_ms()
        self._pop_run_stack(run_id)
        if was_tracked:
            usage = _safe_extract_usage(response)
            end_ev: dict[str, Any] = {
                "type": "llm_invoke_end",
                "id": iid,
                "invokeId": iid,
                "timestamp": ts,
                "usage": usage,
            }
            if model_id:
                end_ev["modelId"] = model_id
            if self._context_meter is not None:
                try:
                    self._context_meter.record_main_invoke_end(
                        input_tokens=int(usage.get("inputTokens") or 0),
                        output_tokens=int(usage.get("outputTokens") or 0),
                        model_id=model_id,
                        ended_at_ms=ts,
                    )
                except Exception as exc:  # noqa: BLE001
                    logger.debug("context_meter_record_failed", error=str(exc))
            self._emit_end(end_ev)

    async def on_llm_error(
        self, error: BaseException, *, run_id: UUID, **kwargs: Any
    ) -> Any:
        iid = self._invoke_id(run_id)
        model_id = self._invoke_model_id.pop(iid, None)
        was_tracked = iid in self._invoke_id_to_run_id
        self._invoke_id_to_run_id.pop(iid, None)
        ts = self._wall_clock_ms()
        self._pop_run_stack(run_id)
        if was_tracked:
            # Error path: we do not have a response — emit zero usage so the
            # frontend keeps its last good value and can mark the invoke failed.
            end_ev_err: dict[str, Any] = {
                "type": "llm_invoke_end",
                "id": iid,
                "invokeId": iid,
                "timestamp": ts,
                "usage": {"inputTokens": 0, "outputTokens": 0},
            }
            if model_id:
                end_ev_err["modelId"] = model_id
            self._emit_end(end_ev_err)

    def release_stack_for_synthetic_llm_invoke_end(self, iid: str) -> None:
        """Pop stack for ``iid`` when the adapter emits synthetic ``llm_invoke_end``.

        No-op if ``on_llm_end`` already ran (map entry cleared) or ``iid`` unknown.
        """
        if not iid:
            return
        rid = self._invoke_id_to_run_id.pop(iid, None)
        if rid is not None:
            self._pop_run_stack(rid)


__all__ = [
    "LlmInvokeLifecycleCallbackHandler",
    "current_llm_invoke_id_for_delta",
    "flatten_runnable_callbacks",
]
