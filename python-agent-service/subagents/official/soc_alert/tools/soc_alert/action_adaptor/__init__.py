"""Generic SOC action adaptor for vendor tool mapping."""

from .resolver import (
    SUPPORTED_SOC_ACTION_VENDORS,
    build_vendor_params,
    execute_generic_action,
    list_generic_actions,
    resolve_generic_action,
)
from .tool_factory import create_soc_alert_action_tools
from .types import GenericActionSelection, ResolvedActionCall

__all__ = [
    "SUPPORTED_SOC_ACTION_VENDORS",
    "GenericActionSelection",
    "ResolvedActionCall",
    "build_vendor_params",
    "list_generic_actions",
    "resolve_generic_action",
    "execute_generic_action",
    "create_soc_alert_action_tools",
]
