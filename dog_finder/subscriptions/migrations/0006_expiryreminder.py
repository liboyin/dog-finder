import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):
    """Persist unique expiry reminder records without storing rendered credentials."""

    dependencies = [
        ("subscriptions", "0005_subscriber_address_version_and_more"),
    ]

    operations = [
        migrations.CreateModel(
            name="ExpiryReminder",
            fields=[
                (
                    "id",
                    models.BigAutoField(
                        auto_created=True, primary_key=True, serialize=False, verbose_name="ID"
                    ),
                ),
                ("expires_at", models.DateTimeField()),
                ("created_at", models.DateTimeField()),
                ("status", models.CharField(default="pending", max_length=10)),
                ("previewed_at", models.DateTimeField(null=True)),
                (
                    "search",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="reminders",
                        to="subscriptions.search",
                    ),
                ),
            ],
            options={
                "indexes": [
                    models.Index(fields=["status", "id"], name="subscriptio_status_ae9acd_idx")
                ],
                "constraints": [
                    models.UniqueConstraint(
                        fields=("search", "expires_at"), name="reminder_search_expiry"
                    ),
                    models.CheckConstraint(
                        condition=models.Q(("status__in", ["pending", "previewed", "obsolete"])),
                        name="valid_reminder_status",
                    ),
                ],
            },
        ),
    ]
