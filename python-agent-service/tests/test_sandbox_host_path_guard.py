"""Tests for the sandbox host-virtual-path guard.

The guard rejects ``sandbox_run`` / ``sandbox_pty_run`` calls that reference
SecManus host virtual paths (``/workspace/``, ``/uploads/``, ``workspace/``),
which never resolve inside an E2B sandbox. The goal is one-shot feedback to
the LLM, not repeated ``cat: No such file`` retries.
"""

from __future__ import annotations

import json

import pytest

from app.tools.sandbox_tools import (
    SandboxPtyInput,
    SandboxRunInput,
    UploadFileSpec,
    _contains_host_virtual_path,
    _reject_host_virtual_paths_after_staging,
    _sandbox_pty_run,
    _sandbox_run,
)


class TestContainsHostVirtualPath:
    @pytest.mark.parametrize(
        "needle",
        [
            "cat /workspace/foo.txt",
            "grep -n sth /uploads/u_abc/file.php",
            "cat workspace/ghost.php",
            "ls /workspace",
        ],
    )
    def test_flags_virtual_paths(self, needle: str) -> None:
        assert _contains_host_virtual_path(needle) is not None

    @pytest.mark.parametrize(
        "clean",
        [
            "cat /tmp/secmanus/work/in/sample.php",
            "ls /home/user/workspace",  # sandbox-local 'workspace' dir, not root token
            "echo hello",
            "",
            "python3 -c 'print(42)'",
        ],
    )
    def test_passes_clean_strings(self, clean: str) -> None:
        assert _contains_host_virtual_path(clean) is None


class TestRejectHostVirtualPaths:
    def test_rejects_command_virtual_path(self) -> None:
        guard = _reject_host_virtual_paths_after_staging(
            command="cat /workspace/foo.txt",
            cwd=None,
            upload_files=None,
            sandbox_id=None,
        )
        assert guard is not None
        payload = json.loads(guard)
        assert payload["exit_code"] == -1
        assert "command" in payload["error"]
        assert "/workspace" in payload["error"]

    def test_rejects_upload_files_sandbox_path(self) -> None:
        guard = _reject_host_virtual_paths_after_staging(
            command="cat /tmp/a",
            cwd=None,
            upload_files=[
                UploadFileSpec(
                    sandbox_path="/workspace/oops.txt",
                    content_text="hi",
                )
            ],
            sandbox_id=None,
        )
        assert guard is not None
        payload = json.loads(guard)
        assert "upload_files" in payload["error"]

    def test_rejects_cwd_virtual_path(self) -> None:
        guard = _reject_host_virtual_paths_after_staging(
            command="ls",
            cwd="/workspace/x",
            upload_files=None,
            sandbox_id=None,
        )
        assert guard is not None
        assert "cwd" in json.loads(guard)["error"]

    def test_allows_clean_input(self) -> None:
        assert (
            _reject_host_virtual_paths_after_staging(
                command="cat /tmp/secmanus/work/in/sample.php",
                cwd=None,
                upload_files=[
                    UploadFileSpec(
                        sandbox_path="/tmp/secmanus/work/in/sample.php",
                        content_text="hi",
                    )
                ],
                sandbox_id=None,
            )
            is None
        )


class TestAsyncRejection:
    @pytest.mark.asyncio
    async def test_sandbox_run_short_circuits_on_virtual_path(self) -> None:
        inp = SandboxRunInput(
            command="cat workspace/x.php",
            auto_stage_workspace_paths_from_command=False,
        )
        result = await _sandbox_run(inp)
        payload = json.loads(result)
        # Must not leak beyond the guard (no e2b call happens, no sandbox_id).
        assert payload["sandbox_id"] is None
        assert payload["exit_code"] == -1
        assert "host virtual path" in payload["error"]

    @pytest.mark.asyncio
    async def test_sandbox_pty_run_short_circuits(self) -> None:
        inp = SandboxPtyInput(commands=["cat /uploads/a.php"])
        result = await _sandbox_pty_run(inp)
        payload = json.loads(result)
        assert payload["sandbox_id"] is None
        assert "host virtual path" in payload["error"]
