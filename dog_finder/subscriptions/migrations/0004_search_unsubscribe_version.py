import uuid

from django.db import migrations, models


class Migration(migrations.Migration):
    """Add independently revocable cancellation-only credentials to searches."""

    dependencies = [
        ("subscriptions", "0003_search_criteria_revision_search_edit_version"),
    ]

    operations = [
        migrations.AddField(
            model_name="search",
            name="unsubscribe_version",
            field=models.UUIDField(default=uuid.uuid4),
        ),
    ]
