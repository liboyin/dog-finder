"""Import an operator-supplied GeoNames AU.zip without network access."""

import csv
import io
from argparse import ArgumentParser
from zipfile import BadZipFile, ZipFile

from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from dog_finder.subscriptions.forms import STATES
from dog_finder.subscriptions.models import Postcode


class Command(BaseCommand):
    """Load known postcode/state pairs; malformed input never replaces good data."""

    help = "Load postcode/state pairs from a local GeoNames AU.zip archive."

    def add_arguments(self, parser: ArgumentParser) -> None:
        """Require an explicit operator-owned archive path."""
        parser.add_argument("archive")

    def handle(self, *args, **options) -> None:
        """Validate the whole archive before atomically replacing the reference table."""
        pairs = set()
        try:
            with ZipFile(options["archive"]) as archive:
                with archive.open("AU.txt") as raw:
                    for row in csv.reader(io.TextIOWrapper(raw, encoding="utf-8"), delimiter="\t"):
                        if (
                            len(row) != 12
                            or row[0] != "AU"
                            or len(row[1]) != 4
                            or not row[1].isascii()
                            or not row[1].isdigit()
                            or row[4] not in dict(STATES)
                        ):
                            raise CommandError("Invalid Australian postcode row")
                        pairs.add((row[1], row[4]))
        except (OSError, BadZipFile, KeyError, UnicodeError) as exc:
            raise CommandError("Cannot read a valid GeoNames AU.zip archive") from exc
        if not pairs:
            raise CommandError("The archive contains no postcodes")
        with transaction.atomic():
            Postcode.objects.all().delete()
            Postcode.objects.bulk_create(
                [Postcode(code=code, state=state) for code, state in sorted(pairs)]
            )
        self.stdout.write(f"Loaded {len(pairs)} postcode/state pairs (GeoNames, CC BY 4.0).")
