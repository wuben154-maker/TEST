"""IP geolocation helper for login audit."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.services.ip_geo import resolve_ip_country_label


@pytest.mark.asyncio
async def test_resolve_empty_or_invalid():
    assert await resolve_ip_country_label(None) is None
    assert await resolve_ip_country_label("") is None
    assert await resolve_ip_country_label("not-an-ip") is None


@pytest.mark.asyncio
async def test_resolve_private_and_loopback():
    assert await resolve_ip_country_label("127.0.0.1") == "Local"
    assert await resolve_ip_country_label("192.168.0.1") == "Local"
    assert await resolve_ip_country_label("10.0.0.1") == "Local"


@pytest.mark.asyncio
async def test_resolve_public_success_mocked():
    mock_response = MagicMock()
    mock_response.raise_for_status = MagicMock()
    mock_response.json = MagicMock(
        return_value={
            "status": "success",
            "country": "Germany",
            "countryCode": "DE",
        }
    )
    mock_client = AsyncMock()
    mock_client.get = AsyncMock(return_value=mock_response)
    mock_cm = MagicMock()
    mock_cm.__aenter__ = AsyncMock(return_value=mock_client)
    mock_cm.__aexit__ = AsyncMock(return_value=False)

    fake_settings = MagicMock()
    fake_settings.login_ip_geo_lookup_enabled = True
    fake_settings.login_ip_geo_timeout_seconds = 2.0

    with patch("app.services.ip_geo.get_settings", return_value=fake_settings):
        with patch("app.services.ip_geo.httpx.AsyncClient", return_value=mock_cm):
            out = await resolve_ip_country_label("8.8.8.8")
    assert out == "Germany (DE)"
    mock_client.get.assert_called_once()
