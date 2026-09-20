"""Configuration boundaries for safe deployment."""

import pytest
from django.core.exceptions import ImproperlyConfigured

import dog_finder.config as testee


@pytest.mark.parametrize("value", [None, "", "  "])
def test_required_rejects_missing_or_blank_values(value):
    """A missing credential fails closed without printing its contents."""
    env = {} if value is None else {"SETTING": value}
    with pytest.raises(ImproperlyConfigured, match="SETTING must be set"):
        testee.required(env, "SETTING")


def test_required_preserves_explicit_value():
    """Valid configuration is returned without silent modification."""
    assert testee.required({"SETTING": " value "}, "SETTING") == " value "


@pytest.mark.parametrize("value", ["", " , ", "*", "example.org,*"])
def test_production_hosts_rejects_empty_or_wildcard_hosts(value):
    """Production must not accept every Host header."""
    with pytest.raises(ImproperlyConfigured, match="explicit hostnames"):
        testee.production_hosts(value)


def test_production_hosts_accepts_explicit_hosts():
    """Configured hostnames survive trimming and empty separators."""
    assert testee.production_hosts("example.org, , www.example.org ") == [
        "example.org",
        "www.example.org",
    ]
