"""Unit tests for E2B sandbox tools.

All E2B SDK calls are mocked — no live sandbox is required.
Tests cover:
  - Config loader (sandbox.yaml)
  - sandbox_create (session-level sandbox creation)
  - sandbox_destroy (sandbox teardown)
  - sandbox_run (blocking, streaming, per-call, session modes)
  - sandbox_pty_run (PTY interactive session + streaming)
  - SandboxSseEmitter (ContextVar mechanism)
  - E2BSandboxBackend (lazy init, execute, upload, download)
  - Registry: sandbox tools mounted only when E2B_API_KEY set
"""

from __future__ import annotations

import asyncio
import json
import os
from pathlib import Path
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
import yaml

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

SANDBOX_ID = "sandbox-test-abc123"
DUMMY_API_KEY = "e2b_test_key"


def _make_run_result(stdout: str = "ok\n", stderr: str = "", exit_code: int = 0) -> Any:
    r = MagicMock()
    r.stdout = stdout
    r.stderr = stderr
    r.exit_code = exit_code
    return r


def _make_mock_sandbox(sandbox_id: str = SANDBOX_ID) -> AsyncMock:
    sb = AsyncMock()
    sb.sandbox_id = sandbox_id
    # commands.run default
    sb.commands.run = AsyncMock(return_value=_make_run_result())
    # files
    sb.files.write = AsyncMock()
    sb.files.read = AsyncMock(return_value=b"file_content")
    # pty
    pty_handle = MagicMock()
    pty_handle.pid = 42
    sb.pty.create = AsyncMock(return_value=pty_handle)
    sb.pty.subscribe = MagicMock(return_value=_pty_output_gen())
    sb.pty.send_stdin = AsyncMock()
    sb.kill = AsyncMock()
    return sb


async def _pty_output_gen():
    for chunk in [b"$ ", b"output line\r\n", b"$ "]:
        yield chunk


# ---------------------------------------------------------------------------
# Config loader
# ---------------------------------------------------------------------------


class TestSandboxConfig:
    def test_load_from_yaml_file(self, tmp_path: Path) -> None:
        """Config loader correctly parses sandbox.yaml."""
        cfg_content = {
            "defaults": {"template": "base", "timeout_seconds": 60, "max_sandbox_lifetime": 300},
            "templates": {
                "base": {
                    "template_id": "base",
                    "description": "Minimal sandbox",
                    "allow_internet": False,
                    "timeout_seconds": 60,
                    "env": {},
                }
            },
        }
        yaml_path = tmp_path / "sandbox.yaml"
        yaml_path.write_text(yaml.dump(cfg_content))

        from app.tools.sandbox_tools import SandboxConfig, _load_sandbox_config

        # Patch the config path
        with patch("app.tools.sandbox_tools._CONFIG_PATH", yaml_path):
            _load_sandbox_config.cache_clear()
            cfg = _load_sandbox_config()
        assert cfg.defaults.template == "base"
        assert "base" in cfg.templates
        assert cfg.templates["base"].template_id == "base"

    def test_resolve_known_template(self) -> None:
        """_resolve_template returns correct TemplateConfig for a known name."""
        from app.tools.sandbox_tools import _resolve_template

        tpl, resolved = _resolve_template("base")
        assert resolved == "base"
        assert tpl.template_id == "base"

    def test_resolve_unknown_template_raises(self) -> None:
        """_resolve_template raises ValueError for unknown template name."""
        from app.tools.sandbox_tools import _resolve_template

        with pytest.raises(ValueError, match="not found"):
            _resolve_template("nonexistent-template-xyz")


# ---------------------------------------------------------------------------
# sandbox_create
# ---------------------------------------------------------------------------


