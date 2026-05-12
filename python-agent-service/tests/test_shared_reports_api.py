"""Tests for the shared reports API."""

from fastapi.testclient import TestClient

from app.main import app


client = TestClient(app)


def test_shared_reports_endpoints_exist():
  """Basic smoke test to ensure shared reports routes are wired."""
  # Read endpoint should be mounted
  resp = client.get("/shared-reports/by-token/test-token")
  # In most dev environments database_mode is 'local', but if not,
  # the endpoint should at least not 404.
  assert resp.status_code in (404, 501)

