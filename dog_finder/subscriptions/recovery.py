"""Local mailbox recovery and separately scoped address-wide capabilities."""

import uuid
from datetime import datetime, timedelta

from django.conf import settings
from django.core import signing
from django.core.exceptions import ImproperlyConfigured, ValidationError
from django.core.mail import send_mail
from django.db import transaction
from django.db.models import QuerySet
from django.urls import reverse

from . import services, tokens
from .models import Capacity, Search, Subscriber


def issue(subscriber: Subscriber, purpose: str) -> str:
    """Issue a recovery or address capability without embedding an email address."""
    return signing.dumps(
        {"id": subscriber.pk, "version": str(getattr(subscriber, f"{purpose}_version"))},
        salt=f"subscriber.{purpose}",
    )


def resolve(token: str, purpose: str) -> Subscriber | None:
    """Resolve non-suppressed identities with purpose isolation and recovery expiry."""
    try:
        data = signing.loads(
            token,
            salt=f"subscriber.{purpose}",
            max_age=7 * 86400 if purpose == "recovery" else None,
        )
        return Subscriber.objects.filter(
            pk=data["id"], suppressed=False, **{f"{purpose}_version": data["version"]}
        ).first()
    except (signing.BadSignature, KeyError, TypeError, ValueError, ValidationError):
        return None


def available(subscriber: Subscriber, now: datetime) -> QuerySet[Search]:
    """List activated searches through their exclusive renewal grace deadline."""
    return subscriber.searches.filter(
        status="active", expires_at__gt=now - timedelta(days=30)
    ).order_by("created_at", "id")


@transaction.atomic
def request_recovery(email: str, request_source: str, now: datetime) -> None:
    """Capture recovery locally, sharing the three-per-day confirmation/email counter.

    Unknown, suppressed, empty, or limited addresses return identically and receive
    no email. Never create identities or bypass source limits for recovery requests.
    The email argument must come from a validated RecoveryForm.
    """
    if settings.EMAIL_BACKEND != "django.core.mail.backends.locmem.EmailBackend":
        raise ImproperlyConfigured("Recovery currently requires local email capture")
    Capacity.objects.select_for_update().get(pk=1)
    if not services.reserve_request_source(request_source, now):
        return
    local, domain = email.strip().rsplit("@", 1)
    subscriber = Subscriber.objects.filter(
        email=f"{local}@{domain.lower()}", suppressed=False
    ).first()
    if subscriber is None or not available(subscriber, now).exists():
        return
    if subscriber.email_day != now.date():
        subscriber.email_day, subscriber.email_count = now.date(), 0
    if subscriber.email_count >= settings.CONFIRMATION_DAILY_LIMIT:
        return
    subscriber.email_count += 1
    subscriber.save(update_fields=["email_day", "email_count"])
    path = reverse("recovery-confirm", args=[issue(subscriber, "recovery")])
    lines = [
        "Find your Dog Finder alerts",
        "",
        "Open this link and press the button within 7 days:",
        f"{settings.PUBLIC_BASE_URL}{path}",
        "",
        "Expired searches still available for renewal:",
    ]
    for search in available(subscriber, now).filter(expires_at__lte=now):
        path = reverse("search-renew", args=[tokens.issue(search, "management")])
        lines.append(f"{search.name}: {settings.PUBLIC_BASE_URL}{path}")
    lines.append("If you did not request this email, discard it. Your searches are unchanged.")
    send_mail(
        "Find your Dog Finder alerts",
        "\n".join(lines),
        settings.DEFAULT_FROM_EMAIL,
        [subscriber.email],
    )


@transaction.atomic
def consume(token: str) -> Subscriber | None:
    """Consume recovery once under the lifecycle lock without changing search criteria."""
    Capacity.objects.select_for_update().get(pk=1)
    subscriber = resolve(token, "recovery")
    if subscriber is None:
        return None
    subscriber.recovery_version = uuid.uuid4()
    subscriber.save(update_fields=["recovery_version"])
    return subscriber
