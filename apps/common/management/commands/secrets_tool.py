"""Encrypt .env credentials and show what the app resolves, always masked.
Plaintext is read from a prompt or stdin so it never lands in shell history."""

from __future__ import annotations

import os
import sys

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError

from apps.common import secrets

MANAGED_VARS = (
    "MONGODB_PASSWORD",
    "MONGO_ROOT_PASSWORD",
    "APP_ADMIN_PASSWORD",
    "REDIS_PASSWORD",
    "SOURCE_DB_PASSWORD",
)


class Command(BaseCommand):
    help = "Encrypt a credential for .env, or show the resolved configuration masked."

    def add_arguments(self, parser) -> None:
        sub = parser.add_subparsers(dest="action", required=True)

        encrypt = sub.add_parser("encrypt", help="Emit an enc: token to paste into .env")
        encrypt.add_argument("--name", help="Variable name, for the printed hint.", default="VALUE")
        encrypt.add_argument(
            "--stdin", action="store_true", help="Read the plaintext from stdin instead of a prompt."
        )

        sub.add_parser("show", help="Show the resolved configuration with secrets masked.")
        sub.add_parser("check", help="Verify every enc: value in the environment decrypts.")

    def handle(self, *args, **options) -> None:
        action = options["action"]
        if action == "encrypt":
            self._encrypt(options)
        elif action == "show":
            self._show()
        else:
            self._check()

    def _encrypt(self, options) -> None:
        if options["stdin"]:
            plaintext = sys.stdin.read().strip()
        else:
            import getpass

            plaintext = getpass.getpass("Value to encrypt (input hidden): ").strip()
        if not plaintext:
            raise CommandError("No value supplied.")

        try:
            token = secrets.encrypt(plaintext)
        except secrets.SecretError as exc:
            raise CommandError(str(exc)) from exc

        self.stdout.write(self.style.SUCCESS("Add this line to your .env:\n"))
        self.stdout.write(f"{options['name']}={token}\n")
        self.stdout.write(
            self.style.WARNING(
                "\nKeep RANKVISTA_SECRET_KEY out of .env and out of version control. "
                "Without it this value cannot be decrypted."
            )
        )

    def _show(self) -> None:
        self.stdout.write(self.style.MIGRATE_HEADING("Resolved configuration (masked)"))
        rows = [
            ("MongoDB URI", secrets.mask_uri(settings.MONGODB["URI"])),
            ("MongoDB user", os.environ.get("MONGODB_USERNAME") or "(none)"),
            ("MongoDB database", settings.MONGODB["DATABASE"]),
            ("Redis URL", secrets.mask_uri(settings.REDIS_URL)),
            ("Warehouse host", settings.SOURCE_DB["HOST"] or "(not set)"),
            ("Warehouse database", settings.SOURCE_DB["NAME"] or "(not set)"),
            ("Warehouse user", settings.SOURCE_DB["USER"] or "(not set)"),
            ("Warehouse password", secrets.mask(settings.SOURCE_DB["PASSWORD"])),
            ("Django admin enabled", str(settings.ENABLE_DJANGO_ADMIN)),
            ("Debug", str(settings.DEBUG)),
        ]
        for label, value in rows:
            self.stdout.write(f"  {label:<22} {value}")

        self.stdout.write(self.style.MIGRATE_HEADING("\nFingerprints (compare across environments)"))
        for name in MANAGED_VARS:
            raw = os.environ.get(name)
            state = "encrypted" if (raw or "").startswith(secrets.ENC_PREFIX) else "plaintext"
            self.stdout.write(
                f"  {name:<22} {secrets.fingerprint(secrets.resolve(raw)):<14} {state}"
            )

    def _check(self) -> None:
        failures = 0
        for name in MANAGED_VARS:
            raw = os.environ.get(name) or ""
            if not raw.startswith(secrets.ENC_PREFIX):
                self.stdout.write(f"  {name:<22} plaintext (not encrypted)")
                continue
            try:
                secrets.resolve(raw)
                self.stdout.write(self.style.SUCCESS(f"  {name:<22} decrypts OK"))
            except secrets.SecretError as exc:
                failures += 1
                self.stdout.write(self.style.ERROR(f"  {name:<22} FAILED: {exc}"))
        if failures:
            raise CommandError(f"{failures} encrypted value(s) could not be decrypted.")
