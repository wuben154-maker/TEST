"""Unit tests for billing start-of-request gate policy."""

from decimal import Decimal

import pytest
from fastapi import HTTPException

from app.billing.gate import (
    BillingGateInputs,
    apply_billing_gate_policy,
)


def test_gate_allows_implicit_free_under_cap():
    apply_billing_gate_policy(
        BillingGateInputs(
            billable_usd=Decimal("50"),
            monthly_spend_cap_usd=Decimal("100"),
            arrears_allowance_usd=Decimal("5"),
            only_inactive_subscriptions=False,
        )
    )


def test_gate_denies_at_cap_plus_arrears():
    with pytest.raises(HTTPException) as excinfo:
        apply_billing_gate_policy(
            BillingGateInputs(
                billable_usd=Decimal("105"),
                monthly_spend_cap_usd=Decimal("100"),
                arrears_allowance_usd=Decimal("5"),
                only_inactive_subscriptions=False,
            )
        )
    assert excinfo.value.status_code == 402
    assert excinfo.value.detail["error_code"] == "BILLING_CAP_EXCEEDED"


def test_gate_allows_just_below_ceiling():
    apply_billing_gate_policy(
        BillingGateInputs(
            billable_usd=Decimal("104.99"),
            monthly_spend_cap_usd=Decimal("100"),
            arrears_allowance_usd=Decimal("5"),
            only_inactive_subscriptions=False,
        )
    )


def test_gate_denies_only_inactive_subscriptions_even_if_under_cap():
    with pytest.raises(HTTPException) as excinfo:
        apply_billing_gate_policy(
            BillingGateInputs(
                billable_usd=Decimal("0"),
                monthly_spend_cap_usd=Decimal("100"),
                arrears_allowance_usd=Decimal("5"),
                only_inactive_subscriptions=True,
            )
        )
    assert excinfo.value.status_code == 403
    assert excinfo.value.detail["error_code"] == "BILLING_PLAN_INACTIVE"
