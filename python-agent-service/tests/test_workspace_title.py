"""Tests for workspace tab title feature.

Covers:
1. write_todos tool_call: first task title → workspaceTitle (via write_todos_plan helper / persistence)
2. Message persistence: workspaceTitle extraction and state building
3. API: PATCH /messages/:id/title endpoint
"""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from langchain_core.messages import AIMessage, ToolMessage


# ============================================================
# 1. Stream adapter — write_todos toolInput → workspaceTitle (no task_plan SSE)
# ============================================================

async def _astream_yield(*events):
    for e in events:
        yield e


@pytest.fixture
def mock_agent():
    agent = MagicMock()
    agent.astream = MagicMock()
    agent.ainvoke = AsyncMock()
    return agent


@pytest.mark.asyncio
async def test_write_todos_derives_workspace_title_from_first_task(mock_agent):
    """workspaceTitle should be derived from the first task's content."""
    from app.parsers.deepagents_stream_adapter import adapt_astream_to_sse
    from app.parsers.write_todos_plan import build_task_plan_dict_from_write_todos_args

    ai_msg = AIMessage(
        content="",
        tool_calls=[{
            "id": "wt-1",
            "name": "write_todos",
            "args": {
                "todos": [
                    {"content": "Analyze phishing email headers", "status": "pending"},
                    {"content": "Check attachment for malware", "status": "pending"},
                ],
            },
        }],
    )
    tool_msg = ToolMessage(content="Updated todo list", tool_call_id="wt-1")
    final_msg = AIMessage(content="Analysis complete.")

    mock_agent.astream.return_value = _astream_yield(
        {"agent": {"messages": [ai_msg]}},
        {"tools": {"messages": [tool_msg]}},
        {"agent": {"messages": [final_msg]}},
    )

    events = []
    async for e in adapt_astream_to_sse(
        mock_agent, {"messages": []}, {"configurable": {}}, language="zh"
    ):
        events.append(e)

    assert not any(e["type"] == "task_plan" for e in events)
    wt = next(e for e in events if e.get("type") == "tool_call" and e.get("toolName") == "write_todos")
    plan = build_task_plan_dict_from_write_todos_args(wt.get("toolInput") or {})
    assert plan is not None
    assert plan["workspaceTitle"] == "Analyze phishing email headers"


@pytest.mark.asyncio
async def test_write_todos_single_task_workspace_title(mock_agent):
    """Single task: workspaceTitle equals that task's content."""
    from app.parsers.deepagents_stream_adapter import adapt_astream_to_sse
    from app.parsers.write_todos_plan import build_task_plan_dict_from_write_todos_args

    ai_msg = AIMessage(
        content="",
        tool_calls=[{
            "id": "wt-1",
            "name": "write_todos",
            "args": {
                "todos": [
                    {"content": "分析恶意PHP webshell代码", "status": "pending"},
                ],
            },
        }],
    )
    tool_msg = ToolMessage(content="Updated todo list", tool_call_id="wt-1")
    final_msg = AIMessage(content="Done.")

    mock_agent.astream.return_value = _astream_yield(
        {"agent": {"messages": [ai_msg]}},
        {"tools": {"messages": [tool_msg]}},
        {"agent": {"messages": [final_msg]}},
    )

    events = []
    async for e in adapt_astream_to_sse(
        mock_agent, {"messages": []}, {"configurable": {}}, language="zh"
    ):
        events.append(e)

    assert not any(e["type"] == "task_plan" for e in events)
    wt = next(e for e in events if e.get("type") == "tool_call" and e.get("toolName") == "write_todos")
    plan = build_task_plan_dict_from_write_todos_args(wt.get("toolInput") or {})
    assert plan is not None
    assert plan["workspaceTitle"] == "分析恶意PHP webshell代码"


@pytest.mark.asyncio
async def test_write_todos_empty_todos_no_workspace_title(mock_agent):
    """Empty todos list: no derivable plan / workspaceTitle."""
    from app.parsers.deepagents_stream_adapter import adapt_astream_to_sse
    from app.parsers.write_todos_plan import build_task_plan_dict_from_write_todos_args

    ai_msg = AIMessage(
        content="",
        tool_calls=[{
            "id": "wt-1",
            "name": "write_todos",
            "args": {"todos": []},
        }],
    )
    tool_msg = ToolMessage(content="ok", tool_call_id="wt-1")
    final_msg = AIMessage(content="Done.")

    mock_agent.astream.return_value = _astream_yield(
        {"agent": {"messages": [ai_msg]}},
        {"tools": {"messages": [tool_msg]}},
        {"agent": {"messages": [final_msg]}},
    )

    events = []
    async for e in adapt_astream_to_sse(
        mock_agent, {"messages": []}, {"configurable": {}}, language="en"
    ):
        events.append(e)

    assert not any(e["type"] == "task_plan" for e in events)
    wt = next(e for e in events if e.get("type") == "tool_call" and e.get("toolName") == "write_todos")
    plan = build_task_plan_dict_from_write_todos_args(wt.get("toolInput") or {})
    assert plan is None


