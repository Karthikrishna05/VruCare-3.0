from unittest.mock import patch

import pytest


def test_healthz_says_ok(client):
    response = client.get("/healthz")
    assert response.status_code == 200
    assert response.content == b"ok"


@pytest.mark.django_db
def test_readyz_reports_every_dependency_ok(client):
    response = client.get("/readyz")
    assert response.status_code == 200
    assert response.json() == {
        "status": "ok",
        "checks": {"database": "ok", "cache": "ok", "corpus": "ok"},
    }


@pytest.mark.django_db
def test_readyz_returns_503_and_names_failing_dependencies(client):
    broken = ConnectionError("redis://user:secret@host")
    with patch("config.views.cache.set", side_effect=broken):
        response = client.get("/readyz")
    assert response.status_code == 503
    assert response.json() == {
        "status": "unavailable",
        "checks": {"database": "ok", "cache": "error:ConnectionError", "corpus": "ok"},
    }
    assert "secret" not in response.content.decode()
