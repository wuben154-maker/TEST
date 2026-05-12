"""Stripe webhook and billing settings validation."""

from unittest.mock import MagicMock, patch

from fastapi.testclient import TestClient

from app.api.auth import get_current_user
from app.main import app


def test_stripe_webhook_rejects_bad_signature():
    with patch("app.api.billing_api.get_settings") as m:
        s = MagicMock()
        s.stripe_webhook_secret = "whsec_test"
        s.stripe_secret_key = "sk_test"
        m.return_value = s

        def boom(*_a, **_k):
            raise RuntimeError("No signatures found matching the expected signature")

        with patch("stripe.Webhook.construct_event", side_effect=boom):
            client = TestClient(app)
            r = client.post(
                "/webhooks/stripe",
                content=b"{}",
                headers={"stripe-signature": "t=1,v1=abc"},
            )
    assert r.status_code == 400
    assert r.json().get("detail") == "Invalid signature"


def test_patch_billing_settings_rejects_over_server_max():
    client = TestClient(app)
    fake = MagicMock()
    fake.database_mode = "supabase"
    fake.billing_max_monthly_spend_cap_usd = 100.0
    app.dependency_overrides[get_current_user] = lambda: {
        "id": "550e8400-e29b-41d4-a716-446655440000",
        "email": "a@b.co",
    }
    try:
        with patch("app.api.billing_api.get_settings", return_value=fake):
            r = client.patch(
                "/billing/settings",
                json={"monthly_spend_cap_usd": 200.0},
            )
        assert r.status_code == 400
    finally:
        app.dependency_overrides.clear()
