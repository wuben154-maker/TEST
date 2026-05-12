"""Test that _request_user_input_impl builds correct interrupt payloads for text/choice/form."""

from __future__ import annotations

from unittest.mock import patch

import pytest

from app.tools.hitl_tools import FieldSpec, _request_user_input_impl


@pytest.fixture()
def _capture_interrupt():
    """Mock ``langgraph.types.interrupt`` and capture the payload it receives."""
    payloads: list[dict] = []

    def _fake_interrupt(payload):
        payloads.append(payload)
        return "user-reply-stub"

    with patch("app.tools.hitl_tools.interrupt", side_effect=_fake_interrupt):
        yield payloads


class TestTextPayload:
    def test_text_payload_shape(self, _capture_interrupt: list[dict]) -> None:
        result = _request_user_input_impl(
            kind="text",
            prompt="What scope do you want?",
            request_id="txt-001",
        )
        assert len(_capture_interrupt) == 1
        p = _capture_interrupt[0]
        assert p["interruptKind"] == "user_input_v1"
        assert p["kind"] == "text"
        assert p["prompt"] == "What scope do you want?"
        assert p["requestId"] == "txt-001"
        assert p["options"] is None
        assert p["fields"] is None
        assert result["ok"] is True
        assert result["response"] == "user-reply-stub"

    def test_text_auto_generates_request_id(self, _capture_interrupt: list[dict]) -> None:
        _request_user_input_impl(kind="text", prompt="Q")
        rid = _capture_interrupt[0]["requestId"]
        assert isinstance(rid, str) and len(rid) > 0


class TestChoicePayload:
    def test_choice_payload_shape(self, _capture_interrupt: list[dict]) -> None:
        _request_user_input_impl(
            kind="choice",
            prompt="Pick analysis mode",
            options=["Quick triage", "Deep analysis"],
            request_id="ch-002",
        )
        p = _capture_interrupt[0]
        assert p["kind"] == "choice"
        assert p["options"] == ["Quick triage", "Deep analysis"]
        assert p["fields"] is None


class TestFormPayload:
    def test_form_payload_serializes_fieldspec(self, _capture_interrupt: list[dict]) -> None:
        fields = [
            FieldSpec(name="api_url", label="API URL", param_type="url"),
            FieldSpec(
                name="api_key",
                label="API Key",
                param_type="password",
                placeholder="sk-...",
            ),
        ]
        _request_user_input_impl(
            kind="form",
            prompt="Enter credentials",
            fields=fields,
            request_id="frm-003",
        )
        p = _capture_interrupt[0]
        assert p["kind"] == "form"
        assert p["options"] is None

        assert isinstance(p["fields"], list)
        assert len(p["fields"]) == 2

        f0 = p["fields"][0]
        assert f0 == {
            "name": "api_url",
            "label": "API URL",
            "paramType": "url",
            "required": True,
            "placeholder": None,
        }

        f1 = p["fields"][1]
        assert f1["paramType"] == "password"
        assert f1["placeholder"] == "sk-..."

    def test_form_none_fields_passes_none(self, _capture_interrupt: list[dict]) -> None:
        _request_user_input_impl(kind="text", prompt="Q", fields=None)
        assert _capture_interrupt[0]["fields"] is None