class TestSandboxCreate:
    @pytest.mark.asyncio
    async def test_create_returns_sandbox_id(self) -> None:
        """sandbox_create returns a sandbox_id when key is set."""
        mock_sb = _make_mock_sandbox()
        with patch.dict(os.environ, {"E2B_API_KEY": DUMMY_API_KEY}):
            with patch("app.tools.sandbox_tools.AsyncSandbox") as MockCls:
                MockCls.create = AsyncMock(return_value=mock_sb)
                from app.tools.sandbox_tools import _load_sandbox_config, _sandbox_create

                _load_sandbox_config.cache_clear()
                result = json.loads(await _sandbox_create("base", None, "test"))
        assert result["sandbox_id"] == SANDBOX_ID
        assert result["error"] is None

    @pytest.mark.asyncio
    async def test_create_no_api_key_returns_error(self) -> None:
        """sandbox_create returns an error dict when no API key is set."""
        with patch.dict(os.environ, {}, clear=True):
            os.environ.pop("E2B_API_KEY", None)
            from app.tools.sandbox_tools import _sandbox_create

            result = json.loads(await _sandbox_create("base", None, None))
        assert "error" in result
        assert result.get("sandbox_id") is None

    @pytest.mark.asyncio
    async def test_create_async_sandbox_import_failed_returns_clear_error(self) -> None:
        """When e2b failed to import, AsyncSandbox is None — return a clear message, not AttributeError."""
        with patch.dict(os.environ, {"E2B_API_KEY": DUMMY_API_KEY}):
            with patch("app.tools.sandbox_tools.AsyncSandbox", None):
                from app.tools.sandbox_tools import _sandbox_create

                result = json.loads(await _sandbox_create("base", None, None))
        assert result.get("sandbox_id") is None
        assert "failed to import" in result["error"].lower()
        assert "e2b" in result["error"].lower()

    @pytest.mark.asyncio
    async def test_create_with_mock_e2b(self) -> None:
        """Full _sandbox_create path with mocked AsyncSandbox.create."""
        mock_sb = _make_mock_sandbox()
        with patch.dict(os.environ, {"E2B_API_KEY": DUMMY_API_KEY}):
            with patch("app.tools.sandbox_tools.AsyncSandbox") as MockCls:
                MockCls.create = AsyncMock(return_value=mock_sb)
                from app.tools.sandbox_tools import _load_sandbox_config, _sandbox_create

                _load_sandbox_config.cache_clear()
                result = json.loads(await _sandbox_create("base", {"FOO": "bar"}, "label"))
        assert result["sandbox_id"] == SANDBOX_ID
        assert result["template"] == "base"
        assert result["error"] is None


# ---------------------------------------------------------------------------
# sandbox_destroy
# ---------------------------------------------------------------------------


class TestSandboxDestroy:
    @pytest.mark.asyncio
    async def test_destroy_success(self) -> None:
        mock_sb = _make_mock_sandbox()
        with patch.dict(os.environ, {"E2B_API_KEY": DUMMY_API_KEY}):
            with patch("app.tools.sandbox_tools.AsyncSandbox") as MockCls:
                MockCls.connect = AsyncMock(return_value=mock_sb)
                from app.tools.sandbox_tools import _sandbox_destroy

                result = json.loads(await _sandbox_destroy(SANDBOX_ID))
        assert result["status"] == "killed"
        assert result["error"] is None
        mock_sb.kill.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_destroy_no_api_key(self) -> None:
        with patch.dict(os.environ, {}, clear=True):
            os.environ.pop("E2B_API_KEY", None)
            from app.tools.sandbox_tools import _sandbox_destroy

            result = json.loads(await _sandbox_destroy(SANDBOX_ID))
        assert "error" in result


# ---------------------------------------------------------------------------
# sandbox_run — blocking mode
# ---------------------------------------------------------------------------


