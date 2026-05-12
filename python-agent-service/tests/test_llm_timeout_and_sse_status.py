"""Tests for LLM per-request timeout propagation and SSE tool_result status derivation."""

import sys
from pathlib import Path
from unittest.mock import patch, MagicMock

import pytest

APP_DIR = Path(__file__).parent.parent
if str(APP_DIR) not in sys.path:
    sys.path.insert(0, str(APP_DIR))


# ---------------------------------------------------------------------------
# 1. _derive_tool_status
# ---------------------------------------------------------------------------
from app.parsers.tool_status import derive_tool_status as _derive_tool_status


class TestDeriveToolStatus:
    def test_success_on_normal_json(self):
        assert _derive_tool_status('{"result": "ok", "error": null}') == "success"

    def test_success_on_plain_text(self):
        assert _derive_tool_status("All good") == "success"

    def test_success_on_empty(self):
        assert _derive_tool_status("") == "success"
        assert _derive_tool_status(None) == "success"

    def test_error_on_truthy_error_key(self):
        assert _derive_tool_status('{"error": "something broke", "sandbox_id": null}') == "error"

    def test_error_on_nonetype_message(self):
        out = '{"error": "\'NoneType\' object has no attribute \'create\'", "sandbox_id": null}'
        assert _derive_tool_status(out) == "error"

    def test_success_when_error_is_none(self):
        assert _derive_tool_status('{"error": null, "sandbox_id": "sb-123"}') == "success"

    def test_success_when_error_is_empty_string(self):
        assert _derive_tool_status('{"error": "", "data": 1}') == "success"

    def test_success_on_non_dict_json(self):
        assert _derive_tool_status("[1, 2, 3]") == "success"

    def test_success_on_invalid_json(self):
        assert _derive_tool_status("{malformed") == "success"

    def test_non_string_input(self):
        assert _derive_tool_status(42) == "success"
        assert _derive_tool_status({"error": "x"}) == "success"  # not JSON string, dict repr

    def test_error_on_deepagents_read_file_error_prefix(self):
        # DeepAgents filesystem tools return plain strings "Error: ..." on failure.
        # These must surface as SSE status="error" so the UI + master agent can
        # treat them as hard failures (not silent successes).
        msg = "Error: File '/workspace/ghost.php' not found"
        assert _derive_tool_status(msg) == "error"

    def test_error_case_insensitive_and_with_space(self):
        assert _derive_tool_status("error: lower case prefix") == "error"
        assert _derive_tool_status("ERROR reading file") == "error"

    def test_success_when_error_word_appears_mid_text(self):
        # Only the leading token matters; "error" mid-sentence stays success.
        assert _derive_tool_status("No errors found") == "success"
        assert _derive_tool_status("Result: the error budget is fine") == "success"


# ---------------------------------------------------------------------------
# 1b. SSE tool_output error bypass
#     read_file / other tools with emit_output=False must still surface
#     plain "Error: ..." payloads so the UI + user see the failure reason.
# ---------------------------------------------------------------------------
from app.parsers.deepagents_stream_adapter import (  # noqa: E402
    _sse_tool_output,
)
from app.sse.envelope import tag_merged_subagent_sse  # noqa: E402


class TestSSEToolOutputErrorBypass:
    def test_read_file_success_payload_suppressed(self):
        # read_file has emit_output=False → normal successful content omitted.
        assert _sse_tool_output("read_file", "line1\nline2\n") == ""

    def test_read_file_error_payload_preserved(self):
        msg = "Error: File '/workspace/ghost.php' not found"
        out = _sse_tool_output("read_file", msg)
        assert out and "not found" in out

    def test_read_file_error_case_insensitive(self):
        out = _sse_tool_output("read_file", "error: bad path")
        assert out and "bad path" in out

    def test_non_error_empty_payload_returns_empty(self):
        # Empty/None → still empty; no spurious passthrough.
        assert _sse_tool_output("read_file", "") == ""
        assert _sse_tool_output("read_file", None) == ""  # type: ignore[arg-type]

    def test_emit_enabled_tool_unaffected(self):
        # grep has emit_output=True by default → normal text is passed through.
        out = _sse_tool_output("grep", "hit: foo.py:12")
        assert "foo.py" in out


class TestTagMergedSubagentSSEErrorBypass:
    def _base_event(self, **over):
        ev = {
            "type": "tool_result",
            "toolName": "read_file",
            "toolOutput": "line1\n",
            "status": "success",
        }
        ev.update(over)
        return ev

    def test_read_file_success_output_cleared(self):
        ev = tag_merged_subagent_sse(self._base_event())
        # read_file has emit_output=False → success output stripped for bandwidth.
        assert ev["toolOutput"] == ""

    def test_read_file_plain_error_output_kept(self):
        ev = tag_merged_subagent_sse(
            self._base_event(
                toolOutput="Error: path must be under /workspace/",
                status="error",
            )
        )
        assert ev["toolOutput"].startswith("Error:")

    def test_error_status_bypass_even_without_prefix(self):
        # If upstream already marked status="error" but the payload is
        # structured (e.g. ToolMessage content), keep it visible.
        ev = tag_merged_subagent_sse(
            self._base_event(
                toolOutput="something went wrong server-side",
                status="error",
            )
        )
        assert "wrong" in ev["toolOutput"]


