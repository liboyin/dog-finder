"""Shared settings with no provider credentials or live email backend."""

from pathlib import Path

BASE_DIR = Path(__file__).resolve().parents[2]
DEBUG = False
INSTALLED_APPS = [
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.staticfiles",
]
MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
]
ROOT_URLCONF = "dog_finder.urls"
WSGI_APPLICATION = "dog_finder.wsgi.application"
TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [BASE_DIR / "dog_finder" / "templates"],
        "APP_DIRS": True,
        "OPTIONS": {"context_processors": ["django.template.context_processors.request"]},
    }
]
LANGUAGE_CODE = "en-au"
TIME_ZONE = "Australia/Sydney"
USE_TZ = True
DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"
STATIC_URL = "/static/"
STATIC_ROOT = BASE_DIR / "staticfiles"
EMAIL_BACKEND = "django.core.mail.backends.locmem.EmailBackend"
SECURE_REFERRER_POLICY = "no-referrer"
SESSION_COOKIE_HTTPONLY = True
X_FRAME_OPTIONS = "DENY"
