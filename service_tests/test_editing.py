"""Private editing, baseline revisions, and concurrent lifecycle protection."""

import uuid
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime, timedelta
from threading import Barrier

import pytest
from django.db import close_old_connections
from django.test import Client
from django.urls import reverse

import dog_finder.subscriptions.forms as form_testee
import dog_finder.subscriptions.services as testee
import dog_finder.subscriptions.tokens as token_testee
from dog_finder.subscriptions.models import Capacity, Postcode, Search, Subscriber

pytestmark = [pytest.mark.database, pytest.mark.django_db]
NOW = datetime(2026, 9, 21, tzinfo=UTC)


@pytest.fixture
def search():
    """Own a live search and postcode reference without sending email."""
    Capacity.objects.get_or_create(pk=1)
    Postcode.objects.create(code="2000", state="NSW")
    return Search.objects.create(
        subscriber=Subscriber.objects.create(email="editor@example.org"),
        name="Friend",
        description="Calm dog",
        postcode="2000",
        state="NSW",
        interstate=False,
        status="active",
        created_at=NOW,
        activated_at=NOW,
        expires_at=datetime.now(UTC) + timedelta(days=90),
        baseline_pending=False,
    )


def criteria(search, **changes):
    """Build canonical edit data including the version seen by the browser."""
    return {
        **{
            field: getattr(search, field)
            for field in ("name", "description", "postcode", "state", "interstate", "edit_version")
        },
        **changes,
    }


@pytest.mark.parametrize(
    "field,value",
    [
        ("description", "Large dog"),
        ("postcode", "2620"),
        ("state", "ACT"),
        ("interstate", True),
    ],
)
def test_matching_edit_advances_revision_and_resets_baseline(search, field, value):
    """Each matching criterion invalidates the old revision without changing the term."""
    expiry, version = search.expires_at, search.edit_version
    assert (
        testee.edit(search.pk, search.management_version, criteria(search, **{field: value}), NOW)
        == ""
    )
    search.refresh_from_db()
    assert getattr(search, field) == value
    assert search.criteria_revision == 2
    assert search.baseline_pending
    assert search.expires_at == expiry
    assert search.edit_version != version


@pytest.mark.parametrize("name", ["Friend", "Renamed"])
def test_rename_or_noop_preserves_baseline_and_matching_revision(search, name):
    """Non-matching saves cannot reset a ready baseline or change the owner."""
    data = criteria(search, name=name, email="intruder@example.org")
    assert not testee.edit(search.pk, search.management_version, data, NOW)
    search.refresh_from_db()
    assert search.name == name
    assert search.subscriber.email == "editor@example.org"
    assert search.criteria_revision == 1
    assert not search.baseline_pending


@pytest.mark.parametrize(
    "state", ["deleted", "cancelled", "pending", "expired", "suppressed", "revoked"]
)
def test_unavailable_search_cannot_be_changed(search, state):
    """Lifecycle and credential checks are repeated after obtaining the transaction lock."""
    identifier, credential, data = search.pk, search.management_version, criteria(search)
    if state == "deleted":
        search.delete()
    elif state == "suppressed":
        search.subscriber.suppressed = True
        search.subscriber.save()
    else:
        if state == "expired":
            search.expires_at = NOW
        elif state == "revoked":
            search.management_version = uuid.uuid4()
        else:
            search.status = state
        search.save()
    assert "cannot be edited" in testee.edit(identifier, credential, data, NOW)
    if state != "deleted":
        search.refresh_from_db()
        assert search.edit_version == data["edit_version"]
        assert search.criteria_revision == 1


def test_stale_form_does_not_overwrite_saved_changes(search):
    """A second tab or repeated submission cannot silently replace newer criteria."""
    old = criteria(search, name="Second")
    assert not testee.edit(
        search.pk, search.management_version, criteria(search, name="First"), NOW
    )
    assert "Reload" in testee.edit(search.pk, search.management_version, old, NOW)
    search.refresh_from_db()
    assert search.name == "First"


def test_edit_form_uses_creation_validation_without_email(search):
    """Editing validates and trims the same criteria while excluding the owner field."""
    data = criteria(search, interstate="no", description="  Calm dog  ")
    form = form_testee.EditSearchForm(data)
    assert form.is_valid(), form.errors
    assert form.cleaned_data["description"] == "Calm dog"
    assert "email" not in form.fields
    for change in ({"description": "x" * 301}, {"postcode": "0000"}, {"edit_version": "bad"}):
        assert not form_testee.EditSearchForm({**data, **change}).is_valid()


def test_browser_edit_is_scoped_protected_and_preserves_invalid_input(search):
    """Scanner GETs and forged POSTs cannot edit; valid changes return to management."""
    client = Client(enforce_csrf_checks=True)
    token = token_testee.issue(search, "management")
    url = reverse("search-edit", args=[token])
    response = client.get(url)
    assert response.status_code == 200
    assert b'name="email"' not in response.content
    assert b"no-store" in response.headers["Cache-Control"].encode()
    search.refresh_from_db()
    assert not search.baseline_pending
    data = criteria(search, interstate="yes", name="New name")
    assert client.post(url, data).status_code == 403
    data["csrfmiddlewaretoken"] = client.cookies["csrftoken"].value
    invalid = client.post(url, {**data, "description": "x" * 301})
    assert invalid.status_code == 200
    assert b"New name" in invalid.content
    result = client.post(url, data)
    assert result.url == reverse("search-manage", args=[token])
    search.refresh_from_db()
    assert search.interstate
    assert search.name == "New name"
    stale = client.post(url, data)
    assert b"Reload before editing" in stale.content
    assert client.get(reverse("search-edit", args=["bad"])).status_code == 410
    assert (
        client.get(
            reverse("search-edit", args=[token_testee.issue(search, "confirmation")])
        ).status_code
        == 410
    )


@pytest.mark.django_db(transaction=True)
@pytest.mark.parametrize("cancel", [False, True])
def test_concurrent_edits_and_cancellation_preserve_latest_state(search, cancel):
    """Only one competing edit wins, and cancellation always leaves criteria erased."""
    barrier = Barrier(2)

    def attempt(index):
        """Close each worker connection even after a failed attempt."""
        close_old_connections()
        try:
            barrier.wait(timeout=10)
            if cancel and index == 1:
                testee.cancel(search.pk, NOW)
                return "cancelled"
            return testee.edit(
                search.pk, search.management_version, criteria(search, name=str(index)), NOW
            )
        finally:
            close_old_connections()

    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(attempt, range(2)))
    search.refresh_from_db()
    if cancel:
        assert search.status == "cancelled"
        assert search.name == search.description == ""
    else:
        assert results.count("") == 1
        assert search.name in {"0", "1"}
