"""Atomic address suppression across search, reminder, and recovery lifecycles."""

import io
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime, timedelta
from threading import Barrier
from unittest.mock import patch

import pytest
from django.core.management import call_command
from django.db import close_old_connections

import dog_finder.subscriptions.recovery as recovery_testee
import dog_finder.subscriptions.reminders as reminder_testee
import dog_finder.subscriptions.services as testee
from dog_finder.subscriptions.models import Capacity, ExpiryReminder, Search, Subscriber

pytestmark = [pytest.mark.database, pytest.mark.django_db]
NOW = datetime(2026, 9, 21, tzinfo=UTC)


@pytest.fixture
def search():
    """Own an address and activated search without real providers or personal data."""
    Capacity.objects.get_or_create(pk=1)
    subscriber = Subscriber.objects.create(email="blocked@example.org", verified_at=NOW)
    return make_search(subscriber)


def make_search(subscriber, **changes):
    """Create test-owned criteria in the lifecycle state needed by each invariant."""
    fields = dict(
        name="Friend",
        description="Calm dog",
        postcode="2000",
        state="NSW",
        interstate=True,
        created_at=NOW,
        status="active",
        expires_at=NOW + timedelta(days=7),
    )
    return Search.objects.create(subscriber=subscriber, **{**fields, **changes})


def criteria(search):
    """Return valid canonical submission data for the isolated address."""
    return {
        "email": search.subscriber.email,
        **{
            field: getattr(search, field)
            for field in ("name", "description", "postcode", "state", "interstate")
        },
    }


def test_suppression_cancels_all_states_and_preserves_other_addresses(search):
    """An address-wide block erases criteria and releases capacity without affecting peers."""
    pending = make_search(search.subscriber, status="pending", expires_at=None)
    expired = make_search(search.subscriber, expires_at=NOW)
    cancelled = make_search(search.subscriber)
    testee.cancel(cancelled.pk, NOW - timedelta(days=1))
    peer = make_search(Subscriber.objects.create(email="other@example.org"))
    reminder_testee.prepare(NOW)
    subscriber = search.subscriber
    old_address, old_recovery = subscriber.address_version, subscriber.recovery_version
    assert testee.suppress(subscriber.pk, NOW) == 3
    subscriber.refresh_from_db()
    assert subscriber.suppressed
    assert subscriber.address_version != old_address and subscriber.recovery_version != old_recovery
    for item in (search, pending, expired):
        item.refresh_from_db()
        assert item.status == "cancelled" and item.cancelled_at == NOW
        assert item.name == item.description == item.postcode == item.state == ""
        assert not item.interstate
    cancelled.refresh_from_db()
    assert cancelled.cancelled_at == NOW - timedelta(days=1)
    assert ExpiryReminder.objects.get(search=search).status == "obsolete"
    assert ExpiryReminder.objects.get(search=peer).status == "pending"
    peer.refresh_from_db()
    assert peer.status == "active" and peer.description == "Calm dog"
    assert testee.active(NOW).count() == 1
    versions = (subscriber.address_version, subscriber.recovery_version)
    assert testee.suppress(subscriber.pk, NOW + timedelta(days=1)) == 0
    subscriber.refresh_from_db()
    assert versions == (subscriber.address_version, subscriber.recovery_version)
    search.refresh_from_db()
    assert search.cancelled_at == NOW
    assert testee.suppress(999999, NOW) == 0


def test_suppression_blocks_future_work_and_survives_housekeeping(search, mailoutbox):
    """Purging cancelled searches cannot let the blocked address subscribe again."""
    original = criteria(search)
    recovery_token = recovery_testee.issue(search.subscriber, "recovery")
    address_token = recovery_testee.issue(search.subscriber, "address")
    reminder_testee.prepare(NOW)
    reminder = ExpiryReminder.objects.get()
    testee.suppress(search.subscriber_id, NOW)
    assert not reminder_testee.capture(reminder.pk, NOW)
    assert testee.activate(search.pk, search.confirmation_version, NOW)[1]
    assert testee.renew(search.pk, search.management_version, NOW)
    assert testee.edit(search.pk, search.management_version, {}, NOW)
    assert recovery_testee.consume(recovery_token) is None
    assert recovery_testee.resolve(address_token, "address") is None
    recovery_testee.request_recovery(original["email"], "source", NOW)
    assert testee.request_search(original, "source", NOW) is None
    call_command("purge_searches", stdout=io.StringIO())
    assert not Search.objects.filter(subscriber=search.subscriber).exists()
    assert Subscriber.objects.get(pk=search.subscriber_id).suppressed
    assert testee.request_search(original, "source", NOW + timedelta(days=1)) is None
    assert not mailoutbox


