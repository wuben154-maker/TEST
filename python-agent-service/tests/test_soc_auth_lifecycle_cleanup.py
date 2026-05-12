"""Lifecycle cleanup tests for SOC ephemeral vendor auth cache."""

from __future__ import annotations

import pytest
from httpx import ASGITransport, AsyncClient

from app.main import app


@pytest.mark.anyio
async def test_cancel_analysis_clears_vendor_auth_ephemeral(monkeypatch: pytest.MonkeyPatch):
    called: dict[str, str] = {}

    class _FakeAuthService:
        async def clear_request_ephemeral(self, request_id: str) -> None:
            called["request_id"] = request_id

    monkeypatch.setattr("app.main.get_vendor_auth_service", lambda: _FakeAuthService())
    monkeypatch.setattr("app.main.cancel_producer_by_request_id", lambda _rid: True)

    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://test",
        timeout=30.0,
    ) as client:
        response = await client.post(
            "/analyze/cancel",
            json={"request_id": "req-cleanup-1"},
        )

    assert response.status_code == 200
    assert called["request_id"] == "req-cleanup-1"
