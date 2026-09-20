"""Require explicit test-owned database configuration before database setup."""

import pytest
from django.conf import settings


@pytest.fixture(scope="session", autouse=True)
def enforce_test_database_boundary():
    """Refuse development/production settings before any database tests run."""
    database = settings.DATABASES["default"]
    if (
        settings.SETTINGS_MODULE != "dog_finder.settings.test"
        or database["NAME"] != "dog_finder_test_control"
        or database["TEST"]["NAME"] != "test_dog_finder"
    ):
        pytest.fail("Tests require dog_finder.settings.test and disposable test databases")


@pytest.fixture(scope="session")
def django_db_setup(enforce_test_database_boundary, django_db_setup):
    """Validate ownership before pytest-django can create or destroy a database."""
    return django_db_setup
