"""SOC alert specific API tools package."""

from __future__ import annotations

def create_soc_alert_api_tools():
    """Lazy import to avoid package-level circular dependency."""
    from .api_tools import create_soc_alert_api_tools as _impl

    return _impl()


def create_soc_alert_aws_api_tools():
    """Lazy import to avoid package-level circular dependency."""
    from .aws.api_tools_aws import create_soc_alert_aws_api_tools as _impl

    return _impl()


def create_soc_alert_splunk_tools():
    """Lazy import to avoid package-level circular dependency."""
    from .splunk.api_splunk_tools import create_soc_alert_splunk_tools as _impl

    return _impl()


def create_soc_alert_ndr_tools():
    """Lazy import to avoid package-level circular dependency."""
    from .api_ndr_tools import create_soc_alert_ndr_tools as _impl

    return _impl()


def create_soc_alert_onesec_tools():
    """Lazy import to avoid package-level circular dependency."""
    from .onesec.api_onesec_tools import create_soc_alert_onesec_tools as _impl

    return _impl()


def create_soc_alert_virustotal_tools():
    """Lazy import to avoid package-level circular dependency."""
    from .virustotal.api_virustotal_tools import create_soc_alert_virustotal_tools as _impl

    return _impl()


def list_generic_actions(vendor: str) -> list[str]:
    """Lazy import to avoid package-level circular dependency."""
    from ..action_adaptor.resolver import list_generic_actions as _impl

    return _impl(vendor)


def resolve_generic_action(*args, **kwargs):
    """Lazy import to avoid package-level circular dependency."""
    from ..action_adaptor.resolver import resolve_generic_action as _impl

    return _impl(*args, **kwargs)


async def execute_generic_action(*args, **kwargs):
    """Lazy import to avoid package-level circular dependency."""
    from ..action_adaptor.resolver import execute_generic_action as _impl

    return await _impl(*args, **kwargs)


def build_vendor_params(*args, **kwargs):
    """Lazy import to avoid package-level circular dependency."""
    from ..action_adaptor.resolver import build_vendor_params as _impl

    return _impl(*args, **kwargs)


def create_soc_alert_action_tools():
    """Lazy import to avoid package-level circular dependency."""
    from ..action_adaptor.tool_factory import create_soc_alert_action_tools as _impl

    return _impl()


__all__ = [
    "create_soc_alert_api_tools",
    "create_soc_alert_aws_api_tools",
    "create_soc_alert_splunk_tools",
    "create_soc_alert_ndr_tools",
    "create_soc_alert_onesec_tools",
    "create_soc_alert_virustotal_tools",
    "list_generic_actions",
    "resolve_generic_action",
    "execute_generic_action",
    "build_vendor_params",
    "create_soc_alert_action_tools",
]
