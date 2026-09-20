"""Renewal boundaries, scanner safety, and shared admission invariants."""

import uuid
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime, timedelta
from threading import Barrier
from unittest.mock import patch

import pytest
from django.db import close_old_connections
from django.test import Client
from django.urls import reverse

import dog_finder.subscriptions.services as testee
import dog_finder.subscriptions.tokens as token_testee
import dog_finder.subscriptions.views as view_testee
from dog_finder.subscriptions.models import Capacity, Search, Subscriber

pytestmark = [pytest.mark.database, pytest.mark.django_db]
NOW = datetime(2026, 9, 21, tzinfo=UTC)


@pytest.fixture
def search():
    """Own an activated search with a ready baseline and stable test clock."""
    Capacity.objects.get_or_create(pk=1)
    return Search.objects.create(
        subscriber=Subscriber.objects.create(email="renew@example.org"),
        name="Friend",
        description="Calm dog",
        postcode="2000",
        state="NSW",
        interstate=False,
        status="active",
        created_at=NOW - timedelta(days=90),
        activated_at=NOW - timedelta(days=90),
        expires_at=NOW + timedelta(days=7),
        baseline_pending=False,
    )


@pytest.mark.parametrize("days", [7, 100])
def test_active_renewal_preserves_baseline_and_never_stacks_terms(search, days, settings):
    """Renewal uses max(existing, now plus term) without another quota slot."""
    search.expires_at = NOW + timedelta(days=days)
    search.save()
    settings.ACTIVE_SEARCH_LIMIT = settings.ACTIVE_SUBSCRIBER_LIMIT = 1
    version = search.edit_version
    for _ in range(3):
        assert not testee.renew(search.pk, search.management_version, NOW)
    search.refresh_from_db()
    assert search.expires_at == NOW + timedelta(days=max(days, 90))
    assert search.criteria_revision == 1
    assert not search.baseline_pending
    assert search.edit_version == version


@pytest.mark.parametrize("elapsed", [timedelta(0), timedelta(days=30, microseconds=-1)])
def test_grace_renewal_resets_baseline_once_and_preserves_identity(search, elapsed):
    """The expiry instant and last grace instant can renew without replaying old work."""
    search.expires_at = NOW - elapsed
    search.save()
    version = search.edit_version
    original_activation = search.activated_at
    assert not testee.renew(search.pk, search.management_version, NOW)
    assert not testee.renew(search.pk, search.management_version, NOW)
    search.refresh_from_db()
    assert search.expires_at == NOW + timedelta(days=90)
    assert search.criteria_revision == 2
    assert search.baseline_pending
    assert search.edit_version != version
    assert search.activated_at == original_activation
    assert search.description == "Calm dog"
    assert Search.objects.count() == 1


@pytest.mark.parametrize(
    "state",
    ["deleted", "cancelled", "pending", "missing_expiry", "deadline", "suppressed", "revoked"],
)
def test_unavailable_renewal_does_not_change_state(search, state):
    """No private link can revive cancelled, unverified, suppressed, or fully expired data."""
    identifier, credential = search.pk, search.management_version
    if state == "deleted":
        search.delete()
    elif state == "suppressed":
        search.subscriber.suppressed = True
        search.subscriber.save()
    else:
        if state == "deadline":
            search.expires_at = NOW - timedelta(days=30)
        elif state == "missing_expiry":
            search.expires_at = None
        elif state == "revoked":
            search.management_version = uuid.uuid4()
        else:
            search.status = state
        search.save()
    assert "cannot be renewed" in testee.renew(identifier, credential, NOW)
    if state != "deleted":
        expected = search.expires_at
        search.refresh_from_db()
        assert search.expires_at == expected
        assert search.criteria_revision == 1


@pytest.mark.parametrize("same_address", [False, True])
def test_grace_renewal_requires_capacity_and_can_retry(search, settings, same_address):
    """Full subscriber or search capacity leaves the expired search unchanged until freed."""
    search.expires_at = NOW
    search.save()
    settings.ACTIVE_SEARCH_LIMIT = settings.ACTIVE_SUBSCRIBER_LIMIT = 1
    peer = Search.objects.create(
        subscriber=search.subscriber
        if same_address
        else Subscriber.objects.create(email="peer@example.org"),
        name="Peer",
        description="Calm",
        postcode="2000",
        state="NSW",
        interstate=False,
        status="active",
        created_at=NOW,
        expires_at=NOW + timedelta(days=10),
    )
    assert testee.renew(search.pk, search.management_version, NOW)
    search.refresh_from_db()
    assert search.expires_at == NOW
    assert search.criteria_revision == 1
    testee.cancel(peer.pk, NOW)
    assert not testee.renew(search.pk, search.management_version, NOW)


