"""StructuredTool factory for generic SOC query actions."""

from __future__ import annotations

from typing import Any

from langchain_core.tools import StructuredTool
from pydantic import BaseModel, Field

from .resolver import SUPPORTED_SOC_ACTION_VENDORS, execute_generic_action, list_generic_actions


class GenericQueryActionInput(BaseModel):
    """Common tool input for one generic query action."""

    action_params: dict[str, Any] = Field(
        default_factory=dict,
        description="Canonical params produced by planning stage.",
    )
    raw_alert_context: dict[str, Any] | None = Field(
        default=None,
        description="Raw alert payload for missing-parameter autofill.",
    )
    vendor_routing: dict[str, Any] | None = Field(
        default=None,
        description="Optional routing hints from node1, e.g. vendor/platform/provider.",
    )
    vendor: str = Field(
        default="",
        description=(
            "Optional vendor id. Supported values: "
            + ", ".join(SUPPORTED_SOC_ACTION_VENDORS)
            + ". SIEM-class actions should provide vendor (or vendor_routing.provider); "
            "WEB-class actions can omit vendor and rely on runtime default vendor."
        ),
    )
    session_id: str | None = Field(
        default=None,
        description="Optional session id for user-scoped auth lookup.",
    )
    request_id: str | None = Field(
        default=None,
        description="Optional request id for ephemeral auth cache scope.",
    )
    user_id: str | None = Field(
        default=None,
        description="Optional user id for persistent auth records.",
    )


def _action_description(action_name: str) -> str:
    return (
        f"Execute SOC generic action `{action_name}` through vendor adaptor. "
        "Runtime resolver maps vendor routing and calls concrete SOC API tools."
    )


def _make_action_callable(action_name: str):
    async def _run_action(
        action_params: dict[str, Any] | None = None,
        raw_alert_context: dict[str, Any] | None = None,
        vendor_routing: dict[str, Any] | None = None,
        vendor: str = "",
        session_id: str | None = None,
        request_id: str | None = None,
        user_id: str | None = None,
    ) -> dict[str, Any]:
        return await execute_generic_action(
            vendor=vendor,
            generic_action=action_name,
            action_params=action_params,
            raw_alert_context=raw_alert_context,
            vendor_routing=vendor_routing,
            session_id=session_id,
            request_id=request_id,
            user_id=user_id,
        )

    _run_action.__name__ = action_name
    return _run_action


def create_soc_alert_action_tools() -> list[StructuredTool]:
    """Register generic query actions as StructuredTool list."""
    tools: list[StructuredTool] = []
    action_names: set[str] = set()
    for vendor_name in SUPPORTED_SOC_ACTION_VENDORS:
        action_names.update(list_generic_actions(vendor_name))
    for action_name in sorted(action_names):
        fn = _make_action_callable(action_name)
        tools.append(
            StructuredTool.from_function(
                name=action_name,
                description=_action_description(action_name),
                func=fn,
                coroutine=fn,
                args_schema=GenericQueryActionInput,
            )
        )
    return tools

