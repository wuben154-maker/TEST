"""Unit tests for FieldSpec, RequestUserInputArgs, and interrupt payload serialization."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from app.tools.hitl_tools import FieldSpec, RequestUserInputArgs


# ---------------------------------------------------------------------------
# FieldSpec
# ---------------------------------------------------------------------------


class TestFieldSpec:
    def test_minimal(self) -> None:
        f = FieldSpec(name="host", label="Target host")
        assert f.name == "host"
        assert f.label == "Target host"
        assert f.param_type == "text"
        assert f.required is True
        assert f.placeholder is None

    def test_full(self) -> None:
        f = FieldSpec(
            name="api_key",
            label="API Key",
            param_type="password",
            required=True,
            placeholder="sk-...",
        )
        assert f.param_type == "password"
        assert f.placeholder == "sk-..."

    def test_to_interrupt_dict_camel_case(self) -> None:
        f = FieldSpec(
            name="api_url",
            label="API URL",
            param_type="url",
            required=True,
            placeholder="https://...",
        )
        d = f.to_interrupt_dict()
        assert d == {
            "name": "api_url",
            "label": "API URL",
            "paramType": "url",
            "required": True,
            "placeholder": "https://...",
        }

    def test_to_interrupt_dict_defaults(self) -> None:
        d = FieldSpec(name="x", label="X").to_interrupt_dict()
        assert d["paramType"] == "text"
        assert d["required"] is True
        assert d["placeholder"] is None

    def test_missing_name_raises(self) -> None:
        with pytest.raises(ValidationError):
            FieldSpec(label="no name")  # type: ignore[call-arg]

    def test_missing_label_raises(self) -> None:
        with pytest.raises(ValidationError):
            FieldSpec(name="no_label")  # type: ignore[call-arg]


# ---------------------------------------------------------------------------
# RequestUserInputArgs — kind=text
# ---------------------------------------------------------------------------


class TestRequestUserInputText:
    def test_text_minimal(self) -> None:
        args = RequestUserInputArgs(kind="text", prompt="What do you want?")
        assert args.kind == "text"
        assert args.options is None
        assert args.fields is None

    def test_text_ignores_extra_options(self) -> None:
        args = RequestUserInputArgs(
            kind="text", prompt="Q", options=["a", "b"]
        )
        assert args.options == ["a", "b"]


# ---------------------------------------------------------------------------
# RequestUserInputArgs — kind=choice
# ---------------------------------------------------------------------------


class TestRequestUserInputChoice:
    def test_choice_valid(self) -> None:
        args = RequestUserInputArgs(
            kind="choice",
            prompt="Pick one",
            options=["Quick triage", "Deep analysis"],
        )
        assert args.kind == "choice"
        assert len(args.options) == 2  # type: ignore[arg-type]

    def test_choice_missing_options_raises(self) -> None:
        with pytest.raises(ValidationError, match="options must be non-empty"):
            RequestUserInputArgs(kind="choice", prompt="Pick one")

    def test_choice_empty_options_raises(self) -> None:
        with pytest.raises(ValidationError, match="options must be non-empty"):
            RequestUserInputArgs(kind="choice", prompt="Pick one", options=[])


# ---------------------------------------------------------------------------
# RequestUserInputArgs — kind=form
# ---------------------------------------------------------------------------


class TestRequestUserInputForm:
    def test_form_valid(self) -> None:
        args = RequestUserInputArgs(
            kind="form",
            prompt="Enter credentials",
            fields=[
                FieldSpec(name="username", label="Username"),
                FieldSpec(
                    name="password",
                    label="Password",
                    param_type="password",
                ),
            ],
        )
        assert args.kind == "form"
        assert len(args.fields) == 2  # type: ignore[arg-type]
        assert args.fields[0].name == "username"  # type: ignore[index]
        assert args.fields[1].param_type == "password"  # type: ignore[index]

    def test_form_missing_fields_raises(self) -> None:
        with pytest.raises(ValidationError, match="fields must be non-empty"):
            RequestUserInputArgs(kind="form", prompt="Enter creds")

    def test_form_empty_fields_raises(self) -> None:
        with pytest.raises(ValidationError, match="fields must be non-empty"):
            RequestUserInputArgs(kind="form", prompt="Enter creds", fields=[])


# ---------------------------------------------------------------------------
# RequestUserInputArgs — request_id
# ---------------------------------------------------------------------------


class TestRequestId:
    def test_request_id_optional(self) -> None:
        args = RequestUserInputArgs(kind="text", prompt="Q")
        assert args.request_id is None

    def test_request_id_preserved(self) -> None:
        args = RequestUserInputArgs(
            kind="text", prompt="Q", request_id="custom-123"
        )
        assert args.request_id == "custom-123"