# ============================================================
# 2. Message persistence — _build_state_from_events
# ============================================================

def test_build_state_extracts_workspace_title():
    """_build_state_from_events should extract workspaceTitle from task_plan event."""
    from app.services.message_persistence import _build_state_from_events

    events = [
        {
            "type": "task_plan",
            "id": "task-plan",
            "plan": {
                "id": "task-plan",
                "tasks": [{"id": "0", "title": "Analyze", "status": "pending"}],
                "workspaceTitle": "malware.exe 逆向分析",
            },
        },
        {"type": "conclusion", "id": "conclusion", "content": "Malware confirmed."},
    ]
    state = _build_state_from_events(events, "analyze this malware", ui_language="zh")
    assert state["workspace_title"] == "malware.exe 逆向分析"


def test_build_state_extracts_workspace_title_from_write_todos_tool_call():
    """_build_state_from_events should extract workspaceTitle from write_todos tool_call."""
    from app.services.message_persistence import _build_state_from_events

    events = [
        {
            "type": "tool_call",
            "id": "wt-1",
            "toolName": "write_todos",
            "toolInput": {
                "todos": [{"content": "From todos only", "status": "pending"}],
            },
        },
        {"type": "conclusion", "id": "conclusion", "content": "Done."},
    ]
    state = _build_state_from_events(events, "hello", ui_language="en")
    assert state["workspace_title"] == "From todos only"


def test_build_state_empty_workspace_title_when_missing():
    """_build_state_from_events returns empty workspace_title when not in plan."""
    from app.services.message_persistence import _build_state_from_events

    events = [
        {
            "type": "task_plan",
            "id": "task-plan",
            "plan": {
                "id": "task-plan",
                "tasks": [{"id": "0", "title": "Analyze", "status": "pending"}],
            },
        },
        {"type": "conclusion", "id": "conclusion", "content": "Done."},
    ]
    state = _build_state_from_events(events, "analyze this", ui_language="en")
    assert state["workspace_title"] == ""


def test_extended_thinking_steps_includes_workspace_title():
    """_extended_thinking_steps should include workspaceTitle in __extended."""
    from app.services.message_persistence import _extended_thinking_steps

    state = {
        "thinking_steps": [{"id": "s1", "label": "step1", "status": "running"}],
        "task_plan": {"id": "tp", "tasks": []},
        "understanding": None,
        "task_summary": "summary",
        "workspace_title": "test.eml 分析",
    }
    result = _extended_thinking_steps(state)
    assert result["__extended"]["workspaceTitle"] == "test.eml 分析"


def test_extended_thinking_steps_none_workspace_title():
    """_extended_thinking_steps with empty workspace_title should produce None."""
    from app.services.message_persistence import _extended_thinking_steps

    state = {
        "thinking_steps": [],
        "task_plan": None,
        "understanding": None,
        "task_summary": "",
        "workspace_title": "",
    }
    result = _extended_thinking_steps(state)
    assert result["__extended"]["workspaceTitle"] is None


# ============================================================
# 3. API — PATCH /messages/:id/title
# ============================================================

def _skip_if_not_local_db():
    """Skip test if database_mode is not 'local' or DB is unavailable."""
    try:
        from app.config import get_settings
        settings = get_settings()
        if settings.database_mode != "local":
            pytest.skip("Requires database_mode=local")
    except Exception:
        pytest.skip("Settings unavailable")


class _FakeConn:
    """Fake asyncpg connection for testing."""

    def __init__(self):
        self.execute = AsyncMock(return_value="UPDATE 1")


class _FakePool:
    """Fake asyncpg pool with async context manager acquire()."""

    def __init__(self, conn):
        self._conn = conn

    def acquire(self):
        return self

    async def __aenter__(self):
        return self._conn

    async def __aexit__(self, *args):
        pass


@pytest.mark.asyncio
async def test_patch_message_title_endpoint():
    """PATCH /messages/:id/title should update workspace_title via API."""
    from httpx import ASGITransport, AsyncClient

    from app.api.auth import get_current_user
    from app.main import app

    mock_user = {"id": "test-user-id", "email": "test@example.com"}
    app.dependency_overrides[get_current_user] = lambda: mock_user

    fake_conn = _FakeConn()
    fake_pool = _FakePool(fake_conn)

    async def fake_get_pg_pool():
        return fake_pool

    try:
        with patch("app.api.messages.get_settings") as mock_settings:
            mock_settings.return_value.database_mode = "local"

            with patch("app.api.messages.get_pg_pool", side_effect=fake_get_pg_pool):
                async with AsyncClient(
                    transport=ASGITransport(app=app),
                    base_url="http://test",
                ) as client:
                    resp = await client.patch(
                        "/messages/msg-123/title",
                        json={"title": "新标题"},
                    )

            assert resp.status_code == 200
            fake_conn.execute.assert_called_once()
            call_args = fake_conn.execute.call_args
            assert "workspace_title" in call_args[0][0]
            assert call_args[0][1] == "新标题"
            assert call_args[0][2] == "msg-123"
    finally:
        app.dependency_overrides.pop(get_current_user, None)
