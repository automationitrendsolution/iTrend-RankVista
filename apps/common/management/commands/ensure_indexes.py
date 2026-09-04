"""Create the MongoDB indexes the platform relies on. Safe to run repeatedly."""

from __future__ import annotations

from django.core.management.base import BaseCommand

from apps.common.mongo import ping
from apps.common.schema import ensure_indexes


class Command(BaseCommand):
    help = "Create MongoDB indexes for projects, ASINs, keywords and rankings."

    def handle(self, *args, **options) -> None:
        if not ping():
            self.stdout.write(self.style.WARNING("MongoDB is unreachable. No indexes created."))
            return
        created = ensure_indexes(verbose=True)
        for collection, names in created.items():
            status = ", ".join(names) if names else "unchanged"
            self.stdout.write(f"  {collection}: {status}")
        self.stdout.write(self.style.SUCCESS("MongoDB indexes ensured."))
