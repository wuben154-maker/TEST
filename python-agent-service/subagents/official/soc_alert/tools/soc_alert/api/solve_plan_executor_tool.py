"""StructuredTool: run node3 solve plan (auth + vendor APIs) for node5 execution_result."""

from __future__ import annotations

from typing import Any

from langchain_core.tools import StructuredTool
from pydantic import BaseModel, Field

from subagents.official.soc_alert.tools.soc_alert.execution.solve_plan_executor import (
    execute_solve_plan,
    parse_solve_plan_text,
)


class ExecuteSocSolvePlanInput(BaseModel):
    """Inputs for batch execution of a soc_solve_v1 plan."""

    solve_plan: dict[str, Any] | str = Field(
        ...,
        description=(
            "Node3 output: soc_solve_v1 JSON object, or a string containing only JSON "
            "(optional ```json fences are stripped server-side)."
        ),
    )
    raw_alert_context: dict[str, Any] | None = Field(
        default=None,
        description="Raw alert envelope for param autofill and auth scope (same as generic SOC actions).",
    )
    session_id: str | None = Field(
        default=None,
        description="Session scope for vendor auth ephemeral cache.",
    )
    request_id: str | None = Field(
        default=None,
        description="Request scope for ephemeral auth and HITL correlation.",
    )
    user_id: str | None = Field(
        default=None,
        description="User id for persistent vendor connections when remember_auth is used.",
    )


async def _run_execute_soc_solve_plan(
    solve_plan: dict[str, Any] | str,
    raw_alert_context: dict[str, Any] | None = None,
    session_id: str | None = None,
    request_id: str | None = None,
    user_id: str | None = None,
) -> dict[str, Any]:
    plan: dict[str, Any] | str = solve_plan
    if isinstance(plan, str):
        plan = parse_solve_plan_text(plan)
    return await execute_solve_plan(
        plan,
        raw_alert_context=raw_alert_context,
        session_id=session_id,
        request_id=request_id,
        user_id=user_id,
    )


def create_execute_soc_solve_plan_tool() -> StructuredTool:
    """Single tool wrapping ``execute_solve_plan`` (node3 -> APIs -> soc_execution_v1)."""

    async def _coro(
        solve_plan: dict[str, Any] | str,
        raw_alert_context: dict[str, Any] | None = None,
        session_id: str | None = None,
        request_id: str | None = None,
        user_id: str | None = None,
    ) -> dict[str, Any]:
        return await _run_execute_soc_solve_plan(
            solve_plan=solve_plan,
            raw_alert_context=raw_alert_context,
            session_id=session_id,
            request_id=request_id,
            user_id=user_id,
        )

    return StructuredTool.from_function(
        name="execute_soc_solve_plan",
        description=(
            "Mandatory after node3: run the soc_solve_v1 JSON through the platform executor. "
            "Resolves vendor credentials (database, ephemeral cache, or HITL form via interrupt), "
            "executes each non-null generic_action, returns soc_execution_v1. "
            "Use the returned object verbatim as execution_result when applying node5_judge.md."
        ),
        func=_coro,
        coroutine=_coro,
        args_schema=ExecuteSocSolvePlanInput,
    )
