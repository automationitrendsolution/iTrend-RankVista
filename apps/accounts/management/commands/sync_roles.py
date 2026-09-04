"""Seed the built-in roles and their page grants. Idempotent and non-destructive."""

from __future__ import annotations

from django.core.management.base import BaseCommand
from django.db import transaction

from apps.accounts import roles as role_service
from apps.accounts.models import ROLE_RANK, Role
from apps.accounts.pages import PAGES
from apps.accounts.role_models import RoleDefinition, RolePermission


class Command(BaseCommand):
    help = "Create the built-in roles and their default page permissions."

    def add_arguments(self, parser) -> None:
        parser.add_argument(
            "--reset",
            action="store_true",
            help="Restore the built-in grants for system roles, discarding edits.",
        )

    @transaction.atomic
    def handle(self, *args, **options) -> None:
        created_roles = 0
        for code, label in Role.choices:
            role, created = RoleDefinition.objects.get_or_create(
                code=code,
                defaults={
                    "label": label,
                    "description": role_service.SYSTEM_DESCRIPTIONS.get(code, ""),
                    "rank": ROLE_RANK.get(code, 10),
                    "is_system": True,
                },
            )
            if created:
                created_roles += 1
            elif not role.is_system:
                role.is_system = True
                role.save(update_fields=["is_system", "updated_at"])

            existing = {p.page_key: p for p in role.permissions.all()}
            for item in PAGES:
                default = item.allows(code)
                current = existing.get(item.key)
                if current is None:
                    RolePermission.objects.create(
                        role=role, page_key=item.key, allowed=default
                    )
                elif options["reset"] and current.allowed != default:
                    current.allowed = default
                    current.save(update_fields=["allowed"])

            # Retire grants for pages that no longer exist.
            known = {item.key for item in PAGES}
            role.permissions.exclude(page_key__in=known).delete()

        role_service.invalidate()
        total = RoleDefinition.objects.count()
        self.stdout.write(
            self.style.SUCCESS(
                f"Roles synced: {total} total, {created_roles} created."
                + (" Built-in grants restored." if options["reset"] else "")
            )
        )
