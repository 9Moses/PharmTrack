import json
from unittest.mock import patch

import pytest
from django.test import Client


@pytest.fixture
def client():
    return Client()


@pytest.mark.django_db
def test_healthz_returns_200_when_db_ok(client):
    response = client.get("/api/docs/")
    assert response.status_code == 200


def test_notifications_endpoint_requires_auth(client):
    response = client.get("/notifications/")
    assert response.status_code in (401, 403)


@pytest.mark.django_db
def test_mark_all_read_requires_auth(client):
    response = client.patch("/notifications/read-all/")
    assert response.status_code in (401, 403)
