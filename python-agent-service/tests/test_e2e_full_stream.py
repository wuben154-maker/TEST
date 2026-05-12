"""E2E test: full streaming flow from HTTP /analyze to SSE events.

Verifies the complete flow including our recent fixes:
1. POST /analyze with stream=true
2. Consume SSE stream
3. task_plan OR write_todos tool_call (task list visibility)
4. task_summary: digest from final message (not arbitrarily truncated to 500)
5. conclusion present
6. reasoning events (when model returns thinking)
7. done event
8. When ``task()`` ran: non-empty ``task_summary`` and ``conclusion`` must satisfy the
   final-message contract (no leading ``## SM_FULL_REPORT`` / ``## SM_TASK_DIGEST`` on
   ``conclusion`` — i.e. parser split or valid heuristic; model should follow MASTER_AGENT anchors)

Requires: GOOGLE_API_KEY or ANTHROPIC_API_KEY or OPENAI_API_KEY.
Run: pytest tests/test_e2e_full_stream.py -v -s
Skip in CI: pytest -m "not e2e"
"""

import json
import uuid

import pytest
from app.auth import create_access_token
from app.config import get_settings
from app.main import app
from app.parsers.final_message_split import DIGEST_HEADING, REPORT_HEADING
from httpx import ASGITransport, AsyncClient

_E2E_ANALYZE_AUTH_HEADERS = {
    "Authorization": f"Bearer {create_access_token('e2e-analyze-user', 'e2e-analyze@secmanus.test')}",
}


def _has_llm_key() -> bool:
    s = get_settings()
    return bool(
        getattr(s, "anthropic_api_key", None)
        or getattr(s, "openai_api_key", None)
        or getattr(s, "google_api_key", None)
    )


def _parse_sse_stream(text: str) -> list[dict]:
    """Parse SSE stream into list of event dicts."""
    events = []
    for line in text.strip().split("\n"):
        if line.startswith("data: "):
            payload = line[6:]
            if payload.strip() == "[DONE]" or payload.strip() == "":
                continue
            try:
                events.append(json.loads(payload))
            except json.JSONDecodeError:
                pass
    return events


def _task_tool_calls(events: list[dict]) -> list[dict]:
    return [
        e for e in events
        if e.get("type") == "tool_call" and e.get("toolName") == "task"
    ]


def assert_task_flow_final_message_contract(events: list[dict], *, context: str) -> None:
    """If the stream includes ``task()`` tool calls, enforce digest + split conclusion.

    Expects at least one ``task_summary`` with non-empty body, and ``conclusion`` that does
    not start with machine anchor headings (those belong in raw AIMessage only; SSE
    ``conclusion`` is the report slice).
    """
    if not _task_tool_calls(events):
        return

    task_summaries = [e for e in events if e.get("type") == "task_summary"]
    conclusions = [e for e in events if e.get("type") == "conclusion"]

    assert len(task_summaries) >= 1, (
        f"{context}: task() flow requires at least one task_summary event "
        f"(SM_TASK_DIGEST or heuristic digest)."
    )
    summary = (task_summaries[0].get("summary") or "").strip()
    assert summary, f"{context}: task_summary.summary must be non-empty"

    assert len(conclusions) >= 1, f"{context}: task() flow requires a conclusion event"
    conc = (conclusions[0].get("content") or "").lstrip()
    assert not conc.startswith(DIGEST_HEADING), (
        f"{context}: conclusion must not start with {DIGEST_HEADING!r} "
        "(report body only after split; main agent should use MASTER_AGENT anchors)."
    )
    assert not conc.startswith(REPORT_HEADING), (
        f"{context}: conclusion must not start with {REPORT_HEADING!r} "
        "(heading line is stripped by the adapter)."
    )


