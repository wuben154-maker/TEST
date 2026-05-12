"""User message formatting for DB persistence (attachment names)."""

from app.services.message_persistence import (
    USER_MESSAGE_ATTACHMENT_LINE_PREFIX,
    _build_state_from_events,
    format_user_message_for_persistence,
)


def test_format_no_attachments():
    assert format_user_message_for_persistence("hello", []) == "hello"
    assert format_user_message_for_persistence("", []) == "[Attachment-only request]"


def test_format_text_and_files():
    out = format_user_message_for_persistence(
        "分析",
        [{"filename": "a.php"}, {"filename": "b.txt"}],
    )
    assert out == (
        "分析\n\n"
        f"{USER_MESSAGE_ATTACHMENT_LINE_PREFIX}a.php\n"
        f"{USER_MESSAGE_ATTACHMENT_LINE_PREFIX}b.txt"
    )


def test_format_attachments_only():
    out = format_user_message_for_persistence("", [{"filename": "x.eml"}])
    assert out == f"{USER_MESSAGE_ATTACHMENT_LINE_PREFIX}x.eml"


def test_resume_leg_without_task_plan_still_gets_workspace_blocks():
    """POST /analyze/resume only forwards resume SSE events — task_plan may be absent."""
    zh_report = (
        "大规模SOC环境下的自动化分诊\n"
        "在每日告警量达到10万级别的超大规模安全运营中心（SOC）中，模式已无法维系。"
    )
    events = [
        {"type": "step", "id": "s1", "label": "Running", "status": "running"},
        {"type": "conclusion", "id": "conclusion", "content": zh_report},
    ]
    state = _build_state_from_events(events, "[HITL resume]", ui_language="zh")
    assert state["blocks"]
    assert state["blocks"][0]["type"] == "analysis"
    assert "大规模SOC" in state["blocks"][0]["content"]


def test_regular_user_conclusion_only_does_not_synthesize_workspace_blocks():
    """Simple /analyze turns should keep the answer in chat (content), not mirror into blocks."""
    events = [
        {"type": "reasoning", "content": "thinking…"},
        {"type": "conclusion", "id": "conclusion", "content": "Final answer for the user."},
    ]
    state = _build_state_from_events(events, "What is 2+2?", ui_language="en")
    assert state["blocks"] == []
    assert state["content"] == "Final answer for the user."


def test_no_false_interrupt_message_when_task_plan_present():
    """Task-plan runs often have empty chat content but valid steps — not an interrupt."""
    events = [
        {
            "type": "task_plan",
            "plan": {"id": "p1", "tasks": [{"id": "t1", "title": "T", "status": "running", "steps": []}]},
        },
        {"type": "step", "id": "s1", "label": "Thinking", "status": "running"},
    ]
    state = _build_state_from_events(events, "user asks", ui_language="zh")
    assert state["task_plan"] is not None
    assert "分析过程中断" not in (state.get("content") or "")