class TestSandboxRun:
    @pytest.mark.asyncio
    async def test_per_call_mode_creates_and_kills_sandbox(self) -> None:
        """Per-call mode creates a sandbox, runs the command, then destroys it."""
        mock_sb = _make_mock_sandbox()
        mock_sb.commands.run.return_value = _make_run_result("hello\n", "", 0)

        with patch.dict(os.environ, {"E2B_API_KEY": DUMMY_API_KEY}):
            with patch("app.tools.sandbox_tools.AsyncSandbox") as MockCls:
                MockCls.create = AsyncMock(return_value=mock_sb)
                from app.tools.sandbox_tools import SandboxRunInput, _load_sandbox_config, _sandbox_run

                _load_sandbox_config.cache_clear()
                inp = SandboxRunInput(command="echo hello")
                result = json.loads(await _sandbox_run(inp))

        assert result["exit_code"] == 0
        assert result["stdout"] == "hello\n"
        assert result["mode"] == "per_call"
        mock_sb.kill.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_session_mode_reuses_sandbox(self) -> None:
        """Session mode connects to an existing sandbox and does NOT kill it."""
        mock_sb = _make_mock_sandbox()
        mock_sb.commands.run.return_value = _make_run_result("session\n", "", 0)

        with patch.dict(os.environ, {"E2B_API_KEY": DUMMY_API_KEY}):
            with patch("app.tools.sandbox_tools.AsyncSandbox") as MockCls:
                MockCls.connect = AsyncMock(return_value=mock_sb)
                from app.tools.sandbox_tools import SandboxRunInput, _sandbox_run

                inp = SandboxRunInput(command="ls", sandbox_id=SANDBOX_ID)
                result = json.loads(await _sandbox_run(inp))

        assert result["mode"] == "session"
        mock_sb.kill.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_upload_and_download(self) -> None:
        """File upload and download are called correctly."""
        mock_sb = _make_mock_sandbox()
        mock_sb.commands.run.return_value = _make_run_result("done\n", "", 0)
        mock_sb.files.read.return_value = b"output bytes"

        with patch.dict(os.environ, {"E2B_API_KEY": DUMMY_API_KEY}):
            with patch("app.tools.sandbox_tools.AsyncSandbox") as MockCls:
                MockCls.create = AsyncMock(return_value=mock_sb)
                from app.tools.sandbox_tools import SandboxRunInput, UploadFileSpec, _load_sandbox_config, _sandbox_run

                _load_sandbox_config.cache_clear()
                inp = SandboxRunInput(
                    command="cat /tmp/in.txt > /tmp/out.txt",
                    upload_files=[
                        UploadFileSpec(sandbox_path="/tmp/in.txt", content_text="hello")
                    ],
                    download_paths=["/tmp/out.txt"],
                )
                result = json.loads(await _sandbox_run(inp))

        mock_sb.files.write.assert_awaited_once()
        assert result["downloaded_files"][0]["sandbox_path"] == "/tmp/out.txt"

    @pytest.mark.asyncio
    async def test_no_api_key_returns_error(self) -> None:
        with patch.dict(os.environ, {}, clear=True):
            os.environ.pop("E2B_API_KEY", None)
            from app.tools.sandbox_tools import SandboxRunInput, _sandbox_run

            result = json.loads(await _sandbox_run(SandboxRunInput(command="ls")))
        assert "error" in result


# ---------------------------------------------------------------------------
# sandbox_run — streaming mode
# ---------------------------------------------------------------------------


class TestSandboxRunStreaming:
    @pytest.mark.asyncio
    async def test_stream_to_sse_emits_events(self) -> None:
        """When stream_to_sse=True, emit_sandbox_output is called for each line."""
        mock_sb = _make_mock_sandbox()

        # Simulate the on_stdout callback being invoked during commands.run
        async def fake_run(cmd, **kwargs):
            on_stdout_fn = kwargs.get("on_stdout")
            if on_stdout_fn:
                line_obj = MagicMock()
                line_obj.line = "line1"
                await on_stdout_fn(line_obj)
            return _make_run_result("line1\n", "", 0)

        mock_sb.commands.run.side_effect = fake_run

        with patch.dict(os.environ, {"E2B_API_KEY": DUMMY_API_KEY}):
            with patch("app.tools.sandbox_tools.AsyncSandbox") as MockCls:
                MockCls.create = AsyncMock(return_value=mock_sb)
                # Patch the already-imported name inside sandbox_tools
                with patch("app.tools.sandbox_tools.emit_sandbox_output", new_callable=AsyncMock) as mock_emit:
                    from app.tools.sandbox_tools import SandboxRunInput, _load_sandbox_config, _sandbox_run

                    _load_sandbox_config.cache_clear()
                    inp = SandboxRunInput(command="cat file.txt", stream_to_sse=True)
                    result = json.loads(await _sandbox_run(inp))

        mock_emit.assert_awaited()
        assert result["streamed_lines"] == 1

    @pytest.mark.asyncio
    async def test_no_sse_when_stream_false(self) -> None:
        """When stream_to_sse=False, emit_sandbox_output is never called."""
        mock_sb = _make_mock_sandbox()
        with patch.dict(os.environ, {"E2B_API_KEY": DUMMY_API_KEY}):
            with patch("app.tools.sandbox_tools.AsyncSandbox") as MockCls:
                MockCls.create = AsyncMock(return_value=mock_sb)
                with patch("app.tools.sandbox_tools.emit_sandbox_output", new_callable=AsyncMock) as mock_emit:
                    from app.tools.sandbox_tools import SandboxRunInput, _load_sandbox_config, _sandbox_run

                    _load_sandbox_config.cache_clear()
                    inp = SandboxRunInput(command="ls", stream_to_sse=False)
                    result = json.loads(await _sandbox_run(inp))

        mock_emit.assert_not_awaited()
        assert result["streamed_lines"] is None


