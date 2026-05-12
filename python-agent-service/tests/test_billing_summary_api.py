"""`GET /billing/summary` USD-first response contract (billing-plan-benefits-ux Stage 1)."""

from unittest.mock import AsyncMock, MagicMock, patch

from fastapi.testclient import TestClient

from app.main import app


def _fake_summary_payload() -> dict:
    return {
        "plan_slug": "pro",
        "subscription_status": "active",
        "period_start": "2026-05-01T00:00:00Z",
        "period_end": "2026-06-01T00:00:00Z",
        "spent_usd_period": "12.345678",
        "monthly_spend_cap_usd": 100.0,
        "arrears_allowance_usd": 5.0,
        "included_credits_usd": 40.0,
        "credits_label": "credits",
        "tokens_used_period_estimate": 123456,
        "has_stripe_customer": False,
    }


def test_billing_summary_returns_usd_credits_fields(monkeypatch):
    """A-07: summary returns spent/cap/credits/token-estimate; no legacy fields."""
    client = TestClient(app)
    fake_settings = MagicMock()
    fake_settings.database_mode = "local"
    fake_user = {"id": "00000000-0000-0000-0000-000000000001"}

    async def _fake_summary(_uid: str) -> dict:
        return _fake_summary_payload()

    with patch("app.api.billing_api.get_settings", return_value=fake_settings):
        with patch("app.api.billing_api._summary_local_async", AsyncMock(side_effect=_fake_summary)):
            with patch("app.api.billing_api.get_current_user", return_value=fake_user):
                # FastAPI dependency override path: directly invoke endpoint.
                from app.main import app as _app
                from app.api.auth import get_current_user as _real_dep

                _app.dependency_overrides[_real_dep] = lambda: fake_user
                try:
                    r = client.get(
                        "/billing/summary",
                        headers={"Authorization": "Bearer test"},
                    )
                finally:
                    _app.dependency_overrides.pop(_real_dep, None)

    assert r.status_code == 200, r.text
    body = r.json()
    assert body["plan_slug"] == "pro"
    assert body["spent_usd_period"] == "12.345678"
    assert body["monthly_spend_cap_usd"] == 100.0
    assert body["included_credits_usd"] == 40.0
    assert body["credits_label"] == "credits"
    assert body["tokens_used_period_estimate"] == 123456
    # A-09: legacy fields must not appear.
    assert "included_tokens_per_period" not in body
    assert "tokens_used_period" not in body
