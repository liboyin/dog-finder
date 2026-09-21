"""Explicitly enqueue local-only reminder previews, without starting a worker."""

from django.core.management.base import BaseCommand
from django.utils import timezone

from ... import reminder_queue


class Command(BaseCommand):
    """Plan and defer preview jobs while reporting only aggregate counts."""

    help = "Enqueue local expiry reminder previews; does not send real email."

    def handle(self, *args: object, **options: object) -> None:
        """Commit the batch before reporting successful deferral."""
        planned, queued = reminder_queue.enqueue(timezone.now())
        self.stdout.write(f"Planned {planned}; queued {queued} local previews. No real email sent.")
