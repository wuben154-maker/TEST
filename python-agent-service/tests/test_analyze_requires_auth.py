"""POST /analyze, /analyze/resume, /analyze/cancel require a valid Bearer token."""

from fastapi.testclient import TestClient

from app.main import app


def test_analyze_without_authorization_returns_401():
    client = TestClient(app)
    response = client.post(
        "/analyze",
        json={"message": "hello", "stream": False},
    )
    assert response.status_code == 401


def test_analyze_resume_without_authorization_returns_401():
    client = TestClient(app)
    response = client.post(
        "/analyze/resume",
        json={
            "session_id": "s1",
            "resume": {"type": "text", "text": "ok"},
        },
    )
    assert response.status_code == 401


def test_analyze_cancel_without_authorization_returns_401():
    client = TestClient(app)
    response = client.post(
        "/analyze/cancel",
        json={"request_id": "rid-1"},
    )
    assert response.status_code == 401
