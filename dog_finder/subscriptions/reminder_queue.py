"""Transactional planning and deferral of local-only reminder previews."""

from datetime import datetime

from django.db import transaction
from procrastinate.exceptions import AlreadyEnqueued

from . import reminders, tasks
from .models import ExpiryReminder


@transaction.atomic
def enqueue(now: datetime) -> tuple[int, int]:
    """Atomically plan reminders and enqueue pending IDs with per-reminder locks.

    Planning holds the shared lifecycle lock until all deferrals commit. Queueing
    locks coalesce waiting jobs; execution locks serialize duplicate jobs, while
    capture rechecks durable completion and lifecycle state. An explicit later
    invocation can requeue a pending reminder whose job exhausted its retries.
    """
    planned = reminders.prepare(now)
    queued = 0
    for reminder_id in ExpiryReminder.objects.filter(status="pending").values_list("id", flat=True):
        key = f"reminder-preview:{reminder_id}"
        try:
            # A duplicate violates a queue constraint: isolate it in a savepoint
            # so catching AlreadyEnqueued does not poison the outer transaction.
            with transaction.atomic():
                tasks.preview_expiry_reminder.configure(lock=key, queueing_lock=key).defer(
                    reminder_id=reminder_id
                )
        except AlreadyEnqueued:
            continue
        queued += 1
    return planned, queued
