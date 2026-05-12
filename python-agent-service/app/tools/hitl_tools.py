"""Human-in-the-loop tools (explicit user input via LangGraph interrupt)."""

from __future__ import annotations

import uuid
from typing import Any, Literal

from langchain_core.tools import StructuredTool
from langgraph.types import interrupt
from pydantic import BaseModel, Field, model_validator


class FieldSpec(BaseModel):
    """Typed specification for a single form field (kind='form').

    Serialized to camelCase ``paramType`` in the interrupt payload so that
    ``hitl_interrupt_sse.py`` can pass it through to the frontend unchanged.
    """

    name: str = Field(description="Identifier (e.g. 'api_url', 'username')")
    label: str = Field(description="Human-readable label shown to user")
    param_type: str = Field(
        default="text",
        description="text | password | url | number | email",
    )
    required: bool = Field(default=True)
    placeholder: str | None = Field(default=None)

    def to_interrupt_dict(self) -> dict[str, Any]:
        """Serialize to the camelCase format expected by hitl_interrupt_sse."""
        return {
            "name": self.name,
            "label": self.label,
            "paramType": self.param_type,
            "required": self.required,
            "placeholder": self.placeholder,
        }


class RequestUserInputArgs(BaseModel):
    """Arguments for ``request_user_input`` tool."""

    kind: Literal["choice", "form", "text"] = Field(
        description=(
            "text: open-ended question (scope, intent, context). "
            "choice: pick one from 2-6 options. "
            "form: structured fields (credentials, config, multi-param)."
        )
    )
    prompt: str = Field(description="User-facing question or instructions")
    options: list[str] | None = Field(
        default=None,
        description="Required for kind=choice: list of option labels (2-6 items)",
    )
    fields: list[FieldSpec] | None = Field(
        default=None,
        description="Required for kind=form: structured input fields",
    )
    request_id: str | None = Field(
        default=None,
        description="Optional stable id for UI correlation; auto-generated if omitted",
    )

    @model_validator(mode="after")
    def _check_kind_fields(self) -> "RequestUserInputArgs":
        if self.kind == "choice" and not self.options:
            raise ValueError("options must be non-empty when kind='choice'")
        if self.kind == "form" and not self.fields:
            raise ValueError("fields must be non-empty when kind='form'")
        return self


def _request_user_input_impl(
    kind: Literal["choice", "form", "text"],
    prompt: str,
    options: list[str] | None = None,
    fields: list[FieldSpec] | None = None,
    request_id: str | None = None,
) -> dict[str, Any]:
    """Pause graph until human provides input; resume value is returned to the model."""
    rid = (request_id or "").strip() or str(uuid.uuid4())
    payload: dict[str, Any] = {
        "interruptKind": "user_input_v1",
        "requestId": rid,
        "kind": kind,
        "prompt": prompt,
        "options": options,
        "fields": [f.to_interrupt_dict() for f in fields] if fields else None,
    }
    response = interrupt(payload)
    return {
        "ok": True,
        "requestId": rid,
        "response": response,
    }


DEFAULT_REQUEST_USER_INPUT_DESCRIPTION = (
    "Ask the human operator a question and wait for an answer. "
    "Use for missing parameters, clarifications, or explicit choices. "
    "Do not use for dangerous-tool approval; that is handled by policy."
)


def create_hitl_tools(
    *, description_override: str | None = None
) -> list[StructuredTool]:
    """Tools that participate in custom HITL (pattern C).

    ``description_override`` comes from
    ``config/tool_presentation.yaml`` when set.
    """
    desc = (
        (description_override or "").strip()
        or DEFAULT_REQUEST_USER_INPUT_DESCRIPTION
    )
    return [
        StructuredTool.from_function(
            name="request_user_input",
            description=desc,
            func=_request_user_input_impl,
            args_schema=RequestUserInputArgs,
        ),
    ]
