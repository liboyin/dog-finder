"""Production WSGI entry point; requires explicit production configuration."""

import os

from django.core.wsgi import get_wsgi_application

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "dog_finder.settings.production")
application = get_wsgi_application()
