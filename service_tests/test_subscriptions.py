"""PostgreSQL-backed subscriber lifecycle, privacy, and input validation."""

import io
import logging
import uuid
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime, timedelta
from threading import Barrier
from unittest.mock import patch
from zipfile import ZipFile

import pytest
from django.core import signing
from django.core.exceptions import ImproperlyConfigured
from django.core.management import call_command
from django.core.management.base import CommandError
from django.db import close_old_connections
from django.test import Client, RequestFactory
from django.urls import reverse

import dog_finder.subscriptions.forms as forms
import dog_finder.subscriptions.privacy as privacy
import dog_finder.subscriptions.services as testee
import dog_finder.subscriptions.tokens as tokens
from dog_finder.subscriptions.models import Capacity, Postcode, RequestSource, Search, Subscriber

pytestmark = [pytest.mark.database, pytest.mark.django_db]
NOW = datetime(2026, 9, 21, 4, tzinfo=UTC)


@pytest.fixture
def criteria():
    """Provide test-owned known postcodes and valid canonical criteria."""
    Capacity.objects.get_or_create(pk=1)
    Postcode.objects.bulk_create(
        [
            Postcode(code="2000", state="NSW"),
            Postcode(code="2620", state="NSW"),
            Postcode(code="2620", state="ACT"),
        ]
    )
    return dict(
        email="owner@example.org",
        postcode="2000",
        state="NSW",
        interstate=False,
        name="Small friend",
        description="A calm small dog for a home with a cat",
    )


def pending(criteria, email="owner@example.org", created_at=NOW):
    """Create a pending fixture without spending confirmation rate limits."""
    subscriber, _ = Subscriber.objects.get_or_create(email=email)
    return Search.objects.create(
        subscriber=subscriber,
        created_at=created_at,
        **{k: v for k, v in criteria.items() if k != "email"},
    )


def posted(criteria):
    """Translate canonical booleans to the public form's explicit yes/no choice."""
    return {**criteria, "interstate": "no"}


@pytest.mark.parametrize(
    "overrides,field",
    [
        ({"email": "not-an-email"}, "email"),
        ({"postcode": "0000"}, "postcode"),
        ({"postcode": "abc"}, "postcode"),
        ({"state": "VIC"}, "state"),
        ({"postcode": "2620", "state": ""}, "state"),
        ({"interstate": ""}, "interstate"),
        ({"name": "  "}, "name"),
        ({"name": "friend\nInjected header"}, "name"),
        ({"description": "  "}, "description"),
        ({"description": "x" * 301}, "description"),
    ],
)
def test_form_rejects_invalid_input(criteria, overrides, field):
    """Missing, conflicting, and overlong criteria cannot create a search."""
    form = forms.SearchForm({**posted(criteria), **overrides})
    assert not form.is_valid()
    assert field in form.errors


@pytest.mark.parametrize("postcode,state,expected", [("2000", "", "NSW"), ("2620", "ACT", "ACT")])
def test_form_trims_and_resolves_known_postcodes(criteria, postcode, state, expected):
    """A valid postcode resolves uniquely or respects the explicit state selection."""
    form = forms.SearchForm(
        {
            **posted(criteria),
            "postcode": postcode,
            "state": state,
            "description": "  " + "x" * 300 + "  ",
        }
    )
    assert form.is_valid(), form.errors
    assert form.cleaned_data["state"] == expected
    assert form.cleaned_data["description"] == "x" * 300
    assert form.cleaned_data["interstate"] is False


def test_request_captures_one_email_without_activating(criteria, mailoutbox):
    """A submitted search remains pending until its owner confirms it."""
    search = testee.request_search(criteria, "192.0.2.1", NOW)
    assert search.status == "pending"
    assert search.expires_at is None
    assert len(mailoutbox) == 1
    assert mailoutbox[0].to == [criteria["email"]]
    assert criteria["description"] in mailoutbox[0].body
    assert "192.0.2.1" not in RequestSource.objects.get().key


