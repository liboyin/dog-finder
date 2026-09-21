"""Reminder deduplication, lifecycle checks, rendered output, and local-only effects."""

import io
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime, timedelta
from threading import Barrier
from unittest.mock import patch

import pytest
from django.core.exceptions import ImproperlyConfigured
from django.core.management import call_command
from django.db import close_old_connections

import dog_finder.subscriptions.management.commands.preview_expiry_reminders as command_testee
import dog_finder.subscriptions.recovery as recovery_testee
import dog_finder.subscriptions.reminders as testee
import dog_finder.subscriptions.services as service_testee
import dog_finder.subscriptions.tokens as token_testee
from dog_finder.subscriptions.models import Capacity, ExpiryReminder, Search, Subscriber

pytestmark = [pytest.mark.database, pytest.mark.django_db]
NOW = datetime(2026, 9, 21, tzinfo=UTC)


@pytest.fixture
def search():
    """Own one search exactly seven days before expiry, without real provider access."""
    Capacity.objects.get_or_create(pk=1)
    return Search.objects.create(
        subscriber=Subscriber.objects.create(email="reminder@example.org", verified_at=NOW),
        name="<em>Friend & dog</em>",
        description="Calm dog",
        postcode="2000",
        state="NSW",
        interstate=False,
        status="active",
        created_at=NOW - timedelta(days=83),
        expires_at=NOW + timedelta(days=7),
        baseline_pending=False,
    )


@pytest.mark.parametrize(
    "offset,expected",
    [
        (timedelta(days=7, microseconds=1), 0),
        (timedelta(days=7), 1),
        (timedelta(seconds=1), 1),
        (timedelta(0), 0),
        (timedelta(days=-1), 0),
    ],
)
def test_planning_window_boundaries(search, offset, expected):
    """A delayed run catches up before expiry but never before the seven-day window."""
    search.expires_at = NOW + offset
    search.save()
    assert testee.prepare(NOW) == expected
    assert testee.prepare(NOW) == 0
    assert ExpiryReminder.objects.count() == expected


@pytest.mark.parametrize("state", ["pending", "cancelled", "suppressed"])
def test_ineligible_searches_are_not_planned(search, state):
    """Unactivated, cancelled, and suppressed searches never receive planned reminders."""
    if state == "suppressed":
        search.subscriber.suppressed = True
        search.subscriber.save()
    else:
        search.status = state
        search.save()
    assert testee.prepare(NOW) == 0


def test_capture_renders_current_links_and_deduplicates(search, mailoutbox):
    """Local HTML/text contain current renewal/cancel links without tracking or duplicates."""
    testee.prepare(NOW)
    reminder = ExpiryReminder.objects.get()
    old_token = token_testee.issue(search, "management")
    recovery_testee.consume(
        recovery_testee.issue(search.subscriber, "recovery"), replace_links=True
    )
    assert testee.capture(reminder.pk, NOW)
    assert not testee.capture(reminder.pk, NOW)
    assert testee.prepare(NOW) == 0
    assert len(mailoutbox) == 1
    message = mailoutbox[0]
    assert message.to == [search.subscriber.email]
    assert search.name in message.body
    assert "28 September 2026" in message.body
    assert old_token not in message.body
    assert "/s/renew/" in message.body and "/s/cancel/" in message.body
    assert "activated this search" in message.body
    assert message.alternatives[0].mimetype == "text/html"
    html = message.alternatives[0].content
    assert "&lt;em&gt;Friend &amp; dog&lt;/em&gt;" in html
    assert "<em>Friend" not in html and "<img" not in html
    reminder.refresh_from_db()
    assert reminder.status == "previewed" and reminder.previewed_at == NOW


