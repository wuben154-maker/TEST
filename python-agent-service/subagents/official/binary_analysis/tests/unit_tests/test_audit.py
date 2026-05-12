"""Tests for binary_analysis.audit — C1-AC2 and C1-AC3."""

import asyncio
import json
import uuid
from pathlib import Path

from audit import (
    analysis_context,
    current_analysis_id,
    log_indicator_write,
    log_llm_request,
    log_sandbox_lifecycle,
    log_skill_read,
    log_tool_call,
)

# ---------------------------------------------------------------------------
# C1-AC2: context propagation
# ---------------------------------------------------------------------------


def test_current_analysis_id_default_empty():
    assert current_analysis_id() == ""


def test_analysis_context_sets_id():
    aid = str(uuid.uuid4())
    with analysis_context(aid):
        assert current_analysis_id() == aid


def test_analysis_context_restores_after_exit():
    outer = str(uuid.uuid4())
    inner = str(uuid.uuid4())
    with analysis_context(outer):
        with analysis_context(inner):
            assert current_analysis_id() == inner
        assert current_analysis_id() == outer


def test_analysis_context_yields_id():
    aid = str(uuid.uuid4())
    with analysis_context(aid) as returned:
        assert returned == aid


def test_analysis_context_restores_on_exception():
    aid = str(uuid.uuid4())
    try:
        with analysis_context(aid):
            raise RuntimeError("boom")
    except RuntimeError:
        pass
    assert current_analysis_id() == ""


def test_concurrent_contexts_are_isolated():
    """Each asyncio task should see its own analysis_id."""
    results: dict[int, str] = {}

    async def worker(idx: int, aid: str) -> None:
        with analysis_context(aid):
            await asyncio.sleep(0)  # yield to other tasks
            results[idx] = current_analysis_id()

    aids = [str(uuid.uuid4()) for _ in range(5)]

    async def run() -> None:
        await asyncio.gather(*[worker(i, a) for i, a in enumerate(aids)])

    asyncio.run(run())

    for i, expected in enumerate(aids):
        assert results[i] == expected, (
            f"task {i}: expected {expected}, got {results[i]}"
        )


# ---------------------------------------------------------------------------
# C1-AC3: JSONL output helpers
# ---------------------------------------------------------------------------


def _read_entries(path: Path) -> list[dict]:
    return [
        json.loads(line)
        for line in path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]


def test_log_tool_call_writes_valid_json(tmp_path):
    aid = str(uuid.uuid4())
    with analysis_context(aid, log_dir=tmp_path):
        log_tool_call(
            "FileIdentifyTool",
            {"path": "/tmp/sample.bin"},
            {"format": "PE"},
            42.5,
            log_dir=tmp_path,
        )

    entries = _read_entries(tmp_path / f"{aid}.audit.jsonl")
    assert len(entries) == 1
    e = entries[0]
    assert e["event_type"] == "tool_call"
    assert e["analysis_id"] == aid
    assert "timestamp_iso" in e
    assert e["tool_name"] == "FileIdentifyTool"
    assert e["duration_ms"] == 42.5
    assert e["success"] is True


def test_log_tool_call_failure(tmp_path):
    aid = str(uuid.uuid4())
    with analysis_context(aid, log_dir=tmp_path):
        log_tool_call(
            "BashTool",
            {},
            None,
            100.0,
            success=False,
            error_code="TOOL_CRASH",
            log_dir=tmp_path,
        )

    entries = _read_entries(tmp_path / f"{aid}.audit.jsonl")
    assert entries[0]["success"] is False
    assert entries[0]["error_code"] == "TOOL_CRASH"


def test_log_llm_request_writes_valid_json(tmp_path):
    aid = str(uuid.uuid4())
    with analysis_context(aid, log_dir=tmp_path):
        log_llm_request(
            "claude-opus-4-5", "quick_scan", 1000, 500, 2000.0, log_dir=tmp_path
        )

    entries = _read_entries(tmp_path / f"{aid}.audit.jsonl")
    assert len(entries) == 1
    e = entries[0]
    assert e["event_type"] == "llm_request"
    assert e["model"] == "claude-opus-4-5"
    assert e["stage"] == "quick_scan"
    assert e["prompt_tokens"] == 1000
    assert e["completion_tokens"] == 500


def test_log_sandbox_lifecycle_writes_valid_json(tmp_path):
    aid = str(uuid.uuid4())
    sb_id = "sb_abc123"
    with analysis_context(aid, log_dir=tmp_path):
        log_sandbox_lifecycle(
            "create",
            sb_id,
            "binary-analysis-ubuntu-2204",
            duration_ms=3500.0,
            log_dir=tmp_path,
        )

    entries = _read_entries(tmp_path / f"{aid}.audit.jsonl")
    assert len(entries) == 1
    e = entries[0]
    assert e["event_type"] == "sandbox_lifecycle"
    assert e["sandbox_id"] == sb_id
    assert e["event"] == "create"
    assert e["fallback_used"] is False


def test_log_indicator_write_writes_valid_json(tmp_path):
    aid = str(uuid.uuid4())
    with analysis_context(aid, log_dir=tmp_path):
        log_indicator_write(
            "IND-001", "file_meta", "fact", "INFO", "FR-01", log_dir=tmp_path
        )

    entries = _read_entries(tmp_path / f"{aid}.audit.jsonl")
    assert len(entries) == 1
    e = entries[0]
    assert e["event_type"] == "indicator_write"
    assert e["indicator_id"] == "IND-001"
    assert e["bucket"] == "file_meta"
    assert e["kind"] == "fact"


def test_log_skill_read_writes_valid_json(tmp_path):
    aid = str(uuid.uuid4())
    with analysis_context(aid, log_dir=tmp_path):
        log_skill_read(
            "reverse-engineering-malware-with-ghidra",
            "examples/binary_analysis/skills/reverse-engineering-malware-with-ghidra/SKILL.md",
            log_dir=tmp_path,
        )

    entries = _read_entries(tmp_path / f"{aid}.audit.jsonl")
    assert len(entries) == 1
    e = entries[0]
    assert e["event_type"] == "skill_read"
    assert e["skill_name"] == "reverse-engineering-malware-with-ghidra"


def test_multiple_entries_appended(tmp_path):
    aid = str(uuid.uuid4())
    with analysis_context(aid, log_dir=tmp_path):
        log_tool_call("T1", {}, {}, 10.0, log_dir=tmp_path)
        log_tool_call("T2", {}, {}, 20.0, log_dir=tmp_path)
        log_tool_call("T3", {}, {}, 30.0, log_dir=tmp_path)

    entries = _read_entries(tmp_path / f"{aid}.audit.jsonl")
    assert len(entries) == 3
    names = [e["tool_name"] for e in entries]
    assert names == ["T1", "T2", "T3"]


def test_entries_per_analysis_id_isolated(tmp_path):
    """Two concurrent analyses must write to separate JSONL files."""
    aid1 = str(uuid.uuid4())
    aid2 = str(uuid.uuid4())
    with analysis_context(aid1, log_dir=tmp_path):
        log_tool_call("A", {}, {}, 1.0, log_dir=tmp_path)
    with analysis_context(aid2, log_dir=tmp_path):
        log_tool_call("B", {}, {}, 2.0, log_dir=tmp_path)

    entries1 = _read_entries(tmp_path / f"{aid1}.audit.jsonl")
    entries2 = _read_entries(tmp_path / f"{aid2}.audit.jsonl")
    assert len(entries1) == 1 and entries1[0]["tool_name"] == "A"
    assert len(entries2) == 1 and entries2[0]["tool_name"] == "B"