def test_requests_obey_daily_address_limits_and_reset(criteria, mailoutbox):
    """Only three emails are captured per address per UTC day, even across sources."""
    for index in range(3):
        assert testee.request_search(criteria, str(index), NOW)
    assert testee.request_search(criteria, "another-source", NOW) is None
    assert len(mailoutbox) == 3
    assert testee.request_search(criteria, "0", NOW + timedelta(days=1))
    assert len(mailoutbox) == 4


def test_source_and_pending_limits(criteria, settings):
    """One source or a full pending queue cannot create unbounded new searches."""
    settings.REQUEST_SOURCE_DAILY_LIMIT = 1
    assert testee.request_search(criteria, "source", NOW)
    assert testee.request_search({**criteria, "email": "other@example.org"}, "source", NOW) is None
    settings.PENDING_SEARCH_LIMIT = 1
    assert testee.request_search(criteria, "different-source", NOW) is None


def test_suppression_and_site_capacity_prevent_confirmation(criteria, settings, mailoutbox):
    """Blocked addresses and new subscribers at capacity receive no email."""
    Subscriber.objects.create(email=criteria["email"], suppressed=True)
    assert testee.request_search(criteria, "source", NOW) is None
    settings.ACTIVE_SUBSCRIBER_LIMIT = 0
    assert testee.request_search({**criteria, "email": "new@example.org"}, "source", NOW) is None
    assert not mailoutbox


def test_existing_subscriber_can_request_at_site_capacity(criteria, settings):
    """A full subscriber population does not block an existing subscriber's extra search."""
    search = pending(criteria)
    testee.activate(search.pk, search.confirmation_version, NOW)
    settings.ACTIVE_SUBSCRIBER_LIMIT = 1
    assert testee.request_search(criteria, "source", NOW)


def test_live_email_backend_is_refused(criteria, settings):
    """The preview cannot accidentally turn a configured SMTP backend into live delivery."""
    settings.EMAIL_BACKEND = "django.core.mail.backends.smtp.EmailBackend"
    with pytest.raises(ImproperlyConfigured, match="local email capture"):
        testee.request_search(criteria, "source", NOW)
    assert not Search.objects.exists()


def test_confirmation_is_scoped_expiring_and_single_use(criteria):
    """Activation rotates the confirmation credential and starts exactly one 90-day term."""
    search = pending(criteria)
    token = tokens.issue(search, "confirmation")
    assert tokens.resolve(token, "confirmation").pk == search.pk
    assert tokens.resolve(token, "management") is None
    active, error = testee.activate(search.pk, search.confirmation_version, NOW)
    assert not error
    assert active.expires_at == NOW + timedelta(days=90)
    assert active.baseline_pending
    assert tokens.resolve(token, "confirmation") is None
    assert testee.activate(search.pk, search.confirmation_version, NOW)[1]
    assert Search.objects.count() == 1


@pytest.mark.parametrize("change", ["expired", "suppressed", "revoked"])
def test_activation_rejects_invalid_state(criteria, change):
    """Expired, revoked, and suppressed confirmations cannot activate."""
    search = pending(criteria)
    version = search.confirmation_version
    if change == "expired":
        search.created_at = NOW - timedelta(days=7)
        search.save()
    elif change == "suppressed":
        search.subscriber.suppressed = True
        search.subscriber.save()
    else:
        version = uuid.uuid4()
    assert testee.activate(search.pk, version, NOW)[1]
    search.refresh_from_db()
    assert search.status == "pending"


def test_search_quota_and_expired_slot_reuse(criteria, settings):
    """Expired and cancelled searches do not consume active-search slots."""
    settings.ACTIVE_SEARCH_LIMIT = 1
    first = pending(criteria)
    testee.activate(first.pk, first.confirmation_version, NOW)
    second = pending(criteria)
    assert "five active" in testee.activate(second.pk, second.confirmation_version, NOW)[1]
    Search.objects.filter(pk=first.pk).update(expires_at=NOW)
    assert not testee.activate(second.pk, second.confirmation_version, NOW)[1]
    testee.cancel(second.pk, NOW)
    third = pending(criteria)
    assert not testee.activate(third.pk, third.confirmation_version, NOW)[1]


