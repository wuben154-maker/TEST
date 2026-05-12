"""Regression test: consecutive requests (text, text, file, text) with same session_id.

User scenario:
- Request 1: text -> OK
- Request 2: text -> OK
- Request 3: PHP file -> BUG: returns previous result, does NOT trigger subagent
- Request 4: text -> BUG: triggers the 3rd request's file processing (delayed)

Run: pytest tests/test_consecutive_requests_regression.py -v -s
Requires: GOOGLE_API_KEY or ANTHROPIC_API_KEY or OPENAI_API_KEY
"""

import uuid

import pytest
from app.agents.deep_agent import stream_analyze_request
from app.config import get_settings


def _has_llm_key() -> bool:
    s = get_settings()
    return bool(
        getattr(s, "anthropic_api_key", None)
        or getattr(s, "openai_api_key", None)
        or getattr(s, "google_api_key", None)
    )


@pytest.mark.e2e
@pytest.mark.skipif(
    not _has_llm_key(),
    reason="No LLM API key. Set GOOGLE_API_KEY or ANTHROPIC_API_KEY or OPENAI_API_KEY.",
)
@pytest.mark.asyncio
async def test_consecutive_text_text_file_text_same_session():
    """Reproduce: text, text, PHP file, text - same session_id.

    Expected: Each request processes its own input. Request 3 (file) must trigger task/subagent.
    Bug: Request 3 returns old conclusion, no subagent. Request 4 triggers request 3's file processing.
    """
    session_id = f"regression-{uuid.uuid4().hex[:12]}"
    php_content = """<?php
echo $_GET['cmd'] ?? 'no input';
"""
    files_php = [
        {
            "filename": "shell.php",
            "content_type": "text/x-php",
            "content": php_content,
            "size": len(php_content),
        }
    ]

    all_rounds = []

    # Round 1: text
    events1 = []
    async for e in stream_analyze_request(
        text="这是什么类型的 IP 地址？8.8.8.8",
        files=None,
        session_id=session_id,
        ui_language="zh",
        input_language="zh",
    ):
        events1.append(e)
    all_rounds.append(("round1_text", events1))

    # Round 2: text
    events2 = []
    async for e in stream_analyze_request(
        text="再分析一下 1.1.1.1",
        files=None,
        session_id=session_id,
        ui_language="zh",
        input_language="zh",
    ):
        events2.append(e)
    all_rounds.append(("round2_text", events2))

    # Round 3: PHP file (BUG: should trigger subagent, but returns old result)
    events3 = []
    async for e in stream_analyze_request(
        text="分析这个 PHP 文件",
        files=files_php,
        session_id=session_id,
        ui_language="zh",
        input_language="zh",
    ):
        events3.append(e)
    all_rounds.append(("round3_file", events3))

    # Round 4: text (BUG: triggers round 3's file processing)
    events4 = []
    async for e in stream_analyze_request(
        text="总结一下刚才的分析",
        files=None,
        session_id=session_id,
        ui_language="zh",
        input_language="zh",
    ):
        events4.append(e)
    all_rounds.append(("round4_text", events4))

    # Diagnose: print event summary per round
    for name, events in all_rounds:
        types = [e.get("type") for e in events]
        task_calls = [e for e in events if e.get("type") == "tool_call" and e.get("toolName") == "task"]
        conclusions = [e for e in events if e.get("type") == "conclusion"]
        conclusion_preview = ""
        if conclusions:
            c = conclusions[0].get("content", "")[:80]
            conclusion_preview = f" | conclusion: {c}..."
        print(f"\n[{name}] events={len(events)} | task_calls={len(task_calls)}{conclusion_preview}")
        print(f"  types: {types[:15]}{'...' if len(types) > 15 else ''}")

    # Assert: Round 3 MUST have task (subagent) - this is the regression
    task_calls_r3 = [e for e in events3 if e.get("type") == "tool_call" and e.get("toolName") == "task"]
    assert len(task_calls_r3) >= 1, (
        f"REGRESSION: Round 3 (PHP file) must trigger task/subagent. "
        f"Got {len(task_calls_r3)} task calls. Events: {[e.get('type') for e in events3]}"
    )

    # Round 4 should NOT have task (it's a text summary request) - or if it does, it's the "delayed" bug
    # For now we only assert round 3
    print("\n[PASS] Round 3 correctly triggered subagent")


@pytest.mark.e2e
@pytest.mark.skipif(
    not _has_llm_key(),
    reason="No LLM API key.",
)
@pytest.mark.asyncio
async def test_round3_file_only_empty_message():
    """Round 3 with ONLY file, no text (message='') - like user uploads file without typing.

    Frontend sends message: '' and attachments: [file]. Does backend handle this?
    """
    session_id = f"regression-empty-{uuid.uuid4().hex[:12]}"
    php_content = """<?php
echo $_GET['cmd'] ?? 'no input';
"""
    files_php = [
        {"filename": "shell.php", "content_type": "text/x-php", "content": php_content, "size": len(php_content)},
    ]

    # Round 1, 2: text (same as before)
    async for _ in stream_analyze_request(
        text="分析 8.8.8.8", files=None, session_id=session_id, ui_language="zh", input_language="zh",
    ):
        pass
    async for _ in stream_analyze_request(
        text="分析 1.1.1.1", files=None, session_id=session_id, ui_language="zh", input_language="zh",
    ):
        pass

    # Round 3: ONLY file, empty text (simulates user submitting with just file, no input)
    events3 = []
    async for e in stream_analyze_request(
        text="",  # EMPTY - like frontend when user only uploads file
        files=files_php,
        session_id=session_id,
        ui_language="zh",
        input_language="zh",
    ):
        events3.append(e)

    task_calls = [e for e in events3 if e.get("type") == "tool_call" and e.get("toolName") == "task"]
    conclusions = [e for e in events3 if e.get("type") == "conclusion"]
    print(f"\n[round3_file_only] events={len(events3)} task_calls={len(task_calls)} conclusions={len(conclusions)}")
    print(f"  types: {[e.get('type') for e in events3]}")

    assert len(task_calls) >= 1, (
        f"Empty message + file must trigger subagent. Got task_calls={len(task_calls)}"
    )
    assert len(conclusions) >= 1, "Must have conclusion"
    print("[PASS] Empty message + file correctly triggers subagent")


