"""Real PostgreSQL queue transactions, worker completion, and safe replay."""

import io
from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta
from threading import Barrier
from unittest.mock import patch

import pytest
from django.core.management import call_command
from django.db import close_old_connections, connection, transaction
from django.utils import timezone
from procrastinate.contrib.django import app
from procrastinate.contrib.django.models import ProcrastinateJob

import dog_finder.subscriptions.management.commands.enqueue_expiry_reminders as command_testee
import dog_finder.subscriptions.reminder_queue as testee
import dog_finder.subscriptions.services as service_testee
import dog_finder.subscriptions.tasks as task_testee
from dog_finder.subscriptions.models import Capacity, ExpiryReminder, Search, Subscriber

pytestmark = [pytest.mark.database, pytest.mark.django_db(transaction=True)]


@pytest.fixture(autouse=True)
def queue_state():
    """Clean unmanaged library tables only inside pytest's disposable database."""
    assert connection.settings_dict["NAME"] == "test_dog_finder"
    with connection.cursor() as cursor:
        cursor.execute("TRUNCATE procrastinate_jobs, procrastinate_workers CASCADE")
    try:
        yield
    finally:
        with connection.cursor() as cursor:
            cursor.execute("TRUNCATE procrastinate_jobs, procrastinate_workers CASCADE")


@pytest.fixture
def search():
    """Own a due search without public requests or external providers."""
    Capacity.objects.get_or_create(pk=1)
    return Search.objects.create(
        subscriber=Subscriber.objects.create(email="queue@example.org"),
        name="Queue test",
        description="Quiet dog",
        postcode="2000",
        state="NSW",
        interstate=False,
        status="active",
        created_at=timezone.now() - timedelta(days=84),
        expires_at=timezone.now() + timedelta(days=6),
    )


def run_worker():
    """Drain ready test jobs and close the worker's pool and loop before returning."""
    with app.replace_connector(app.connector.get_worker_connector()):
        app.run_worker(wait=False, install_signal_handlers=False, listen_notify=False)


def test_enqueue_is_id_only_and_coalesces_pending_jobs(search):
    """Duplicate deferral keeps one waiting job without storing private email content."""
    assert testee.enqueue(timezone.now()) == (1, 1)
    assert testee.enqueue(timezone.now()) == (0, 0)
    job = ProcrastinateJob.objects.get()
    assert job.args == {"reminder_id": ExpiryReminder.objects.get().pk}
    assert job.queue_name == "reminder-preview"
    assert job.task_name == "subscriptions.preview_expiry_reminder"
    assert job.lock == job.queueing_lock == f"reminder-preview:{job.args['reminder_id']}"
    assert job.status == "todo"


def test_outer_rollback_removes_both_reminder_and_job(search):
    """Queue insertion shares the caller's transaction, not a separate connection."""
    with pytest.raises(RuntimeError, match="rollback"):
        with transaction.atomic():
            assert testee.enqueue(timezone.now()) == (1, 1)
            raise RuntimeError("rollback")
    assert not ExpiryReminder.objects.exists()
    assert not ProcrastinateJob.objects.exists()


def test_concurrent_enqueue_commits_one_job(search):
    """Competing planners cannot publish duplicate logical reminders or waiting jobs."""
    barrier = Barrier(2)

    def enqueue_once(index):
        """Own each connection and join both calls before test teardown."""
        close_old_connections()
        try:
            barrier.wait(timeout=10)
            return testee.enqueue(timezone.now())
        finally:
            close_old_connections()

    with ThreadPoolExecutor(max_workers=2) as pool:
        assert sorted(pool.map(enqueue_once, range(2))) == [(0, 0), (1, 1)]
    assert ExpiryReminder.objects.count() == ProcrastinateJob.objects.count() == 1


def test_queue_failure_rolls_back_planning(search):
    """A deferral failure leaves no reminder published without its job."""
    with patch.object(task_testee.preview_expiry_reminder, "configure", side_effect=RuntimeError):
        with pytest.raises(RuntimeError):
            testee.enqueue(timezone.now())
    assert not ExpiryReminder.objects.exists()
    assert not ProcrastinateJob.objects.exists()


def test_worker_captures_once_and_replay_is_safe(search, mailoutbox):
    """Actual worker execution captures locally; replay cannot create a second message."""
    testee.enqueue(timezone.now())
    reminder = ExpiryReminder.objects.get()
    run_worker()
    reminder.refresh_from_db()
    assert reminder.status == "previewed"
    assert len(mailoutbox) == 1
    assert ProcrastinateJob.objects.get().status == "succeeded"
    task_testee.preview_expiry_reminder.defer(reminder_id=reminder.pk)
    run_worker()
    assert len(mailoutbox) == 1
    assert ProcrastinateJob.objects.filter(status="succeeded").count() == 2
    assert testee.enqueue(timezone.now()) == (0, 0)


@pytest.mark.parametrize("change", ["cancel", "suppress", "renew", "expire", "delete"])
def test_worker_rechecks_state_after_enqueue(search, change, mailoutbox):
    """Queued IDs do not bypass later lifecycle changes or capture stale credentials."""
    testee.enqueue(timezone.now())
    if change == "cancel":
        service_testee.cancel(search.pk, timezone.now())
    elif change == "suppress":
        service_testee.suppress(search.subscriber_id, timezone.now())
    elif change == "renew":
        service_testee.renew(search.pk, search.management_version, timezone.now())
    elif change == "expire":
        search.expires_at = timezone.now() - timedelta(seconds=1)
        search.save()
    else:
        search.delete()
    run_worker()
    assert not mailoutbox
    assert ProcrastinateJob.objects.get().status == "succeeded"
    assert not ExpiryReminder.objects.filter(status="pending").exists()


def test_failed_worker_retries_twice_then_stops(search, settings, mailoutbox):
    """Misconfiguration never sends live mail and cannot produce unlimited retries."""
    testee.enqueue(timezone.now())
    settings.EMAIL_BACKEND = "django.core.mail.backends.smtp.EmailBackend"
    for attempt in range(3):
        before = timezone.now()
        run_worker()
        job = ProcrastinateJob.objects.get()
        assert job.status == ("todo" if attempt < 2 else "failed")
        if attempt < 2:
            assert job.scheduled_at >= before + timedelta(seconds=60)
            # Advance only the test-owned job, avoiding sleeps or a global clock patch.
            with connection.cursor() as cursor:
                cursor.execute(
                    "UPDATE procrastinate_jobs SET scheduled_at = NULL WHERE id = %s", [job.pk]
                )
    assert job.attempts == 3
    assert ExpiryReminder.objects.get().status == "pending"
    assert not mailoutbox


def test_enqueue_command_reports_only_counts(search):
    """The operator command exposes counts but no addresses, descriptions, or tokens."""
    output = io.StringIO()
    with patch.object(command_testee.timezone, "now", return_value=timezone.now()):
        call_command("enqueue_expiry_reminders", stdout=output)
        call_command("enqueue_expiry_reminders", stdout=output)
    assert output.getvalue() == (
        "Planned 1; queued 1 local previews. No real email sent.\n"
        "Planned 0; queued 0 local previews. No real email sent.\n"
    )
