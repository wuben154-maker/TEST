"""Tests for llm_invoke_triplet, LlmInvokeEmitter, and _SubagentEagerStartCallback."""

from unittest.mock import patch
from uuid import uuid4

import pytest

from app.parsers.llm_invoke_sse import LlmInvokeEmitter, llm_invoke_triplet
from app._vendor.deepagents.middleware.subagents import _SubagentEagerStartCallback


def test_llm_invoke_triplet_empty():
    assert llm_invoke_triplet("reasoning", "") == []
    assert llm_invoke_triplet("reasoning", "   \n") == []


def test_llm_invoke_triplet_preserves_whitespace_payload():
    evs = llm_invoke_triplet("reasoning", " a ")
    assert len(evs) == 3
    assert evs[0]["type"] == "llm_invoke_start"
    assert evs[1]["type"] == "llm_delta" and evs[1]["channel"] == "reasoning"
    assert evs[1]["content"] == " a "
    assert evs[2]["type"] == "llm_invoke_end"
    assert evs[0]["invokeId"] == evs[1]["invokeId"] == evs[2]["invokeId"]
    assert isinstance(evs[0].get("timestamp"), int)
    assert isinstance(evs[2].get("timestamp"), int)
    assert evs[2]["timestamp"] >= evs[0]["timestamp"]


def test_llm_invoke_triplet_text_channel():
    evs = llm_invoke_triplet("text", "hello")
    assert evs[1]["channel"] == "text"


def test_llm_invoke_triplet_usage_from_ai_message_metadata():
    """``usage`` with LangChain ``usage_metadata`` shape lands on the end event.

    Research / task_planner paths do not go through
    ``LlmInvokeLifecycleCallbackHandler`` — without this propagation the
    realtime context-usage indicator stays hidden forever.
    """
    usage_meta = {"input_tokens": 1200, "output_tokens": 340, "total_tokens": 1540}
    evs = llm_invoke_triplet("text", "hello", usage=usage_meta, model_id="anthropic/claude")
    assert evs[0]["type"] == "llm_invoke_start"
    assert evs[0]["modelId"] == "anthropic/claude"
    end = evs[2]
    assert end["type"] == "llm_invoke_end"
    assert end["usage"] == {"inputTokens": 1200, "outputTokens": 340}


def test_llm_invoke_triplet_usage_accepts_prenormalized_shape():
    evs = llm_invoke_triplet(
        "reasoning",
        "thinking",
        usage={"inputTokens": 500, "outputTokens": 0},
    )
    assert evs[2]["usage"] == {"inputTokens": 500, "outputTokens": 0}


def test_llm_invoke_triplet_usage_absent_when_zero_or_missing():
    """Zero-only usage is dropped (contract: let frontend skip event)."""
    no_usage = llm_invoke_triplet("text", "hi")
    assert "usage" not in no_usage[2]
    zero_usage = llm_invoke_triplet("text", "hi", usage={"input_tokens": 0, "output_tokens": 0})
    assert "usage" not in zero_usage[2]
    bad_usage = llm_invoke_triplet("text", "hi", usage="nonsense")  # type: ignore[arg-type]
    assert "usage" not in bad_usage[2]


def test_llm_invoke_emitter_close_idempotent():
    seen: list[dict] = []

    def emit(ev: dict) -> dict:
        seen.append(dict(ev))
        return ev

    em = LlmInvokeEmitter(emit)
    assert em.close() == []
    assert em.close() == []


def test_llm_invoke_emitter_close_forwards_usage_metadata():
    """``close(usage=...)`` must stamp usage on the end event.

    Subagent middleware calls ``close`` after processing each AIMessage; without
    this propagation the context-usage indicator stays empty for subagent runs.
    """
    seen: list[dict] = []

    def emit(ev: dict) -> dict:
        seen.append(dict(ev))
        return ev

    em = LlmInvokeEmitter(emit, emit_boundaries=True)
    em.pre_open("sa-0001", 1_700_000_000_000)
    result = em.close(
        usage={"input_tokens": 2500, "output_tokens": 612, "total_tokens": 3112},
    )
    assert len(result) == 1
    assert result[0]["type"] == "llm_invoke_end"
    assert result[0]["usage"] == {"inputTokens": 2500, "outputTokens": 612}


