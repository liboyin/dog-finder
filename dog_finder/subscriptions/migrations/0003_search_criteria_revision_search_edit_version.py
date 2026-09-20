import uuid

from django.db import migrations, models


class Migration(migrations.Migration):
    """Add matching revision and optimistic edit versions to existing searches."""

    dependencies = [
        ("subscriptions", "0002_capacity"),
    ]

    operations = [
        migrations.AddField(
            model_name="search",
            name="criteria_revision",
            field=models.PositiveIntegerField(default=1),
        ),
        migrations.AddField(
            model_name="search",
            name="edit_version",
            field=models.UUIDField(default=uuid.uuid4),
        ),
    ]
