"""Landing and operational probes stay independent of external providers."""

from unittest.mock import patch

import pytest
from django.db import DatabaseError

import dog_finder.views as testee


def test_home_explains_registration_is_not_open(client):
    """The initial page does not pretend subscriber features exist."""
    response = client.get("/")
    assert response.status_code == 200
    assert b"Search registration is not open yet" in response.content
    assert response.headers["Referrer-Policy"] == "no-referrer"


def test_health_does_not_access_database(client):
    """Liveness works while database access is forbidden by pytest-django."""
    response = client.get("/health/")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_ready_hides_database_failure_details(client):
    """Database failures return a generic failure without leaking credentials."""
    with patch.object(testee.connection, "cursor", side_effect=DatabaseError("private details")):
        response = client.get("/ready/")
    assert response.status_code == 503
    assert response.json() == {"status": "unavailable"}
    assert b"private details" not in response.content


@pytest.mark.database
@pytest.mark.django_db
def test_ready_checks_real_postgresql(client):
    """Readiness succeeds against the disposable test PostgreSQL database."""
    assert testee.connection.vendor == "postgresql"
    assert testee.connection.settings_dict["NAME"] == "test_dog_finder"
    response = client.get("/ready/")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


@pytest.mark.parametrize("path", ["/", "/health/", "/ready/"])
def test_public_read_routes_reject_post(client, path):
    """Read-only routes reject mutations before touching their dependencies."""
    assert client.post(path).status_code == 405