def test_llm_invoke_emitter_close_without_usage_stays_legacy():
    """No usage → no ``usage`` field (frontend skips the event — legacy contract)."""
    seen: list[dict] = []

    def emit(ev: dict) -> dict:
        seen.append(dict(ev))
        return ev

    em = LlmInvokeEmitter(emit, emit_boundaries=True)
    em.pre_open("sa-0002", 1_700_000_000_000)
    result = em.close()
    assert result[0]["type"] == "llm_invoke_end"
    assert "usage" not in result[0]


def test_pre_open_emits_start_immediately():
    """pre_open must emit llm_invoke_start with the supplied timestamp."""
    seen: list[dict] = []

    def emit(ev: dict) -> dict:
        seen.append(dict(ev))
        return ev

    em = LlmInvokeEmitter(emit)
    result = em.pre_open("abc123", 1_700_000_000_000)
    assert len(result) == 1
    assert result[0]["type"] == "llm_invoke_start"
    assert result[0]["invokeId"] == "abc123"
    assert result[0]["timestamp"] == 1_700_000_000_000
    assert em.is_open
    assert em.invoke_id == "abc123"


def test_pre_open_then_delta_skips_duplicate_start():
    """After pre_open, delta() must NOT emit a second llm_invoke_start."""
    seen: list[dict] = []

    def emit(ev: dict) -> dict:
        seen.append(dict(ev))
        return ev

    em = LlmInvokeEmitter(emit)
    em.pre_open("abc123", 1_700_000_000_000)
    seen.clear()

    em.delta("text", "hello")
    types = [e["type"] for e in seen]
    assert "llm_invoke_start" not in types
    assert "llm_delta" in types
    assert seen[0]["invokeId"] == "abc123"


def test_pre_open_then_close_emits_end():
    """After pre_open + delta, close() must emit llm_invoke_end."""
    seen: list[dict] = []

    def emit(ev: dict) -> dict:
        seen.append(dict(ev))
        return ev

    em = LlmInvokeEmitter(emit)
    em.pre_open("abc123", 1_700_000_000_000)
    em.delta("text", "hello")
    seen.clear()

    result = em.close()
    assert len(result) == 1
    assert result[0]["type"] == "llm_invoke_end"
    assert result[0]["invokeId"] == "abc123"
    assert not em.is_open


def test_pre_open_closes_previous_invoke():
    """Calling pre_open while another invoke is open must close the previous one first."""
    seen: list[dict] = []

    def emit(ev: dict) -> dict:
        seen.append(dict(ev))
        return ev

    em = LlmInvokeEmitter(emit)
    em.pre_open("aaa111", 1_700_000_000_000)
    em.delta("text", "first")
    seen.clear()

    em.pre_open("bbb222", 1_700_000_005_000)
    types = [e["type"] for e in seen]
    assert types == ["llm_invoke_end", "llm_invoke_start"]
    assert seen[0]["invokeId"] == "aaa111"
    assert seen[1]["invokeId"] == "bbb222"
    assert seen[1]["timestamp"] == 1_700_000_005_000


def test_pre_open_with_emit_boundaries_false():
    """pre_open with emit_boundaries=False must not emit start."""
    seen: list[dict] = []

    def emit(ev: dict) -> dict:
        seen.append(dict(ev))
        return ev

    em = LlmInvokeEmitter(emit, emit_boundaries=False)
    result = em.pre_open("abc123", 1_700_000_000_000)
    assert result == []
    assert em.is_open
    assert em.invoke_id == "abc123"


def test_emitter_emit_boundaries_false_realigns_when_context_invoke_id_changes():
    """After on_llm_end pops ContextVar, a new run id must not reuse stale emitter state."""
    seen: list[dict] = []

    def emit(ev: dict) -> dict:
        seen.append(dict(ev))
        return ev

    orphans: list[str] = []

    def on_orphan(iid: str) -> None:
        orphans.append(iid)

    em = LlmInvokeEmitter(emit, emit_boundaries=False, on_orphan_realign=on_orphan)
    with patch(
        "app.parsers.llm_invoke_sse.current_llm_invoke_id_for_delta", return_value="aaa111"
    ):
        em.delta("reasoning", "x")
    with patch(
        "app.parsers.llm_invoke_sse.current_llm_invoke_id_for_delta", return_value="bbb222"
    ):
        em.delta("reasoning", "y")
    assert [e["invokeId"] for e in seen if e["type"] == "llm_delta"] == ["aaa111", "bbb222"]
    assert orphans == ["aaa111"]


# --- _SubagentEagerStartCallback tests ---