def test_suppression_rolls_back_all_effects_on_failure(search):
    """A partially cancelled address cannot escape the all-or-nothing transaction."""
    make_search(search.subscriber)
    reminder_testee.prepare(NOW)
    original_cancel = testee.cancel
    attempts = []

    def fail_second(*args, **kwargs):
        """Fail after one mutation to exercise transaction rollback rather than preflight."""
        attempts.append(args[0])
        if len(attempts) == 2:
            raise RuntimeError("controlled failure")
        return original_cancel(*args, **kwargs)

    with patch.object(testee, "cancel", side_effect=fail_second):
        with pytest.raises(RuntimeError, match="controlled failure"):
            testee.suppress(search.subscriber_id, NOW)
    search.subscriber.refresh_from_db()
    assert not search.subscriber.suppressed
    assert Search.objects.filter(status="active", description="Calm dog").count() == 2
    assert ExpiryReminder.objects.filter(status="pending").count() == 2


def test_suppression_keeps_preview_history_and_releases_admission_slot(search, settings):
    """Past local captures are not recalled, while a different address can take the slot."""
    settings.ACTIVE_SUBSCRIBER_LIMIT = 1
    reminder_testee.prepare(NOW)
    reminder = ExpiryReminder.objects.get()
    reminder_testee.capture(reminder.pk, NOW)
    peer = make_search(
        Subscriber.objects.create(email="other@example.org"), status="pending", expires_at=None
    )
    assert testee.activate(peer.pk, peer.confirmation_version, NOW)[1]
    testee.suppress(search.subscriber_id, NOW)
    assert not testee.activate(peer.pk, peer.confirmation_version, NOW)[1]
    reminder.refresh_from_db()
    assert reminder.status == "previewed" and reminder.previewed_at == NOW


@pytest.mark.django_db(transaction=True)
@pytest.mark.parametrize("operation", ["activate", "create", "renew", "capture", "repeat"])
def test_suppression_serializes_with_other_lifecycle_operations(search, operation, mailoutbox):
    """Whichever contender wins first, suppression leaves no send-eligible search behind."""
    pending = make_search(search.subscriber, status="pending", expires_at=None)
    reminder_testee.prepare(NOW)
    reminder = ExpiryReminder.objects.get()
    original = criteria(search)
    barrier = Barrier(2)

    def attempt(index):
        """Own each connection and synchronize only the start of bounded operations."""
        close_old_connections()
        try:
            barrier.wait(timeout=10)
            if index == 0 or operation == "repeat":
                return testee.suppress(search.subscriber_id, NOW)
            if operation == "activate":
                return testee.activate(pending.pk, pending.confirmation_version, NOW)
            if operation == "create":
                return testee.request_search(original, "source", NOW)
            if operation == "renew":
                return testee.renew(search.pk, search.management_version, NOW)
            return reminder_testee.capture(reminder.pk, NOW)
        finally:
            close_old_connections()

    with ThreadPoolExecutor(max_workers=2) as pool:
        list(pool.map(attempt, range(2)))
    assert Subscriber.objects.get(pk=search.subscriber_id).suppressed
    assert not Search.objects.exclude(status="cancelled").exists()
    assert not ExpiryReminder.objects.filter(status="pending").exists()
    captured = len(mailoutbox)
    assert captured <= 1
    assert not reminder_testee.capture(reminder.pk, NOW)
    assert testee.request_search(original, "source", NOW) is None
    assert len(mailoutbox) == captured