@pytest.mark.parametrize("change", ["cancel", "suppress", "renew", "expire", "delete"])
def test_capture_rechecks_lifecycle_after_planning(search, change, mailoutbox):
    """Work planned earlier cannot survive cancellation, suppression, expiry, or renewal."""
    testee.prepare(NOW)
    reminder = ExpiryReminder.objects.get()
    capture_time = NOW
    if change == "cancel":
        service_testee.cancel(search.pk, NOW)
    elif change == "suppress":
        search.subscriber.suppressed = True
        search.subscriber.save()
    elif change == "renew":
        service_testee.renew(search.pk, search.management_version, NOW)
    elif change == "expire":
        capture_time = search.expires_at
    else:
        search.delete()
    assert not testee.capture(reminder.pk, capture_time)
    assert not mailoutbox
    if change == "delete":
        assert not ExpiryReminder.objects.exists()
    else:
        reminder.refresh_from_db()
        assert reminder.status == "obsolete"


def test_new_expiry_gets_new_reminder_and_early_capture_waits(search, mailoutbox):
    """A new term gets its own reminder; a clock before the due window cannot capture."""
    testee.prepare(NOW)
    original = ExpiryReminder.objects.get()
    assert not testee.capture(original.pk, NOW - timedelta(seconds=1))
    original.refresh_from_db()
    assert original.status == "pending"
    assert testee.capture(original.pk, NOW)
    service_testee.renew(search.pk, search.management_version, NOW)
    assert testee.prepare(NOW) == 0
    due = NOW + timedelta(days=83)
    assert testee.prepare(due) == 1
    fresh = ExpiryReminder.objects.exclude(pk=original.pk).get()
    assert testee.capture(fresh.pk, due)
    assert len(mailoutbox) == 2


@pytest.mark.parametrize("outcome", [0, RuntimeError("controlled failure")])
def test_failed_capture_remains_pending_for_retry(search, outcome):
    """No recorded capture is committed when local capture fails or reports zero emails."""
    testee.prepare(NOW)
    reminder = ExpiryReminder.objects.get()
    options = (
        {"side_effect": outcome} if isinstance(outcome, Exception) else {"return_value": outcome}
    )
    with patch.object(testee.EmailMultiAlternatives, "send", **options):
        with pytest.raises(RuntimeError):
            testee.capture(reminder.pk, NOW)
    reminder.refresh_from_db()
    assert reminder.status == "pending" and reminder.previewed_at is None


def test_live_backend_is_refused(search, settings):
    """Reminder preview cannot be switched into SMTP delivery through configuration."""
    testee.prepare(NOW)
    settings.EMAIL_BACKEND = "django.core.mail.backends.smtp.EmailBackend"
    with pytest.raises(ImproperlyConfigured, match="local email capture"):
        testee.capture(ExpiryReminder.objects.get().pk, NOW)


def test_preview_command_reports_counts_without_private_data(search, mailoutbox):
    """The local command prints aggregate counts, never credentials or message bodies."""
    output = io.StringIO()
    with patch.object(command_testee.timezone, "now", return_value=NOW):
        call_command("preview_expiry_reminders", stdout=output)
        call_command("preview_expiry_reminders", stdout=output)
    assert (
        output.getvalue()
        == "Planned 1; locally captured 1. No real email sent.\nPlanned 0; locally captured 0. No real email sent.\n"
    )
    assert len(mailoutbox) == 1


@pytest.mark.django_db(transaction=True)
def test_parallel_planning_and_capture_happen_once(search, mailoutbox):
    """Overlapping preview workers cannot duplicate either the intent or local message."""
    barrier = Barrier(2)

    def attempt(index):
        """Own and close the connection for each bounded concurrent attempt."""
        close_old_connections()
        try:
            barrier.wait(timeout=10)
            testee.prepare(NOW)
            return testee.capture(ExpiryReminder.objects.get().pk, NOW)
        finally:
            close_old_connections()

    with ThreadPoolExecutor(max_workers=2) as pool:
        assert list(pool.map(attempt, range(2))).count(True) == 1
    assert ExpiryReminder.objects.count() == len(mailoutbox) == 1
