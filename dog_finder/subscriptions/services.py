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


def admission_error(subscriber_id: int, now: datetime) -> str:
    """Check both quotas while the caller holds the shared capacity-row lock."""
    searches = active(now)
    count = searches.filter(subscriber_id=subscriber_id).count()
    if count >= settings.ACTIVE_SEARCH_LIMIT:
        return "You already have five active searches. Cancel one before starting another."
    if (
        count == 0
        and searches.values("subscriber_id").distinct().count() >= settings.ACTIVE_SUBSCRIBER_LIMIT
    ):
        return "Dog Finder is at capacity. Please try again later."
    return ""


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
    if error := admission_error(search.subscriber_id, now):
        return search, error
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


@transaction.atomic
def unsubscribe(token: str, now: datetime) -> None:
    """Cancel only the credential's search, with retries and stale links as no-ops.

    Resolve under the lifecycle lock so revocation and deletion cannot race the
    mutation. Reuse cancellation's criteria erasure; the nested lock is reentrant
    within this transaction. No subscriber-wide suppression is implied.
    """
    Capacity.objects.select_for_update().get(pk=1)
    search = tokens.resolve(token, "unsubscribe")
    if search is not None and search.status != "cancelled":
        cancel(search.pk, now)


@transaction.atomic
def edit(
    search_id: uuid.UUID,
    management_version: uuid.UUID,
    criteria: dict,
    now: datetime,
) -> str:
    """Save validated EditSearchForm data without overwriting a newer edit.

    Recheck the credential and lifecycle under the shared lock. Matching changes
    advance the criteria revision; renames preserve it and the existing baseline.
    No matching queues or source snapshots exist in this preview yet.
    """
    Capacity.objects.select_for_update().get(pk=1)
    search = Search.objects.select_related("subscriber").filter(pk=search_id).first()
    if (
        search is None
        or search.management_version != management_version
        or search.status != "active"
        or search.expires_at <= now
        or search.subscriber.suppressed
    ):
        return "This search cannot be edited. It may be expired, cancelled, or unavailable."
    if search.edit_version != criteria["edit_version"]:
        return "This search changed since you opened the form. Reload before editing again."
    matching_fields = ("postcode", "state", "interstate", "description")
    if any(getattr(search, field) != criteria[field] for field in matching_fields):
        search.criteria_revision += 1
        search.baseline_pending = True
    for field in ("name", *matching_fields):
        setattr(search, field, criteria[field])
    search.edit_version = uuid.uuid4()
    search.save()
    return ""


def renewable(search: Search | None, now: datetime) -> bool:
    """Return eligibility before quota checks; the exact grace deadline is exclusive."""
    return (
        search is not None
        and search.status == "active"
        and search.expires_at is not None
        and search.expires_at + timedelta(days=30) > now
        and not search.subscriber.suppressed
    )


@transaction.atomic
def renew(search_id: uuid.UUID, management_version: uuid.UUID, now: datetime) -> str:
    """Extend a term without stacking clicks, reacquiring capacity after expiry.

    Active renewal preserves the matching baseline. Grace-period renewal advances
    the matching revision and marks its baseline pending for the future pipeline.
    The shared lock serializes renewal with activation, editing, purge, and cancel.
    """
    Capacity.objects.select_for_update().get(pk=1)
    search = Search.objects.select_related("subscriber").filter(pk=search_id).first()
    if not renewable(search, now) or search.management_version != management_version:
        return "This search cannot be renewed. Create a new search if its renewal period has ended."
    if search.expires_at <= now:
        if error := admission_error(search.subscriber_id, now):
            return error
        search.criteria_revision += 1
        search.baseline_pending = True
        search.edit_version = uuid.uuid4()
    search.expires_at = max(search.expires_at, now + timedelta(days=90))
    search.save()
    return ""
