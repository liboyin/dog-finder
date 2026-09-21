"""Durable expiry reminder planning and local-only email previews."""

from datetime import datetime, timedelta

from django.conf import settings
from django.core.exceptions import ImproperlyConfigured
from django.core.mail import EmailMultiAlternatives
from django.db import transaction
from django.template.loader import render_to_string
from django.urls import reverse

from . import tokens
from .models import Capacity, ExpiryReminder, Search


@transaction.atomic
def prepare(now: datetime) -> int:
    """Plan once per expiry in the seven-day window, catching up only before expiry."""
    Capacity.objects.select_for_update().get(pk=1)
    searches = Search.objects.filter(
        status="active",
        expires_at__gt=now,
        expires_at__lte=now + timedelta(days=7),
        subscriber__suppressed=False,
    ).order_by("id")
    created_count = 0
    for search in searches:
        _, created = ExpiryReminder.objects.get_or_create(
            search=search, expires_at=search.expires_at, defaults={"created_at": now}
        )
        created_count += int(created)
    return created_count


@transaction.atomic
def capture(reminder_id: int, now: datetime) -> bool:
    """Capture one current reminder locally, serializing with renewal and cancellation.

    This is not a provider send: production integration must use durable send intents
    and acceptance reconciliation. Private URLs are rendered from current versions
    only after locking; the database stores neither rendered bodies nor credentials.
    """
    if settings.EMAIL_BACKEND != "django.core.mail.backends.locmem.EmailBackend":
        raise ImproperlyConfigured("Reminder preview requires local email capture")
    Capacity.objects.select_for_update().get(pk=1)
    reminder = (
        ExpiryReminder.objects.select_related("search__subscriber").filter(pk=reminder_id).first()
    )
    if reminder is None or reminder.status != "pending":
        return False
    search = reminder.search
    if (
        search.status != "active"
        or search.subscriber.suppressed
        or search.expires_at != reminder.expires_at
        or search.expires_at <= now
    ):
        reminder.status = "obsolete"
        reminder.save(update_fields=["status"])
        return False
    if search.expires_at > now + timedelta(days=7):
        return False
    credential = tokens.issue(search, "management")
    context = {
        "search": search,
        **{
            action: settings.PUBLIC_BASE_URL + reverse(f"search-{action}", args=[credential])
            for action in ("renew", "cancel", "manage")
        },
    }
    message = EmailMultiAlternatives(
        f"Your Dog Finder search expires soon: {search.name}",
        render_to_string("subscriptions/reminder.txt", context),
        settings.DEFAULT_FROM_EMAIL,
        [search.subscriber.email],
    )
    message.attach_alternative(
        render_to_string("subscriptions/reminder.html", context), "text/html"
    )
    if message.send() != 1:
        raise RuntimeError("Reminder was not captured")
    reminder.status = "previewed"
    reminder.previewed_at = now
    reminder.save(update_fields=["status", "previewed_at"])
    return True
