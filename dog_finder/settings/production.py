"""Fail-closed production settings; integrations and deployment are not enabled yet."""

import os

from dog_finder.config import production_hosts, required

from .base import *

SECRET_KEY = required(os.environ, "DJANGO_SECRET_KEY")
ALLOWED_HOSTS = production_hosts(required(os.environ, "ALLOWED_HOSTS"))
DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.postgresql",
        "NAME": required(os.environ, "DATABASE_NAME"),
        "USER": required(os.environ, "DATABASE_USER"),
        "PASSWORD": required(os.environ, "DATABASE_PASSWORD"),
        "HOST": required(os.environ, "DATABASE_HOST"),
        "PORT": os.environ.get("DATABASE_PORT", "5432"),
    }
}
SECURE_SSL_REDIRECT = True
SESSION_COOKIE_SECURE = True
CSRF_COOKIE_SECURE = True
SECURE_HSTS_SECONDS = 31536000
SECURE_HSTS_INCLUDE_SUBDOMAINS = True
SECURE_HSTS_PRELOAD = True
# The eventual reverse proxy must overwrite, rather than forward, this header.
SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")