# ---------------------------------------------------------------------------
# sandbox_pty_run
# ---------------------------------------------------------------------------


class TestSandboxPtyRun:
    @pytest.mark.asyncio
    async def test_pty_sends_commands_and_returns_output(self) -> None:
        """PTY tool sends each command and collects output."""
        mock_sb = _make_mock_sandbox()
        chunks = [b"$ ", b"hello\r\n", b"$ "]

        async def _gen(pid: int):
            for c in chunks:
                yield c

        mock_sb.pty.subscribe = _gen

        with patch.dict(os.environ, {"E2B_API_KEY": DUMMY_API_KEY}):
            with patch("app.tools.sandbox_tools.AsyncSandbox") as MockCls:
                MockCls.create = AsyncMock(return_value=mock_sb)
                from app.tools.sandbox_tools import SandboxPtyInput, _load_sandbox_config, _sandbox_pty_run

                _load_sandbox_config.cache_clear()
                inp = SandboxPtyInput(
                    commands=["echo hello", "exit"],
                    stream_to_sse=False,
                    initial_wait_ms=0,
                    between_cmd_ms=0,
                    timeout=5,
                )
                result = json.loads(await _sandbox_pty_run(inp))

        assert result["commands_sent"] == 2
        assert "hello" in result["output"]
        assert result["error"] is None

    @pytest.mark.asyncio
    async def test_pty_streams_to_sse(self) -> None:
        """PTY tool calls emit_sandbox_output when stream_to_sse=True."""
        mock_sb = _make_mock_sandbox()
        chunks = [b"line1\r\n"]

        async def _gen(pid: int):
            for c in chunks:
                yield c

        mock_sb.pty.subscribe = _gen

        with patch.dict(os.environ, {"E2B_API_KEY": DUMMY_API_KEY}):
            with patch("app.tools.sandbox_tools.AsyncSandbox") as MockCls:
                MockCls.create = AsyncMock(return_value=mock_sb)
                with patch("app.tools.sandbox_tools.emit_sandbox_output", new_callable=AsyncMock) as mock_emit:
                    from app.tools.sandbox_tools import SandboxPtyInput, _load_sandbox_config, _sandbox_pty_run

                    _load_sandbox_config.cache_clear()
                    inp = SandboxPtyInput(
                        commands=["ls"],
                        stream_to_sse=True,
                        initial_wait_ms=0,
                        between_cmd_ms=0,
                        timeout=5,
                    )
                    result = json.loads(await _sandbox_pty_run(inp))

        mock_emit.assert_awaited()
        assert result["streamed_chunks"] >= 1

    @pytest.mark.asyncio
    async def test_pty_no_api_key(self) -> None:
        with patch.dict(os.environ, {}, clear=True):
            os.environ.pop("E2B_API_KEY", None)
            from app.tools.sandbox_tools import SandboxPtyInput, _sandbox_pty_run

            result = json.loads(await _sandbox_pty_run(SandboxPtyInput(commands=["ls"])))
        assert "error" in result


# ---------------------------------------------------------------------------
# SandboxSseEmitter (ContextVar)
# ---------------------------------------------------------------------------


