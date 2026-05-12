"""Tests for LlmInvokeLifecycleCallbackHandler.

Design: The callback handler emits ``llm_invoke_start`` on every
``on_chat_model_start`` and ``llm_invoke_end`` on every ``on_llm_end`` /
``on_llm_error``.  Every LLM invocation is reported regardless of whether
it produces visible delta content, so the frontend can accurately count
LLM calls and measure per-call duration.
"""

from unittest import mock

import pytest
from uuid import uuid4

from app.parsers.llm_invoke_callbacks import (
    LlmInvokeLifecycleCallbackHandler,
    _llm_invoke_id_stack,
    current_llm_invoke_id_for_delta,
    flatten_runnable_callbacks,
)


def _make_handler():
    events: list[dict] = []
    handler = LlmInvokeLifecycleCallbackHandler(emit_event=events.append)
    return handler, events


def test_flatten_runnable_callbacks_accepts_async_callback_manager():
    """LangGraph may pass AsyncCallbackManager; it must not be passed to list()."""
    from langchain_core.callbacks.manager import AsyncCallbackManager

    h = LlmInvokeLifecycleCallbackHandler(emit_event=list.append)
    mgr = AsyncCallbackManager([h])
    out = flatten_runnable_callbacks(mgr)
    assert isinstance(out, list)
    assert h in out
    assert len(out) == 1


def test_flatten_runnable_callbacks_list_passthrough():
    h = LlmInvokeLifecycleCallbackHandler(emit_event=list.append)
    out = flatten_runnable_callbacks([h])
    assert out == [h]


