"""Idempotent bootstrap of the initial administrator from environment variables.
The password is only ever hashed; it is never printed, returned or stored raw."""

from __future__ import annotations

import os

from django.core.exceptions import ValidationError
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from apps.accounts.models import Role, User
from apps.common.secrets import resolve
from apps.audit.models import AuditAction
from apps.audit.services import record

REQUIRED_VARS = ("APP_ADMIN_EMAIL", "APP_ADMIN_USERNAME", "APP_ADMIN_PASSWORD")


class Command(BaseCommand):
    help = "Create or repair the bootstrap administrator defined by APP_ADMIN_* env vars."

    def add_arguments(self, parser) -> None:
        parser.add_argument(
            "--skip-if-missing",
            action="store_true",
            help="Exit quietly instead of failing when the env vars are absent.",
        )
        parser.add_argument(
            "--reset-password",
            action="store_true",
            help="Also reset the password of an existing bootstrap admin.",
        )

    @transaction.atomic
    def handle(self, *args, **options) -> None:
        missing = [name for name in REQUIRED_VARS if not os.environ.get(name)]
        if missing:
            message = f"Missing required environment variables: {', '.join(missing)}"
            if options["skip_if_missing"]:
                self.stdout.write(self.style.WARNING(f"{message}. Skipping bootstrap."))
                return
            raise CommandError(message)

        email = os.environ["APP_ADMIN_EMAIL"].strip().lower()
        username = os.environ["APP_ADMIN_USERNAME"].strip()
        password = resolve(os.environ["APP_ADMIN_PASSWORD"])

        if len(password) < 10:
            raise CommandError("APP_ADMIN_PASSWORD must be at least 10 characters long.")

        user = User.objects.filter(email__iexact=email).first()
        if user is None:
            # The configured email may have changed; adopt the account holding the
            # bootstrap username rather than failing on a unique-constraint clash.
            user = User.objects.filter(username__iexact=username).first()
            adopted = user is not None

        if user is None:
            try:
                user = User.objects.create_user(
                    email=email, username=username, password=password, role=Role.SUPER_ADMIN
                )
            except (ValidationError, ValueError) as exc:
                raise CommandError(f"Could not create the bootstrap administrator: {exc}") from exc
            record(AuditAction.ADMIN_BOOTSTRAPPED, target=email, detail="created")
            self.stdout.write(self.style.SUCCESS(f"Bootstrap administrator created: {email}"))
            return

        changes: list[str] = []
        if locals().get("adopted") and user.email.lower() != email:
            user.email = email
            changes.append("email")
        if user.role != Role.SUPER_ADMIN:
            user.role = Role.SUPER_ADMIN
            changes.append("role")
        if not user.is_active:
            user.is_active = True
            user.deactivated_at = None
            changes.append("is_active")
        if user.is_deleted:
            user.is_deleted = False
            changes.append("is_deleted")
        if user.username != username and not User.objects.filter(
            username__iexact=username
        ).exclude(pk=user.pk).exists():
            user.username = username
            changes.append("username")
        if options["reset_password"]:
            user.set_password(password)
            changes.append("password")

        if changes:
            user.save()
            record(AuditAction.ADMIN_BOOTSTRAPPED, target=email, detail=",".join(changes))
            self.stdout.write(
                self.style.SUCCESS(
                    f"Bootstrap administrator updated: {email} ({', '.join(changes)})"
                )
            )
        else:
            self.stdout.write(f"Bootstrap administrator already present and correct: {email}")
