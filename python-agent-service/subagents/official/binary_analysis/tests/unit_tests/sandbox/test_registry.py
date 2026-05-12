"""Unit tests for `_SESSION_REGISTRY` (C4-AC3, ADR-16)."""

from __future__ import annotations

import asyncio

import pytest

from sandbox.client import SandboxSession
from sandbox.registry import (
    _SESSION_REGISTRY,
    all_analysis_ids,
    get_session,
    register_session,
    unregister_session,
)


@pytest.fixture(autouse=True)
def _clean_registry():
    _SESSION_REGISTRY.clear()
    yield
    _SESSION_REGISTRY.clear()


def _make(aid: str) -> SandboxSession:
    return SandboxSession(
        analysis_id=aid,
        sandbox_id=f"sbx-{aid}",
        backend="subprocess",
        workdir=f"/workspace/{aid}/",
        created_at=0.0,
    )


class TestRegistryBasics:
    async def test_register_then_get_returns_same_instance(self):
        session = _make("aid-1")
        await register_session(session)
        assert await get_session("aid-1") is session

    async def test_get_unknown_returns_none(self):
        assert await get_session("no-such-id") is None

    async def test_unregister_pops_and_returns_session(self):
        session = _make("aid-2")
        await register_session(session)
        popped = await unregister_session("aid-2")
        assert popped is session
        assert await get_session("aid-2") is None

    async def test_unregister_unknown_returns_none(self):
        assert await unregister_session("unknown") is None

    async def test_duplicate_register_raises(self):
        await register_session(_make("aid-3"))
        with pytest.raises(RuntimeError):
            await register_session(_make("aid-3"))

    async def test_all_analysis_ids_returns_registered(self):
        await register_session(_make("a"))
        await register_session(_make("b"))
        ids = await all_analysis_ids()
        assert set(ids) == {"a", "b"}


class TestConcurrentRegistration:
    async def test_concurrent_create_produces_distinct_sessions(self):
        """C4-AC3: `REGISTRY[aid1] != REGISTRY[aid2]` after concurrent creates."""
        s1 = _make("aid-concurrent-1")
        s2 = _make("aid-concurrent-2")

        await asyncio.gather(register_session(s1), register_session(s2))

        got1 = await get_session("aid-concurrent-1")
        got2 = await get_session("aid-concurrent-2")
        assert got1 is s1
        assert got2 is s2
        assert got1 is not got2

    async def test_kill_removes_entry(self):
        """C4-AC3: `REGISTRY.get(aid1) is None` after `kill(aid1)`."""
        s = _make("aid-kill")
        await register_session(s)
        await unregister_session("aid-kill")
        assert await get_session("aid-kill") is None
