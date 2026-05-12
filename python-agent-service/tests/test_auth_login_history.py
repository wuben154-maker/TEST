"""GET /auth/login-history and login event wiring (smoke)."""

from unittest.mock import AsyncMock, patch

from fastapi.testclient import TestClient

from app.api.auth import get_current_user
from app.main import app


def test_login_history_requires_auth():
    client = TestClient(app)
    assert client.get("/auth/login-history").status_code == 401


def test_login_history_returns_list_mocked():
    client = TestClient(app)
    app.dependency_overrides[get_current_user] = lambda: {
        "id": "550e8400-e29b-41d4-a716-446655440000",
        "email": "a@b.co",
    }
    sample = [
        {
            "id": "e1",
            "logged_in_at": "2026-04-08T12:00:00+00:00",
            "ip_address": "127.0.0.1",
            "user_agent": "pytest",
            "ip_country": "Local",
        }
    ]
    mock_list = AsyncMock(return_value=sample)
    try:
        with patch("app.api.auth.list_recent_logins_async", mock_list):
            r = client.get("/auth/login-history?limit=5")
        assert r.status_code == 200
        assert r.json() == sample
        mock_list.assert_awaited_once_with("550e8400-e29b-41d4-a716-446655440000", 5)
    finally:
        app.dependency_overrides.clear()
