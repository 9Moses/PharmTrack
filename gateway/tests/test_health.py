import json
from unittest.mock import patch

import pytest
from django.test import Client
from django.urls import reverse


@pytest.fixture
def client():
    return Client()


@pytest.mark.django_db
def test_healthz_returns_200_when_db_ok(client):
    response = client.get("/healthz/")
    assert response.status_code == 200
    body = json.loads(response.content)
    assert body["service"] == "pharmtrack-gateway"
    assert body["status"] == "ok"


def test_healthz_returns_503_when_db_down(client):
    from django.db.utils import OperationalError

    with patch("pharmtrack_gateway.health.connections") as mock_conns:
        mock_conns.__getitem__.return_value.cursor.side_effect = OperationalError("down")
        response = client.get("/healthz/")

    assert response.status_code == 503
    body = json.loads(response.content)
    assert body["database"] == "error"
    assert body["status"] == "error"