def test_site_quota_releases_after_cancellation(criteria, settings):
    """Cancellation of the last active search releases subscriber capacity."""
    settings.ACTIVE_SUBSCRIBER_LIMIT = 1
    first = pending(criteria)
    testee.activate(first.pk, first.confirmation_version, NOW)
    second = pending(criteria, email="other@example.org")
    assert "at capacity" in testee.activate(second.pk, second.confirmation_version, NOW)[1]
    testee.cancel(first.pk, NOW)
    assert not testee.activate(second.pk, second.confirmation_version, NOW)[1]


def test_cancel_is_idempotent_and_erases_criteria(criteria):
    """Repeated cancellation retains only the lifecycle record and private access."""
    search = pending(criteria)
    testee.activate(search.pk, search.confirmation_version, NOW)
    token = tokens.issue(search, "management")
    testee.cancel(search.pk, NOW)
    testee.cancel(search.pk, NOW)
    search.refresh_from_db()
    assert search.status == "cancelled"
    assert (search.name, search.description, search.postcode, search.state) == ("", "", "", "")
    assert tokens.resolve(token, "management").pk == search.pk


def test_housekeeping_between_link_resolution_and_post_is_safe(criteria):
    """A search deleted by housekeeping cannot turn a button press into a server error."""
    search = pending(criteria)
    identifier, version = search.pk, search.confirmation_version
    search.delete()
    assert testee.activate(identifier, version, NOW)[1]
    assert testee.cancel(identifier, NOW) is None


@pytest.mark.parametrize("payload", [{}, [], {"id": "bad", "version": "bad"}])
def test_malformed_signed_payload_is_unavailable(payload):
    """Malformed structures cannot crash credential resolution."""
    assert tokens.resolve(signing.dumps(payload, salt="search.management"), "management") is None


def test_deleted_or_expired_tokens_are_unavailable(criteria):
    """Deleted records and timestamp-expired confirmations resolve to no search."""
    search = pending(criteria)
    token = tokens.issue(search, "management")
    search.delete()
    assert tokens.resolve(token, "management") is None
    with patch.object(tokens.signing.time, "time", return_value=1):
        expired = tokens.issue(search, "confirmation")
    assert tokens.resolve(expired, "confirmation") is None


def test_public_form_and_generic_receipt(client, criteria, mailoutbox):
    """Valid submissions redirect without revealing credentials or address status."""
    assert client.get(reverse("search-create")).status_code == 200
    invalid = client.post(reverse("search-create"), {**posted(criteria), "email": "bad"})
    assert invalid.status_code == 200
    assert criteria["name"].encode() in invalid.content
    valid = client.post(reverse("search-create"), posted(criteria))
    assert valid.status_code == 302
    receipt = client.get(valid.url)
    assert b"Check your inbox" in receipt.content
    assert b"no-store" in receipt.headers["Cache-Control"].encode()
    assert b"/s/confirm/" not in receipt.content
    Subscriber.objects.update(suppressed=True)
    assert client.post(reverse("search-create"), posted(criteria)).url == valid.url
    assert len(mailoutbox) == 1


def test_registration_closed_in_production(client, settings):
    """A disabled registration setting blocks GET and POST without database writes."""
    settings.SEARCH_REGISTRATION_ENABLED = False
    assert client.get(reverse("search-create")).status_code == 503
    assert client.post(reverse("search-create"), {}).status_code == 503


def test_create_requires_csrf_and_private_criteria_are_escaped(criteria):
    """Forged public submissions fail and user-authored HTML is rendered as text."""
    client = Client(enforce_csrf_checks=True)
    assert client.post(reverse("search-create"), posted(criteria)).status_code == 403
    search = pending({**criteria, "name": "<script>alert(1)</script>"})
    response = client.get(reverse("search-manage", args=[tokens.issue(search, "management")]))
    assert b"<script>alert(1)</script>" not in response.content
    assert b"&lt;script&gt;" in response.content


