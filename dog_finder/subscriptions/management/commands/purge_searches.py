"""Remove abandoned and retired search data without sending any emails."""

from datetime import timedelta

from django.core.management.base import BaseCommand
from django.db import transaction
from django.db.models import Q
from django.utils import timezone

from dog_finder.subscriptions.models import Capacity, RequestSource, Search, Subscriber


class Command(BaseCommand):
    """Run daily housekeeping; automated reminder delivery follows separately."""

    help = "Delete expired confirmations, cancelled searches, and searches beyond renewal grace."

    @transaction.atomic
    def handle(self, *args, **options) -> None:
        """Preserve other searches, same-day rate limits, and suppressed addresses."""
        Capacity.objects.select_for_update().get(pk=1)
        now = timezone.now()
        Search.objects.filter(
            Q(status="pending", created_at__lte=now - timedelta(days=7))
            | Q(status="cancelled")
            | Q(status="active", expires_at__lte=now - timedelta(days=30))
        ).delete()
        Subscriber.objects.filter(searches__isnull=True, suppressed=False).filter(
            Q(email_day__lt=now.date()) | Q(email_day__isnull=True)
        ).delete()
        RequestSource.objects.filter(day__lt=now.date()).delete()
        self.stdout.write("Search housekeeping complete.")