class TestSandboxSseEmitter:
    @pytest.mark.asyncio
    async def test_emit_no_emitter_is_noop(self) -> None:
        """emit_sandbox_output is a no-op when no emitter is registered."""
        from app.tools.sandbox_sse import clear_sse_emitter, emit_sandbox_output

        clear_sse_emitter()
        # Should not raise
        await emit_sandbox_output("sb1", "sandbox_run", "stdout", "line", 0)

    @pytest.mark.asyncio
    async def test_emit_calls_registered_emitter(self) -> None:
        """emit_sandbox_output calls the registered emitter with correct payload."""
        from app.tools.sandbox_sse import (
            clear_sse_emitter,
            emit_sandbox_output,
            set_sse_emitter,
        )

        received: list[dict] = []

        async def my_emitter(event: dict) -> None:
            received.append(event)

        set_sse_emitter(my_emitter)
        try:
            await emit_sandbox_output("sb-1", "sandbox_run", "stdout", "hello", 5)
        finally:
            clear_sse_emitter()

        assert len(received) == 1
        assert received[0]["type"] == "sandbox_output"
        assert received[0]["data"]["line"] == "hello"
        assert received[0]["data"]["seq"] == 5
        assert received[0]["data"]["stream"] == "stdout"

    @pytest.mark.asyncio
    async def test_context_var_isolation_across_tasks(self) -> None:
        """ContextVar is isolated per asyncio task context."""
        from app.tools.sandbox_sse import (
            clear_sse_emitter,
            emit_sandbox_output,
            set_sse_emitter,
        )

        received_a: list[dict] = []
        received_b: list[dict] = []

        async def task_a():
            async def emitter_a(ev: dict) -> None:
                received_a.append(ev)

            set_sse_emitter(emitter_a)
            await emit_sandbox_output("sb", "t", "stdout", "from-a", 0)
            clear_sse_emitter()

        async def task_b():
            # No emitter set in task_b — should get nothing
            await emit_sandbox_output("sb", "t", "stdout", "from-b", 0)

        await asyncio.gather(task_a(), task_b())
        assert len(received_a) == 1
        assert len(received_b) == 0

    @pytest.mark.asyncio
    async def test_emitter_failure_does_not_raise(self) -> None:
        """A failing emitter is caught and logged — tool execution continues."""
        from app.tools.sandbox_sse import (
            clear_sse_emitter,
            emit_sandbox_output,
            set_sse_emitter,
        )

        async def bad_emitter(ev: dict) -> None:
            raise RuntimeError("boom")

        set_sse_emitter(bad_emitter)
        try:
            await emit_sandbox_output("sb", "t", "stdout", "line", 0)  # must not raise
        finally:
            clear_sse_emitter()


# ---------------------------------------------------------------------------
# Tool registry — conditional mounting
# ---------------------------------------------------------------------------


class TestSandboxToolRegistry:
    def test_sandbox_tools_not_mounted_without_api_key(self) -> None:
        """When E2B_API_KEY is unset, sandbox tools must NOT appear in create_common_tools()."""
        with patch.dict(os.environ, {}, clear=True):
            os.environ.pop("E2B_API_KEY", None)
            from app.sse.tool_presentation import clear_tool_registry_cache
            from app.tools.common.tools import create_common_tools

            clear_tool_registry_cache()
            tools = create_common_tools()
        names = {t.name for t in tools}
        assert "sandbox_create" not in names
        assert "sandbox_run" not in names

    def test_sandbox_tools_mounted_with_api_key(self) -> None:
        """When E2B_API_KEY is set, sandbox tools appear in create_common_tools()."""
        with patch.dict(os.environ, {"E2B_API_KEY": DUMMY_API_KEY}):
            # Avoid importing e2b at module level — mock it
            with patch.dict("sys.modules", {"e2b": MagicMock()}):
                from app.sse.tool_presentation import clear_tool_registry_cache
                from app.tools.common.tools import create_common_tools

                clear_tool_registry_cache()
                tools = create_common_tools()
        names = {t.name for t in tools}
        assert "sandbox_create" in names
        assert "sandbox_destroy" in names
        assert "sandbox_run" in names
        assert "sandbox_pty_run" in names
