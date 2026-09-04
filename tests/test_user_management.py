"""SaaS user administration: create, edit, activate, reset, delete, search."""

from __future__ import annotations

import pytest
from django.test import Client
from django.urls import reverse

from apps.accounts.models import Role, User
from apps.audit.models import AuditAction, AuditLog

pytestmark = pytest.mark.django_db


def test_create_user(client_as_super):
    response = client_as_super.post(
        reverse("useradmin:user_create"),
        {
            "email": "New.User@Example.com",
            "username": "newuser",
            "full_name": "New User",
            "role": Role.USER,
            "is_active": "on",
            "password1": "Cr3ateUser!Pass",
            "password2": "Cr3ateUser!Pass",
        },
    )
    assert response.status_code == 302
    user = User.objects.get(username="newuser")
    assert user.email == "new.user@example.com"
    assert user.check_password("Cr3ateUser!Pass")
    assert AuditLog.objects.filter(action=AuditAction.USER_CREATED).exists()


def test_create_rejects_mismatched_passwords(client_as_super):
    response = client_as_super.post(
        reverse("useradmin:user_create"),
        {
            "email": "mismatch@example.com",
            "username": "mismatch",
            "role": Role.USER,
            "password1": "Cr3ateUser!Pass",
            "password2": "Different!Pass99",
        },
    )
    assert response.status_code == 200
    assert b"do not match" in response.content
    assert not User.objects.filter(username="mismatch").exists()


def test_create_rejects_weak_password(client_as_super):
    response = client_as_super.post(
        reverse("useradmin:user_create"),
        {
            "email": "weak@example.com",
            "username": "weakuser",
            "role": Role.USER,
            "password1": "password",
            "password2": "password",
        },
    )
    assert response.status_code == 200
    assert not User.objects.filter(username="weakuser").exists()


def test_create_rejects_duplicate_email(client_as_super, normal_user):
    response = client_as_super.post(
        reverse("useradmin:user_create"),
        {
            "email": normal_user.email.upper(),
            "username": "duplicate",
            "role": Role.USER,
            "password1": "Cr3ateUser!Pass",
            "password2": "Cr3ateUser!Pass",
        },
    )
    assert response.status_code == 200
    assert b"already exists" in response.content


def test_edit_user_records_role_change(client_as_super, normal_user):
    response = client_as_super.post(
        reverse("useradmin:user_edit", args=[normal_user.pk]),
        {
            "email": normal_user.email,
            "username": normal_user.username,
            "full_name": "Promoted Person",
            "role": Role.ADMIN,
            "is_active": "on",
        },
    )
    assert response.status_code == 302
    normal_user.refresh_from_db()
    assert normal_user.role == Role.ADMIN
    assert AuditLog.objects.filter(action=AuditAction.ROLE_CHANGED).exists()


def test_toggle_active(client_as_super, normal_user):
    client_as_super.post(reverse("useradmin:user_toggle", args=[normal_user.pk]))
    normal_user.refresh_from_db()
    assert not normal_user.is_active
    assert normal_user.deactivated_at is not None

    client_as_super.post(reverse("useradmin:user_toggle", args=[normal_user.pk]))
    normal_user.refresh_from_db()
    assert normal_user.is_active and normal_user.deactivated_at is None


def test_reset_password(client_as_super, normal_user):
    response = client_as_super.post(
        reverse("useradmin:user_password", args=[normal_user.pk]),
        {"password1": "R3setThisPass!", "password2": "R3setThisPass!"},
    )
    assert response.status_code == 302
    normal_user.refresh_from_db()
    assert normal_user.check_password("R3setThisPass!")
    assert AuditLog.objects.filter(action=AuditAction.PASSWORD_RESET).exists()


def test_soft_delete_frees_email_and_blocks_login(client_as_super, normal_user):
    original_email = normal_user.email
    client_as_super.post(reverse("useradmin:user_delete", args=[normal_user.pk]))

    normal_user.refresh_from_db()
    assert normal_user.is_deleted and not normal_user.is_active
    assert normal_user.email != original_email
    assert not User.objects.filter(email=original_email).exists()

    # A fresh anonymous client: client_as_super is the same Client instance.
    response = Client().post(
        reverse("accounts:login"), {"identifier": original_email, "password": "Us3rSecret!Pass"}
    )
    assert b"Incorrect email or password" in response.content


def test_deleted_users_are_hidden_from_the_list(client_as_super, normal_user):
    client_as_super.post(reverse("useradmin:user_delete", args=[normal_user.pk]))
    response = client_as_super.get(reverse("useradmin:user_list"))
    assert normal_user.username.encode() not in response.content


def test_search_and_role_filter(client_as_super, normal_user, admin_user):
    response = client_as_super.get(reverse("useradmin:user_list"), {"q": "normaluser"})
    assert b"normaluser" in response.content
    assert b"adminuser" not in response.content

    response = client_as_super.get(reverse("useradmin:user_list"), {"role": Role.ADMIN})
    assert b"adminuser" in response.content
    assert b"normaluser" not in response.content


def test_status_filter(client_as_super, normal_user, inactive_user):
    response = client_as_super.get(reverse("useradmin:user_list"), {"status": "inactive"})
    assert b"inactiveuser" in response.content
    assert b"normaluser" not in response.content


def test_pagination_limits_rows(client_as_super):
    for index in range(12):
        User.objects.create_user(
            email=f"bulk{index}@rankvista.test",
            username=f"bulk{index}",
            password="Bulk!Password99",
        )
    response = client_as_super.get(reverse("useradmin:user_list"), {"size": 5})
    page = response.context["page_obj"]
    assert len(page.items) == 5
    assert page.num_pages >= 3
