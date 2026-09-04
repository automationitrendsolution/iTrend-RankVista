"""Bootstrap administrator command: idempotency, repair and safe failure."""

from __future__ import annotations

import pytest
from django.core.management import call_command
from django.core.management.base import CommandError

from apps.accounts.models import Role, User

pytestmark = pytest.mark.django_db

ENV = {
    "APP_ADMIN_EMAIL": "boot@rankvista.test",
    "APP_ADMIN_USERNAME": "bootadmin",
    "APP_ADMIN_PASSWORD": "B00tstrapPass!42",
}


@pytest.fixture
def admin_env(monkeypatch):
    for key, value in ENV.items():
        monkeypatch.setenv(key, value)
    return ENV


def test_creates_super_admin(admin_env):
    call_command("bootstrap_admin")
    user = User.objects.get(email=ENV["APP_ADMIN_EMAIL"])
    assert user.role == Role.SUPER_ADMIN
    assert user.is_active and user.is_staff and user.is_superuser


def test_password_is_hashed_never_stored_raw(admin_env):
    call_command("bootstrap_admin")
    user = User.objects.get(email=ENV["APP_ADMIN_EMAIL"])
    assert user.password != ENV["APP_ADMIN_PASSWORD"]
    assert user.check_password(ENV["APP_ADMIN_PASSWORD"])


def test_is_idempotent(admin_env):
    call_command("bootstrap_admin")
    call_command("bootstrap_admin")
    call_command("bootstrap_admin")
    assert User.objects.filter(email=ENV["APP_ADMIN_EMAIL"]).count() == 1


def test_never_prints_the_password(admin_env, capsys):
    call_command("bootstrap_admin")
    output = capsys.readouterr()
    assert ENV["APP_ADMIN_PASSWORD"] not in output.out
    assert ENV["APP_ADMIN_PASSWORD"] not in output.err


def test_repairs_demoted_or_deactivated_admin(admin_env):
    call_command("bootstrap_admin")
    User.objects.filter(email=ENV["APP_ADMIN_EMAIL"]).update(
        role=Role.USER, is_active=False, is_deleted=True
    )

    call_command("bootstrap_admin")
    user = User.objects.get(email=ENV["APP_ADMIN_EMAIL"])
    assert user.role == Role.SUPER_ADMIN
    assert user.is_active and not user.is_deleted


def test_does_not_reset_password_unless_asked(admin_env):
    call_command("bootstrap_admin")
    user = User.objects.get(email=ENV["APP_ADMIN_EMAIL"])
    user.set_password("SomethingElse!2026")
    user.save()

    call_command("bootstrap_admin")
    user.refresh_from_db()
    assert user.check_password("SomethingElse!2026")

    call_command("bootstrap_admin", "--reset-password")
    user.refresh_from_db()
    assert user.check_password(ENV["APP_ADMIN_PASSWORD"])


def test_fails_when_env_is_missing(monkeypatch):
    for key in ENV:
        monkeypatch.delenv(key, raising=False)
    with pytest.raises(CommandError, match="Missing required environment variables"):
        call_command("bootstrap_admin")


def test_skip_flag_exits_quietly(monkeypatch, capsys):
    for key in ENV:
        monkeypatch.delenv(key, raising=False)
    call_command("bootstrap_admin", "--skip-if-missing")
    assert "Skipping bootstrap" in capsys.readouterr().out
    assert User.objects.count() == 0


def test_rejects_short_password(monkeypatch):
    monkeypatch.setenv("APP_ADMIN_EMAIL", ENV["APP_ADMIN_EMAIL"])
    monkeypatch.setenv("APP_ADMIN_USERNAME", ENV["APP_ADMIN_USERNAME"])
    monkeypatch.setenv("APP_ADMIN_PASSWORD", "short")
    with pytest.raises(CommandError, match="at least 10 characters"):
        call_command("bootstrap_admin")
