"""Mailbox recovery boundaries, shared quotas, and address-wide scope."""

from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime, timedelta
from threading import Barrier
from unittest.mock import patch

import pytest
from django.core import signing
from django.core.exceptions import ImproperlyConfigured
from django.db import close_old_connections
from django.test import Client
from django.urls import reverse

import dog_finder.subscriptions.recovery as testee
import dog_finder.subscriptions.recovery_views as view_testee
import dog_finder.subscriptions.services as service_testee
import dog_finder.subscriptions.tokens as token_testee
from dog_finder.subscriptions.models import Capacity, Search, Subscriber

pytestmark = [pytest.mark.database, pytest.mark.django_db]
NOW = datetime(2026, 9, 21, tzinfo=UTC)


@pytest.fixture
def search():
    """Own one verified active search without real providers or personal data."""
    Capacity.objects.get_or_create(pk=1)
    return Search.objects.create(
        subscriber=Subscriber.objects.create(email="owner@example.org", verified_at=NOW),
        name="My dog",
        description="Calm dog",
        postcode="2000",
        state="NSW",
        interstate=False,
        created_at=NOW,
        status="active",
        expires_at=NOW + timedelta(days=90),
    )


def criteria(search):
    """Provide valid canonical creation input for testing shared service quotas."""
    return {
        "email": search.subscriber.email,
        **{
            k: getattr(search, k)
            for k in ("name", "description", "postcode", "state", "interstate")
        },
    }


def test_recovery_email_and_shared_address_limit(search, mailoutbox):
    """Two confirmations leave exactly one recovery slot; the next UTC day resets it."""
    for _ in range(2):
        service_testee.request_search(criteria(search), "source", NOW)
    testee.request_recovery("owner@EXAMPLE.ORG", "source", NOW)
    testee.request_recovery(search.subscriber.email, "another-source", NOW)
    assert len(mailoutbox) == 3
    assert "Open this link" in mailoutbox[-1].body
    assert "/s/recover/" in mailoutbox[-1].body
    testee.request_recovery(search.subscriber.email, "source", NOW + timedelta(days=1))
    assert len(mailoutbox) == 4


def test_recovery_reserves_creation_email_and_source_limits(search, settings, mailoutbox):
    """Recovery consumes the same source and email budgets as new confirmations."""
    settings.REQUEST_SOURCE_DAILY_LIMIT = 1
    testee.request_recovery(search.subscriber.email, "source", NOW)
    testee.request_recovery(search.subscriber.email, "source", NOW)
    assert service_testee.request_search(criteria(search), "source", NOW) is None
    for source in ("two", "three"):
        testee.request_recovery(search.subscriber.email, source, NOW)
    assert service_testee.request_search(criteria(search), "four", NOW) is None
    assert len(mailoutbox) == 3


@pytest.mark.parametrize("state", ["unknown", "suppressed", "pending", "cancelled", "expired"])
def test_unrecoverable_address_sends_nothing(search, state, mailoutbox):
    """Only an address with an activated search inside grace receives recovery mail."""
    email = search.subscriber.email
    if state == "unknown":
        email = "missing@example.org"
    elif state == "suppressed":
        search.subscriber.suppressed = True
        search.subscriber.save()
    else:
        if state == "expired":
            search.expires_at = NOW - timedelta(days=30)
        else:
            search.status = state
        search.save()
    testee.request_recovery(email, "source", NOW)
    assert not mailoutbox
    assert Subscriber.objects.count() == 1


def test_recovery_refuses_live_provider(search, settings):
    """No SMTP configuration can turn the preview into real recovery delivery."""
    settings.EMAIL_BACKEND = "django.core.mail.backends.smtp.EmailBackend"
    with pytest.raises(ImproperlyConfigured, match="local email capture"):
        testee.request_recovery(search.subscriber.email, "source", NOW)


@pytest.mark.parametrize("payload", [{}, [], {"id": "bad", "version": "bad"}])
def test_malformed_subscriber_credentials_do_not_crash(payload):
    """Invalid signed structures cannot expose an address or crash resolution."""
    assert testee.resolve(signing.dumps(payload, salt="subscriber.address"), "address") is None


def test_recovery_expires_is_single_use_and_separate_from_management(search):
    """Recovery grants address access only through one successful consumption."""
    subscriber = search.subscriber
    token = testee.issue(subscriber, "recovery")
    assert testee.resolve(token, "address") is None
    assert token_testee.resolve(token, "management") is None
    assert testee.resolve(token_testee.issue(search, "management"), "address") is None
    assert testee.consume(token).pk == subscriber.pk
    assert testee.consume(token) is None
    subscriber.refresh_from_db()
    with patch.object(testee.signing.time, "time", return_value=1):
        expired = testee.issue(subscriber, "recovery")
    assert testee.resolve(expired, "recovery") is None
    subscriber.refresh_from_db()
    address = testee.issue(subscriber, "address")
    assert testee.resolve(address, "address").pk == subscriber.pk
    subscriber.delete()
    assert testee.resolve(address, "address") is None