def test_existing_subscriber_can_resume_at_site_cap(search, settings):
    """A grace search only consumes a search slot when its address is already active."""
    search.expires_at = NOW
    search.save()
    Search.objects.create(
        subscriber=search.subscriber,
        name="Peer",
        description="Calm",
        postcode="2000",
        state="NSW",
        interstate=False,
        status="active",
        created_at=NOW,
        expires_at=NOW + timedelta(days=10),
    )
    settings.ACTIVE_SUBSCRIBER_LIMIT = 1
    assert not testee.renew(search.pk, search.management_version, NOW)


def test_browser_renewal_requires_protected_post_and_shows_expiry(search, settings):
    """Management explains expiry; scanners do not renew, and failures stay on the page."""
    search.expires_at = NOW
    search.save()
    client = Client(enforce_csrf_checks=True)
    token = token_testee.issue(search, "management")
    url = reverse("search-renew", args=[token])
    management = reverse("search-manage", args=[token])
    with patch.object(view_testee.timezone, "now", return_value=NOW):
        page = client.get(management)
        assert b"has expired" in page.content
        assert b"Keep searching" in page.content
        assert client.get(url).status_code == 200
        search.refresh_from_db()
        assert search.expires_at == NOW
        assert client.post(url).status_code == 403
        data = {"csrfmiddlewaretoken": client.cookies["csrftoken"].value}
        settings.ACTIVE_SUBSCRIBER_LIMIT = 0
        denied = client.post(url, data)
        assert denied.status_code == 200
        assert b"at capacity" in denied.content
        settings.ACTIVE_SUBSCRIBER_LIMIT = 250
        assert client.post(url, data).url == management
        assert b"has expired" not in client.get(management).content
        testee.cancel(search.pk, NOW)
        assert b"unavailable for renewal" in client.get(url).content
        assert b"cannot be renewed" in client.post(url, data).content
        assert b"Keep searching" not in client.get(management).content
    assert client.get(reverse("search-renew", args=["bad"])).status_code == 410
    assert (
        client.get(
            reverse("search-renew", args=[token_testee.issue(search, "confirmation")])
        ).status_code
        == 410
    )


@pytest.mark.django_db(transaction=True)
@pytest.mark.parametrize("competitor", ["activation", "renewal", "repeat", "cancel"])
@pytest.mark.parametrize("same_address", [False, True])
def test_renewal_races_share_capacity_and_cancellation_lock(
    search, settings, competitor, same_address
):
    """Competing transitions cannot overbook or revive a concurrently cancelled search."""
    settings.ACTIVE_SEARCH_LIMIT = settings.ACTIVE_SUBSCRIBER_LIMIT = 1
    search.expires_at = NOW
    search.save()
    peer = Search.objects.create(
        subscriber=search.subscriber
        if same_address
        else Subscriber.objects.create(email="peer@example.org"),
        name="Peer",
        description="Calm",
        postcode="2000",
        state="NSW",
        interstate=False,
        status="pending" if competitor == "activation" else "active",
        created_at=NOW,
        expires_at=NOW,
    )
    barrier = Barrier(2)

    def attempt(index):
        """Own the thread connection and wait only for the paired test transition."""
        close_old_connections()
        try:
            barrier.wait(timeout=10)
            if index == 0:
                return testee.renew(search.pk, search.management_version, NOW)
            if competitor == "activation":
                return testee.activate(peer.pk, peer.confirmation_version, NOW)[1]
            if competitor == "renewal":
                return testee.renew(peer.pk, peer.management_version, NOW)
            if competitor == "repeat":
                return testee.renew(search.pk, search.management_version, NOW)
            testee.cancel(search.pk, NOW)
            return "cancelled"
        finally:
            close_old_connections()

    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(attempt, range(2)))
    if competitor == "cancel":
        search.refresh_from_db()
        assert search.status == "cancelled"
        assert search.description == ""
    elif competitor == "repeat":
        assert results == ["", ""]
        search.refresh_from_db()
        assert search.criteria_revision == 2
        assert search.expires_at == NOW + timedelta(days=90)
    else:
        assert results.count("") == 1
        assert testee.active(NOW).count() == 1


def test_management_at_grace_deadline_offers_no_renewal(search, client):
    """The page cannot advertise renewal after the same boundary enforced by the service."""
    search.expires_at = NOW - timedelta(days=30)
    search.save()
    token = token_testee.issue(search, "management")
    with patch.object(view_testee.timezone, "now", return_value=NOW):
        page = client.get(reverse("search-manage", args=[token]))
    assert b"renewal period has ended" in page.content
    assert b"Keep searching" not in page.content
    assert b"Edit search" not in page.content