# ---------------------------------------------------------------------------
# 2. LLM factory timeout propagation
# ---------------------------------------------------------------------------

def _make_registry(provider_id, sdk_model="test-model", extra_model_cfg=None):
    """Build a mock registry returning a single model config."""
    model_cfg = {"sdk_model": sdk_model}
    if extra_model_cfg:
        model_cfg.update(extra_model_cfg)
    mock_reg = MagicMock()
    mock_reg.get_model_config.return_value = {
        "provider_id": provider_id,
        "model_id": f"{provider_id}/{sdk_model}",
        "model": model_cfg,
        "provider": {"api_key": "test-key", "base_url": None},
    }
    mock_reg.get_default_model.return_value = f"{provider_id}/{sdk_model}"
    return mock_reg


def _settings_with_timeout(timeout_val):
    """Return a mock Settings object with the given llm_request_timeout_seconds."""
    s = MagicMock()
    s.llm_request_timeout_seconds = timeout_val
    s.enable_anthropic_thinking = False
    s.enable_gemini_thinking = False
    return s


class TestFactoryTimeoutPropagation:
    """Verify get_model passes timeout and max_retries to each provider."""

    def test_anthropic_receives_timeout_and_no_retries(self):
        with (
            patch("app.llm_gateway.factory.get_registry", return_value=_make_registry("anthropic", "claude-test")),
            patch("app.llm_gateway.factory.get_settings", return_value=_settings_with_timeout(90)),
            patch("app.llm_gateway.factory.ChatAnthropic") as MockChat,
        ):
            from app.llm_gateway.factory import get_model
            get_model("anthropic/claude-test")
            kwargs = MockChat.call_args[1]
            assert kwargs["timeout"] == 90.0
            assert kwargs["max_retries"] == 0

    def test_openai_receives_timeout_and_no_retries(self):
        with (
            patch("app.llm_gateway.factory.get_registry", return_value=_make_registry("openai", "gpt-4o")),
            patch("app.llm_gateway.factory.get_settings", return_value=_settings_with_timeout(60)),
            patch("app.llm_gateway.factory.ChatOpenAI") as MockChat,
        ):
            from app.llm_gateway.factory import get_model
            get_model("openai/gpt-4o")
            kwargs = MockChat.call_args[1]
            assert kwargs["timeout"] == 60.0
            assert kwargs["max_retries"] == 0

    def test_google_receives_timeout(self):
        with (
            patch("app.llm_gateway.factory.get_registry", return_value=_make_registry("google", "gemini-test")),
            patch("app.llm_gateway.factory.get_settings", return_value=_settings_with_timeout(120)),
            patch("app.llm_gateway.factory.ChatGoogleGenerativeAI") as MockChat,
        ):
            from app.llm_gateway.factory import get_model
            get_model("google/gemini-test")
            kwargs = MockChat.call_args[1]
            assert kwargs["timeout"] == 120.0

    @pytest.mark.parametrize("provider", ["kimi", "minimax", "glm", "doubao"])
    def test_openai_compatible_receives_timeout_and_no_retries(self, provider):
        reg = _make_registry(provider)
        reg.get_model_config.return_value["provider"]["base_url"] = f"https://{provider}.com/v1"
        with (
            patch("app.llm_gateway.factory.get_registry", return_value=reg),
            patch("app.llm_gateway.factory.get_settings", return_value=_settings_with_timeout(45)),
            patch("app.llm_gateway.factory.ChatOpenAI") as MockChat,
        ):
            from app.llm_gateway.factory import get_model
            get_model(f"{provider}/test-model")
            kwargs = MockChat.call_args[1]
            assert kwargs["timeout"] == 45.0
            assert kwargs["max_retries"] == 0

    def test_no_timeout_when_zero(self):
        """timeout=0 is falsy, so it should NOT be passed (provider default)."""
        with (
            patch("app.llm_gateway.factory.get_registry", return_value=_make_registry("openai", "gpt-4o")),
            patch("app.llm_gateway.factory.get_settings", return_value=_settings_with_timeout(0)),
            patch("app.llm_gateway.factory.ChatOpenAI") as MockChat,
        ):
            from app.llm_gateway.factory import get_model
            get_model("openai/gpt-4o")
            kwargs = MockChat.call_args[1]
            assert "timeout" not in kwargs