def test_single_search_cannot_open_address_dashboard_and_empty_dashboard_is_safe(search, client):
    """Search-scoped access cannot escalate; an emptied address page discloses no old criteria."""
    single = token_testee.issue(search, "management")
    assert client.get(reverse("address-manage", args=[single])).status_code == 410
    address = testee.issue(search.subscriber, "address")
    service_testee.cancel(search.pk, NOW)
    page = client.get(reverse("address-manage", args=[address]))
    assert b"No active searches" in page.content
    assert b"Calm dog" not in page.content


def test_generic_request_form_closed_mode_and_csrf(search, mailoutbox, settings):
    """Public recovery never distinguishes absent, existing, or suppressed addresses."""
    client = Client(enforce_csrf_checks=True)
    url = reverse("recovery-request")
    assert client.get(url).status_code == 200
    assert client.post(url, {"email": search.subscriber.email}).status_code == 403
    csrf = {"csrfmiddlewaretoken": client.cookies["csrftoken"].value}
    assert b"Enter a valid email" in client.post(url, {**csrf, "email": "bad"}).content
    responses = []
    for email in (search.subscriber.email, "absent@example.org"):
        responses.append(client.post(url, {**csrf, "email": email}).url)
    search.subscriber.suppressed = True
    search.subscriber.save()
    responses.append(client.post(url, {**csrf, "email": search.subscriber.email}).url)
    assert len(set(responses)) == 1
    assert b"If recovery is available" in client.get(responses[0]).content
    assert len(mailoutbox) == 1
    settings.SEARCH_REGISTRATION_ENABLED = False
    assert client.get(url).status_code == 503
    assert client.post(url, csrf).status_code == 503


def test_recovery_browser_and_address_scope(search, mailoutbox):
    """Scanner-safe recovery opens only this address's active and grace searches."""
    for name, status, expiry in (
        ("Grace dog", "active", NOW),
        ("Unconfirmed dog", "pending", None),
        ("Cancelled dog", "cancelled", NOW),
        ("Old dog", "active", NOW - timedelta(days=30)),
    ):
        Search.objects.create(
            subscriber=search.subscriber,
            name=name,
            description="Dog",
            postcode="2000",
            state="NSW",
            interstate=False,
            created_at=NOW,
            status=status,
            expires_at=expiry,
        )
    Search.objects.create(
        subscriber=Subscriber.objects.create(email="other@example.org"),
        name="Other address",
        description="Dog",
        postcode="2000",
        state="NSW",
        interstate=False,
        created_at=NOW,
        status="active",
        expires_at=NOW + timedelta(days=90),
    )
    testee.request_recovery(search.subscriber.email, "source", NOW)
    assert "Grace dog" in mailoutbox[0].body
    assert "/s/renew/" in mailoutbox[0].body
    assert "Old dog" not in mailoutbox[0].body
    client = Client(enforce_csrf_checks=True)
    token = testee.issue(search.subscriber, "recovery")
    url = reverse("recovery-confirm", args=[token])
    assert client.get(url).status_code == 200
    assert testee.resolve(token, "recovery")
    assert client.post(url).status_code == 403
    result = client.post(url, {"csrfmiddlewaretoken": client.cookies["csrftoken"].value})
    assert result.status_code == 302
    assert client.get(url).status_code == 410
    with patch.object(view_testee.timezone, "now", return_value=NOW):
        page = client.get(result.url)
    assert b"My dog" in page.content and b"Grace dog" in page.content
    for hidden in (
        b"Unconfirmed dog",
        b"Cancelled dog",
        b"Old dog",
        b"Other address",
        b"owner@example.org",
    ):
        assert hidden not in page.content
    assert "no-store" in page.headers["Cache-Control"]
    assert page.headers["Referrer-Policy"] == "no-referrer"
    assert not page.cookies
    search.subscriber.suppressed = True
    search.subscriber.save()
    assert client.get(result.url).status_code == 410


@pytest.mark.django_db(transaction=True)
@pytest.mark.parametrize("operation", ["consume", "send"])
def test_parallel_recovery_is_single_use_and_rate_limited(search, mailoutbox, operation):
    """The capacity lock serializes recovery consumption and mixed email reservations."""
    token = testee.issue(search.subscriber, "recovery")
    barrier = Barrier(4)

    def attempt(index):
        """Close each owned worker connection after the bounded transition."""
        close_old_connections()
        try:
            barrier.wait(timeout=10)
            if operation == "consume":
                return testee.consume(token)
            if index % 2:
                return service_testee.request_search(criteria(search), str(index), NOW)
            return testee.request_recovery(search.subscriber.email, str(index), NOW)
        finally:
            close_old_connections()

    with ThreadPoolExecutor(max_workers=4) as pool:
        results = list(pool.map(attempt, range(4)))
    if operation == "consume":
        assert sum(result is not None for result in results) == 1
    else:
        assert len(mailoutbox) == 3
        search.subscriber.refresh_from_db()
        assert search.subscriber.email_count == 3
