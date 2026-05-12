"""Tests for search_history tool and repository search."""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest

from app.analyze_request_context import (
    reset_analyze_request_context,
    set_analyze_request_context,
)
from app.tools.conversation_history_tools import search_history
from app.tools.common.tools import create_common_tools


@pytest.mark.asyncio
async def test_search_history_no_context():
    out = await search_history(query="x", limit=5)
    assert out["ok"] is False
    assert out["error"] == "no_request_context"


@pytest.mark.asyncio
async def test_search_history_with_context_calls_repo():
    ut, pt, rt, st = set_analyze_request_context(
        user_id="550e8400-e29b-41d4-a716-446655440000",
        project_id="660e8400-e29b-41d4-a716-446655440001",
        request_id="",
        session_id="sess-test",
    )
    try:
        fake = {
            "ok": True,
            "matches": [
                {
                    "id": "m1",
                    "type": "user",
                    "request_id": "r1",
                    "created_at": "2026-01-01T00:00:00",
                    "content_preview": "hello",
                    "truncated": False,
                }
            ],
        }
        with patch(
            "app.tools.conversation_history_tools.search_project_messages",
            new_callable=AsyncMock,
            return_value=fake,
        ) as mock_search:
            out = await search_history(query="hel", limit=3, request_id="r1")
        assert out == fake
        mock_search.assert_awaited_once()
        kwargs = mock_search.call_args.kwargs
        assert kwargs["query"] == "hel"
        assert kwargs["limit"] == 3
        assert kwargs["request_id_filter"] == "r1"
    finally:
        reset_analyze_request_context(ut, pt, rt, st)


@pytest.mark.asyncio
async def test_search_project_messages_access_denied():
    from app.services.context_memory import repository as repo

    with patch.object(repo, "verify_project_owner", new_callable=AsyncMock, return_value=False):
        out = await repo.search_project_messages(
            "660e8400-e29b-41d4-a716-446655440001",
            "550e8400-e29b-41d4-a716-446655440000",
            query=None,
            limit=5,
            request_id_filter=None,
        )
    assert out["ok"] is False
    assert out["error"] == "access_denied"


def test_create_common_tools_includes_search_history():
    names = {t.name for t in create_common_tools(include_hitl=False)}
    assert "search_history" in names


def test_search_history_description_comes_from_tool_registry_yaml():
    """LLM description must be loaded from config/tool_presentation.yaml, not hardcoded in code."""
    tools = create_common_tools(include_hitl=False)
    sh = next(t for t in tools if t.name == "search_history")
    assert sh.description and len(sh.description.strip()) > 40
