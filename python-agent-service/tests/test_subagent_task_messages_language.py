"""Subagent task() initial messages include a response-language SystemMessage."""

from langchain_core.messages import HumanMessage, SystemMessage
from app._vendor.deepagents.middleware.subagents import build_subagent_task_messages


class _FakeRuntime:
    def __init__(self, configurable: dict | None = None):
        self.config = {"configurable": configurable or {}}


def test_build_subagent_task_messages_uses_subagent_response_language():
    rt = _FakeRuntime({"subagent_response_language": "zh"})
    msgs = build_subagent_task_messages('{"taskObjective":"x"}', rt)
    assert len(msgs) == 2
    assert isinstance(msgs[0], SystemMessage)
    assert "简体中文" in (msgs[0].content or "")
    assert isinstance(msgs[1], HumanMessage)
    assert msgs[1].content == '{"taskObjective":"x"}'


def test_build_subagent_task_messages_falls_back_to_sse_ui_language():
    rt = _FakeRuntime({"sse_ui_language": "ja"})
    msgs = build_subagent_task_messages("payload", rt)
    assert "Japanese" in (msgs[0].content or "")


def test_build_subagent_task_messages_default_english():
    rt = _FakeRuntime({})
    msgs = build_subagent_task_messages("payload", rt)
    assert "**English**" in (msgs[0].content or "")


def test_build_subagent_task_messages_zh_hant():
    rt = _FakeRuntime({"subagent_response_language": "zh-TW"})
    msgs = build_subagent_task_messages("payload", rt)
    assert "繁體中文" in (msgs[0].content or "")


def test_build_subagent_task_messages_prefers_subagent_over_sse():
    rt = _FakeRuntime({"subagent_response_language": "ko", "sse_ui_language": "en"})
    msgs = build_subagent_task_messages("payload", rt)
    assert "Korean" in (msgs[0].content or "")
