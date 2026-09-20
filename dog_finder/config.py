"""Validate deployment configuration without reading local secret files."""

from collections.abc import Mapping

from django.core.exceptions import ImproperlyConfigured


def required(env: Mapping[str, str], name: str) -> str:
    """Return a required nonblank setting without exposing its value in errors."""
    value = env.get(name, "")
    if not value.strip():
        raise ImproperlyConfigured(f"{name} must be set")
    return value


def production_hosts(value: str) -> list[str]:
    """Require explicit production hosts rather than accepting a wildcard."""
    hosts = [host.strip() for host in value.split(",") if host.strip()]
    if not hosts or any("*" in host for host in hosts):
        raise ImproperlyConfigured("ALLOWED_HOSTS must contain explicit hostnames")
    return hosts
