"""Run Django commands; default to local development settings."""

import os
import sys

from django.core.management import execute_from_command_line

if __name__ == "__main__":
    os.environ.setdefault("DJANGO_SETTINGS_MODULE", "dog_finder.settings.development")
    execute_from_command_line(sys.argv)