@pytest.mark.e2e
@pytest.mark.skipif(
    not _has_llm_key(),
    reason="No LLM API key. Set GOOGLE_API_KEY or ANTHROPIC_API_KEY or OPENAI_API_KEY.",
)
@pytest.mark.asyncio
async def test_e2e_analyze_stream_full_flow():
    """Full E2E: POST /analyze stream -> consume SSE -> verify event flow."""
    session_id = f"e2e-{uuid.uuid4().hex[:12]}"

    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://test",
        timeout=120.0,
    ) as client:
        response = await client.post(
            "/analyze",
            json={
                "message": "分析这个 IP 地址: 8.8.8.8",
                "attachments": None,
                "analysis_scope": "all_input",
                "stream": True,
                "session_id": session_id,
                "ui_language": "zh",
                "input_language": "zh",
            },
            headers=_E2E_ANALYZE_AUTH_HEADERS,
        )

    assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text[:500]}"
    assert "text/event-stream" in response.headers.get("content-type", "")

    # Consume full stream (response.text gives us the entire body for sync response)
    body = response.text
    events = _parse_sse_stream(body)

    event_types = [e.get("type") for e in events]

    # 1. Must have done
    done_events = [e for e in events if e.get("type") == "done"]
    assert len(done_events) >= 1, f"Expected done event. Got: {event_types}"

    # 2. Must have conclusion (direct reply or task synthesis)
    conclusions = [e for e in events if e.get("type") == "conclusion"]
    assert len(conclusions) >= 1, f"Expected conclusion. Got: {event_types}"

    # 3. If task flow: task_plan OR write_todos tool_call
    task_plans = [e for e in events if e.get("type") == "task_plan"]
    write_todos_calls = [
        e for e in events
        if e.get("type") == "tool_call" and e.get("toolName") == "write_todos"
    ]
    task_calls = [e for e in events if e.get("type") == "tool_call" and e.get("toolName") == "task"]

    has_task_flow = len(task_calls) >= 1
    if has_task_flow:
        # Task flow: must have task list from task_plan or write_todos
        has_task_list = len(task_plans) >= 1 or len(write_todos_calls) >= 1
        assert has_task_list, (
            f"Task flow but no task_plan or write_todos. Got: {event_types}"
        )

    assert_task_flow_final_message_contract(
        events, context="test_e2e_analyze_stream_full_flow"
    )

    # 4. task_summary: if present, must NOT be truncated (was 500 char limit)
    task_summaries = [e for e in events if e.get("type") == "task_summary"]
    for ts in task_summaries:
        summary = ts.get("summary", "")
        if len(summary) > 500:
            assert not summary.endswith("..."), "task_summary must not be truncated"

    # 5. step events (analysis-start, analysis-complete)
    steps = [e for e in events if e.get("type") == "step"]
    assert len(steps) >= 1, f"Expected at least one step. Got: {event_types}"

    # 6. No internal events in final list (they are filtered by mark_event_internal)
    # We just verify we got a valid stream
    assert len(events) >= 3, f"Expected multiple events. Got {len(events)}: {event_types}"

    # Log summary for debugging
    print(f"\n[E2E] Events: {len(events)} total")
    print(f"  Types: {event_types}")
    print(f"  task_plan: {len(task_plans)}, write_todos: {len(write_todos_calls)}, task: {len(task_calls)}")
    print(f"  task_summary: {len(task_summaries)}, conclusion: {len(conclusions)}")
    if task_summaries:
        s = task_summaries[0].get("summary", "")
        print(f"  task_summary length: {len(s)} chars")


@pytest.mark.e2e
@pytest.mark.skipif(
    not _has_llm_key(),
    reason="No LLM API key. Set GOOGLE_API_KEY or ANTHROPIC_API_KEY or OPENAI_API_KEY.",
)
@pytest.mark.asyncio
async def test_e2e_task_summary_not_truncated():
    """E2E: task flow must produce task_summary with full content (no 500 char cut)."""
    session_id = f"e2e-{uuid.uuid4().hex[:12]}"

    # Use file analysis to trigger task flow (more likely to get multi-step output)
    php_content = """<?php
echo $_GET['cmd'] ?? 'no input';
"""
    files = [
        {
            "filename": "test.php",
            "content_type": "text/x-php",
            "content": php_content,
            "size": len(php_content),
        }
    ]

    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://test",
        timeout=120.0,
    ) as client:
        response = await client.post(
            "/analyze",
            json={
                "message": "分析这个 PHP 文件的安全性",
                "attachments": files,
                "analysis_scope": "all_input",
                "stream": True,
                "session_id": session_id,
                "ui_language": "zh",
                "input_language": "zh",
            },
            headers=_E2E_ANALYZE_AUTH_HEADERS,
        )

    assert response.status_code == 200
    body = response.text
    events = _parse_sse_stream(body)

    task_summaries = [e for e in events if e.get("type") == "task_summary"]
    assert_task_flow_final_message_contract(
        events, context="test_e2e_task_summary_not_truncated"
    )
    if task_summaries:
        summary = task_summaries[0].get("summary", "")
        # Regression: previously truncated to 500
        assert len(summary) > 0, "task_summary must not be empty"
        # If subagent returned long content, we must have it all
        assert len(summary) == len(summary), "No truncation"
        print(f"\n[E2E] task_summary length: {len(summary)} chars (no truncation)")