class TestSubagentEagerStartCallback:
    @pytest.mark.asyncio
    async def test_on_chat_model_start_pre_opens_emitter(self):
        """Callback must call pre_open so llm_invoke_start is emitted immediately."""
        seen: list[dict] = []

        def emit(ev: dict) -> dict:
            seen.append(dict(ev))
            return ev

        em = LlmInvokeEmitter(emit)
        cb = _SubagentEagerStartCallback(em)

        run_id = uuid4()
        await cb.on_chat_model_start({}, [[]], run_id=run_id)

        assert em.is_open
        assert em.invoke_id == run_id.hex[:12]
        starts = [e for e in seen if e["type"] == "llm_invoke_start"]
        assert len(starts) == 1
        assert starts[0]["invokeId"] == run_id.hex[:12]
        assert isinstance(starts[0]["timestamp"], int)

    @pytest.mark.asyncio
    async def test_callback_then_delta_then_close_full_lifecycle(self):
        """Full sequence: callback start → delta → close = start + delta + end."""
        seen: list[dict] = []

        def emit(ev: dict) -> dict:
            seen.append(dict(ev))
            return ev

        em = LlmInvokeEmitter(emit)
        cb = _SubagentEagerStartCallback(em)

        run_id = uuid4()
        await cb.on_chat_model_start({}, [[]], run_id=run_id)
        em.delta("text", "result content")
        em.close()

        types = [e["type"] for e in seen]
        assert types == ["llm_invoke_start", "llm_delta", "llm_invoke_end"]
        iids = [e["invokeId"] for e in seen]
        assert len(set(iids)) == 1
        assert iids[0] == run_id.hex[:12]

    @pytest.mark.asyncio
    async def test_on_llm_end_is_noop(self):
        """on_llm_end must not emit anything — end comes from emitter.close()."""
        seen: list[dict] = []

        def emit(ev: dict) -> dict:
            seen.append(dict(ev))
            return ev

        em = LlmInvokeEmitter(emit)
        cb = _SubagentEagerStartCallback(em)

        run_id = uuid4()
        await cb.on_chat_model_start({}, [[]], run_id=run_id)
        seen.clear()
        await cb.on_llm_end(object(), run_id=run_id)
        assert len(seen) == 0
        assert em.is_open

    @pytest.mark.asyncio
    async def test_on_llm_error_is_noop(self):
        """on_llm_error must not emit anything either."""
        seen: list[dict] = []

        def emit(ev: dict) -> dict:
            seen.append(dict(ev))
            return ev

        em = LlmInvokeEmitter(emit)
        cb = _SubagentEagerStartCallback(em)

        run_id = uuid4()
        await cb.on_chat_model_start({}, [[]], run_id=run_id)
        seen.clear()
        await cb.on_llm_error(RuntimeError("boom"), run_id=run_id)
        assert len(seen) == 0

    @pytest.mark.asyncio
    async def test_does_not_touch_contextvar(self):
        """Callback must not set _llm_invoke_id_stack — no main-agent stack corruption."""
        from app.parsers.llm_invoke_callbacks import _llm_invoke_id_stack

        sentinel = ["sentinel"]
        _llm_invoke_id_stack.set(sentinel)

        seen: list[dict] = []
        em = LlmInvokeEmitter(lambda ev: (seen.append(ev), ev)[-1])
        cb = _SubagentEagerStartCallback(em)

        await cb.on_chat_model_start({}, [[]], run_id=uuid4())
        assert _llm_invoke_id_stack.get() is sentinel

    @pytest.mark.asyncio
    async def test_multiple_sequential_invokes(self):
        """Two sequential LLM calls must each get their own start/end pair."""
        seen: list[dict] = []

        def emit(ev: dict) -> dict:
            seen.append(dict(ev))
            return ev

        em = LlmInvokeEmitter(emit)
        cb = _SubagentEagerStartCallback(em)

        rid1 = uuid4()
        await cb.on_chat_model_start({}, [[]], run_id=rid1)
        em.delta("text", "first")
        em.close()

        rid2 = uuid4()
        await cb.on_chat_model_start({}, [[]], run_id=rid2)
        em.delta("text", "second")
        em.close()

        types = [e["type"] for e in seen]
        assert types == [
            "llm_invoke_start", "llm_delta", "llm_invoke_end",
            "llm_invoke_start", "llm_delta", "llm_invoke_end",
        ]
        assert seen[0]["invokeId"] == rid1.hex[:12]
        assert seen[3]["invokeId"] == rid2.hex[:12]
