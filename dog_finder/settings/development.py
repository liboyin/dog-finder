"""Loopback-only defaults for local development; never import production secrets."""

import os

from .base import *

DEBUG = True
SEARCH_REGISTRATION_ENABLED = True
SECRET_KEY = "development-only-not-for-deployment"
ALLOWED_HOSTS = ["localhost", "127.0.0.1", "[::1]"]
DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.postgresql",
        "NAME": os.environ.get("DATABASE_NAME", "dog_finder_dev"),
        "USER": os.environ.get("DATABASE_USER", "dog_finder_dev"),
        "PASSWORD": os.environ.get("DATABASE_PASSWORD", "local-development-only"),
        "HOST": os.environ.get("DATABASE_HOST", "127.0.0.1"),
        "PORT": os.environ.get("DATABASE_PORT", "55432"),
    }
}
