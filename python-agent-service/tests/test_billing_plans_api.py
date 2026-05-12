"""Billing plans catalog API contract.

Stage 1 of `billing-plan-benefits-ux`:
- `GET /billing/plans` returns Credits + benefit payload per plan.
- Legacy `included_tokens_per_period` is no longer emitted by API.
"""

from unittest.mock import AsyncMock, MagicMock, patch

from fastapi.testclient import TestClient

from app.main import app


def _sample_local_plans() -> list[dict]:
    return [
        {
            "slug": "free",
            "display_name": "Free",
            "monthly_price_usd": 0.0,
            "sort_order": 0,
            "included_credits_usd": 5.0,
            "credits_label": "credits",
            "tagline_json": {"en": "Try it", "zh": "试用"},
            "features_json": [
                {"id": "workspace_basic", "text": {"en": "Full workspace", "zh": "完整工作区"}},
            ],
            "quota_hints": [
                {
                    "id": "concurrent_analyses",
                    "value": "1",
                    "label": {"en": "Concurrent analyses", "zh": "并发分析数"},
                }
            ],
        },
        {
            "slug": "pro",
            "display_name": "Pro",
            "monthly_price_usd": 40.0,
            "sort_order": 1,
            "included_credits_usd": 40.0,
            "credits_label": "credits",
            "tagline_json": {"en": "Daily security teams", "zh": "日常调查团队"},
            "features_json": [
                {"id": "models_pro", "text": {"en": "Frontier models", "zh": "旗舰模型"}},
            ],
            "quota_hints": [
                {
                    "id": "concurrent_analyses",
                    "value": "3",
                    "label": {"en": "Concurrent analyses", "zh": "并发分析数"},
                }
            ],
        },
    ]


def test_billing_plans_returns_credits_and_benefits_local_mocked():
    """A-02 / A-06: each plan exposes Credits + structured benefit payload."""
    client = TestClient(app)
    fake_settings = MagicMock()
    fake_settings.database_mode = "local"
    sample = _sample_local_plans()
    mock_list = AsyncMock(return_value=sample)
    with patch("app.api.billing_api.get_settings", return_value=fake_settings):
        with patch("app.api.billing_api._list_plans_local_async", mock_list):
            r = client.get("/billing/plans")
    assert r.status_code == 200
    body = r.json()
    plans = body["plans"]
    assert len(plans) == 2
    pro = next(p for p in plans if p["slug"] == "pro")
    assert pro["included_credits_usd"] == 40.0
    assert pro["credits_label"] == "credits"
    assert pro["tagline_json"]["en"]
    assert pro["features_json"][0]["id"] == "models_pro"
    assert pro["quota_hints"][0]["id"] == "concurrent_analyses"


def test_billing_plans_response_omits_legacy_token_field():
    """A-09: legacy `included_tokens_per_period` is not emitted."""
    client = TestClient(app)
    fake_settings = MagicMock()
    fake_settings.database_mode = "local"
    sample = _sample_local_plans()
    mock_list = AsyncMock(return_value=sample)
    with patch("app.api.billing_api.get_settings", return_value=fake_settings):
        with patch("app.api.billing_api._list_plans_local_async", mock_list):
            r = client.get("/billing/plans")
    body = r.json()
    for p in body["plans"]:
        assert "included_tokens_per_period" not in p, (
            "legacy field must not appear on /billing/plans response"
        )


def test_billing_plans_response_omits_stripe_price_id():
    """Existing safety: never expose stripe_price_id from public catalog."""
    client = TestClient(app)
    fake_settings = MagicMock()
    fake_settings.database_mode = "local"
    sample = _sample_local_plans()
    mock_list = AsyncMock(return_value=sample)
    with patch("app.api.billing_api.get_settings", return_value=fake_settings):
        with patch("app.api.billing_api._list_plans_local_async", mock_list):
            r = client.get("/billing/plans")
    for p in r.json()["plans"]:
        assert "stripe_price_id" not in p
