"""Report the real MongoDB collections, indexes and field shapes.
Read-only: it samples documents and never writes, renames or drops anything."""

from __future__ import annotations

import json
from collections import Counter
from typing import Any

from django.core.management.base import BaseCommand
from pymongo.errors import PyMongoError

from apps.common.mongo import get_database, ping
from apps.common.schema import ALL_COLLECTIONS, SCHEMA, describe

SAMPLE_SIZE = 50


def _type_name(value: Any) -> str:
    return type(value).__name__


class Command(BaseCommand):
    help = "Inspect the connected MongoDB and compare it with the canonical schema."

    def add_arguments(self, parser) -> None:
        parser.add_argument("--json", action="store_true", help="Emit machine-readable JSON.")
        parser.add_argument(
            "--sample", type=int, default=SAMPLE_SIZE, help="Documents to sample per collection."
        )

    def handle(self, *args, **options) -> None:
        if not ping():
            self.stdout.write(self.style.ERROR("MongoDB is unreachable. Check MONGODB_URI."))
            return

        database = get_database()
        report: dict[str, Any] = {"database": database.name, "collections": {}}

        try:
            names = sorted(database.list_collection_names())
        except PyMongoError as exc:
            self.stdout.write(self.style.ERROR(f"Could not list collections: {type(exc).__name__}"))
            return

        for name in names:
            collection = database[name]
            fields: Counter[str] = Counter()
            types: dict[str, Counter[str]] = {}
            try:
                for doc in collection.find({}, limit=options["sample"]):
                    for key, value in doc.items():
                        fields[key] += 1
                        types.setdefault(key, Counter())[_type_name(value)] += 1
                indexes = [
                    {"name": idx.get("name"), "key": list(idx.get("key", {}).items())}
                    for idx in collection.list_indexes()
                ]
                count = collection.estimated_document_count()
            except PyMongoError as exc:
                self.stdout.write(self.style.WARNING(f"  {name}: {type(exc).__name__}"))
                continue

            report["collections"][name] = {
                "documents": count,
                "indexes": indexes,
                "fields": {
                    key: {"seen": seen, "types": dict(types[key])}
                    for key, seen in fields.most_common()
                },
            }

        report["expected"] = describe()
        report["mapping_gaps"] = self._gaps(report["collections"])

        if options["json"]:
            self.stdout.write(json.dumps(report, indent=2, default=str))
            return
        self._render(report)

    def _gaps(self, actual: dict[str, Any]) -> dict[str, list[str]]:
        """Fields the canonical schema expects but the sampled data does not show."""
        from django.conf import settings

        mapping = settings.MONGODB["COLLECTIONS"]
        gaps: dict[str, list[str]] = {}
        for logical in ALL_COLLECTIONS:
            physical = mapping.get(logical, logical)
            found = actual.get(physical, {}).get("fields", {})
            if not found:
                gaps[logical] = [f"collection '{physical}' is absent or empty"]
                continue
            missing = [field for field in SCHEMA[logical] if field not in found]
            if missing:
                gaps[logical] = missing
        return gaps

    def _render(self, report: dict[str, Any]) -> None:
        self.stdout.write(self.style.MIGRATE_HEADING(f"Database: {report['database']}"))
        if not report["collections"]:
            self.stdout.write(self.style.WARNING("  No collections found."))
        for name, info in report["collections"].items():
            self.stdout.write(
                self.style.MIGRATE_LABEL(f"\n  {name}  ({info['documents']} documents)")
            )
            for field, meta in list(info["fields"].items())[:30]:
                kinds = "/".join(meta["types"])
                self.stdout.write(f"    - {field}: {kinds} (seen {meta['seen']}x)")
            index_names = ", ".join(idx["name"] for idx in info["indexes"])
            self.stdout.write(f"    indexes: {index_names}")

        gaps = report["mapping_gaps"]
        self.stdout.write(self.style.MIGRATE_HEADING("\nSchema mapping"))
        if not gaps:
            self.stdout.write(self.style.SUCCESS("  Every expected field is present."))
            return
        for logical, missing in gaps.items():
            self.stdout.write(self.style.WARNING(f"  {logical}: {', '.join(missing)}"))
        self.stdout.write(
            "\n  Remap collections with MONGODB_COLLECTION_* or adjust apps/common/schema.py."
        )