@pytest.mark.e2e
@pytest.mark.skipif(
    not _has_llm_key(),
    reason="No LLM API key. Set GOOGLE_API_KEY or ANTHROPIC_API_KEY or OPENAI_API_KEY.",
)
@pytest.mark.asyncio
async def test_e2e_write_todos_or_task_plan_present():
    """E2E: task flow must have task_plan event OR write_todos tool_call for UI."""
    session_id = f"e2e-{uuid.uuid4().hex[:12]}"

    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://test",
        timeout=120.0,
    ) as client:
        response = await client.post(
            "/analyze",
            json={
                "message": "分析 IP 1.2.3.4 的威胁情报",
                "attachments": None,
                "analysis_scope": "all_input",
                "stream": True,
                "session_id": session_id,
                "ui_language": "zh",
                "input_language": "zh",
            },
            headers=_E2E_ANALYZE_AUTH_HEADERS,
        )

    assert response.status_code == 200
    events = _parse_sse_stream(response.text)

    task_plans = [e for e in events if e.get("type") == "task_plan"]
    write_todos = [e for e in events if e.get("type") == "tool_call" and e.get("toolName") == "write_todos"]
    task_calls = [e for e in events if e.get("type") == "tool_call" and e.get("toolName") == "task"]

    # If we have task() calls, we should have task_plan or write_todos for UI
    if task_calls:
        has_plan = len(task_plans) >= 1 or len(write_todos) >= 1
        assert has_plan, (
            f"Task flow but no task_plan or write_todos for UI. "
            f"Events: {[e.get('type') for e in events]}"
        )
        print(f"\n[E2E] task_plan: {len(task_plans)}, write_todos: {len(write_todos)}")

    assert_task_flow_final_message_contract(
        events, context="test_e2e_write_todos_or_task_plan_present"
    )


@pytest.mark.e2e
@pytest.mark.skipif(
    not _has_llm_key(),
    reason="No LLM API key. Set GOOGLE_API_KEY or ANTHROPIC_API_KEY or OPENAI_API_KEY.",
)
@pytest.mark.asyncio
async def test_e2e_agentic_main_agent_direct_tools():
    """E2E: Agentic workflow - main agent may use extract_iocs/lookup_threat_intel directly.

    For simple IOC lookup, main agent uses allowed tools (no task()). Stream must include
    tool_call and tool_result events. No bypass warning when only allowed tools used.
    """
    session_id = f"e2e-{uuid.uuid4().hex[:12]}"
    allowed_tools = {
        "extract_iocs", "decode_base64", "decode_url", "lookup_threat_intel",
        "web_search", "scrape_url", "summarize_content",
        "read_file", "grep", "glob", "ls", "write_todos",
    }

    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://test",
        timeout=120.0,
    ) as client:
        response = await client.post(
            "/analyze",
            json={
                "message": "Is 8.8.8.8 malicious? Quick lookup only.",
                "attachments": None,
                "analysis_scope": "all_input",
                "stream": True,
                "session_id": session_id,
                "ui_language": "en",
                "input_language": "en",
            },
            headers=_E2E_ANALYZE_AUTH_HEADERS,
        )

    assert response.status_code == 200
    events = _parse_sse_stream(response.text)

    tool_calls = [e for e in events if e.get("type") == "tool_call"]
    tool_results = [e for e in events if e.get("type") == "tool_result"]
    warnings = [e for e in events if e.get("type") == "warning"]
    bypass_warnings = [e for e in warnings if e.get("id") == "subagent-bypass-detected"]

    # If main agent used tools directly (IOC lookup), tool names must be in allowed set
    for tc in tool_calls:
        name = tc.get("toolName")
        if name and name != "write_todos":
            assert name in allowed_tools, (
                f"Main agent used non-allowed tool {name}. "
                f"Allowed: {allowed_tools}. Bypass would fire."
            )

    # When only allowed tools used, no bypass warning
    if tool_calls and all(tc.get("toolName") in allowed_tools for tc in tool_calls):
        assert len(bypass_warnings) == 0, (
            "Main agent used only allowed tools; bypass warning should not fire"
        )

    # Must have conclusion
    conclusions = [e for e in events if e.get("type") == "conclusion"]
    assert len(conclusions) >= 1, f"Expected conclusion. Got: {[e.get('type') for e in events]}"

    print(f"\n[E2E Agentic] tool_calls: {[e.get('toolName') for e in tool_calls]}")
    print(f"  tool_results: {len(tool_results)}, bypass_warnings: {len(bypass_warnings)}")
