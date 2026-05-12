"""SOC alert API tools aggregator."""

from __future__ import annotations

from langchain_core.tools import StructuredTool

from ..action_adaptor import create_soc_alert_action_tools
from .virustotal.api_virustotal_tools import create_soc_alert_virustotal_tools
from .solve_plan_executor_tool import create_execute_soc_solve_plan_tool


def create_soc_alert_api_tools() -> list[StructuredTool]:
    """Create SOC-alert action tools plus node3 batch executor."""
    return [
        *create_soc_alert_action_tools(),
        *create_soc_alert_virustotal_tools(),
        create_execute_soc_solve_plan_tool(),
    ]
