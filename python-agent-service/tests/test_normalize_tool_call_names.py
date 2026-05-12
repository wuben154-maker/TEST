"""Tests for NormalizeToolCallNamesMiddleware (repeated tool-name glue)."""

from __future__ import annotations

from langchain.agents.middleware.types import (
    ExtendedModelResponse,
    ModelRequest,
    ModelResponse,
)
from langchain_core.messages import AIMessage, ToolMessage

from app.middleware.normalize_tool_call_names import (
    NormalizeToolCallNamesMiddleware,
    _fix_ai_message,
    _normalize_stuttered_tool_name,
)


def test_normalize_stutter_when_task_allowed():
    allowed = {"task", "write_todos"}
    assert _normalize_stuttered_tool_name("tasktasktask", allowed) == "task"
    assert _normalize_stuttered_tool_name("TASKTASK", allowed) == "task"
    assert _normalize_stuttered_tool_name("task", allowed) == "task"


def test_normalize_write_todos_stutter():
    allowed = {"write_todos", "task"}
    assert (
        _normalize_stuttered_tool_name("write_todoswrite_todos", allowed)
        == "write_todos"
    )


def test_longest_allowed_name_matched_first():
    allowed = {"ab", "a"}
    assert _normalize_stuttered_tool_name("abab", allowed) == "ab"
    assert _normalize_stuttered_tool_name("aa", allowed) == "a"


def test_no_change_when_task_not_in_toolkit():
    allowed = {"write_todos"}
    assert _normalize_stuttered_tool_name("tasktasktask", allowed) == "tasktasktask"


def test_no_change_for_other_unknown_tools():
    allowed = {"task", "write_todos"}
    assert _normalize_stuttered_tool_name("unknown", allowed) == "unknown"


def test_fix_ai_message_tool_calls():
    allowed = {"task"}
    msg = AIMessage(
        content="",
        tool_calls=[
            {
                "id": "c1",
                "name": "tasktasktask",
                "args": {
                    "subagent_type": "general-purpose",
                    "description": "x",
                },
            }
        ],
    )
    fixed = _fix_ai_message(msg, allowed)
    assert fixed.tool_calls[0]["name"] == "task"
    assert fixed.tool_calls[0]["id"] == "c1"


def test_middleware_wrap_model_call_rewrites_response():
    tools = [{"name": "task", "description": "delegate"}]

    def handler(_req):
        return ModelResponse(
            result=[
                AIMessage(
                    content="",
                    tool_calls=[
                        {
                            "id": "x",
                            "name": "tasktask",
                            "args": {
                                "subagent_type": "general-purpose",
                                "description": "do it",
                            },
                        }
                    ],
                )
            ]
        )

    mw = NormalizeToolCallNamesMiddleware()
    req = ModelRequest(
        model=None,  # type: ignore[arg-type]
        messages=[],
        system_message=None,
        tool_choice=None,
        tools=tools,
        response_format=None,
        state={},  # type: ignore[arg-type]
        runtime=None,  # type: ignore[arg-type]
        model_settings={},
    )
    out = mw.wrap_model_call(req, handler)
    assert isinstance(out, ModelResponse)
    assert len(out.result) == 1
    assert isinstance(out.result[0], AIMessage)
    assert out.result[0].tool_calls[0]["name"] == "task"


def test_middleware_extended_model_response_preserved():
    tools = [{"name": "task"}]
    inner = ModelResponse(
        result=[
            AIMessage(
                content="",
                tool_calls=[{"id": "1", "name": "tasktasktask", "args": {}}],
            )
        ]
    )

    def handler(_req):
        return ExtendedModelResponse(model_response=inner, command=None)

    mw = NormalizeToolCallNamesMiddleware()
    req = ModelRequest(
        model=None,  # type: ignore[arg-type]
        messages=[ToolMessage(content="ok", tool_call_id="1", name="task")],
        system_message=None,
        tool_choice=None,
        tools=tools,
        response_format=None,
        state={},  # type: ignore[arg-type]
        runtime=None,  # type: ignore[arg-type]
        model_settings={},
    )
    out = mw.wrap_model_call(req, handler)
    assert isinstance(out, ExtendedModelResponse)
    assert out.model_response.result[0].tool_calls[0]["name"] == "task"
