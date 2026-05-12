"""GET /account/overview aggregates."""

from unittest.mock import AsyncMock, MagicMock, patch

from fastapi.testclient import TestClient

from app.api.auth import get_current_user
from app.main import app


def test_account_overview_requires_auth():
    client = TestClient(app)
    assert client.get("/account/overview").status_code == 401


def test_account_overview_local_mocked():
    client = TestClient(app)
    app.dependency_overrides[get_current_user] = lambda: {
        "id": "550e8400-e29b-41d4-a716-446655440000",
        "email": "a@b.co",
    }
    fake_settings = MagicMock()
    fake_settings.database_mode = "local"
    mock_overview = AsyncMock(
        return_value={
            "project_count": 3,
            "analysis_sessions_count": 7,
            "total_llm_tokens_lifetime": 1200,
        }
    )
    try:
        with patch("app.api.account_api.get_settings", return_value=fake_settings):
            with patch("app.api.account_api._overview_local_async", mock_overview):
                r = client.get("/account/overview")
        assert r.status_code == 200
        assert r.json() == {
            "project_count": 3,
            "analysis_sessions_count": 7,
            "total_llm_tokens_lifetime": 1200,
        }
        mock_overview.assert_awaited_once_with("550e8400-e29b-41d4-a716-446655440000")
    finally:
        app.dependency_overrides.clear()
