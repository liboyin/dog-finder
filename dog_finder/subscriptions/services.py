"""Transactional admission and lifecycle operations; no live provider integrations."""

import uuid
from datetime import datetime, timedelta

from django.conf import settings
from django.core.exceptions import ImproperlyConfigured
from django.core.mail import send_mail
from django.db import transaction
from django.db.models import QuerySet
from django.urls import reverse
from django.utils.crypto import salted_hmac

from . import tokens
from .models import Capacity, RequestSource, Search, Subscriber


def active(now: datetime) -> QuerySet[Search]:
    """Count only activated, unexpired searches even before housekeeping runs."""
    return Search.objects.filter(status="active", expires_at__gt=now)


@transaction.atomic
def request_search(criteria: dict, request_source: str, now: datetime) -> Search | None:
    """Create a bounded pending search and capture local email in the same transaction.

    Criteria must come from a validated SearchForm. Returning None is deliberately
    indistinguishable to the public caller. Live email is prohibited in this milestone.
    """
    if settings.EMAIL_BACKEND != "django.core.mail.backends.locmem.EmailBackend":
        raise ImproperlyConfigured("Search creation currently requires local email capture")
    Capacity.objects.select_for_update().get(pk=1)
    today = now.date()
    key = salted_hmac("confirmation-source", request_source).hexdigest()
    source, _ = RequestSource.objects.get_or_create(key=key, defaults={"day": today})
    if source.day != today:
        source.day, source.count = today, 0
    if source.count >= settings.REQUEST_SOURCE_DAILY_LIMIT:
        return None
    source.count += 1
    source.save()
    if Search.objects.filter(status="pending").count() >= settings.PENDING_SEARCH_LIMIT:
        return None
    email = criteria["email"].strip()
    local, domain = email.rsplit("@", 1)
    subscriber, _ = Subscriber.objects.get_or_create(email=f"{local}@{domain.lower()}")
    if subscriber.email_day != today:
        subscriber.email_day, subscriber.email_count = today, 0
    if subscriber.suppressed or subscriber.email_count >= settings.CONFIRMATION_DAILY_LIMIT:
        return None
    if not active(now).filter(subscriber=subscriber).exists():
        if (
            active(now).values("subscriber_id").distinct().count()
            >= settings.ACTIVE_SUBSCRIBER_LIMIT
        ):
            return None
    subscriber.email_count += 1
    subscriber.save()
    search = Search.objects.create(
        subscriber=subscriber,
        created_at=now,
        **{
            key: criteria[key] for key in ("name", "description", "postcode", "state", "interstate")
        },
    )
    path = reverse("search-confirm", args=[tokens.issue(search, "confirmation")])
    send_mail(
        f"Confirm your Dog Finder search: {search.name}",
        f"Dog Finder\n\n{search.name}\n{search.description}\n"
        f"Home: {search.postcode} {search.state}\nInterstate: {search.interstate}\n\n"
        f"Activate this search (expires in 7 days):\n{settings.PUBLIC_BASE_URL}{path}\n\n"
        "If you did not request this search, discard this email. No alerts start without confirmation.",
        settings.DEFAULT_FROM_EMAIL,
        [subscriber.email],
    )
    return search


@transaction.atomic
def activate(search_id: uuid.UUID, version: uuid.UUID, now: datetime) -> tuple[Search | None, str]:
    """Consume confirmation only on success while atomically enforcing both quotas."""
    Capacity.objects.select_for_update().get(pk=1)
    search = Search.objects.select_related("subscriber").filter(pk=search_id).first()
    if (
        search is None
        or search.status != "pending"
        or search.confirmation_version != version
        or search.created_at + timedelta(days=7) <= now
        or search.subscriber.suppressed
    ):
        return search, "This confirmation is no longer available."
    searches = active(now)
    count = searches.filter(subscriber=search.subscriber).count()
    if count >= settings.ACTIVE_SEARCH_LIMIT:
        return (
            search,
            "You already have five active searches. Cancel one before activating another.",
        )
    if (
        count == 0
        and searches.values("subscriber_id").distinct().count() >= settings.ACTIVE_SUBSCRIBER_LIMIT
    ):
        return search, "Dog Finder is at capacity. Please try again later."
    search.status = "active"
    search.activated_at = now
    search.expires_at = now + timedelta(days=90)
    search.confirmation_version = uuid.uuid4()
    search.save()
    search.subscriber.verified_at = now
    search.subscriber.save(update_fields=["verified_at"])
    return search, ""


@transaction.atomic
def cancel(search_id: uuid.UUID, now: datetime) -> Search | None:
    """Cancel idempotently and immediately remove the stored search criteria."""
    Capacity.objects.select_for_update().get(pk=1)
    search = Search.objects.filter(pk=search_id).first()
    if search is None:
        return None
    search.status = "cancelled"
    search.cancelled_at = now
    search.name = search.description = search.postcode = search.state = ""
    search.save()
    return search
