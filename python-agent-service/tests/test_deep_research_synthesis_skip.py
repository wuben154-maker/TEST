"""Tests for DeepResearchSynthesisSkipMiddleware."""

from langchain_core.messages import AIMessage, HumanMessage, ToolMessage

from app.middleware.deep_research_synthesis_skip import (
    DeepResearchSynthesisSkipMiddleware,
    should_skip_main_model_after_deep_research_only_task,
)


def test_skip_true_single_deep_research_task():
    msgs = [
        HumanMessage(content="research X"),
        AIMessage(
            content="",
            tool_calls=[
                {
                    "id": "tc-1",
                    "name": "task",
                    "args": {
                        "subagent_type": "deep-research",
                        "description": "full topic",
                    },
                }
            ],
        ),
        ToolMessage(content="big result", tool_call_id="tc-1", name="task"),
    ]
    assert should_skip_main_model_after_deep_research_only_task(msgs) is True


def test_skip_true_two_parallel_deep_research():
    msgs = [
        AIMessage(
            content="",
            tool_calls=[
                {
                    "id": "a",
                    "name": "task",
                    "args": {
                        "subagent_type": "deep-research",
                        "description": "t1",
                    },
                },
                {
                    "id": "b",
                    "name": "task",
                    "args": {
                        "subagent_type": "deep_research",
                        "description": "t2",
                    },
                },
            ],
        ),
        ToolMessage(content="r1", tool_call_id="a", name="task"),
        ToolMessage(content="r2", tool_call_id="b", name="task"),
    ]
    assert should_skip_main_model_after_deep_research_only_task(msgs) is True


def test_skip_false_mixed_with_general_purpose():
    msgs = [
        AIMessage(
            content="",
            tool_calls=[
                {
                    "id": "a",
                    "name": "task",
                    "args": {
                        "subagent_type": "deep-research",
                        "description": "t1",
                    },
                },
                {
                    "id": "b",
                    "name": "task",
                    "args": {
                        "subagent_type": "general-purpose",
                        "description": "t2",
                    },
                },
            ],
        ),
        ToolMessage(content="r1", tool_call_id="a", name="task"),
        ToolMessage(content="r2", tool_call_id="b", name="task"),
    ]
    assert should_skip_main_model_after_deep_research_only_task(msgs) is False


def test_skip_true_write_todos_plus_deep_research_task():
    """Same AIMessage often bundles write_todos + task(deep-research); synthesis must still skip."""
    msgs = [
        AIMessage(
            content="",
            tool_calls=[
                {
                    "id": "w",
                    "name": "write_todos",
                    "args": {"todos": []},
                },
                {
                    "id": "t",
                    "name": "task",
                    "args": {"subagent_type": "deep-research", "description": "x"},
                },
            ],
        ),
        ToolMessage(content="ok", tool_call_id="w", name="write_todos"),
        ToolMessage(content="ok", tool_call_id="t", name="task"),
    ]
    assert should_skip_main_model_after_deep_research_only_task(msgs) is True


def test_skip_false_write_todos_plus_general_task():
    msgs = [
        AIMessage(
            content="",
            tool_calls=[
                {
                    "id": "w",
                    "name": "write_todos",
                    "args": {"todos": []},
                },
                {
                    "id": "t",
                    "name": "task",
                    "args": {"subagent_type": "general-purpose", "description": "x"},
                },
            ],
        ),
        ToolMessage(content="ok", tool_call_id="w", name="write_todos"),
        ToolMessage(content="ok", tool_call_id="t", name="task"),
    ]
    assert should_skip_main_model_after_deep_research_only_task(msgs) is False


def test_skip_false_last_message_not_tool():
    tc = {
        "id": "t",
        "name": "task",
        "args": {"subagent_type": "deep-research", "description": "x"},
    }
    msgs = [
        AIMessage(content="", tool_calls=[tc]),
        ToolMessage(content="ok", tool_call_id="t", name="task"),
        AIMessage(content="follow up"),
    ]
    assert should_skip_main_model_after_deep_research_only_task(msgs) is False


def test_middleware_wrap_skips_handler():
    called: list[str] = []

    def handler(_req):
        called.append("handler")
        from langchain.agents.middleware.types import ModelResponse
        from langchain_core.messages import AIMessage as AM

        return ModelResponse(result=[AM(content="from model")])

    from langchain.agents.middleware.types import ModelRequest

    mw = DeepResearchSynthesisSkipMiddleware()
    msgs = [
        AIMessage(
            content="",
            tool_calls=[
                {
                    "id": "t",
                    "name": "task",
                    "args": {"subagent_type": "deep-research", "description": "x"},
                }
            ],
        ),
        ToolMessage(content="sub", tool_call_id="t", name="task"),
    ]
    req = ModelRequest(
        model=None,  # type: ignore[arg-type]
        messages=msgs,
        system_message=None,
        tool_choice=None,
        tools=[],
        response_format=None,
        state={},  # type: ignore[arg-type]
        runtime=None,  # type: ignore[arg-type]
        model_settings={},
    )
    out = mw.wrap_model_call(req, handler)
    assert called == []
    assert len(out.result) == 1
    assert out.result[0].content == ""
