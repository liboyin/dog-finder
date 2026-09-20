"""Seed the single row used for serializing subscriber admission."""

from django.db import migrations


class Migration(migrations.Migration):
    """Create a durable capacity lock before accepting subscriber requests."""

    dependencies = [("subscriptions", "0001_initial")]
    operations = [
        migrations.RunSQL(
            "INSERT INTO subscriptions_capacity (id) VALUES (1)",
            "DELETE FROM subscriptions_capacity WHERE id = 1",
        )
    ]
