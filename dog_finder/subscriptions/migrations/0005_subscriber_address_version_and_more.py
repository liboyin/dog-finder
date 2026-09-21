import uuid

from django.db import migrations, models


class Migration(migrations.Migration):
    """Add distinct address-wide management and single-use recovery credentials."""

    dependencies = [
        ("subscriptions", "0004_search_unsubscribe_version"),
    ]

    operations = [
        migrations.AddField(
            model_name="subscriber",
            name="address_version",
            field=models.UUIDField(default=uuid.uuid4),
        ),
        migrations.AddField(
            model_name="subscriber",
            name="recovery_version",
            field=models.UUIDField(default=uuid.uuid4),
        ),
    ]
