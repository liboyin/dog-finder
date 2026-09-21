"""ID-only background tasks; no provider delivery is enabled."""

from django.utils import timezone
from procrastinate import RetryStrategy
from procrastinate.contrib.django import app

from . import reminders


@app.task(
    name="subscriptions.preview_expiry_reminder",
    queue="reminder-preview",
    retry=RetryStrategy(max_attempts=2, wait=60),
)
def preview_expiry_reminder(reminder_id: int) -> None:
    """Capture locally with current lifecycle checks, at most twice retrying failures.

    This task deliberately does not provide external email acceptance semantics.
    Replayed jobs are safe because the reminder record owns completion state.
    """
    reminders.capture(reminder_id, timezone.now())