def test_browser_journey_and_scanner_gets(criteria):
    """Only CSRF-protected button presses activate and cancel a private search."""
    client = Client(enforce_csrf_checks=True)
    search = pending(criteria, created_at=datetime.now(UTC))
    url = reverse("search-confirm", args=[tokens.issue(search, "confirmation")])
    assert client.get(url).status_code == 200
    search.refresh_from_db()
    assert search.status == "pending"
    assert client.post(url).status_code == 403
    response = client.post(url, {"csrfmiddlewaretoken": client.cookies["csrftoken"].value})
    assert response.status_code == 302
    management = client.get(response.url)
    assert management.status_code == 200
    assert criteria["email"].encode() not in management.content
    assert b"***@example.org" in management.content
    assert b"no-store" in management.headers["Cache-Control"].encode()
    assert (
        client.post(url, {"csrfmiddlewaretoken": client.cookies["csrftoken"].value}).status_code
        == 410
    )
    cancel_url = response.url.replace("/manage/", "/cancel/")
    assert client.get(cancel_url).status_code == 200
    search.refresh_from_db()
    assert search.status == "active"
    assert client.post(cancel_url).status_code == 403
    assert (
        client.post(
            cancel_url, {"csrfmiddlewaretoken": client.cookies["csrftoken"].value}
        ).status_code
        == 302
    )
    cancelled = client.get(response.url)
    assert b"Search cancelled" in cancelled.content
    assert criteria["description"].encode() not in cancelled.content


def test_confirmation_capacity_error_stays_on_page(client, criteria, settings):
    """Verified capacity failures show a useful message without activating."""
    settings.ACTIVE_SUBSCRIBER_LIMIT = 0
    search = pending(criteria, created_at=datetime.now(UTC))
    response = client.post(reverse("search-confirm", args=[tokens.issue(search, "confirmation")]))
    assert response.status_code == 200
    assert b"at capacity" in response.content


@pytest.mark.parametrize("route", ["search-confirm", "search-manage", "search-cancel"])
def test_invalid_private_links(client, route):
    """Invalid credentials disclose neither search criteria nor address information."""
    assert client.get(reverse(route, args=["invalid"])).status_code == 410


def test_management_credential_cannot_be_retargeted(criteria):
    """Changing the identifier breaks the signature rather than granting another search."""
    first, second = pending(criteria), pending(criteria, email="other@example.org")
    token = tokens.issue(first, "management")
    assert tokens.resolve(token, "management").pk != second.pk
    assert tokens.resolve(token + "tampered", "management") is None


def make_archive(path, text):
    """Write only synthetic reference rows into a test-owned archive."""
    with ZipFile(path, "w") as archive:
        archive.writestr("AU.txt", text)


def test_postcode_import_is_atomic_and_preserves_shared_states(tmp_path, criteria):
    """Known shared postcodes remain ambiguous and invalid imports preserve prior data."""
    path = tmp_path / "AU.zip"
    row = "AU\t2620\tPlace\tState\t{}\t\t\t\t\t0\t0\t1\n"
    make_archive(path, row.format("ACT") + row.format("NSW") + row.format("NSW"))
    call_command("load_postcodes", str(path), stdout=io.StringIO())
    assert set(Postcode.objects.values_list("code", "state")) == {("2620", "ACT"), ("2620", "NSW")}
    make_archive(path, "bad\tdata")
    with pytest.raises(CommandError, match="Invalid Australian"):
        call_command("load_postcodes", str(path))
    assert Postcode.objects.count() == 2
    make_archive(path, "")
    with pytest.raises(CommandError, match="no postcodes"):
        call_command("load_postcodes", str(path))
    with pytest.raises(CommandError, match="Cannot read"):
        call_command("load_postcodes", str(tmp_path / "absent.zip"))