@pytest.mark.e2e
@pytest.mark.skipif(
    not _has_llm_key(),
    reason="No LLM API key.",
)
@pytest.mark.asyncio
async def test_concurrent_requests_same_session():
    """Simulate user sending request 3 before request 2 completes (concurrent).

    Start request 2, immediately start request 3 (file) - do they race?
    """
    import asyncio
    session_id = f"regression-concurrent-{uuid.uuid4().hex[:12]}"
    php_content = """<?php echo $_GET['x'] ?? '';"""
    files_php = [{"filename": "x.php", "content_type": "text/x-php", "content": php_content, "size": len(php_content)}]

    # Round 1
    async for _ in stream_analyze_request(
        text="8.8.8.8 是什么", files=None, session_id=session_id, ui_language="zh", input_language="zh",
    ):
        pass

    # Start round 2 and round 3 CONCURRENTLY (simulate user clicking fast)
    events2, events3 = [], []

    async def run_round2():
        nonlocal events2
        async for e in stream_analyze_request(
            text="再分析 1.1.1.1", files=None, session_id=session_id, ui_language="zh", input_language="zh",
        ):
            events2.append(e)

    async def run_round3():
        nonlocal events3
        async for e in stream_analyze_request(
            text="分析这个 PHP 文件", files=files_php, session_id=session_id, ui_language="zh", input_language="zh",
        ):
            events3.append(e)

    await asyncio.gather(run_round2(), run_round3())

    task2 = [e for e in events2 if e.get("type") == "tool_call" and e.get("toolName") == "task"]
    task3 = [e for e in events3 if e.get("type") == "tool_call" and e.get("toolName") == "task"]
    print(f"\n[concurrent] round2 task_calls={len(task2)} events={len(events2)}")
    print(f"            round3 task_calls={len(task3)} events={len(events3)}")
    print(f"  round2 types: {[e.get('type') for e in events2][:10]}...")
    print(f"  round3 types: {[e.get('type') for e in events3][:10]}...")

    # With concurrent requests, we expect potential race. At least one should have proper flow.
    # Round 3 (file) should trigger task when it runs
    assert len(task2) + len(task3) >= 1, "At least one round should have task/subagent"
    print("[PASS] Concurrent test completed (race may cause unpredictable results)")


@pytest.mark.e2e
@pytest.mark.skipif(
    not _has_llm_key(),
    reason="No LLM API key. Set GOOGLE_API_KEY or ANTHROPIC_API_KEY or OPENAI_API_KEY.",
)
@pytest.mark.asyncio
async def test_no_delayed_task_or_missing_subagent_on_followup_text_after_file():
    """Regression guard for stale task replay:

    Same session, sequential requests:
    1) text
    2) file analysis
    3) plain text follow-up

    Expected:
    - Round 2 (file) triggers task/subagent.
    - Round 3 (plain text) must NOT replay round 2's task() call.
    - Round 3 must NOT emit missing-subagent-result error.
    """
    session_id = f"regression-no-delayed-{uuid.uuid4().hex[:12]}"
    php_content = """<?php
echo $_GET['cmd'] ?? 'no input';
"""
    files_php = [
        {
            "filename": "shell.php",
            "content_type": "text/x-php",
            "content": php_content,
            "size": len(php_content),
        }
    ]

    # Round 1: text warm-up
    async for _ in stream_analyze_request(
        text="先分析 8.8.8.8 的类型",
        files=None,
        session_id=session_id,
        ui_language="zh",
        input_language="zh",
    ):
        pass

    # Round 2: file request - should trigger subagent task
    events2 = []
    async for e in stream_analyze_request(
        text="分析这个 PHP 文件",
        files=files_php,
        session_id=session_id,
        ui_language="zh",
        input_language="zh",
    ):
        events2.append(e)

    # Round 3: plain text follow-up - must not replay previous task
    events3 = []
    async for e in stream_analyze_request(
        text="用一句话总结上一轮结果",
        files=None,
        session_id=session_id,
        ui_language="zh",
        input_language="zh",
    ):
        events3.append(e)

    task_calls_r2 = [e for e in events2 if e.get("type") == "tool_call" and e.get("toolName") == "task"]
    task_calls_r3 = [e for e in events3 if e.get("type") == "tool_call" and e.get("toolName") == "task"]
    missing_subagent_r3 = [
        e for e in events3
        if e.get("type") == "error" and e.get("id") == "missing-subagent-result"
    ]

    print(
        f"\n[no_delayed_task] round2 task_calls={len(task_calls_r2)} "
        f"| round3 task_calls={len(task_calls_r3)} "
        f"| round3 missing_subagent={len(missing_subagent_r3)}"
    )
    print(f"  round3 types: {[e.get('type') for e in events3]}")

    assert len(task_calls_r2) >= 1, "Round 2 (file) must trigger at least one task/subagent call"
    assert len(task_calls_r3) == 0, (
        "Round 3 (plain text follow-up) must not replay previous round's task/subagent call"
    )
    assert len(missing_subagent_r3) == 0, (
        "Round 3 must not emit missing-subagent-result for stale/replayed task context"
    )
