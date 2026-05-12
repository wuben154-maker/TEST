"""Context memory: merge, injection caps, idempotency, feature flag."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.services.context_memory.merge import (
    format_derived_for_injection,
    merge_project_derived,
    truncate_for_summary,
)
from app.services.context_memory.pipeline import merge_after_message_persist


def test_merge_project_derived_dedupes_entities():
    prev = merge_project_derived(
        None,
        assistant_excerpt="Contact 1.2.3.4 and evil.com",
        request_id="a",
        llm_findings_delta=None,
        llm_summary_delta="first",
    )
    n2 = merge_project_derived(
        prev,
        assistant_excerpt="Again 1.2.3.4 and newhash deadbeefdeadbeefdeadbeefdeadbeef",
        request_id="b",
        llm_findings_delta=None,
        llm_summary_delta="second",
    )
    ips = [e for e in n2["entities"] if e["type"] == "ip"]
    assert len(ips) == 1
    assert n2["source_last_request_id"] == "b"


def test_truncate_for_summary_bounds():
    long = "x" * 100
    out = truncate_for_summary(long, 40)
    assert len(out) < len(long)
    assert "truncated" in out


def test_format_derived_for_injection_max_chars():
    payload = {
        "version": 1,
        "running_summary": "S" * 5000,
        "entities": [{"type": "ip", "value": "10.0.0.1"}],
        "findings": [],
        "open_questions": [],
    }
    text = format_derived_for_injection(payload, 200)
    assert len(text) <= 250


@pytest.mark.asyncio
async def test_merge_after_persist_skips_when_disabled(monkeypatch):
    monkeypatch.setattr(
        "app.services.context_memory.pipeline.get_settings",
        lambda: MagicMock(context_memory_enabled=False),
    )
    await merge_after_message_persist("p", "u", "r1", {"content": "x", "blocks": []})


@pytest.mark.asyncio
async def test_merge_after_persist_skips_empty_request_id(monkeypatch):
    monkeypatch.setattr(
        "app.services.context_memory.pipeline.get_settings",
        lambda: MagicMock(context_memory_enabled=True, database_mode="local"),
    )
    await merge_after_message_persist("p", "u", None, {"content": "x", "blocks": []})
    await merge_after_message_persist("p", "u", "  ", {"content": "x", "blocks": []})


@pytest.mark.asyncio
async def test_merge_idempotent_same_request(monkeypatch):
    settings = MagicMock(
        context_memory_enabled=True,
        database_mode="local",
        derived_layer_model=None,
        context_summary_input_max_chars=8000,
    )
    monkeypatch.setattr("app.services.context_memory.pipeline.get_settings", lambda: settings)

    with (
        patch(
            "app.services.context_memory.pipeline.merge_already_processed",
            new_callable=AsyncMock,
            return_value=False,
        ) as already,
        patch(
            "app.services.context_memory.pipeline.verify_project_owner",
            new_callable=AsyncMock,
            return_value=True,
        ),
        patch(
            "app.services.context_memory.pipeline.load_project_derived",
            new_callable=AsyncMock,
            return_value=None,
        ),
        patch(
            "app.services.context_memory.pipeline.save_project_derived",
            new_callable=AsyncMock,
        ) as save_proj,
        patch(
            "app.services.context_memory.pipeline.fetch_project_title",
            new_callable=AsyncMock,
            return_value="T",
        ),
        patch(
            "app.services.context_memory.pipeline.load_user_index",
            new_callable=AsyncMock,
            return_value=None,
        ),
        patch(
            "app.services.context_memory.pipeline.save_user_index",
            new_callable=AsyncMock,
        ),
        patch(
            "app.services.context_memory.pipeline.record_merge_processed",
            new_callable=AsyncMock,
        ),
    ):
        state = {"content": "8.8.8.8", "blocks": []}
        await merge_after_message_persist("pid", "uid", "rid-1", state)
        already.return_value = True
        await merge_after_message_persist("pid", "uid", "rid-1", state)
        assert save_proj.await_count == 1


@pytest.mark.asyncio
async def test_merge_llm_failure_still_saves_rules(monkeypatch):
    settings = MagicMock(
        context_memory_enabled=True,
        database_mode="local",
        derived_layer_model="google/gemini-3-flash-preview",
        context_summary_input_max_chars=8000,
    )
    monkeypatch.setattr("app.services.context_memory.pipeline.get_settings", lambda: settings)

    async def boom(*_a, **_k):
        raise RuntimeError("llm down")

    with (
        patch(
            "app.services.context_memory.pipeline.merge_already_processed",
            new_callable=AsyncMock,
            return_value=False,
        ),
        patch(
            "app.services.context_memory.pipeline.verify_project_owner",
            new_callable=AsyncMock,
            return_value=True,
        ),
        patch(
            "app.services.context_memory.pipeline.summarize_turn_delta",
            new_callable=AsyncMock,
            side_effect=boom,
        ),
        patch(
            "app.services.context_memory.pipeline.load_project_derived",
            new_callable=AsyncMock,
            return_value=None,
        ),
        patch(
            "app.services.context_memory.pipeline.save_project_derived",
            new_callable=AsyncMock,
        ) as save_proj,
        patch(
            "app.services.context_memory.pipeline.fetch_project_title",
            new_callable=AsyncMock,
            return_value="T",
        ),
        patch(
            "app.services.context_memory.pipeline.load_user_index",
            new_callable=AsyncMock,
            return_value=None,
        ),
        patch(
            "app.services.context_memory.pipeline.save_user_index",
            new_callable=AsyncMock,
        ),
        patch(
            "app.services.context_memory.pipeline.record_merge_processed",
            new_callable=AsyncMock,
        ),
    ):
        await merge_after_message_persist(
            "pid", "uid", "rid-2", {"content": "9.9.9.9", "blocks": []}
        )
        save_proj.assert_awaited()
        args = save_proj.await_args[0]
        payload = args[2]
        assert any(e.get("value") == "9.9.9.9" for e in payload.get("entities", []))


@pytest.mark.asyncio
async def test_fetch_hydration_prefix_respects_flag(monkeypatch):
    from app.services.context_memory.pipeline import fetch_hydration_prefix

    monkeypatch.setattr(
        "app.services.context_memory.pipeline.get_settings",
        lambda: MagicMock(
            context_hydrate_enabled=False,
            context_memory_enabled=True,
        ),
    )
    out = await fetch_hydration_prefix("p", "u")
    assert out == ""

    monkeypatch.setattr(
        "app.services.context_memory.pipeline.get_settings",
        lambda: MagicMock(
            context_hydrate_enabled=True,
            context_memory_enabled=True,
            database_mode="local",
            context_inject_max_chars=500,
            context_hydrate_max_turns=2,
        ),
    )
    with patch(
        "app.services.context_memory.pipeline.fetch_recent_messages_for_hydrate",
        new_callable=AsyncMock,
        return_value=[("user", "hi"), ("assistant", "hello")],
    ):
        h = await fetch_hydration_prefix("p", "u")
    assert h.startswith("[Hydrated from DB history]")
    assert "User:" in h


@pytest.mark.asyncio
async def test_merge_denied_when_not_owner(monkeypatch):
    settings = MagicMock(
        context_memory_enabled=True,
        database_mode="local",
        derived_layer_model=None,
        context_summary_input_max_chars=8000,
    )
    monkeypatch.setattr("app.services.context_memory.pipeline.get_settings", lambda: settings)

    with (
        patch(
            "app.services.context_memory.pipeline.merge_already_processed",
            new_callable=AsyncMock,
            return_value=False,
        ),
        patch(
            "app.services.context_memory.pipeline.verify_project_owner",
            new_callable=AsyncMock,
            return_value=False,
        ),
        patch(
            "app.services.context_memory.pipeline.save_project_derived",
            new_callable=AsyncMock,
        ) as save_proj,
    ):
        await merge_after_message_persist(
            "pid", "uid", "rid-3", {"content": "1.1.1.1", "blocks": []}
        )
        save_proj.assert_not_awaited()
