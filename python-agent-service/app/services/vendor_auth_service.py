"""Compatibility wrapper for SOC vendor auth service.

This module keeps legacy imports stable while moving the implementation
into the SOC domain package.
"""

from subagents.official.soc_alert.tools.soc_alert.auth.service import (
    VendorAuthService,
    get_vendor_auth_service,
)

__all__ = ["VendorAuthService", "get_vendor_auth_service"]

