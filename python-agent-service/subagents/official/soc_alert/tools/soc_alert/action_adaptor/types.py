"""Shared models for generic SOC action selection and resolution."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field


class GenericActionSelection(BaseModel):
    """Generic action emitted by planner (node3)."""

    generic_action: str = Field(description="Vendor-agnostic action name, snake_case.")
    action_params: dict[str, Any] = Field(
        default_factory=dict,
        description="Action parameters before vendor mapping.",
    )
    action_reason: str | None = Field(
        default=None,
        description="Optional reason for selecting this generic action.",
    )


class ResolvedActionCall(BaseModel):
    """Concrete vendor tool invocation resolved from a generic action."""

    vendor: str = Field(description="Vendor key, e.g. elastic_security.")
    generic_action: str = Field(description="Vendor-agnostic action name.")
    tool_name: str = Field(description="Concrete tool name.")
    tool_input: dict[str, Any] = Field(default_factory=dict, description="Concrete tool input.")
