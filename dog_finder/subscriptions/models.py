"""Durable search state and rows used to serialize capacity decisions."""

import uuid

from django.db import models


class Capacity(models.Model):
    """Singleton lock shared by admission, activation, and cancellation transactions."""

    id = models.PositiveSmallIntegerField(primary_key=True, default=1)


class Postcode(models.Model):
    """One known postcode/state pair, allowing postcodes spanning states."""

    code = models.CharField(max_length=4)
    state = models.CharField(max_length=3)

    class Meta:
        """Prevent duplicate reference pairs."""

        constraints = [models.UniqueConstraint(fields=["code", "state"], name="postcode_state")]


class Subscriber(models.Model):
    """An email identity; confirmation alone grants search access."""

    email = models.EmailField(unique=True)
    suppressed = models.BooleanField(default=False)
    verified_at = models.DateTimeField(null=True)
    email_day = models.DateField(null=True)
    email_count = models.PositiveIntegerField(default=0)


class RequestSource(models.Model):
    """A daily keyed hash counter; raw IP addresses are never persisted."""

    key = models.CharField(max_length=64, primary_key=True)
    day = models.DateField()
    count = models.PositiveIntegerField(default=0)


class Search(models.Model):
    """Independent pending/active/cancelled criteria with purpose-specific credentials."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    subscriber = models.ForeignKey(Subscriber, on_delete=models.CASCADE, related_name="searches")
    name = models.CharField(max_length=100)
    description = models.CharField(max_length=300)
    postcode = models.CharField(max_length=4)
    state = models.CharField(max_length=3)
    interstate = models.BooleanField()
    status = models.CharField(max_length=10, default="pending")
    created_at = models.DateTimeField()
    activated_at = models.DateTimeField(null=True)
    expires_at = models.DateTimeField(null=True)
    cancelled_at = models.DateTimeField(null=True)
    confirmation_version = models.UUIDField(default=uuid.uuid4)
    management_version = models.UUIDField(default=uuid.uuid4)
    baseline_pending = models.BooleanField(default=True)
    criteria_revision = models.PositiveIntegerField(default=1)
    edit_version = models.UUIDField(default=uuid.uuid4)

    class Meta:
        """Keep lifecycle queries indexed and reject unsupported states."""

        indexes = [models.Index(fields=["status", "expires_at"])]
        constraints = [
            models.CheckConstraint(
                condition=models.Q(status__in=["pending", "active", "cancelled"]),
                name="valid_search_status",
            )
        ]
