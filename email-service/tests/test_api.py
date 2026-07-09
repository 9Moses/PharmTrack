import pytest
from fastapi.testclient import TestClient

from app.main import app


@pytest.fixture
def client():
    return TestClient(app)


def test_health_endpoint_returns_healthy(client):
    response = client.get("/health")
    assert response.status_code == 200
    body = response.json()
    assert body["status"] in ("healthy", "degraded")
    assert body["service"] == "PharmTrack Email Service"
    assert "version" in body


def test_root_endpoint_returns_service_info(client):
    response = client.get("/")
    assert response.status_code == 200
    body = response.json()
    assert body["service"] == "PharmTrack Email Service"
    assert body["docs"] == "/docs"


def test_send_endpoint_rejects_invalid_payload(client):
    response = client.post("/send", json={"to": "not-an-email", "subject": "Hi", "text_body": "Hello"})
    assert response.status_code == 422
