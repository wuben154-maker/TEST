"""Unit tests for :mod:`tools.bash_tool` (C7-AC1/AC2/AC5)."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

import audit as audit_module
from audit import analysis_context
from errors import ToolSchemaInvalid
from sandbox.client import ExecResult, SandboxSession, sandbox_workspace
from sandbox.registry import _SESSION_REGISTRY
from tools.bash_tool import (
    DEFAULT_LLM_PREVIEW_HEAD_BYTES,
    DEFAULT_LLM_PREVIEW_TAIL_BYTES,
    DEFAULT_STREAM_LIMIT_BYTES,
    BashTool,
    _first_unsupported_shell_token,
    _tokenise_cmd,
    load_bash_whitelist,
)

# ---------------------------------------------------------------------------
# Shared fakes
# ---------------------------------------------------------------------------


class _FakeSandboxClient:
    """In-memory SandboxClient capturing every ``exec`` call."""

    def __init__(
        self,
        *,
        stdout: str = "",
        stderr: str = "",
        exit_code: int = 0,
        duration_ms: float = 12.5,
        timed_out: bool = False,
        files: dict[str, bytes] | None = None,
    ) -> None:
        self.stdout = stdout
        self.stderr = stderr
        self.exit_code = exit_code
        self.duration_ms = duration_ms
        self.timed_out = timed_out
        self.files = files or {}
        self.exec_calls: list[dict[str, Any]] = []

    async def create(self, analysis_id: str) -> SandboxSession:  # pragma: no cover
        raise NotImplementedError

    async def exec(
        self,
        session: SandboxSession,
        cmd: str | list[str],
        *,
        timeout: float,
        user: str = "user",
        cwd: str | None = None,
    ) -> ExecResult:
        self.exec_calls.append(
            {"session": session, "cmd": cmd, "timeout": timeout, "cwd": cwd}
        )
        return ExecResult(
            stdout=self.stdout,
            stderr=self.stderr,
            exit_code=self.exit_code,
            duration_ms=self.duration_ms,
            timed_out=self.timed_out,
        )

    async def upload(self, *args: Any, **kwargs: Any) -> None:  # pragma: no cover
        raise NotImplementedError

    async def download(self, session: SandboxSession, path: str) -> bytes:
        del session
        try:
            return self.files[path]
        except KeyError as exc:
            raise FileNotFoundError(path) from exc

    async def kill(self, session: SandboxSession) -> None:
        _SESSION_REGISTRY.pop(session.analysis_id, None)


class _ExecFailingSandboxClient(_FakeSandboxClient):
    async def exec(
        self,
        session: SandboxSession,
        cmd: str | list[str],
        *,
        timeout: float,
        user: str = "user",
        cwd: str | None = None,
    ) -> ExecResult:
        self.exec_calls.append(
            {"session": session, "cmd": cmd, "timeout": timeout, "cwd": cwd}
        )
        raise RuntimeError("backend unavailable")


def _make_session(analysis_id: str) -> SandboxSession:
    session = SandboxSession(
        analysis_id=analysis_id,
        sandbox_id=f"fake-{analysis_id}",
        backend="subprocess",
        workdir=sandbox_workspace(analysis_id),
        created_at=0.0,
    )
    _SESSION_REGISTRY[analysis_id] = session
    return session


@pytest.fixture(autouse=True)
def _clean_registry_and_logdir(monkeypatch, tmp_path: Path):
    _SESSION_REGISTRY.clear()
    monkeypatch.setattr(audit_module, "_DEFAULT_LOG_DIR", tmp_path)
    yield tmp_path
    _SESSION_REGISTRY.clear()


def _read_audit(aid: str, log_dir: Path) -> list[dict[str, Any]]:
    path = log_dir / f"{aid}.audit.jsonl"
    if not path.is_file():
        return []
    return [
        json.loads(line)
        for line in path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]


# ---------------------------------------------------------------------------
# C7-AC1: whitelist
# ---------------------------------------------------------------------------


class TestAC1Whitelist:
    def test_default_whitelist_contains_all_required_binaries(self):
        whitelist = load_bash_whitelist()
        required = {
            "analyzeHeadless",
            "upx",
            "floss",
            "diec",
            "yara",
            "strings",
            "sha256sum",
            "file",
            "ssdeep",
            "tlsh",
            "python3",
            "ls",
            "pwd",
        }
        assert required.issubset(whitelist), (
            f"missing entries: {required - whitelist!r}"
        )

    def test_whitelist_entries_are_bare_basenames(self):
        """Spec guard: no shell-metachars or slashes leak into the allow-list."""
        for entry in load_bash_whitelist():
            assert "/" not in entry and " " not in entry, entry

    def test_description_matches_whitelist_and_guides_sample_searches(self):
        description = BashTool(sandbox_client=_FakeSandboxClient()).description

        assert "diec" in description
        assert "upx" in description
        assert "analyzing-packed-malware-with-upx-unpacker" in description
        assert "ls, pwd" in description
        assert "grep" in description
        assert "strings -a -n 6" in description
        assert "python_exec" in description

    async def test_non_whitelisted_command_returns_error_dict(
        self, _clean_registry_and_logdir
    ):
        """Whitelist violations surface as a structured tool result.

        The tool returns an ``ok=False`` dict rather than raising so the
        LLM receives a ToolMessage describing the rejection and can retry
        with an allowed binary, instead of killing the whole agent loop
        (F-manual FB-F-04 / FB: single LLM slip would downgrade analysis).
        """
        _make_session("aid-deny")
        tool = BashTool(sandbox_client=_FakeSandboxClient())
        result = await tool.ainvoke(
            {"cmd": "rm -rf /tmp/foo", "analysis_id": "aid-deny"}
        )
        assert result["ok"] is False
        assert result["error_code"] == "TOOL_SCHEMA_INVALID"
        assert result["reason"] == "command_not_whitelisted"
        assert result["details"]["binary"] == "rm"
        assert "allowed binaries" in result["message"]

    async def test_grep_sample_search_returns_recoverable_guidance(
        self, _clean_registry_and_logdir
    ):
        """Regression: binary filtering must use safe primitives, not `grep`."""
        _make_session("aid-grep")
        client = _FakeSandboxClient()
        tool = BashTool(sandbox_client=client)
        result = await tool.ainvoke(
            {
                "cmd": 'grep -i "powershell" /workspace/aid-grep/sample.bin',
                "analysis_id": "aid-grep",
            }
        )
        assert result["ok"] is False
        assert result["error_code"] == "TOOL_SCHEMA_INVALID"
        assert result["reason"] == "command_not_whitelisted"
        assert result["details"]["binary"] == "grep"
        assert "strings" in result["message"]
        assert "python_exec" in result["message"]
        assert client.exec_calls == []

    async def test_whitelisted_full_path_accepted(self):
        """``posixpath.basename`` strip: `/usr/bin/yara` → `yara` → allowed."""
        _make_session("aid-full")
        client = _FakeSandboxClient(stdout="ok")
        tool = BashTool(sandbox_client=client)
        result = await tool.ainvoke(
            {"cmd": "/usr/bin/yara --version", "analysis_id": "aid-full"}
        )
        assert result["ok"] is True
        assert result["binary"] == "yara"

    async def test_upx_unpacked_output_command_is_allowed(self):
        """FR-05 can execute the UPX unpack command shape from the workflow."""
        aid = "aid-upx"
        _make_session(aid)
        client = _FakeSandboxClient(stdout="Ultimate Packer for eXecutables")
        tool = BashTool(sandbox_client=client)

        result = await tool.ainvoke(
            {
                "cmd": [
                    "upx",
                    "-d",
                    f"/workspace/{aid}/sample.bin",
                    "-o",
                    f"/workspace/{aid}/unpacked/upx-unpacked.tmp.bin",
                ],
                "analysis_id": aid,
            }
        )

        assert result["ok"] is True
        assert result["binary"] == "upx"
        assert client.exec_calls[0]["cmd"][0] == "upx"

    async def test_missing_whitelist_yaml_raises_tool_schema_invalid(self, tmp_path):
        missing = tmp_path / "not-here.yaml"
        with pytest.raises(ToolSchemaInvalid) as ei:
            load_bash_whitelist(missing)
        assert ei.value.details["reason"] == "whitelist_missing"

    async def test_malformed_whitelist_rejected(self, tmp_path):
        bad = tmp_path / "bash_whitelist.yaml"
        bad.write_text("commands:\n  - 'bad;entry'\n", encoding="utf-8")
        with pytest.raises(ToolSchemaInvalid) as ei:
            load_bash_whitelist(bad)
        assert ei.value.details["reason"] == "whitelist_entry_invalid"

    async def test_rejected_command_is_never_executed(self):
        """Whitelist violation must not reach the sandbox.

        Even though the tool now returns a structured error (see
        ``test_non_whitelisted_command_returns_error_dict``) instead of
        raising, the safety invariant is unchanged: ``client.exec`` must
        never be invoked for a non-whitelisted binary.
        """
        _make_session("aid-deny-exec")
        client = _FakeSandboxClient()
        tool = BashTool(sandbox_client=client)
        # `rm` is intentionally *not* in `config/bash_whitelist.yaml` — it
        # represents the canonical "mutating command we never want the LLM
        # to issue".
        result = await tool.ainvoke(
            {"cmd": "rm -rf /tmp/sample", "analysis_id": "aid-deny-exec"}
        )
        assert result["ok"] is False
        assert result["error_code"] == "TOOL_SCHEMA_INVALID"
        assert client.exec_calls == []


# ---------------------------------------------------------------------------
# Shell syntax preflight (pipes / redirections)
# ---------------------------------------------------------------------------


class TestShellOperatorPreflight:
    def test_first_unsupported_shell_token_detects_pipe(self):
        tokens = _tokenise_cmd("strings /w/sample.bin | head -n 5")
        assert _first_unsupported_shell_token(tokens) == "|"

    def test_first_unsupported_shell_token_detects_inline_redirect(self):
        tokens = _tokenise_cmd("strings /w/x 2>/w/x/err.log")
        assert _first_unsupported_shell_token(tokens) == "2>/w/x/err.log"

    def test_first_unsupported_shell_token_none_for_plain_argv(self):
        tokens = _tokenise_cmd("strings -n 8 /workspace/aid/sample.bin")
        assert _first_unsupported_shell_token(tokens) is None

    async def test_pipe_command_returns_error_and_skips_exec(
        self, _clean_registry_and_logdir
    ):
        """Regression: ``|`` must not be passed through to ``strings`` as a path."""
        _make_session("aid-pipe")
        client = _FakeSandboxClient()
        tool = BashTool(sandbox_client=client)
        result = await tool.ainvoke(
            {
                "cmd": "strings /workspace/aid-pipe/sample.bin | head -n 100",
                "analysis_id": "aid-pipe",
            }
        )
        assert result["ok"] is False
        assert result["error_code"] == "TOOL_SCHEMA_INVALID"
        assert result["reason"] == "shell_operators_not_supported"
        assert result["details"]["token"] == "|"
        assert client.exec_calls == []

    async def test_pipe_rejection_writes_audit(self, _clean_registry_and_logdir):
        log_dir: Path = _clean_registry_and_logdir
        aid = "aid-pipe-audit"
        _make_session(aid)
        tool = BashTool(sandbox_client=_FakeSandboxClient())
        with analysis_context(aid):
            await tool.ainvoke({"cmd": "yara --version && echo x", "analysis_id": aid})
        entries = _read_audit(aid, log_dir)
        assert len(entries) == 1
        assert entries[0]["success"] is False
        assert entries[0]["error_code"] == "TOOL_SCHEMA_INVALID"
        assert entries[0]["result"]["reason"] == "shell_operators_not_supported"


# ---------------------------------------------------------------------------
# FR-07 Ghidra priority-file preflight
# ---------------------------------------------------------------------------


class TestGhidraPriorityFilePreflight:
    def _cmd(self, aid: str) -> list[str]:
        return [
            "analyzeHeadless",
            f"/workspace/{aid}/ghidra-proj",
            aid,
            "-import",
            f"/workspace/{aid}/sample.bin",
            "-scriptPath",
            "/opt/ghidra/scripts",
            "-postScript",
            "DecompileByList.py",
            f"/workspace/{aid}/decompile_priority.txt",
            f"/workspace/{aid}/decompile/",
            "30",
            "-deleteProject",
            "-readOnly",
        ]

    async def test_decompile_by_list_requires_existing_priority_file(self):
        aid = "aid-ghidra-missing-priority"
        _make_session(aid)
        client = _FakeSandboxClient()
        tool = BashTool(sandbox_client=client)

        result = await tool.ainvoke({"cmd": self._cmd(aid), "analysis_id": aid})

        assert result["ok"] is False
        assert result["error_code"] == "TOOL_SCHEMA_INVALID"
        assert result["reason"] == "decompile_priority_file_missing"
        assert "python_exec" in result["message"]
        assert client.exec_calls == []

    async def test_decompile_by_list_rejects_empty_priority_file(self):
        aid = "aid-ghidra-empty-priority"
        path = f"/workspace/{aid}/decompile_priority.txt"
        _make_session(aid)
        client = _FakeSandboxClient(files={path: b"\n  \n"})
        tool = BashTool(sandbox_client=client)

        result = await tool.ainvoke({"cmd": self._cmd(aid), "analysis_id": aid})

        assert result["ok"] is False
        assert result["error_code"] == "TOOL_SCHEMA_INVALID"
        assert result["reason"] == "decompile_priority_file_empty"
        assert client.exec_calls == []

    async def test_decompile_by_list_runs_after_priority_file_exists(self):
        aid = "aid-ghidra-priority-ok"
        path = f"/workspace/{aid}/decompile_priority.txt"
        _make_session(aid)
        client = _FakeSandboxClient(files={path: b"main@0x401000\n"}, stdout="ok")
        tool = BashTool(sandbox_client=client)

        result = await tool.ainvoke({"cmd": self._cmd(aid), "analysis_id": aid})

        assert result["ok"] is True
        assert result["binary"] == "analyzeHeadless"
        assert client.exec_calls


# ---------------------------------------------------------------------------
# C7-AC2: timeout + stream truncation
# ---------------------------------------------------------------------------


class TestAC2TimeoutAndTruncation:
    async def test_timeout_forwarded_to_sandbox(self):
        _make_session("aid-to")
        client = _FakeSandboxClient()
        tool = BashTool(sandbox_client=client)
        await tool.ainvoke(
            {
                "cmd": ["yara", "--version"],
                "analysis_id": "aid-to",
                "timeout_seconds": 3.5,
            }
        )
        assert client.exec_calls[0]["timeout"] == 3.5  # noqa: PLR2004

    async def test_default_timeout_applied_when_omitted(self):
        _make_session("aid-def")
        client = _FakeSandboxClient()
        tool = BashTool(sandbox_client=client, default_timeout_seconds=17.0)
        await tool.ainvoke({"cmd": "yara --version", "analysis_id": "aid-def"})
        assert client.exec_calls[0]["timeout"] == 17.0  # noqa: PLR2004

    async def test_timed_out_result_surfaced(self):
        _make_session("aid-killed")
        client = _FakeSandboxClient(
            stdout="partial", stderr="", exit_code=-1, timed_out=True
        )
        tool = BashTool(sandbox_client=client)
        result = await tool.ainvoke({"cmd": "yara --slow", "analysis_id": "aid-killed"})
        assert result["timed_out"] is True
        assert result["ok"] is False
        assert result["exit_code"] == -1

    async def test_stdout_truncated_triggers_head_tail_preview(self):
        """Stage-1 (sandbox 64 KiB cap) + stage-2 (LLM-view head/tail preview).

        Stage-1 remains authoritative for the SPEC C7-AC2 / IR-10 contract
        ("stdout truncated to ≤ 64 KiB"): ``stdout_truncated`` still
        flips to ``True`` whenever the raw stream exceeded 64 KiB.

        Stage-2 is the additional compression introduced to keep the
        Agent-visible payload below the
        :class:`~deepagents.middleware.filesystem.FilesystemMiddleware`
        80 000-char eviction threshold.  When it fires, the tool must:

        1. set ``stdout_preview_only=True``;
        2. shrink ``result["stdout"]`` to roughly ``head+tail+marker`` bytes
           (well under 64 KiB — we verify the upper bound here rather than
           an exact size so the marker format can evolve freely);
        3. surface a human-readable marker that names the elided byte count.
        """
        _make_session("aid-big")
        huge = "A" * (DEFAULT_STREAM_LIMIT_BYTES + 10_000)
        client = _FakeSandboxClient(stdout=huge)
        tool = BashTool(sandbox_client=client)
        result = await tool.ainvoke({"cmd": "yara --dump", "analysis_id": "aid-big"})

        assert result["stdout_truncated"] is True
        assert result["stdout_preview_only"] is True
        stdout_bytes = len(result["stdout"].encode("utf-8"))
        # The payload must be strictly smaller than the stage-1 cap and at
        # least as large as the head+tail budget (plus the elision marker).
        preview_budget = DEFAULT_LLM_PREVIEW_HEAD_BYTES + DEFAULT_LLM_PREVIEW_TAIL_BYTES
        assert preview_budget <= stdout_bytes < DEFAULT_STREAM_LIMIT_BYTES, (
            f"preview stdout should sit between head+tail ({preview_budget}) and "
            f"the 64 KiB sandbox cap; got {stdout_bytes}"
        )
        assert "stdout preview" in result["stdout"]
        assert "elided=" in result["stdout"]

    async def test_stderr_truncated_triggers_head_tail_preview(self):
        _make_session("aid-err")
        huge = "E" * (DEFAULT_STREAM_LIMIT_BYTES + 1)
        client = _FakeSandboxClient(stderr=huge, exit_code=2)
        tool = BashTool(sandbox_client=client)
        result = await tool.ainvoke({"cmd": "yara --fail", "analysis_id": "aid-err"})

        assert result["stderr_truncated"] is True
        assert result["stderr_preview_only"] is True
        stderr_bytes = len(result["stderr"].encode("utf-8"))
        assert stderr_bytes < DEFAULT_STREAM_LIMIT_BYTES
        assert "stderr preview" in result["stderr"]

    async def test_short_output_not_truncated(self):
        _make_session("aid-short")
        client = _FakeSandboxClient(stdout="hello")
        tool = BashTool(sandbox_client=client)
        result = await tool.ainvoke({"cmd": "yara", "analysis_id": "aid-short"})
        assert result["stdout_truncated"] is False
        assert result["stdout_preview_only"] is False
        assert result["stdout"] == "hello"

    async def test_preview_reduces_toolmessage_below_eviction_threshold(self):
        """Regression guard for ``/large_tool_results/`` skills-tree pollution.

        With both streams at the 64 KiB sandbox cap, the pre-refactor
        ToolMessage was ~130 KiB and reliably crossed
        :class:`~deepagents.middleware.filesystem.FilesystemMiddleware`'s
        ``tool_token_limit_before_evict * NUM_CHARS_PER_TOKEN`` ≈ 80 000
        char threshold, which — absent a routed
        ``/large_tool_results/`` backend — wrote giant payloads into the
        curated skills tree on disk.  After the preview refactor, the
        same workload must fit comfortably inside the threshold even
        when both streams were compressed separately.
        """
        _make_session("aid-both-big")
        huge = "X" * (DEFAULT_STREAM_LIMIT_BYTES + 50_000)
        client = _FakeSandboxClient(stdout=huge, stderr=huge, exit_code=1)
        tool = BashTool(sandbox_client=client)
        result = await tool.ainvoke(
            {
                "cmd": "strings /workspace/aid-both-big/sample",
                "analysis_id": "aid-both-big",
            }
        )
        # Approximate the on-wire ToolMessage by JSON-encoding the dict —
        # the exact serialiser that langgraph uses is BaseMessage-specific,
        # but byte-for-byte it is within a few percent of ``json.dumps`` of
        # the structured result.  80 000 chars is the FilesystemMiddleware
        # eviction threshold; we assert a generous 3× safety margin.
        serialised = json.dumps(result, ensure_ascii=False)
        assert len(serialised) < 30_000, (
            f"serialised ToolMessage is {len(serialised)} chars — "
            "larger than the 30 000-char safety margin below the 80 000-char "
            "FilesystemMiddleware eviction threshold; preview compression "
            "may have regressed"
        )


# ---------------------------------------------------------------------------
# Session missing guard
# ---------------------------------------------------------------------------


class TestSessionGuard:
    async def test_missing_session_returns_schema_error(self):
        tool = BashTool(sandbox_client=_FakeSandboxClient())
        result = await tool.ainvoke({"cmd": "yara", "analysis_id": "aid-missing"})
        assert result["ok"] is False
        assert result["error_code"] == "TOOL_SCHEMA_INVALID"
        assert result["reason"] == "sandbox_session_missing"

    async def test_backend_exec_exception_returns_tool_crash(
        self, _clean_registry_and_logdir
    ):
        log_dir: Path = _clean_registry_and_logdir
        aid = "aid-backend-error"
        _make_session(aid)
        tool = BashTool(sandbox_client=_ExecFailingSandboxClient())

        with analysis_context(aid):
            result = await tool.ainvoke({"cmd": "yara", "analysis_id": aid})

        assert result["ok"] is False
        assert result["error_code"] == "TOOL_CRASH"
        assert result["reason"] == "sandbox_exec_exception"
        assert result["details"]["error_type"] == "RuntimeError"
        entries = _read_audit(aid, log_dir)
        assert entries[-1]["error_code"] == "TOOL_CRASH"


# ---------------------------------------------------------------------------
# C7-AC5: audit log
# ---------------------------------------------------------------------------


class TestAC5Audit:
    async def test_successful_call_writes_tool_call_event(
        self, _clean_registry_and_logdir
    ):
        log_dir: Path = _clean_registry_and_logdir
        aid = "aid-audit-ok"
        _make_session(aid)
        client = _FakeSandboxClient(stdout="matched", exit_code=0)
        tool = BashTool(sandbox_client=client)
        with analysis_context(aid):
            await tool.ainvoke({"cmd": "yara -r /rules", "analysis_id": aid})

        entries = _read_audit(aid, log_dir)
        assert len(entries) == 1
        entry = entries[0]
        assert entry["event_type"] == "tool_call"
        assert entry["tool_name"] == "bash"
        assert entry["success"] is True
        assert entry["args"]["cmd"] == ["yara", "-r", "/rules"]
        assert entry["result"]["exit_code"] == 0

    async def test_timeout_logs_tool_timeout_error_code(
        self, _clean_registry_and_logdir
    ):
        log_dir: Path = _clean_registry_and_logdir
        aid = "aid-audit-to"
        _make_session(aid)
        client = _FakeSandboxClient(exit_code=-1, timed_out=True)
        tool = BashTool(sandbox_client=client)
        with analysis_context(aid):
            await tool.ainvoke({"cmd": "yara --slow", "analysis_id": aid})

        entries = _read_audit(aid, log_dir)
        assert len(entries) == 1
        assert entries[0]["success"] is False
        assert entries[0]["error_code"] == "TOOL_TIMEOUT"

    async def test_backend_exception_logs_tool_crash_and_returns_error(
        self, _clean_registry_and_logdir
    ):
        """Regression for terminals/39.txt: when the sandbox backend raises
        an unexpected exception (SDK bug, network blip, etc.), the tool must
        still emit an audit entry with ``error_code='TOOL_CRASH'`` and return
        a structured ToolMessage so the agent run can continue.
        """
        log_dir: Path = _clean_registry_and_logdir
        aid = "aid-audit-crash"
        _make_session(aid)

        class _ExplodingClient(_FakeSandboxClient):
            async def exec(self, *args: Any, **kwargs: Any) -> ExecResult:
                raise RuntimeError("e2b control plane unreachable")

        tool = BashTool(sandbox_client=_ExplodingClient())
        with analysis_context(aid):
            result = await tool.ainvoke({"cmd": "yara -r /rules", "analysis_id": aid})

        assert result["ok"] is False
        assert result["error_code"] == "TOOL_CRASH"
        assert result["reason"] == "sandbox_exec_exception"

        entries = _read_audit(aid, log_dir)
        assert len(entries) == 1
        assert entries[0]["success"] is False
        assert entries[0]["error_code"] == "TOOL_CRASH"
        assert entries[0]["result"]["error_type"] == "RuntimeError"
