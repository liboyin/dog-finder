"""Test-owned PostgreSQL configuration, independent of development credentials."""

import os

from .base import *

SECRET_KEY = "test-only-not-for-deployment"
SEARCH_REGISTRATION_ENABLED = True
ALLOWED_HOSTS = ["testserver", "localhost"]
PASSWORD_HASHERS = ["django.contrib.auth.hashers.MD5PasswordHasher"]
DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.postgresql",
        "NAME": "dog_finder_test_control",
        "USER": os.environ.get("TEST_DATABASE_USER", "dog_finder_test"),
        "PASSWORD": os.environ.get("TEST_DATABASE_PASSWORD", "local-test-only"),
        "HOST": os.environ.get("TEST_DATABASE_HOST", "127.0.0.1"),
        "PORT": os.environ.get("TEST_DATABASE_PORT", "55433"),
        "TEST": {"NAME": "test_dog_finder"},
    }
}
