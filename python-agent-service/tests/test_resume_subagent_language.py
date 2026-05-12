"""Resume leg must align subagent output language with the original user request text."""

from langchain_core.messages import HumanMessage

from app.agents.deep_agent import resolve_subagent_language_for_resume


def test_resume_language_explicit_override():
    assert (
        resolve_subagent_language_for_resume(
            {"messages": [HumanMessage(content="hello")]},
            input_language="zh",
        )
        == "zh"
    )


def test_resume_language_auto_from_chinese_user_text():
    snap = {"messages": [HumanMessage(content="请做深度研究")]}
    assert resolve_subagent_language_for_resume(snap, input_language="auto") == "zh"


def test_resume_language_auto_from_english_user_text():
    snap = {"messages": [HumanMessage(content="Please research IOCs")]}
    assert resolve_subagent_language_for_resume(snap, input_language="auto") == "en"


def test_resume_language_content_blocks():
    snap = {
        "messages": [
            HumanMessage(
                content=[{"type": "text", "text": "分析这段日志"}],
            )
        ]
    }
    assert resolve_subagent_language_for_resume(snap, input_language="auto") == "zh"


def test_resume_language_empty_messages_falls_back_en():
    assert resolve_subagent_language_for_resume({}, input_language="auto") == "en"