def test_housekeeping_preserves_active_searches_and_rate_limits(criteria):
    """Purge clears expired confirmations and cancelled criteria without deleting active peers."""
    now = datetime.now(UTC)
    old = pending(criteria, created_at=now - timedelta(days=8))
    retired = pending(criteria, email="retired@example.org")
    testee.cancel(retired.pk, now)
    live = pending(criteria, created_at=now)
    testee.activate(live.pk, live.confirmation_version, now)
    Subscriber.objects.create(email="limited@example.org", email_day=now.date(), email_count=3)
    Subscriber.objects.create(email="blocked@example.org", suppressed=True)
    RequestSource.objects.create(key="old", day=now.date() - timedelta(days=1))
    grace = pending(criteria, email="grace@example.org")
    Search.objects.filter(pk=grace.pk).update(status="active", expires_at=now - timedelta(days=1))
    elapsed = pending(criteria, email="elapsed@example.org")
    Search.objects.filter(pk=elapsed.pk).update(
        status="active", expires_at=now - timedelta(days=31)
    )
    call_command("purge_searches", stdout=io.StringIO())
    assert not Search.objects.filter(pk__in=[old.pk, retired.pk]).exists()
    assert Search.objects.filter(pk=live.pk).exists()
    assert not Subscriber.objects.filter(email="retired@example.org").exists()
    assert Subscriber.objects.filter(email="limited@example.org").exists()
    assert Subscriber.objects.filter(email="blocked@example.org").exists()
    assert not RequestSource.objects.exists()
    assert Search.objects.filter(pk=grace.pk).exists()
    assert not Search.objects.filter(pk=elapsed.pk).exists()


@pytest.mark.parametrize("private", ["message", "request", "neither"])
def test_private_request_logging_redacts_credentials(private):
    """Request logs and exception details do not leak capability paths."""
    record = logging.LogRecord(
        "django",
        logging.ERROR,
        "",
        0,
        "GET /s/manage/secret/" if private == "message" else "ordinary",
        (),
        None,
    )
    record.request = RequestFactory().get(
        "/s/manage/secret/" if private == "request" else "/health/"
    )
    assert privacy.PrivateRequests().filter(record)
    if private == "neither":
        assert record.getMessage() == "ordinary"
    else:
        assert "secret" not in record.getMessage()
        assert record.request is None


@pytest.mark.django_db(transaction=True)
@pytest.mark.parametrize("same_subscriber", [False, True])
def test_concurrent_activation_cannot_overbook(criteria, settings, same_subscriber):
    """Competing activations contend for one slot and only one succeeds."""
    settings.ACTIVE_SUBSCRIBER_LIMIT = settings.ACTIVE_SEARCH_LIMIT = 1
    first = pending(criteria)
    second = pending(criteria, email=criteria["email"] if same_subscriber else "other@example.org")
    barrier = Barrier(2)

    def attempt(search):
        """Own and close the worker thread's database connection."""
        close_old_connections()
        try:
            barrier.wait(timeout=10)
            return testee.activate(search.pk, search.confirmation_version, NOW)[1]
        finally:
            close_old_connections()

    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(attempt, [first, second]))
    assert results.count("") == 1
    assert testee.active(NOW).count() == 1


@pytest.mark.django_db(transaction=True)
def test_concurrent_confirmation_requests_obey_email_limit(criteria, mailoutbox):
    """Parallel requests cannot exceed three captured emails or three pending records."""
    barrier = Barrier(4)

    def attempt(index):
        """Close each thread's owned connection after the bounded request completes."""
        close_old_connections()
        try:
            barrier.wait(timeout=10)
            return testee.request_search(criteria, str(index), NOW)
        finally:
            close_old_connections()

    with ThreadPoolExecutor(max_workers=4) as pool:
        results = list(pool.map(attempt, range(4)))
    assert sum(result is not None for result in results) == 3
    assert len(mailoutbox) == Search.objects.count() == 3
