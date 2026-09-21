"""Plan reminders and capture them in process memory without live delivery."""

from django.core.management.base import BaseCommand
from django.utils import timezone

from dog_finder.subscriptions import reminders
from dog_finder.subscriptions.models import ExpiryReminder


class Command(BaseCommand):
    """Run the local-only reminder preview; never print private email bodies or links."""

    help = "Plan due reminders and capture local previews (not inbox delivery)."

    def handle(self, *args, **options) -> None:
        """Report only aggregate counts and leave stale records obsolete."""
        planned = reminders.prepare(timezone.now())
        identifiers = list(
            ExpiryReminder.objects.filter(status="pending").values_list("pk", flat=True)
        )
        captured = sum(reminders.capture(identifier, timezone.now()) for identifier in identifiers)
        self.stdout.write(f"Planned {planned}; locally captured {captured}. No real email sent.")