class TestLifecycleCallbacks:
    @pytest.mark.asyncio
    async def test_on_chat_model_start_emits_start(self):
        """on_chat_model_start must emit llm_invoke_start for every LLM call."""
        handler, events = _make_handler()
        run_id = uuid4()
        await handler.on_chat_model_start({}, [[]], run_id=run_id)
        assert len(events) == 1
        assert events[0]["type"] == "llm_invoke_start"
        assert events[0]["invokeId"] == run_id.hex[:12]

    @pytest.mark.asyncio
    async def test_on_llm_end_emits_end(self):
        """on_llm_end must emit llm_invoke_end, paired with the start from on_chat_model_start."""
        handler, events = _make_handler()
        run_id = uuid4()
        await handler.on_chat_model_start({}, [[]], run_id=run_id)
        await handler.on_llm_end(object(), run_id=run_id)
        types = [e["type"] for e in events]
        assert types == ["llm_invoke_start", "llm_invoke_end"]

    @pytest.mark.asyncio
    async def test_end_invoke_id_matches_run_id(self):
        """invokeId on both start and end must match the truncated run_id."""
        handler, events = _make_handler()
        run_id = uuid4()
        await handler.on_chat_model_start({}, [[]], run_id=run_id)
        await handler.on_llm_end(object(), run_id=run_id)
        assert events[0]["invokeId"] == run_id.hex[:12]
        assert events[1]["invokeId"] == run_id.hex[:12]

    @pytest.mark.asyncio
    async def test_on_llm_error_also_closes_invoke(self):
        """on_llm_error must emit llm_invoke_end to avoid dangling state."""
        handler, events = _make_handler()
        run_id = uuid4()
        await handler.on_chat_model_start({}, [[]], run_id=run_id)
        await handler.on_llm_error(RuntimeError("boom"), run_id=run_id)
        types = [e["type"] for e in events]
        assert types == ["llm_invoke_start", "llm_invoke_end"]

    @pytest.mark.asyncio
    async def test_multiple_independent_invocations(self):
        """Each LLM call (different run_id) produces its own start+end pair."""
        handler, events = _make_handler()
        run_id_a = uuid4()
        run_id_b = uuid4()
        await handler.on_chat_model_start({}, [[]], run_id=run_id_a)
        await handler.on_chat_model_start({}, [[]], run_id=run_id_b)
        await handler.on_llm_end(object(), run_id=run_id_b)
        await handler.on_llm_end(object(), run_id=run_id_a)
        starts = [e for e in events if e["type"] == "llm_invoke_start"]
        ends = [e for e in events if e["type"] == "llm_invoke_end"]
        assert len(starts) == 2
        assert len(ends) == 2
        start_ids = {e["invokeId"] for e in starts}
        end_ids = {e["invokeId"] for e in ends}
        assert start_ids == end_ids

    @pytest.mark.asyncio
    async def test_start_and_end_carry_wall_clock_timestamp(self):
        """Both start and end must record callback-time ms for accurate duration."""
        handler, events = _make_handler()
        run_id = uuid4()
        t_start = 1_700_000_000_000
        t_end = 1_700_000_005_000
        with mock.patch.object(
            LlmInvokeLifecycleCallbackHandler,
            "_wall_clock_ms",
            return_value=t_start,
        ):
            await handler.on_chat_model_start({}, [[]], run_id=run_id)
        with mock.patch.object(
            LlmInvokeLifecycleCallbackHandler,
            "_wall_clock_ms",
            return_value=t_end,
        ):
            await handler.on_llm_end(object(), run_id=run_id)
        assert events[0]["timestamp"] == t_start
        assert events[1]["timestamp"] == t_end

    @pytest.mark.asyncio
    async def test_release_stack_for_synthetic_then_on_llm_end_idempotent(self):
        """Adapter may synthesize end first; late on_llm_end must not emit duplicate end."""
        handler, events = _make_handler()
        run_id = uuid4()
        await handler.on_chat_model_start({}, [[]], run_id=run_id)
        iid = run_id.hex[:12]
        assert current_llm_invoke_id_for_delta() == iid
        handler.release_stack_for_synthetic_llm_invoke_end(iid)
        assert current_llm_invoke_id_for_delta() is None
        await handler.on_llm_end(object(), run_id=run_id)
        assert len([e for e in events if e["type"] == "llm_invoke_start"]) == 1
        assert len([e for e in events if e["type"] == "llm_invoke_end"]) == 0

    def test_on_chat_model_end_not_called_by_langchain_is_dead_code(self):
        from langchain_core.callbacks.base import BaseCallbackHandler
        langchain_methods = [m for m in dir(BaseCallbackHandler) if m.startswith("on_")]
        assert "on_chat_model_end" not in langchain_methods
        assert "on_chat_model_start" in langchain_methods
        assert "on_llm_end" in langchain_methods

    def test_handler_is_async_callback_handler(self):
        from langchain_core.callbacks.base import AsyncCallbackHandler
        handler, _ = _make_handler()
        assert isinstance(handler, AsyncCallbackHandler)

    def test_handler_init_sets_contextvar_to_mutable_list(self):
        handler, _ = _make_handler()
        stack = _llm_invoke_id_stack.get()
        assert stack is handler._invoke_stack
        assert isinstance(stack, list)

    @pytest.mark.asyncio
    async def test_stack_visible_after_start(self):
        """current_llm_invoke_id_for_delta must see the iid after on_chat_model_start
        pushes it onto the shared mutable list."""
        handler, _events = _make_handler()
        run_id = uuid4()
        await handler.on_chat_model_start({}, [[]], run_id=run_id)
        iid = run_id.hex[:12]
        assert current_llm_invoke_id_for_delta() == iid
        await handler.on_llm_end(object(), run_id=run_id)
        assert current_llm_invoke_id_for_delta() is None

    @pytest.mark.asyncio
    async def test_nested_stack_lifo_order(self):
        """Nested calls: current_llm_invoke_id_for_delta returns the innermost."""
        handler, _events = _make_handler()
        rid_a = uuid4()
        rid_b = uuid4()
        iid_a = rid_a.hex[:12]
        iid_b = rid_b.hex[:12]
        await handler.on_chat_model_start({}, [[]], run_id=rid_a)
        assert current_llm_invoke_id_for_delta() == iid_a
        await handler.on_chat_model_start({}, [[]], run_id=rid_b)
        assert current_llm_invoke_id_for_delta() == iid_b
        await handler.on_llm_end(object(), run_id=rid_b)
        assert current_llm_invoke_id_for_delta() == iid_a
        await handler.on_llm_end(object(), run_id=rid_a)
        assert current_llm_invoke_id_for_delta() is None
