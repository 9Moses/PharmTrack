import json
import pytest
from django.test import Client


@pytest.fixture
def client():
    return Client()


def test_docs_endpoint_available(client):
    response = client.get("/api/docs/")
    assert response.status_code == 200
    assert b"swagger-ui" in response.content  # drf-spectacular uses custom title; check div id


def test_notifications_requires_auth(client):
    response = client.get("/notifications/")
    assert response.status_code in (401, 403)


def test_mark_all_read_requires_auth(client):
    response = client.patch("/notifications/read-all/")
    assert response.status_code in (401, 403)
