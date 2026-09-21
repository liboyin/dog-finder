"""Cancellation-only native unsubscribe credentials and machine requests."""

import uuid
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime, timedelta
from threading import Barrier

import pytest
from django.core.files.uploadedfile import SimpleUploadedFile
from django.db import close_old_connections
from django.test import Client
from django.urls import reverse

import dog_finder.subscriptions.services as testee
import dog_finder.subscriptions.tokens as token_testee
from dog_finder.subscriptions.models import Capacity, Search, Subscriber

pytestmark = [pytest.mark.database, pytest.mark.django_db]
NOW = datetime(2026, 9, 21, tzinfo=UTC)
PAYLOAD = {"List-Unsubscribe": "One-Click"}


@pytest.fixture
def search():
    """Own a live search without contacting any email provider."""
    Capacity.objects.get_or_create(pk=1)
    return Search.objects.create(
        subscriber=Subscriber.objects.create(email="unsubscribe@example.org"),
        name="Friend",
        description="Calm dog",
        postcode="2000",
        state="NSW",
        interstate=False,
        status="active",
        created_at=NOW,
        expires_at=NOW + timedelta(days=90),
    )


def url(search, purpose="unsubscribe"):
    """Generate a fresh test-only credential rather than embedding real private links."""
    return reverse("search-unsubscribe", args=[token_testee.issue(search, purpose)])


@pytest.mark.parametrize("multipart", [False, True])
def test_native_post_cancels_without_session_or_csrf(search, multipart):
    """Both RFC encodings cancel without redirects, cookies, or exposing criteria."""
    client = Client(enforce_csrf_checks=True)
    if multipart:
        response = client.post(url(search), PAYLOAD)
    else:
        response = client.post(
            url(search),
            "List-Unsubscribe=One-Click",
            content_type="application/x-www-form-urlencoded",
        )
    assert response.status_code == 204
    assert not response.content
    assert not response.cookies
    assert "Location" not in response.headers
    assert "no-store" in response.headers["Cache-Control"]
    search.refresh_from_db()
    assert search.status == "cancelled"
    assert search.description == search.name == search.postcode == search.state == ""


@pytest.mark.parametrize("method", ["get", "head", "put", "delete", "options"])
def test_scanners_and_other_methods_cannot_cancel(search, method):
    """Only the protocol's explicit POST may mutate the subscription."""
    response = getattr(Client(enforce_csrf_checks=True), method)(url(search))
    assert response.status_code == 405
    assert "no-store" in response.headers["Cache-Control"]
    search.refresh_from_db()
    assert search.status == "active"


@pytest.mark.parametrize(
    "data",
    [
        {},
        {"List-Unsubscribe": "wrong"},
        {"List-Unsubscribe": ["One-Click", "One-Click"]},
        {**PAYLOAD, "extra": "ignored"},
    ],
)
def test_malformed_form_cannot_cancel(search, data):
    """Missing, duplicated, unexpected, or incorrect fields fail without mutation."""
    assert Client(enforce_csrf_checks=True).post(url(search), data).status_code == 400
    search.refresh_from_db()
    assert search.status == "active"


def test_nonform_payload_and_upload_cannot_cancel(search):
    """The machine endpoint rejects JSON and file attachments."""
    client = Client(enforce_csrf_checks=True)
    assert client.post(url(search), PAYLOAD, content_type="application/json").status_code == 400
    assert (
        client.post(
            url(search), {**PAYLOAD, "file": SimpleUploadedFile("test.txt", b"test")}
        ).status_code
        == 400
    )
    search.refresh_from_db()
    assert search.status == "active"


@pytest.mark.parametrize("purpose", ["confirmation", "management"])
def test_other_credentials_cannot_native_unsubscribe(search, purpose):
    """An unrelated credential receives a generic acknowledgement but cannot cancel."""
    assert Client(enforce_csrf_checks=True).post(url(search, purpose), PAYLOAD).status_code == 204
    search.refresh_from_db()
    assert search.status == "active"


@pytest.mark.parametrize(
    "route", ["search-manage", "search-edit", "search-renew", "search-cancel", "search-confirm"]
)
def test_unsubscribe_token_never_grants_management_access(search, client, route):
    """Cancellation-only authority cannot read criteria or use browser mutations."""
    path = reverse(route, args=[token_testee.issue(search, "unsubscribe")])
    assert client.get(path).status_code == 410
    assert client.post(path).status_code == (405 if route == "search-manage" else 410)
    search.refresh_from_db()
    assert search.status == "active"


def test_retries_deleted_revoked_and_invalid_credentials_are_safe(search, client):
    """Retries preserve cancellation time; invalid or deleted records need no retry."""
    stale = token_testee.issue(search, "unsubscribe")
    search.unsubscribe_version = uuid.uuid4()
    search.save()
    testee.unsubscribe(stale, NOW)
    search.refresh_from_db()
    assert search.status == "active"
    token = token_testee.issue(search, "unsubscribe")
    testee.unsubscribe(token, NOW)
    testee.unsubscribe(token, NOW + timedelta(days=1))
    search.refresh_from_db()
    assert search.cancelled_at == NOW
    assert not search.subscriber.suppressed
    search.delete()
    for invalid in (token, "invalid", token + "tampered"):
        assert (
            client.post(reverse("search-unsubscribe", args=[invalid]), PAYLOAD).status_code == 204
        )


def test_one_search_unsubscribe_leaves_other_searches_untouched(search):
    """Neither address-wide suppression nor sibling cancellation is implied."""
    sibling = Search.objects.create(
        subscriber=search.subscriber,
        name="Other",
        description="Large dog",
        postcode="2000",
        state="NSW",
        interstate=False,
        status="active",
        created_at=NOW,
        expires_at=NOW + timedelta(days=90),
    )
    testee.unsubscribe(token_testee.issue(search, "unsubscribe"), NOW)
    sibling.refresh_from_db()
    assert sibling.status == "active"
    assert sibling.description == "Large dog"


@pytest.mark.django_db(transaction=True)
def test_parallel_unsubscribe_and_renewal_cannot_revive_cancelled_search(search):
    """The native path participates in the same lifecycle lock as browser renewal."""
    token = token_testee.issue(search, "unsubscribe")
    barrier = Barrier(3)

    def attempt(index):
        """Close each worker connection even if a transition fails."""
        close_old_connections()
        try:
            barrier.wait(timeout=10)
            if index == 0:
                testee.renew(search.pk, search.management_version, NOW)
            else:
                testee.unsubscribe(token, NOW)
        finally:
            close_old_connections()

    with ThreadPoolExecutor(max_workers=3) as pool:
        list(pool.map(attempt, range(3)))
    search.refresh_from_db()
    assert search.status == "cancelled"
    assert search.description == ""
    assert search.cancelled_at == NOW
